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

# Wait for $SEED (mongod1, priority 2 — highest, so it settles as PRIMARY after any
# election) to actually report itself PRIMARY. createUser/updateUser MUST run against
# a primary; on an ALREADY-initialized set (the common re-run case — e.g. after a
# `mongod-setup` restart, or during enable-mongo-auth.sh's phase 1) there can be a
# brief window right after startup where an election is still in progress and $SEED
# is a secondary. Without this wait, every createUser call below fails with
# 'not primary' and is silently skipped — which previously let the script continue
# on to enforce auth with the app/root users never actually created. Called
# unconditionally (fresh init AND already-initialized) so both paths are covered.
wait_for_primary() {
  echo "[setup] waiting for PRIMARY..."
  for i in $(seq 1 60); do
    P=$(mongosh "mongodb://${SEED}/" --quiet --eval "try{print(rs.status().myState===1?'P':'N')}catch(e){print('E')}" | tail -1)
    [ "$P" = "P" ] && { echo "[setup] PRIMARY ready"; return 0; }
    sleep 2
  done
  echo "[setup] WARNING: no PRIMARY after 120s — user provisioning below will likely fail" >&2
  return 1
}

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
else
  echo "[setup] replica set already initialized"
fi
wait_for_primary || true

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

# Run the createUser/updateUser JS in $2 against the mongo URI in $1, returning its
# last printed line. The JS always prints one of: 'created', 'synced', 'NEEDS_AUTH',
# or 'err <message>' — never silently swallows a real failure.
_run_ensure_js() {
  local uri="$1" js="$2"
  mongosh "$uri" --quiet --eval "$js" 2>/dev/null | tail -1
}

echo "[setup] ensuring ${MONGOT_USER} (searchCoordinator)..."
# Idempotent AND rotation-safe: create the user if absent, otherwise reset its
# password to the current secret so re-running the installer with a fresh
# password actually takes effect. Password passed via a shell env var into
# mongosh (never interpolated into the JS string) so special characters are safe.
MONGOT_JS='
const a = db.getSiblingDB("admin");
const u = process.env.MONGOT_USER, p = process.env.MONGOT_PW;
try {
  a.createUser({ user:u, pwd:p, roles:[{role:"searchCoordinator",db:"admin"}] });
  print("created");
} catch(e){
  if(e.code===51003){ try { a.updateUser(u, { pwd:p }); print("synced"); } catch(e2){ print("err " + e2.message); } }
  else if(e.codeName==="Unauthorized"){ print("NEEDS_AUTH"); }
  else print("err " + e.message);
}
'
RESULT=$(MONGOT_USER="$MONGOT_USER" MONGOT_PW="$MONGOT_PW" _run_ensure_js "mongodb://${SEED}/" "$MONGOT_JS")
if [ "$RESULT" = "NEEDS_AUTH" ]; then
  # Auth is already enforced (e.g. a re-run after enable-mongo-auth.sh). Retry
  # authenticated as root instead of assuming the user already exists — a prior
  # buggy run may have enforced auth WITHOUT ever successfully creating it.
  if [ "${MONGO_AUTH_ENABLED:-false}" = "true" ] && [ -n "${MONGO_ROOT_USER:-}" ] && [ -n "${MONGO_ROOT_PASSWORD:-}" ]; then
    ROOT_URI="mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@${SEED}/?authSource=admin"
    RESULT=$(MONGOT_USER="$MONGOT_USER" MONGOT_PW="$MONGOT_PW" _run_ensure_js "$ROOT_URI" "$MONGOT_JS")
  fi
fi
case "$RESULT" in
  created) echo "[setup] ${MONGOT_USER}: user created" ;;
  synced)  echo "[setup] ${MONGOT_USER}: user exists — password synced" ;;
  NEEDS_AUTH) echo "[setup] WARNING: ${MONGOT_USER} needs auth to fix and no working root credentials were available — mongot will fail to authenticate. Disable auth (drop config/keyfile, unset MONGO_AUTH_ENABLED) and re-run to recover." >&2 ;;
  *) echo "[setup] WARNING: ${MONGOT_USER}: $RESULT" >&2 ;;
