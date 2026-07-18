#!/usr/bin/env bash
# Dump container logs + health into ./logs/ for troubleshooting.
# Windows (no WSL/Git Bash)?  Use collect-logs.ps1 instead.
cd "$(dirname "$0")"
mkdir -p logs
echo "collecting logs into ./logs/  ($(date '+%Y-%m-%d %H:%M:%S'))"

for c in warden-mongod1 warden-mongod2 warden-mongod3 warden-setup warden-mongot \
         warden-ollama warden-ollama-pull warden-app; do
  if docker inspect "$c" >/dev/null 2>&1; then
    docker logs --tail 400 "$c" > "logs/${c}.log" 2>&1
  else
    echo "container $c not found" > "logs/${c}.log"
  fi
done

# Use explicit service files (docker-compose.yml's `include:` needs Compose v2.20+),
# unless .env pins COMPOSE_FILE. Falls back to a plain `ps` if neither is usable.
if grep -q '^COMPOSE_FILE=' .env 2>/dev/null; then
  docker compose ps > logs/_status.txt 2>&1
else
  docker compose -f docker-compose.app.yml -f docker-compose.mongodb.yml -f docker-compose.ollama.yml ps > logs/_status.txt 2>&1
fi
curl -s localhost:8001/api/status > logs/app_status.json 2>&1 || echo "app unreachable" > logs/app_status.json
echo "done -> ./logs/"
