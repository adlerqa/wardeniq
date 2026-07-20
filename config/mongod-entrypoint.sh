#!/bin/sh
set -eu
# Used ONLY by the opt-in auth override (docker-compose.mongodb-auth.yml).
#
# mongod requires its replica-set keyFile to be owned by the running user and NOT
# readable by group/other. Windows/macOS (and even Linux) bind mounts often present
# the mounted file as world-readable and with a foreign owner, which mongod rejects
# ("permissions on ... are too open"). So — exactly like config/mongot-entrypoint.sh
# does for mongot's password file — copy the mounted keyfile to a private, owner-only
# path and start mongod against that copy.
src_key="/etc/mongo-keyfile.src"
secure_dir="/tmp/wardeniq-mongod-secrets"
key="${secure_dir}/keyfile"
if [ -f "$src_key" ]; then
  mkdir -p "$secure_dir"
  chmod 700 "$secure_dir"
  cp "$src_key" "$key"
  chmod 400 "$key"
fi

# Exec the official server binary with our config + the secured keyfile. Passing
# --keyFile implicitly enables client authorization on this node.
exec mongod --config /etc/mongod.conf --replSet rs0 --keyFile "$key"
