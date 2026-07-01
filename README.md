# infocom26

This repository now keeps its implementation under `source/`, while preserving root-level entrypoints so the project can still be run with the original commands.

## Pipeline Layout

### Stage 1: `main_analysis.py` / `source/main_analysis.py`

This is the uncertainty-aware candidate-support generation stage. It:

- loads landing-station coordinates, submarine cable metadata, AS relationship data, `pfx2as`, owner-to-ASN mappings, and traceroute files
- geolocates hops with the MMDB database
- converts traceroute hops into adjacent hop-pair links
- builds Geo-spatial Core, AS-economic Core, and RTT/Physical Feasibility Core evidence
- fuses evidence into `candidate_support`, `fused_candidate_support`, `normalized_candidate_support`, and `core_agreement`
- writes link-level candidate outputs to `output/result/cable_matching_output.json`
- writes enhanced matcher statistics to `output/result/cable_matching_stats_5051.json`
- writes a run manifest to `output/result/cable_matching_manifest.json`

### Stage 2: `concerntration_analysis.py` / `source/concerntration_analysis.py`

This is the dependency aggregation stage. It:

- loads the raw traceroute file, stage-1 output, probe metadata, cable owner metadata, MMDB, and `pfx2as`
- aggregates dependency by country and root/target
- computes cable concentration, owner concentration, cross-border AS-pair concentration, and related summary indicators
- writes the final dependency table to `output/result/country_root_cable_dependency_hybrid.csv`

### Post-processing: `postprocess_candidate_output.py`

This script reads the stage-1 JSON output and generates:

- `output/result/trace_candidate_support.csv`
- `output/result/unit_physical_candidate_diversity.csv`
- `output/result/unit_logical_diversity.csv`
- `output/result/unit_mismatch.csv`
- `output/result/dataset_summary.csv`

### Robustness: `robustness_compare.py`

This script compares evidence settings over the post-processed candidate table and writes:

- `output/result/robustness_summary.csv`

## Source Organization

```text
source/
  __init__.py
  main_analysis.py
  concerntration_analysis.py
  postprocess_candidate_output.py
  robustness_compare.py
```

Root-level scripts are thin wrappers that call the corresponding `source/` modules.

## Required Inputs

### Stage 1 inputs

- `data/cable/landing-point-geo.json`
- `data/cable/*.json`
- `data/traceroute_rundnsroot/**/*.json`
- `data/ipinfo/ipinfo_location.mmdb`
- `data/asrelationship/20250901.as-rel2.txt`
- `data/pfx2as/202512.pfx2as`
- `data/owner2asn/owner_to_asn.csv`

### Stage 2 inputs

- `data/traceroute_rundnsroot/root_dns_traces.json` for routine testing
- `output/result/cable_matching_output.json` produced by stage 1
- `data/probe/20251201.json`
- `data/ipinfo/ipinfo_location.mmdb`
- `data/pfx2as/202512.pfx2as`
- `data/cable/*.json`

The larger `data/traceroute/ripe_atlas_5051_20251201.json` file can still be used for full runs, but routine tests should stay on the smaller `root_dns_traces.json` input.

## Environment Setup

Install dependencies with:

```powershell
python -m pip install -r .\requirements.txt
```

On this machine, a user-scoped Python 3.13.14 environment and these packages have already been installed:

- `maxminddb`
- `geopy`
- `scikit-learn`
- `tqdm`
- `pandas`

## Run Order

The original entrypoints still work:

```powershell
python .\main_analysis.py
python .\concerntration_analysis.py
python .\postprocess_candidate_output.py --input .\output\result\cable_matching_output.json --output .\output\result
python .\robustness_compare.py --input .\output\result\trace_candidate_support.csv --output .\output\result
```

If you want to choose a specific probe metadata file for stage 2:

```powershell
python .\concerntration_analysis.py --probe-file-name 20251223.json
python .\concerntration_analysis.py --probe-use-latest
```

You can also run the source files directly:

```powershell
python .\source\main_analysis.py
python .\source\concerntration_analysis.py
```

## Directory Skeleton

```text
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
  result/
```

## Collaboration Workflow

This repository is intended to be edited across multiple computers through GitHub.

- The shared source of truth is `origin/main`.
- After pulling the repository on another computer, Codex can continue editing the same tracked source tree.
- Runtime datasets remain local inputs and should be placed into the prepared `data/` folders on any machine that needs to run the pipelines.
- Completed changes in this project should be committed to `main` and pushed to GitHub unless you explicitly choose a different workflow.

For agent-facing workflow rules, see `AGENTS.md`.
