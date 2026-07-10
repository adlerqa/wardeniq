#!/usr/bin/env bash
# One-shot cleanup after the RBAC fixes:
#   1. Removes the corrupt admin row whose email is the leaked .env comment
#      ("# seeded as the first admin ...").
#   2. Prints the remaining users so you can confirm the state.
#
# Run AFTER rebuilding the app (docker compose up -d --build) and with the stack up.
# Usage:  ./scripts/fix-rbac-users.sh
set -uo pipefail
cd "$(dirname "$0")/.."

DB="${DB_NAME:-wardeniq}"

# Find the primary mongod container (the app connects to the replica set primary).
MONGO_CONTAINER="$(docker compose ps -q mongod1 2>/dev/null)"
[ -z "$MONGO_CONTAINER" ] && MONGO_CONTAINER="$(docker ps --filter name=mongod1 -q | head -1)"
[ -z "$MONGO_CONTAINER" ] && MONGO_CONTAINER="$(docker ps --filter name=mongo -q | head -1)"

if [ -z "$MONGO_CONTAINER" ]; then
  echo "!! Could not find a mongod container. Is the stack running (./run.sh)?"
  exit 1
fi
echo "==> using mongo container: $MONGO_CONTAINER  (db: $DB)"

# Delete any user whose email or name starts with '#' (the leaked comment), or that
# is not a syntactically valid email. This is safe: real users have real emails.
docker exec -i "$MONGO_CONTAINER" mongosh --quiet "$DB" <<'JS'
const bad = db.users.find({
  $or: [
    { email: /^\s*#/ },
    { email: { $not: /@/ } },
    { name:  /^\s*#/ }
  ]
}).toArray();

if (bad.length === 0) {
  print("No corrupt user rows found. Nothing to delete.");
} else {
  bad.forEach(u => print("Deleting corrupt user: _id=" + u._id + " email=" + JSON.stringify(u.email)));
  const res = db.users.deleteMany({
    $or: [
      { email: /^\s*#/ },
      { email: { $not: /@/ } },
      { name:  /^\s*#/ }
    ]
  });
  print("Deleted " + res.deletedCount + " row(s).");
}

print("\n==> Remaining users:");
db.users.find({}, { email: 1, name: 1, role: 1, active: 1, invite_status: 1 })
  .forEach(u => printjson(u));

const admins = db.users.countDocuments({ role: "admin", active: true });
print("\nActive admins: " + admins);
if (admins === 0) {
  print("!! No active admin left. Sign in with the ADMIN_EMAIL from your .env —");
  print("   the app seeds it as admin on startup, or the first code-requester becomes admin.");
}
JS

echo
echo "==> Done. If no admin remains, restart the app so ADMIN_EMAIL is re-seeded:"
echo "    docker compose restart wardeniq"
