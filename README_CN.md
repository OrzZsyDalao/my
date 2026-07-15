# infocom26 项目说明

## Run-isolated 可复现运行

论文实验写入独立的 `runs/<run_id>/`；历史 `output/` 目录不能作为论文结果包。每个 run 记录输入校验和、参数配置、Git commit、measurement 状态、日志和 trace 分母。结果打包只读取当前 run index 中 `status=completed` 的 measurement，避免历史输出污染。

```powershell
python -m pipeline.run_experiment --measurement-id 5009
python -m pipeline.run_experiment --resume-run-id <failed_run_id>
python -m pipeline.package_paper_results --run-id <run_id>
```

跨服务 matched comparison 被明确标记为 `optional_posthoc_analysis`，不会由全量 pipeline 自动运行，也不影响 measurement 完成状态或论文结果打包：

```powershell
python -m pipeline.matched_comparison --run-id <run_id> --comparison-services Wikipedia,Reddit
```

论文正文的走廊集中度只使用 `international_inter_region` 与 `domestic_inter_region` 候选。`intra_landing_region` 候选仍保留在可行候选审计和补充输出中，但不会进入正文的跨区域走廊分布。完整 summary 同时输出 `all_publicly_visible` 和 `resolved_entry_only` 两种 path scope；所有 `paper_*.csv` 均严格限制为 `auditable_paper_case == True`。RTT 与生命周期等候选级统计使用 `candidate_rows_*` 命名，`atomic_segments_*` 只统计唯一 hop-pair 观测。

论文可审计阈值使用完整“国家—服务—path scope”分组内 probe 与 probe ASN 的并集。每条走廊的 `unique_probes` 仅作为走廊内描述；`group_unique_probes` 和 `group_unique_probe_asns` 才是 corridor concentration 与可审计判定使用的组级数量。

默认参数受版本控制，位于 `config/default_experiment.json`。`all_feasible_segments` 是 infeasibility-first 候选集合；`all_segments` 仅是保留兼容性的 support-thresholded 视图。Candidate support 是证据分数，不是实际海缆使用概率。由于当前海缆元数据通常只提供无序 landing-point 集合，而没有路由或 branch topology，默认的 `allow_unordered_reachability` 会枚举同一条海缆上有效登陆站之间的两两组合，作为可达性候选。这些候选会明确标注为 `unordered_cable_reachability`，不代表已确认的直接物理海缆段。只有在有显式有序路径或 segment/branch topology 时，才建议使用 `--cable-topology-policy adjacent_only` 进行严格直接物理段的敏感性分析。timeout gap 和 same-city geolocation ambiguity 会保留为字段。observation mass 只表示 traceroute 观测到的路径转换，不表示流量、数据包或实际海缆利用率。

## 当前论文主框架

当前 paper-facing 分析统一为 **application / network / corridor distribution audit**，核心问题是：

> 对于一个来源探针国家访问一个应用服务时，网络层观测到的路径转换分布，在投影到可行海缆走廊后是否仍然保持分散，还是集中在少量物理走廊上？

主流程为：

```text
Application observation
  -> publicly visible client-to-service path
  -> atomic network-transition segments
  -> infeasibility-first physical candidate construction
  -> landing-region corridor projection
  -> corridor observation-mass distribution
  -> network-transition vs corridor-distribution audit
```

主分析单元是 `probe_country x service_id`。`probe_country` 来自 RIPE Atlas probe metadata；`transition_near_country` 和 `transition_far_country` 描述 hop-pair transition 的地理两端，二者不能混用。

| 层级 | 主观测对象 |
| --- | --- |
| Application | `service_id`、实际 `target_ip` / `target_asn`、`probe_country` |
| Network | 同一批 mappable atomic segments 上的 AS / country transition |
| Physical | 可行 landing-region corridor candidates |
| Aggregate | service physical exposure、corridor concentration、cross-layer distribution class |

论文主输出文件：

- `paper_service_country_physical_exposure.csv`
- `paper_service_country_corridor_concentration.csv`
- `paper_service_country_cross_layer_distribution.csv`
- `paper_network_broad_physical_concentrated_cases.csv`
- `paper_broad_corridor_distribution_cases.csv`
- `paper_physical_exposure_cases.csv`

