#!/usr/bin/env bash
# wardenIQ launcher. Builds + starts the full stack, then captures logs.
#   ./run.sh           build + start
#   ./run.sh --reset   wipe data volumes first (fresh replica set + DB)
# Windows (no WSL/Git Bash)?  Use run.ps1 instead — same steps, pure PowerShell.
set -uo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "creating .env from .env.example (edit APP_SECRET!)"; cp .env.example .env; }

# mongot's password is NOT committed (config/pwfile is git-ignored). Generate a
# strong random one on first run; the setup container reads the SAME file to
# provision the mongot user, so the two always match. Re-generate if it's still
# the old committed default. `--rotate-mongot-pw` forces a fresh one.
if [ "${1:-}" = "--rotate-mongot-pw" ]; then rm -f config/pwfile; shift; fi
if [ ! -s config/pwfile ] || [ "$(cat config/pwfile 2>/dev/null)" = "mongotPassword" ]; then
  ( LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32 ) > config/pwfile
  echo "==> generated a random mongot (search) password → config/pwfile"
fi

# mongot requires its password file to be readable by owner only.
chmod 400 config/pwfile 2>/dev/null || true
chmod +x config/setup-replica-set.sh collect-logs.sh 2>/dev/null || true

# ── first-start database/backend selection (#109) ──────────────────────────
# Only ever prompts (and only ever writes .env below) on a genuinely fresh
# install: neither MONGO_URI nor COMPOSE_FILE is already pinned. This is the
# EXACT gate the kernel check further below already used pre-#109 — reusing it
# here (rather than inventing a new "already configured" signal) guarantees an
# existing installation is never re-prompted and never notices this change.
FRESH_DB_INSTALL=1
grep -qE '^MONGO_URI=.+' .env 2>/dev/null && FRESH_DB_INSTALL=0
grep -q '^COMPOSE_FILE=' .env 2>/dev/null && FRESH_DB_INSTALL=0

