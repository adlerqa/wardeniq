#!/usr/bin/env bash
# wardenIQ interactive installer — no repo, no build. Pulls the published Docker Hub
# image and downloads only the handful of small config files needed to run it, then
# guides you through the few choices that matter and starts the stack for you.
#
#   curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash
#
# It reads your answers from the terminal (/dev/tty) even when run via `curl | bash`.
# Fully non-interactive / CI use: set the WARDENIQ_* env vars below and it won't prompt.
#
# Env (all optional):
#   WARDENIQ_DIR=wardeniq         install directory
#   WARDENIQ_TAG=beta             image tag (adlerqa/wardeniq:<tag>)
#   WARDENIQ_MODE=bundled|byo     bundled all-in-one demo, or bring-your-own MongoDB
#   WARDENIQ_MONGO_URI=...        your MongoDB URI (byo mode)
#   WARDENIQ_ADMIN_PASSWORD=...   bootstrap admin password (>=8 chars, letter+number)
#   WARDENIQ_WIPE=yes|no          on re-install, wipe existing data volumes (default no)
#   WARDENIQ_ASSUME_YES=1         accept all defaults, never prompt
# Legacy: passing --bundled still forces bundled mode.
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/adlerqa/wardeniq/main"
DEST="${WARDENIQ_DIR:-wardeniq}"
TAG="${WARDENIQ_TAG:-beta}"
APP_IMAGE_REF="adlerqa/wardeniq:${TAG}"

MODE="${WARDENIQ_MODE:-}"
for arg in "${@:-}"; do
  case "$arg" in
    --bundled) MODE="bundled" ;;
    "") ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

# ── tiny UI helpers (prompt from the real terminal so `curl | bash` still works) ──
c_bold=$'\033[1m'; c_dim=$'\033[2m'; c_grn=$'\033[32m'; c_ylw=$'\033[33m'; c_red=$'\033[31m'; c_rst=$'\033[0m'
say()  { printf '%s==>%s %s\n' "$c_grn$c_bold" "$c_rst" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s!! %s%s\n' "$c_ylw" "$*" "$c_rst" >&2; }
die()  { printf '%sxx %s%s\n' "$c_red" "$*" "$c_rst" >&2; exit 1; }

TTY=""; [ -r /dev/tty ] && TTY="/dev/tty"
ASSUME_YES="${WARDENIQ_ASSUME_YES:-0}"
interactive() { [ -n "$TTY" ] && [ "$ASSUME_YES" != "1" ]; }

# ask "Question" "default"  → prints the chosen value on stdout
ask() {
  local q="$1" def="${2:-}" ans=""
  if interactive; then
    printf '%s%s%s%s ' "$c_bold" "$q" "$c_rst" "${def:+ [$def]}" > "$TTY"
    IFS= read -r ans < "$TTY" || true
  fi
  printf '%s' "${ans:-$def}"
}
# ask_secret "Question"  → silent, returns typed value (no default)
ask_secret() {
  local q="$1" ans=""
  if interactive; then
    printf '%s%s%s ' "$c_bold" "$q" "$c_rst" > "$TTY"
    IFS= read -rs ans < "$TTY" || true
    printf '\n' > "$TTY"
  fi
  printf '%s' "$ans"
}
# ask_yesno "Question" "y|n"  → returns 0 for yes, 1 for no
ask_yesno() {
  local q="$1" def="${2:-n}" ans
  ans="$(ask "$q ($( [ "$def" = y ] && echo 'Y/n' || echo 'y/N'))" "$def")"
  ans="$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')"
  case "$ans" in y|yes) return 0 ;; n|no) return 1 ;; *) [ "$def" = y ] ;; esac
}
rand() {  # rand N → N random alphanumeric chars
  local n="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 $((n * 2)) | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "$n"
  else
    LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$n"
  fi
}
# password_policy_ok "pw" → 0 if acceptable, else 1 (mirrors app/auth.py policy)
password_policy_ok() {
  local p="$1"
  [ "${#p}" -ge 8 ] || return 1
  printf '%s' "$p" | grep -q '[A-Za-z]' || return 1
  printf '%s' "$p" | grep -q '[0-9]' || return 1
  [ "$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')" != "admin123" ] || return 1
}
# mongo_uri_format_ok "uri" → 0 if it at least LOOKS like a Mongo connection string
# (mongodb:// or mongodb+srv:// scheme). Catches plain typos/placeholders (e.g.
# pasting a random word) before they're ever saved to .env.
mongo_uri_format_ok() {
  case "$1" in
    mongodb://*|mongodb+srv://*) return 0 ;;
    *) return 1 ;;
  esac
}
# mongo_uri_reachable "uri" → 0 if a live connection actually succeeds, 1 if it
# fails, 2 if we can't check at all (no mongosh on this host — not an error).
# Best-effort only: a short timeout, never blocks setup, and network access from
# this host may legitimately differ from the container's (e.g. an Atlas IP
# allow-list that includes the server's IP but not this laptop's).
mongo_uri_reachable() {
  command -v mongosh >/dev/null 2>&1 || return 2
  mongosh "$1" --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1 &
  local pid=$! i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -ge 100 ] && { kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; return 1; }  # ~10s
    sleep 0.1
  done
  wait "$pid"
}
# set_env KEY VALUE  → replace-or-append literally (no sed escaping surprises)
set_env() {
  local k="$1"; shift; local v="$*"
  [ -f .env ] || : > .env
  grep -v "^${k}=" .env > .env.tmp 2>/dev/null || true
  mv .env.tmp .env
  printf '%s=%s\n' "$k" "$v" >> .env
}

