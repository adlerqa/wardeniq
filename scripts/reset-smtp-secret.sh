#!/usr/bin/env bash
# The SMTP password is stored ENCRYPTED with APP_SECRET (crypto.py). If APP_SECRET
# was rotated, the stored password can no longer be decrypted -> Gmail returns
# "535 Username and Password not accepted". This clears ONLY the stored SMTP
# password so you can re-enter it in Configuration -> Email, which re-encrypts it
# with the current APP_SECRET. If you're locked out because email sign-in is down,
# an admin's one-time code is printed to the server log while SMTP is unusable
# (e.g. `docker logs wardeniq`) — use that to get back in.
#
# It does NOT touch host/port/user/from — you only re-enter the password.
#
# Run with the stack up:  ./scripts/reset-smtp-secret.sh
set -uo pipefail
cd "$(dirname "$0")/.."
DB="${DB_NAME:-wardeniq}"

MONGO="$(docker ps --filter name=warden-mongod1 -q | head -1)"
[ -z "$MONGO" ] && MONGO="$(docker ps --filter name=mongod1 -q | head -1)"
[ -z "$MONGO" ] && MONGO="$(docker ps --filter name=mongo -q | head -1)"
if [ -z "$MONGO" ]; then
  echo "!! Could not find a mongod container. Is the stack up?"; exit 1
fi
echo "==> mongo container: $MONGO  (db: $DB)"

docker exec -i "$MONGO" mongosh --quiet "$DB" <<'JS'
const s = db.settings.findOne({ _id: "app" }) || {};
print("Before:  smtp_host=" + JSON.stringify(s.smtp_host) +
      "  smtp_user=" + JSON.stringify(s.smtp_user) +
      "  smtp_pass_set=" + Boolean(s.smtp_pass_enc));
// Clear the whole SMTP block. You will re-enter all of it in Configuration ->
// Email (re-encrypts with the current APP_SECRET).
const res = db.settings.updateOne(
  { _id: "app" },
  { $unset: { smtp_host: "", smtp_port: "", smtp_user: "",
              smtp_from: "", smtp_pass_enc: "", smtp_tls: "", smtp_ssl: "" } });
print("Cleared SMTP config (matched " + res.matchedCount + ", modified " + res.modifiedCount + ").");
const s2 = db.settings.findOne({ _id: "app" }) || {};
print("After:   smtp_host=" + JSON.stringify(s2.smtp_host) +
      "  smtp_pass_set=" + Boolean(s2.smtp_pass_enc));
JS

echo
echo "==> Done. Next:"
echo "   1) Log in (if locked out, an admin's one-time code is printed to the server log while SMTP is down)"
echo "   2) Configuration -> Email -> re-enter your Gmail App Password -> Save + Test"
