# infocom26 项目说明

本仓库实现的是一个面向 RIPE Atlas traceroute、AS 关系与海缆候选基础设施的**不确定性感知跨层多样性审计**（uncertainty-aware cross-layer diversity auditing）流程。

核心研究问题是：

> 网络层（network layer）观察到的多样性，在投影到物理候选基础设施空间之后，是否仍然保持多样性？

本项目的目标**不是**对每一条路径做“真实海缆”的确定性归因，而是输出：

- 候选物理支撑分布（candidate-support distribution）
- network-layer diversity
- physical-candidate diversity
- network-physical mismatch
- ambiguity / robustness profile

## 解释边界

- `candidate_support`、`fused_candidate_support`、`normalized_candidate_support` 都是**证据分数**，不是 ground truth。
- 排名第一的候选海缆，只表示在当前证据模型下最强的候选解释，不表示该路径真实使用了这根海缆。
- 保留 cable-level 和 corridor-level 两种输出，是因为平行海缆会影响解释粒度。

## 仓库结构

```text
source/
  main_analysis.py
  concerntration_analysis.py
  postprocess_candidate_output.py
  robustness_compare.py
  precompute_as_graph.py

data/
  asrelationship/
  cable/
  ipinfo/
  owner2asn/
  pfx2as/
  probe/
  traceroute/
  traceroute_rundnsroot/

output/
  preprocessed/
  result/
```

根目录下的 `main_analysis.py`、`postprocess_candidate_output.py` 等只是薄封装入口，真正实现位于 `source/`。

## 流程总览

1. `precompute_as_graph.py`  
   可选预处理。为 AS-economic core 预先构造 owner group 的 AS 图可达性。

2. `main_analysis.py`  
   第一阶段。对 traceroute 逐链路做 candidate-support 计算，输出 link-level 候选海缆结果。

3. `concerntration_analysis.py`  
   第二阶段。读取第一阶段输出，按国家 / root 聚合依赖和集中度。

4. `postprocess_candidate_output.py`  
   读取第一阶段输出，计算 unit-level diversity、mismatch、ambiguity、解释性表格和图。

5. `robustness_compare.py`  
   基于展开后的 candidate-support 表，比较不同 evidence view 下 mismatch 的稳定性。

## 输入文件说明

### 通用输入文件

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `data/cable/landing-point-geo.json` | 第一阶段 | GeoJSON，`features[].properties.id` 为 landing station ID，geometry 为坐标 | landing station 坐标索引 |
| `data/cable/*.json` | 第一阶段、第二阶段、AS 预处理 | 每根海缆一个 JSON，包含 `id`、`name`、`landing_points`、`owners` 等 | 海缆元数据、登陆站对、owner 信息 |
| `data/ipinfo/ipinfo_location.mmdb` | 第一阶段、第二阶段 | MMDB geolocation 数据库 | IP 到国家 / 城市 / ASN 的地理映射 |
| `data/asrelationship/20250901.as-rel2.txt` | 第一阶段、AS 预处理 | CAIDA 格式 AS 关系文件 | AS-economic core 的关系图输入 |
| `data/pfx2as/202512.pfx2as` | 第一阶段、第二阶段 | prefix 到 origin ASN 的映射 | IP 到 ASN 解析 |
| `data/owner2asn/owner_to_asn.csv` | 第一阶段、AS 预处理 | `owner,asn` 两列 | cable owner 到 ASN 的映射 |

### traceroute 与 probe 输入

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `data/traceroute_rundnsroot/root_dns_traces.json` | 第一阶段默认、第二阶段默认 | RIPE Atlas traceroute JSON 数组 | 小规模日常测试输入 |
| `data/traceroute_rundnsroot/**/*.json` | 第一阶段 | RIPE Atlas traceroute 结果文件 | 第一阶段主输入目录 |
| `data/traceroute/ripe_atlas_5051_20251201.json` | 可选 | 大规模 traceroute 输入 | 全量运行用 |
| `data/probe/*.json` | 第二阶段 | probe 元数据，通常包含 `objects[].id` 与 `objects[].country_code` | 将 probe ID 映射到源国家 |

### 可选预处理输入

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `output/preprocessed/as_graph_owner_reachability.pkl.gz` | 第一阶段 | gzip pickle 格式的 owner-group reachability 结果 | 加速 AS-economic support 计算 |

## 各脚本参数说明

### `python precompute_as_graph.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--asrel-file` | `data/asrelationship/20250901.as-rel2.txt` | CAIDA AS relationship 文件 |
| `--owner2asn-file` | `data/owner2asn/owner_to_asn.csv` | owner 到 ASN 映射 |
| `--cable-dir` | `data/cable/` | 海缆元数据目录 |
| `--output` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | 预处理输出路径 |
| `--max-hops-unknown` | `2` | 在线推理时，超过该 hop 数就视为 unknown |
| `--search-max-hops` | `2` | 预处理时的离线搜索深度 |
| `--peer-cost` | `1.0` | peer 边成本 |
| `--provider-customer-cost` | `2.0` | provider-customer 边成本 |
| `--limit-owner-groups` | `None` | 可选 smoke test 限制 |

### `python main_analysis.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--as-precompute-file` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | 可选 AS 图预处理输入 |

