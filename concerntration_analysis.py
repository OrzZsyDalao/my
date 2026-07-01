import argparse
import ipaddress
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import maxminddb
import pandas as pd
try:
    import pytricia
except ImportError:
    pytricia = None
from tqdm import tqdm


# --- [默认配置区域] ---
DEFAULT_FLAG_CROSS_COUNTRY = True

# Default to the smaller traceroute source for routine testing.
DEFAULT_RAW_TRACES_FILE = "./data/traceroute_rundnsroot/root_dns_traces.json"
DEFAULT_MATCH_OUTPUT_FILE = "./output/result/cable_matching_output.json"
DEFAULT_PROBE_META_FILE = "./data/probe/20251201.json"
DEFAULT_OUTPUT_CSV = "./output/result/country_root_cable_dependency_hybrid.csv"

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
DATA_DIR = os.path.join(BASE_DIR, 'data')
IPINFO_DIR = os.path.join(DATA_DIR, 'ipinfo')
CABLE_DIR = os.path.join(DATA_DIR, 'cable')
PFX2AS_DIR = os.path.join(DATA_DIR, 'pfx2as')

DEFAULT_MMDB_PATH = os.path.join(IPINFO_DIR, 'ipinfo_location.mmdb')
DEFAULT_CABLE_DIR = CABLE_DIR
DEFAULT_PFX2AS_PATH = os.path.join(PFX2AS_DIR, '202512.pfx2as')

# --- [默认] 聚合与过滤配置 ---
DEFAULT_AGGREGATION_MODE = "weighted"
DEFAULT_MATCH_THRESHOLD = 0.5
DEFAULT_ONLY_CONFIDENCE_BUCKET = None
DEFAULT_SUMMARY_JSON = None

# owner 聚合模式默认仍然是 full：
# 只要 owner 参与拥有该 cable，就继承该 cable 的归一化概率
DEFAULT_OWNER_MULTI_ENTITY_MODE = "full"

CABLE_EXCLUSION_FILE = 'landing-point-geo.json'


