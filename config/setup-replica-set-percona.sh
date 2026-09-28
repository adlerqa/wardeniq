#!/bin/bash
# Validation-only setup for the Percona compose profile (issue #41): initiates a
# single-node replica set and creates the searchCoordinator user mongot syncs as.
# Single-node mirrors config/setup-replica-set.sh's user-provisioning logic but
# skips the 3-member wiring — this stack validates search behavior, not HA.
set -e
SEED="mongod-percona.warden-net-percona:27017"

echo "[setup-percona] waiting for $SEED ..."
until mongosh "mongodb://$SEED/" --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
  sleep 2
done

RS=$(mongosh "mongodb://${SEED}/" --quiet --eval "
try { rs.status(); print('INITIALIZED'); }
catch (e) { if (e.code===94 || e.message.includes('no replset config')) print('NOT_INITIALIZED'); else print('ERR ' + e.message); }
" | tail -1)

if [ "$RS" = "NOT_INITIALIZED" ]; then
  echo "[setup-percona] initiating single-node replica set rs0..."
  mongosh "mongodb://${SEED}/" --quiet --eval "rs.initiate({ _id: 'rs0', members: [{ _id: 0, host: '${SEED}' }] });"
else
  echo "[setup-percona] replica set state: $RS"
fi

echo "[setup-percona] waiting for PRIMARY..."
for i in $(seq 1 60); do
  P=$(mongosh "mongodb://${SEED}/" --quiet --eval "try{print(rs.status().myState===1?'P':'N')}catch(e){print('E')}" | tail -1)
  [ "$P" = "P" ] && { echo "[setup-percona] PRIMARY ready"; break; }
  sleep 2
done

MONGOT_PW="$(tr -d '\r\n' < /run/secrets/mongot-pw)"
echo "[setup-percona] ensuring mongotUser (searchCoordinator)..."
mongosh "mongodb://${SEED}/" --quiet --eval "
const a = db.getSiblingDB('admin');
try {
  a.createUser({ user: 'mongotUser', pwd: '$MONGOT_PW', roles: [{ role: 'searchCoordinator', db: 'admin' }] });
  print('created');
} catch(e) {
  if (e.code === 51003) { a.updateUser('mongotUser', { pwd: '$MONGOT_PW' }); print('synced'); }
  else print('err ' + e.message);
}
"
echo "[setup-percona] done"
