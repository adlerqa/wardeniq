#!/usr/bin/env bash
# Enable MongoDB authentication on the BUNDLED replica set (opt-in hardening).
#
# Why a script (not just a compose flag): a keyfile enables auth immediately, and the
# first user on an auth-enabled set can only be created via the localhost exception —
# which does NOT apply across containers. So we do the MongoDB-recommended TWO-PHASE
# bootstrap:
#   Phase 1 — bring the set up WITHOUT the keyfile and create root + app + mongot users
#             while it's still unauthenticated (setup-replica-set.sh does this).
#   Phase 2 — restart the mongods WITH the keyfile so those credentials are enforced,
#             and point the app at a MONGO_URI that carries the app credentials.
#
# Idempotent: safe to re-run. It also writes COMPOSE_FILE into .env so every later
# `docker compose ...` / `./run.sh` keeps auth on automatically.
#
# NOTE: this path has not been exercised on a live Docker host in this workspace —
# run it once and watch `docker logs warden-setup` + `docker logs warden-mongod1`.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

# Explicit service files (NOT docker-compose.yml's `include:`, which needs Compose
# v2.20+) so this works on any Compose v2.
BASE_FILES=(-f docker-compose.app.yml -f docker-compose.mongodb.yml -f docker-compose.ollama.yml)
AUTH="docker-compose.mongodb-auth.yml"
COMPOSE_FILE_VALUE="docker-compose.app.yml:docker-compose.mongodb.yml:docker-compose.ollama.yml:${AUTH}"
[ -f docker-compose.mongodb.yml ] || { echo "run this from a wardenIQ checkout"; exit 1; }
[ -f .env ] || cp .env.example .env

rand() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 $(( ${1:-32} * 2 )) | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "${1:-32}"
  else LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-32}"; fi
}
get_env() { grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }
set_env() {  # replace-or-append literally
  local k="$1"; shift; local v="$*"
  grep -v "^${k}=" .env > .env.tmp 2>/dev/null || true; mv .env.tmp .env
  printf '%s=%s\n' "$k" "$v" >> .env
}

echo "==> generating a replica-set keyfile (internal member auth)"
if [ ! -s config/keyfile ]; then
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 756 > config/keyfile
  else head -c 756 /dev/urandom | base64 | tr -d '\n' > config/keyfile; fi
  chmod 400 config/keyfile
  echo "    created config/keyfile"
else
  echo "    config/keyfile already present — keeping it"
fi

# ── credentials (reuse existing .env values; generate strong ones otherwise) ──
ROOT_U="$(get_env MONGO_ROOT_USER)"; ROOT_U="${ROOT_U:-wardenRoot}"
APP_U="$(get_env MONGO_APP_USER)";   APP_U="${APP_U:-wardenApp}"
ROOT_P="$(get_env MONGO_ROOT_PASSWORD)"; [ -n "$ROOT_P" ] || ROOT_P="$(rand 32)"
APP_P="$(get_env MONGO_APP_PASSWORD)";   [ -n "$APP_P" ] || APP_P="$(rand 32)"
DB_NAME="$(get_env DB_NAME)"; DB_NAME="${DB_NAME:-wardeniq}"

MEMBERS="mongod1.warden-net:27017,mongod2.warden-net:27017,mongod3.warden-net:27017"
APP_URI="mongodb://${APP_U}:${APP_P}@${MEMBERS}/?replicaSet=rs0&authSource=admin"

set_env MONGO_AUTH_ENABLED true
set_env MONGO_ROOT_USER "$ROOT_U"
set_env MONGO_ROOT_PASSWORD "$ROOT_P"
set_env MONGO_APP_USER "$APP_U"
set_env MONGO_APP_PASSWORD "$APP_P"
set_env MONGO_URI "$APP_URI"

echo "==> phase 1: creating users on the still-unauthenticated replica set"
docker compose "${BASE_FILES[@]}" up -d --no-build mongod1 mongod2 mongod3 mongod-setup
echo "    waiting for the setup job to finish..."
docker wait warden-setup >/dev/null 2>&1 || true
docker logs warden-setup 2>&1 | tail -6 || true

echo "==> phase 2: restarting mongods WITH the keyfile (auth now enforced)"
docker compose "${BASE_FILES[@]}" -f "$AUTH" up -d --no-build --force-recreate mongod1 mongod2 mongod3

echo "==> bringing up the rest of the stack (app now uses authenticated MONGO_URI)"
docker compose "${BASE_FILES[@]}" -f "$AUTH" up -d --no-build

# Persist the file list so future `docker compose` / run.sh keep auth on.
set_env COMPOSE_FILE "$COMPOSE_FILE_VALUE"

echo
echo "MongoDB authentication is ON. Credentials saved to .env (keep it safe):"
echo "    root user : ${ROOT_U}"
echo "    app  user : ${APP_U}"
echo "    MONGO_URI : mongodb://${APP_U}:***@${MEMBERS}/?replicaSet=rs0&authSource=admin"
echo
echo "Every later 'docker compose ...' and './run.sh' now includes the keyfile override"
echo "(via COMPOSE_FILE in .env). To connect a local client, add credentials + authSource=admin."
echo "Watch it come up:  docker logs -f warden-app"
