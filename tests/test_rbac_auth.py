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