### `python concerntration_analysis.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--raw-traces-file` | `data/traceroute_rundnsroot/root_dns_traces.json` | 原始 traceroute 输入文件或目录 |
| `--match-output-file` | `output/result/cable_matching_output.json` | 第一阶段输出 JSON |
| `--probe-meta-file` | `data/probe/20251201.json` | probe 元数据文件 |
| `--probe-file-name` | `None` | 从 `data/probe/` 中按文件名选 probe 文件 |
| `--probe-use-latest` | `False` | 自动选择最新 probe JSON |
| `--mmdb-path` | `data/ipinfo/ipinfo_location.mmdb` | geolocation MMDB 路径 |
| `--pfx2as-file` | `data/pfx2as/202512.pfx2as` | pfx2as 路径 |
| `--output-csv` | `output/result/country_root_cable_dependency_hybrid.csv` | 第二阶段主输出路径 |
| `--summary-json` | `None` | 可选第二阶段 summary JSON |
| `--cable-dir` | `data/cable/` | 海缆元数据目录 |
| `--aggregation-mode` | `weighted` | trace 级聚合方式：`hard_top1`、`weighted`、`thresholded_normalized` |
| `--match-threshold` | `0.5` | thresholded 模式的候选阈值 |
| `--confidence-bucket` | `None` | 可选 bucket 过滤：`high`、`medium`、`ambiguous` |
| `--owner-multi-entity-mode` | `full` | owner 是否继承全部支持度还是拆分 |
| `--cross-country` / `--no-cross-country` | `--cross-country` | 是否仅保留跨国路径 |
| `--topn-preview` | `10` | 控制台预览行数 |
| `--output-total-table` | `False` | 输出 total table 合并版本 |
| `--detail-dir` | `None` | 输出 total table 时的各模式细分目录 |
| `--collapse-roots` | `False` | 是否把所有 root 聚合为 `ALL` |

### `python postprocess_candidate_output.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--input` | `output/result/cable_matching_output.json` | 第一阶段 candidate-support JSON |
| `--output` | `output/result/` | 后处理结果目录 |
| `--unit-fields` | `src_country,msm_id,file_name` | 定义 unit 聚合粒度的 `link_info` 字段 |

### `python robustness_compare.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--input` | `output/result/trace_candidate_support.csv` | 展开的 candidate-support 表 |
| `--output` | `output/result/` | robustness 输出目录 |

## 推荐运行顺序

```powershell
python .\precompute_as_graph.py
python .\main_analysis.py
python .\concerntration_analysis.py
python .\postprocess_candidate_output.py --input .\output\result\cable_matching_output.json --output .\output\result
python .\robustness_compare.py --input .\output\result\trace_candidate_support.csv --output .\output\result
```

## 输出文件说明

### A. AS 图预处理输出

#### `output/preprocessed/as_graph_owner_reachability.pkl.gz`

二进制预处理结果，供第一阶段 AS-economic core 使用，包含：

- ASN 到内部节点 ID 的映射
- owner group signature
- endpoint ASN 到 owner group 的 bounded shortest path 信息

这是实现级缓存文件，一般不直接人工阅读。

#### `output/preprocessed/as_graph_owner_reachability.pkl.gz.manifest.json`

用于描述预处理结果的 manifest。

| 字段 | 含义 |
| --- | --- |
| `output_file` | 生成的 payload 路径 |
| `owner_group_count` | 预处理的 owner group 数量 |
| `graph_node_count` | AS 图节点数 |
| `graph_edge_count` | AS 图有向边数 |
| `reachable_entry_count` | 存储的可达条目数 |
| `config` | 预处理配置 |

### B. 第一阶段输出

#### `cable_loading_debug.json`

海缆与 landing station 载入调试文件，用于检查数据是否完整。

#### `output/result/cable_matching_output.json`

第一阶段的主输出，JSON 数组。每个元素代表一个被分析的 hop-pair link，包含三个主要部分：

##### `link_info`

| 字段 | 含义 |
| --- | --- |
| `msm_id` | RIPE Atlas measurement ID |
| `probe_id` | RIPE Atlas probe ID |
| `file_name` | 来源 traceroute 文件 |
| `timestamp` | trace 时间戳 |
| `hop_range` | 该 link 对应的 hop 区间 |
| `src_ip`, `dst_ip` | 相邻 hop 的 IP |
| `src_city`, `dst_city` | 两端地理定位城市 |
| `src_country`, `dst_country` | 两端地理定位国家 |
| `rtt_delta_ms` | 相邻 hop 的 RTT 差值 |
| `is_potential_oceanic` | 是否潜在为跨洋 / 海底链路 |

##### `match_summary`

| 字段 | 含义 |
| --- | --- |
| `filtered_reason` | 若无结果，说明过滤原因 |
| `num_candidates_total` | 阈值前候选总数 |
| `num_candidates_above_threshold` | 阈值后保留候选数 |
| `support_sum` | 该 link 内所有候选 support 之和 |
| `top1_candidate_support`, `top2_candidate_support` | 前两名候选的原始 support |
| `top1_top2_gap` | top1 与 top2 的差距 |
| `confidence_bucket` | `high` / `medium` / `ambiguous` |
| `core_agreement_summary` | core agreement 的 link 级摘要 |
| `ambiguity_summary` | ambiguity 的 link 级摘要 |
| `link_physical_projection_class` | link 级物理投影类别，例如单海缆、平行走廊、多走廊投影 |
| `top1_score`, `top2_score` | 兼容下游的别名字段 |

##### `all_segments[]` 中每个 candidate 的字段

候选身份与 corridor 信息：

