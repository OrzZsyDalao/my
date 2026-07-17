# infocom26

This repository implements an uncertainty-aware cross-layer diversity auditing pipeline for RIPE Atlas traceroute measurements, AS-level economic signals, and submarine-cable candidate infrastructure.

The main research question is:

> Does network-layer diversity remain diverse after it is projected into the physical-candidate infrastructure space?

The goal is **not** per-path ground-truth submarine cable attribution. The pipeline produces candidate-support distributions, diversity metrics, mismatch diagnostics, ambiguity profiles, and robustness comparisons.

## Run-Isolated Reproducibility

Paper runs are isolated under `runs/<run_id>/`; historical `output/` folders are not paper result bundles. Each run records input checksums, configuration, Git commit, per-measurement status, logs, and trace denominators. Packaging reads only `status=completed` entries in the current run index, preventing historical measurements from contaminating a new result package.

```powershell
python -m pipeline.run_experiment --measurement-id 5009
python -m pipeline.run_experiment --resume-run-id <failed_run_id>
python -m pipeline.package_paper_results --run-id <run_id>
```

Cross-service matched comparison is an `optional_posthoc_analysis`; it is not run by the full pipeline and is not required for measurement completion or paper packaging:

```powershell
python -m pipeline.matched_comparison --run-id <run_id> --comparison-services Wikipedia,Reddit
```

Defaults are versioned in `config/default_experiment.json`. `all_feasible_segments` is the infeasibility-first candidate set; `all_segments` is the legacy support-thresholded view. Candidate support is evidence support, not a probability of true cable use. Because the current cable metadata generally provides unordered landing-point sets rather than route or branch topology, the default `allow_unordered_reachability` policy enumerates valid landing-station pairs on the same cable as reachability candidates. These candidates are explicitly labelled `unordered_cable_reachability`; they are not asserted direct physical segments. Use `--cable-topology-policy adjacent_only` only when an explicit ordered path or segment/branch topology is available and a strict direct-segment sensitivity analysis is desired. Timeout gaps and same-city geolocation ambiguity are retained as fields. Observation mass is traceroute-observed path-transition mass, never traffic volume or actual cable utilisation.

Paper-primary corridor concentration uses only `international_inter_region` and `domestic_inter_region` candidates. `intra_landing_region` candidates remain in the feasible-candidate audit and supplementary outputs, but do not enter the main inter-region corridor distribution. Full summaries contain `all_publicly_visible` and `resolved_entry_only` strata; every `paper_*.csv` is restricted to `auditable_paper_case == True`. Candidate-row RTT/lifecycle counters are named `candidate_rows_*`, while `atomic_segments_*` always count unique hop-pair observations.

Paper audit thresholds use the union of probes and probe ASNs over the complete country-service-path-scope group. Per-corridor `unique_probes` remains descriptive; `group_unique_probes` and `group_unique_probe_asns` are the group-level counts used by corridor concentration and audit eligibility.

## Current Paper-Primary Framework

The paper-facing analysis is now an **application/network/corridor distribution audit**:

```text
Application observation
  -> publicly visible client-to-service path
  -> atomic network-transition segments
  -> infeasibility-first physical candidate construction
  -> landing-region corridor projection
  -> corridor observation-mass distribution
  -> network-transition vs corridor-distribution audit
```

The primary analysis unit is `probe_country x service_id`. `probe_country` comes from RIPE Atlas probe metadata, while `transition_near_country` / `transition_far_country` describe where each mapped hop-pair transition occurs. These are intentionally separate fields.

| Layer | Primary Observation |
| --- | --- |
| Application | `service_id`, actual `target_ip` / `target_asn`, `probe_country` |
| Network | atomic AS/country transitions over mappable hop-pair segments |
| Physical | feasible landing-region corridor candidates |
| Aggregate | service physical exposure, corridor concentration, cross-layer distribution class |

Paper-primary outputs are:

- `paper_service_country_physical_exposure.csv`
- `paper_service_country_corridor_concentration.csv`
- `paper_service_country_cross_layer_distribution.csv`
- `paper_network_broad_physical_concentrated_cases.csv`
- `paper_broad_corridor_distribution_cases.csv`
- `paper_physical_exposure_cases.csv`

Observation mass is measurement-observed transition mass. It is **not** traffic volume, packet count, bandwidth, or cable-use probability. Candidate breadth, best-case upper-bound diversity, compression ratios, rank gaps, cable-level weighted support, product-of-experts ranking, and AS-owner reranking are retained as supplementary views.

## Country Geography Candidate-Dependency Proxy

`source/postprocess_candidate_output.py` also stratifies inter-region feasible-corridor candidate exposure by broad country geography. This is a descriptive candidate-dependency proxy, not observed cable use or national resilience.

Input:

- `data/country_geography_types.json`: versioned operational taxonomy. `landlocked_country_codes` and `island_or_archipelagic_country_codes` are explicit ISO alpha-2 lists; other valid two-letter codes use `default_valid_alpha2_type=coastal_mainland_or_mixed`. `unknown_country_codes` prevents missing values from silently becoming coastal countries.
- `--country-geography-catalog <path>`: optional post-processing override. The default points to the tracked catalog above.

Dependency-proxy tiers use the paper-primary inter-region candidate exposure rate:

- `no_observed_inter_region_candidate_exposure`: rate = 0.
- `low_candidate_dependency_proxy`: 0 < rate < 0.05.
- `moderate_candidate_dependency_proxy`: 0.05 <= rate < 0.15.
- `high_candidate_dependency_proxy`: 0.15 <= rate < 0.30.
- `very_high_candidate_dependency_proxy`: rate >= 0.30.

Generated outputs:

| File | Meaning |
| --- | --- |
| `country_geography_candidate_dependency.csv` | Complete probe-country table, recomputed directly from trace rows for `all_publicly_visible` and `resolved_entry_only`. |
| `service_country_geography_candidate_dependency.csv` | Complete country-service table enriched with corridor concentration and cross-layer distribution fields. |
| `geography_type_candidate_dependency_summary.csv` | Geography-type comparison with trace-weighted rates, eligible-country medians/IQRs, and auditable concentration shares. |
| `paper_service_country_geography_candidate_dependency.csv` | Paper-facing country-service rows restricted to `auditable_paper_case == True`. |
| `country_geography_catalog_resolved.csv` | Country codes observed in the dataset, their resolved geography type, and classification provenance. |
| `country_geography_dependency_manifest.json` | Catalog checksum, formulas, thresholds, path scopes, output list, and interpretation boundary. |

Key fields:

| Field | Meaning |
| --- | --- |
| `country_geography_type` | `landlocked`, `island_or_archipelagic`, `coastal_mainland_or_mixed`, or `unknown`. |
| `traces_with_inter_region_candidates` | Unique traces containing at least one feasible domestic or international inter-region corridor candidate. |
| `candidate_dependency_proxy_rate` | `traces_with_inter_region_candidates / total_valid_traces`; identical to the paper-primary inter-region exposure rate. |
| `inter_region_candidate_rate_among_mappable_traces` | Conditional rate using only mappable traces as denominator; reported separately to expose mapping-coverage effects. |
| `candidate_dependency_proxy_tier` | Transparent descriptive tier defined above. |
| `trace_weighted_candidate_dependency_proxy_rate` | Geography-type aggregate recomputed from summed trace numerators and denominators, not an average of country percentages. |
| `median_country_candidate_dependency_proxy_rate`, `*_p25`, `*_p75` | Distribution across geography-summary-eligible countries. |
| `auditable_corridor_concentrated_unit_share` | Share of auditable service-country units with severe or moderate corridor observation concentration. |
| `auditable_network_broad_physical_concentrated_unit_share` | Share of auditable units in the paper-primary cross-layer class. |

`intra_landing_region` remains a supplementary rate and is excluded from `candidate_dependency_proxy_rate`. Geography type is an explanatory stratum only; it never changes candidate filtering, support scoring, corridor assignment, or paper audit eligibility.

## Interpretation Boundary

- `candidate_support`, `fused_candidate_support`, and `normalized_candidate_support` are evidence scores, not ground-truth cable utilization.
- A top-ranked candidate is the strongest explanation under the current evidence model, not proof that the path truly used that cable.
- Cable-level and corridor-level outputs are both kept because parallel infrastructure can change the interpretation granularity.

## Repository Layout

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

Root-level scripts such as `main_analysis.py` are thin wrappers that call the corresponding `source/` modules.

## Pipeline Overview

Recommended paper-facing run order:

1. Download or prepare RIPE Atlas traceroute inputs.
2. Prepare probe metadata, IPinfo geolocation, IPinfo ASN MMDB, AS relationship, owner-to-AS, and cable metadata.
3. Run Stage 1 feasible corridor construction with landing-region grouping:
   `python source/main_analysis.py --landing-region-radius-km 50 --rtt-tolerance-ms 5`
4. Run Stage 2 application/network/corridor distribution audit:
   `python source/postprocess_candidate_output.py --input output/result/cable_matching_output.json --output output/result`
5. Run robustness analyses:
   `python source/robustness_compare.py --input output/result/trace_candidate_support.csv --output output/result`
6. Optionally run legacy cable/owner analysis.

Script roles:

1. `precompute_as_graph.py`  
   Optional offline preprocessing for the AS-economic core. Builds bounded owner-group reachability over the CAIDA AS relationship graph.

2. `main_analysis.py`  
   Stage 1 candidate-support generation. Reads traceroutes and infrastructure metadata, scores cable candidates, and writes link-level matching output.

3. `concerntration_analysis.py`  
   Stage 2 dependency aggregation. Reads Stage 1 output and produces country/root dependency and concentration tables.

4. `postprocess_candidate_output.py`  
   Reads Stage 1 output and produces unit-level diversity, mismatch, ambiguity, and interpretation files.

5. `robustness_compare.py`  
   Reads the flattened candidate-support table and compares mismatch stability under different evidence views.

6. `build_peeringdb_descriptors.py`
   Reads local PeeringDB dump files from `data/peeringdb/` and builds country-level external interconnection footprint descriptors. These descriptors are only used for stratification and interpretation, not for feasible candidate filtering or candidate support scoring.

7. `probe/run_ripe_atlas_traceroute.py`
   Auxiliary experiment helper. Reads a local RIPE Atlas config JSON, selects active public probes, chunks them into batches, and creates one-off traceroute measurements toward configured targets. It does not modify the main analysis pipeline.

8. `ripe_atlas_public_download/download_public_traceroutes.py`
   Public dataset downloader. Downloads the first-round RIPE Atlas public IPv4 traceroute measurement set for the 2026-07-01 00:00:00 UTC to 01:00:00 UTC window. It validates measurement metadata first and writes pipeline-ready result arrays under `data/traceroute_rundnsroot/`.

9. `ripe_atlas_public_download/run_per_measurement_pipeline.py`
   Per-measurement batch runner. Discovers downloaded public traceroute files, creates one result folder per `msm_id`, and runs `main_analysis.py`, `postprocess_candidate_output.py`, and `robustness_compare.py` separately for each measurement.

10. `ripe_atlas_public_download/package_paper_csv_results.py` and `run_july1_pipeline_and_publish.ps1`
   Package only paper-facing country/service-country CSV summaries from the completed 2026-07-01 public Atlas runs into `results/july1_public_atlas_20260701/`. The PowerShell wrapper runs the full batch, applies a 95 MB per-file GitHub guard, then commits and pushes only this compact bundle; raw Atlas JSON, matching JSON, and trace-level tables remain local.
   `publish_july1_results_after_task.ps1` is the non-duplicating variant for an already-running Windows scheduled pipeline task: it waits for successful completion before packaging and pushing the same bundle.
   `resume_incomplete_july1_pipeline.ps1` resumes the eight non-baseline measurements left by the interrupted optimized July 1 batch and publishes the same compact bundle on success.

## Input File Reference

### Shared Input Files

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `data/cable/landing-point-geo.json` | Stage 1 | GeoJSON features keyed by landing-station `id`, with coordinates | Landing-station coordinate lookup for spatial candidate generation |
| `data/cable/*.json` | Stage 1, Stage 2, AS precompute | One JSON per cable, including `id`, `name`, `landing_points`, `owners` | Cable metadata, landing pairs, and owner metadata |
| `data/ipinfo/ipinfo_location.mmdb` | Stage 1, Stage 2 | MMDB geolocation database | IP-to-country/city geolocation |
| `data/ipinfo/ipinfo_asn.mmdb` | Stage 1, Stage 2 | IPinfo ASN MMDB database | Active IP-to-ASN lookup source for hop, endpoint, target, service-entry, and network-transition ASN fields |
| `data/asrelationship/20250901.as-rel2.txt` | Stage 1, AS precompute | CAIDA-style AS relationships (`AS1|AS2|rel`) | AS-economic relationship model |
| `data/pfx2as/202512.pfx2as` | Legacy compatibility only | Prefix-to-origin-AS mapping | Retained for old experiments; current IP-to-ASN mapping uses `data/ipinfo/ipinfo_asn.mmdb` |
| `data/owner2asn/owner_to_asn.csv` | Stage 1, AS precompute | CSV with `owner,asn` | Maps cable owners to ASNs |

### Traceroute and Probe Inputs

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `data/traceroute_rundnsroot/root_dns_traces.json` | Stage 1 default, Stage 2 default | RIPE Atlas traceroute results in JSON array format | Small routine test input |
| `data/traceroute_rundnsroot/**/*.json` | Stage 1 | RIPE Atlas traceroute result files | Main traceroute source directory |
| `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100/*.json` | Stage 1 | Downloaded public RIPE Atlas traceroute result arrays with filenames containing dataset, service/root name, `msm_id`, and UTC window | First-round DNS Root, application, extension, and topology-baseline dataset |
| `data/traceroute/ripe_atlas_5051_20251201.json` | Optional | Larger full-scale traceroute input | Full dataset run |
| `data/probe/*.json` | Stage 2 | Probe metadata, typically with `objects[].id` and `objects[].country_code` | Maps probe IDs to source countries |

### Precomputed Optional Input

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `output/preprocessed/as_graph_owner_reachability.pkl.gz` | Stage 1 | Gzipped Python pickle with owner-group reachability payload | Speeds up the AS-economic support computation |

### Probe Helper Local Files

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `probe/atlas_traceroute_config.example.json` | Probe helper | JSON config template with `api_key`, `targets`, `probe_selection`, and `measurement_defaults` | Template for RIPE Atlas measurement creation |
| `probe/atlas_traceroute_config.local.json` | Probe helper, optional | Same schema as the example config | Recommended local config file for real API keys and experiment-specific targets |
| `probe/results/*.json` | Probe helper output | Submission receipts and returned measurement IDs | Local bookkeeping for later data collection |

## Command-Line Parameters

### `python precompute_as_graph.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--asrel-file` | `data/asrelationship/20250901.as-rel2.txt` | CAIDA AS relationship input |
| `--owner2asn-file` | `data/owner2asn/owner_to_asn.csv` | Owner-to-ASN mapping |
| `--cable-dir` | `data/cable/` | Cable metadata directory |
| `--output` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | Output precompute payload |
| `--max-hops-unknown` | `2` | Online hop threshold above which AS paths are treated as unknown |
| `--search-max-hops` | `2` | Offline bounded search depth |
| `--peer-cost` | `1.0` | Cost assigned to peer edges |
| `--provider-customer-cost` | `2.0` | Cost assigned to provider-customer edges |
| `--limit-owner-groups` | `None` | Optional smoke-test limit |

### `python main_analysis.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--as-precompute-file` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | Optional precomputed owner-group reachability input |
| `--asn-mmdb-path` | `data/ipinfo/ipinfo_asn.mmdb` | IPinfo ASN MMDB used for every IP-to-ASN lookup |

### `python concerntration_analysis.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--raw-traces-file` | `data/traceroute_rundnsroot/root_dns_traces.json` | Raw traceroute input file or directory |
| `--match-output-file` | `output/result/cable_matching_output.json` | Stage 1 matching JSON |
| `--probe-meta-file` | `data/probe/20251201.json` | Probe metadata file |
| `--probe-file-name` | `None` | Probe filename under `data/probe/` |
| `--probe-use-latest` | `False` | Automatically select latest probe JSON |
| `--mmdb-path` | `data/ipinfo/ipinfo_location.mmdb` | MMDB path |
| `--asn-mmdb-path` | `data/ipinfo/ipinfo_asn.mmdb` | IPinfo ASN MMDB path for IP-to-ASN lookup |
| `--pfx2as-file` | `data/pfx2as/202512.pfx2as` | Legacy ignored option; current IP-to-ASN lookup uses `--asn-mmdb-path` |
| `--output-csv` | `output/result/country_root_cable_dependency_hybrid.csv` | Main Stage 2 output path |
| `--summary-json` | `None` | Optional Stage 2 summary JSON path |
| `--cable-dir` | `data/cable/` | Cable metadata directory |
| `--aggregation-mode` | `weighted` | Candidate-to-trace aggregation mode: `hard_top1`, `weighted`, or `thresholded_normalized` |
| `--match-threshold` | `0.5` | Minimum candidate support threshold for thresholded aggregation |
| `--confidence-bucket` | `None` | Optional filter: `high`, `medium`, or `ambiguous` |
| `--owner-multi-entity-mode` | `full` | Whether owners inherit full support or split it |
| `--cross-country` / `--no-cross-country` | `--cross-country` | Whether to keep only cross-country traces |
| `--topn-preview` | `10` | Number of preview rows printed to console |
| `--output-total-table` | `False` | Emit merged variant table instead of one single-mode table |
| `--detail-dir` | `None` | Optional detail directory for per-mode tables |
| `--collapse-roots` | `False` | Collapse all roots into `ALL` |

### `python postprocess_candidate_output.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--input` | `output/result/cable_matching_output.json` | Stage 1 candidate-support JSON |
| `--output` | `output/result/` | Directory for post-processed files |
| `--unit-fields` | `src_country,msm_id,file_name` | Fields from `link_info` used to define aggregation units |

### `python robustness_compare.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--input` | `output/result/trace_candidate_support.csv` | Flattened candidate-support table |
| `--output` | `output/result/` | Directory for robustness outputs |