`observation_mass` 表示 measurement-observed transition mass，不表示真实流量、包数量、带宽或真实海缆使用概率。candidate breadth、best-case upper bound、compression ratio、rank-gap mismatch、cable-level weighted support、product-of-experts ranking、AS-owner reranking 都保留为 supplementary views。

推荐运行顺序：

1. 下载或准备 RIPE Atlas traceroute。
2. 准备 probe metadata、pfx2as、IP geolocation、AS relationship、owner-to-AS、cable metadata。
3. 运行 Stage 1 feasible corridor construction：`python source/main_analysis.py --landing-region-radius-km 50 --rtt-tolerance-ms 5`
4. 运行 Stage 2 application/network/corridor distribution audit：`python source/postprocess_candidate_output.py --input output/result/cable_matching_output.json --output output/result`
5. 运行 robustness analyses：`python source/robustness_compare.py --input output/result/trace_candidate_support.csv --output output/result`
6. 可选运行 legacy cable / owner analysis。

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

probe/
  run_ripe_atlas_traceroute.py
  atlas_traceroute_config.example.json
  results/

ripe_atlas_public_download/
  download_public_traceroutes.py
  run_per_measurement_pipeline.py
  manifests/

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

6. `probe/run_ripe_atlas_traceroute.py`
   辅助实验脚本。读取本地 RIPE Atlas 配置 JSON，选择活跃公开探针，按批次创建指向指定目标的一次性 traceroute 测量。它不会改动主分析流程，只负责补充实验测量。

7. `ripe_atlas_public_download/download_public_traceroutes.py`
   公开数据下载脚本。下载第一轮 RIPE Atlas 公开 IPv4 traceroute measurement 数据，默认时间窗口为 2026-07-01 00:00:00 UTC 到 01:00:00 UTC。脚本会先校验 measurement metadata，再把可直接进入主流程的结果 JSON 数组写入 `data/traceroute_rundnsroot/`。

8. `ripe_atlas_public_download/run_per_measurement_pipeline.py`
   按 measurement 分别运行的批处理脚本。它会发现已下载的公开 traceroute 文件，按 `msm_id` 创建独立结果文件夹，并分别运行 `main_analysis.py`、`postprocess_candidate_output.py` 和 `robustness_compare.py`。

## 输入文件说明

### 通用输入文件

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `data/cable/landing-point-geo.json` | 第一阶段 | GeoJSON，`features[].properties.id` 为 landing station ID，geometry 为坐标 | landing station 坐标索引 |
| `data/cable/*.json` | 第一阶段、第二阶段、AS 预处理 | 每根海缆一个 JSON，包含 `id`、`name`、`landing_points`、`owners` 等 | 海缆元数据、登陆站对、owner 信息 |
| `data/ipinfo/ipinfo_location.mmdb` | 第一阶段、第二阶段 | MMDB geolocation 数据库 | IP 到国家 / 城市的地理映射 |
| `data/ipinfo/ipinfo_asn.mmdb` | 第一阶段、第二阶段 | IPinfo ASN MMDB 数据库 | 当前所有 hop、endpoint、target、service-entry、network-transition 的 IP 到 ASN 映射来源 |
| `data/asrelationship/20250901.as-rel2.txt` | 第一阶段、AS 预处理 | CAIDA 格式 AS 关系文件 | AS-economic core 的关系图输入 |
| `data/pfx2as/202512.pfx2as` | 旧实验兼容 | prefix 到 origin ASN 的映射 | 保留给旧实验；当前 IP 到 ASN 解析使用 `data/ipinfo/ipinfo_asn.mmdb` |
| `data/owner2asn/owner_to_asn.csv` | 第一阶段、AS 预处理 | `owner,asn` 两列 | cable owner 到 ASN 的映射 |

### traceroute 与 probe 输入

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `data/traceroute_rundnsroot/root_dns_traces.json` | 第一阶段默认、第二阶段默认 | RIPE Atlas traceroute JSON 数组 | 小规模日常测试输入 |
| `data/traceroute_rundnsroot/**/*.json` | 第一阶段 | RIPE Atlas traceroute 结果文件 | 第一阶段主输入目录 |
| `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100/*.json` | 第一阶段 | 下载得到的 RIPE Atlas traceroute result 数组，文件名包含 dataset、服务/root 名称、`msm_id` 和 UTC 时间窗口 | 第一轮 DNS Root、应用、扩展和 topology baseline 数据集 |
| `data/traceroute/ripe_atlas_5051_20251201.json` | 可选 | 大规模 traceroute 输入 | 全量运行用 |
| `data/probe/*.json` | 第二阶段 | probe 元数据，通常包含 `objects[].id` 与 `objects[].country_code` | 将 probe ID 映射到源国家 |

