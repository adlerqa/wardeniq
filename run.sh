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

if [ "${1:-}" = "--reset" ]; then
  echo "==> wiping volumes"
  "${COMPOSE[@]}" down -v --remove-orphans
fi

echo "==> building + starting wardenIQ"
"${COMPOSE[@]}" up -d --build

echo "==> waiting for services to settle (replica set + model pulls can take a few minutes)"
sleep 45
./collect-logs.sh || true

echo
echo "wardenIQ → http://localhost:8001"
echo "Logs captured in ./logs/"
