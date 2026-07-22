<#
  wardenIQ interactive installer (Windows) - no repo, no build. Pulls the published
  Docker Hub image and downloads only the small config files needed to run it, then
  guides you through the few choices that matter and starts the stack for you.
  Requires Docker Desktop with the `docker compose` CLI on PATH.

  One-liner (Command Prompt or PowerShell):
    powershell -c "irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"

  Run as a saved file to get the interactive prompts reliably:
    iwr https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 -OutFile install.ps1
    .\install.ps1
    .\install.ps1 -Bundled        # force the all-in-one demo
    .\install.ps1 -Mode byo -MongoUri "mongodb+srv://..."   # non-interactive

  Env (optional, for fully non-interactive / CI): WARDENIQ_MODE (bundled|byo),
  WARDENIQ_MONGO_URI, WARDENIQ_ADMIN_PASSWORD, WARDENIQ_WIPE (yes|no),
  WARDENIQ_ASSUME_YES=1, WARDENIQ_DIR, WARDENIQ_TAG.

  NOTE: this file must stay plain ASCII (Windows PowerShell 5.1 reads a BOM-less
  UTF-8 .ps1 as the local codepage). Use -, ->, and "" only - no smart quotes/arrows.
#>
param(
    [switch]$Bundled = ($env:WARDENIQ_BUNDLED -eq "1"),
    [string]$Mode = $env:WARDENIQ_MODE,
    [string]$MongoUri = $env:WARDENIQ_MONGO_URI,
    [string]$AdminPassword = $env:WARDENIQ_ADMIN_PASSWORD,
    [string]$Wipe = $env:WARDENIQ_WIPE,
    [string]$Dest = $(if ($env:WARDENIQ_DIR) { $env:WARDENIQ_DIR } else { "wardeniq" }),
    [string]$Tag = $(if ($env:WARDENIQ_TAG) { $env:WARDENIQ_TAG } else { "latest" })
)

$ErrorActionPreference = "Stop"
$RepoRaw = "https://raw.githubusercontent.com/adlerqa/wardeniq/main"
$AppImageRef = "adlerqa/wardeniq:$Tag"
$AssumeYes = ($env:WARDENIQ_ASSUME_YES -eq "1")
$Interactive = ([Environment]::UserInteractive) -and (-not $AssumeYes)

function Say($m)  { Write-Host "==> $m" -ForegroundColor Green }
function Info($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "xx $m" -ForegroundColor Red; exit 1 }

# RunNative { scriptblock } -> runs a native command (docker, docker compose, ...)
# with $ErrorActionPreference temporarily relaxed, then restores it. Needed
# because with the script's global $ErrorActionPreference = "Stop", ANY stderr
# output from a native command becomes an unhandled terminating error -- even
# on success. docker/docker compose routinely print benign lines to stderr
# (blkio/cgroup warnings on `docker info`, pull progress, compose status), which
# previously crashed the installer outright (or, wrapped in try/catch, made a
# working Docker daemon look broken). $LASTEXITCODE still reflects the command's
# real exit code afterward -- callers check that for actual failures.
function RunNative([scriptblock]$Cmd) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try { & $Cmd } finally { $ErrorActionPreference = $prevEap }
}

function Ask($q, $def) {
    if (-not $Interactive) { return $def }
    $suffix = if ($def) { " [$def]" } else { "" }
    $ans = Read-Host "$q$suffix"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $def } else { return $ans }
}
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
function Rand($n) {
    $bytes = New-Object 'System.Byte[]' ($n * 2)
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $chars = ([char[]](48..57 + 65..90 + 97..122))  # 0-9 A-Z a-z
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })[0..($n - 1)]
}
function PasswordPolicyOk($p) {
    if ($p.Length -lt 8) { return $false }
    if ($p -notmatch '[A-Za-z]') { return $false }
    if ($p -notmatch '[0-9]') { return $false }
    if ($p.ToLower() -eq "admin123") { return $false }
    return $true
}
function SetEnv($k, $v) {
    if (-not (Test-Path ".env")) { New-Item -ItemType File -Path ".env" | Out-Null }
    $lines = @(Get-Content ".env" | Where-Object { $_ -notmatch "^$k=" })
    $lines += "$k=$v"
    Set-Content -Path ".env" -Value $lines
}
# MongoUriFormatOk "uri" -> $true if it at least LOOKS like a Mongo connection
# string (mongodb:// or mongodb+srv:// scheme). Catches plain typos/placeholders
# (e.g. pasting a random word) before they're ever saved to .env.
function MongoUriFormatOk($u) {
    return ($u -match '^mongodb(\+srv)?://')
}
# MongoUriReachable "uri" -> 0 connected OK, 1 failed, 2 can't check (no mongosh
# on this machine - not an error). Best-effort only, ~10s cap: network access
# from this machine may legitimately differ from the container's (e.g. an Atlas
# IP allow-list that includes the server's IP but not this laptop's).
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