### 可选预处理输入

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `output/preprocessed/as_graph_owner_reachability.pkl.gz` | 第一阶段 | gzip pickle 格式的 owner-group reachability 结果 | 加速 AS-economic support 计算 |

### probe 辅助脚本本地文件

| 路径 | 被哪些流程使用 | 预期内容 | 作用 |
| --- | --- | --- | --- |
| `probe/atlas_traceroute_config.example.json` | probe 辅助脚本 | 包含 `api_key`、`targets`、`probe_selection`、`measurement_defaults` 的 JSON 模板 | RIPE Atlas 测量创建模板 |
| `probe/atlas_traceroute_config.local.json` | probe 辅助脚本，可选 | 与示例模板相同的 JSON 结构 | 推荐本地保存真实 API key 和实验目标 |
| `probe/results/*.json` | probe 辅助脚本输出 | 测量提交回执与返回的 measurement IDs | 后续数据采集前的本地实验记录 |

### 2026-07-01 公开 Atlas 结果打包与同步

`ripe_atlas_public_download/package_paper_csv_results.py` 会从每个 `msm_id` 的结果目录中收集论文级的国家/服务-国家汇总、走廊观察分布、跨层审计与案例 CSV，输出到 `results/july1_public_atlas_20260701/`。`run_july1_pipeline_and_publish.ps1` 则在全部 pipeline 成功后打包、暂存该目录、提交并推送到 `main`。它不会提交原始 RIPE JSON、匹配 JSON 或 trace-level 大型表，并对单文件应用 95 MB GitHub 上限保护。

全量批处理可以重复使用 `--exclude-measurement-id` 排除指定 `msm_id`，例如 `--exclude-measurement-id 5051 --exclude-measurement-id 5151`。

`--publish-paper-results` 可以在所有已选 measurement 成功完成后，只打包并提交论文级 CSV 结果，不会暂存原始数据或 trace-level 大型表。

若全量 pipeline 已以 Windows 计划任务的方式运行，可使用 `publish_july1_results_after_task.ps1`。它只会等待该任务成功结束后打包并推送，不会重复运行一遍测量 pipeline。

`resume_incomplete_july1_pipeline.ps1` 用于继续优化后 2026-07-01 批处理中被中断的 8 个非 baseline measurement，成功后同样只打包并推送论文级 CSV。

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
| `--asn-mmdb-path` | `data/ipinfo/ipinfo_asn.mmdb` | IPinfo ASN MMDB 路径，用于当前 IP 到 ASN 映射 |
| `--pfx2as-file` | `data/pfx2as/202512.pfx2as` | 旧兼容参数；当前 IP 到 ASN 映射使用 `--asn-mmdb-path` |
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

### `python probe/run_ripe_atlas_traceroute.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--config` | 自动检测 | 配置文件路径。脚本会依次尝试 `probe/atlas_traceroute_config.local.json`、`probe/atlas_traceroute_config.json`、`probe/atlas_traceroute_config.example.json` |
| `--output` | `probe/results/` | 提交回执输出目录 |
| `--dry-run` | `False` | 只预览选中的 probes 和测量 payload，不真正提交 |
| `--limit-probes` | `None` | 可选 CLI 覆盖，用于限制选中的 probe 数量 |
| `--list-only` | `False` | 仅拉取并预览选中的 probes，不构造也不提交测量 |