| 字段 | 含义 |
| --- | --- |
| `cable_name`, `cable_id` | 候选海缆名称和 ID |
| `segment` | 有向 landing station pair 字符串 |
| `landing_pair` | 保留兼容用途的 landing pair 表达 |
| `corridor_id` | corridor 的规范 ID |
| `corridor_type` | corridor 类型，当前为 `exact_landing_pair` |
| `parallel_group_id` | 平行海缆组 ID |
| `parallel_group_size` | 该组内海缆数量 |
| `is_parallel_ambiguous` | 是否属于平行海缆模糊组 |
| `physical_candidate_group_id` | 类 SRLG 的物理候选分组 ID，当前与 corridor 级平行组保持一致 |
| `physical_candidate_group_type` | 物理候选分组类型，当前为 `srlg_like_corridor_group` |
| `link_physical_projection_class` | 为扁平化分析保留的 link 级物理投影类别 |

support 与排序：

| 字段 | 含义 |
| --- | --- |
| `candidate_support` | 主候选证据分数 |
| `fused_candidate_support` | 当前实现中与 `candidate_support` 相同的融合分数 |
| `normalized_candidate_support` | 在 link 内归一化后的 support |
| `candidate_rank_by_fused_support` | 按 fused support 排名 |
| `geo_only_rank` | 仅按 geo score 排名 |
| `as_only_rank` | 仅按 AS-economic score 排名 |
| `dual_core_rank` | dual-core 融合后的排名 |
| `candidate_rank` | 旧版兼容排名字段 |
| `score_gap_to_top1` | 与 top1 的差值 |

Geo-spatial core：

| 字段 | 含义 |
| --- | --- |
| `geo_spatial_score` | Geo-spatial core 总分 |
| `geo_entry_score`, `geo_exit_score` | link 两端的空间打分 |
| `prob_in`, `prob_out` | 距离衰减项 |
| `d_in`, `d_out` | hop 到 landing station 的距离（km） |
| `ls_entry_to_ls_exit_gcd_km` | 两登陆站之间大圆距离（km） |
| `city_a`, `city_b`, `country_a`, `country_b` | 候选对应的城市 / 国家背景 |
| `geo-a`, `geo-b` | 两端坐标 |

AS-economic core：

| 字段 | 含义 |
| --- | --- |
| `as_economic_score` | AS-economic support 分数 |
| `as_economic_cost` | 代价模型中的 cost |
| `as_economic_reason` | cost 的来源说明 |
| `as_economic_support` | `as_economic_score` 的别名 |
| `as_economic_src_owner_hops`, `as_economic_dst_owner_hops` | 端点 ASN 到 owner group 的 hop 数 |
| `as_economic_src_owner_path_cost`, `as_economic_dst_owner_path_cost` | 端点到 owner group 的路径 cost |
| `as_economic_path_found` | 是否找到了 owner group 路径 |
| `as_economic_owner_group_id` | 内部 owner group ID |
| `src_asn`, `dst_asn` | link 两端 ASN |
| `owner_asn_count` | 候选海缆 owner 对应的 ASN 数量 |

RTT / feasibility：

| 字段 | 含义 |
| --- | --- |
| `rtt_feasible` | 是否通过 RTT feasibility 过滤 |
| `rtt_score` | RTT feasibility 分数 |
| `min_rtt_ms` | 模型估计的最小 RTT |
| `measured_rtt_ms` | 实际测得 RTT 差值 |
| `rtt_margin_ms` | 实测与理论最小 RTT 的裕量 |
| `latency_penalty` | 融合时使用的延迟惩罚项 |

解释与模糊性：

| 字段 | 含义 |
| --- | --- |
| `core_agreement` | geo 与 AS-economic evidence 的一致性类别 |
| `ambiguity_tags` | ambiguity 标签列表 |
| `parallel_segment_candidate_count` | 旧版平行候选计数字段 |
| `dual_core_agreement` | 是否属于 dual-core-agreement |
| `deprecated_fields` | 保留兼容的旧字段名列表 |

旧版兼容别名：

| 字段 | 含义 |
| --- | --- |
| `segment_probability` | `candidate_support` 的旧别名 |
| `geo_score` | `geo_spatial_score` 的旧别名 |
| `ownership_score` | `as_economic_score` 的旧别名 |

#### `output/result/cable_matching_stats_5051.json`

第一阶段整体统计。

| 字段 | 含义 |
| --- | --- |
| `total_links_seen` | 总共检查的 hop-pair link 数 |
| `same_city_filtered` | 被“同城过滤”剔除的 link 数 |
| `links_with_ls_candidates` | 有 landing station 候选的 link 数 |
| `links_with_geo_candidates` | 有 geo 候选的 link 数 |
| `candidate_segments_considered` | RTT 过滤前考虑过的 candidate segment 数 |
| `rtt_infeasible_filtered` | 被 RTT feasibility 去掉的候选数 |
| `links_below_threshold` | 候选存在但都低于阈值的 link 数 |
| `candidates_above_threshold` | 阈值后保留候选总数 |
| `links_with_any_match` | 至少有一个最终候选的 link 数 |
| `links_with_filtered_candidates` | 阈值后仍有候选的 link 数 |
| `links_with_no_feasible_rtt_candidate` | RTT 过滤后一个都不剩的 link 数 |
| `total_candidates_generated` | 原始生成候选数 |
| `total_candidates_after_threshold` | 阈值后保留候选数 |
| `links_with_dual_core_agreement` | 存在 dual-core-agreement 候选的 link 数 |
| `links_with_geo_dominant_as_weak` | geo 主导但 AS 弱的 link 数 |
| `links_with_as_dominant_geo_ambiguous` | AS 主导但 geo 模糊的 link 数 |
| `links_with_parallel_ambiguity` | 存在平行海缆模糊性的 link 数 |
| `links_with_many_candidates` | 候选数过多的 link 数 |
| `links_with_domestic_candidates` | 存在 domestic submarine candidate 的 link 数 |
| `as_precompute_enabled` | 是否启用了 AS 预处理 |
| `candidate_count_list` | 每个 matched link 的候选数量列表 |
| `mean_candidate_count_per_matched_link`, `median_candidate_count_per_matched_link` | 匹配 link 候选数均值 / 中位数 |

