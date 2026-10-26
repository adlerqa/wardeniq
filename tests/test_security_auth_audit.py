"""Master-reset restrictions, sign-in auditing, the server-side invite gate and the
audit actor recorded for API-token requests."""
import time

import pytest

mongomock = pytest.importorskip("mongomock")

import auth  # noqa: E402
import main  # noqa: E402
import store.base as store_base  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from store import Store  # noqa: E402

routes = main._auth_routes
client = TestClient(main.app)
GOOD = "Correct-horse-9"


@pytest.fixture
def audits(monkeypatch):
    rec = []
    monkeypatch.setattr(main.store, "add_audit",
                        lambda action, **kw: rec.append({"action": action, **kw}) or True)
    return rec


@pytest.fixture
def st(monkeypatch, audits):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    s = Store("mongodb://localhost/?", f"wardeniq_audit_{time.time_ns()}", 8)
    monkeypatch.setattr(routes, "store", s)
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: None)
    return s


def _master(username):
    return client.post("/api/auth/reset-password-master",
                       json={"username": username, "app_secret": auth._session_secret(),
                             "new_password": GOOD})


def test_master_reset_refuses_non_admin_accounts(st, audits):
    st.create_user("viewer@example.com", "V", "viewer")
    r = _master("viewer@example.com")
    assert r.status_code == 403
    assert st.get_user_by_email("viewer@example.com").get("password_hash") is None
    assert audits[-1]["action"] == "auth.master_reset_failed"


def test_master_reset_admin_revokes_sessions_and_is_audited(st, audits):
    uid = st.create_user("boss@example.com", "B", "admin")["id"]
    before = st.get_user(uid).get("session_version", 0)
    assert _master("boss@example.com").status_code == 200
    assert st.get_user(uid)["session_version"] == before + 1
    assert audits[-1]["action"] == "auth.master_reset"


def test_master_reset_bootstrap_admin_still_works(st):
    assert _master("admin").status_code == 200
    assert st.get_user_by_email("admin")["role"] == "admin"


def test_bad_master_secret_is_audited(st, audits):
    r = client.post("/api/auth/reset-password-master",
                    json={"app_secret": "nope", "new_password": GOOD})
    assert r.status_code == 401
    assert audits[-1]["action"] == "auth.master_reset_failed"


def test_password_sign_in_success_and_failure_are_audited(st, audits):
    uid = st.create_user("alice@example.com", "A", "editor")["id"]
    st.set_user_password(uid, auth.hash_password(GOOD))
    client.post("/api/auth/login-password", json={"username": "alice@example.com", "password": "x"})
    assert audits[-1]["action"] == "auth.login_failed"
    assert audits[-1]["target"] == "alice@example.com"
    r = client.post("/api/auth/login-password",
                    json={"username": "alice@example.com", "password": GOOD})
    assert r.status_code == 200
    assert audits[-1]["action"] == "auth.login"
    assert audits[-1]["actor"]["id"] == uid


def test_otp_sign_in_failure_is_audited(st, audits):
    st.create_user("alice@example.com", "A", "editor")
    uid = st.get_user_by_email("alice@example.com")["id"]
    st.set_otp(uid, auth.hash_otp("123456"), time.time() + 600)
    client.post("/api/auth/verify-otp", json={"email": "alice@example.com", "code": "000000"})
    assert audits[-1]["action"] == "auth.login_failed"
    r = client.post("/api/auth/verify-otp", json={"email": "alice@example.com", "code": "123456"})
    assert r.status_code == 200
    assert audits[-1]["action"] == "auth.login"


# ------------------------------------------------------------ invite gate
def test_pending_invite_user_cannot_use_api(monkeypatch):
    user = {"id": "u9", "email": "new@example.com", "role": "editor", "active": True,
            "session_version": 0, "all_projects": True, "invite_status": "pending"}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    monkeypatch.setattr(main.store, "list_projects", lambda *a, **k: [], raising=False)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u9", 0)}
    r = client.get("/api/projects", cookies=cookie)
    assert r.status_code == 403
    assert "invitation" in r.json()["detail"]
    # The self-service invite endpoints stay reachable.
    monkeypatch.setattr(main.store, "invite_inviter_info", lambda uid: None, raising=False)
    assert client.get("/api/auth/my-invite", cookies=cookie).status_code == 200
    user["invite_status"] = "accepted"
    assert client.get("/api/projects", cookies=cookie).status_code != 403


# ------------------------------------------------------------ token audit actor
def test_api_token_actions_record_the_token_principal(audits):
    from core.audit import _audit

    class _Req:
        headers = {}
        client = None
        state = type("S", (), {"user": {"id": "token:t1", "email": None, "name": "ci-bot",
                                        "is_service_account": True, "token_id": "t1"}})()
    _audit(_Req(), "feature.created", target="F")
    assert audits[-1]["actor"]["id"] == "token:t1"
    assert audits[-1]["actor"]["email"] == "api-token:ci-bot"
