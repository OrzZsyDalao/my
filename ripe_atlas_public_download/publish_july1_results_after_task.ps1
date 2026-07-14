<#
Wait for a named Windows scheduled pipeline task to finish successfully, then
package and publish only the compact paper-facing CSV bundle.
#>

param(
    [string]$PipelineTaskName = "Infocom26July1FullPipeline",
    [int]$PollSeconds = 300
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

while ($true) {
    $task = Get-ScheduledTask -TaskName $PipelineTaskName
    $info = Get-ScheduledTaskInfo -TaskName $PipelineTaskName
    if ($task.State -ne "Running") {
        if ($info.LastTaskResult -ne 0) {
            throw "Pipeline task ended with result $($info.LastTaskResult); result bundle was not published."
        }
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

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