# ── pre-flight ──────────────────────────────────────────────────────────────
say "wardenIQ installer"
command -v docker >/dev/null 2>&1 || die "Docker is required — install Docker Desktop first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (comes with Docker Desktop)."
docker info >/dev/null 2>&1 || die "Docker is installed but the daemon isn't running — start Docker Desktop and re-run."

# ── choose deployment mode ──────────────────────────────────────────────────
if [ -z "$MODE" ]; then
  if interactive; then
    info "How do you want to run wardenIQ?"
    info "  1) All-in-one demo   — bundled MongoDB + search + Ollama (zero accounts, heavier)"
    info "  2) Bring your own DB — just the app; you supply a MongoDB URI (e.g. Atlas)"
    case "$(ask 'Choose 1 or 2' '1')" in
      2|byo|b) MODE="byo" ;; *) MODE="bundled" ;;
    esac
  else
    MODE="bundled"   # friendliest zero-config default for non-interactive runs
  fi
fi
say "mode: ${c_bold}${MODE}${c_rst}"

say "setting up in ./$DEST  (published image ${APP_IMAGE_REF} — no source needed)"
mkdir -p "$DEST"; cd "$DEST"

fetch() { curl -fsSL "$REPO_RAW/$1" -o "$1"; }

# ── fetch just what the chosen mode needs ───────────────────────────────────
fetch docker-compose.app.yml
fetch .env.example
if [ "$MODE" = "bundled" ]; then
  info "downloading the bundled MongoDB/Ollama stack (config/ + compose files)"
  fetch docker-compose.yml
  fetch docker-compose.mongodb.yml
  fetch docker-compose.ollama.yml
  mkdir -p config
  for f in mongod.conf mongot.conf mongot-entrypoint.sh setup-replica-set.sh; do
    curl -fsSL "$REPO_RAW/config/$f" -o "config/$f"
  done
  chmod +x config/setup-replica-set.sh config/mongot-entrypoint.sh
fi

# ── existing install? keep or wipe ──────────────────────────────────────────
WIPE="no"
existing="$(docker ps -aq --filter 'name=warden-' 2>/dev/null || true)"
if [ -n "$existing" ]; then
  warn "an existing wardenIQ install was detected (warden-* containers)."
  if [ -n "${WARDENIQ_WIPE:-}" ]; then
    WIPE="$WARDENIQ_WIPE"
  elif interactive; then
    if ask_yesno "Wipe ALL existing data (database + downloaded models) for a clean start?" "n"; then
      WIPE="yes"
    fi
  fi
  [ "$WIPE" = "yes" ] && warn "will WIPE data volumes." || info "keeping existing data volumes."
fi

# ── .env: create + app image + secrets ──────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  say "created .env"
else
  info ".env already exists — updating only the values you choose"
fi
grep -q '^APP_IMAGE=' .env || set_env APP_IMAGE "$APP_IMAGE_REF"

# APP_SECRET: generate a strong one now (signs sessions + encrypts secrets at rest).
cur_secret="$(grep '^APP_SECRET=' .env | head -1 | cut -d= -f2- || true)"
case "${cur_secret}" in
  ""|change-me-in-production|change-me|changeme|mongoT-qa-dev-key-change-me)
    set_env APP_SECRET "$(rand 48)"
    info "generated a strong APP_SECRET"
    ;;
esac