# -- pre-flight --------------------------------------------------------------
# NOTE: native docker calls are run via RunNative (see above), which relaxes
# $ErrorActionPreference for the duration of the call. Under this script's
# global $ErrorActionPreference = "Stop", ANY stderr output from a native
# command -- even on PowerShell 5.1, not just PS7's
# $PSNativeCommandUseErrorActionPreference -- is treated as a terminating
# error. `docker info` routinely prints benign WARNING lines to stderr (blkio
# support, cgroup v1 deprecation, etc.) even when it succeeds, which previously
# either tripped a try/catch (misreporting "daemon isn't running" for a daemon
# that was fine) or, once try/catch was removed, crashed the script outright
# with an unhandled NativeCommandError. $LASTEXITCODE still reflects the real
# exit code and is what's checked below.
Say "wardenIQ installer"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die "Docker is required - install Docker Desktop first." }
RunNative { docker compose version *> $null }
if ($LASTEXITCODE -ne 0) { Die "Docker Compose v2 is required (comes with Docker Desktop)." }
RunNative { docker info *> $null }
if ($LASTEXITCODE -ne 0) { Die "Docker is installed but the daemon isn't running - start Docker Desktop and re-run." }

# -- deployment mode ---------------------------------------------------------
if ($Bundled) { $Mode = "bundled" }
if (-not $Mode) {
    if ($Interactive) {
        Info "How do you want to run wardenIQ?"
        Info "  1) All-in-one demo   - bundled MongoDB + search + Ollama (zero accounts, heavier)"
        Info "  2) Bring your own DB - just the app; you supply a MongoDB URI (e.g. Atlas)"
        if ((Ask "Choose 1 or 2" "1") -match '^(2|b|byo)$') { $Mode = "byo" } else { $Mode = "bundled" }
    } else { $Mode = "bundled" }
}
Say "mode: $Mode"

Say "setting up in .\$Dest  (published image $AppImageRef - no source needed)"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Set-Location -Path $Dest

function Fetch($rel) { Invoke-WebRequest -Uri "$RepoRaw/$rel" -OutFile $rel }

# -- fetch what the mode needs -----------------------------------------------
Fetch "docker-compose.app.yml"
Fetch ".env.example"
if ($Mode -eq "bundled") {
    Info "downloading the bundled MongoDB/Ollama stack (config/ + compose files)"
    Fetch "docker-compose.yml"
    Fetch "docker-compose.mongodb.yml"
    Fetch "docker-compose.ollama.yml"
    New-Item -ItemType Directory -Force -Path "config" | Out-Null
    foreach ($f in @("mongod.conf", "mongot.conf", "mongot-entrypoint.sh", "setup-replica-set.sh")) {
        Invoke-WebRequest -Uri "$RepoRaw/config/$f" -OutFile "config/$f"
    }
}

# -- existing install? keep or wipe ------------------------------------------
$DoWipe = "no"
$existing = (docker ps -aq --filter "name=warden-" 2>$null)
if ($existing) {
    Warn "an existing wardenIQ install was detected (warden-* containers)."
    if ($Wipe) { $DoWipe = $Wipe }
    elseif ($Interactive) {
        if (AskYesNo "Wipe ALL existing data (database + downloaded models) for a clean start?" "n") { $DoWipe = "yes" }
    }
    if ($DoWipe -eq "yes") { Warn "will WIPE data volumes." } else { Info "keeping existing data volumes." }
}

# -- .env: create + app image + secrets --------------------------------------
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Say "created .env" }
else { Info ".env already exists - updating only the values you choose" }
if (-not (Select-String -Path ".env" -Pattern '^APP_IMAGE=' -Quiet)) { SetEnv "APP_IMAGE" $AppImageRef }

$curSecret = (Select-String -Path ".env" -Pattern '^APP_SECRET=(.*)$').Matches.Groups[1].Value
if ($curSecret -in @("", "change-me-in-production", "change-me", "changeme", "mongoT-qa-dev-key-change-me")) {
    SetEnv "APP_SECRET" (Rand 48); Info "generated a strong APP_SECRET"
}

