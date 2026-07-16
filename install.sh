#!/usr/bin/env bash
# wardenIQ installer — no repo, no build. Pulls the published Docker Hub image and
# downloads only the handful of small config files needed to run it.
#
#   curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash
#
# By default this sets you up to bring your own MongoDB (recommended — e.g. MongoDB
# Atlas; see the "Cloud / lightweight deployment" section of the README). Add
# --bundled if you'd rather also grab the all-local demo stack (bundled MongoDB +
# Ollama) so you can try wardenIQ with zero cloud accounts:
#
#   curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash -s -- --bundled
#
# Env overrides: WARDENIQ_DIR (default "wardeniq"), WARDENIQ_TAG (default "beta").
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/adlerqa/wardeniq/main"
DEST="${WARDENIQ_DIR:-wardeniq}"
TAG="${WARDENIQ_TAG:-beta}"
BUNDLED=false

for arg in "$@"; do
  case "$arg" in
    --bundled) BUNDLED=true ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "Docker is required — install Docker Desktop first."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (comes with Docker Desktop)."; exit 1; }

echo "==> setting up wardenIQ in ./$DEST (published image adlerqa/wardeniq:$TAG — no source needed)"
mkdir -p "$DEST"
cd "$DEST"

fetch() { curl -fsSL "$REPO_RAW/$1" -o "$1"; }

fetch docker-compose.app.yml
fetch .env.example

if [ "$BUNDLED" = true ]; then
  echo "==> also grabbing the bundled MongoDB/Ollama demo stack (config/ + compose files)"
  fetch docker-compose.yml
  fetch docker-compose.mongodb.yml
  fetch docker-compose.ollama.yml
  mkdir -p config
  for f in mongod.conf mongot.conf pwfile mongot-entrypoint.sh setup-replica-set.sh; do
    curl -fsSL "$REPO_RAW/config/$f" -o "config/$f"
  done
  chmod 400 config/pwfile
  chmod +x config/setup-replica-set.sh config/mongot-entrypoint.sh
fi

if [ ! -f .env ]; then
  cp .env.example .env
  grep -q '^APP_IMAGE=' .env || echo "APP_IMAGE=adlerqa/wardeniq:${TAG}" >> .env
  echo "==> created .env — APP_SECRET is generated automatically on first boot, nothing to edit there"
else
  echo "==> .env already exists, leaving it as-is"
fi

# Point the Ollama fallback at the right place for the chosen mode so an out-of-the-box
# run never targets a non-existent container:
#   bundled  -> the in-stack Ollama container
#   app-only -> the user's own Ollama on the host (Docker Desktop resolves
#               host.docker.internal; native Linux uses the host-gateway alias in
#               docker-compose.app.yml). Switch to a hosted provider in-app anytime.
if [ "$BUNDLED" = true ]; then
  OLLAMA_BUNDLED_URL="http://ollama:11434"
else
  OLLAMA_BUNDLED_URL="http://host.docker.internal:11434"
fi
if grep -q '^OLLAMA_URL_BUNDLED=' .env; then
  sed -i.bak "s#^OLLAMA_URL_BUNDLED=.*#OLLAMA_URL_BUNDLED=${OLLAMA_BUNDLED_URL}#" .env && rm -f .env.bak
else
  echo "OLLAMA_URL_BUNDLED=${OLLAMA_BUNDLED_URL}" >> .env
fi

# Pull the published app image up front so the "no source needed" promise holds.
# docker-compose.app.yml carries a build: section for open-source contributors who
# have ./app checked out. In this installer there is NO source, so if the image is
# not cached locally `docker compose up` would fall back to BUILDING from ./app and
# fail on a missing app/Dockerfile. Caching the image here keeps build: dormant, and
# --no-build below turns any remaining fallback into a clear error instead of a
# confusing source build.
echo "==> pulling adlerqa/wardeniq:${TAG}"
docker pull "adlerqa/wardeniq:${TAG}"

if [ "$BUNDLED" = true ]; then
  echo "==> starting the full bundled demo stack (app + MongoDB + Ollama) — pulling images, not building"
  docker compose up -d --no-build
  echo
  echo "wardenIQ → http://localhost:8001"
  echo "First launch takes a few minutes (replica set init + model download)."
  echo "Watch it come up: docker logs -f warden-app"
else
  echo
  echo "One thing left — this flow brings your own MongoDB (no bundled DB was downloaded)."
  echo "Open $DEST/.env and set MONGO_URI to your database (e.g. a MongoDB Atlas connection string)."
  echo "Then start it:"
  echo
  echo "    cd $DEST && docker compose -f docker-compose.app.yml up -d --no-build"
  echo
  echo "(Prefer the zero-cloud-accounts local demo instead? Re-run this installer with --bundled.)"
fi
