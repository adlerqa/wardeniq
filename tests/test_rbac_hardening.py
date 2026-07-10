"""RBAC hardening — email validation, admin-only destructive routes, OTP throttle, audit."""
import os
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


M = _import_main()


class TestEmailValidation:
    @pytest.mark.parametrize("e", ["a@b.com", "first.last@sub.example.co", "x+y@z.io"])
    def test_valid(self, e):
        assert auth.is_valid_email(e) is True

    @pytest.mark.parametrize("e", ["", "notanemail", "@b.com", "a@", "a@b", "a b@c.com",
                                   "# seeded as the first admin on startup; if blank, the", None])
    def test_invalid(self, e):
        assert auth.is_valid_email(e) is False


class TestAdminOnlyRoutes:
    @pytest.mark.parametrize("m,p", [
        ("DELETE", "/api/projects/p1"), ("DELETE", "/api/repos/r1"),
        ("DELETE", "/api/features/f1"), ("DELETE", "/api/test-cases/c1"),
        ("DELETE", "/api/steps/s1"), ("DELETE", "/api/test-cycles/cy1"),
        ("DELETE", "/api/cycle-templates/t1"), ("POST", "/api/develop"),
        ("POST", "/api/code-analysis"), ("POST", "/api/analyze"),
        ("POST", "/api/repos/r1/watch")])
    def test_destructive_is_admin(self, m, p):
        assert M._min_role(m, p) == "admin"

    @pytest.mark.parametrize("m,p", [
        ("PATCH", "/api/features/f1"),
        ("PUT", "/api/test-cases/c1"),
        ("POST", "/api/features/f1/validator"),
        ("POST", "/api/test-cases"),
        ("POST", "/api/repos/r1/sync")])
    def test_normal_writes_stay_editor(self, m, p):
        assert M._min_role(m, p) == "editor"

    def test_reads_stay_viewer(self):
        assert M._min_role("GET", "/api/projects/p1") == "viewer"
        assert M._min_role("GET", "/api/features/f1") == "viewer"


class TestOtpThrottle:
    def test_throttle_after_limit(self, monkeypatch):
        state = {"count": 0, "otp_set": 0}

        class FS:
            def get_user_by_email(self, e):
                return {"id": "u1", "email": e, "active": True, "name": "U"}
            def count_users(self):
                return 1
            def otp_recent_issue_count(self, uid, w):
                state["count"] += 1
                return state["count"]
            def set_otp(self, *a):
                state["otp_set"] += 1

        monkeypatch.setattr(M, "store", FS())
        monkeypatch.setattr(M, "OTP_MAX_PER_WINDOW", 2)
        monkeypatch.setattr(M, "_deliver_otp", lambda *a, **k: ("sent", ""))
        body = M.OtpRequestIn(email="x@y.com")
        M.request_otp(body)
        M.request_otp(body)
        assert state["otp_set"] == 2
        r = M.request_otp(body)          # count 3 > limit 2
        assert r == {"sent": True} and state["otp_set"] == 2


class TestAudit:
    def test_add_and_list_roundtrip(self):
        class FakeCol:
            def __init__(self):
                self.docs = []
            def insert_one(self, d):
                self.docs.append(dict(d))
            def find(self, q):
                res = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]

                class C:
                    def __init__(s, r):
                        s.r = r
                    def sort(s, *a):
                        return s
                    def limit(s, n):
                        for i, d in enumerate(s.r):
                            d = dict(d); d["_id"] = i; yield d
                return C(res)

        from store import Store
        st = Store.__new__(Store)
        object.__setattr__(st, "db", {"audit_logs": FakeCol()})
        st.add_audit("user.deleted", actor={"id": "a1", "email": "admin@x.com"}, target="bob@x.com")
        logs = st.list_audit(limit=10)
        assert len(logs) == 1
        assert logs[0]["action"] == "user.deleted"
        assert logs[0]["actor_email"] == "admin@x.com"
        assert logs[0]["target"] == "bob@x.com"
