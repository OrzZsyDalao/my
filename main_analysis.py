import ipaddress
import json
import os
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple

import maxminddb
import numpy as np
import pandas as pd
import pytricia
from geopy.distance import geodesic
from sklearn.neighbors import BallTree
from tqdm import tqdm

# --- 全局路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output/result')

# 输入文件目录
CABLE_DIR = os.path.join(DATA_DIR, 'cable')
TRACE_DIR = os.path.join(DATA_DIR, 'traceroute_rundnsroot')
IPINFO_DIR = os.path.join(DATA_DIR, 'ipinfo')
ASREL_DIR = os.path.join(DATA_DIR, 'asrelationship')
PFX2AS_DIR = os.path.join(DATA_DIR, 'pfx2as')
OWNER2ASN_DIR = os.path.join(DATA_DIR, 'owner2asn')

# 核心文件路径
LS_GEO_PATH = os.path.join(CABLE_DIR, 'landing-point-geo.json')
MMDB_PATH = os.path.join(IPINFO_DIR, 'ipinfo_location.mmdb')
ASREL_PATH = os.path.join(ASREL_DIR, '20250901.as-rel2.txt')
PFX2AS_PATH = os.path.join(PFX2AS_DIR, '202512.pfx2as')
OWNER2ASN_PATH = os.path.join(OWNER2ASN_DIR, 'owner_to_asn.csv')

# 输出文件路径
CABLE_DEBUG_OUTPUT_PATH = os.path.join(BASE_DIR, 'cable_loading_debug.json')
OUTPUT_RESULTS_PATH = os.path.join(OUTPUT_DIR, 'cable_matching_output.json')
MATCH_STATS_OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'cable_matching_stats_5051.json')

# 文件过滤配置
TRACEROUTE_EXCLUSIONS = ('_result.json', '_geo.json', '_analysis.json')
CABLE_EXCLUSION_FILE = 'landing-point-geo.json'


############################################################
##################### --- 数据加载 --- ######################
############################################################

