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
        # 2>&1 + ToString() instead of `*>`: in Windows PowerShell 5.1 a native command's
        # stderr, once redirected, arrives as ErrorRecord objects and `*>` writes each
        # one as a full "NativeCommandError / CategoryInfo / At line:" block into the
        # log. ToString() keeps just the text the container printed (follow-up to #286).
        docker logs --tail 400 $c 2>&1 | ForEach-Object { $_.ToString() } |
            Out-File -FilePath "logs\${c}.log" -Encoding utf8
    } else {
        "container $c not found" | Out-File -FilePath "logs\${c}.log" -Encoding utf8
    }
}

docker compose ps 2>&1 | ForEach-Object { $_.ToString() } | Out-File -FilePath "logs\_status.txt" -Encoding utf8

# /api/status needs a login, so an unauthenticated request got a 401 and this file
# said "app unreachable" for an app that was up. /api/auth/boot-status is public and
# reports the startup stage ("indexing", "ready", ...), which is what a bug report
# needs. A request that gets an HTTP error is recorded with its status code; only a
# request that gets no answer at all is "unreachable" (follow-up to #286).
try {
    # -ErrorAction Stop so the catch below still runs now that the script default is Continue.
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8001/api/auth/boot-status" -TimeoutSec 5 -ErrorAction Stop
    $resp.Content | Out-File -FilePath "logs\app_status.json" -Encoding utf8
} catch {
    $ex = $_.Exception
    $code = $null
    if ($ex.Response) { try { $code = [int]$ex.Response.StatusCode } catch { $code = $null } }
    if ($code) {
        "app answered with HTTP $code" | Out-File -FilePath "logs\app_status.json" -Encoding utf8
    } else {
        "app unreachable" | Out-File -FilePath "logs\app_status.json" -Encoding utf8
    }
}

Write-Host "done -> .\logs\"
