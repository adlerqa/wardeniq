"""Phase B — invite / OTP flow tests.

Exercises the invite/resend/cancel handlers and accept-on-login with a fake store
and a stubbed OTP delivery (no SMTP). Handlers are plain functions, called directly
with a fake Request carrying request.state.user (as the auth_gateway would set).
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
    """In-memory stand-in for the parts of store.Store's user API used here.
    Returns dicts already in `_user_out` shape (invite fields included)."""
    def __init__(self):
        self.docs = {}
        self._n = 0
        self.otps = {}

    def get_settings(self):
        return {}

    def get_user(self, uid):
        return self.docs.get(uid)

    def get_user_by_email(self, email):
        e = (email or "").strip().lower()
        return next((u for u in self.docs.values() if u["email"] == e), None)

    def count_active_admins(self):
        return sum(1 for u in self.docs.values()
                   if u.get("role") == "admin" and u.get("active"))

    def get_project(self, pid):
        return {"id": pid}   # pretend any project id exists

    def add_audit(self, *a, **k):
        return True          # audit is best-effort; no-op in tests

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
                          "all_projects": bool(all_projects),
                          "project_ids": [] if all_projects else list(project_ids or [])}
        return self.docs[uid]

    def set_otp(self, uid, h, exp):
        self.otps[uid] = (h, exp)

    def clear_otp(self, uid):
        self.otps.pop(uid, None)

    def delete_user(self, uid):
        self.docs.pop(uid, None)
        return {"deleted": uid}

    def mark_invite_accepted(self, uid):
        u = self.docs.get(uid)
        if u and u.get("invite_status") == "pending":
            u["invite_status"] = "active"

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



class FakeReq:
    def __init__(self, user=None):
        self.state = types.SimpleNamespace(user=user)


@pytest.fixture
def main_mod(monkeypatch):
    m = _import_main()
    fake = FakeUsers()
    monkeypatch.setattr(m, "store", fake)
    monkeypatch.setattr(m, "_smtp_cfg", lambda: {"host": "localhost"})
    import email_send
    monkeypatch.setattr(email_send, "send_invite", lambda *a, **k: (True, ""))
    return m, fake


class TestInvite:
    def test_invite_creates_pending_and_issues_code(self, main_mod, monkeypatch):
        m, fake = main_mod
        body = m.UserIn(email="Newbie@Example.com", name="New", role="editor")
        resp = m.invite_user(body, FakeReq(user={"id": "admin1"}))
        u = resp["user"]
        assert u["invite_status"] == "pending"
        assert u["email"] == "newbie@example.com"
        assert u["role"] == "editor"
        assert resp["delivery"] == "sent"
        assert "Invite sent" in resp["message"]
        assert fake.docs[u["id"]]["invite_token_hash"] is not None
        assert fake.docs[u["id"]]["invited_by"] == "admin1"

    def test_invite_refused_reports_honestly(self, main_mod, monkeypatch):
        m, fake = main_mod
        monkeypatch.setattr(m, "_smtp_cfg", lambda: None)
        resp = m.invite_user(m.UserIn(email="r@e.com"), FakeReq(user={"id": "a"}))
        assert resp["delivery"] == "refused"
        assert "no invitation email was sent" in resp["message"]
        assert "dev_code" not in resp        # never leak a code we didn't send
        assert fake.get_user_by_email("r@e.com") is not None

    def test_invite_rejects_bad_email(self, main_mod):
        m, _ = main_mod
        with pytest.raises(m.HTTPException) as ei:
            m.invite_user(m.UserIn(email="not-an-email"), FakeReq(user={"id": "a"}))
        assert ei.value.status_code == 400

    def test_invite_rejects_duplicate(self, main_mod, monkeypatch):
        m, fake = main_mod
        m.invite_user(m.UserIn(email="dup@e.com"), FakeReq(user={"id": "a"}))
        with pytest.raises(m.HTTPException) as ei:
            m.invite_user(m.UserIn(email="dup@e.com"), FakeReq(user={"id": "a"}))
        assert ei.value.status_code == 409


class TestResendCancel:
    def _pending(self, m, fake, monkeypatch):
        return m.invite_user(m.UserIn(email="p@e.com"), FakeReq(user={"id": "a"}))["user"]

    def test_resend_reissues_code(self, main_mod, monkeypatch):
        m, fake = main_mod
        u = self._pending(m, fake, monkeypatch)
        old = fake.docs[u["id"]]["invite_token_hash"]
        resp = m.resend_invite(u["id"], FakeReq(user={"id": "admin1"}))
        assert resp["delivery"] == "sent"
        assert fake.docs[u["id"]]["invite_token_hash"] != old

    def test_resend_disabled_user_rejected(self, main_mod, monkeypatch):
        m, fake = main_mod
        u = self._pending(m, fake, monkeypatch)
        fake.docs[u["id"]]["active"] = False
        with pytest.raises(m.HTTPException) as ei:
            m.resend_invite(u["id"], FakeReq(user={"id": "admin1"}))
        assert ei.value.status_code == 400

    def test_resend_unknown_user(self, main_mod):
        m, _ = main_mod
        with pytest.raises(m.HTTPException) as ei:
            m.resend_invite("nope", FakeReq(user={"id": "admin1"}))
        assert ei.value.status_code == 404

    def test_cancel_pending_deletes(self, main_mod, monkeypatch):
        m, fake = main_mod
        u = self._pending(m, fake, monkeypatch)
        resp = m.cancel_invite(u["id"])
        assert resp == {"cancelled": u["id"]}
        assert fake.get_user(u["id"]) is None
        assert fake.docs.get(u["id"]) is None

    def test_cancel_active_user_rejected(self, main_mod, monkeypatch):
        m, fake = main_mod
        u = self._pending(m, fake, monkeypatch)
        fake.docs[u["id"]]["invite_status"] = "active"
        with pytest.raises(m.HTTPException) as ei:
            m.cancel_invite(u["id"])
        assert ei.value.status_code == 400
        assert fake.get_user(u["id"]) is not None


class TestAcceptOnLogin:
    def test_mark_invite_accepted_flips_pending(self, main_mod, monkeypatch):
        m, fake = main_mod
        u = m.invite_user(m.UserIn(email="join@e.com"), FakeReq(user={"id": "a"}))["user"]
        assert fake.docs[u["id"]]["invite_status"] == "pending"
        fake.mark_invite_accepted(u["id"])
        assert fake.docs[u["id"]]["invite_status"] == "active"
        fake.mark_invite_accepted(u["id"])   # idempotent
        assert fake.docs[u["id"]]["invite_status"] == "active"