### `python build_peeringdb_descriptors.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--input-dir` | `data/peeringdb` | Directory containing local PeeringDB dumps such as `ix.json`, `fac.json`, `net.json`, `netfac.json`, and `netixlan.json` |
| `--output` | `output/result/country_peeringdb_descriptors.csv` | Output descriptor CSV |

### `python probe/run_ripe_atlas_traceroute.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--config` | auto-detect | Config path. The helper tries `probe/atlas_traceroute_config.local.json`, then `probe/atlas_traceroute_config.json`, then `probe/atlas_traceroute_config.example.json` |
| `--output` | `probe/results/` | Directory where submission receipts are written |
| `--dry-run` | `False` | Preview selected probes and measurement payloads without real submission |
| `--limit-probes` | `None` | Optional CLI override limiting the number of selected probes |
| `--list-only` | `False` | Fetch and preview the selected probes without building or submitting measurements |

### `python ripe_atlas_public_download/download_public_traceroutes.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--output-dir` | `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100` | Directory for pipeline-ready RIPE Atlas result JSON arrays |
| `--manifest` | auto path under `ripe_atlas_public_download/manifests/` | Manifest path recording metadata validation, output files, byte counts, and record counts |
| `--start` | `2026-07-01T00:00:00Z` | UTC download-window start time |
| `--duration-minutes` | `60` | Download-window length |
| `--measurement-id` | all 18 first-round IDs | Optional filter. Repeat this argument to download or test selected measurements only |
| `--metadata-only` | `False` | Validate RIPE Atlas measurement metadata without downloading result data |
| `--skip-existing` | `False` | Reuse existing output files instead of downloading them again |
| `--no-count-records` | `False` | Skip streaming record counting after each download |
| `--timeout` | `120` | HTTP timeout in seconds |
| `--retries` | `3` | HTTP retry count |

### `python ripe_atlas_public_download/run_per_measurement_pipeline.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--input-dir` | `data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100` | Directory containing downloaded public Atlas traceroute JSON arrays |
| `--output-root` | `output/public_traceroute_by_msmid` | Root directory where one subfolder per `msm_id` is created |
| `--as-precompute-file` | `output/preprocessed/as_graph_owner_reachability.pkl.gz` | AS-graph precompute file passed to Stage 1 |
| `--measurement-id` | all discovered files | Optional filter. Repeat to run selected measurements only |
| `--exclude-measurement-id` | none | Optional exclusion. Repeat to omit selected measurements, e.g. `--exclude-measurement-id 5051 --exclude-measurement-id 5151` |
| `--skip-existing` | `False` | Skip a measurement if its `cable_matching_manifest.json` already exists |
| `--skip-robustness` | `False` | Skip robustness comparison for faster smoke tests |
| `--publish-paper-results` | `False` | After all selected measurements succeed, package and push only the compact paper-facing CSV bundle |
| `--dry-run` | `False` | Print commands without executing them |

## Recommended Run Order

```powershell
python .\precompute_as_graph.py
python .\main_analysis.py
python .\concerntration_analysis.py
python .\postprocess_candidate_output.py --input .\output\result\cable_matching_output.json --output .\output\result
python .\robustness_compare.py --input .\output\result\trace_candidate_support.csv --output .\output\result
python .\build_peeringdb_descriptors.py
python .\probe\run_ripe_atlas_traceroute.py --config .\probe\atlas_traceroute_config.local.json --dry-run
python .\ripe_atlas_public_download\download_public_traceroutes.py --metadata-only
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --skip-existing
```

## Public RIPE Atlas Dataset Downloader

The first-round public traceroute downloader covers 18 public IPv4 traceroute measurements:

- 13 DNS Root measurements: A-Root through M-Root.
- 2 primary application measurements: Wikipedia and Reddit.
- 1 extension measurement: Netflix assets, interpreted only as `assets.nflxext.com` paths.
- 2 topology baselines: `5151` ICMP as the primary baseline and `5051` UDP as the historical protocol baseline.

The default window is `2026-07-01T00:00:00Z` for 60 minutes. Downloaded files are named with dataset, service/root label, `msm_id`, and the UTC window, for example:

```text
data/traceroute_rundnsroot/ripe_atlas_public_20260701_0000_0100/dns-root_a-root_msm5009_20260701T000000Z_010000Z.json
```

These result files preserve RIPE Atlas fields such as `dst_addr`; the application measurements must not be treated as a single fixed destination IP because probes may resolve or reach different service endpoints.

Useful commands:

```powershell
python .\ripe_atlas_public_download\download_public_traceroutes.py --metadata-only
python .\ripe_atlas_public_download\download_public_traceroutes.py --measurement-id 5009
python .\ripe_atlas_public_download\download_public_traceroutes.py --skip-existing
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --measurement-id 5009 --skip-existing
python .\ripe_atlas_public_download\run_per_measurement_pipeline.py --skip-existing
```

Per-`msm_id` outputs are written under:

```text
output/public_traceroute_by_msmid/msm5009_dns-root-a-root/
```

Each folder contains the Stage 1 matching output, post-processing tables, robustness tables, and manifests for that individual measurement. Large intermediate files such as `cable_matching_output.json`, `trace_candidate_support.csv`, and `trace_feasible_candidate_space.csv` are ignored by Git because they can exceed GitHub-friendly sizes; compact summary tables and manifests can be committed for inspection.

## RIPE Atlas Probe Helper Config

Edit one local JSON config file and the helper can create world-wide traceroute measurements toward your chosen targets.

Key fields:

| Field | Meaning |
| --- | --- |
| `api_key` | RIPE Atlas API key used for real submission |
| `bill_to` | Optional RIPE Atlas billing handle |
| `request_name` | Prefix used in measurement descriptions and receipt filenames |
| `dry_run` | Whether preview-only mode should be enabled by default |
| `probe_selection.mode` | Current helper mode. `all_public_active` means fetch active public probes and then apply local filters |
| `probe_selection.status` | Probe status filter passed to the RIPE Atlas probes endpoint. `1` targets connected probes |
| `probe_selection.is_public` | Whether only public probes should be selected |
| `probe_selection.include_anchors` | Whether Atlas anchors should also be included |
| `probe_selection.batch_size` | Number of probe IDs placed into each measurement batch |
| `probe_selection.page_size` | Page size used when fetching probes from the public probes endpoint |
| `probe_selection.limit` | Optional config-level cap on the selected probe count |
| `probe_selection.country_allowlist` | Optional country-code filter applied after fetching probes |
| `probe_selection.asn_allowlist` | Optional ASN filter applied after fetching probes |
| `measurement_defaults.*` | Default traceroute definition fields such as `af`, `protocol`, `packets`, `paris`, `size`, `timeout`, `resolve_on_probe`, `include_probe_id`, `skip_dns_check`, `spread`, `is_public`, and `tags` |
| `targets[]` | Target list. Each entry must define `target` and may override traceroute fields such as `description`, `af`, `protocol`, `packets`, or `port` |

The helper creates measurements and stores submission receipts. It does not download the resulting traceroute dataset by itself.

## Output File Reference

### A. AS-Graph Precompute Outputs

#### `output/preprocessed/as_graph_owner_reachability.pkl.gz`

Binary precomputed reachability payload used by Stage 1. It contains:

- AS node mappings
- owner-group signatures
- bounded shortest-path metadata from endpoint ASNs to owner groups

This file is an implementation artifact and is not meant for manual inspection.

#### `output/preprocessed/as_graph_owner_reachability.pkl.gz.manifest.json`

Manifest for the precompute payload. Main keys:

| Key | Meaning |
| --- | --- |
| `output_file` | Relative path to the generated payload |
| `owner_group_count` | Number of unique cable-owner ASN groups precomputed |
| `graph_node_count` | Number of AS nodes in the graph |
| `graph_edge_count` | Number of directed AS edges |
| `reachable_entry_count` | Number of stored bounded reachability entries |
| `config` | The precompute configuration used to build the file |

### A0. Probe Helper Outputs

#### `probe/results/ripe_atlas_traceroute_request_*.json`

Local submission receipt written by the RIPE Atlas probe helper. Main fields:

| Field | Meaning |
| --- | --- |
| `request_name` | Human-readable request prefix from the config |
| `config_path` | Config file actually used |
| `submitted_at_utc` | UTC timestamp when the helper ran |
| `dry_run` | Whether the helper only previewed payloads instead of submitting |
| `probe_selection_summary` | Summary of the selected probe population, batch size, and batch count |
| `targets` | Target list copied from the config used in this run |
| `probe_preview` | Compact preview of the selected probes, including probe ID, country, ASN, anchor flag, and status |
| `submissions[]` | One record per target per probe batch |

Fields inside `submissions[]`:

| Field | Meaning |
| --- | --- |
| `target` | Measurement destination hostname or IP |
| `description` | Description used for the traceroute definition |
| `batch_index` | Probe-batch index |
| `probe_count` | Number of probes in the batch |
| `probe_id_min`, `probe_id_max` | Minimum and maximum probe IDs in the batch for quick sanity checks |
| `payload_preview` | JSON payload prepared for the RIPE Atlas measurement creation API |
| `status` | `dry_run_only` or `submitted` |
| `api_response` | Raw RIPE Atlas response when a real submission occurs |
| `measurement_ids` | Returned RIPE Atlas measurement IDs when available |

