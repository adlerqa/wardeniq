#!/usr/bin/env pwsh
<#
  Windows port of run.sh - builds + starts the full stack, then captures logs.
  Functionally identical to the bash version (see run.sh's comments); this
  exists so Windows users don't need WSL2 or Git Bash. Requires Docker
  Desktop with the `docker compose` CLI on PATH.

    .\run.ps1            build + start
    .\run.ps1 -Reset     wipe data volumes first (fresh replica set + DB)

  If Windows blocks script execution, either run once via:
    powershell -ExecutionPolicy Bypass -File .\run.ps1
  or (as an admin, one-time) relax the policy for your user:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

  NOTE: this file must stay plain ASCII - see install.ps1's header comment for why
  (Windows PowerShell 5.1 mis-parses non-ASCII characters in a BOM-less .ps1 file).
#>
param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "creating .env from .env.example (edit APP_SECRET!)"
    Copy-Item ".env.example" ".env"
}

# No chmod step here (unlike run.sh): mongot's password file needs 0400 perms,
# but Windows bind mounts can't express that anyway. config/mongot-entrypoint.sh
# already copies the secret to a private, owner-only path INSIDE the container
# and re-secures it there - see that file's comments - so this is a non-issue
# on Windows (and macOS) regardless of host-side permissions.

if ($Reset) {
    Write-Host "==> wiping volumes"
    docker compose down -v --remove-orphans
}

Write-Host "==> building + starting wardenIQ"
docker compose up -d --build

Write-Host "==> waiting for services to settle (replica set + model pulls can take a few minutes)"
Start-Sleep -Seconds 45

try {
    & "$PSScriptRoot\collect-logs.ps1"
} catch {
    # best-effort, mirrors `./collect-logs.sh || true` in run.sh
    Write-Host "log collection failed: $_"
}

Write-Host ""
Write-Host "wardenIQ -> http://localhost:8001"
Write-Host "Logs captured in .\logs\"