#### `output/result/cable_matching_manifest.json`

第一阶段运行 manifest。

| 字段 | 含义 |
| --- | --- |
| `traceroute_file_paths` | 本次处理的 traceroute 输入文件 |
| `total_files_processed` | traceroute 文件数 |
| `total_traces_processed` | traceroute 记录数 |
| `empty_trace_count` | 空 / 无效 trace 数量 |
| `matched_links_above_threshold` | 最终写入输出的 matched link 数 |
| `match_output_file` | 主输出文件路径 |
| `match_stats_file` | stats 文件路径 |
| `as_precompute_file` | 使用的 AS 预处理文件 |
| `method_profile` | 当前方法 profile 名称 |

### C. 第二阶段输出

#### `output/result/country_root_cable_dependency_hybrid.csv`
#### `output/result/country_root_cable_dependency_hybrid_same_source.csv`

国家 / root 级依赖度与集中度表，`_same_source` 是相同 schema 的另一个运行版本。

| 字段 | 含义 |
| --- | --- |
| `Country`, `Root` | 聚合键 |
| `Aggregation_Mode`, `Confidence_Filter`, `Owner_Multi_Entity_Mode` | 第二阶段配置 |
| `Total_Traces` | 该单元总 trace 数 |
| `Submarine_Traces` | 具有 submarine candidate 支撑的 trace 数 |
| `Dependency_Rate` | `Submarine_Traces / Total_Traces` |
| `Top_Cable`, `Top2_Cable` | 聚合后前两名海缆候选 |
| `Top_Cable_Expected_Vol`, `Top2_Cable_Expected_Vol` | 聚合 support 量 |
| `Top_Cable_Share`, `Top2_Cable_Share` | 海缆 support 占总 trace 的比例 |
| `Dominance_Margin` | top1 cable share 与 top2 cable share 的差 |
| `Unique_CrossBorder_AS_Pairs` | 不同跨国 AS pair 的数量 |
| `Top_CrossBorder_AS_Pair`, `Top2_CrossBorder_AS_Pair` | 最常见的跨国 AS pair |
| `Top_CrossBorder_AS_Pair_Count`, `Top2_CrossBorder_AS_Pair_Count` | 对应出现次数 |
| `Top_CrossBorder_AS_Pair_Share`, `Top2_CrossBorder_AS_Pair_Share` | 占总 trace 的比例 |
| `CrossBorder_AS_Pair_Dominance_Margin` | 前两名 AS pair 的差 |
| `Cable_vs_ASPair_Concentration_Gap` | top cable share 与 top AS pair share 的差 |
| `Top_Owner`, `Top2_Owner` | 聚合后前两名 owner |
| `Top_Owner_Expected_Vol`, `Top2_Owner_Expected_Vol` | owner 聚合 support 量 |
| `Top_Owner_Share`, `Top2_Owner_Share` | owner 占比 |
| `Owner_Dominance_Margin` | owner 前两名差值 |
| `Cable_Owner_Concentration_Gap` | top owner share 与 top cable share 的差 |
| `High_Bucket_Traces`, `Medium_Bucket_Traces`, `Ambiguous_Bucket_Traces` | 各 confidence bucket 的 trace 数 |

#### `output/result/country_root_dependency_total.csv`

三种第二阶段配置合并后的总表，包括：

- `weighted_all`
- `hard_top1_all`
- `weighted_high`

这些模式下大部分字段都带对应后缀。额外的稳定性字段：

| 字段 | 含义 |
| --- | --- |
| `Cable_Stable_vs_Hard`, `Cable_Stable_vs_High`, `Cable_Stable_All3` | top cable 是否在不同设置下稳定 |
| `Owner_Stable_vs_Hard`, `Owner_Stable_vs_High`, `Owner_Stable_All3` | top owner 是否稳定 |

#### `output/result/dependency_variants/*.csv`（可选）

当第二阶段使用 `--output-total-table --detail-dir ...` 运行时，会在该目录下生成按模式拆开的细表，例如 `weighted_all.csv`、`hard_top1_all.csv`、`weighted_high.csv`。

这些文件与 `country_root_cable_dependency_hybrid.csv` 使用相同 schema，只是每个文件只对应一种聚合 / confidence-filter 设置。

#### `output/result/country_root_summary.json`
#### `output/result/country_root_summary_same_source.json`

第二阶段的小型 summary 文件。

| 字段 | 含义 |
| --- | --- |
| `raw_traces_file`, `resolved_raw_trace_files` | 使用的原始 traceroute 输入 |
| `match_output_file` | 第一阶段输出文件 |
| `probe_meta_file` | probe 元数据文件 |
| `mmdb_path`, `pfx2as_file`, `cable_dir` | 参考输入文件 |
| `output_csv` | 第二阶段主输出路径 |
| `aggregation_mode`, `collapse_roots`, `match_threshold`, `confidence_bucket`, `cross_country`, `owner_multi_entity_mode` | 第二阶段配置 |
| `rows`, `countries`, `roots` | 输出规模信息 |

### D. 后处理输出

#### `output/result/trace_candidate_support.csv`