def load_ls_coordinates(path: str) -> Dict[str, Tuple[float, float]]:
    """Land Station 坐标文件导入。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            ls_geo_data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到 landing-point-geo.json 文件于 {path}")

    ls_coordinates: Dict[str, Tuple[float, float]] = {}
    for feature in ls_geo_data.get('features', []):
        ls_id = feature['properties']['id']
        lon, lat = feature['geometry']['coordinates']
        ls_coordinates[ls_id] = (lat, lon)
    return ls_coordinates


def load_all_cables(directory: str) -> List[Dict[str, Any]]:
    """加载海缆 JSON 文件。"""
    all_cables = []
    try:
        for filename in os.listdir(directory):
            if filename.endswith('.json') and filename != CABLE_EXCLUSION_FILE:
                file_path = os.path.join(directory, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        cable_data = json.load(f)
                        cable_id = cable_data.get('id', 'Unknown')
                        cable_name = cable_data.get('name', cable_id)
                        owners = cable_data.get('owners', [])
                        ls_points = [
                            point['id']
                            for point in cable_data.get('landing_points', [])
                            if point.get('id')
                        ]
                        all_cables.append({
                            'id': cable_id,
                            'name': cable_name,
                            'owners': owners,
                            'ls_points': ls_points,
                        })
                    except json.JSONDecodeError:
                        # 保持原有宽松行为：坏文件直接跳过。
                        pass
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 海缆目录 {directory} 未找到。")
    return all_cables


def load_as_relationship(path: str) -> Dict[Tuple[str, str], int]:
    """加载 CAIDA AS Relationship 数据。"""
    as_relations: Dict[Tuple[str, str], int] = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('|')
                if len(parts) >= 3:
                    as_a, as_b, rel_type = parts[0], parts[1], parts[2]
                    as_relations[(as_a, as_b)] = int(rel_type)
                    as_relations[(as_b, as_a)] = -int(rel_type)
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到 AS 关系文件于 {path}")
    return as_relations


def load_pfx2as_mapping(path: str) -> pytricia.PyTricia:
    """加载 pfx2as 到 PyTricia。"""
    trie = pytricia.PyTricia(32)
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                prefix, length, asn = line.split()
            except ValueError:
                continue
            if ':' in prefix:
                # 当前实现仍然只做 IPv4。
                continue
            asn = asn.strip('{}').split('_')[0]
            trie[f"{prefix}/{length}"] = asn
    return trie


def load_owner2asn_mapping(path: str) -> Dict[str, Set[str]]:
    """加载 owner -> ASN 映射。"""
    owner2asn: Dict[str, Set[str]] = {}
    try:
        df = pd.read_csv(
            path,
            dtype={'owner': str, 'asn': str},
            usecols=['owner', 'asn'],
            keep_default_na=False,
            encoding='utf-8'
        )
        df['owner'] = df['owner'].str.strip()
        df['asn'] = df['asn'].str.strip()
        for _, row in df.iterrows():
            owner = row['owner']
            asn = row['asn']
            if pd.isna(owner) or pd.isna(asn) or owner == '' or asn == '':
                continue
            owner2asn.setdefault(owner, set()).add(asn)
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到 Owner to ASN 文件于 {path}")
    return owner2asn


############################################################
##################### --- 辅助函数 --- ######################
############################################################

def stream_json_array(path: str) -> Generator[Dict[str, Any], None, None]:
    """
    [保留] 关键流式读取生成器。
    逐行读取大型 JSON 数组文件，避免一次性加载导致的内存溢出。

    当前主流程优先尝试 json.load 读取 traceroute 文件；
    这个生成器保留，方便未来切换到 jsonl / 超大数组文件，
    也作为 json.load 失败后的兜底方案。
    """
    if not os.path.exists(path):
        return

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line == '[' or line == ']' or not line:
                continue
            if line.endswith(','):
                line = line[:-1]
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_traceroute_results(path: str) -> Generator[Dict[str, Any], None, None]:
    """
    统一的 traceroute 结果迭代器。

    优先使用 json.load 读取标准 JSON / JSON 数组文件；
    如果失败，则回退到 stream_json_array 做流式解析。
    这样既兼容常见数组文件，也兼容部分超大文件/半结构化文件。
    """
    if not os.path.exists(path):
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    yield item
        elif isinstance(payload, dict):
            yield payload
        return
    except Exception:
        # 回退到流式逐行解析
        pass

    for item in stream_json_array(path):
        if isinstance(item, dict):
            yield item


def is_private_or_special_ip(ip_address: str) -> bool:
    """
    判断 IP 是否属于私网/保留/特殊地址。
    这样比直接 startswith('172.') 更准确。
    """
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    except ValueError:
        return True


def get_geo_info(ip_address: str, mmdb_reader: maxminddb.Reader) -> Dict[str, Any]:
    """查询 IP 的地理信息。"""
    geo_data = {'lat': None, 'lon': None, 'asn': None, 'country': None, 'city': None}
    if not ip_address or is_private_or_special_ip(ip_address):
        return geo_data

    try:
        record = mmdb_reader.get(ip_address)
        if record:
            geo_data['lat'] = record.get('latitude')
            geo_data['lon'] = record.get('longitude')
            geo_data['country'] = record.get('country_code')
            geo_data['city'] = record.get('city')
            if 'traits' in record and 'autonomous_system_number' in record['traits']:
                geo_data['asn'] = f"AS{record['traits']['autonomous_system_number']}"
    except Exception:
        # 保持原有宽松行为：查询异常时返回空 geo。
        pass
    return geo_data


def parse_hops_to_links(
    hops: List[Dict[str, Any]],
    msm_id: str,
    prb_id: str,
    timestamp: str,
    file_name: str,
    mmdb_reader: maxminddb.Reader,
) -> List[Dict[str, Any]]:
    """
    [核心逻辑] 将 Traceroute Hops 转换为 Links，并进行地理定位。
    只有当两个连续的 Hop 都有坐标时，才生成链路。
    """
    parsed_links: List[Dict[str, Any]] = []
    previous_rtt = 0.0
    previous_hop_info: Optional[Dict[str, Any]] = None

    for hop_data in hops:
        # 1. 提取基础数据
        rtt_results = [r.get('rtt') for r in hop_data.get('result', []) if r.get('rtt') is not None]
        ip = hop_data.get('result', [{}])[0].get('from')

        if not ip or not rtt_results:
            previous_hop_info = None
            continue

        # 使用最小 RTT，较少受单次回包抖动影响。
        rtt = min(rtt_results)

        # 2. 执行地理查询
        current_hop_info = {
            'ip': ip,
            'rtt': rtt,
            'geo': get_geo_info(ip, mmdb_reader),
            'hop_num': hop_data['hop']
        }

        # 3. 严格连续性检查：R_i 和 R_{i+1} 都必须有地理坐标
        is_previous_geolocated = previous_hop_info and previous_hop_info['geo']['lat'] is not None
        is_current_geolocated = current_hop_info['geo']['lat'] is not None

        if is_previous_geolocated and is_current_geolocated:
            rtt_delta = rtt - previous_rtt
            # RTT 增量判断潜在跨洋链路 (15ms 阈值)
            is_potential_oceanic = rtt_delta > 15.0

            link = {
                'source': previous_hop_info,
                'destination': current_hop_info,
                'rtt_delta': rtt_delta,
                'ips': (previous_hop_info['ip'], current_hop_info['ip']),
                'is_oceanic': is_potential_oceanic,
                'measurement_id': msm_id,
                'probe_id': prb_id,
                'timestamp': timestamp,
                'file_name': file_name,
            }
            parsed_links.append(link)

        previous_rtt = rtt
        previous_hop_info = current_hop_info

    return parsed_links


def process_single_traceroute_file(path: str, mmdb_reader: maxminddb.Reader) -> List[Dict[str, Any]]:
    """
    [保留] 处理单个 traceroute 文件并提取 links。
    当前 main 已改成“逐条 traceroute 记录”处理；
    这个函数保留，方便未来做文件级批处理对照实验。
    """
    all_links: List[Dict[str, Any]] = []
    file_name = os.path.basename(path)

    for result_data in iter_traceroute_results(path):
        if result_data.get('result'):
            msm_id = result_data.get('msm_id', 'N/A')
            prb_id = result_data.get('prb_id', 'N/A')
            timestamp = result_data.get('timestamp', 'N/A')
            hops = result_data['result']

            links_from_run = parse_hops_to_links(
                hops=hops,
                msm_id=msm_id,
                prb_id=prb_id,
                timestamp=timestamp,
                file_name=file_name,
                mmdb_reader=mmdb_reader,
            )
            all_links.extend(links_from_run)

    return all_links


# --- 阶段二：核心匹配器 (CableMatcher Class) ---

class CableMatcher:
    # 物理常数和超参数
    SOL_FIBER_KM_MS = 200.0   # 光纤中的光速 (km/ms)
    SLACK_FACTOR = 1.2        # 光纤松弛因子
    LS_CATCHMENT_RADIUS_KM = 100.0  # LS 集水区查询半径 (km)
    R_EARTH = 6371.0          # 地球半径 (km)

    # 匹配阈值与置信度分桶阈值
    MATCH_THRESHOLD = 0.5
    HIGH_CONF_THRESHOLD = 0.7
    MEDIUM_CONF_THRESHOLD = 0.5
    HIGH_GAP_THRESHOLD = 0.2
    MEDIUM_GAP_THRESHOLD = 0.1

    def __init__(
        self,
        processed_cables: List[Dict[str, Any]],
        ls_coordinates: Dict[str, Tuple[float, float]],
        as_relationship: Dict[Tuple[str, str], int],
        pfx2as_trie: pytricia.PyTricia,
        owner2asn: Dict[str, Set[str]],
    ):
        self.all_cables = processed_cables
        self.ls_geo = ls_coordinates
        self.as_relationship = as_relationship
        self.pfx2as_trie = pfx2as_trie
        self.owner2asn = owner2asn

        # 统计 coverage / pruning 的计数器
        self.stats = {
            'total_links_seen': 0,
            'same_city_filtered': 0,
            'links_with_ls_candidates': 0,  # 更准确地说，这是双端都有 landing-station 邻域的 link 数
            'candidate_segments_considered': 0,
            'rtt_infeasible_filtered': 0,
            'links_below_threshold': 0,
            'candidates_above_threshold': 0,
            'links_with_any_match': 0,
        }

        # 1. 初始化 BallTree 结构
        ls_ids = list(self.ls_geo.keys())
        ls_coords_rad = np.radians([self.ls_geo[ls_id] for ls_id in ls_ids])
        self.ls_tree = BallTree(ls_coords_rad, metric='haversine')
        self.ls_id_map = {i: ls_id for i, ls_id in enumerate(ls_ids)}
        self.ls_coord_map = {ls_id: self.ls_geo[ls_id] for ls_id in ls_ids}

        # 2. 预计算 LS Segment -> Cable 的映射
        self.segment_to_cables: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.gcd_cache: Dict[Tuple[str, str], float] = {}
        shortest_gcd_tracker: Dict[Tuple[str, str], float] = {}

        for cable in self.all_cables:
            points = cable['ls_points']
            for i in range(len(points)):
                for j in range(i + 1, len(points)):
                    ls_a = points[i]
                    ls_b = points[j]
                    if ls_a == ls_b or ls_a not in self.ls_geo or ls_b not in self.ls_geo:
                        continue

                    segment = tuple(sorted((ls_a, ls_b)))

                    if segment in self.gcd_cache:
                        gcd_dist = self.gcd_cache[segment]
                    else:
                        gcd_dist = geodesic(self.ls_geo[ls_a], self.ls_geo[ls_b]).km
                        self.gcd_cache[segment] = gcd_dist

                    new_cable_info = {
                        'cable_id': cable['id'],
                        'cable_name': cable['name'],
                        'cable_owners': cable['owners'],
                        'gcd_dist': gcd_dist,
                    }

                    if segment not in shortest_gcd_tracker:
                        shortest_gcd_tracker[segment] = gcd_dist
                        self.segment_to_cables[segment] = [new_cable_info]
                    else:
                        current_shortest_gcd = shortest_gcd_tracker[segment]
                        if gcd_dist < current_shortest_gcd:
                            shortest_gcd_tracker[segment] = gcd_dist
                            self.segment_to_cables[segment] = [new_cable_info]
                        elif abs(gcd_dist - current_shortest_gcd) < 0.01:
                            existing_ids = {info['cable_id'] for info in self.segment_to_cables[segment]}
                            if cable['id'] not in existing_ids:
                                self.segment_to_cables[segment].append(new_cable_info)

    def IP2ASN(self, ip: str) -> str:
        try:
            asn = self.pfx2as_trie.get(ip)
            return asn if asn else '-1'
        except Exception:
            return '-1'

    def asRelationship_prob_calculation(self, asn1: str, asn2: str, cable_owners: Set[str]) -> float:
        """
        [保留并整理] Discrete Economic Incentive Model based on BGP LocalPref.
        与其输出严格概率，这里更适合作为 ownership / relationship evidence score。
        """
        a1, a2 = str(asn1), str(asn2)

        # --- Tier 1: Self-Owned (Cost = 0) ---
        is_a1_owner = a1 in cable_owners
        is_a2_owner = a2 in cable_owners
        if is_a1_owner and is_a2_owner:
            return 1.0
        if is_a1_owner or is_a2_owner:
            return 0.95

        # --- Check Relations ---
        rel_type = None
        if (a1, a2) in self.as_relationship:
            rel_type = self.as_relationship[(a1, a2)]
        elif (a2, a1) in self.as_relationship:
            rel_type = self.as_relationship[(a2, a1)]

        # --- Tier 2: Peering ---
        if rel_type == 0:
            return 0.8

        # --- Tier 3: Transit ---
        if rel_type == 1 or rel_type == -1:
            return 0.7

        # --- Tier 4: No direct relation, but owner affinity exists ---
        for owner in cable_owners:
            owner_str = str(owner)
            if (a1, owner_str) in self.as_relationship or (owner_str, a1) in self.as_relationship:
                return 0.6
            if (a2, owner_str) in self.as_relationship or (owner_str, a2) in self.as_relationship:
                return 0.6

        return 0.5

    def match_link_to_cable(self, link: Dict[str, Any]) -> Dict[str, Any]:
        """
        对单条 hop-pair 链路进行匹配。

        返回值分两层：
        1. all_segments: 通过阈值的候选 segment 列表
        2. match_summary: 用于后续 uncertainty / robustness 分析的概要信息
        """
        self.stats['total_links_seen'] += 1

        hop_a = link['source']
        hop_b = link['destination']
        measured_rtt_delta = link['rtt_delta']

        city_a = hop_a['geo'].get('city')
        city_b = hop_b['geo'].get('city')
        country_a = hop_a['geo'].get('country')
        country_b = hop_b['geo'].get('country')

        # 【条件 1】同城且同国，视为 metro/internal link，直接过滤。
        if city_a and city_b and country_a and country_b and city_a == city_b and country_a == country_b:
            self.stats['same_city_filtered'] += 1
            return {
                'all_segments': [],
                'match_summary': {
                    'filtered_reason': 'same_city',
                    'num_candidates_total': 0,
                    'num_candidates_above_threshold': 0,
                    'top1_score': 0.0,
                    'top2_score': 0.0,
                    'top1_top2_gap': 0.0,
                    'confidence_bucket': 'none',
                }
            }

        candidates: List[Dict[str, Any]] = []
        radius_rad = self.LS_CATCHMENT_RADIUS_KM / self.R_EARTH

        hop_a_loc = (np.radians(hop_a['geo']['lat']), np.radians(hop_a['geo']['lon']))
        hop_b_loc = (np.radians(hop_b['geo']['lat']), np.radians(hop_b['geo']['lon']))

        idx_a_list = self.ls_tree.query_radius([hop_a_loc], r=radius_rad)[0]
        idx_b_list = self.ls_tree.query_radius([hop_b_loc], r=radius_rad)[0]

        if len(idx_a_list) > 0 and len(idx_b_list) > 0:
            self.stats['links_with_ls_candidates'] += 1

        entries_a = []
        for i in idx_a_list:
            ls_id = self.ls_id_map[i]
            d_in = geodesic((hop_a['geo']['lat'], hop_a['geo']['lon']), self.ls_coord_map[ls_id]).km
            entries_a.append((ls_id, d_in))

        entries_b = []
        for i in idx_b_list:
            ls_id = self.ls_id_map[i]
            d_out = geodesic((hop_b['geo']['lat'], hop_b['geo']['lon']), self.ls_coord_map[ls_id]).km
            entries_b.append((ls_id, d_out))

        ips = link['ips']
        asn_a = self.IP2ASN(ips[0])
        asn_b = self.IP2ASN(ips[1])

        for ls_a_id, d_in in entries_a:
            for ls_b_id, d_out in entries_b:
                if ls_a_id == ls_b_id:
                    continue

                segment_key = tuple(sorted((ls_a_id, ls_b_id)))
                if segment_key not in self.segment_to_cables:
                    continue

                # [保留] Butterworth 风格衰减：对 entry 和 exit 分别评分，再取几何平均。
                decay_cutoff_km = 100.0
                decay_steepness = 2.0
                prob_in = 1.0 / (1.0 + (d_in / decay_cutoff_km) ** decay_steepness)
                prob_out = 1.0 / (1.0 + (d_out / decay_cutoff_km) ** decay_steepness)
                prob_geo = np.sqrt(prob_in * prob_out)

                for cable_info in self.segment_to_cables[segment_key]:
                    self.stats['candidate_segments_considered'] += 1

                    gcd_dist = cable_info['gcd_dist']
                    est_fiber_len = gcd_dist * self.SLACK_FACTOR
                    min_rtt = (est_fiber_len * 2) / self.SOL_FIBER_KM_MS
                    rtt_margin = measured_rtt_delta - min_rtt

                    if measured_rtt_delta < min_rtt:
                        self.stats['rtt_infeasible_filtered'] += 1
                        continue

                    # [保留] Latency Inflation Penalty
                    inflation_ratio = measured_rtt_delta / min_rtt if min_rtt > 0 else float('inf')
                    latency_penalty = 1.0
                    if min_rtt < 5.0 and inflation_ratio > 20.0:
                        latency_penalty = 0.5

                    cable_owner_asn: Set[str] = set()
                    for owner in cable_info['cable_owners']:
                        if owner in self.owner2asn:
                            for asn in self.owner2asn[owner]:
                                cable_owner_asn.add(asn)

                    prob_ownership = self.asRelationship_prob_calculation(asn_a, asn_b, cable_owner_asn)

                    # [保留] Geo-Dominance Override
                    min_prob_geo = min(prob_in, prob_out)
                    if min_prob_geo >= 0.9:
                        prob_ownership = max(prob_ownership, 0.8)

                    final_segment_probability = prob_geo * prob_ownership * latency_penalty

                    candidates.append({
                        'cable_name': cable_info['cable_name'],
                        'cable_id': cable_info['cable_id'],
                        'segment': f"{ls_a_id} -> {ls_b_id}",
                        'segment_probability': float(f"{final_segment_probability:.6f}"),

                        # score decomposition
                        'geo_score': float(f"{prob_geo:.6f}"),
                        'ownership_score': float(f"{prob_ownership:.6f}"),
                        'latency_penalty': float(f"{latency_penalty:.6f}"),

                        # RTT evidence
                        'rtt_feasible': True,
                        'min_rtt_ms': float(f"{min_rtt:.4f}"),
                        'measured_rtt_ms': float(f"{measured_rtt_delta:.4f}"),
                        'rtt_margin_ms': float(f"{rtt_margin:.4f}"),

                        # ASN context
                        'src_asn': asn_a,
                        'dst_asn': asn_b,
                        'owner_asn_count': len(cable_owner_asn),

                        # geo / context
                        'city_a': city_a,
                        'city_b': city_b,
                        'country_a': country_a,
                        'country_b': country_b,
                        'geo-a': (float(f"{hop_a['geo']['lat']:.4f}"), float(f"{hop_a['geo']['lon']:.4f}")),
                        'geo-b': (float(f"{hop_b['geo']['lat']:.4f}"), float(f"{hop_b['geo']['lon']:.4f}")),
                        'd_in': float(f"{d_in:.2f}"),
                        'd_out': float(f"{d_out:.2f}"),
                        'ls_entry_to_ls_exit_gcd_km': float(f"{gcd_dist:.2f}"),
                    })

        if not candidates:
            return {
                'all_segments': [],
                'match_summary': {
                    'filtered_reason': 'no_candidate',
                    'num_candidates_total': 0,
                    'num_candidates_above_threshold': 0,
                    'top1_score': 0.0,
                    'top2_score': 0.0,
                    'top1_top2_gap': 0.0,
                    'confidence_bucket': 'none',
                }
            }

        # 先按概率降序排列，再按 cable_id 去重，保留每条 cable 的最佳 candidate。
        sorted_candidates = sorted(candidates, key=lambda x: x.get('segment_probability', 0), reverse=True)

        deduplicated_candidates: Dict[str, Dict[str, Any]] = {}
        unique_list: List[Dict[str, Any]] = []
        for cand in sorted_candidates:
            cid = cand['cable_id']
            if cid not in deduplicated_candidates:
                deduplicated_candidates[cid] = cand
                unique_list.append(cand)

        filtered_candidates = [
            c for c in unique_list if c.get('segment_probability', 0) >= self.MATCH_THRESHOLD
        ]

        if unique_list and not filtered_candidates:
            self.stats['links_below_threshold'] += 1

        self.stats['candidates_above_threshold'] += len(filtered_candidates)
        if filtered_candidates:
            self.stats['links_with_any_match'] += 1

        top1 = filtered_candidates[0]['segment_probability'] if len(filtered_candidates) >= 1 else 0.0
        top2 = filtered_candidates[1]['segment_probability'] if len(filtered_candidates) >= 2 else 0.0
        gap = top1 - top2

        if top1 >= self.HIGH_CONF_THRESHOLD and gap >= self.HIGH_GAP_THRESHOLD:
            bucket = 'high'
        elif top1 >= self.MEDIUM_CONF_THRESHOLD and gap >= self.MEDIUM_GAP_THRESHOLD:
            bucket = 'medium'
        elif filtered_candidates:
            bucket = 'ambiguous'
        else:
            bucket = 'none'

        for rank, candidate in enumerate(filtered_candidates, start=1):
            candidate['candidate_rank'] = rank
            candidate['score_gap_to_top1'] = float(f"{top1 - candidate['segment_probability']:.6f}")

        return {
            'all_segments': filtered_candidates,
            'match_summary': {
                'filtered_reason': None if filtered_candidates else 'below_threshold',
                'num_candidates_total': len(unique_list),
                'num_candidates_above_threshold': len(filtered_candidates),
                'top1_score': float(f"{top1:.6f}"),
                'top2_score': float(f"{top2:.6f}"),
                'top1_top2_gap': float(f"{gap:.6f}"),
                'confidence_bucket': bucket,
            }
        }


# --- 阶段四：主程序和调试输出函数 ---

def output_debug_cable_info(ls_coords: Dict[str, Tuple[float, float]], cables: List[Dict[str, Any]], path: str):
    """输出海缆和着陆点信息到单独的调试文件。"""
    debug_data = {
        'landing_station_count': len(ls_coords),
        'submarine_cable_count': len(cables),
        'landing_station_sample': {k: v for i, (k, v) in enumerate(ls_coords.items()) if i < 5},
        'submarine_cable_sample': cables[:2],
        'all_cables': cables,
    }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=4)
        print(f"✅ 海缆/着陆点调试信息已输出至: {path}")
    except Exception as e:
        print(f"❌ 调试文件写入失败: {e}")


def load_all_traceroute_files(directory: str) -> List[str]:
    """遍历 traceroute 目录，加载所有符合条件的 JSON 文件路径。"""
    traceroute_files: List[str] = []

    if not os.path.exists(directory):
        print(f"⚠️ 警告: Traceroute 目录 {directory} 不存在!")
        return []

    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.endswith('.json'):
                is_excluded = any(filename.endswith(suffix) for suffix in TRACEROUTE_EXCLUSIONS)
                if not is_excluded:
                    traceroute_files.append(os.path.join(root, filename))

    # 保留原来的“用户上传示例文件”兜底逻辑，但不再强依赖它。
    user_uploaded_files = [
        'ripe_atlas_msm_104851959_traceroute_A-Root.json',
        '2africa.json',
    ]
    existing_basenames = {os.path.basename(p) for p in traceroute_files}
    for filename in user_uploaded_files:
        candidate_path = os.path.join(BASE_DIR, filename)
        if os.path.exists(candidate_path) and filename not in existing_basenames:
            traceroute_files.append(candidate_path)

    return traceroute_files


def main():
    """主执行函数：处理所有有效链路，并输出匹配结果和统计信息。"""
    # 1. 基础数据加载和检查
    try:
        ls_coordinates = load_ls_coordinates(LS_GEO_PATH)
        all_cables = load_all_cables(CABLE_DIR)
        as_relationship = load_as_relationship(ASREL_PATH)
        pfx2as_trie = load_pfx2as_mapping(PFX2AS_PATH)
        owner2asn = load_owner2asn_mapping(OWNER2ASN_PATH)
    except FileNotFoundError as e:
        print('--- ⚠️ 严重错误：基础文件加载失败 ---')
        print(str(e))
        return

    # 输出海缆和着陆点调试信息
    output_debug_cable_info(ls_coordinates, all_cables, CABLE_DEBUG_OUTPUT_PATH)

    # 2. 实例化匹配器 (BallTree 结构在此处构建)
    matcher = CableMatcher(all_cables, ls_coordinates, as_relationship, pfx2as_trie, owner2asn)

    # 3. 遍历 traceroute 文件并处理 (采用增量输出)
    traceroute_file_paths = load_all_traceroute_files(TRACE_DIR)

    print('\n--- 海缆匹配任务开始 ---')
    print(f'共识别到 {len(traceroute_file_paths)} 个 traceroute 文件待处理。')
    print(f'链路匹配结果将增量输出至: {OUTPUT_RESULTS_PATH}')
    print('------------------------')

    valid_link_count = 0
    total_files_processed = 0
    total_traces_processed = 0
    empty_trace_count = 0
    is_first_entry = True

    try:
        os.makedirs(os.path.dirname(OUTPUT_RESULTS_PATH), exist_ok=True)

        with maxminddb.open_database(MMDB_PATH) as mmdb_reader:
            with open(OUTPUT_RESULTS_PATH, 'w', encoding='utf-8') as output_file:
                output_file.write('[\n')

                # 改为“按 traceroute 记录”更新进度，而不是“按文件”更新。
                # 这里不预扫总量，避免额外全盘读取一遍文件；tqdm 会显示已处理条数和速率。
                with tqdm(desc='处理 traceroute 记录', unit=' trace', dynamic_ncols=True, mininterval=10.0, miniters=5000) as pbar:
                    for tr_path in traceroute_file_paths:
                        total_files_processed += 1
                        file_name = os.path.basename(tr_path)

                        file_trace_count = 0
                        file_matched_link_count = 0

                        for raw_result in iter_traceroute_results(tr_path):
                            file_trace_count += 1
                            total_traces_processed += 1

                            # 每扫描一条 traceroute 记录就更新一次进度条
                            pbar.update(1)

                            msm_id = raw_result.get('msm_id', 'N/A')
                            prb_id = raw_result.get('prb_id', 'N/A')
                            timestamp = raw_result.get('endtime', raw_result.get('timestamp', 'N/A'))
                            hops = raw_result.get('result', [])

                            if not hops:
                                empty_trace_count += 1
                                # pbar.set_postfix({
                                #     'file': file_name[:20],
                                #     'matched_links': valid_link_count,
                                #     'empty_traces': empty_trace_count,
                                # })
                                continue

                            traceroute_links = parse_hops_to_links(
                                hops=hops,
                                msm_id=msm_id,
                                prb_id=prb_id,
                                timestamp=timestamp,
                                file_name=file_name,
                                mmdb_reader=mmdb_reader,
                            )

                            for link in traceroute_links:
                                match_output = matcher.match_link_to_cable(link)
                                all_segments = match_output['all_segments']
                                match_summary = match_output['match_summary']

                                if all_segments:
                                    valid_link_count += 1
                                    file_matched_link_count += 1

                                    link_info = {
                                        'msm_id': link.get('measurement_id', 'N/A'),
                                        'probe_id': link.get('probe_id', 'N/A'),
                                        'file_name': link.get('file_name', file_name),
                                        'timestamp': link.get('timestamp', 'N/A'),
                                        'hop_range': f"Hop {link['source']['hop_num']} -> {link['destination']['hop_num']}",
                                        'src_ip': link['source']['ip'],
                                        'dst_ip': link['destination']['ip'],
                                        'src_city': link['source']['geo'].get('city'),
                                        'dst_city': link['destination']['geo'].get('city'),
                                        'src_country': link['source']['geo']['country'],
                                        'dst_country': link['destination']['geo']['country'],
                                        'rtt_delta_ms': link['rtt_delta'],
                                        'is_potential_oceanic': link['is_oceanic'],
                                    }

                                    match_result = {
                                        'link_info': link_info,
                                        'match_summary': match_summary,
                                        'all_segments': all_segments,
                                    }

                                    if not is_first_entry:
                                        output_file.write(',\n')

                                    json.dump(match_result, output_file, ensure_ascii=False, indent=4)
                                    is_first_entry = False

                            # pbar.set_postfix({
                            #     'file': file_name[:20],
                            #     'matched_links': valid_link_count,
                            #     'file_traces': file_trace_count,
                            #     'file_matches': file_matched_link_count,
                            # })

                output_file.write('\n]\n')

        with open(MATCH_STATS_OUTPUT_PATH, 'w', encoding='utf-8') as stats_file:
            json.dump(matcher.stats, stats_file, ensure_ascii=False, indent=4)

    except Exception as e:
        print(f'\n❌ 结果文件写入失败: {e}')
        return

    print(f'\n✅ 匹配完成。总共扫描了 {total_files_processed} 个 traceroute 文件。')
    print(f'✅ 总共扫描了 {total_traces_processed} 条 traceroute 记录。')
    print(f'✅ 其中空/无效 traceroute 记录数: {empty_trace_count}')
    print(f'✅ 找到 {valid_link_count} 条达到匹配阈值 (>= {matcher.MATCH_THRESHOLD}) 的海缆链路。')
    print(f'✅ 结果已保存至: {OUTPUT_RESULTS_PATH}')
    print(f'✅ 匹配统计已保存至: {MATCH_STATS_OUTPUT_PATH}')


if __name__ == '__main__':
    main()