### B. Stage 1 Outputs

#### `cable_loading_debug.json`

Debug file describing cable and landing-station loading status. Useful for validating data completeness.

#### `output/result/cable_matching_output.json`

Main Stage 1 link-level candidate-support output. It is a JSON array where each element has:

##### `link_info`

| Field | Meaning |
| --- | --- |
| `msm_id` | RIPE Atlas measurement ID |
| `probe_id` | RIPE Atlas probe ID |
| `file_name` | Source traceroute file |
| `timestamp` | Trace timestamp |
| `hop_range` | Hop-pair index range represented by the link |
| `src_ip`, `dst_ip` | Link endpoint IPs |
| `src_city`, `dst_city` | Geolocated cities of the hop endpoints |
| `src_country`, `dst_country` | Geolocated countries of the hop endpoints |
| `rtt_delta_ms` | Measured RTT delta between the two consecutive hops |
| `is_potential_oceanic` | Whether the hop-pair is potentially submarine/oceanic |

##### `match_summary`

| Field | Meaning |
| --- | --- |
| `filtered_reason` | Reason for no-candidate or filtered outcome |
| `num_candidates_total` | Number of unique candidates generated before thresholding |
| `num_candidates_above_threshold` | Number of candidates kept after thresholding |
| `support_sum` | Sum of candidate support values within the link |
| `top1_candidate_support`, `top2_candidate_support` | Raw support of the top two candidates |
| `top1_top2_gap` | Gap between top-1 and top-2 support |
| `confidence_bucket` | Link confidence bucket, such as `high`, `medium`, or `ambiguous` |
| `core_agreement_summary` | Summary of agreement/disagreement among evidence cores |
| `ambiguity_summary` | Summary of ambiguity tags for this link |
| `link_physical_projection_class` | Link-level projection class, such as single-cable, parallel-corridor, or multi-corridor projection |
| `top1_score`, `top2_score` | Compatibility aliases used by downstream aggregation code |

##### `all_segments[]` candidate fields

Spatial and candidate identity:

| Field | Meaning |
| --- | --- |
| `cable_name`, `cable_id` | Candidate cable identity |
| `segment` | Directed landing-station pair string |
| `landing_pair` | Same landing-pair description retained for compatibility |
| `corridor_id` | Canonical corridor identifier |
| `corridor_type` | Corridor type, currently `exact_landing_pair` |
| `parallel_group_id` | Parallel-candidate grouping identifier |
| `parallel_group_size` | Number of cables in the same corridor group |
| `is_parallel_ambiguous` | Whether this candidate belongs to a parallel corridor group |
| `physical_candidate_group_id` | SRLG-like physical candidate group identifier, currently aligned with the corridor-level parallel bundle |
| `physical_candidate_group_type` | Physical grouping type, currently `srlg_like_corridor_group` |
| `link_physical_projection_class` | Link-level projection class copied onto candidate rows for flattened analysis |

Support and ranking:

| Field | Meaning |
| --- | --- |
| `candidate_support` | Main candidate evidence score |
| `fused_candidate_support` | Same fused score under current implementation |
| `normalized_candidate_support` | Candidate support normalized within the link |
| `candidate_rank_by_fused_support` | Rank under fused support |
| `geo_only_rank` | Rank under geo-spatial score only |
| `as_only_rank` | Rank under AS-economic score only |
| `dual_core_rank` | Rank after dual-core fusion |
| `candidate_rank` | Legacy alias for fused rank |
| `score_gap_to_top1` | Difference from the top fused-support candidate |

Geo-spatial core:

| Field | Meaning |
| --- | --- |
| `geo_spatial_score` | Fused geo-spatial core score |
| `geo_entry_score`, `geo_exit_score` | Entry/exit side spatial scores |
| `prob_in`, `prob_out` | Butterworth-style entry and exit proximity terms |
| `d_in`, `d_out` | Endpoint-to-landing-station distances in km |
| `ls_entry_to_ls_exit_gcd_km` | Great-circle distance between the landing stations |
| `city_a`, `city_b`, `country_a`, `country_b` | Candidate-side geographic context |
| `geo-a`, `geo-b` | Rounded endpoint coordinates |

AS-economic core:

| Field | Meaning |
| --- | --- |
| `as_economic_score` | Main AS-economic support score |
| `as_economic_cost` | Cost before exponential transformation |
| `as_economic_reason` | Cost-model reason label |
| `as_economic_support` | Alias of AS-economic score |
| `as_economic_src_owner_hops`, `as_economic_dst_owner_hops` | Hop distance from endpoint ASNs to owner groups |
| `as_economic_src_owner_path_cost`, `as_economic_dst_owner_path_cost` | Path-cost details |
| `as_economic_path_found` | Whether precomputed owner reachability was found |
| `as_economic_owner_group_id` | Internal owner-group identifier |
| `src_asn`, `dst_asn` | Origin ASNs of the endpoint IPs |
| `owner_asn_count` | Number of owner ASNs known for the cable |

RTT and feasibility:

| Field | Meaning |
| --- | --- |
| `rtt_feasible` | Whether the candidate passed the feasibility filter |
| `rtt_score` | RTT-based feasibility score |
| `min_rtt_ms` | Estimated minimum RTT under the fiber model |
| `measured_rtt_ms` | Measured hop-pair RTT delta |
| `rtt_margin_ms` | Headroom between measured RTT and estimated minimum |
| `latency_penalty` | Penalty term applied during score fusion |

Interpretation and ambiguity:

| Field | Meaning |
| --- | --- |
| `core_agreement` | Relationship between geo and AS-economic evidence |
| `ambiguity_tags` | List of ambiguity labels |
| `parallel_segment_candidate_count` | Legacy parallel-corridor count |
| `dual_core_agreement` | Boolean convenience flag |
| `deprecated_fields` | Names of compatibility fields retained for downstream readers |

Legacy compatibility aliases:

| Field | Meaning |
| --- | --- |
| `segment_probability` | Deprecated alias of `candidate_support` |
| `geo_score` | Deprecated alias of `geo_spatial_score` |
| `ownership_score` | Deprecated alias of `as_economic_score` |

#### `output/result/cable_matching_stats_5051.json`

Global Stage 1 run statistics.

| Key | Meaning |
| --- | --- |
| `total_links_seen` | Total hop-pair links inspected |
| `same_city_filtered` | Links filtered because both endpoints stayed in the same city |
| `links_with_ls_candidates` | Links with at least one landing-station candidate |
| `links_with_geo_candidates` | Links with valid geo-spatial candidate generation |
| `candidate_segments_considered` | Candidate cable segments evaluated before RTT filtering |
| `rtt_infeasible_filtered` | Candidates removed by RTT feasibility |
| `links_below_threshold` | Links where candidates remained below the support threshold |
| `candidates_above_threshold` | Count of retained candidates above threshold |
| `links_with_any_match` | Links with at least one retained candidate |
| `links_with_filtered_candidates` | Links with post-threshold candidate sets |
| `links_with_no_feasible_rtt_candidate` | Links where RTT filtering removed all candidates |
| `total_candidates_generated` | Number of raw generated candidates |
| `total_candidates_after_threshold` | Number of retained candidates after thresholding |
| `links_with_dual_core_agreement` | Links containing dual-core-agreement candidates |
| `links_with_geo_dominant_as_weak` | Links showing geo-dominant disagreement |
| `links_with_as_dominant_geo_ambiguous` | Links showing AS-dominant disagreement |
| `links_with_parallel_ambiguity` | Links with parallel-corridor ambiguity |
| `links_with_many_candidates` | Links with large candidate sets |
| `links_with_domestic_candidates` | Links with domestic submarine candidates |
| `as_precompute_enabled` | Whether AS-graph precompute was loaded |
| `candidate_count_list` | Per-matched-link retained candidate counts |
| `mean_candidate_count_per_matched_link`, `median_candidate_count_per_matched_link` | Aggregate candidate multiplicity metrics |

#### `output/result/cable_matching_manifest.json`

Stage 1 run manifest.

| Key | Meaning |
| --- | --- |
| `traceroute_file_paths` | Input traceroute files processed |
| `total_files_processed` | Number of traceroute input files |
| `total_traces_processed` | Number of traceroute records processed |
| `empty_trace_count` | Invalid or empty traceroute record count |
| `matched_links_above_threshold` | Number of matched links written to output |
| `match_output_file` | Output JSON path |
| `match_stats_file` | Stats JSON path |
| `as_precompute_file` | AS precompute file used, if any |
| `method_profile` | Named method profile string |

### C. Stage 2 Outputs

#### `output/result/country_root_cable_dependency_hybrid.csv`
#### `output/result/country_root_cable_dependency_hybrid_same_source.csv`

Country/root dependency tables. The `_same_source` variant is another run variant with the same schema.

