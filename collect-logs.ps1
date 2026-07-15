#!/usr/bin/env pwsh
<#
  Windows port of collect-logs.sh - dumps container logs + health into ./logs/
  for troubleshooting. Functionally identical to the bash version; see that
  file's comments for the "why". Run from PowerShell (Windows PowerShell 5.1+
  or PowerShell 7+):

      .\collect-logs.ps1
#>

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
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8001/api/status" -TimeoutSec 5
    $resp.Content | Out-File -FilePath "logs\app_status.json" -Encoding utf8
} catch {
    "app unreachable" | Out-File -FilePath "logs\app_status.json" -Encoding utf8
}

Write-Host "done -> .\logs\"
