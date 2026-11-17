#!/usr/bin/env pwsh
<#
  Windows port of collect-logs.sh - dumps container logs + health into ./logs/
  for troubleshooting. Functionally identical to the bash version; see that
  file's comments for the "why". Run from PowerShell (Windows PowerShell 5.1+
  or PowerShell 7+):

      .\collect-logs.ps1
#>

# run.ps1 sets $ErrorActionPreference = "Stop" and calls this script with `&`, so the
# script inherits it. Under "Stop", the first native command that reports an error ends
# the whole collection: in Windows PowerShell 5.1 any stderr output from `docker logs`
# redirected with `*>` (mongot prints a Java warning) becomes a terminating error, and
# in PowerShell 7 a non-zero exit code can too. The remaining containers' logs, usually
# warden-ollama and warden-app, were then never written (#286). Collection is
# best-effort, so keep going and keep whatever each command printed. Run on its own
# the script already used "Continue"; install.ps1's RunNative relaxes the preference
# for the same reason.
$ErrorActionPreference = "Continue"

Set-Location -Path $PSScriptRoot

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
Write-Host "collecting logs into .\logs\  ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))"

$containers = @(
    "warden-mongod1", "warden-mongod2", "warden-mongod3", "warden-setup",
    "warden-mongot", "warden-ollama", "warden-ollama-pull", "warden-app"
)

foreach ($c in $containers) {
    # ${c} (not $c) before a literal ".log" - PowerShell string interpolation
    # would otherwise parse "$c.log" as member-access ($c.log) instead of
    # concatenation, and strings have no .log property.
    docker inspect $c *> $null
    if ($LASTEXITCODE -eq 0) {
        docker logs --tail 400 $c *> "logs\${c}.log"
    } else {
        "container $c not found" | Out-File -FilePath "logs\${c}.log" -Encoding utf8
    }
}

docker compose ps *> "logs\_status.txt"

try {
    # -ErrorAction Stop so the catch below still runs now that the script default is Continue.
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8001/api/status" -TimeoutSec 5 -ErrorAction Stop
    $resp.Content | Out-File -FilePath "logs\app_status.json" -Encoding utf8
} catch {
    "app unreachable" | Out-File -FilePath "logs\app_status.json" -Encoding utf8
}

Write-Host "done -> .\logs\"
