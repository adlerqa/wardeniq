"""Invite Accept/Decline + my-invite view (single-tenant invite workflow).

Login no longer auto-accepts a pending invite; the invited user sees a banner and
explicitly Accepts (status -> accepted) or Declines (status -> declined + account
deactivated). Handlers are called directly with a fake store and a stubbed session.
"""
import os
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _import_main():
    old = Path.cwd()
    try:
        os.chdir(_ROOT / "app")
        import main
        return main
    finally:
        os.chdir(old)


class FakeUsers:
    def __init__(self):
        self.docs = {}
        self._n = 0
        self.otps = {}

    def get_settings(self):
        return {}

    def get_user(self, uid):
        return self.docs.get(uid)

    def get_user_by_email(self, e):
        e = (e or "").strip().lower()
        return next((u for u in self.docs.values() if u["email"] == e), None)

    def get_project(self, pid):
        return {"id": pid}

    def add_audit(self, *a, **k):
        return True

    def create_user(self, email, name, role="viewer", active=True,
                    invite_status="active", invited_by=None,
                    all_projects=True, project_ids=None):
        self._n += 1
        uid = f"u{self._n}"
        self.docs[uid] = {"id": uid, "email": email.strip().lower(), "name": name,
                          "role": role, "active": active, "created_at": 1.0,
                          "last_login": None, "invite_status": invite_status,
                          "invited_by": invited_by,
                          "invited_at": 2.0 if invite_status == "pending" else None,
                          "invite_resolved_at": None, "session_version": 0,
                          "all_projects": bool(all_projects),
                          "project_ids": [] if all_projects else list(project_ids or [])}
        return self.docs[uid]

    def set_otp(self, uid, h, e):
        self.otps[uid] = (h, e)

    def clear_otp(self, uid):
        self.otps.pop(uid, None)

    def accept_invite(self, uid):
        u = self.docs.get(uid)
        if u and u["invite_status"] == "pending":
            u["invite_status"] = "accepted"; u["invite_resolved_at"] = 9.0
        return u

    def decline_invite(self, uid):
        u = self.docs.get(uid)
        if u and u["invite_status"] == "pending":
            u["invite_status"] = "declined"; u["active"] = False; u["invite_resolved_at"] = 9.0
        return u

    def invite_inviter_info(self, uid):
        u = self.docs.get(uid)
        inv = self.docs.get((u or {}).get("invited_by"))
        return {"email": inv["email"], "name": inv.get("name")} if inv else None

    def set_invite_token(self, uid, token_hash, expires):
        if uid in self.docs:
            self.docs[uid]["invite_token_hash"] = token_hash
            self.docs[uid]["invite_token_expires"] = expires

    def clear_invite_token(self, uid):
        if uid in self.docs:
            self.docs[uid].pop("invite_token_hash", None)
            self.docs[uid].pop("invite_token_expires", None)

    def get_user_by_invite_token(self, token):
        import auth as _auth
        h = _auth.hash_token(token)
        for u in self.docs.values():
            if u.get("invite_token_hash") == h:
                return u
        return None



class Req:
    def __init__(self, user=None):
        self.state = types.SimpleNamespace(user=user)


class Resp:
    def __init__(self):
        self.deleted = []

    def delete_cookie(self, name, path="/"):
        self.deleted.append(name)


@pytest.fixture
def env(monkeypatch):
    m = _import_main()
    fake = FakeUsers()
    monkeypatch.setattr(m, "store", fake)
    monkeypatch.setattr(m, "_deliver_otp", lambda *a, **k: ("sent", ""))
    admin = fake.create_user("admin@x.com", "Admin", "admin")
    inv = m.invite_user(m.UserIn(email="new@x.com", name="New", role="viewer"),
                        Req(user={"id": admin["id"]}))
    return m, fake, admin, inv["user"]


class TestMyInviteView:
    def test_pending_invite_shows_inviter_role_workspace(self, env, monkeypatch):
        m, fake, admin, u = env
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(u["id"]))
        inv = m.my_invite(Req())["invite"]
        assert inv["pending"] is True
        assert inv["role"] == "viewer"
        assert inv["invited_by"]["email"] == "admin@x.com"
        assert inv["workspace"]
        assert inv["invited_at"] == 2.0

    def test_non_pending_user_has_no_pending_invite(self, env, monkeypatch):
        m, fake, admin, u = env
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(admin["id"]))
        assert m.my_invite(Req())["invite"]["pending"] is False


class TestAccept:
    def test_accept_flips_to_accepted(self, env, monkeypatch):
        m, fake, admin, u = env
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(u["id"]))
        r = m.accept_my_invite(Req())
        assert fake.docs[u["id"]]["invite_status"] == "accepted"
        assert r["invite"]["pending"] is False
        assert r["user"]["invite_status"] == "accepted"

    def test_accept_idempotent(self, env, monkeypatch):
        m, fake, admin, u = env
        fake.docs[u["id"]]["invite_status"] = "accepted"
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(u["id"]))
        assert m.accept_my_invite(Req())["invite"]["pending"] is False


class TestDecline:
    def test_decline_deactivates_and_clears_cookie(self, env, monkeypatch):
        m, fake, admin, u = env
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(u["id"]))
        resp = Resp()
        r = m.decline_my_invite(Req(), resp)
        assert r["declined"] is True
        assert fake.docs[u["id"]]["invite_status"] == "declined"
        assert fake.docs[u["id"]]["active"] is False
        assert m.auth.SESSION_COOKIE in resp.deleted

    def test_decline_when_not_pending_is_noop(self, env, monkeypatch):
        m, fake, admin, u = env
        fake.docs[u["id"]]["invite_status"] = "accepted"
        monkeypatch.setattr(m, "_session_user", lambda req: fake.get_user(u["id"]))
        assert m.decline_my_invite(Req(), Resp())["declined"] is False


class TestLoginDoesNotAutoAccept:
    def test_invited_user_stays_pending_after_invite(self, env):
        m, fake, admin, u = env
        assert fake.docs[u["id"]]["invite_status"] == "pending"