由 `cable_matching_output.json` 展开得到的 candidate-level 表。它包含前文 `link_info`、`match_summary`、candidate 字段，以及：

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 由 `--unit-fields` 定义的聚合单元 ID |
| `link_id` | link 唯一标识 |
| `record_index` | 原始 Stage 1 记录索引 |
| `corridor_id_fallback`, `parallel_group_id_fallback` | 缺少显式 corridor 字段时的回退列 |
| `physical_candidate_group_id`, `physical_candidate_group_type`, `physical_candidate_group_id_fallback` | 用于 corridor / bundle 分析的类 SRLG 物理分组列 |
| `link_physical_projection_class` | 下游 mismatch 与 robustness 会使用的 link 级投影类别 |

#### `output/result/unit_physical_candidate_diversity_cable.csv`
#### `output/result/unit_physical_candidate_diversity_corridor.csv`
#### `output/result/unit_physical_candidate_diversity.csv`

物理候选多样性表。`unit_physical_candidate_diversity.csv` 是 cable-level 的 legacy alias。

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `physical_level` | `cable` 或 `corridor` |
| `dominant_candidate_key` | 支撑占比最高的 cable ID 或 corridor ID |
| `dominant_candidate_support_share` | 主导候选的支持占比 |
| `expected_candidate_support_total` | 聚合前 support 总量 |
| `candidate_entropy` | 候选分布的 Shannon entropy |
| `effective_num_candidates` | `exp(entropy)`，等效候选数 |
| `gini_candidate_support` | 候选支撑分布的 Gini 系数 |
| `num_candidates_with_support` | 非零候选数量 |
| `num_matched_links` | 该 unit 中匹配成功的 link 数 |
| `num_probes` | 该 unit 中 probe 数 |
| `physical_candidate_diversity_score` | 物理多样性主分数，当前等于 `effective_num_candidates` |
| `candidate_identifier_column` | 实际用于聚合的列，例如 `cable_id`、`corridor_id` 或 `segment` |

#### `output/result/unit_network_layer_diversity.csv`
#### `output/result/unit_logical_diversity.csv`

unit 级 network diversity 表。`unit_logical_diversity.csv` 是 legacy alias。

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `num_probes`, `num_measurements`, `num_files_or_targets` | 单元规模信息 |
| `num_dst_countries`, `num_src_dst_country_pairs` | 地理多样性计数 |
| `num_src_asns`, `num_dst_asns`, `num_src_dst_as_pairs` | ASN 多样性计数 |
| `link_country_sequence_entropy` | 国家对序列的熵 |
| `src_asn_entropy`, `dst_asn_entropy` | 源 / 目的 ASN 熵 |
| `as_pair_entropy`, `src_dst_as_pair_entropy` | 源-目的 ASN pair 的熵 |
| `network_score_component_as_pair` | 复合分数中的 AS pair 分量 |
| `network_score_component_country_pair` | 复合分数中的国家对分量 |
| `network_score_component_endpoint_asn` | 复合分数中的 endpoint ASN 分量 |
| `network_score_component_probe_target` | 复合分数中的 probe/target 分量 |
| `network_layer_diversity_score_as_only` | 仅 AS 相关分量的分数 |
| `network_layer_diversity_score_country_only` | 仅国家相关分量的分数 |
| `network_layer_diversity_score_probe_target_only` | 仅 probe/target 分量的分数 |
| `network_layer_diversity_score` | network-layer diversity 主分数 |
| `logical_diversity_score` | 与 `network_layer_diversity_score` 相同的 legacy alias |

#### `output/result/unit_network_physical_mismatch.csv`
#### `output/result/unit_network_physical_mismatch_corridor.csv`
#### `output/result/unit_mismatch.csv`

network diversity 与 physical diversity 连接后的 mismatch 表。`unit_mismatch.csv` 是 cable-level 的 legacy alias。

这些表包含全部 network-layer 字段、全部 physical diversity 字段，以及：

| 字段 | 含义 |
| --- | --- |
| `network_high` | 是否高于 network diversity 中位数 |
| `physical_low` | 是否低于或等于 physical diversity 中位数 |
| `network_physical_mismatch_category` | 四象限类别 |
| `network_physical_gap` | network score 减去 physical score |
| `network_definition` | 当前 mismatch 视图使用的 network diversity 定义 |
| `network_score_column` | 实际用于 mismatch 计算的 network score 列名 |
| `selected_network_diversity_score` | 该 mismatch 视图实际选用的 network score |
| `network_diversity_percentile`, `physical_diversity_percentile` | network 与 physical 分数的百分位位置 |
| `network_physical_percentile_gap` | network 与 physical 的百分位差值 |
| `network_diversity_rank`, `physical_diversity_rank` | network 与 physical 的降序排名 |
| `network_physical_rank_gap` | physical 与 network 的 rank-gap mismatch |
| `logical_physical_gap` | 同上，legacy alias |
| `logical_high` | `network_high` 的 legacy alias |
| `mismatch_category` | `network_physical_mismatch_category` 的 legacy alias |
| `is_target_quadrant` | 是否属于 `network_high_physical_low` |

#### `output/result/network_physical_quadrants.csv`

| 字段 | 含义 |
| --- | --- |
| `physical_level` | `cable` 或 `corridor` |
| `network_physical_mismatch_category` | 四象限标签 |
| `unit_count` | 该象限中的 unit 数 |
| `unit_share` | 占全部 unit 的比例 |

#### `output/result/cable_vs_corridor_physical_diversity.csv`

对比 cable-level 与 corridor-level 物理多样性的表。

| 字段组 | 含义 |
| --- | --- |
| `cable_*` | cable-level 的 diversity 指标和象限标签 |
| `corridor_*` | corridor-level 的 diversity 指标和象限标签 |
| `corridor_minus_cable_physical_diversity` | corridor 分数减去 cable 分数 |
| `corridor_vs_cable_effective_num_ratio` | 两者等效候选数比值 |
| `target_quadrant_preserved` | 是否在两层级都保持为目标象限 |
| `quadrant_label_stable` | 两层级四象限标签是否一致 |

