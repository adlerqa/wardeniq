"""RBAC / auth unit tests.

Covers the authorization primitives that had zero test coverage before the RBAC
hardening pass:
  * auth.py — role ranks, session sign/verify, OTP hashing, weak-secret detection
  * main.py — _min_role gateway rules incl. the admin-secret-write elevation

All import-light: auth.py is pure; main.py's Store uses a lazy MongoClient so it
imports without a live DB (same approach as test_sheet_import_main_helpers.py).
"""
import os
from pathlib import Path

import pytest

import auth

_ROOT = Path(__file__).resolve().parents[1]


def _import_main():
    old = Path.cwd()
    try:
        os.chdir(_ROOT / "app")
        import main  # noqa: WPS433
        return main
    finally:
        os.chdir(old)


# --------------------------------------------------------------------------- has_role
class TestHasRole:
    def test_rank_ordering(self):
        assert auth.ROLE_RANK == {"viewer": 1, "editor": 2, "admin": 3}

    @pytest.mark.parametrize("role,minimum,expected", [
        ("admin", "admin", True), ("admin", "editor", True), ("admin", "viewer", True),
        ("editor", "admin", False), ("editor", "editor", True), ("editor", "viewer", True),
        ("viewer", "editor", False), ("viewer", "viewer", True),
    ])
    def test_has_role(self, role, minimum, expected):
        assert auth.has_role(role, minimum) is expected

    def test_unknown_role_denied(self):
        assert auth.has_role("superuser", "viewer") is False
        assert auth.has_role(None, "viewer") is False

    def test_unknown_minimum_denied(self):
        # An unrecognized minimum fails closed (rank default 99).
        assert auth.has_role("admin", "root") is False