class IPv4PrefixLookup:
    """Fallback longest-prefix matcher used when pytricia is unavailable."""

    def __init__(self, max_bits: int = 32):
        self.max_bits = max_bits
        self._prefix_maps: Dict[int, Dict[int, str]] = {}
        self._masks = {
            prefix_len: ((0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF) if prefix_len > 0 else 0
            for prefix_len in range(max_bits + 1)
        }

    def __setitem__(self, cidr: str, value: str) -> None:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.version != 4:
            return
        prefix_len = network.prefixlen
        network_int = int(network.network_address)
        self._prefix_maps.setdefault(prefix_len, {})[network_int] = value

    def get(self, ip_address: str) -> Optional[str]:
        try:
            ip_obj = ipaddress.ip_address(ip_address)
        except ValueError:
            return None

        if ip_obj.version != 4:
            return None

        ip_int = int(ip_obj)
        for prefix_len in range(self.max_bits, -1, -1):
            mask = self._masks[prefix_len]
            network_int = ip_int & mask
            prefix_bucket = self._prefix_maps.get(prefix_len)
            if prefix_bucket and network_int in prefix_bucket:
                return prefix_bucket[network_int]
        return None

# Root 映射表
MSM_TO_TARGET = {
    5001: "K-Root", 5004: "F-Root", 5005: "I-Root", 5006: "M-Root",
    5008: "L-Root", 5009: "A-Root", 5010: "B-Root", 5011: "C-Root",
    5012: "D-Root", 5013: "E-Root", 5014: "G-Root", 5015: "H-Root",
    5016: "J-Root",
    1591146: "8.8.8.8",
    5051: "anchor"
}


def is_private_or_special_ip(ip_address: str) -> bool:
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
        pass
    return geo_data


def load_probe_metadata(filepath: str) -> Dict[str, str]:
    print(f"📡 正在加载探针元数据: {filepath} ...")
    probe_map: Dict[str, str] = {}

    if not os.path.exists(filepath):
        filepath = os.path.basename(filepath)

    if not os.path.exists(filepath):
        print("⚠️ 警告: 找不到探针文件。")
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            objects = data.get("objects", []) if isinstance(data, dict) else data
            for p in objects:
                if p.get("id") and p.get("country_code"):
                    probe_map[str(p["id"])] = p["country_code"]
        print(f"✅ 已加载 {len(probe_map)} 个探针。")
        return probe_map
    except Exception as e:
        print(f"❌ 加载探针失败: {e}")
        return {}


def load_pfx2as_mapping(path: str) -> Optional[Any]:
    if not path:
        print("⚠️ 未提供 pfx2as 文件，逻辑层 AS-pair 特征将被跳过。")
        return None
    if not os.path.exists(path):
        print(f"⚠️ 找不到 pfx2as 文件: {path}，逻辑层 AS-pair 特征将被跳过。")
        return None

    print(f"🧭 正在加载 pfx2as: {path} ...")
    trie = pytricia.PyTricia(32) if pytricia is not None else IPv4PrefixLookup(32)
    count = 0
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
                continue  # 当前只做 IPv4
            asn = asn.strip('{}').split('_')[0]
            trie[f"{prefix}/{length}"] = asn
            count += 1
    print(f"✅ 已加载 {count} 条 pfx2as 前缀。")
    return trie


def ip_to_asn(ip_address: str, pfx2as_trie: Optional[Any]) -> Optional[str]:
    if not ip_address or is_private_or_special_ip(ip_address) or pfx2as_trie is None:
        return None
    try:
        asn = pfx2as_trie.get(ip_address)
        if not asn:
            return None
        asn = str(asn).strip()
        if not asn or asn == '-1':
            return None
        return asn if asn.startswith('AS') else f"AS{asn}"
    except Exception:
        return None


def normalize_owners_field(raw_owners: Any) -> List[str]:
    if raw_owners is None:
        return []

    if isinstance(raw_owners, str):
        owners = [o.strip() for o in raw_owners.split(',')]
        return [o for o in owners if o]

    if isinstance(raw_owners, list):
        out = []
        for item in raw_owners:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
            else:
                s = str(item).strip()
                if s:
                    out.append(s)
        return out

    s = str(raw_owners).strip()
    if not s:
        return []
    return [o.strip() for o in s.split(',') if o.strip()]


def load_cable_owner_mapping(cable_dir: str) -> Dict[str, Dict[str, Any]]:
    print(f"🧵 正在加载 cable owner 元数据: {cable_dir} ...")
    mapping: Dict[str, Dict[str, Any]] = {}

    if not os.path.exists(cable_dir):
        print("⚠️ cable 目录不存在，将无法回填 owner 信息。")
        return mapping

    count = 0
    for filename in os.listdir(cable_dir):
        if not filename.endswith('.json'):
            continue
        if filename == CABLE_EXCLUSION_FILE:
            continue

        path = os.path.join(cable_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cable = json.load(f)

            cable_id = cable.get('id')
            cable_name = cable.get('name')
            owners = normalize_owners_field(cable.get('owners', []))

            item = {
                "cable_id": cable_id,
                "cable_name": cable_name,
                "owners": owners,
            }

            if cable_id:
                mapping[f"id::{cable_id}"] = item
            if cable_name:
                mapping[f"name::{cable_name}"] = item

            count += 1
        except Exception:
            continue

    print(f"✅ 已加载 {count} 条 cable 元数据。")
    return mapping


def get_root_name(item: Dict[str, Any]) -> Optional[str]:
    msm_id = item.get('msm_id')
    if msm_id is None:
        link_info = item.get('link_info', {})
        msm_id = link_info.get('msm_id')

    if msm_id is not None:
        try:
            if msm_id in MSM_TO_TARGET:
                return MSM_TO_TARGET[msm_id]
            if int(msm_id) in MSM_TO_TARGET:
                return MSM_TO_TARGET[int(msm_id)]
        except Exception:
            pass

    link_info = item.get('link_info', {})
    target_root = link_info.get('target_root')
    if target_root:
        return target_root

    return None


def aggregate_trace_cables(
    segments: List[Dict[str, Any]],
    mode: str = "weighted",
    threshold: float = 0.5
) -> Dict[str, float]:
    if not segments:
        return {}

    dedup = defaultdict(float)
    for seg in segments:
        c_name = seg.get('cable_name')
        p = seg.get('segment_probability', 0.0)
        if c_name:
            dedup[c_name] = max(dedup[c_name], p)

    if not dedup:
        return {}

    if mode == "hard_top1":
        top_cable = max(dedup.items(), key=lambda x: x[1])[0]
        return {top_cable: 1.0}

    if mode == "weighted":
        return dict(dedup)

    if mode == "thresholded_normalized":
        kept = {k: v for k, v in dedup.items() if v >= threshold}
        s = sum(kept.values())
        if s > 0:
            return {k: v / s for k, v in kept.items()}
        return {}

    raise ValueError(f"Unknown aggregation mode: {mode}")


def extract_cable_to_owners(
    segments: List[Dict[str, Any]],
    cable_owner_meta: Dict[str, Dict[str, Any]],
) -> Dict[str, List[str]]:
    cable_to_owners: Dict[str, List[str]] = {}

    for seg in segments:
        cable_name = seg.get("cable_name")
        cable_id = seg.get("cable_id")
        if not cable_name and not cable_id:
            continue

        owners = normalize_owners_field(seg.get("cable_owners"))
        chosen_name = cable_name or f"ID::{cable_id}"

        if owners:
            if chosen_name not in cable_to_owners:
                cable_to_owners[chosen_name] = owners
            continue

        meta = None
        if cable_id:
            meta = cable_owner_meta.get(f"id::{cable_id}")
        if meta is None and cable_name:
            meta = cable_owner_meta.get(f"name::{cable_name}")

        if chosen_name not in cable_to_owners:
            cable_to_owners[chosen_name] = list(meta.get("owners", [])) if meta else []

    return cable_to_owners


def normalize_trace_cable_scores(cable_scores: Dict[str, float]) -> Dict[str, float]:
    if not cable_scores:
        return {}

    s = sum(v for v in cable_scores.values() if v is not None and v > 0)
    if s <= 0:
        return {}

    return {k: (v / s) for k, v in cable_scores.items() if v is not None and v > 0}


def distribute_owner_score(
    score: float,
    owners: List[str],
    owner_multi_entity_mode: str,
    unknown_label: str = "UNKNOWN_OWNER",
) -> Dict[str, float]:
    if not owners:
        return {unknown_label: score}

    clean_owners = [o for o in owners if o]
    if not clean_owners:
        return {unknown_label: score}

    if owner_multi_entity_mode == "full":
        return {owner: score for owner in clean_owners}

    if owner_multi_entity_mode == "split":
        share = score / len(clean_owners)
        return {owner: share for owner in clean_owners}

    raise ValueError(f"Unknown owner_multi_entity_mode: {owner_multi_entity_mode}")


def aggregate_trace_owners(
    segments: List[Dict[str, Any]],
    cable_owner_meta: Dict[str, Dict[str, Any]],
    mode: str = "weighted",
    threshold: float = 0.5,
    owner_multi_entity_mode: str = "full",
) -> Dict[str, float]:
    raw_cable_scores = aggregate_trace_cables(segments, mode=mode, threshold=threshold)
    cable_scores = normalize_trace_cable_scores(raw_cable_scores)
    if not cable_scores:
        return {}

    cable_to_owners = extract_cable_to_owners(segments, cable_owner_meta)
    owner_scores = defaultdict(float)

    for cable_name, prob in cable_scores.items():
        owners = cable_to_owners.get(cable_name, [])
        alloc = distribute_owner_score(
            score=prob,
            owners=owners,
            owner_multi_entity_mode=owner_multi_entity_mode,
            unknown_label="UNKNOWN_OWNER",
        )
        for owner, v in alloc.items():
            owner_scores[owner] += v

    return dict(owner_scores)


def extract_crossborder_as_pairs_from_trace(
    traceroute_item: Dict[str, Any],
    mmdb_reader: maxminddb.Reader,
    pfx2as_trie: Optional[Any],
) -> Set[Tuple[str, str]]:
    """
    从单条 traceroute 中提取“跨国 AS-pair”集合。
    规则：
    - 仅考虑相邻 hop
    - 相邻 hop 的国家不同
    - 两端 ASN 都有效
    - ASN 不相同
    - 同一条 trace 内相同 pair 只记一次
    """
    results = traceroute_item.get('result', [])
    if not isinstance(results, list) or not results:
        return set()

    hop_infos: List[Tuple[Optional[str], Optional[str]]] = []
    for hop in results:
        if not isinstance(hop, dict):
            continue
        resp_list = hop.get('result', [])
        if not isinstance(resp_list, list):
            continue

        ip = None
        for resp in resp_list:
            if isinstance(resp, dict) and resp.get('from'):
                ip = resp.get('from')
                break
        if not ip:
            continue

        geo = get_geo_info(ip, mmdb_reader)
        country = geo.get('country')
        asn = ip_to_asn(ip, pfx2as_trie)
        if not country or not asn:
            continue

        hop_infos.append((country, asn))

    pairs: Set[Tuple[str, str]] = set()
    prev_country = None
    prev_asn = None
    for country, asn in hop_infos:
        if prev_country is not None and prev_asn is not None:
            if country != prev_country and asn != prev_asn:
                pairs.add((prev_asn, asn))
        prev_country, prev_asn = country, asn

    return pairs


def top2_from_usage(usage_dict: Dict[Any, float]) -> Dict[str, Any]:
    sorted_items = sorted(usage_dict.items(), key=lambda x: x[1], reverse=True)

    top1_name: Any = "None"
    top1_score = 0.0
    top2_name: Any = "None"
    top2_score = 0.0

    if len(sorted_items) >= 1:
        top1_name = sorted_items[0][0]
        top1_score = sorted_items[0][1]

    if len(sorted_items) >= 2:
        top2_name = sorted_items[1][0]
        top2_score = sorted_items[1][1]

    return {
        "top1_name": top1_name,
        "top1_score": top1_score,
        "top2_name": top2_name,
        "top2_score": top2_score,
    }


def stringify_as_pair(pair: Any) -> str:
    if isinstance(pair, tuple) and len(pair) == 2:
        return f"{pair[0]}->{pair[1]}"
    if pair is None:
        return "None"
    return str(pair)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按国家/Root 聚合海缆依赖，并扩展到 owner 与逻辑层跨境 AS-pair 分析。支持一次输出单表或总表。"
    )

    parser.add_argument("--raw-traces-file", default=DEFAULT_RAW_TRACES_FILE,
                        help="原始 traceroute 文件路径，用于统计总流量分母与逻辑层 AS-pair。")
    parser.add_argument("--match-output-file", default=DEFAULT_MATCH_OUTPUT_FILE,
                        help="merge_main 输出的海缆匹配结果 JSON。")
    parser.add_argument("--probe-meta-file", default=DEFAULT_PROBE_META_FILE,
                        help="探针元数据文件路径。")
    parser.add_argument("--mmdb-path", default=DEFAULT_MMDB_PATH,
                        help="IP 地理库 MMDB 路径。")
    parser.add_argument("--pfx2as-file", default=DEFAULT_PFX2AS_PATH,
                        help="pfx2as 文件路径，用于逻辑层跨境 AS-pair 特征。")
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV,
                        help="输出 CSV 路径。单模式时输出单表；总表模式时输出总表。")
    parser.add_argument("--summary-json", default=DEFAULT_SUMMARY_JSON,
                        help="可选：输出一个 summary JSON。")
    parser.add_argument("--cable-dir", default=DEFAULT_CABLE_DIR,
                        help="海缆元数据目录，用于回填 cable owners。")

    parser.add_argument("--aggregation-mode",
                        choices=["hard_top1", "weighted", "thresholded_normalized"],
                        default=DEFAULT_AGGREGATION_MODE,
                        help="单条 trace 内 cable 候选的聚合方式。")
    parser.add_argument("--match-threshold", type=float, default=DEFAULT_MATCH_THRESHOLD,
                        help="thresholded_normalized 模式及统一实验配置使用的阈值。")
    parser.add_argument("--confidence-bucket",
                        choices=["high", "medium", "ambiguous"],
                        default=DEFAULT_ONLY_CONFIDENCE_BUCKET,
                        help="仅保留指定 confidence bucket 的匹配结果。默认不过滤。")

    parser.add_argument("--owner-multi-entity-mode",
                        choices=["full", "split"],
                        default=DEFAULT_OWNER_MULTI_ENTITY_MODE,
                        help="owner 聚合模式。full=owner 继承相关 cable 的归一化概率；split=再在 owners 间均分。")

    parser.add_argument("--cross-country", dest="cross_country", action="store_true",
                        default=DEFAULT_FLAG_CROSS_COUNTRY,
                        help="仅统计跨国流量（默认开启）。")
    parser.add_argument("--no-cross-country", dest="cross_country", action="store_false",
                        help="不做跨国过滤。")
    parser.add_argument("--topn-preview", type=int, default=10,
                        help="终端打印前 N 条高风险结果。")

    parser.add_argument("--output-total-table", action="store_true",
                        help="一次运行输出总表：自动生成 weighted_all / hard_top1_all / weighted_high 三种模式，并合并成总表。")
    parser.add_argument("--detail-dir", default=None,
                        help="总表模式下，可选：同时输出每个子模式的明细 CSV 到该目录。")

    parser.add_argument("--collapse-roots", action="store_true",
                        help="忽略不同 DNS Root / target 的差异，按 Country 聚合。启用后 Root 列统一写为 ALL。")

    return parser.parse_args()