#### `output/result/unit_ambiguity_profile.csv`

unit 级 ambiguity profile。

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `num_candidate_rows` | 候选行数 |
| `num_links` | 链路数 |
| `*_support_share` | 某类 ambiguity 占该 unit 支撑的比例 |
| `no_ambiguity_support_share` | 无 ambiguity 标签的支撑占比 |

#### `output/result/ambiguity_summary.csv`

全局 ambiguity 汇总表。

| 字段 | 含义 |
| --- | --- |
| `ambiguity_class` | ambiguity 类别，包括 `no_ambiguity` |
| `candidate_rows` | 带该标签的候选行数 |
| `candidate_row_share` | 候选行占比 |
| `aggregate_normalized_support` | 累积 support 总量 |
| `aggregate_support_share` | support 占全部 support 的比例 |
| `units_affected` | 受影响的 unit 数 |

#### `output/result/ambiguity_taxonomy.csv`

ambiguity 标签的解释表。

| 字段 | 含义 |
| --- | --- |
| `ambiguity_class` | 标签名 |
| `reviewer_concern` | 论文审稿人可能关注的问题 |
| `treatment` | 代码与分析中如何处理 |
| `interpretation_boundary` | 不应过度解释到什么程度 |

#### `output/result/core_agreement_summary.csv`

evidence core 一致性统计。

| 字段 | 含义 |
| --- | --- |
| `core_agreement` | 一致性类别，如 `dual_core_agreement` |
| `candidate_rows` | 该类别候选行数 |
| `candidate_row_share` | 候选行占比 |
| `aggregate_normalized_support` | 该类别的累积 support |
| `aggregate_support_share` | support 占比 |
| `units_affected` | 涉及的 unit 数 |

#### `output/result/as_reranking_effect.csv`

描述 geo-only、AS-only 与 fused 排名关系的 link 级统计。

| 字段 | 含义 |
| --- | --- |
| `total_links` | 分析的 link 数量 |
| `geo_as_top_agreement_rate` | geo top1 与 AS top1 一致比例 |
| `geo_fused_top_agreement_rate` | geo top1 与 fused top1 一致比例 |
| `as_fused_top_agreement_rate` | AS top1 与 fused top1 一致比例 |
| `as_changes_geo_top1_rate` | AS 是否改变 geo top1 的比例 |
| `mean_geo_to_fused_rank_shift` | geo top1 到 fused 排名的平均偏移 |
| `mean_as_to_fused_rank_shift` | AS top1 到 fused 排名的平均偏移 |
| `parallel_links` | 平行海缆 link 数 |
| `parallel_links_with_dual_core_agreement` | 平行 link 中存在 dual-core agreement 的数量 |
| `parallel_links_remaining_ambiguous` | 平行 link 中仍然 ambiguous 的数量 |

#### `output/result/filtering_breakdown.csv`

第一阶段过滤和保留过程的轻量汇总。

| 字段 | 含义 |
| --- | --- |
| `total_traces_processed` | 处理的 traceroute 数量 |
| `empty_trace_count` | 空 / 无效 trace 数量 |
| `total_links_seen` | 总 link 数 |
| `same_city_filtered` | 同城过滤掉的 link 数 |
| `links_with_ls_candidates` | 有 landing station 候选的 link 数 |
| `links_with_geo_candidates` | 有 geo 候选的 link 数 |
| `candidate_segments_considered` | RTT 过滤前考虑过的 segment 数 |
| `rtt_infeasible_filtered` | RTT 不可行被去掉的候选数 |
| `links_with_any_match` | 至少有一个最终匹配的 link 数 |
| `total_candidates_generated` | 原始候选数 |
| `total_candidates_after_threshold` | 阈值后保留候选数 |
| `links_with_parallel_ambiguity` | 存在平行模糊性的 link 数 |
| `links_with_domestic_candidates` | 存在 domestic submarine candidate 的 link 数 |

#### `output/result/dataset_summary.csv`

两列 summary 表。

| 字段 | 含义 |
| --- | --- |
| `metric` | 指标名称 |
| `value` | 指标值 |

#### `output/result/method_manifest.json`

后处理方法 manifest。

| 字段 | 含义 |
| --- | --- |
| `method_name` | 方法名称 |
| `main_question` | 主审计问题 |
| `claim_boundary` | 解释边界 |
| `primary_target_quadrant` | 重点关注的 mismatch 象限 |
| `evidence_cores` | 使用的 evidence core |
| `fusion_model` | 融合模型名称 |
| `physical_levels` | 支持的物理层粒度 |
| `ambiguity_classes` | 已知 ambiguity 标签 |
| `network_definitions` | 在 mismatch 与 robustness 中支持的 network diversity 定义 |
| `primary_outputs` | 主要后处理输出 |
| `interpretation` | 一句解释说明 |

#### 后处理 SVG 图文件

| 文件 | 含义 |
| --- | --- |
| `network_physical_quadrant_scatter_cable.svg` | network vs cable-level physical diversity 散点图 |
| `network_physical_quadrant_scatter_corridor.svg` | network vs corridor-level physical diversity 散点图 |
| `network_physical_quadrant_counts_cable.svg` | cable-level 四象限数量柱状图 |
| `network_physical_quadrant_counts_corridor.svg` | corridor-level 四象限数量柱状图 |
| `cable_vs_corridor_physical_diversity.svg` | cable-level vs corridor-level 物理多样性对比图 |

