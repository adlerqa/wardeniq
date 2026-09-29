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
    [switch]$Reset,
    [string]$Db = $env:WARDENIQ_DB,
    [string]$MongoUri = $env:WARDENIQ_MONGO_URI
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

# mongot's password is NOT committed (config/pwfile is git-ignored). Generate a
# strong random one on first run; the setup container reads the SAME file so the
# two always match. Re-generate if it's still the old committed default.
$pwPath = Join-Path $PSScriptRoot "config/pwfile"
$curPw = if (Test-Path $pwPath) { (Get-Content $pwPath -Raw).Trim() } else { "" }
if (-not $curPw -or $curPw -eq "mongotPassword") {
    $bytes = New-Object 'System.Byte[]' 64
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $chars = ([char[]](48..57 + 65..90 + 97..122))
    $pw = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })[0..31]
    [IO.File]::WriteAllText($pwPath, $pw)
    Write-Host "==> generated a random mongot (search) password -> config/pwfile"
}

# -- first-start database/backend selection (#109) --------------------------
# Only ever prompts (and only ever writes .env below) on a genuinely fresh
# install: neither MONGO_URI nor COMPOSE_FILE is already pinned. This is the
# EXACT gate the kernel check further below already used pre-#109 - reusing it
# here (rather than inventing a new "already configured" signal) guarantees an
# existing installation is never re-prompted and never notices this change.
$freshDbInstall = (-not (Select-String -Path ".env" -Pattern '^MONGO_URI=.+' -Quiet -ErrorAction SilentlyContinue)) `
    -and (-not (Select-String -Path ".env" -Pattern '^COMPOSE_FILE=' -Quiet -ErrorAction SilentlyContinue))

if ($freshDbInstall) {
    # Same interactive/non-interactive pattern install.ps1 already established
    # (Ask/AskSecret/AskYesNo/$Interactive) - reused here, not reinvented.
    $Interactive = ([Environment]::UserInteractive) -and ($env:WARDENIQ_ASSUME_YES -ne "1")
    function Ask($q, $def) {
        if (-not $Interactive) { return $def }
        $suffix = if ($def) { " [$def]" } else { "" }
        $ans = Read-Host "$q$suffix"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $def } else { return $ans }
    }
    # Silent (no echo) - a MONGO_URI may embed credentials, so it must never hit
    # the terminal, shell history, or logs (see install.ps1's AskSecret).
    function AskSecret($q) {
        if (-not $Interactive) { return "" }
        $sec = Read-Host $q -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    function AskYesNo($q, $def) {
        $hint = if ($def -eq "y") { "Y/n" } else { "y/N" }
        $ans = (Ask "$q ($hint)" $def).ToLower()
        switch ($ans) { "y" { $true } "yes" { $true } "n" { $false } "no" { $false } default { $def -eq "y" } }
    }
    function MongoUriFormatOk($u) {
        return ($u -match '^mongodb(\+srv)?://')
    }
    # 0 = connected, 1 = failed to connect, 2 = can't check (no mongosh - not an error).
    function MongoUriReachable($u) {
        if (-not (Get-Command mongosh -ErrorAction SilentlyContinue)) { return 2 }
        $job = Start-Job -ScriptBlock {
            param($uri) & mongosh $uri --quiet --eval "db.adminCommand('ping')" *> $null
            $LASTEXITCODE
        } -ArgumentList $u
        if (Wait-Job $job -Timeout 10) {
            $code = Receive-Job $job
            Remove-Job $job -Force
            if ($code -eq 0) { return 0 } else { return 1 }
        } else {
            Stop-Job $job; Remove-Job $job -Force
            return 1
        }
    }
    function SetEnv($k, $v) {
        if (-not (Test-Path ".env")) { New-Item -ItemType File -Path ".env" | Out-Null }
        $lines = @(Get-Content ".env" | Where-Object { $_ -notmatch "^$k=" })
        $lines += "$k=$v"
        Set-Content -Path ".env" -Value $lines
    }

    $dbChoice = $Db
    if (-not $dbChoice) {
        if ($Interactive) {
            Write-Host ""
            Write-Host "No existing wardenIQ database configuration was detected."
            Write-Host ""
            Write-Host "Choose your database:"
            Write-Host ""
            Write-Host "  1) MongoDB Community Server (bundled, default)"
            Write-Host "  2) Percona Server for MongoDB + Percona Search (bundled, technical preview - see #27, #41)"
            Write-Host "  3) Use an existing MongoDB-compatible database"
            Write-Host ""
            while (-not $dbChoice) {
                switch (Ask "Select [1-3]" "1") {
                    "1" { $dbChoice = "community" }
                    "2" { $dbChoice = "percona" }
                    "3" { $dbChoice = "external" }
                    default { Write-Host "Please enter 1, 2, or 3." }
                }
            }
        } else {
            $dbChoice = "community"   # non-interactive, no -Db/WARDENIQ_DB: friendliest zero-config default
        }
    }

    switch ($dbChoice) {
        "community" {
            # unchanged current behavior - MONGO_URI stays unset, falls back to MONGO_URI_BUNDLED
        }
        "percona" {
            Write-Host "==> Percona is a technical preview: it does NOT avoid the kernel >= 6.19"
            Write-Host "    limitation below (see #27, #41, docs/percona-search-validation.md)."
            $perconaPwPath = Join-Path $PSScriptRoot "config/pwfile-percona"
            $curPerconaPw = if (Test-Path $perconaPwPath) { (Get-Content $perconaPwPath -Raw).Trim() } else { "" }
            if (-not $curPerconaPw) {
                $bytes = New-Object 'System.Byte[]' 64
                [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
                $chars = ([char[]](48..57 + 65..90 + 97..122))
                $pw = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })[0..31]
                [IO.File]::WriteAllText($perconaPwPath, $pw)
                Write-Host "==> generated a random Percona mongot (search) password -> config/pwfile-percona"
            }
            SetEnv "MONGO_URI" "mongodb://mongod-percona:27017/?replicaSet=rs0"
            SetEnv "COMPOSE_FILE" "docker-compose.app.yml:docker-compose.mongodb-percona.yml:docker-compose.ollama.yml"
        }
        "external" {
            $uri = $MongoUri
            if (-not $uri -and $Interactive) {
                Write-Host "Paste your MongoDB connection string (needs Vector Search - Atlas M10+ or self-managed mongot)."
                while ($true) {
                    $uri = Ask "MONGO_URI" ""
                    if (-not $uri) { break }
                    if (-not (MongoUriFormatOk $uri)) {
                        Write-Host "that doesn't look like a MongoDB connection string - it must start with mongodb:// or mongodb+srv://"
                        continue
                    }
                    Write-Host "checking the connection..."
                    $rc = MongoUriReachable $uri
                    if ($rc -eq 0) { Write-Host "connected OK"; break }
                    elseif ($rc -eq 2) { Write-Host "(mongosh not found on this machine - skipping the live connection check; format looks OK)"; break }
                    else {
                        Write-Host "could not connect using that URI (wrong host/user/password, IP not allow-listed, cluster paused, etc)."
                        if (AskYesNo "Use it anyway?" "n") { break }
                    }
                }
            } elseif ($uri -and -not (MongoUriFormatOk $uri)) {
                Write-Host "==> WARDENIQ_MONGO_URI doesn't look like a valid MongoDB connection string (must start with mongodb:// or mongodb+srv://) - saving it as given since this is a non-interactive run, but the app will fail to start until it's fixed."
            }
            if ($uri) { SetEnv "MONGO_URI" $uri }
            else { Write-Host "==> no MONGO_URI provided - set it in .env before wardenIQ will start." }
            SetEnv "COMPOSE_FILE" "docker-compose.app.yml:docker-compose.ollama.yml"
            SetEnv "OLLAMA_URL_BUNDLED" "http://host.docker.internal:11434"
        }
        default {
            Write-Host "==> invalid WARDENIQ_DB value: '$dbChoice' (expected community, percona, or external)"
            exit 1
        }
    }
}

# Compose file selection. docker-compose.yml uses `include:`, which needs Compose
# v2.20+. To work on ANY Compose v2, pass the three service files explicitly - unless
# .env pins COMPOSE_FILE (e.g. after the first-start selection above, or
# scripts/enable-mongo-auth.sh), then honour that.
if (Select-String -Path ".env" -Pattern '^COMPOSE_FILE=' -Quiet -ErrorAction SilentlyContinue) {
    $Compose = @("compose")
} else {
    $Compose = @("compose", "-f", "docker-compose.app.yml", "-f", "docker-compose.mongodb.yml", "-f", "docker-compose.ollama.yml")
}

# Fail fast on a kernel MongoDB's tcmalloc allocator refuses to start on (see #27).
# Applies to EITHER bundled MongoDB profile (Community or Percona - Docker Desktop
# on Windows runs Linux containers inside a Linux VM, and `docker info`'s
# KernelVersion below reports THAT VM's kernel - exactly what MongoDB's tcmalloc
# allocator actually runs against - so this check is just as meaningful on Windows
# as on Linux/macOS; it is not a Unix-only concern, which is why run.ps1 already
# carried a port of it before #109. The Percona validation in #41/PR #105
# confirmed Percona's mongod hits the identical tcmalloc failure, so choosing
# Percona must not silently skip this check just because it also sets MONGO_URI.
# Only a genuine bring-your-own MONGO_URI (no bundled compose file pinned) skips
# it, since that database isn't started here.
$perconaPinned = $false
if (Select-String -Path ".env" -Pattern '^COMPOSE_FILE=' -Quiet -ErrorAction SilentlyContinue) {
    $composeFileLine = (Select-String -Path ".env" -Pattern '^COMPOSE_FILE=.*' -ErrorAction SilentlyContinue | Select-Object -First 1).Line
    if ($composeFileLine -match 'docker-compose\.mongodb-percona\.yml') { $perconaPinned = $true }
}
$mongoUriSet = Select-String -Path ".env" -Pattern '^MONGO_URI=.+' -Quiet -ErrorAction SilentlyContinue
if ($perconaPinned -or (-not $mongoUriSet)) {
    $kernelVersion = ""
    try { $kernelVersion = (docker info --format '{{.KernelVersion}}' 2>$null) } catch {}
    if ($kernelVersion -match '^(\d+)\.(\d+)') {
        $kMajor = [int]$Matches[1]
        $kMinor = [int]$Matches[2]
        if (($kMajor -gt 6) -or (($kMajor -eq 6) -and ($kMinor -ge 19))) {
            Write-Host "==> refusing to start: Docker's Linux kernel is $kernelVersion"
            Write-Host "    MongoDB's tcmalloc allocator has a known startup failure on kernel >= 6.19"
            Write-Host "    (see https://github.com/adlerqa/wardeniq/issues/27 for the full analysis)."
            Write-Host "    The bundled local stack cannot run on this Docker install today."
            Write-Host ""
            Write-Host "    Supported alternative: bring your own MongoDB. Set MONGO_URI in .env"
            Write-Host "    (Atlas, or a self-managed replica set with mongot) and run this script again."
            exit 1
        }
    }
}

if ($Reset) {
    Write-Host "==> wiping volumes"
    docker @Compose down -v --remove-orphans
}

Write-Host "==> building + starting wardenIQ"
docker @Compose up -d --build

# Readiness gate: don't report success until the app actually answers, not just
# "started". Polls the same public boot-status endpoint the sign-in screen
# uses (never returns raw driver errors - see #34/#44).
Write-Host "==> waiting for wardenIQ to become ready (replica set + model pulls can take a few minutes)"
$ready = $false
$deadline = (Get-Date).AddSeconds(300)
$lastStatus = "no response from http://localhost:8001"
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8001/api/auth/boot-status" -TimeoutSec 5
        $lastStatus = $resp | ConvertTo-Json -Compress
        if ($resp.ready -eq $true) {
            $ready = $true
            break
        }
    } catch {
        # app not answering yet - keep polling
    }
    Start-Sleep -Seconds 5
}

try {
    & "$PSScriptRoot\collect-logs.ps1"
} catch {
    # best-effort, mirrors `./collect-logs.sh || true` in run.sh
    Write-Host "log collection failed: $_"
}

if (-not $ready) {
    Write-Host ""
    Write-Host "==> wardenIQ did not become ready within 5 minutes."
    Write-Host "    Last boot status: $lastStatus"
    Write-Host ""
    Write-Host "--- docker logs warden-app (last 50 lines) ---"
    docker logs --tail 50 warden-app
    Write-Host ""
    Write-Host "--- docker logs warden-mongod1 (last 50 lines) ---"
    docker logs --tail 50 warden-mongod1
    Write-Host ""
    Write-Host "Full logs also captured in .\logs\"
    exit 1
}

Write-Host ""
Write-Host "wardenIQ -> http://localhost:8001"
Write-Host "Logs captured in .\logs\"