esac

# ── OPTIONAL: provision auth users (opt-in; see scripts/enable-mongo-auth.sh) ──
# On a fresh, still-unauthenticated set (phase 1 of the two-phase bootstrap) plain
# createUser over the network works. On a re-run against a set that already has
# auth enforced, retry authenticated as root instead of just assuming the users
# are already there — a prior failed run (e.g. the 'not primary' race this file
# now guards against above) could have enforced auth without ever creating them.
if [ "${MONGO_AUTH_ENABLED:-false}" = "true" ]; then
  : "${MONGO_ROOT_USER:?MONGO_ROOT_USER required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_ROOT_PASSWORD:?MONGO_ROOT_PASSWORD required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_APP_USER:?MONGO_APP_USER required when MONGO_AUTH_ENABLED=true}"
  : "${MONGO_APP_PASSWORD:?MONGO_APP_PASSWORD required when MONGO_AUTH_ENABLED=true}"
  echo "[setup] MONGO_AUTH_ENABLED — provisioning root + app users..."
  # Credentials passed via env (never interpolated into the JS string) so any
  # special characters are safe. App user gets 'root' so it can create its DB and
  # the 6 vectorSearch indexes without privilege gaps (single-tenant; scope down later).
  AUTH_JS='
    const admin = db.getSiblingDB("admin");
    const e = process.env;
    function ensure(user, pwd, roles){
      try { admin.createUser({ user:user, pwd:pwd, roles:roles }); print(user + ":created"); }
      catch(err){
        if(err.code===51003){ try { admin.updateUser(user, { pwd:pwd, roles:roles }); print(user + ":synced"); } catch(e2){ print(user + ":err " + e2.message); } }
        else if(err.codeName==="Unauthorized"){ print(user + ":NEEDS_AUTH"); }
        else print(user + ":err " + err.message);
      }
    }
    ensure(e.MONGO_ROOT_USER, e.MONGO_ROOT_PASSWORD, [{role:"root", db:"admin"}]);
    ensure(e.MONGO_APP_USER,  e.MONGO_APP_PASSWORD,  [{role:"root", db:"admin"}]);
  '
  AUTH_RESULT=$(MONGO_ROOT_USER="$MONGO_ROOT_USER" MONGO_ROOT_PASSWORD="$MONGO_ROOT_PASSWORD" \
    MONGO_APP_USER="$MONGO_APP_USER" MONGO_APP_PASSWORD="$MONGO_APP_PASSWORD" \
    mongosh "mongodb://${SEED}/" --quiet --eval "$AUTH_JS" 2>/dev/null)
  if echo "$AUTH_RESULT" | grep -q "NEEDS_AUTH"; then
    # Retry authenticated as root — covers the legitimate re-run/rotation case AND
    # recovers from a prior run that enforced auth before the users existed.
    ROOT_URI="mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@${SEED}/?authSource=admin"
    AUTH_RESULT=$(MONGO_ROOT_USER="$MONGO_ROOT_USER" MONGO_ROOT_PASSWORD="$MONGO_ROOT_PASSWORD" \
      MONGO_APP_USER="$MONGO_APP_USER" MONGO_APP_PASSWORD="$MONGO_APP_PASSWORD" \
      mongosh "$ROOT_URI" --quiet --eval "$AUTH_JS" 2>/dev/null)
  fi
  echo "$AUTH_RESULT" | while IFS= read -r line; do
    case "$line" in
      *:NEEDS_AUTH) echo "[setup] WARNING: $line — root credentials didn't work either; auth is enforced with no working user. Disable auth (drop config/keyfile) and re-run to recover." >&2 ;;
      *:err\ *) echo "[setup] WARNING: $line" >&2 ;;
      *) echo "[setup] $line" ;;
    esac
  done
fi
echo "[setup] done"