### `python ripe_atlas_public_download/download_public_traceroutes.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--output-dir` | `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100` | 可直接被主流程读取的 RIPE Atlas result JSON 数组输出目录 |
| `--manifest` | `ripe_atlas_public_download/manifests/` 下自动生成 | manifest 路径，记录 metadata 校验、输出文件、字节数和记录数 |
| `--start` | `2026-07-01T00:00:00Z` | UTC 下载窗口开始时间 |
| `--duration-minutes` | `60` | 下载窗口长度 |
| `--measurement-id` | 默认全部 18 个第一轮 measurement | 可选过滤项，可重复传入以只下载或测试指定 measurement |
| `--metadata-only` | `False` | 只校验 RIPE Atlas measurement metadata，不下载结果数据 |
| `--skip-existing` | `False` | 如果输出文件已存在，则复用已有文件 |
| `--no-count-records` | `False` | 下载后跳过流式记录数统计 |
| `--timeout` | `120` | HTTP 超时时间，单位秒 |
| `--retries` | `3` | HTTP 重试次数 |

### `python ripe_atlas_public_download/run_per_measurement_pipeline.py`

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--input-dir` | `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100` | 已下载公开 Atlas traceroute JSON 数组所在目录 |
| `--output-root` | `output/public_traceroute_by_msmid` | 按 `msm_id` 创建独立结果子目录的根目录 |
| `--as-precompute-file` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | 传给第一阶段的 AS 图预处理文件 |
| `--measurement-id` | 默认全部发现的文件 | 可选过滤项，可重复传入以只运行指定 measurement |
| `--skip-existing` | `False` | 如果某个 measurement 的 `cable_matching_manifest.json` 已存在，则跳过 |
| `--skip-robustness` | `False` | 跳过 robustness comparison，用于更快的 smoke test |
| `--dry-run` | `False` | 只打印将执行的命令，不实际运行 |

## 推荐运行顺序

```powershell
python .\precompute_as_graph.py
python .\main_analysis.py
python .\concerntration_analysis.py
python .\postprocess_candidate_output.py --input .\output\result\cable_matching_output.json --output .\output\result
python .\robustness_compare.py --input .\output\result\trace_candidate_support.csv --output .\output\result
python .\probe\run_ripe_atlas_traceroute.py --config .\probe\atlas_traceroute_config.local.json --dry-run
python .\ripe_atlas_public_download\download_public_traceroutes.py --metadata-only
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --skip-existing
```

## RIPE Atlas 公开 traceroute 数据下载

第一轮公开 traceroute 下载器覆盖 18 个公开 IPv4 traceroute measurements：

- 13 个 DNS Root measurements：A-Root 到 M-Root。
- 2 个主要应用 measurements：Wikipedia 和 Reddit。
- 1 个扩展 measurement：Netflix assets，只解释为 `assets.nflxext.com` 的路径。
- 2 个 topology baselines：`5151` ICMP 作为主要 baseline，`5051` UDP 作为历史协议 baseline。

默认时间窗口是 `2026-07-01T00:00:00Z` 开始的 60 分钟。下载文件名会包含 dataset、服务/root 标签、`msm_id` 和 UTC 时间窗口，例如：

```text
data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100/dns-root_a-root_msm5009_20260701T000000Z_010000Z.json
```

这些文件会保留 RIPE Atlas 返回的 `dst_addr` 等字段；应用服务 measurement 不能假定所有 probes 都访问同一个固定目标 IP。

常用命令：

```powershell
python .\ripe_atlas_public_download\download_public_traceroutes.py --metadata-only
python .\ripe_atlas_public_download\download_public_traceroutes.py --measurement-id 5009
python .\ripe_atlas_public_download\download_public_traceroutes.py --skip-existing
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --measurement-id 5009 --skip-existing
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --skip-existing
```

按 `msm_id` 分别运行后的输出位于：

```text
output/public_traceroute_by_msmid/msm5009_dns-root-a-root/
```

每个文件夹包含该 measurement 单独的第一阶段匹配输出、postprocess 表、robustness 表和 manifest。`cable_matching_output.json`、`trace_candidate_support.csv`、`trace_feasible_candidate_space.csv` 这类大型中间文件默认不提交到 GitHub；体量较小的 summary 表和 manifest 可以提交用于检查。

## RIPE Atlas probe 辅助脚本配置说明

这个辅助脚本的目标是：你只需要修改一个本地 JSON 配置文件，就可以对指定目标发起全局 probe traceroute 测量。

关键配置项如下：

| 字段 | 含义 |
| --- | --- |
| `api_key` | RIPE Atlas API key，真实提交时必需 |
| `bill_to` | 可选的 RIPE Atlas 计费标识 |
| `request_name` | 测量描述和回执文件名使用的前缀 |
| `dry_run` | 是否默认启用仅预览模式 |
| `probe_selection.mode` | 当前选择模式。`all_public_active` 表示先拉取活跃公开探针，再做本地过滤 |
| `probe_selection.status` | 传给 RIPE Atlas probes 接口的状态过滤。`1` 通常表示已连接探针 |
| `probe_selection.is_public` | 是否只选择公开探针 |
| `probe_selection.include_anchors` | 是否把 Atlas anchors 也纳入探针集合 |
| `probe_selection.batch_size` | 每个测量批次中放入多少个 probe ID |
| `probe_selection.page_size` | 从公开 probes 接口拉取分页时使用的 page size |
| `probe_selection.limit` | 配置级别的 probe 数量上限 |
| `probe_selection.country_allowlist` | 拉取后按国家代码过滤的可选白名单 |
| `probe_selection.asn_allowlist` | 拉取后按 ASN 过滤的可选白名单 |
| `measurement_defaults.*` | traceroute 默认参数，如 `af`、`protocol`、`packets`、`paris`、`size`、`timeout`、`resolve_on_probe`、`include_probe_id`、`skip_dns_check`、`spread`、`is_public`、`tags` |
| `targets[]` | 目标列表。每个目标至少需要定义 `target`，也可以单独覆盖 `description`、`af`、`protocol`、`packets`、`port` 等字段 |

这个脚本只负责创建测量并保存提交回执，不会自动下载最终 traceroute 结果集。

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

### A0. probe 辅助脚本输出

#### `probe/results/ripe_atlas_traceroute_request_*.json`

RIPE Atlas probe 辅助脚本生成的本地提交回执。主要字段如下：

| 字段 | 含义 |
| --- | --- |
| `request_name` | 配置中定义的人类可读请求前缀 |
| `config_path` | 本次实际使用的配置文件路径 |
| `submitted_at_utc` | 脚本运行时间的 UTC 时间戳 |
| `dry_run` | 本次是否只预览 payload 而没有真实提交 |
| `probe_selection_summary` | 选中的 probe 总数、batch 大小、batch 数量等摘要 |
| `targets` | 本次运行使用的目标列表 |
| `probe_preview` | 选中 probes 的紧凑预览，包含 probe ID、国家、ASN、anchor 标记和状态 |
| `submissions[]` | 每个目标、每个 probe batch 的一条提交记录 |

`submissions[]` 内部字段：

| 字段 | 含义 |
| --- | --- |
| `target` | 测量目标主机名或 IP |
| `description` | traceroute definition 使用的描述 |
| `batch_index` | 当前 probe 批次编号 |
| `probe_count` | 当前批次中的 probe 数量 |
| `probe_id_min`, `probe_id_max` | 当前批次 probe ID 的最小值和最大值，便于快速检查 |
| `payload_preview` | 准备提交到 RIPE Atlas measurement create API 的 JSON payload |
| `status` | `dry_run_only` 或 `submitted` |
| `api_response` | 真实提交时 RIPE Atlas 返回的原始响应 |
| `measurement_ids` | 返回的 RIPE Atlas measurement ID 列表（如果有） |

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
| `output/result/unit_physical_candidate_set_diversity_corridor.csv` | corridor-level 保守可行集合多样性；它是 candidate-breadth 描述符，不是论文主 observation-concentration 指标 |
| `output/result/unit_network_physical_upper_bound_mismatch.csv` | 使用 conservative feasible-set upper bound 的 long-form mismatch 表，覆盖全部 network definition 和 cable/corridor 两层 |
| `output/result/paper_unit_physical_candidate_diversity.csv` | corridor-level 保守可行集合多样性的 legacy / supplementary 别名 |
| `output/result/paper_unit_network_physical_mismatch.csv` | corridor-level upper-bound mismatch 的 legacy / supplementary 别名 |
| `output/result/conservative_candidate_audit_manifest.json` | 说明 infeasibility-first 语义、weighted view 与 conservative set view 的简明 manifest |
| `output/result/robustness_conservative_candidate_audit.csv` | 对比 weighted support 与 conservative feasible set 的 robustness 表 |

### 解释边界

- Geo / RTT / landing / country 等约束主要用于排除不可能或高度不可信的候选。
- `candidate_support` 是保留后的可行候选集合内部的 evidence support，不是 ground-truth 海缆使用概率。
- conservative set-based diversity 把所有可行候选等权看待，因此应解释为“可能物理多样性上界”。

## PeeringDB 外部互联描述符补充

PeeringDB 在本仓库中只作为**外部网络层互联足迹描述符**使用：

- 不参与 feasible candidate filtering
- 不参与 candidate support scoring
- 不参与 corridor assignment

本地输入目录：

- `data/peeringdb/`

支持的本地 dump 文件：

- `ix.json`
- `fac.json`
- `net.json`
- `netfac.json`
- `netixlan.json`

新增脚本：

- `python .\build_peeringdb_descriptors.py`

主输出：

- `output/result/country_peeringdb_descriptors.csv`

主要字段：

| 字段 | 含义 |
| --- | --- |
| `country` | 用于与 `src_country` 连接的国家键 |
| `pdb_num_ixps` | 该国的 PeeringDB IXP 数量 |
| `pdb_num_facilities` | 该国的 PeeringDB facility 数量 |
| `pdb_num_networks` | 在该国有 facility presence 或 IXP participation 的唯一网络数 |
| `pdb_num_network_facility_presence` | 该国 `netfac` 记录数 |
| `pdb_num_ixp_participants` | 该国唯一 network-to-IXP participation 数 |
| `pdb_ixp_participant_entropy` | 该国各 IXP 参与者数量分布的熵 |
| `pdb_facility_participant_entropy` | 该国各 facility presence 数量分布的熵 |
| `pdb_interconnection_footprint_score` | 透明、对数缩放的外部互联足迹描述符 |
| `pdb_interconnection_footprint_percentile` | 在可用国家中的百分位 |
| `pdb_interconnection_footprint_tier` | 按三分位划分的 `low` / `medium` / `high` |

新增分层输出：

- `output/result/peeringdb_footprint_mismatch_summary.csv`

PeeringDB 描述符会并入：

- `output/result/unit_network_physical_upper_bound_mismatch.csv`
- `output/result/paper_unit_network_physical_mismatch.csv`
- `output/result/robustness_conservative_candidate_audit.csv`（当描述符上下文可用时）

## Latest network diversity update

当前论文主定义的 network definition 是 `as_egress_primary`。

- `as_egress_primary`：基于跨境 traceroute 链路中的 source-country AS egress transition
- `as_pair_primary`：当显式 egress 观测不足时的 AS-pair / endpoint-AS 主备定义
- `dst_asn_primary`：目的端 ASN 多样性
- `geographic_transition_supplementary`：补充性的 country transition 描述
- `application_observation_supplementary`：probe / measurement / target 丰富度描述
- `combined_supplementary`：保留的历史 composite 补充定义

`country_only` 继续保留用于兼容旧输出，但现在是 supplementary descriptor，不再是正文主定义。

新增输出：

- `output/result/network_diversity_metric_catalog.csv`
- `output/result/paper_unit_network_physical_mismatch.csv` 是 legacy / supplementary 别名，默认对应 `as_egress_primary` + `corridor` + conservative upper-bound 视图；它不是论文主 corridor observation concentration 表。

PeeringDB 继续保持 external-only：

- 不参与 feasible candidate filtering
- 不参与 candidate support scoring
- 不参与 corridor assignment
- 不参与 `network_diversity_as_egress_primary` 计算
- 只用于 mismatch / robustness 分层解释

## 最新 cross-layer audit 更新

现在将**非 rank 的跨层压缩/覆盖指标**作为一等输出，而不是单独的 fallback 视图。

- 主要非 rank 指标：
  - `network_effective_diversity`
  - `physical_candidate_diversity_upper_bound`
  - `network_to_physical_compression_ratio`
  - `log_network_physical_compression_gap`
  - `physical_coverage_ratio`
  - `absolute_compression_tier`
- 相对比较型指标继续保留在同一批表中：
  - `network_percentile`
  - `physical_upper_bound_percentile`
  - `rank_gap_upper_bound`
  - `strict_upper_bound_mismatch_75_25`
  - `upper_bound_mismatch_category`

新增输出文件：

- `output/result/unit_cross_layer_audit.csv`：unit 级 cross-layer 审计表，包含 application / network / physical / 非 rank 压缩指标 / 可选相对指标 / PeeringDB 描述符。
- `output/result/country_cross_layer_audit.csv`：country 级 cross-layer 审计表，直接从 link 观测与 feasible candidate 行重算，不是对 unit 结果做平均。
- `output/result/service_country_cross_layer_audit.csv`：`src_country + service_id` 级 cross-layer 审计表；`service_id` 优先使用显式字段，否则回退到 `file_name`，再回退到 `msm_id`。
- `output/result/paper_country_cross_layer_audit.csv`：country 审计表的 legacy / supplementary corridor-level 别名。
- `output/result/paper_service_country_cross_layer_audit.csv`：service-country 审计表的 legacy / supplementary corridor-level 别名。
- `output/result/cross_layer_metric_summary.csv`：对新 cross-layer audit 表中非 rank 压缩层级与相对 mismatch 比例做汇总。

解释更新：

- 同一套非 rank compression / coverage 指标同时适用于多国全局数据集和单国数据集。
- rank-based mismatch 继续保留，但它只是所选语料范围内的相对比较视图，不再是唯一的跨层解释方式。

## 最新 corridor observation concentration 更新

现在论文主物理集中度视图改为基于**corridor observation distribution** 的 path-transition segment 审计。

- 一条 traceroute 会被拆成多个可独立映射的 hop-pair / country-transition segment。
- 每个 segment 按 near-side country 归属。
- 同一个 atomic segment 内，如果多条 cable candidate 属于同一个 corridor，会先做 corridor 去重。
- 在论文主视图里，每个 atomic segment 贡献 1 单位 observation mass；若存在多个 feasible corridor，则在这些 corridor 之间做均匀分配。
- 这里的 observation mass 表示 measurement-observed path-transition segments，不表示真实流量字节数或报文数。
- unique feasible corridor count 继续保留，但它只表示 candidate breadth，不再是论文主集中度指标。

新增或提升为主输出的文件：

- `output/result/atomic_segment_id_diagnostics.json`：记录 atomic segment ID 的稳定字段构造方式。
- `output/result/country_corridor_observation_distribution.csv`：country 级 corridor observation mass 分布表。关键字段包括 `observation_mass`、`share_of_country_observation_mass`、`rank_within_country`。
- `output/result/service_country_corridor_observation_distribution.csv`：service-country 级 corridor observation mass 分布表。关键字段包括 `observation_mass`、`share_of_unit_observation_mass`、`rank_within_unit`。
- `output/result/country_corridor_concentration_summary.csv`：country 级 corridor 集中度汇总，核心字段包括 `top1_corridor_share`、`top3_corridor_share`、`effective_corridor_count`、`corridor_concentration_tier`、`auditable_corridor_concentration`。
- `output/result/service_country_corridor_concentration_summary.csv`：service-country 级 corridor 集中度汇总，也是论文主用的 corridor observation concentration 单元表。
- `output/result/country_network_transition_concentration_summary.csv`：在同一批可映射 segment 上计算的 network transition 集中度，优先使用 AS transition，缺失 ASN 时回退到 country transition。
- `output/result/service_country_network_transition_concentration_summary.csv`：service-country 级 network transition 集中度汇总。
- `output/result/country_cross_layer_distribution_audit.csv`：country 级 cross-layer distribution-shape 审计表，联合 network transition concentration 与 corridor observation concentration。
- `output/result/service_country_cross_layer_distribution_audit.csv`：service-country 级 cross-layer distribution-shape 审计表，`cross_layer_distribution_class` 是主解释字段。
- `output/result/paper_corridor_observation_concentration_cases.csv`：auditable 的 severe / moderate corridor observation concentration 案例。
- `output/result/paper_network_broad_physical_concentrated_cases.csv`：论文主案例，表示 network 观测仍较宽而 corridor 观测已经集中。
- `output/result/paper_broad_corridor_distribution_cases.csv`：broad corridor 分布的反例表，用来说明框架不会强行得出集中结论。

解释更新：

- candidate breadth 回答的是“一个 unit 里出现了多少个 unique feasible corridors”。
- observation concentration 回答的是“这些 measurement-observed path-transition segments 在 feasible corridors 上如何分布”。
- cross-layer distribution audit 比较的是同一批 segment 上的分布形态，而不是把 AS-transition 数量和 corridor 数量当作同一种计量单位直接比较。

## 5051 全量运行结果说明

仓库同样支持 RIPE Atlas `msm_id = 5051` 的全量运行。

- 建议将全量运行输出写到 `output/result_5051/`
- 体量适中的 summary / audit 结果可以直接提交到仓库供检查
- 超大的 link-level 结果文件可能因为 GitHub 体积限制而只保留在本地

典型的超大本地文件包括：

- `output/result_5051/cable_matching_output.json`
- `output/result_5051/trace_feasible_candidate_space.csv`
- `output/result_5051/trace_candidate_support.csv`

## best-case physical-candidate audit 更新

当前论文主解释已经升级为 best-case physical-candidate audit。

- `physical_candidate_diversity_upper_bound` 表示在 hard feasibility constraints 下，best-case feasible physical-candidate space 的上界宽度。
- physical-candidate concentration 表示 best-case feasible candidate space 本身就很窄。
- network-to-physical compression 表示 `network_effective_diversity` 超过了 best-case physical-candidate upper bound。
- 没有 network-to-physical compression 并不等于没有 physical-candidate exposure。
- PeeringDB 继续只作为外部 interconnection-footprint descriptor，不参与 physical-candidate construction，也不参与 candidate-support scoring。
- rank / percentile 指标继续保留，但只是辅助性的相对比较视图。

新增输出：

- `output/result/physical_candidate_concentration_summary.csv`
- `output/result/joint_cross_layer_risk_summary.csv`
- `output/result/paper_physical_concentration_cases.csv`
- `output/result/paper_joint_mismatch_cases.csv`
- `output/result/paper_broad_physical_space_cases.csv`

## 最新论文一致性补丁

Stage 1 现在补充记录与论文方法定义对齐的元数据，但不改变候选匹配主流程。

- `--cable-availability-mode` 用于控制海缆生命周期过滤。论文主视图默认值为 `confirmed_active_only`，会排除在 traceroute 时间点已知为未来规划、已退役或生命周期未知的候选。`confirmed_active_plus_unknown` 只作为 robustness / coverage 视图使用，用来保留并标记生命周期未知的候选。
- 非正数或明显噪声 RTT delta 会标记为 `rtt_feasibility_status = inconclusive`：这些候选会保留在 feasible set 中，并带有 `rtt_inconclusive` ambiguity tag，不作为硬不可行证据。只有有效 RTT 观测在考虑 tolerance 后仍违反下界约束时，才会被 hard-filter。
- 可以通过 `--landing-region-override-file` 提供 landing-region 手工覆盖文件。该 JSON 将 `landing_station_id` 映射到 `landing_region_id` / `landing_region_name`；手工覆盖优先于自动 geographic connected component，并会记录在 manifest 中。
- traceroute link 生成阶段会在 hop 序列中观察到实际目标 ASN 时记录 service-entry 边界。后处理中的 trace summary 会输出该边界是否被解析，但物理投影仍然保持 hop-pair 粒度。
- candidate 行新增海缆生命周期字段，例如 `cable_status`、`cable_rfs_date`、`cable_retired_date`、`cable_availability_status` 和 `availability_filter_passed`。
- `output/result/supplementary_owner_concentration.csv` 汇总 feasible corridor observation mass 上的拆分 owner exposure。它只是补充描述表：owner 不作为 ground truth，也不能解释为真实流量体积或真实海缆使用量。

## 最新 IPinfo ASN 数据库更新

当前所有 IP 到 ASN 的映射统一使用 `data/ipinfo/ipinfo_asn.mmdb`。

- `source/main_analysis.py` 中的 hop ASN、link endpoint ASN、target ASN、service-entry ASN 都通过 IPinfo ASN MMDB 查询。
- `source/concerntration_analysis.py` 中用于 cross-border AS pair 的 ASN 也通过 IPinfo ASN MMDB 查询。
- `data/ipinfo/ipinfo_location.mmdb` 继续用于国家、城市、经纬度 geolocation，不再作为主要 ASN 来源。
- `data/pfx2as/202512.pfx2as` 和 `--pfx2as-file` 仅保留为旧实验兼容说明；当前主流程不再使用它进行 IP 到 ASN 映射。
- 如需指定其他 IPinfo ASN 数据库，可以使用 `--asn-mmdb-path`。