| Column | Meaning |
| --- | --- |
| `Country`, `Root` | Aggregation key |
| `Aggregation_Mode`, `Confidence_Filter`, `Owner_Multi_Entity_Mode` | Stage 2 configuration used for the row |
| `Total_Traces` | Denominator trace count for the unit |
| `Submarine_Traces` | Number of traces with submarine-candidate support |
| `Dependency_Rate` | `Submarine_Traces / Total_Traces` |
| `Top_Cable`, `Top2_Cable` | Highest and second-highest aggregated cable candidates |
| `Top_Cable_Expected_Vol`, `Top2_Cable_Expected_Vol` | Aggregated support mass assigned to the top cable candidates |
| `Top_Cable_Share`, `Top2_Cable_Share` | Top cable support divided by `Total_Traces` |
| `Dominance_Margin` | Gap between top cable and second cable share |
| `Unique_CrossBorder_AS_Pairs` | Count of distinct logical cross-border AS pairs |
| `Top_CrossBorder_AS_Pair`, `Top2_CrossBorder_AS_Pair` | Most frequent cross-border AS pairs |
| `Top_CrossBorder_AS_Pair_Count`, `Top2_CrossBorder_AS_Pair_Count` | Raw counts of those AS pairs |
| `Top_CrossBorder_AS_Pair_Share`, `Top2_CrossBorder_AS_Pair_Share` | AS-pair count divided by `Total_Traces` |
| `CrossBorder_AS_Pair_Dominance_Margin` | Gap between top AS pair and second AS pair |
| `Cable_vs_ASPair_Concentration_Gap` | Top cable share minus top AS-pair share |
| `Top_Owner`, `Top2_Owner` | Highest and second-highest cable owners after owner aggregation |
| `Top_Owner_Expected_Vol`, `Top2_Owner_Expected_Vol` | Aggregated support mass assigned to owners |
| `Top_Owner_Share`, `Top2_Owner_Share` | Owner support divided by `Total_Traces` |
| `Owner_Dominance_Margin` | Gap between top owner and second owner share |
| `Cable_Owner_Concentration_Gap` | Top owner share minus top cable share |
| `High_Bucket_Traces`, `Medium_Bucket_Traces`, `Ambiguous_Bucket_Traces` | Number of traces in each confidence bucket |

#### `output/result/country_root_dependency_total.csv`

Merged comparison table across three Stage 2 settings:

- `weighted_all`
- `hard_top1_all`
- `weighted_high`

The schema repeats most dependency columns above with a suffix showing which setting produced the metric. Additional stability fields:

| Column | Meaning |
| --- | --- |
| `Cable_Stable_vs_Hard`, `Cable_Stable_vs_High`, `Cable_Stable_All3` | Whether the top cable remained stable across settings |
| `Owner_Stable_vs_Hard`, `Owner_Stable_vs_High`, `Owner_Stable_All3` | Whether the top owner remained stable across settings |

#### `output/result/dependency_variants/*.csv` (optional)

If Stage 2 is run with `--output-total-table --detail-dir ...`, this directory contains per-setting detail tables such as `weighted_all.csv`, `hard_top1_all.csv`, and `weighted_high.csv`.

These files use the same schema as `country_root_cable_dependency_hybrid.csv`, but each file corresponds to one aggregation / confidence-filter setting only.

#### `output/result/country_root_summary.json`
#### `output/result/country_root_summary_same_source.json`

Small run summaries for Stage 2. Main keys:

| Key | Meaning |
| --- | --- |
| `raw_traces_file`, `resolved_raw_trace_files` | Stage 2 traceroute input path(s) |
| `match_output_file` | Stage 1 output used |
| `probe_meta_file` | Probe metadata file used |
| `mmdb_path`, `asn_mmdb_path`, `ip_to_asn_source`, `cable_dir` | Reference input files and active IP-to-ASN source |
| `pfx2as_file`, `pfx2as_file_semantics` | Legacy compatibility metadata; not used for current IP-to-ASN lookup |
| `output_csv` | Main Stage 2 output path |
| `aggregation_mode`, `collapse_roots`, `match_threshold`, `confidence_bucket`, `cross_country`, `owner_multi_entity_mode` | Stage 2 configuration |
| `rows`, `countries`, `roots` | Output size summary |

### D. Post-Processing Outputs

#### `output/result/trace_candidate_support.csv`

Flattened candidate-level table derived from `cable_matching_output.json`. It contains all `link_info`, `match_summary`, and candidate fields described above, plus:

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit built from `--unit-fields` |
| `link_id` | Unique link-level row identifier |
| `record_index` | Index of the parent Stage 1 record |
| `corridor_id_fallback`, `parallel_group_id_fallback` | Graceful fallback identifiers used when explicit corridor fields are missing |
| `physical_candidate_group_id`, `physical_candidate_group_type`, `physical_candidate_group_id_fallback` | SRLG-like physical grouping columns retained for corridor / bundle analysis |
| `link_physical_projection_class` | Link-level projection class used by downstream mismatch and robustness analysis |
| `projection_class` | Projection-quality label: `strong`, `moderate`, `weak`, or `ambiguous` |

#### `output/result/unit_physical_candidate_diversity_cable.csv`
#### `output/result/unit_physical_candidate_diversity_corridor.csv`
#### `output/result/unit_physical_candidate_diversity.csv`

Physical-candidate diversity tables. The legacy file `unit_physical_candidate_diversity.csv` is an alias of the cable-level version.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `physical_level` | `cable` or `corridor` |
| `dominant_candidate_key` | Dominant cable ID or corridor ID |
| `dominant_candidate_support_share` | Dominant candidate share after unit-level aggregation |
| `expected_candidate_support_total` | Total aggregated support mass before share normalization |
| `candidate_entropy` | Shannon entropy over aggregated candidate shares |
| `effective_num_candidates` | `exp(entropy)` |
| `gini_candidate_support` | Gini coefficient over candidate shares |
| `num_candidates_with_support` | Number of candidates with non-zero support |
| `feasible_candidate_count` | Number of distinct feasible candidates retained for the unit |
| `candidate_entropy_uniform` | Uniform entropy over the feasible candidate set, ignoring support weights |
| `effective_candidate_count_uniform` | Uniform effective candidate count, equal to the feasible-set size |
| `num_matched_links` | Number of matched links in the unit |
| `num_probes` | Number of probes represented in the unit |
| `physical_candidate_diversity_score` | Primary physical diversity score, currently `effective_num_candidates` |
| `candidate_identifier_column` | Column actually used for aggregation, such as `cable_id`, `corridor_id`, or `segment` |

#### `output/result/unit_physical_candidate_upper_bound.csv`

Conservative upper-bound physical diversity derived only from feasible candidate-set size, without candidate weights.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `num_feasible_candidates` | Distinct feasible cable candidates in the unit |
| `num_feasible_corridors` | Distinct feasible corridors in the unit |
| `candidate_entropy_uniform` | Uniform entropy over feasible cable candidates |
| `corridor_entropy_uniform` | Uniform entropy over feasible corridors |
| `effective_candidate_count_uniform` | Uniform effective cable count |
| `effective_corridor_count_uniform` | Uniform effective corridor count |
| `physical_candidate_diversity_upper_bound` | Conservative upper-bound physical diversity score, currently the feasible cable-count view |

#### `output/result/unit_network_layer_diversity.csv`
#### `output/result/unit_logical_diversity.csv`

Unit-level network diversity tables. The legacy file `unit_logical_diversity.csv` is an alias of the network-layer version.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `num_probes`, `num_measurements`, `num_files_or_targets` | Unit composition counts |
| `num_dst_countries`, `num_src_dst_country_pairs` | Geographic diversity counts |
| `num_src_asns`, `num_dst_asns`, `num_src_dst_as_pairs` | ASN diversity counts |
| `link_country_sequence_entropy` | Entropy of observed country-pair sequences |
| `src_asn_entropy`, `dst_asn_entropy` | Entropy of source and destination ASN distributions |
| `as_pair_entropy`, `src_dst_as_pair_entropy` | Entropy of source-destination ASN pair distribution |
| `network_score_component_as_pair` | ASN-pair component of the composite network score |
| `network_score_component_country_pair` | Country-pair component of the composite network score |
| `network_score_component_endpoint_asn` | Endpoint-ASN component of the composite network score |
| `network_score_component_probe_target` | Probe/target multiplicity component |
| `network_layer_diversity_score_as_only` | Composite score using only AS-related components |
| `network_layer_diversity_score_country_only` | Composite score using only country component |
| `network_layer_diversity_score_probe_target_only` | Composite score using only the probe/target multiplicity component |
| `network_layer_diversity_score` | Main network-layer diversity score |
| `logical_diversity_score` | Legacy alias of `network_layer_diversity_score` |

#### `output/result/unit_network_physical_mismatch.csv`
#### `output/result/unit_network_physical_mismatch_corridor.csv`
#### `output/result/unit_mismatch.csv`

Joined network-vs-physical mismatch tables. The legacy file `unit_mismatch.csv` is an alias of the cable-level mismatch table.

These files contain all unit-level network-layer columns plus all physical-diversity columns, and:

| Column | Meaning |
| --- | --- |
| `network_high` | Whether network-layer diversity is above the unit median |
| `physical_low` | Whether physical diversity is at or below the unit median |
| `network_physical_mismatch_category` | One of the four quadrant labels |
| `network_physical_gap` | Network-layer diversity score minus physical diversity score |
| `network_definition` | Network diversity definition used to build the mismatch view |
| `network_score_column` | Concrete score column used for the network-side mismatch computation |
| `selected_network_diversity_score` | Network diversity score actually used for this mismatch view |
| `network_diversity_percentile`, `physical_diversity_percentile` | Percentile positions of the network and physical scores |
| `network_physical_percentile_gap` | Percentile gap between network and physical diversity |
| `network_diversity_rank`, `physical_diversity_rank` | Descending ranks of network and physical diversity |
| `network_physical_rank_gap` | Rank-gap mismatch between physical and network diversity |
| `logical_physical_gap` | Legacy alias of the same gap |
| `logical_high` | Legacy alias of `network_high` |
| `mismatch_category` | Legacy alias of `network_physical_mismatch_category` |
| `is_target_quadrant` | Whether the unit is in `network_high_physical_low` |

#### `output/result/unit_network_physical_upper_bound_mismatch.csv`

Mismatch table that compares network diversity against the conservative feasible candidate-space upper bound instead of the weighted candidate-support view.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `network_diversity_combined` | Composite network-layer diversity score |
| `network_diversity_as_only` | AS-only network diversity score |
| `network_diversity_country_only` | Country-only network diversity score |
| `network_diversity_target_probe` | Probe/target multiplicity score |
| `physical_candidate_diversity_upper_bound` | Conservative upper-bound physical diversity score |
| `network_percentile` | Percentile position of the combined network diversity score |
| `physical_upper_percentile` | Percentile position of the physical upper-bound score |
| `rank_gap_upper_bound` | Rank-gap mismatch between upper-bound physical diversity and network diversity |
| `strict_upper_bound_mismatch` | Whether the unit is high in network diversity but low even under the conservative physical upper bound |

#### `output/result/network_physical_quadrants.csv`

| Column | Meaning |
| --- | --- |
| `physical_level` | `cable` or `corridor` |
| `network_physical_mismatch_category` | Quadrant label |
| `unit_count` | Number of units in that quadrant |
| `unit_share` | Share of units in that quadrant |

#### `output/result/cable_vs_corridor_physical_diversity.csv`

Compares cable-level and corridor-level physical diversity for each unit.

| Column Group | Meaning |
| --- | --- |
| `cable_*` | Cable-level diversity metrics and quadrant labels |
| `corridor_*` | Corridor-level diversity metrics and quadrant labels |
| `corridor_minus_cable_physical_diversity` | Corridor score minus cable score |
| `corridor_vs_cable_effective_num_ratio` | Effective number ratio |
| `target_quadrant_preserved` | Whether the unit stays in the target quadrant at both levels |
| `quadrant_label_stable` | Whether cable-level and corridor-level quadrant labels agree |

#### `output/result/candidate_space_profile.csv`

Profiles how broad and ambiguous the feasible candidate space remains for each unit.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `avg_candidates_per_link`, `max_candidates_per_link` | Average / maximum number of feasible cable candidates per link |
| `avg_corridors_per_link`, `max_corridors_per_link` | Average / maximum number of feasible corridors per link |
| `share_parallel_ambiguity` | Share of links carrying parallel-corridor ambiguity |
| `share_multi_segment_possible` | Share of links tagged as potentially multi-segment |
| `share_domestic_submarine` | Share of links tagged as domestic submarine candidates |
| `share_large_radius` | Share of links with large landing-radius ambiguity |
| `share_low_confidence_projection` | Share of links whose `projection_class` is `weak` or `ambiguous` |

#### `output/result/weighted_vs_conservative_diversity.csv`

Corridor-first comparison between weighted diversity and uniform feasible-set diversity.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `weighted_effective_corridors` | Corridor-level effective diversity using weighted candidate support |
| `uniform_effective_corridors` | Corridor-level effective diversity using the uniform feasible corridor set |
| `weighted_entropy` | Weighted corridor entropy |
| `uniform_entropy` | Uniform corridor entropy |
| `weighted_rank`, `uniform_rank` | Unit ranks under the weighted and uniform corridor views |
| `weighted_gap`, `uniform_gap` | Gap between network diversity and the weighted / uniform corridor diversity view |

#### `output/result/unit_ambiguity_profile.csv`

Unit-level ambiguity support profile.

| Column | Meaning |
| --- | --- |
| `unit_id` | Aggregation unit |
| `num_candidate_rows` | Number of candidate rows belonging to the unit |
| `num_links` | Number of links in the unit |
| `*_support_share` | Share of unit support associated with a given ambiguity class |
| `no_ambiguity_support_share` | Share of support with no ambiguity tag |

#### `output/result/ambiguity_summary.csv`

Global ambiguity summary.

| Column | Meaning |
| --- | --- |
| `ambiguity_class` | Ambiguity category, including `no_ambiguity` |
| `candidate_rows` | Candidate rows carrying that ambiguity |
| `candidate_row_share` | Share of candidate rows |
| `aggregate_normalized_support` | Summed candidate support attributed to that ambiguity |
| `aggregate_support_share` | Share of global support mass |
| `units_affected` | Number of units affected |

#### `output/result/ambiguity_taxonomy.csv`

Interpretation guide for ambiguity classes.

| Column | Meaning |
| --- | --- |
| `ambiguity_class` | Tag name |
| `reviewer_concern` | Concern likely to be raised by a reviewer |
| `treatment` | How the code handles or interprets the ambiguity |
| `interpretation_boundary` | What the result should not be over-claimed to mean |

#### `output/result/core_agreement_summary.csv`

Global summary of evidence-core agreement.

| Column | Meaning |
| --- | --- |
| `core_agreement` | Agreement class such as `dual_core_agreement` |
| `candidate_rows` | Number of candidate rows in the class |
| `candidate_row_share` | Share of candidate rows |
| `aggregate_normalized_support` | Summed support mass in the class |
| `aggregate_support_share` | Share of total support mass |
| `units_affected` | Number of units containing the class |

#### `output/result/as_reranking_effect.csv`

Link-level summary of how geo-only, AS-only, and fused rankings differ.

| Column | Meaning |
| --- | --- |
| `total_links` | Number of links evaluated |
| `geo_as_top_agreement_rate` | Fraction of links where geo-only and AS-only top-1 agree |
| `geo_fused_top_agreement_rate` | Fraction of links where geo-only and fused top-1 agree |
| `as_fused_top_agreement_rate` | Fraction of links where AS-only and fused top-1 agree |
| `as_changes_geo_top1_rate` | Fraction of links where AS-only changes the geo-only top-1 |
| `mean_geo_to_fused_rank_shift` | Average shift from geo top-1 to its fused rank |
| `mean_as_to_fused_rank_shift` | Average shift from AS top-1 to its fused rank |
| `parallel_links` | Number of parallel-corridor links |
| `parallel_links_with_dual_core_agreement` | Parallel links containing dual-core agreement |
| `parallel_links_remaining_ambiguous` | Parallel links that remain ambiguous |

#### `output/result/filtering_breakdown.csv`

Lightweight summary of Stage 1 filtering and retention.

| Column | Meaning |
| --- | --- |
| `total_traces_processed` | Number of traceroute records processed |
| `empty_trace_count` | Empty or invalid trace count |
| `total_links_seen` | Total links evaluated |
| `same_city_filtered` | Same-city links removed early |
| `links_with_ls_candidates` | Links with landing-station candidates |
| `links_with_geo_candidates` | Links with spatial candidates |
| `candidate_segments_considered` | Candidate segments considered before RTT filtering |
| `rtt_infeasible_filtered` | RTT-infeasible candidates removed |
| `links_with_any_match` | Links with at least one final match |
| `total_candidates_generated` | Total candidate rows generated |
| `total_candidates_after_threshold` | Candidate rows retained after thresholding |
| `links_with_parallel_ambiguity` | Links marked as parallel ambiguous |
| `links_with_domestic_candidates` | Links with domestic submarine candidates |

#### `output/result/dataset_summary.csv`

Two-column metric table summarizing the overall run.

| Column | Meaning |
| --- | --- |
| `metric` | Summary metric name |
| `value` | Metric value |

#### `output/result/method_manifest.json`

Post-processing method manifest.

| Key | Meaning |
| --- | --- |
| `method_name` | High-level method name |
| `main_question` | Main auditing question |
| `claim_boundary` | Explicit interpretation boundary |
| `primary_target_quadrant` | Main mismatch quadrant of interest |
| `evidence_cores` | Evidence cores used by the model |
| `fusion_model` | High-level fusion rule |
| `physical_levels` | Supported physical aggregation levels |
| `ambiguity_classes` | Known ambiguity tags |
| `network_definitions` | Supported network diversity definitions used in robustness and mismatch comparison |
| `primary_outputs` | Main post-processing outputs |
| `interpretation` | One-line interpretation guidance |

#### Post-processing SVG files

| File | Meaning |
| --- | --- |
| `network_physical_quadrant_scatter_cable.svg` | Scatter of network-layer vs cable-level physical diversity |
| `network_physical_quadrant_scatter_corridor.svg` | Scatter of network-layer vs corridor-level physical diversity |
| `network_physical_quadrant_counts_cable.svg` | Cable-level quadrant count bar chart |
| `network_physical_quadrant_counts_corridor.svg` | Corridor-level quadrant count bar chart |
| `cable_vs_corridor_physical_diversity.svg` | Scatter comparing cable-level and corridor-level physical diversity |