def collect_json_files(path: Optional[str]) -> List[str]:
    if not path:
        return []
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        return []

    files: List[str] = []
    for root, _, filenames in os.walk(path):
        for filename in filenames:
            if filename.endswith('.json'):
                files.append(os.path.join(root, filename))
    files.sort()
    return files


def resolve_raw_trace_files(raw_traces_file: Optional[str], match_output_file: str) -> List[str]:
    direct_files = collect_json_files(raw_traces_file)
    if direct_files:
        return direct_files

    manifest_path = os.path.join(os.path.dirname(os.path.abspath(match_output_file)), 'cable_matching_manifest.json')
    if not os.path.exists(manifest_path):
        return []

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception:
        return []

    raw_paths = manifest.get('traceroute_file_paths', [])
    if not isinstance(raw_paths, list):
        return []

    repo_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(manifest_path))))
    resolved_files: List[str] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = raw_path if os.path.isabs(raw_path) else os.path.normpath(os.path.join(repo_base_dir, raw_path))
        if os.path.exists(candidate):
            resolved_files.append(candidate)
    return resolved_files


def load_raw_trace_totals_and_logic_features(
    raw_trace_files: List[str],
    probe_geo_db: Dict[str, str],
    mmdb_path: str,
    flag_cross_country: bool,
    pfx2as_trie: Optional[Any],
    collapse_roots: bool = False,
):
    total_counts_raw = defaultdict(lambda: defaultdict(int))
    as_pair_counts_raw = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    cross_country = 0

    if not raw_trace_files:
        print("⚠️ 找不到可用的原始 traceroute 输入，分母与逻辑层特征将不完整。")
        return total_counts_raw, as_pair_counts_raw, cross_country

    try:
        with maxminddb.open_database(mmdb_path) as mmdb_reader:
            for raw_traces_file in raw_trace_files:
                print(f"📂 正在读取原始 Trace 文件: {raw_traces_file}")
                try:
                    with open(raw_traces_file, 'r', encoding='utf-8') as f:
                        raw_data = json.load(f)
                except Exception:
                    print("⚠️ 尝试重新读取原始文件为行格式...")
                    raw_data = []
                    with open(raw_traces_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                raw_data.append(json.loads(line))

                print(f"📊 正在处理 {len(raw_data)} 条原始记录...")
                for item in tqdm(raw_data, desc=f"统计 {os.path.basename(raw_traces_file)}"):
                    probe_id = str(item.get('prb_id', item.get('probe_id')))
                    country = probe_geo_db.get(probe_id)
                    if not country:
                        continue

                    root_name = get_root_name(item)
                    if not root_name:
                        continue
                    if collapse_roots:
                        root_name = "ALL"

                    if flag_cross_country:
                        dst_country = get_geo_info(item.get('dst_addr'), mmdb_reader).get('country')
                        if dst_country == country:
                            continue
                        cross_country += 1

                    total_counts_raw[country][root_name] += 1

                    # 逻辑层：提取跨国 AS-pair，单条 trace 内去重后再计数
                    as_pairs = extract_crossborder_as_pairs_from_trace(
                        traceroute_item=item,
                        mmdb_reader=mmdb_reader,
                        pfx2as_trie=pfx2as_trie,
                    )
                    for pair in as_pairs:
                        as_pair_counts_raw[country][root_name][pair] += 1

    except Exception as e:
        raise RuntimeError(f"处理原始 Trace 失败: {e}")

    return total_counts_raw, as_pair_counts_raw, cross_country


def load_match_data(match_output_file: str) -> List[Dict[str, Any]]:
    print(f"🔗 正在读取海缆匹配结果: {match_output_file}")
    with open(match_output_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_single_mode(
    *,
    total_counts_raw: Dict[str, Dict[str, int]],
    as_pair_counts_raw: Dict[str, Dict[str, Dict[Tuple[str, str], int]]],
    match_data: List[Dict[str, Any]],
    probe_geo_db: Dict[str, str],
    cable_owner_meta: Dict[str, Dict[str, Any]],
    aggregation_mode: str,
    match_threshold: float,
    only_confidence_bucket: Optional[str],
    flag_cross_country: bool,
    owner_multi_entity_mode: str,
    collapse_roots: bool = False,
) -> pd.DataFrame:
    cable_weighted_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    owner_weighted_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    submarine_trace_counts = defaultdict(lambda: defaultdict(int))
    bucket_trace_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for entry in tqdm(match_data, desc=f"计算 {aggregation_mode}/{only_confidence_bucket or 'all'}"):
        link = entry.get('link_info', {})
        segments = entry.get('all_segments', [])
        summary = entry.get('match_summary', {})

        if not segments or not link:
            continue

        bucket = summary.get('confidence_bucket')
        if only_confidence_bucket is not None and bucket != only_confidence_bucket:
            continue

        probe_id = str(link.get('probe_id'))
        country = probe_geo_db.get(probe_id)
        if not country:
            continue

        target_root = get_root_name(entry)
        if not target_root:
            continue
        if collapse_roots:
            target_root = "ALL"

        if flag_cross_country:
            dst_country = link.get('dst_country')
            if dst_country == country:
                continue

        diff_country_seg = False
        for seg in segments:
            seg_src_country = seg.get('country_a')
            seg_dst_country = seg.get('country_b')
            if seg_dst_country is None or seg_src_country is None:
                diff_country_seg = True
                break
            if seg_src_country != country or seg_dst_country != country:
                diff_country_seg = True
                break
        if not diff_country_seg:
            continue

        submarine_trace_counts[country][target_root] += 1
        bucket_trace_counts[country][target_root][bucket] += 1

        cables_in_this_trace = aggregate_trace_cables(
            segments,
            mode=aggregation_mode,
            threshold=match_threshold
        )
        for c_name, p in cables_in_this_trace.items():
            cable_weighted_counts[country][target_root][c_name] += p

        owners_in_this_trace = aggregate_trace_owners(
            segments,
            cable_owner_meta=cable_owner_meta,
            mode=aggregation_mode,
            threshold=match_threshold,
            owner_multi_entity_mode=owner_multi_entity_mode,
        )
        for owner, p in owners_in_this_trace.items():
            owner_weighted_counts[country][target_root][owner] += p

    results = []
    all_countries = set(total_counts_raw.keys()) | set(submarine_trace_counts.keys())

    for country in sorted(all_countries):
        roots = set(total_counts_raw[country].keys()) | set(submarine_trace_counts[country].keys())

        for root in roots:
            raw_total_int = total_counts_raw[country].get(root, 0)
            sub_count_int = submarine_trace_counts[country].get(root, 0)
            corrected_total_int = max(raw_total_int, sub_count_int)
            if corrected_total_int == 0:
                continue

            dependency_rate = sub_count_int / corrected_total_int

            cable_usage = cable_weighted_counts[country].get(root, {})
            cable_top = top2_from_usage(cable_usage)
            top_cable_share = cable_top["top1_score"] / corrected_total_int
            top2_cable_share = cable_top["top2_score"] / corrected_total_int
            cable_margin = top_cable_share - top2_cable_share

            owner_usage = owner_weighted_counts[country].get(root, {})
            owner_top = top2_from_usage(owner_usage)
            top_owner_share = owner_top["top1_score"] / corrected_total_int
            top2_owner_share = owner_top["top2_score"] / corrected_total_int
            owner_margin = top_owner_share - top2_owner_share

            as_pair_usage = as_pair_counts_raw[country].get(root, {})
            as_pair_top = top2_from_usage(as_pair_usage)
            top_as_pair_share = as_pair_top["top1_score"] / corrected_total_int
            top2_as_pair_share = as_pair_top["top2_score"] / corrected_total_int
            as_pair_margin = top_as_pair_share - top2_as_pair_share

            results.append({
                'Country': country,
                'Root': root,

                'Aggregation_Mode': aggregation_mode,
                'Confidence_Filter': only_confidence_bucket or "all",
                'Owner_Multi_Entity_Mode': owner_multi_entity_mode,

                'Total_Traces': corrected_total_int,
                'Submarine_Traces': sub_count_int,
                'Dependency_Rate': round(dependency_rate, 4),

                'Top_Cable': cable_top["top1_name"],
                'Top_Cable_Expected_Vol': round(cable_top["top1_score"], 4),
                'Top_Cable_Share': round(top_cable_share, 4),
                'Top2_Cable': cable_top["top2_name"],
                'Top2_Cable_Expected_Vol': round(cable_top["top2_score"], 4),
                'Top2_Cable_Share': round(top2_cable_share, 4),
                'Dominance_Margin': round(cable_margin, 4),

                'Unique_CrossBorder_AS_Pairs': int(len(as_pair_usage)),
                'Top_CrossBorder_AS_Pair': stringify_as_pair(as_pair_top["top1_name"]),
                'Top_CrossBorder_AS_Pair_Count': int(as_pair_top["top1_score"]),
                'Top_CrossBorder_AS_Pair_Share': round(top_as_pair_share, 4),
                'Top2_CrossBorder_AS_Pair': stringify_as_pair(as_pair_top["top2_name"]),
                'Top2_CrossBorder_AS_Pair_Count': int(as_pair_top["top2_score"]),
                'Top2_CrossBorder_AS_Pair_Share': round(top2_as_pair_share, 4),
                'CrossBorder_AS_Pair_Dominance_Margin': round(as_pair_margin, 4),
                'Cable_vs_ASPair_Concentration_Gap': round(top_cable_share - top_as_pair_share, 4),

                'Top_Owner': owner_top["top1_name"],
                'Top_Owner_Expected_Vol': round(owner_top["top1_score"], 4),
                'Top_Owner_Share': round(top_owner_share, 4),
                'Top2_Owner': owner_top["top2_name"],
                'Top2_Owner_Expected_Vol': round(owner_top["top2_score"], 4),
                'Top2_Owner_Share': round(top2_owner_share, 4),
                'Owner_Dominance_Margin': round(owner_margin, 4),

                'Cable_Owner_Concentration_Gap': round(top_owner_share - top_cable_share, 4),

                'High_Bucket_Traces': bucket_trace_counts[country][root].get('high', 0),
                'Medium_Bucket_Traces': bucket_trace_counts[country][root].get('medium', 0),
                'Ambiguous_Bucket_Traces': bucket_trace_counts[country][root].get('ambiguous', 0),
            })

    df = pd.DataFrame(results)
    if not df.empty:
        df.sort_values(by=['Dependency_Rate', 'Top_Cable_Share'], ascending=[False, False], inplace=True)
    return df


def print_preview(df: pd.DataFrame, topn: int, title: str) -> None:
    if df.empty:
        print(f"⚠️ {title}: 没有结果。")
        return
    preview_cols = [
        'Country', 'Root', 'Aggregation_Mode', 'Confidence_Filter',
        'Total_Traces', 'Dependency_Rate',
        'Top_Cable', 'Top_Cable_Share',
        'Top_CrossBorder_AS_Pair', 'Top_CrossBorder_AS_Pair_Share',
        'Cable_vs_ASPair_Concentration_Gap',
        'Top_Owner', 'Top_Owner_Share',
        'Cable_Owner_Concentration_Gap'
    ]
    preview_cols = [c for c in preview_cols if c in df.columns]
    print(f"\n--- 🔥 Top {topn} {title} ---")
    print(df[preview_cols].head(topn).to_string(index=False))


def write_summary(summary_json: str, summary: Dict[str, Any]) -> None:
    out_dir = os.path.dirname(summary_json)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(summary_json, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"📝 Summary 已保存: {summary_json}")



def merge_total_table_variants(
    merged_frames: List[Tuple[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    正确合并 weighted_all / hard_top1_all / weighted_high 三个子表。

    关键修复：
    1. 只按稳定主键 Country + Root 合并，避免因为 Total_Traces 在不同子模式下出现差异而拆成两行；
    2. Total_Traces 只保留一列，并在合并后做一致性兜底；
    3. 对重复键做聚合性去重，优先保留非空值。
    """
    def collapse_duplicate_keys(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        def pick_first_non_null(series: pd.Series):
            non_null = series.dropna()
            if len(non_null) == 0:
                return pd.NA
            return non_null.iloc[0]

        agg = {col: pick_first_non_null for col in df.columns if col not in ['Country', 'Root']}
        collapsed = (
            df.groupby(['Country', 'Root'], as_index=False, dropna=False)
              .agg(agg)
        )
        return collapsed

    merged_df = None
    total_trace_cols = []

    for label, variant_df in merged_frames:
        current = variant_df.copy()

        # 记录并统一 Total_Traces 的来源；只在最终表保留一个 Total_Traces
        total_col = 'Total_Traces'
        if total_col in current.columns:
            current.rename(columns={total_col: f'Total_Traces__{label}'}, inplace=True)
            total_trace_cols.append(f'Total_Traces__{label}')

        current = collapse_duplicate_keys(current)

        if merged_df is None:
            merged_df = current
        else:
            merged_df = pd.merge(
                merged_df,
                current,
                on=['Country', 'Root'],
                how='outer'
            )

    if merged_df is None:
        return pd.DataFrame()

    # 合并 Total_Traces：优先 weighted_all，其次 hard_top1_all，再其次 weighted_high
    preferred_order = [
        'Total_Traces__weighted_all',
        'Total_Traces__hard_top1_all',
        'Total_Traces__weighted_high',
    ]
    ordered_cols = [c for c in preferred_order if c in merged_df.columns] + [
        c for c in total_trace_cols if c not in preferred_order and c in merged_df.columns
    ]

    if ordered_cols:
        merged_df['Total_Traces'] = pd.NA
        for c in ordered_cols:
            merged_df['Total_Traces'] = merged_df['Total_Traces'].fillna(merged_df[c])

        # 保留一个一致性标记，方便调试，但不强制中断
        if len(ordered_cols) >= 2:
            def _trace_consistent(row):
                vals = []
                for c in ordered_cols:
                    v = row.get(c)
                    if pd.notna(v):
                        vals.append(v)
                return len(set(vals)) <= 1
            merged_df['Total_Traces_Consistent'] = merged_df.apply(_trace_consistent, axis=1)

        merged_df.drop(columns=[c for c in ordered_cols if c in merged_df.columns], inplace=True)

    # 再做一次最终去重，防止 merge 前后极端情况下残留重复键
    merged_df = collapse_duplicate_keys(merged_df)

    # 列顺序整理：主键和 Total_Traces 放在前面
    front_cols = [c for c in ['Country', 'Root', 'Total_Traces', 'Total_Traces_Consistent'] if c in merged_df.columns]
    other_cols = [c for c in merged_df.columns if c not in front_cols]
    merged_df = merged_df[front_cols + other_cols]

    return merged_df

def analyze_dependency_hybrid(args: argparse.Namespace):
    raw_traces_file = args.raw_traces_file
    match_output_file = args.match_output_file
    probe_meta_file = args.probe_meta_file
    output_csv = args.output_csv
    mmdb_path = args.mmdb_path
    pfx2as_file = args.pfx2as_file
    aggregation_mode = args.aggregation_mode
    match_threshold = args.match_threshold
    only_confidence_bucket = args.confidence_bucket
    flag_cross_country = args.cross_country
    topn_preview = args.topn_preview
    summary_json = args.summary_json
    cable_dir = args.cable_dir
    owner_multi_entity_mode = args.owner_multi_entity_mode
    collapse_roots = getattr(args, "collapse_roots", False)

    probe_geo_db = load_probe_metadata(probe_meta_file)
    cable_owner_meta = load_cable_owner_mapping(cable_dir)
    pfx2as_trie = load_pfx2as_mapping(pfx2as_file)
    raw_trace_files = resolve_raw_trace_files(raw_traces_file, match_output_file)

    total_counts_raw, as_pair_counts_raw, cross_country = load_raw_trace_totals_and_logic_features(
        raw_trace_files=raw_trace_files,
        probe_geo_db=probe_geo_db,
        mmdb_path=mmdb_path,
        flag_cross_country=flag_cross_country,
        pfx2as_trie=pfx2as_trie,
        collapse_roots=collapse_roots,
    )
    if flag_cross_country:
        print(f"🌐 跨国流量计数: {cross_country} 条记录。")

    match_data = load_match_data(match_output_file)

    if args.output_total_table:
        runs = [
            ("weighted", None, "weighted_all"),
            ("hard_top1", None, "hard_top1_all"),
            ("weighted", "high", "weighted_high"),
        ]
        merged_frames = []

        detail_dir = args.detail_dir
        if detail_dir:
            os.makedirs(detail_dir, exist_ok=True)

        logic_cols = [
            'Unique_CrossBorder_AS_Pairs',
            'Top_CrossBorder_AS_Pair',
            'Top_CrossBorder_AS_Pair_Count',
            'Top_CrossBorder_AS_Pair_Share',
            'Top2_CrossBorder_AS_Pair',
            'Top2_CrossBorder_AS_Pair_Count',
            'Top2_CrossBorder_AS_Pair_Share',
            'CrossBorder_AS_Pair_Dominance_Margin',
            'Cable_vs_ASPair_Concentration_Gap',
        ]

        for idx, (agg_mode, conf_bucket, label) in enumerate(runs):
            df = compute_single_mode(
                total_counts_raw=total_counts_raw,
                as_pair_counts_raw=as_pair_counts_raw,
                match_data=match_data,
                probe_geo_db=probe_geo_db,
                cable_owner_meta=cable_owner_meta,
                aggregation_mode=agg_mode,
                match_threshold=match_threshold,
                only_confidence_bucket=conf_bucket,
                flag_cross_country=flag_cross_country,
                owner_multi_entity_mode=owner_multi_entity_mode,
                collapse_roots=collapse_roots,
            )

            if df.empty:
                print(f"⚠️ {label} 没有结果。")
                continue

            rename_cols = {
                'Submarine_Traces': f'Submarine_Traces_{label}',
                'Dependency_Rate': f'Dependency_Rate_{label}',

                'Top_Cable': f'Top_Cable_{label}',
                'Top_Cable_Expected_Vol': f'Top_Cable_Expected_Vol_{label}',
                'Top_Cable_Share': f'Top_Cable_Share_{label}',
                'Top2_Cable': f'Top2_Cable_{label}',
                'Top2_Cable_Expected_Vol': f'Top2_Cable_Expected_Vol_{label}',
                'Top2_Cable_Share': f'Top2_Cable_Share_{label}',
                'Dominance_Margin': f'Dominance_Margin_{label}',

                'Top_Owner': f'Top_Owner_{label}',
                'Top_Owner_Expected_Vol': f'Top_Owner_Expected_Vol_{label}',
                'Top_Owner_Share': f'Top_Owner_Share_{label}',
                'Top2_Owner': f'Top2_Owner_{label}',
                'Top2_Owner_Expected_Vol': f'Top2_Owner_Expected_Vol_{label}',
                'Top2_Owner_Share': f'Top2_Owner_Share_{label}',
                'Owner_Dominance_Margin': f'Owner_Dominance_Margin_{label}',

                'Cable_Owner_Concentration_Gap': f'Cable_Owner_Concentration_Gap_{label}',

                'High_Bucket_Traces': f'High_Bucket_Traces_{label}',
                'Medium_Bucket_Traces': f'Medium_Bucket_Traces_{label}',
                'Ambiguous_Bucket_Traces': f'Ambiguous_Bucket_Traces_{label}',
            }

            variant_df = df.copy()
            for col in ['Aggregation_Mode', 'Confidence_Filter', 'Owner_Multi_Entity_Mode']:
                if col in variant_df.columns:
                    variant_df.drop(columns=[col], inplace=True)

            if idx > 0:
                drop_logic_cols = [c for c in logic_cols if c in variant_df.columns]
                if drop_logic_cols:
                    variant_df.drop(columns=drop_logic_cols, inplace=True)

            variant_df.rename(columns=rename_cols, inplace=True)

            if detail_dir:
                detail_path = os.path.join(detail_dir, f"{label}.csv")
                df.to_csv(detail_path, index=False, encoding='utf-8-sig')
                print(f"📄 明细已保存: {detail_path}")

            merged_frames.append((label, variant_df))

        if not merged_frames:
            print("⚠️ 总表模式下没有可写出的结果。")
            return

        merged_df = merge_total_table_variants(merged_frames)

        for prefix in ['Cable', 'Owner']:
            weighted_col = f"Top_{prefix}_weighted_all"
            hard_col = f"Top_{prefix}_hard_top1_all"
            high_col = f"Top_{prefix}_weighted_high"

            if weighted_col in merged_df.columns and hard_col in merged_df.columns:
                merged_df[f"{prefix}_Stable_vs_Hard"] = (
                    merged_df[weighted_col].fillna("None") == merged_df[hard_col].fillna("None")
                )

            if weighted_col in merged_df.columns and high_col in merged_df.columns:
                merged_df[f"{prefix}_Stable_vs_High"] = (
                    merged_df[weighted_col].fillna("None") == merged_df[high_col].fillna("None")
                )

            if weighted_col in merged_df.columns and hard_col in merged_df.columns and high_col in merged_df.columns:
                merged_df[f"{prefix}_Stable_All3"] = (
                    (merged_df[weighted_col].fillna("None") == merged_df[hard_col].fillna("None")) &
                    (merged_df[weighted_col].fillna("None") == merged_df[high_col].fillna("None"))
                )

        if not merged_df.empty:
            sort_keys = [c for c in ['Country', 'Root'] if c in merged_df.columns]
            if sort_keys:
                merged_df.sort_values(by=sort_keys, inplace=True)

        output_dir = os.path.dirname(output_csv)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        merged_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
        print(f"\n✅ 总表分析完成！")
        print(f"📄 总表已保存: {output_csv}")

        sort_col = 'Top_Cable_Share_weighted_all'
        if sort_col in merged_df.columns:
            merged_df.sort_values(by=[sort_col], ascending=[False], inplace=True)

        preview_cols = [c for c in [
            'Country', 'Root', 'Total_Traces',
            'Unique_CrossBorder_AS_Pairs', 'Top_CrossBorder_AS_Pair', 'Top_CrossBorder_AS_Pair_Share',
            'Cable_vs_ASPair_Concentration_Gap',
            'Dependency_Rate_weighted_all',
            'Top_Cable_weighted_all', 'Top_Cable_Share_weighted_all',
            'Top_Cable_hard_top1_all', 'Top_Cable_Share_hard_top1_all',
            'Top_Cable_weighted_high', 'Top_Cable_Share_weighted_high',
            'Cable_Stable_vs_Hard', 'Cable_Stable_vs_High', 'Cable_Stable_All3',
            'Top_Owner_weighted_all', 'Top_Owner_Share_weighted_all',
            'Owner_Stable_vs_Hard', 'Owner_Stable_vs_High', 'Owner_Stable_All3',
            'Cable_Owner_Concentration_Gap_weighted_all',
        ] if c in merged_df.columns]
        print(f"\n--- 🔥 Top {topn_preview} 总表预览 ---")
        print(merged_df[preview_cols].head(topn_preview).to_string(index=False))

        if summary_json:
            summary = {
                "raw_traces_file": raw_traces_file,
                "resolved_raw_trace_files": raw_trace_files,
                "match_output_file": match_output_file,
                "probe_meta_file": probe_meta_file,
                "mmdb_path": mmdb_path,
                "pfx2as_file": pfx2as_file,
                "cable_dir": cable_dir,
                "output_csv": output_csv,
                "output_total_table": True,
                "collapse_roots": collapse_roots,
                "owner_multi_entity_mode": owner_multi_entity_mode,
                "match_threshold": match_threshold,
                "cross_country": flag_cross_country,
                "rows": int(len(merged_df)),
                "countries": int(merged_df['Country'].nunique()) if 'Country' in merged_df.columns else 0,
                "roots": int(merged_df['Root'].nunique()) if 'Root' in merged_df.columns else 0,
            }
            write_summary(summary_json, summary)
        return

    df = compute_single_mode(
        total_counts_raw=total_counts_raw,
        as_pair_counts_raw=as_pair_counts_raw,
        match_data=match_data,
        probe_geo_db=probe_geo_db,
        cable_owner_meta=cable_owner_meta,
        aggregation_mode=aggregation_mode,
        match_threshold=match_threshold,
        only_confidence_bucket=only_confidence_bucket,
        flag_cross_country=flag_cross_country,
        owner_multi_entity_mode=owner_multi_entity_mode,
        collapse_roots=collapse_roots,
    )

    if df.empty:
        print("⚠️ 没有结果可写出，请检查输入和过滤条件。")
        return

    output_dir = os.path.dirname(output_csv)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')

    print("\n✅ 混合分析完成！")
    print(f"📄 结果已保存: {output_csv}")
    print_preview(df, topn_preview, "High Risk (Cable / AS-pair / Owner)")

    if summary_json:
        summary = {
            "raw_traces_file": raw_traces_file,
            "resolved_raw_trace_files": raw_trace_files,
            "match_output_file": match_output_file,
            "probe_meta_file": probe_meta_file,
            "mmdb_path": mmdb_path,
            "pfx2as_file": pfx2as_file,
            "cable_dir": cable_dir,
            "output_csv": output_csv,
            "aggregation_mode": aggregation_mode,
            "collapse_roots": collapse_roots,
            "match_threshold": match_threshold,
            "confidence_bucket": only_confidence_bucket,
            "cross_country": flag_cross_country,
            "owner_multi_entity_mode": owner_multi_entity_mode,
            "rows": int(len(df)),
            "countries": int(df['Country'].nunique()) if 'Country' in df.columns else 0,
            "roots": int(df['Root'].nunique()) if 'Root' in df.columns else 0,
        }
        write_summary(summary_json, summary)


if __name__ == "__main__":
    args = parse_args()
    analyze_dependency_hybrid(args)
