"""API tokens for machine authentication (issue #37): a non-human principal
that authenticates via `Authorization: Bearer <token>` instead of a cookie
session, resolved through core/security.py's principal-resolver registry
(see core/token_auth.py). Reuses the existing high-entropy-token hashing
scheme (auth.hash_token/token_matches) rather than inventing one — only the
hash is ever stored, matching store/users_auth.py's invite-token pattern.

Moved out to its own mixin (Phase 5 style, REFACTOR_PLAN.md Option A) rather
than folded into users_auth.py: an API token is not a user account (no email,
no invite lifecycle, no password) even though it shares the project-scoping
shape.
"""

import time

from bson import ObjectId


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: see store/users_auth.py's identical comment for why this mixin
    # still inherits only `object` at runtime (store/__init__.py's Store MRO
    # provides the real collection attributes via BaseStore.__init__).
    from store.base import BaseStore as _Base
else:
    _Base = object


class ApiTokensMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    @staticmethod
    def _token_out(t):
        if not t:
            return None
        return {"id": str(t["_id"]), "name": t.get("name"),
                "role": t.get("role", "viewer"),
                "all_projects": t.get("all_projects", True),
                "project_ids": t.get("project_ids", []),
                "active": t.get("active", True),
                "created_at": t.get("created_at"), "created_by": t.get("created_by"),
                "last_used_at": t.get("last_used_at"),
                "expires_at": t.get("expires_at"),
                "revoked_at": t.get("revoked_at")}

    def create_api_token(self, name, token_hash, role="viewer", all_projects=True,
                         project_ids=None, created_by=None, expires_at=None):
        doc = {"name": name, "token_hash": token_hash, "role": role,
               "all_projects": bool(all_projects),
               "project_ids": [] if all_projects else list(project_ids or []),
               "active": True, "created_at": time.time(), "created_by": created_by,
               "last_used_at": None, "expires_at": expires_at, "revoked_at": None}
        res = self.api_tokens.insert_one(doc)
        return self._token_out(self.api_tokens.find_one({"_id": res.inserted_id}))

    def get_api_token(self, tid):
        try:
            return self._token_out(self.api_tokens.find_one({"_id": ObjectId(tid)}))
        except Exception:  # noqa: BLE001
            return None

    def list_api_tokens(self):
        return [self._token_out(t) for t in self.api_tokens.find().sort("created_at", 1)]

    def get_api_token_by_hash(self, token_hash):
        """Return the token principal for a still-active, unexpired token hash, else
        None. Never raises on a garbage hash — an unknown/revoked/expired token must
        fail closed, never 500 (issue #37 acceptance criteria)."""
        t = self.api_tokens.find_one({"token_hash": token_hash, "active": True})
        if not t:
            return None
        expires_at = t.get("expires_at")
        if expires_at and expires_at < time.time():
            return None
        return self._token_out(t)

    def revoke_api_token(self, tid):
        """Revoke immediately: the resolver re-checks `active` on every request (no
        caching), so this takes effect on the very next call — no session-version
        bump needed (that mechanism is cookie-session-specific)."""
        self.api_tokens.update_one({"_id": ObjectId(tid)},
                                   {"$set": {"active": False, "revoked_at": time.time()}})
        return self.get_api_token(tid)

    def touch_api_token_last_used(self, tid):
        self.api_tokens.update_one({"_id": ObjectId(tid)},
                                   {"$set": {"last_used_at": time.time()}})

    # ---- rate limiting on token-auth failures --------------------------------
    # Keyed by caller IP (an unknown/garbage bearer token has no token doc of its
    # own to attach a counter to). Rolling-window array on a small per-key doc,
    # same approach as users_auth.py's otp_recent_issue_count.
    def api_token_failure_count(self, key, window_seconds):
        """How many token-auth failures from `key` in the last `window_seconds`,
        without recording a new one (a read-only pre-check)."""
        now = time.time()
        cutoff = now - window_seconds
        doc = self.api_token_failures.find_one({"_id": key}) or {}
        return len([t for t in (doc.get("attempts") or []) if t >= cutoff])

    def record_api_token_failure(self, key, window_seconds):
        """Record a token-auth failure from `key` now; returns the resulting count
        within the window (including this one)."""
        now = time.time()
        cutoff = now - window_seconds
        doc = self.api_token_failures.find_one({"_id": key}) or {}
        attempts = [t for t in (doc.get("attempts") or []) if t >= cutoff]
        attempts.append(now)
        self.api_token_failures.update_one(
            {"_id": key}, {"$set": {"attempts": attempts[-50:]}}, upsert=True)
        return len(attempts)
