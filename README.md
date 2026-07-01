# infocom26

This repository currently contains two Python analysis scripts for submarine-cable inference and dependency aggregation.

## What The Two Scripts Do

### `main_analysis.py`

This script is the first-stage pipeline. It:

- loads landing-station coordinates, submarine cable metadata, AS relationship data, `pfx2as`, owner-to-ASN mappings, and traceroute files
- geolocates hops with the MMDB database
- converts traceroute hops into adjacent hop-to-hop links
- scores each link against candidate submarine cable segments using geography, RTT feasibility, and ASN/owner relationship evidence
- writes matched link results to `output/result/cable_matching_output.json`
- writes match statistics to `output/result/cable_matching_stats_5051.json`
- writes a cable/landing-station debug snapshot to `cable_loading_debug.json`

### `concerntration_analysis.py`

This script is the second-stage pipeline. It:

- loads the raw traceroute file, the stage-1 match result, probe metadata, cable owner metadata, MMDB, and `pfx2as`
- aggregates dependency by country and root/target
- computes cable concentration, owner concentration, cross-border AS-pair concentration, and related summary indicators
- writes the final dependency table to `output/result/country_root_cable_dependency_hybrid.csv`
- optionally writes a merged total table, per-mode detail CSVs, and a summary JSON

## How They Work Together

The intended flow is:

1. `main_analysis.py` reads traceroute data and produces per-link cable match candidates.
2. `concerntration_analysis.py` reads that match output plus the raw traces and probe metadata, then computes country/root-level dependency statistics.

In short: the first script infers which cables each traceroute segment may traverse, and the second script turns those inferred cable usages into dependency/concentration tables.

## Required Inputs

The repository is currently missing all runtime data files. The following paths are expected by default.

### Required by `main_analysis.py`

- `data/cable/landing-point-geo.json`
- `data/cable/*.json` for submarine cable metadata
- `data/traceroute_rundnsroot/**/*.json`
- `data/ipinfo/ipinfo_location.mmdb`
- `data/asrelationship/20250901.as-rel2.txt`
- `data/pfx2as/202512.pfx2as`
- `data/owner2asn/owner_to_asn.csv`

### Required by `concerntration_analysis.py`

- `data/traceroute/RIPE-Atlas-measurement-5051-1764518400-to-1764540000.json`
- `output/result/cable_matching_output.json` produced by `main_analysis.py`
- `data/probe/20251201.json`
- `data/ipinfo/ipinfo_location.mmdb`
- `data/pfx2as/202512.pfx2as`
- `data/cable/*.json`

## Directory Skeleton

The folder structure below is now prepared in the repository so the missing datasets can be dropped into place directly:

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

This repository is set up so it can be used from multiple computers through GitHub.

- The shared source of truth is the GitHub repository, not a single Codex session.
- After pulling the repository on another computer, Codex can continue editing the same project because the code, directory skeleton, and workflow instructions are all tracked in the repo.
- The default workflow for this project is to work on `main`, commit completed changes, and push them to `origin/main` unless you explicitly ask for a different branch strategy.
- Runtime datasets are still local inputs that must be placed into the prepared `data/` folders on each machine as needed.

For agent-facing workflow rules, see `AGENTS.md`.

## Quick Run Order

```powershell
python .\main_analysis.py
python .\concerntration_analysis.py
```