# -- bring-your-own MongoDB --------------------------------------------------
if ($Mode -eq "byo") {
    $uri = $MongoUri
    if (-not $uri -and $Interactive) {
        Info "Paste your MongoDB connection string (needs Vector Search - Atlas M10+ or self-managed mongot)."
        while ($true) {
            $uri = Ask "MONGO_URI" ""
            if (-not $uri) { break }
            if (-not (MongoUriFormatOk $uri)) {
                Warn "that doesn't look like a MongoDB connection string - it must start with mongodb:// or mongodb+srv://"
                continue
            }
            Info "checking the connection..."
            $rc = MongoUriReachable $uri
            if ($rc -eq 0) { Info "connected OK"; break }
            elseif ($rc -eq 2) { Info "(mongosh not found on this machine - skipping the live connection check; format looks OK)"; break }
            else {
                Warn "could not connect using that URI (wrong host/user/password, IP not allow-listed, cluster paused, etc)."
                if (AskYesNo "Use it anyway?" "n") { break }
            }
        }
    } elseif ($uri -and -not (MongoUriFormatOk $uri)) {
        Warn "WARDENIQ_MONGO_URI doesn't look like a valid MongoDB connection string (must start with mongodb:// or mongodb+srv://) - saving it as given since this is a non-interactive run, but the app will fail to start until it's fixed."
    }
    if ($uri) { SetEnv "MONGO_URI" $uri; Info "MONGO_URI saved to .env" }
    else { Warn "no MONGO_URI provided - set it in $Dest\.env before the app will start." }
    SetEnv "OLLAMA_URL_BUNDLED" "http://host.docker.internal:11434"
} else {
    SetEnv "OLLAMA_URL_BUNDLED" "http://ollama:11434"
}

# -- admin password (replaces admin123) --------------------------------------
$adminPw = $AdminPassword
if (-not $adminPw -and $Interactive) {
    Info "Set the first admin's login password (username: admin). Policy: >=8 chars, a letter and a number."
    Info "Leave blank to keep the default admin123 (forced change on first login)."
    while ($true) {
        $p1 = AskSecret "Admin password (blank = default)"
        if ([string]::IsNullOrEmpty($p1)) { break }
        if (-not (PasswordPolicyOk $p1)) { Warn "must be >=8 chars, include a letter and a number, and not be 'admin123'."; continue }
        $p2 = AskSecret "Confirm password"
        if ($p1 -eq $p2) { $adminPw = $p1; break } else { Warn "passwords didn't match - try again." }
    }
}
if ($adminPw) {
    if (PasswordPolicyOk $adminPw) { SetEnv "ADMIN_PASSWORD" $adminPw; Info "admin password set (admin123 will be disabled)" }
    else { Warn "provided admin password fails policy - leaving the default (forced change on first login)." }
}

# -- mongot search password (bundled only) - random, never committed ---------
if ($Mode -eq "bundled") {
    $pwPath = "config/pwfile"
    $cur = if (Test-Path $pwPath) { (Get-Content $pwPath -Raw).Trim() } else { "" }
    if (-not $cur -or $cur -eq "mongotPassword") {
        [IO.File]::WriteAllText((Resolve-Path -LiteralPath . ).Path + "\$pwPath", (Rand 32))
        Info "generated a random mongot (search) password -> config/pwfile"
    } else { Info "keeping existing config/pwfile mongot password" }
}

# -- compose selection -------------------------------------------------------
# Pass service files explicitly rather than relying on docker-compose.yml's `include:`
# (needs Compose v2.20+), so this works on any Compose v2.
if ($Mode -eq "bundled") {
    $Compose = @("compose", "-f", "docker-compose.app.yml", "-f", "docker-compose.mongodb.yml", "-f", "docker-compose.ollama.yml")
} else {
    $Compose = @("compose", "-f", "docker-compose.app.yml")
}

# -- cleanup previous run + pull fresh ---------------------------------------
# All of these go through RunNative (see helper near the top): docker/compose
# routinely write status/progress lines to stderr, which -- even redirected
# with `2>$null` or `*>$null` -- still get promoted to a terminating
# NativeCommandError under this script's $ErrorActionPreference = "Stop".
# Redirection alone does not prevent that; only relaxing $ErrorActionPreference
# for the duration of the call does.
Say "cleaning up any previous wardenIQ containers"
if ($DoWipe -eq "yes") { RunNative { docker @Compose down -v --remove-orphans *>$null } }
else { RunNative { docker @Compose down --remove-orphans *>$null } }

Say "pulling fresh images"
RunNative { docker pull $AppImageRef *>$null }
if ($LASTEXITCODE -ne 0) { Warn "could not pull $AppImageRef (will fall back to any local image / build)." }
RunNative { docker @Compose pull *>$null }

# -- start -------------------------------------------------------------------
$hasUri = (Select-String -Path ".env" -Pattern '^MONGO_URI=..*' -Quiet)
if ($Mode -eq "byo" -and -not $hasUri) {
    Write-Host ""
    Say "setup complete, but no MONGO_URI is set yet."
    Info "Edit $Dest\.env -> set MONGO_URI, then start it:"
    Info "    cd $Dest; docker compose -f docker-compose.app.yml up -d --no-build --pull always"
    exit 0
}

Say "starting wardenIQ"
RunNative { docker @Compose up -d --no-build --pull always *>$null }
if ($LASTEXITCODE -ne 0) { Die "docker compose up failed - run 'docker compose -f docker-compose.app.yml up -d' manually to see the full error." }

Write-Host ""
Say "wardenIQ -> http://localhost:8001"
if ($Mode -eq "bundled") { Info "First launch takes a few minutes (replica-set init + model download)." }
Info "Sign in as admin with the password you set."
Info "Watch it come up:  docker logs -f warden-app"