### E. Robustness 输出

#### `output/result/robustness_summary.csv`

| 字段 | 含义 |
| --- | --- |
| `mode` | evidence setting 名称 |
| `network_definition` | 本次比较使用的 network diversity 定义 |
| `physical_level` | `cable` 或 `corridor` |
| `num_units_compared` | 与 baseline 比较的 unit 数 |
| `spearman_dominant_candidate_support_share` | dominant support share 的 Spearman 相关性 |
| `spearman_effective_num_candidates` | effective number 的 Spearman 相关性 |
| `topk_dominant_share_overlap` | top-k 主导 share 单元重合度 |

#### `output/result/robustness_mismatch_stability.csv`

| 字段 | 含义 |
| --- | --- |
| `mode` | evidence setting 名称 |
| `network_definition` | 本次比较使用的 network diversity 定义 |
| `physical_level` | `cable` 或 `corridor` |
| `num_units_compared` | 参与比较的 unit 数 |
| `baseline_target_units` | baseline 的目标象限 unit 数 |
| `mode_target_units` | 当前设置下的目标象限 unit 数 |
| `shared_target_units` | 两者重合的目标象限 unit 数 |
| `target_jaccard_vs_baseline` | 与 baseline 的 Jaccard 重合度 |
| `target_precision_vs_baseline` | 相对 baseline 的 precision |
| `target_recall_vs_baseline` | 相对 baseline 的 recall |
| `quadrant_agreement_rate` | 四象限标签整体一致率 |

#### `output/result/robustness_quadrant_summary.csv`

| 字段 | 含义 |
| --- | --- |
| `physical_level` | `cable` 或 `corridor` |
| `network_physical_mismatch_category` | 四象限标签 |
| `unit_count` | 该象限 unit 数 |
| `unit_share` | 占比 |
| `network_definition` | 该 robustness 切片使用的 network diversity 定义 |
| `mode` | evidence setting 名称 |

#### `output/result/robustness_profile_table.csv`

更适合论文正文表格引用的 robustness 表。

| 字段 | 含义 |
| --- | --- |
| `setting` | 完整设置名，如 `fused_dual_core_cable` |
| `evidence_view` | 更粗粒度的 evidence 类别，如 `geo_only`、`as_only` |
| `network_definition` | 使用的 network diversity 定义，例如 `composite`、`as_only`、`country_only` |
| `physical_level` | `cable` 或 `corridor` |
| `physical_projection_setting` | 物理投影设置，表示是直接 cable 候选还是 corridor 聚合候选 |
| `rank_corr_dominant_support` | dominant support 排名相关性 |
| `rank_corr_effective_num` | effective number 排名相关性 |
| `target_quadrant_jaccard` | 目标象限 unit 的 Jaccard 重合度 |
| `target_quadrant_recall` | 目标象限 unit 的 recall |
| `quadrant_agreement_rate` | 四象限一致率 |
| `interpretation` | 对该 robustness setting 的文字说明 |

#### `output/result/robustness_network_high_physical_low_stability.svg`

展示不同 robustness setting 下 `network_high_physical_low` 单元重合情况的柱状图。

## 协作说明

- 仓库设计为通过 GitHub 在多台电脑之间协作使用。
- 默认共享主线是 `origin/main`。
- 运行时数据文件仍然是本地输入；代码与文档通过 Git 跟踪。
- 面向 Codex/agent 的协作规则见 `AGENTS.md`。

## 本轮新增内容补充

### 新增字段

#### `trace_candidate_support.csv` 补充字段

| 字段 | 含义 |
| --- | --- |
| `projection_class` | 投影质量分级：`strong`、`moderate`、`weak`、`ambiguous` |

#### `unit_physical_candidate_diversity_cable.csv` / `unit_physical_candidate_diversity_corridor.csv` 补充字段

| 字段 | 含义 |
| --- | --- |
| `feasible_candidate_count` | 该聚合层级下可行候选集合大小 |
| `candidate_entropy_uniform` | 忽略 support 权重、将可行候选视为均匀分布时的熵 |
| `effective_candidate_count_uniform` | 均匀可行候选集合对应的等效候选数 |

### 新增输出文件

#### `output/result/unit_physical_candidate_upper_bound.csv`

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `num_feasible_candidates` | 不同可行 cable 候选数量 |
| `num_feasible_corridors` | 不同可行 corridor 数量 |
| `candidate_entropy_uniform` | cable 候选集合的均匀熵 |
| `corridor_entropy_uniform` | corridor 集合的均匀熵 |
| `effective_candidate_count_uniform` | 均匀 cable 等效候选数 |
| `effective_corridor_count_uniform` | 均匀 corridor 等效候选数 |
| `physical_candidate_diversity_upper_bound` | 保守物理多样性上界分数，当前采用可行 cable 数视角 |

#### `output/result/unit_network_physical_upper_bound_mismatch.csv`

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `network_diversity_combined` | 组合 network-layer diversity 分数 |
| `network_diversity_as_only` | AS-only network diversity 分数 |
| `network_diversity_country_only` | country-only network diversity 分数 |
| `network_diversity_target_probe` | probe/target multiplicity 分数 |
| `physical_candidate_diversity_upper_bound` | 保守物理多样性上界分数 |
| `network_percentile` | 组合 network diversity 的百分位 |
| `physical_upper_percentile` | 物理上界分数的百分位 |
| `rank_gap_upper_bound` | 物理上界与 network diversity 的 rank-gap |
| `strict_upper_bound_mismatch` | 即使在保守物理上界下仍然是 “network 高、physical 低” 的单元 |

