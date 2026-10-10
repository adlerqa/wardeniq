"""User accounts, invites, OTP and password-reset codes, and session versioning.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md).
"""

import time

from bson import ObjectId
from pymongo import timeout


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: gives this mixin visibility into the collection attributes and
    # cross-mixin helpers that store/__init__.py's Store actually composes in at
    # runtime (BaseStore.__init__ sets self.projects/self.cases/etc; other mixins
    # add their own methods). At runtime this mixin still inherits only `object`
    # (see the `else` branch) — Store's own MRO (store/__init__.py) is what really
    # provides these at runtime, unchanged from before this TYPE_CHECKING addition.
    from store.base import BaseStore as _Base
else:
    _Base = object


class UsersAuthMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    @staticmethod
    def _user_out(u):
        if not u:
            return None
        return {"id": str(u["_id"]), "email": u.get("email"), "name": u.get("name"),
                "role": u.get("role", "viewer"), "active": u.get("active", True),
                "created_at": u.get("created_at"), "last_login": u.get("last_login"),
                # Invite lifecycle (additive; pre-existing docs default to "active"
                # since a user without invite metadata was created before this field
                # and has effectively already joined).
                "invite_status": u.get("invite_status", "active"),
                "invited_by": u.get("invited_by"), "invited_at": u.get("invited_at"),
                "invite_resolved_at": u.get("invite_resolved_at"),
                "session_version": u.get("session_version", 0),
                # Project access (additive; pre-existing docs have no field → default
                # to all_projects=True so existing users are grandfathered in).
                "all_projects": u.get("all_projects", True),
                "project_ids": u.get("project_ids", []),
                "otp_hash": u.get("otp_hash"), "otp_expires": u.get("otp_expires", 0),
                "otp_attempts": u.get("otp_attempts", 0),
                "reset_hash": u.get("reset_hash"), "reset_expires": u.get("reset_expires", 0),
                "reset_attempts": u.get("reset_attempts", 0),
                # Local admin password (bootstrap "admin" account only). Never
                # surfaced over the API — main.py's _user_public() doesn't whitelist
                # it; this is just the internal store-level representation.
                "password_hash": u.get("password_hash")}

    def get_user(self, uid):
        try:
            return self._user_out(self.users.find_one({"_id": ObjectId(uid)}))
        except Exception:  # noqa: BLE001
            return None

    def get_user_by_email(self, email):
        return self._user_out(self.users.find_one({"email": (email or "").strip().lower()}))

    def list_users(self):
        return [self._user_out(u) for u in self.users.find().sort("created_at", 1)]

    def count_users(self):
        return self.users.count_documents({})

    def has_users(self):
        """Bound public diagnostics when MongoDB is down; never load user data."""
        with timeout(1):
            return self.users.find_one({}, {"_id": 1}) is not None

    def count_active_admins(self):
        return self.users.count_documents({"role": "admin", "active": True})

    def create_user(self, email, name, role="viewer", active=True,
                    invite_status="active", invited_by=None,
                    all_projects=True, project_ids=None):
        """Create a user.

        invite_status:
          * "active"  — self-service / bootstrap sign-in (no pending invite).
          * "pending" — created via admin invite; becomes "active" on first login.
        invited_by is the admin's user id, kept for the audit trail.

        Project access:
          * all_projects=True  → access to every project (default; also how existing
            users and admins behave).
          * all_projects=False → access limited to project_ids (a list of project ids).
        """
        doc = {"email": email.strip().lower(), "name": name, "role": role,
               "active": active, "created_at": time.time(), "last_login": None,
               "invite_status": invite_status, "invited_by": invited_by,
               "invited_at": time.time() if invite_status == "pending" else None,
               "all_projects": bool(all_projects),
               "project_ids": [] if all_projects else list(project_ids or [])}
        res = self.users.insert_one(doc)
        return self.get_user(str(res.inserted_id))

    def set_user_projects(self, uid, all_projects, project_ids=None):
        """Update a user's project access. all_projects=True clears the explicit list."""
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {
            "all_projects": bool(all_projects),
            "project_ids": [] if all_projects else list(project_ids or [])}})
        return self.get_user(uid)

    def accept_invite(self, uid):
        """Explicit accept of a pending invite (from the invited user). Idempotent:
        only a pending invite transitions to accepted."""
        self.users.update_one(
            {"_id": ObjectId(uid), "invite_status": "pending"},
            {"$set": {"invite_status": "accepted", "invite_resolved_at": time.time()}})
        return self.get_user(uid)

    def decline_invite(self, uid):
        """Explicit decline of a pending invite. Marks it declined and deactivates
        the account so the person can't act, but keeps the record for the admin."""
        self.users.update_one(
            {"_id": ObjectId(uid), "invite_status": "pending"},
            {"$set": {"invite_status": "declined", "active": False,
                      "invite_resolved_at": time.time()}})
        return self.get_user(uid)

    def invite_inviter_info(self, uid):
        """Return {email, name} of whoever sent this user's invite, or None."""
        u = self.users.find_one({"_id": ObjectId(uid)}, {"invited_by": 1})
        inviter_id = (u or {}).get("invited_by")
        if not inviter_id:
            return None
        inv = self.get_user(inviter_id)
        return {"email": inv["email"], "name": inv.get("name")} if inv else None

    def bump_session_version(self, uid):
        """Increment a user's session_version, invalidating all their existing
        sessions. Called on role change / disable / forced logout so authorization
        changes take effect immediately (the user must re-authenticate)."""
        self.users.update_one({"_id": ObjectId(uid)}, {"$inc": {"session_version": 1}})
        return self.get_user(uid)

    def set_user_password(self, uid, password_hash):
        """Set (or change) the local admin's password hash. Bumps session_version so
        every OTHER session this user already holds is forced to re-authenticate —
        the caller (main.py) re-issues a fresh cookie for the session making the
        change, so that one isn't logged out."""
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"password_hash": password_hash},
                               "$inc": {"session_version": 1}})
        return self.get_user(uid)

    def update_user(self, uid, fields):
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": fields})
        return self.get_user(uid)

    def delete_user(self, uid):
        self.users.delete_one({"_id": ObjectId(uid)})
        return {"deleted": uid}

    def set_otp(self, uid, otp_hash, expires):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"otp_hash": otp_hash, "otp_expires": expires,
                                        "otp_attempts": 0}})

    def otp_recent_issue_count(self, uid, window_seconds):
        """Record an OTP issuance now and return how many were issued within the last
        `window_seconds` (including this one). Used to rate-limit code requests.
        Keeps only timestamps inside the window."""
        now = time.time()
        cutoff = now - window_seconds
        u = self.users.find_one({"_id": ObjectId(uid)}, {"otp_issues": 1}) or {}
        issues = [t for t in (u.get("otp_issues") or []) if t >= cutoff]
        issues.append(now)
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {"otp_issues": issues[-20:]}})
        return len(issues)

    def inc_otp_attempts(self, uid):
        self.users.update_one({"_id": ObjectId(uid)}, {"$inc": {"otp_attempts": 1}})

    def clear_otp(self, uid):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$unset": {"otp_hash": "", "otp_expires": "", "otp_attempts": ""}})

    def set_reset_code(self, uid, reset_hash, expires):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"reset_hash": reset_hash, "reset_expires": expires,
                                        "reset_attempts": 0}})

    def inc_reset_attempts(self, uid):
        self.users.update_one({"_id": ObjectId(uid)}, {"$inc": {"reset_attempts": 1}})

    def clear_reset_code(self, uid):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$unset": {"reset_hash": "", "reset_expires": "", "reset_attempts": ""}})

    def set_invite_token(self, uid, token_hash, expires):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"invite_token_hash": token_hash,
                                        "invite_token_expires": expires}})

    def get_user_by_invite_token(self, token):
        """Return the (still-valid, unexpired) user whose invite token matches, else
        None. Compares the hash against every user carrying a live token."""
        import auth as _auth  # local import: store.py stays framework-light
        h = _auth.hash_token(token)
        now = time.time()
        u = self.users.find_one({"invite_token_hash": h,
                                 "invite_token_expires": {"$gt": now}})
        return self._user_out(u)

    def clear_invite_token(self, uid):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$unset": {"invite_token_hash": "", "invite_token_expires": ""}})

    def touch_login(self, uid):
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {"last_login": time.time()}})
