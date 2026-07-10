"""Phase C — session_version (targeted revocation + role-change propagation).

verify_session now returns (user_id, session_version); a user's session_version is
bumped on role change / disable so their existing sessions are invalidated and the
change takes effect immediately.
"""
import os
import time
import types
from pathlib import Path

import pytest

import auth

_ROOT = Path(__file__).resolve().parents[1]


def _import_main():
    old = Path.cwd()
    try:
        os.chdir(_ROOT / "app")
        import main
        return main
    finally:
        os.chdir(old)


class TestSessionVersionToken:
    def test_roundtrip_carries_sv(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        tok = auth.sign_session("u1", session_version=3)
        assert auth.verify_session(tok) == ("u1", 3)

    def test_default_sv_zero(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        assert auth.verify_session(auth.sign_session("u1")) == ("u1", 0)

    def test_legacy_3part_token_still_verifies(self, monkeypatch):
        # A token minted the OLD way (user_id.exp.sig, no sv) must still validate as
        # sv=0 so existing cookies survive the upgrade.
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        import base64, hashlib, hmac
        exp = int(time.time()) + 600
        msg = f"legacyuser.{exp}"
        sig = hmac.new(auth._secret(), msg.encode(), hashlib.sha256).hexdigest()
        legacy = base64.urlsafe_b64encode(f"{msg}.{sig}".encode()).decode()
        assert auth.verify_session(legacy) == ("legacyuser", 0)

    def test_tampered_sv_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        import base64
        tok = auth.sign_session("u1", session_version=1)
        raw = base64.urlsafe_b64decode(tok.encode()).decode()
        uid, sv, exp, sig = raw.rsplit(".", 3)
        forged = f"{uid}.{int(sv)+9}.{exp}.{sig}"   # bump sv without re-signing
        bad = base64.urlsafe_b64encode(forged.encode()).decode()
        assert auth.verify_session(bad) is None

    def test_expired_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        assert auth.verify_session(auth.sign_session("u1", 2, ttl=-1)) is None


class TestPatchUserBumpsSessionVersion:
    """patch_user must bump session_version on role/active change (not name-only)."""

    @pytest.fixture
    def env(self, monkeypatch):
        m = _import_main()
        state = {"sv": 0, "role": "viewer", "active": True, "name": "X"}

        class FS:
            def get_user(self, uid):
                return {"id": "u1", "email": "u@e.com", "name": state["name"],
                        "role": state["role"], "active": state["active"],
                        "session_version": state["sv"], "invite_status": "active",
                        "invited_at": None}
            def count_active_admins(self):
                return 5   # never trip the last-admin guard here
            def update_user(self, uid, upd):
                state.update(upd)
                return self.get_user(uid)
            def bump_session_version(self, uid):
                state["sv"] += 1
                return self.get_user(uid)

        monkeypatch.setattr(m, "store", FS())
        return m, state

    def _req(self):
        return types.SimpleNamespace(state=types.SimpleNamespace(user={"id": "admin"}))

    def test_role_change_bumps_sv(self, env):
        m, state = env
        assert state["sv"] == 0
        m.patch_user("u1", m.UserPatch(role="editor"), self._req())
        assert state["role"] == "editor" and state["sv"] == 1

    def test_disable_bumps_sv(self, env):
        m, state = env
        m.patch_user("u1", m.UserPatch(active=False), self._req())
        assert state["active"] is False and state["sv"] == 1

    def test_name_only_does_not_bump_sv(self, env):
        m, state = env
        m.patch_user("u1", m.UserPatch(name="New Name"), self._req())
        assert state["name"] == "New Name" and state["sv"] == 0

    def test_same_role_noop_does_not_bump(self, env):
        m, state = env
        m.patch_user("u1", m.UserPatch(role="viewer"), self._req())
        assert state["sv"] == 0
