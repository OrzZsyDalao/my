# infocom26

This repository implements an uncertainty-aware cross-layer diversity auditing pipeline for RIPE Atlas traceroute measurements, AS-level economic signals, and submarine-cable candidate infrastructure.

The main research question is:

> Does network-layer diversity remain diverse after it is projected into the physical-candidate infrastructure space?

The goal is **not** per-path ground-truth submarine cable attribution. The pipeline produces candidate-support distributions, diversity metrics, mismatch diagnostics, ambiguity profiles, and robustness comparisons.

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

## Input File Reference

### Shared Input Files

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `data/cable/landing-point-geo.json` | Stage 1 | GeoJSON features keyed by landing-station `id`, with coordinates | Landing-station coordinate lookup for spatial candidate generation |
| `data/cable/*.json` | Stage 1, Stage 2, AS precompute | One JSON per cable, including `id`, `name`, `landing_points`, `owners` | Cable metadata, landing pairs, and owner metadata |
| `data/ipinfo/ipinfo_location.mmdb` | Stage 1, Stage 2 | MMDB geolocation database | IP-to-country/city/ASN geolocation |
| `data/asrelationship/20250901.as-rel2.txt` | Stage 1, AS precompute | CAIDA-style AS relationships (`AS1|AS2|rel`) | AS-economic relationship model |
| `data/pfx2as/202512.pfx2as` | Stage 1, Stage 2 | Prefix-to-origin-AS mapping | IP to origin ASN lookup |
| `data/owner2asn/owner_to_asn.csv` | Stage 1, AS precompute | CSV with `owner,asn` | Maps cable owners to ASNs |

### Traceroute and Probe Inputs

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `data/traceroute_rundnsroot/root_dns_traces.json` | Stage 1 default, Stage 2 default | RIPE Atlas traceroute results in JSON array format | Small routine test input |
| `data/traceroute_rundnsroot/**/*.json` | Stage 1 | RIPE Atlas traceroute result files | Main traceroute source directory |
| `data/traceroute/ripe_atlas_5051_20251201.json` | Optional | Larger full-scale traceroute input | Full dataset run |
| `data/probe/*.json` | Stage 2 | Probe metadata, typically with `objects[].id` and `objects[].country_code` | Maps probe IDs to source countries |

### Precomputed Optional Input

| Path | Used By | Expected Content | Purpose |
| --- | --- | --- | --- |
| `output/preprocessed/as_graph_owner_reachability.pkl.gz` | Stage 1 | Gzipped Python pickle with owner-group reachability payload | Speeds up the AS-economic support computation |

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

### `python concerntration_analysis.py`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `--raw-traces-file` | `data/traceroute_rundnsroot/root_dns_traces.json` | Raw traceroute input file or directory |
| `--match-output-file` | `output/result/cable_matching_output.json` | Stage 1 matching JSON |
| `--probe-meta-file` | `data/probe/20251201.json` | Probe metadata file |
| `--probe-file-name` | `None` | Probe filename under `data/probe/` |
| `--probe-use-latest` | `False` | Automatically select latest probe JSON |
| `--mmdb-path` | `data/ipinfo/ipinfo_location.mmdb` | MMDB path |
| `--pfx2as-file` | `data/pfx2as/202512.pfx2as` | pfx2as path |
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

## Recommended Run Order

```powershell
python .\precompute_as_graph.py
python .\main_analysis.py
python .\concerntration_analysis.py
python .\postprocess_candidate_output.py --input .\output\result\cable_matching_output.json --output .\output\result
python .\robustness_compare.py --input .\output\result\trace_candidate_support.csv --output .\output\result
```

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
| `mmdb_path`, `pfx2as_file`, `cable_dir` | Reference input files |
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
- `output/result/unit_physical_candidate_set_diversity_corridor.csv`: corridor-level conservative feasible-set diversity and the primary paper-ready physical diversity view.
- `output/result/unit_network_physical_upper_bound_mismatch.csv`: long-form mismatch table comparing network diversity with conservative upper-bound physical diversity across all network definitions and both cable/corridor levels.
- `output/result/paper_unit_physical_candidate_diversity.csv`: paper-ready alias of the corridor-level conservative feasible-set diversity output.
- `output/result/paper_unit_network_physical_mismatch.csv`: paper-ready alias of the corridor-level conservative upper-bound mismatch output.
- `output/result/conservative_candidate_audit_manifest.json`: compact manifest describing infeasibility-first semantics and generated outputs.
- `output/result/robustness_conservative_candidate_audit.csv`: robustness table comparing weighted support vs conservative feasible sets across network definitions, physical levels, and projection subsets.

Interpretation boundary:

- Geo/RTT/landing constraints are used primarily to exclude impossible or highly implausible candidates.
- `candidate_support` is an evidence-support score inside the retained feasible set, not a ground-truth cable-usage probability.
- Conservative set-based diversity treats all feasible candidates equally and should be interpreted as an upper bound on possible physical diversity.