### E. Robustness Outputs

#### `output/result/robustness_summary.csv`

| Column | Meaning |
| --- | --- |
| `mode` | Evidence-setting label |
| `network_definition` | Network diversity definition used in the comparison |
| `physical_level` | `cable` or `corridor` |
| `num_units_compared` | Number of units compared with baseline |
| `spearman_dominant_candidate_support_share` | Spearman correlation of dominant support share |
| `spearman_effective_num_candidates` | Spearman correlation of effective number of candidates |
| `topk_dominant_share_overlap` | Overlap ratio of top-k dominant-share units |

#### `output/result/robustness_mismatch_stability.csv`

| Column | Meaning |
| --- | --- |
| `mode` | Evidence-setting label |
| `network_definition` | Network diversity definition used in the comparison |
| `physical_level` | `cable` or `corridor` |
| `num_units_compared` | Number of units in the comparison |
| `baseline_target_units` | Number of baseline target-quadrant units |
| `mode_target_units` | Number of target-quadrant units in the current setting |
| `shared_target_units` | Number of shared target-quadrant units |
| `target_jaccard_vs_baseline` | Jaccard overlap with baseline target units |
| `target_precision_vs_baseline` | Precision relative to baseline target units |
| `target_recall_vs_baseline` | Recall relative to baseline target units |
| `quadrant_agreement_rate` | Overall quadrant-label agreement rate |

#### `output/result/robustness_quadrant_summary.csv`

| Column | Meaning |
| --- | --- |
| `physical_level` | `cable` or `corridor` |
| `network_physical_mismatch_category` | Quadrant label |
| `unit_count` | Number of units in that quadrant |
| `unit_share` | Share of units in that quadrant |
| `network_definition` | Network diversity definition used for that robustness slice |
| `mode` | Evidence-setting label |

#### `output/result/robustness_profile_table.csv`

Paper-facing robustness table.

| Column | Meaning |
| --- | --- |
| `setting` | Full setting label such as `fused_dual_core_cable` |
| `evidence_view` | Coarser evidence view such as `geo_only` or `as_only` |
| `network_definition` | Network diversity definition, such as `composite`, `as_only`, or `country_only` |
| `physical_level` | `cable` or `corridor` |
| `physical_projection_setting` | Whether physical candidates are evaluated as direct cable candidates or corridor-grouped candidates |
| `rank_corr_dominant_support` | Spearman correlation of dominant support ranking |
| `rank_corr_effective_num` | Spearman correlation of effective number ranking |
| `target_quadrant_jaccard` | Jaccard overlap of target-quadrant units |
| `target_quadrant_recall` | Recall of target-quadrant units relative to baseline |
| `quadrant_agreement_rate` | Overall quadrant-label agreement |
| `interpretation` | Human-readable description of the robustness setting |

#### `output/result/robustness_candidate_space.csv`

Candidate-space robustness table comparing weighted vs uniform diversity, cable vs corridor aggregation, and all links vs strong projections only.

| Column | Meaning |
| --- | --- |
| `network_definition` | Network diversity definition used in the comparison |
| `setting` | Robustness setting label |
| `weighting_view` | `weighted` or `uniform` feasible-set physical diversity |
| `physical_level` | `cable` or `corridor` |
| `physical_projection_setting` | Cable-candidate or corridor-grouped physical projection setting |
| `projection_subset` | Whether the view uses all projections or only `strong` projections |
| `num_units_compared` | Number of units compared under the setting |
| `rank_corr_physical_diversity` | Spearman correlation of physical-diversity rankings relative to the corridor-weighted baseline |
| `target_quadrant_jaccard` | Jaccard overlap of `network_high_physical_low` units relative to the corridor-weighted baseline |
| `target_quadrant_recall` | Recall of target-quadrant units relative to the corridor-weighted baseline |
| `quadrant_agreement_rate` | Overall quadrant agreement rate relative to the corridor-weighted baseline |
| `baseline_setting` | Baseline used for the comparison, currently `weighted_all_corridor` |

#### `output/result/robustness_network_high_physical_low_stability.svg`

Bar chart showing shared `network_high_physical_low` units across robustness settings.

## Collaboration Notes

- The repository is intended to be used across multiple computers through GitHub.
- The expected shared source of truth is `origin/main`.
- Runtime data files remain local inputs; code and documentation are tracked in Git.
- For agent-side collaboration rules, see `AGENTS.md`.

## Latest Conservative Candidate Audit Additions

The repository now distinguishes two Stage 1 candidate views:

- `all_feasible_segments`: the infeasibility-first feasible candidate space retained before support thresholding.
- `all_segments`: the legacy support-thresholded view kept for backward compatibility.

Additional Stage 1 `match_summary` fields include:

- `num_feasible_candidates_total`
- `num_feasible_corridors_total`
- `feasible_candidate_retention_mode`
- `support_threshold_used_for_legacy_all_segments`
- `support_threshold_value`

Additional candidate-level fields include:

- `hard_feasible`
- `infeasibility_filter_passed`
- `support_above_threshold`
- `support_filter_reason`
- `geo_entry_support`
- `geo_exit_support`
- `geo_spatial_support`

New post-processing outputs:

- `output/result/trace_feasible_candidate_space.csv`: flattened feasible candidate-space table derived from `all_feasible_segments`, with automatic fallback to `all_segments` for old JSON files.
- `output/result/unit_physical_candidate_set_diversity_cable.csv`: cable-level conservative feasible-set diversity.
- `output/result/unit_physical_candidate_set_diversity_corridor.csv`: corridor-level conservative feasible-set diversity. This is a candidate-breadth descriptor, not the paper-primary observation-concentration metric.
- `output/result/unit_network_physical_upper_bound_mismatch.csv`: long-form mismatch table comparing network diversity with conservative upper-bound physical diversity across all network definitions and both cable/corridor levels.
- `output/result/paper_unit_physical_candidate_diversity.csv`: legacy/supplementary alias of the corridor-level conservative feasible-set diversity output.
- `output/result/paper_unit_network_physical_mismatch.csv`: legacy/supplementary alias of the corridor-level conservative upper-bound mismatch output.
- `output/result/conservative_candidate_audit_manifest.json`: compact manifest describing infeasibility-first semantics and generated outputs.
- `output/result/robustness_conservative_candidate_audit.csv`: robustness table comparing weighted support vs conservative feasible sets across network definitions, physical levels, and projection subsets.

Interpretation boundary:

- Geo/RTT/landing constraints are used primarily to exclude impossible or highly implausible candidates.
- `candidate_support` is an evidence-support score inside the retained feasible set, not a ground-truth cable-usage probability.
- Conservative set-based diversity treats all feasible candidates equally and should be interpreted as an upper bound on possible physical diversity.

## PeeringDB Descriptor Additions

PeeringDB is treated only as an external network-layer interconnection footprint descriptor. It is not used in feasible candidate filtering, candidate support scoring, or corridor assignment.

Input directory:

- `data/peeringdb/`

Supported local dump files when present:

- `ix.json`
- `fac.json`
- `net.json`
- `netfac.json`
- `netixlan.json`

Primary descriptor output:

- `output/result/country_peeringdb_descriptors.csv`

Columns:

| Column | Meaning |
| --- | --- |
| `country` | Source-country join key |
| `pdb_num_ixps` | Number of PeeringDB IXPs in the country |
| `pdb_num_facilities` | Number of PeeringDB facilities in the country |
| `pdb_num_networks` | Number of unique networks with facility presence or IXP participation in the country |
| `pdb_num_network_facility_presence` | Number of network-to-facility presence records in the country |
| `pdb_num_ixp_participants` | Number of unique network-to-IXP participation pairs in the country |
| `pdb_ixp_participant_entropy` | Shannon entropy of participant counts across IXPs |
| `pdb_facility_participant_entropy` | Shannon entropy of facility-presence counts across facilities |
| `pdb_interconnection_footprint_score` | Log-scaled external interconnection footprint descriptor |
| `pdb_interconnection_footprint_percentile` | Percentile rank of the descriptor across available countries |
| `pdb_interconnection_footprint_tier` | `low`, `medium`, or `high`, based on tertiles |

Additional outputs:

- `output/result/peeringdb_footprint_mismatch_summary.csv`

PeeringDB descriptors are merged into:

- `output/result/unit_network_physical_upper_bound_mismatch.csv`
- `output/result/paper_unit_network_physical_mismatch.csv`
- `output/result/robustness_conservative_candidate_audit.csv` when descriptor context is available

## Latest Network-Diversity Update

The paper-primary network definition is now `as_egress_primary`.

- `as_egress_primary`: source-country AS-egress transition diversity across cross-border traceroute links
- `as_pair_primary`: AS-pair and endpoint-AS diversity fallback when explicit egress observations are sparse
- `dst_asn_primary`: destination-AS diversity view
- `geographic_transition_supplementary`: country-transition descriptor kept as a supplementary geographic view
- `application_observation_supplementary`: probe/measurement/target richness descriptor
- `combined_supplementary`: historical composite score retained as a supplementary summary

Country-only remains available for backward compatibility, but it is now a supplementary descriptor rather than the recommended main-text network diversity metric.

Additional outputs:

- `output/result/network_diversity_metric_catalog.csv`: documents each network diversity definition, its score column, metric role, interpretation, and whether it is recommended for the paper main text.
- `output/result/paper_unit_network_physical_mismatch.csv`: legacy/supplementary alias that defaults to the `as_egress_primary` + `corridor` + conservative upper-bound view. It is not the paper-primary corridor observation concentration table.

PeeringDB remains external-only:

- it is merged into mismatch and robustness outputs for stratification,
- it is not used for feasible candidate filtering,
- it is not used for candidate-support scoring,
- it is not used for corridor assignment,
- and it is not used to compute `network_diversity_as_egress_primary`.

## Latest Cross-Layer Audit Update

Non-rank cross-layer metrics are now first-class outputs rather than a fallback interpretation layer.

- Primary non-rank metrics:
  - `network_effective_diversity`
  - `physical_candidate_diversity_upper_bound`
  - `network_to_physical_compression_ratio`
  - `log_network_physical_compression_gap`
  - `physical_coverage_ratio`
  - `absolute_compression_tier`
- Relative rank/percentile metrics remain available in the same tables:
  - `network_percentile`
  - `physical_upper_bound_percentile`
  - `rank_gap_upper_bound`
  - `strict_upper_bound_mismatch_75_25`
  - `upper_bound_mismatch_category`

New output files:

- `output/result/unit_cross_layer_audit.csv`: unit-level cross-layer audit table with application, network, physical, non-rank compression, optional relative, and PeeringDB descriptor columns.
- `output/result/country_cross_layer_audit.csv`: country-level cross-layer audit recomputed directly from link-level observations and feasible candidate rows.
- `output/result/service_country_cross_layer_audit.csv`: source-country plus service-level cross-layer audit; `service_id` prefers explicit `service_id`, then falls back to `file_name`, then `msm_id`.
- `output/result/paper_country_cross_layer_audit.csv`: legacy/supplementary corridor-level alias of the country audit output.
- `output/result/paper_service_country_cross_layer_audit.csv`: legacy/supplementary corridor-level alias of the service-country audit output.
- `output/result/cross_layer_metric_summary.csv`: compact summary of non-rank compression tiers and relative mismatch rates across the new audit tables.

Interpretation update:

- The same non-rank compression/coverage metrics support both global multi-country corpora and single-country datasets.
- Rank-based mismatch remains a relative comparison view over the chosen corpus, not the only cross-layer interpretation.

## Latest Corridor Observation Concentration Update

The paper-primary physical concentration view is now based on **corridor observation distributions** over independently mappable path-transition segments.

- A traceroute is decomposed into independently mappable hop-pair / country-transition segments.
- Each segment is anchored to the near-side country of the transition.
- Multiple feasible cable rows belonging to the same corridor are deduplicated within the same atomic segment.
- Each atomic segment contributes one unit of observation mass, split uniformly across its distinct feasible corridors in the paper-primary view.
- Observation mass reflects measurement-observed path-transition segments, not byte or packet traffic volume.
- Unique feasible corridor count remains a candidate-breadth descriptor, not the paper-primary concentration metric.

New or newly promoted outputs:

- `output/result/atomic_segment_id_diagnostics.json`: records the stable field bundle used to construct atomic segment IDs.
- `output/result/country_corridor_observation_distribution.csv`: country-level corridor observation-mass distribution. Key columns include `observation_mass`, `share_of_country_observation_mass`, and `rank_within_country`.
- `output/result/service_country_corridor_observation_distribution.csv`: service-country corridor observation-mass distribution. Key columns include `observation_mass`, `share_of_unit_observation_mass`, and `rank_within_unit`.
- `output/result/country_corridor_concentration_summary.csv`: paper-facing country summary with `top1_corridor_share`, `top3_corridor_share`, `effective_corridor_count`, `corridor_concentration_tier`, and `auditable_corridor_concentration`.
- `output/result/service_country_corridor_concentration_summary.csv`: service-country version of the same concentration summary and the main paper-ready unit table for corridor observation concentration.
- `output/result/country_network_transition_concentration_summary.csv`: network-transition concentration over the same mappable segment population, using AS transitions first and country-transition fallback when ASNs are missing.
- `output/result/service_country_network_transition_concentration_summary.csv`: service-country network-transition concentration summary.
- `output/result/country_cross_layer_distribution_audit.csv`: country-level cross-layer distribution-shape audit joining network transition concentration and corridor observation concentration.
- `output/result/service_country_cross_layer_distribution_audit.csv`: service-country cross-layer distribution-shape audit with `cross_layer_distribution_class` as the main interpretation field.
- `output/result/paper_corridor_observation_concentration_cases.csv`: auditable severe or moderate corridor observation concentration cases.
- `output/result/paper_network_broad_physical_concentrated_cases.csv`: main paper cases where network observations remain broad but corridor observations are concentrated.
- `output/result/paper_broad_corridor_distribution_cases.csv`: broad-corridor counterexamples showing the framework does not force concentration findings.

Interpretation update:

- Candidate breadth asks how many unique feasible corridors appear in a unit.
- Observation concentration asks how measurement-observed path-transition segments distribute over those feasible corridors.
- The cross-layer distribution audit compares concentration patterns over the same observed segment population; it does not equate AS-transition counts with corridor counts as identical units.

## Large-Scale 5051 Run Artifacts

The repository also supports a full-scale RIPE Atlas `msm_id = 5051` run.

- Recommended output directory for the large-scale run: `output/result_5051/`
- Small and medium summary artifacts from that run can be committed for inspection.
- Extremely large link-level artifacts may remain local-only because they exceed practical GitHub size limits.

Typical large local-only files from a full `5051` run:

- `output/result_5051/cable_matching_output.json`
- `output/result_5051/trace_feasible_candidate_space.csv`
- `output/result_5051/trace_candidate_support.csv`

## Best-Case Physical-Candidate Audit Update

The primary paper interpretation is now a best-case physical-candidate audit.

- `physical_candidate_diversity_upper_bound` is the upper-bound width of the best-case feasible physical-candidate space under hard feasibility constraints.
- Physical-candidate concentration means the best-case feasible candidate space itself is narrow.
- Network-to-physical compression means `network_effective_diversity` exceeds the best-case physical-candidate upper bound.
- No network-to-physical compression does not imply no physical-candidate exposure.
- PeeringDB descriptors remain external interconnection-footprint descriptors only and are not used for physical-candidate construction or candidate-support scoring.
- Rank/percentile metrics remain auxiliary relative views.

Additional outputs:

- `output/result/physical_candidate_concentration_summary.csv`
- `output/result/joint_cross_layer_risk_summary.csv`
- `output/result/paper_physical_concentration_cases.csv`
- `output/result/paper_joint_mismatch_cases.csv`
- `output/result/paper_broad_physical_space_cases.csv`

## Latest Framework-Alignment Patch

Stage 1 now records additional paper-alignment metadata without changing the candidate matching philosophy.

- `--cable-availability-mode` controls conservative cable lifecycle filtering. The paper-primary default is `confirmed_active_only`, which excludes candidates that are known to be future/planned, retired, or lifecycle-unknown at the traceroute timestamp. Use `confirmed_active_plus_unknown` only as a robustness/coverage view that retains and marks unknown lifecycle metadata.
- Non-positive or otherwise noisy RTT deltas are treated as `rtt_feasibility_status = inconclusive`: they are retained in the feasible set with an `rtt_inconclusive` ambiguity tag and are not used as hard infeasibility evidence. Only valid RTT observations that violate the lower-bound constraint after tolerance are hard-filtered.
- Optional landing-region overrides can be supplied with `--landing-region-override-file`. The file maps `landing_station_id` to `landing_region_id` / `landing_region_name`; manual overrides take precedence over automatic geographic connected components and are recorded in the manifest.
- Traceroute link generation records a service-entry boundary when the actual target ASN is observed in the hop sequence. Downstream trace summaries expose whether the service-entry point was resolved, while the physical projection remains hop-pair based.
- Candidate rows carry cable lifecycle fields such as `cable_status`, `cable_rfs_date`, `cable_retired_date`, `cable_availability_status`, and `availability_filter_passed`.
- `output/result/supplementary_owner_concentration.csv` summarizes split owner exposure over feasible corridor observation mass. It is supplementary only: owners are not used as ground truth, and this table must not be read as per-owner traffic volume or per-cable utilization.

## Latest IPinfo ASN Database Update

All current IP-to-ASN lookups use `data/ipinfo/ipinfo_asn.mmdb`.

- `source/main_analysis.py` resolves hop ASNs, link endpoint ASNs, target ASNs, and service-entry ASNs through the IPinfo ASN MMDB.
- `source/concerntration_analysis.py` resolves ASNs for cross-border AS-pair features through the IPinfo ASN MMDB.
- `data/ipinfo/ipinfo_location.mmdb` remains the geolocation source for country, city, latitude, and longitude; it is no longer the primary ASN source.
- `data/pfx2as/202512.pfx2as` and `--pfx2as-file` are retained only for legacy compatibility notes; the current pipeline does not use them for IP-to-ASN lookup.
- Use `--asn-mmdb-path` to point either stage at another IPinfo ASN MMDB file.