# --------------------------------------------------------------------------- sessions
class TestSessions:
    # verify_session returns (user_id, session_version) since the Phase C revocation
    # work; sign_session defaults session_version to 0.
    def test_roundtrip(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        assert auth.verify_session(auth.sign_session("user-123")) == ("user-123", 0)

    def test_expired_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        assert auth.verify_session(auth.sign_session("u", ttl=-1)) is None

    def test_tampered_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        tok = auth.sign_session("user-123")
        bad = tok[:-1] + ("A" if tok[-1] != "A" else "B")
        assert auth.verify_session(bad) is None

    def test_rotation_invalidates(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "secret-one-aaaaaaaaaaaa")
        tok = auth.sign_session("user-123")
        assert auth.verify_session(tok) == ("user-123", 0)
        monkeypatch.setenv("APP_SECRET", "secret-two-bbbbbbbbbbbb")
        assert auth.verify_session(tok) is None

    def test_garbage(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        assert auth.verify_session("") is None
        assert auth.verify_session("not-a-token") is None


# --------------------------------------------------------------------------- OTP
class TestOtp:
    def test_six_digits(self):
        for _ in range(20):
            c = auth.gen_otp()
            assert len(c) == 6 and c.isdigit()

    def test_matches(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        h = auth.hash_otp("123456")
        assert auth.otp_matches(h, "123456") is True
        assert auth.otp_matches(h, "000000") is False

    def test_depends_on_secret(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "secret-one-aaaaaaaaaaaa")
        h1 = auth.hash_otp("123456")
        monkeypatch.setenv("APP_SECRET", "secret-two-bbbbbbbbbbbb")
        assert auth.otp_matches(h1, "123456") is False

    def test_empty_hash(self):
        assert auth.otp_matches("", "123456") is False


# --------------------------------------------------------------------------- weak secret
class TestWeakSecret:
    @pytest.mark.parametrize("value", [
        None, "", "mongoT-qa-dev-key-change-me", "change-me-in-production",
        "change-me", "changeme", "short", "MongoT-QA-Dev-Key-Change-Me",
    ])
    def test_weak(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv("APP_SECRET", raising=False)
        else:
            monkeypatch.setenv("APP_SECRET", value)
        assert auth.secret_is_weak() is True

    @pytest.mark.parametrize("value", ["a-genuinely-strong-secret-2026", "0123456789abcdef"])
    def test_strong(self, monkeypatch, value):
        monkeypatch.setenv("APP_SECRET", value)
        assert auth.secret_is_weak() is False


# --------------------------------------------------------------------------- _min_role gateway
class TestMinRole:
    @classmethod
    def setup_class(cls):
        cls.main = _import_main()

    def test_get_is_viewer(self):
        assert self.main._min_role("GET", "/api/projects") == "viewer"
        assert self.main._min_role("GET", "/api/features/abc") == "viewer"

    @pytest.mark.parametrize("method", ["PUT", "PATCH"])
    def test_ordinary_write_editor(self, method):
        # feature rename/patch is an editor write; DELETE is now admin-only (see
        # test_rbac_hardening.py) — hardening pass moved destructive ops to admin.
        assert self.main._min_role(method, "/api/features/abc") == "editor"

    def test_ordinary_post_editor(self):
        assert self.main._min_role("POST", "/api/features/abc/validator") == "editor"

    def test_viewer_post_ok(self):
        assert self.main._min_role("POST", "/api/retrieve") == "viewer"

    @pytest.mark.parametrize("path", [
        "/api/users", "/api/users/abc", "/api/settings",
        "/api/llm/test", "/api/jira/test", "/api/smtp/test",
    ])
    def test_admin_paths(self, path):
        assert self.main._min_role("POST", path) == "admin"

    def test_admin_read(self):
        assert self.main._min_role("GET", "/api/users") == "admin"

    # NEW: secret-handling project routes elevated to admin on writes
    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_git_pat_write_admin(self, method):
        assert self.main._min_role(method, "/api/projects/p1/github/pat") == "admin"
        assert self.main._min_role(method, "/api/projects/p1/gitlab/pat") == "admin"

    def test_repo_create_admin(self):
        assert self.main._min_role("POST", "/api/projects/p1/repos") == "admin"

    # status GETs stay viewer; operational sub-routes stay editor
    def test_pat_status_read_viewer(self):
        assert self.main._min_role("GET", "/api/projects/p1/github/pat") == "viewer"
        assert self.main._min_role("GET", "/api/projects/p1/gitlab/pat") == "viewer"

    def test_repo_ops_stay_editor(self):
        assert self.main._min_role("POST", "/api/projects/p1/repos/r1/rescan") == "editor"
        assert self.main._min_role("POST", "/api/projects/p1/repos/r1/scan/reset") == "editor"
        assert self.main._min_role("GET", "/api/projects/p1/repos") == "viewer"

    def test_is_public(self):
        assert self.main._is_public("/") is True
        assert self.main._is_public("/api/auth/request-otp") is True
        assert self.main._is_public("/assets/index-abc123.js") is True
        assert self.main._is_public("/api/projects") is False
        assert self.main._is_public("/api/auth/smtp-status") is True
        assert self.main._is_public("/api/auth/login-password") is True


# --------------------------------------------------------------------------- smtp & password login
class TestSmtpAndPasswordLogin:
    @classmethod
    def setup_class(cls):
        cls.main = _import_main()

    def test_smtp_status_endpoint(self, monkeypatch):
        # 1. When SMTP is configured:
        monkeypatch.setattr(self.main, "_smtp_cfg", lambda: {"host": "smtp.gmail.com"})
        r = self.main.smtp_status()
        assert r == {"smtp_setup": True}

        # 2. When SMTP is not configured:
        monkeypatch.setattr(self.main, "_smtp_cfg", lambda: None)
        r = self.main.smtp_status()
        assert r == {"smtp_setup": False}

    def test_login_password_endpoint_flow(self, monkeypatch):
        # Mock store
        class FakeStore:
            def __init__(self):
                self.users = {}
            def get_user_by_email(self, email):
                return self.users.get(email)
            def create_user(self, email, name, role):
                u = {"id": "admin-id-123", "email": email, "name": name, "role": role, "active": True}
                self.users[email] = u
                return u
            def get_user(self, uid):
                for u in self.users.values():
                    if u["id"] == uid:
                        return u
                return None
            def touch_login(self, uid):
                pass

        fs = FakeStore()
        monkeypatch.setattr(self.main, "store", fs)

        # Mock Response
        class FakeResponse:
            def __init__(self):
                self.cookies = {}
            def set_cookie(self, name, value, **kwargs):
                self.cookies[name] = value

        # 1. When SMTP is configured, password login must fail
        monkeypatch.setattr(self.main, "_smtp_cfg", lambda: {"host": "smtp.gmail.com"})
        body = self.main.LoginPasswordIn(username="admin", password="admin123")
        with pytest.raises(self.main.HTTPException) as exc:
            self.main.login_password(body, FakeResponse())
        assert exc.value.status_code == 400
        assert "Password login is disabled" in exc.value.detail

        # 2. When SMTP is not configured:
        monkeypatch.setattr(self.main, "_smtp_cfg", lambda: None)

        # 2a. Wrong credentials must fail
        body = self.main.LoginPasswordIn(username="admin", password="wrongpassword")
        with pytest.raises(self.main.HTTPException) as exc:
            self.main.login_password(body, FakeResponse())
        assert exc.value.status_code == 401
        assert "Invalid username or password" in exc.value.detail

        # 2b. Correct credentials must succeed and bootstrap user
        body = self.main.LoginPasswordIn(username="admin", password="admin123")
        resp = FakeResponse()
        r = self.main.login_password(body, resp)
        assert r["user"]["email"] == "admin"
        assert r["user"]["role"] == "admin"
        assert self.main.auth.SESSION_COOKIE in resp.cookies

    def test_request_otp_first_run_with_admin(self, monkeypatch):
        class FakeStore:
            def __init__(self):
                self.users = {}
            def get_user_by_email(self, email):
                return self.users.get(email)
            def create_user(self, email, name, role):
                u = {"id": "uid-" + email, "email": email, "name": name, "role": role, "active": True}
                self.users[email] = u
                return u
            def list_users(self):
                return list(self.users.values())
            def otp_recent_issue_count(self, uid, w):
                return 0
            def set_otp(self, uid, h, exp):
                pass

        fs = FakeStore()
        monkeypatch.setattr(self.main, "store", fs)
        monkeypatch.setattr(self.main, "_deliver_otp", lambda *a, **k: ("sent", ""))

        # Create the local admin user (non-valid email)
        fs.create_user("admin", "Admin", "admin")

        # Request OTP for a new valid email
        body = self.main.OtpRequestIn(email="samyak@adlerqa.in")
        r = self.main.request_otp(body)

        # It should bootstrap the user and return sent
        assert r["sent"] is True
        assert r["bootstrap"] is True
        assert fs.get_user_by_email("samyak@adlerqa.in") is not None

    def test_verify_otp_migrates_admin_placeholder(self, monkeypatch):
        class FakeStore:
            def __init__(self):
                self.users = {}
            def get_user_by_email(self, email):
                return self.users.get(email)
            def create_user(self, email, name, role):
                u = {"id": "uid-" + email, "email": email, "name": name, "role": role, "active": True,
                     "otp_hash": None, "otp_expires": 0, "otp_attempts": 0}
                self.users[email] = u
                return u
            def list_users(self):
                return list(self.users.values())
            def get_user(self, uid):
                for u in self.users.values():
                    if u["id"] == uid:
                        return u
                return None
            def update_user(self, uid, fields):
                u = self.get_user(uid)
                if u:
                    self.users.pop(u["email"], None)
                    u.update(fields)
                    self.users[u["email"]] = u
                return u
            def set_otp(self, uid, h, exp):
                u = self.get_user(uid)
                if u:
                    u["otp_hash"] = h
                    u["otp_expires"] = exp
            def clear_otp(self, uid):
                u = self.get_user(uid)
                if u:
                    u["otp_hash"] = None
                    u["otp_attempts"] = 0
            def touch_login(self, uid):
                pass
            def inc_otp_attempts(self, uid):
                pass

        fs = FakeStore()
        monkeypatch.setattr(self.main, "store", fs)

        # Create admin user
        admin = fs.create_user("admin", "Admin", "admin")

        # Set fake OTP code on admin
        import time
        code = "123456"
        h = self.main.auth.hash_otp(code)
        fs.set_otp(admin["id"], h, time.time() + 600)

        # Mock Response
        class FakeResponse:
            def __init__(self):
                self.cookies = {}
            def set_cookie(self, name, value, **kwargs):
                self.cookies[name] = value

        # Call verify_otp with real email
        body = self.main.OtpVerifyIn(email="samyak@adlerqa.in", code=code)
        resp = FakeResponse()
        r = self.main.verify_otp(body, resp)

        # Check that it migrated admin to samyak@adlerqa.in
        assert r["user"]["email"] == "samyak@adlerqa.in"
        assert fs.get_user_by_email("samyak@adlerqa.in") is not None
        assert fs.get_user_by_email("admin") is None