# ── bring-your-own MongoDB URI ──────────────────────────────────────────────
if [ "$MODE" = "byo" ]; then
  uri="${WARDENIQ_MONGO_URI:-}"
  if [ -z "$uri" ] && interactive; then
    info "Paste your MongoDB connection string (needs Vector Search — Atlas M10+ or self-managed mongot)."
    while :; do
      uri="$(ask 'MONGO_URI' '')"
      [ -z "$uri" ] && break
      if ! mongo_uri_format_ok "$uri"; then
        warn "that doesn't look like a MongoDB connection string — it must start with mongodb:// or mongodb+srv://"
        continue
      fi
      info "checking the connection..."
      # install.sh runs under `set -e`; mongo_uri_reachable legitimately returns
      # non-zero when the connection fails (that's the whole point), so it MUST
      # be guarded here or a real connection failure kills the entire installer
      # silently right at this line, with no error message at all.
      rc=0
      mongo_uri_reachable "$uri" || rc=$?
      if [ "$rc" -eq 0 ]; then
        info "connected OK"
        break
      elif [ "$rc" -eq 2 ]; then
        info "(mongosh not found on this machine — skipping the live connection check; format looks OK)"
        break
      else
        warn "could not connect using that URI (wrong host/user/password, IP not allow-listed, cluster paused, etc)."
        if ask_yesno "Use it anyway?" "n"; then break; fi
        # loop back and re-prompt
      fi
    done
  elif [ -n "$uri" ] && ! mongo_uri_format_ok "$uri"; then
    warn "WARDENIQ_MONGO_URI doesn't look like a valid MongoDB connection string (must start with mongodb:// or mongodb+srv://) — saving it as given since this is a non-interactive run, but the app will fail to start until it's fixed."
  fi
  if [ -n "$uri" ]; then
    set_env MONGO_URI "$uri"; info "MONGO_URI saved to .env"
  else
    warn "no MONGO_URI provided — set it in $DEST/.env before the app will start."
  fi
  # App-only flow: default AI to an Ollama on the host (or switch to a hosted provider in-app).
  set_env OLLAMA_URL_BUNDLED "http://host.docker.internal:11434"
else
  set_env OLLAMA_URL_BUNDLED "http://ollama:11434"
fi

# ── admin password (replaces the admin123 default) ──────────────────────────
admin_pw="${WARDENIQ_ADMIN_PASSWORD:-}"
if [ -z "$admin_pw" ] && interactive; then
  info "Set the first admin's login password (username: admin). Policy: >=8 chars, a letter and a number."
  info "Leave blank to keep the default admin123 (you'll be forced to change it on first login)."
  while :; do
    p1="$(ask_secret 'Admin password (blank = default):')"
    [ -z "$p1" ] && break
    if ! password_policy_ok "$p1"; then
      warn "must be >=8 chars, include a letter and a number, and not be 'admin123'."; continue
    fi
    p2="$(ask_secret 'Confirm password:')"
    [ "$p1" = "$p2" ] && { admin_pw="$p1"; break; } || warn "passwords didn't match — try again."
  done
fi
if [ -n "$admin_pw" ]; then
  if password_policy_ok "$admin_pw"; then
    set_env ADMIN_PASSWORD "$admin_pw"; info "admin password set (admin123 will be disabled)"
  else
    warn "provided admin password fails policy — leaving the default (forced change on first login)."
  fi
fi

# ── mongot search password (bundled only) — random, never committed ─────────
if [ "$MODE" = "bundled" ]; then
  if [ ! -s config/pwfile ] || [ "$(cat config/pwfile 2>/dev/null)" = "mongotPassword" ]; then
    rand 32 | tr -d '\n' > config/pwfile
    info "generated a random mongot (search) password → config/pwfile"
  else
    info "keeping existing config/pwfile mongot password"
  fi
  chmod 400 config/pwfile
fi

# ── pick the compose selection for this mode ────────────────────────────────
if [ "$MODE" = "bundled" ]; then
  # Pass the three service files explicitly rather than relying on docker-compose.yml's
  # `include:` (which needs Compose v2.20+). Works on any Compose v2.
  COMPOSE=(docker compose -f docker-compose.app.yml -f docker-compose.mongodb.yml -f docker-compose.ollama.yml)
else
  COMPOSE=(docker compose -f docker-compose.app.yml)
fi

# ── cleanup previous run + pull fresh images ────────────────────────────────
say "cleaning up any previous wardenIQ containers"
if [ "$WIPE" = "yes" ]; then
  "${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
else
  "${COMPOSE[@]}" down --remove-orphans 2>/dev/null || true
fi

say "pulling fresh images"
docker pull "$APP_IMAGE_REF" || die "could not pull $APP_IMAGE_REF"
"${COMPOSE[@]}" pull 2>/dev/null || true   # refresh mongo/mongot/ollama too (bundled)

# ── start ───────────────────────────────────────────────────────────────────
if [ "$MODE" = "byo" ] && ! grep -q '^MONGO_URI=..*' .env; then
  echo
  say "setup complete, but no MONGO_URI is set yet."
  info "Edit $DEST/.env → set MONGO_URI, then start it:"
  info "    cd $DEST && docker compose -f docker-compose.app.yml up -d --no-build --pull always"
  exit 0
fi

say "starting wardenIQ"
"${COMPOSE[@]}" up -d --no-build --pull always

echo
say "wardenIQ → ${c_bold}http://localhost:8001${c_rst}"
[ "$MODE" = "bundled" ] && info "First launch takes a few minutes (replica-set init + model download)."
info "Sign in as ${c_bold}admin${c_rst} with the password you set${admin_pw:+ (or the one you chose)}."
info "Watch it come up:  docker logs -f warden-app"
