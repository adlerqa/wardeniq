#!/bin/bash
# Initialize a 3-MEMBER replica set (high availability — one node can fail without
# downtime; also satisfies mongot's replica-set requirement) and create the user
# mongot uses to sync. Idempotent — safe to re-run.
set -e
SEED="mongod1.warden-net:27017"
M1="mongod1.warden-net:27017"
M2="mongod2.warden-net:27017"
M3="mongod3.warden-net:27017"

wait_for() {
  echo "[setup] waiting for $1 ..."
  until mongosh "mongodb://$1/" --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
    sleep 2
  done
}
wait_for "$M1"; wait_for "$M2"; wait_for "$M3"

RS=$(mongosh "mongodb://${SEED}/" --quiet --eval "
try { rs.status(); print('INITIALIZED'); }
catch (e) { if (e.code===94 || e.message.includes('no replset config')) print('NOT_INITIALIZED'); else print('ERR ' + e.message); }
" | tail -1)

if [ "$RS" = "NOT_INITIALIZED" ]; then
  echo "[setup] initiating 3-member replica set rs0..."
  mongosh "mongodb://${SEED}/" --quiet --eval "
  rs.initiate({ _id: 'rs0', members: [
    { _id: 0, host: '${M1}', priority: 2 },
    { _id: 1, host: '${M2}', priority: 1 },
    { _id: 2, host: '${M3}', priority: 1 }
  ]});"
  echo "[setup] waiting for PRIMARY..."
  for i in $(seq 1 60); do
    P=$(mongosh "mongodb://${SEED}/" --quiet --eval "try{print(rs.status().myState===1?'P':'N')}catch(e){print('E')}" | tail -1)
    [ "$P" = "P" ] && { echo "[setup] PRIMARY ready"; break; }
    sleep 2
  done
else
  echo "[setup] replica set already initialized"
fi

# mongot authenticates to mongod as this user (official self-managed role).
#
# The password is NOT hard-coded any more. It comes from the SAME secret mongot
# itself reads (config/pwfile), mounted here read-only at /run/secrets/mongot-pw,
# so the two can never drift. An explicit MONGOT_PASSWORD env var wins if set.
# Legacy fallback ('mongotPassword') only applies to old installs with neither.
MONGOT_USER="${MONGOT_USER:-mongotUser}"
if [ -n "${MONGOT_PASSWORD:-}" ]; then
  MONGOT_PW="$MONGOT_PASSWORD"
elif [ -f /run/secrets/mongot-pw ]; then
  # Strip any trailing newline/CR a text editor may have added.
  MONGOT_PW="$(tr -d '\r\n' < /run/secrets/mongot-pw)"
else
  MONGOT_PW="mongotPassword"
fi

echo "[setup] ensuring ${MONGOT_USER} (searchCoordinator)..."
# Idempotent AND rotation-safe: create the user if absent, otherwise reset its
# password to the current secret so re-running the installer with a fresh
# password actually takes effect. Password passed via a shell env var into
# mongosh (never interpolated into the JS string) so special characters are safe.
MONGOT_USER="$MONGOT_USER" MONGOT_PW="$MONGOT_PW" mongosh "mongodb://${SEED}/" --quiet --eval "
const a = db.getSiblingDB('admin');
const u = process.env.MONGOT_USER, p = process.env.MONGOT_PW;
try {
  a.createUser({ user:u, pwd:p, roles:[{role:'searchCoordinator',db:'admin'}] });
  print('user created');
} catch(e){
  if(e.code===51003){ a.updateUser(u, { pwd:p }); print('user exists — password synced'); }
  else print('err ' + e.message);
}
"

# ── OPTIONAL: provision auth users (opt-in; see scripts/enable-mongo-auth.sh) ──
# This runs while the replica set is still UNAUTHENTICATED (phase 1 of the two-phase
# bootstrap), so plain createUser over the network works. A later keyfile restart
# (docker-compose.mongodb-auth.yml) then enforces these credentials. On re-runs where
# auth is already enforced, the createUser calls are caught and skipped harmlessly.
if [ "${MONGO_AUTH_ENABLED:-false}" = "true" ]; then
  : "${MONGO_ROOT_USER:?MONGO_ROOT_USER required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_ROOT_PASSWORD:?MONGO_ROOT_PASSWORD required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_APP_USER:?MONGO_APP_USER required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_APP_PASSWORD:?MONGO_APP_PASSWORD required when MONGO_AUTH_ENABLED=true}"
  echo "[setup] MONGO_AUTH_ENABLED — provisioning root + app users..."
  # Credentials passed via env (never interpolated into the JS string) so any
  # special characters are safe. App user gets 'root' so it can create its DB and
  # the 6 vectorSearch indexes without privilege gaps (single-tenant; scope down later).
  MONGO_ROOT_USER="$MONGO_ROOT_USER" MONGO_ROOT_PASSWORD="$MONGO_ROOT_PASSWORD" \
  MONGO_APP_USER="$MONGO_APP_USER" MONGO_APP_PASSWORD="$MONGO_APP_PASSWORD" \
  mongosh "mongodb://${SEED}/" --quiet --eval '
    const admin = db.getSiblingDB("admin");
    const e = process.env;
    function ensure(user, pwd, roles){
      try { admin.createUser({ user:user, pwd:pwd, roles:roles }); print("created " + user); }
      catch(err){
        if(err.code===51003){ try { admin.updateUser(user, { pwd:pwd, roles:roles }); print(user + " synced"); } catch(e2){ print("update skipped for " + user); } }
        else if(err.codeName==="Unauthorized"){ print("auth already enforced — leaving " + user + " as-is"); }
        else print("err " + err.message);
      }
    }
    ensure(e.MONGO_ROOT_USER, e.MONGO_ROOT_PASSWORD, [{role:"root", db:"admin"}]);
    ensure(e.MONGO_APP_USER,  e.MONGO_APP_PASSWORD,  [{role:"root", db:"admin"}]);
  '
fi
echo "[setup] done"