if [ "$FRESH_DB_INSTALL" = "1" ]; then
  # Same interactive/non-interactive pattern install.sh already established —
  # reused verbatim rather than reinvented, per the issue's own instruction.
  TTY=""; [ -r /dev/tty ] && TTY="/dev/tty"
  ASSUME_YES="${WARDENIQ_ASSUME_YES:-0}"
  interactive() { [ -n "$TTY" ] && [ "$ASSUME_YES" != "1" ]; }
  ask() {
    local q="$1" def="${2:-}" ans=""
    if interactive; then
      printf '%s%s ' "$q" "${def:+ [$def]}" > "$TTY"
      IFS= read -r ans < "$TTY" || true
    fi
    printf '%s' "${ans:-$def}"
  }
  # Silent (no echo) — a MONGO_URI may embed credentials, so it must never hit
  # the terminal, shell history, or logs (see install.sh's ask_secret()).
  ask_secret() {
    local q="$1" ans=""
    if interactive; then
      printf '%s ' "$q" > "$TTY"
      IFS= read -rs ans < "$TTY" || true
      printf '\n' > "$TTY"
    fi
    printf '%s' "$ans"
  }
  ask_yesno() {
    local q="$1" def="${2:-n}" ans
    ans="$(ask "$q ($( [ "$def" = y ] && echo 'Y/n' || echo 'y/N'))" "$def")"
    ans="$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')"
    case "$ans" in y|yes) return 0 ;; n|no) return 1 ;; *) [ "$def" = y ] ;; esac
  }
  mongo_uri_format_ok() {
    case "$1" in
      mongodb://*|mongodb+srv://*) return 0 ;;
      *) return 1 ;;
    esac
  }
  # 0 = connected, 1 = failed to connect, 2 = can't check (no mongosh — not an error).
  mongo_uri_reachable() {
    command -v mongosh >/dev/null 2>&1 || return 2
    mongosh "$1" --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1 &
    local pid=$! i=0
    while kill -0 "$pid" 2>/dev/null; do
      i=$((i + 1))
      [ "$i" -ge 100 ] && { kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; return 1; }
      sleep 0.1
    done
    wait "$pid"
  }
  set_env() {
    local k="$1"; shift; local v="$*"
    [ -f .env ] || : > .env
    grep -v "^${k}=" .env > .env.tmp 2>/dev/null || true
    mv .env.tmp .env
    printf '%s=%s\n' "$k" "$v" >> .env
  }

  DB_CHOICE="${WARDENIQ_DB:-}"
  if [ -z "$DB_CHOICE" ]; then
    if interactive; then
      echo
      echo "No existing wardenIQ database configuration was detected."
      echo
      echo "Choose your database:"
      echo
      echo "  1) MongoDB Community Server (bundled, default)"
      echo "  2) Percona Server for MongoDB + Percona Search (bundled, technical preview — see #27, #41)"
      echo "  3) Use an existing MongoDB-compatible database"
      echo
      while :; do
        case "$(ask 'Select [1-3]' '1')" in
          1) DB_CHOICE="community"; break ;;
          2) DB_CHOICE="percona"; break ;;
          3) DB_CHOICE="external"; break ;;
          *) echo "Please enter 1, 2, or 3." >&2 ;;
        esac
      done
    else
      DB_CHOICE="community"   # non-interactive, no WARDENIQ_DB: friendliest zero-config default
    fi
  fi

  case "$DB_CHOICE" in
    community)
      : # unchanged current behavior — MONGO_URI stays unset, falls back to MONGO_URI_BUNDLED
      ;;
    percona)
      echo "==> Percona is a technical preview: it does NOT avoid the kernel >= 6.19"
      echo "    limitation below (see #27, #41, docs/percona-search-validation.md)."
      if [ ! -s config/pwfile-percona ]; then
        ( LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32 ) > config/pwfile-percona
        echo "==> generated a random Percona mongot (search) password → config/pwfile-percona"
      fi
      chmod 400 config/pwfile-percona 2>/dev/null || true
      set_env MONGO_URI "mongodb://mongod-percona:27017/?replicaSet=rs0"
      set_env COMPOSE_FILE "docker-compose.app.yml:docker-compose.mongodb-percona.yml:docker-compose.ollama.yml"
      ;;
    external)
      uri="${WARDENIQ_MONGO_URI:-}"
      if [ -z "$uri" ] && interactive; then
        echo "Paste your MongoDB connection string (needs Vector Search — Atlas M10+ or self-managed mongot)."
        while :; do
          uri="$(ask_secret 'MONGO_URI:')"
          [ -z "$uri" ] && break
          if ! mongo_uri_format_ok "$uri"; then
            echo "that doesn't look like a MongoDB connection string — it must start with mongodb:// or mongodb+srv://" >&2
            continue
          fi
          echo "checking the connection..."
          # mongo_uri_reachable legitimately returns non-zero when the connection
          # fails (that's the whole point) — capture it via `||` rather than relying
          # on $? directly, matching install.sh's own identical guard.
          rc=0
          mongo_uri_reachable "$uri" || rc=$?
          if [ "$rc" -eq 0 ]; then
            echo "connected OK"; break
          elif [ "$rc" -eq 2 ]; then
            echo "(mongosh not found on this machine — skipping the live connection check; format looks OK)"
            break
          else
            echo "could not connect using that URI (wrong host/user/password, IP not allow-listed, cluster paused, etc)." >&2
            if ask_yesno "Use it anyway?" "n"; then break; fi
          fi
        done
      elif [ -n "$uri" ] && ! mongo_uri_format_ok "$uri"; then
        echo "==> WARDENIQ_MONGO_URI doesn't look like a valid MongoDB connection string (must start with mongodb:// or mongodb+srv://) — saving it as given since this is a non-interactive run, but the app will fail to start until it's fixed." >&2
      fi
      if [ -n "$uri" ]; then
        set_env MONGO_URI "$uri"
      else
        echo "==> no MONGO_URI provided — set it in .env before wardenIQ will start." >&2
      fi
      set_env COMPOSE_FILE "docker-compose.app.yml:docker-compose.ollama.yml"
      set_env OLLAMA_URL_BUNDLED "http://host.docker.internal:11434"
      ;;
    *)
      echo "==> invalid WARDENIQ_DB value: '$DB_CHOICE' (expected community, percona, or external)" >&2
      exit 1
      ;;
  esac
fi

