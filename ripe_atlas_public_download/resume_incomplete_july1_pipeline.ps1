<# Resume the measurements interrupted during the optimized July 1 rerun. #>

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$measurementIds = @(
    5005, 5016, 5001, 5008, 5006,
    176517335, 176906957, 86710103
)
$runnerArgs = @("ripe_atlas_public_download/run_per_measurement_pipeline.py")
foreach ($measurementId in $measurementIds) {
    $runnerArgs += "--measurement-id"
    $runnerArgs += "$measurementId"
}
$runnerArgs += "--publish-paper-results"

python -u @runnerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Incomplete July 1 batch resume failed with exit code $LASTEXITCODE"
}