#### `output/result/candidate_space_profile.csv`

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `avg_candidates_per_link`, `max_candidates_per_link` | 每条 link 的平均 / 最大可行 cable 候选数 |
| `avg_corridors_per_link`, `max_corridors_per_link` | 每条 link 的平均 / 最大可行 corridor 数 |
| `share_parallel_ambiguity` | 含平行走廊歧义的 link 占比 |
| `share_multi_segment_possible` | 含多段可能性的 link 占比 |
| `share_domestic_submarine` | 含 domestic submarine candidate 的 link 占比 |
| `share_large_radius` | 含 large landing-radius 歧义的 link 占比 |
| `share_low_confidence_projection` | `projection_class` 为 `weak` 或 `ambiguous` 的 link 占比 |

#### `output/result/weighted_vs_conservative_diversity.csv`

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 聚合单元 |
| `weighted_effective_corridors` | 基于 weighted candidate support 的 corridor 等效多样性 |
| `uniform_effective_corridors` | 基于均匀可行 corridor 集合的等效多样性 |
| `weighted_entropy` | weighted corridor 熵 |
| `uniform_entropy` | uniform corridor 熵 |
| `weighted_rank`, `uniform_rank` | weighted / uniform corridor 视图下的 unit 排名 |
| `weighted_gap`, `uniform_gap` | network diversity 与 weighted / uniform corridor 多样性之间的差值 |

#### `output/result/robustness_candidate_space.csv`

| 字段 | 含义 |
| --- | --- |
| `network_definition` | 本次比较使用的 network diversity 定义 |
| `setting` | robustness setting 名称 |
| `weighting_view` | `weighted` 或 `uniform` 物理多样性视图 |
| `physical_level` | `cable` 或 `corridor` |
| `physical_projection_setting` | 直接 cable 候选或 corridor-grouped 候选 |
| `projection_subset` | 使用全部投影还是仅使用 `strong` 投影 |
| `num_units_compared` | 参与比较的 unit 数量 |
| `rank_corr_physical_diversity` | 相对 corridor-weighted baseline 的物理多样性排名相关 |
| `target_quadrant_jaccard` | 相对 corridor-weighted baseline 的目标象限 Jaccard 重合度 |
| `target_quadrant_recall` | 相对 corridor-weighted baseline 的目标象限召回率 |
| `quadrant_agreement_rate` | 相对 corridor-weighted baseline 的整体象限一致率 |
| `baseline_setting` | 当前 baseline，现为 `weighted_all_corridor` |

## 最新保守候选空间审计补充

仓库现在明确区分两种 Stage 1 候选视图：

- `all_feasible_segments`：先做 infeasibility-first 过滤后保留下来的全部可行候选集合，不受 support threshold 限制。
- `all_segments`：为兼容旧流程保留的 support-thresholded legacy 视图。

### 新增 Stage 1 `match_summary` 字段

| 字段 | 含义 |
| --- | --- |
| `num_feasible_candidates_total` | 当前 link 的可行候选总数 |
| `num_feasible_corridors_total` | 当前 link 的可行 corridor 总数 |
| `feasible_candidate_retention_mode` | 当前固定为 `infeasibility_first` |
| `support_threshold_used_for_legacy_all_segments` | support threshold 只用于 legacy `all_segments` 视图 |
| `support_threshold_value` | legacy 视图使用的阈值 |

### 新增 candidate 字段

| 字段 | 含义 |
| --- | --- |
| `hard_feasible` | 是否通过硬可行性过滤 |
| `infeasibility_filter_passed` | 是否通过 infeasibility-first 过滤 |
| `support_above_threshold` | 是否高于 legacy threshold |
| `support_filter_reason` | `above_threshold` 或 `below_threshold_but_feasible` |
| `geo_entry_support`, `geo_exit_support`, `geo_spatial_support` | Geo 证据支持分数；保留旧 `prob_*` 字段仅作兼容，不表示真实海缆使用概率 |

### 新增输出文件

| 文件 | 含义 |
| --- | --- |
| `output/result/trace_feasible_candidate_space.csv` | 从 `all_feasible_segments` 展开的可行候选空间表；旧 JSON 若缺少该字段会自动 fallback 到 `all_segments` 并告警 |
| `output/result/unit_physical_candidate_set_diversity_cable.csv` | cable-level 保守可行集合多样性 |
| `output/result/unit_physical_candidate_set_diversity_corridor.csv` | corridor-level 保守可行集合多样性，也是论文主物理层视图 |
| `output/result/unit_network_physical_upper_bound_mismatch.csv` | 使用 conservative feasible-set upper bound 的 long-form mismatch 表，覆盖全部 network definition 和 cable/corridor 两层 |
| `output/result/paper_unit_physical_candidate_diversity.csv` | 论文默认使用的 corridor-level 保守可行集合多样性别名 |
| `output/result/paper_unit_network_physical_mismatch.csv` | 论文默认使用的 corridor-level upper-bound mismatch 别名 |
| `output/result/conservative_candidate_audit_manifest.json` | 说明 infeasibility-first 语义、weighted view 与 conservative set view 的简明 manifest |
| `output/result/robustness_conservative_candidate_audit.csv` | 对比 weighted support 与 conservative feasible set 的 robustness 表 |

### 解释边界

- Geo / RTT / landing / country 等约束主要用于排除不可能或高度不可信的候选。
- `candidate_support` 是保留后的可行候选集合内部的 evidence support，不是 ground-truth 海缆使用概率。
- conservative set-based diversity 把所有可行候选等权看待，因此应解释为“可能物理多样性上界”。
