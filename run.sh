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

# Compose file selection. docker-compose.yml uses `include:`, which needs Compose
# v2.20+. To work on ANY Compose v2, we pass the three service files explicitly
# instead of relying on that include — UNLESS .env pins COMPOSE_FILE (e.g. after
# ./scripts/enable-mongo-auth.sh), in which case we let Compose honour that.
if grep -q '^COMPOSE_FILE=' .env 2>/dev/null; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker compose -f docker-compose.app.yml -f docker-compose.mongodb.yml -f docker-compose.ollama.yml)
fi

# Fail fast on a kernel MongoDB's tcmalloc allocator refuses to start on (see #27).
# Only applies to the bundled MongoDB profile — bring-your-own MONGO_URI isn't
# affected, since that database isn't started by this script.
if ! grep -qE '^MONGO_URI=.+' .env 2>/dev/null; then
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
