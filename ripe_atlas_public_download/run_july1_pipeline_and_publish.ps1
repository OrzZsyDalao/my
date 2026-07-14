<#
Run the July 1 public Atlas pipeline, package paper-facing CSVs, and publish
only the result bundle. This intentionally never stages raw JSON or trace-level
candidate tables.
#>

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

python -u .\ripe_atlas_public_download\run_per_measurement_pipeline.py
if ($LASTEXITCODE -ne 0) { throw "Per-measurement pipeline failed with exit code $LASTEXITCODE" }

python .\ripe_atlas_public_download\package_paper_csv_results.py
if ($LASTEXITCODE -ne 0) { throw "Result packaging failed with exit code $LASTEXITCODE" }

git add -- results\july1_public_atlas_20260701
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "No packaged result changes to publish."
    exit 0
}

git commit -m "Add July 1 public Atlas audit CSV results"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed with exit code $LASTEXITCODE" }

git push origin main
if ($LASTEXITCODE -ne 0) { throw "Git push failed with exit code $LASTEXITCODE" }