# Compose file selection. docker-compose.yml uses `include:`, which needs Compose
# v2.20+. To work on ANY Compose v2, we pass the three service files explicitly
# instead of relying on that include — UNLESS .env pins COMPOSE_FILE (e.g. after
# the first-start selection above, or ./scripts/enable-mongo-auth.sh), in which
# case we let Compose honour that.
if grep -q '^COMPOSE_FILE=' .env 2>/dev/null; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker compose -f docker-compose.app.yml -f docker-compose.mongodb.yml -f docker-compose.ollama.yml)
fi

# Fail fast on a kernel MongoDB's tcmalloc allocator refuses to start on (see #27).
# Applies to EITHER bundled MongoDB profile (Community or Percona — the Percona
# validation in #41/PR #105 confirmed Percona's mongod hits the identical
# tcmalloc failure, so choosing Percona must not silently skip this check just
# because it also sets MONGO_URI). Only a genuine bring-your-own MONGO_URI (no
# bundled compose file pinned) skips it, since that database isn't started here.
PERCONA_PINNED=0
if grep -q '^COMPOSE_FILE=' .env 2>/dev/null; then
  case "$(grep '^COMPOSE_FILE=' .env | head -1)" in
    *docker-compose.mongodb-percona.yml*) PERCONA_PINNED=1 ;;
  esac
fi
if [ "$PERCONA_PINNED" = "1" ] || ! grep -qE '^MONGO_URI=.+' .env 2>/dev/null; then
  KERNEL_VERSION=$(docker info --format '{{.KernelVersion}}' 2>/dev/null || true)
  KMAJOR=$(printf '%s' "$KERNEL_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+).*/\1/')
  KMINOR=$(printf '%s' "$KERNEL_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+).*/\2/')
  if [[ "$KMAJOR" =~ ^[0-9]+$ ]] && [[ "$KMINOR" =~ ^[0-9]+$ ]] \
     && { [ "$KMAJOR" -gt 6 ] || { [ "$KMAJOR" -eq 6 ] && [ "$KMINOR" -ge 19 ]; }; }; then
    echo "==> refusing to start: Docker's Linux kernel is $KERNEL_VERSION" >&2
    echo "    MongoDB's tcmalloc allocator has a known startup failure on kernel >= 6.19" >&2
    echo "    (see https://github.com/adlerqa/wardeniq/issues/27 for the full analysis)." >&2
    echo "    The bundled local stack cannot run on this Docker install today." >&2
    echo >&2
    echo "    Supported alternative: bring your own MongoDB. Set MONGO_URI in .env" >&2
    echo "    (Atlas, or a self-managed replica set with mongot) and run this script again." >&2
    exit 1
  fi
fi

if [ "${1:-}" = "--reset" ]; then
  echo "==> wiping volumes"
  "${COMPOSE[@]}" down -v --remove-orphans
fi

echo "==> building + starting wardenIQ"
"${COMPOSE[@]}" up -d --build

# Readiness gate: don't report success until the app actually answers, not just
# "started". Polls the same public boot-status endpoint the sign-in screen
# uses (never returns raw driver errors — see #34/#44).
echo "==> waiting for wardenIQ to become ready (replica set + model pulls can take a few minutes)"
READY=""
DEADLINE=$((SECONDS + 300))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  BOOT_JSON=$(curl -fsS http://localhost:8001/api/auth/boot-status 2>/dev/null) || BOOT_JSON=""
  case "$BOOT_JSON" in
    *'"ready":true'*|*'"ready": true'*) READY=1; break ;;
  esac
  sleep 5
done

./collect-logs.sh || true

if [ -z "$READY" ]; then
  echo >&2
  echo "==> wardenIQ did not become ready within 5 minutes." >&2
  echo "    Last boot status: ${BOOT_JSON:-no response from http://localhost:8001}" >&2
  echo >&2
  echo "--- docker logs warden-app (last 50 lines) ---" >&2
  docker logs --tail 50 warden-app 2>&1 >&2 || true
  echo >&2
  echo "--- docker logs warden-mongod1 (last 50 lines) ---" >&2
  docker logs --tail 50 warden-mongod1 2>&1 >&2 || true
  echo >&2
  echo "Full logs also captured in ./logs/" >&2
  exit 1
fi

echo
echo "wardenIQ → http://localhost:8001"
echo "Logs captured in ./logs/"
