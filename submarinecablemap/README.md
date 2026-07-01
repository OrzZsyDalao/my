This directory stores a reproducible fetch from [submarinecablemap.com](https://www.submarinecablemap.com/) using the site's public JSON endpoints.

Key endpoints confirmed from the live site on 2026-07-01:

- `https://www.submarinecablemap.com/api/v3/search.json`
- `https://www.submarinecablemap.com/api/v3/cable/cable-geo.json`
- `https://www.submarinecablemap.com/api/v3/config.json`
- `https://www.submarinecablemap.com/api/v3/cable/{id}.json`
- `https://www.submarinecablemap.com/robots.txt`

Usage:

```powershell
& 'C:\Users\13578\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  submarinecablemap\fetch_and_compare.py
```

Outputs:

- `submarinecablemap/cable/`: latest per-cable JSON files plus `landing-point-geo.json`, organized so this folder can directly replace `data/cable`
- `submarinecablemap/comparison_summary.json`: aggregate comparison summary
- `submarinecablemap/comparison_changed.json`: field-level diffs for shared cable ids
- `submarinecablemap/comparison_remote_only.json`: cables present on the live site but missing locally
- `submarinecablemap/comparison_local_only.json`: cables present locally but absent on the live site
- `submarinecablemap/comparison_landing_point_geo.json`: landing-point GeoJSON diff summary
- `submarinecablemap/replacement_validation.json`: compatibility checks against the current loader expectations
