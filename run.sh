#!/usr/bin/env bash
# wardenIQ launcher. Builds + starts the full stack, then captures logs.
#   ./run.sh           build + start
#   ./run.sh --reset   wipe data volumes first (fresh replica set + DB)
# Windows (no WSL/Git Bash)?  Use run.ps1 instead — same steps, pure PowerShell.
set -uo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "creating .env from .env.example (edit APP_SECRET!)"; cp .env.example .env; }

# mongot requires its password file to be readable by owner only.
chmod 400 config/pwfile 2>/dev/null || true
chmod +x config/setup-replica-set.sh collect-logs.sh 2>/dev/null || true

if [ "${1:-}" = "--reset" ]; then
  echo "==> wiping volumes"
  docker compose down -v --remove-orphans
fi

echo "==> building + starting wardenIQ"
docker compose up -d --build

echo "==> waiting for services to settle (replica set + model pulls can take a few minutes)"
sleep 45
./collect-logs.sh || true

echo
echo "wardenIQ → http://localhost:8001"
echo "Logs captured in ./logs/"
