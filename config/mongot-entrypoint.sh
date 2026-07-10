#!/bin/sh
set -eu

data_dir="${MONGOT_DATA_DIR:-/var/lib/mongot}"
journal="${data_dir}/configJournal.json"

# An interrupted Docker volume write can leave mongot's config journal filled
# entirely with NUL bytes. Mongot cannot parse that file and otherwise enters an
# endless restart loop ("failed to initialize from config journal"). Only
# quarantine this unmistakably corrupt shape; valid/partial journals are left
# untouched for diagnosis. mongot rebuilds a fresh journal from the replica set.
if [ -s "$journal" ] && ! tr -d '\000' <"$journal" | grep -q .; then
  recovery_dir="${data_dir}/recovery"
  mkdir -p "$recovery_dir"
  quarantined="${recovery_dir}/configJournal.json.nul-corrupt.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$journal" "$quarantined"
  echo "Quarantined NUL-corrupted mongot config journal: $quarantined" >&2
fi

# mongot refuses to start if its password file is readable by anyone but the
# owner. Windows/macOS bind mounts often present files as world-readable and
# ignore chmod, so copy the mounted secret to a private, owner-only path and
# point the config at it (config/mongot.conf uses this same path).
src_secret="/etc/mongot/secrets/passwordFile"
secure_dir="/tmp/wardeniq-mongot-secrets"
if [ -f "$src_secret" ]; then
  mkdir -p "$secure_dir"
  chmod 700 "$secure_dir"
  cp "$src_secret" "$secure_dir/passwordFile"
  chmod 400 "$secure_dir/passwordFile"
fi

# Launch the OFFICIAL MongoDB Community mongot against our mounted config
# (the image's default entrypoint runs exactly this; we wrap it for self-heal).
exec /mongot-community/mongot --config /mongot-community/config.default.yml
