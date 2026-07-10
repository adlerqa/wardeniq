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
echo "[setup] ensuring mongotUser (searchCoordinator)..."
mongosh "mongodb://${SEED}/" --quiet --eval "
const a = db.getSiblingDB('admin');
try { a.createUser({ user:'mongotUser', pwd:'mongotPassword', roles:[{role:'searchCoordinator',db:'admin'}] }); print('user created'); }
catch(e){ if(e.code===51003) print('user exists'); else print('err ' + e.message); }
"
echo "[setup] done"
