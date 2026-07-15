#!/usr/bin/env pwsh
<#
  Windows port of install.sh - no repo, no build. Pulls the published Docker Hub
  image and downloads only the handful of small config files needed to run it.
  Requires Docker Desktop with the `docker compose` CLI on PATH.

  One-liner (run from Command Prompt or PowerShell - both work, since this
  explicitly invokes powershell.exe rather than relying on the calling shell):

    powershell -c "irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"

  For the bundled (zero-cloud-accounts local demo) variant, since a piped `iex`
  can't take a -Bundled switch directly, set an env var first instead:

    powershell -c "$env:WARDENIQ_BUNDLED=1; irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"

  Prefer running it as a saved file instead of the download-and-execute pattern?

    iwr https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 -OutFile install.ps1
    .\install.ps1                # bring your own MongoDB (recommended)
    .\install.ps1 -Bundled       # also grab the all-local demo stack (bundled MongoDB + Ollama)

  If Windows blocks script execution, either run once via:
    powershell -ExecutionPolicy Bypass -File .\install.ps1
  or (as an admin, one-time) relax the policy for your user:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

  NOTE: this file must stay plain ASCII. Windows PowerShell 5.1 (the default
  powershell.exe on most Windows installs) does not reliably auto-detect UTF-8 in a
  .ps1 file that has no byte-order mark, and a raw download via Invoke-WebRequest /
  curl won't add one - so any non-ASCII character (em dashes, curly quotes, arrows,
  etc.) risks being misread as a different codepage and breaking the parser with
  errors like "Missing closing ')' in expression". Stick to -, ->, and "" instead.
#>
param(
    [switch]$Bundled = ($env:WARDENIQ_BUNDLED -eq "1"),
    [string]$Dest = "wardeniq",
    [string]$Tag = "beta"
)

$ErrorActionPreference = "Stop"
$RepoRaw = "https://raw.githubusercontent.com/adlerqa/wardeniq/main"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is required - install Docker Desktop first."
    exit 1
}

Write-Host "==> setting up wardenIQ in .\$Dest (pulling adlerqa/wardeniq:$Tag - no source needed)"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Set-Location -Path $Dest

function Fetch($relPath) {
    Invoke-WebRequest -Uri "$RepoRaw/$relPath" -OutFile $relPath
}

Fetch "docker-compose.app.yml"
Fetch ".env.example"

if ($Bundled) {
    Write-Host "==> also grabbing the bundled MongoDB/Ollama demo stack (config/ + compose files)"
    Fetch "docker-compose.yml"
    Fetch "docker-compose.mongodb.yml"
    Fetch "docker-compose.ollama.yml"
    New-Item -ItemType Directory -Force -Path "config" | Out-Null
    foreach ($f in @("mongod.conf", "mongot.conf", "pwfile", "mongot-entrypoint.sh", "setup-replica-set.sh")) {
        Invoke-WebRequest -Uri "$RepoRaw/config/$f" -OutFile "config/$f"
    }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    if (-not (Select-String -Path ".env" -Pattern '^APP_IMAGE=' -Quiet)) {
        Add-Content -Path ".env" -Value "APP_IMAGE=adlerqa/wardeniq:$Tag"
    }
    Write-Host "==> created .env - APP_SECRET is generated automatically on first boot, nothing to edit there"
} else {
    Write-Host "==> .env already exists, leaving it as-is"
}

if ($Bundled) {
    Write-Host "==> starting the full bundled demo stack (app + MongoDB + Ollama) - pulling images, not building"
    docker compose up -d
    Write-Host ""
    Write-Host "wardenIQ -> http://localhost:8001"
    Write-Host "First launch takes a few minutes (replica set init + model download)."
    Write-Host "Watch it come up: docker logs -f warden-app"
} else {
    Write-Host ""
    Write-Host "One thing left - this flow brings your own MongoDB (no bundled DB was downloaded)."
    Write-Host "Open $Dest\.env and set MONGO_URI to your database (e.g. a MongoDB Atlas connection string)."
    Write-Host "Then start it:"
    Write-Host ""
    Write-Host "    cd $Dest; docker compose -f docker-compose.app.yml up -d"
    Write-Host ""
    Write-Host "(Prefer the zero-cloud-accounts local demo instead? Re-run this installer with -Bundled.)"
}
