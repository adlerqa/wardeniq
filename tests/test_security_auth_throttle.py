"""Brute-force throttling on the public auth routes, OTP/reset-code issuance limits,
and the no-SMTP sign-in code delivery policy.

Runs the real routes through TestClient against a mongomock-backed Store, so the
atomic counter updates are exercised for real (no MongoDB needed).
"""
import time

import pytest

mongomock = pytest.importorskip("mongomock")

import auth  # noqa: E402
import main  # noqa: E402
import store.base as store_base  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from store import Store  # noqa: E402

from core import client_ip as client_ip_mod  # noqa: E402
from core import throttle  # noqa: E402

routes = main._auth_routes
client = TestClient(main.app)
GOOD = "Correct-horse-9"


@pytest.fixture
def st(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    s = Store("mongodb://localhost/?", f"wardeniq_throttle_{time.time_ns()}", 8)
    monkeypatch.setattr(routes, "store", s)
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: None)
    monkeypatch.setattr(throttle, "AUTH_MAX_FAILURES_PER_ACCOUNT", 3)
    monkeypatch.setattr(throttle, "AUTH_MAX_FAILURES_PER_IP", 5)
    uid = s.create_user("alice@example.com", "Alice", "editor")["id"]
    s.set_user_password(uid, auth.hash_password(GOOD))
    return s


def _login(username, password):
    return client.post("/api/auth/login-password",
                       json={"username": username, "password": password})


def test_account_lockout_blocks_even_correct_password(st):
    for _ in range(3):
        assert _login("alice@example.com", "wrong-1").status_code == 401
    r = _login("alice@example.com", GOOD)
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_success_clears_account_failures(st):
    for _ in range(2):
        assert _login("alice@example.com", "wrong-1").status_code == 401
    assert _login("alice@example.com", GOOD).status_code == 200
    for _ in range(2):
        assert _login("alice@example.com", "wrong-1").status_code == 401
    assert _login("alice@example.com", GOOD).status_code == 200


def test_unknown_accounts_are_throttled_the_same_way(st):
    for _ in range(3):
        assert _login("nobody@example.com", "x").status_code == 401
    assert _login("nobody@example.com", "x").status_code == 429


def test_per_ip_limit_spans_accounts(st):
    for i in range(5):
        assert _login(f"user{i}@example.com", "x").status_code == 401
    assert _login("alice@example.com", GOOD).status_code == 429


def test_refused_requests_are_not_counted(st):
    for _ in range(3):
        _login("alice@example.com", "wrong-1")
    for _ in range(5):
        assert _login("alice@example.com", "wrong-1").status_code == 429
    # Lockout over: the refused attempts above did not pile up into a new lockout.
    st.auth_throttle.update_many({}, {"$set": {"locked_until": time.time() - 1}})
    assert _login("alice@example.com", "wrong-1").status_code == 401
    assert _login("alice@example.com", GOOD).status_code == 200


def test_master_reset_is_throttled(st):
    for _ in range(3):
        r = client.post("/api/auth/reset-password-master",
                        json={"app_secret": "nope", "new_password": GOOD})
        assert r.status_code == 401
    r = client.post("/api/auth/reset-password-master",
                    json={"app_secret": auth._session_secret(), "new_password": GOOD})
    assert r.status_code == 429


def test_verify_otp_and_reset_code_guesses_are_throttled(st):
    for path, body in (("/api/auth/verify-otp", {"email": "alice@example.com", "code": "000000"}),
                       ("/api/auth/reset-password", {"username_or_email": "alice@example.com",
                                                     "code": "000000", "new_password": GOOD})):
        codes = [client.post(path, json=body).status_code for _ in range(4)]
        assert codes[-1] == 429, (path, codes)


# ------------------------------------------------------------ issuance limits
def test_otp_issue_throttle_is_atomic_and_ignores_throttled_requests(st):
    uid = st.get_user_by_email("alice@example.com")["id"]
    counts = [st.otp_recent_issue_count(uid, 900, 2) for _ in range(4)]
    assert counts == [1, 2, 3, 3]
    assert len(st.users.find_one({"email": "alice@example.com"})["otp_issues"]) == 2


def test_throttled_reset_request_keeps_outstanding_code_and_attempts(st, monkeypatch):
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: {"host": "smtp.example"})
    monkeypatch.setattr(routes, "_deliver_reset_code", lambda *a, **k: ("sent", ""))
    monkeypatch.setattr(routes, "RESET_CODE_MAX_PER_WINDOW", 2)
    body = {"username_or_email": "alice@example.com"}
    for _ in range(2):
        assert client.post("/api/auth/request-password-reset", json=body).status_code == 200
    uid = st.get_user_by_email("alice@example.com")["id"]
    st.inc_reset_attempts(uid)
    before = st.users.find_one({"email": "alice@example.com"})
    r = client.post("/api/auth/request-password-reset", json=body)
    assert r.status_code == 200 and r.json()["sent"] is True       # same generic answer
    after = st.users.find_one({"email": "alice@example.com"})
    assert after["reset_hash"] == before["reset_hash"]
    assert after["reset_attempts"] == 1


# ------------------------------------------------------------ no-SMTP code delivery
def test_no_smtp_code_not_returned_or_logged_for_regular_user(st, caplog, monkeypatch):
    monkeypatch.setattr(routes, "OTP_DEV_CODES", False)
    st.create_user("admin2@example.com", "A", "admin")       # a real admin exists
    r = client.post("/api/auth/request-otp", json={"email": "alice@example.com"})
    assert r.status_code == 200
    assert "dev_code" not in r.json()
    assert r.json()["message"] == routes.OTP_MASKED_MESSAGE
    assert "one-time sign-in code" not in caplog.text


def test_no_smtp_existing_admin_gets_no_code_unless_bootstrap(st, monkeypatch):
    monkeypatch.setattr(routes, "OTP_DEV_CODES", False)
    monkeypatch.setattr(routes, "ADMIN_EMAIL", "")
    st.create_user("boss@example.com", "Boss", "admin")
    r = client.post("/api/auth/request-otp", json={"email": "boss@example.com"})
    assert "dev_code" not in r.json()


def test_no_smtp_bootstrap_admin_code_is_logged_not_returned(st, monkeypatch):
    monkeypatch.setattr(routes, "OTP_DEV_CODES", False)
    logged = []
    monkeypatch.setattr(routes.log, "info", lambda msg, *a: logged.append(a))
    mode, detail = routes._deliver_otp("first@example.com", "123456", is_admin=True,
                                       is_bootstrap=True)
    assert (mode, detail) == ("logged", "")
    assert any("123456" in a for a in logged)


def test_dev_codes_opt_in_returns_code(st, monkeypatch):
    monkeypatch.setattr(routes, "OTP_DEV_CODES", True)
    assert routes._deliver_otp("a@example.com", "654321") == ("logged", "654321")
    r = client.post("/api/auth/request-otp", json={"email": "alice@example.com"})
    assert r.json()["delivery"] == "log"
    assert len(r.json()["dev_code"]) == 6


def test_dev_codes_never_enabled_in_production(monkeypatch):
    import importlib

    import core.config as cfg
    monkeypatch.setenv("OTP_DEV_CODES", "true")
    monkeypatch.setenv("APP_ENV", "production")
    try:
        assert importlib.reload(cfg).OTP_DEV_CODES is False
        monkeypatch.setenv("APP_ENV", "development")
        assert importlib.reload(cfg).OTP_DEV_CODES is True
    finally:
        monkeypatch.delenv("OTP_DEV_CODES")
        monkeypatch.delenv("APP_ENV")
        importlib.reload(cfg)


# ------------------------------------------------------------ client IP
class _Req:
    def __init__(self, peer, xff=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = {"x-forwarded-for": xff} if xff else {}


def test_client_ip_ignores_forwarded_header_by_default():
    assert client_ip_mod.client_ip(_Req("10.0.0.5", "1.2.3.4"), trusted=[]) == "10.0.0.5"


def test_client_ip_uses_forwarded_header_only_from_trusted_proxy():
    trusted = client_ip_mod._networks(["10.0.0.0/8"])
    assert client_ip_mod.client_ip(_Req("10.0.0.5", "9.9.9.9, 1.2.3.4"), trusted) == "1.2.3.4"
    assert client_ip_mod.client_ip(_Req("10.0.0.5", "1.2.3.4, 10.0.0.9"), trusted) == "1.2.3.4"
    assert client_ip_mod.client_ip(_Req("8.8.8.8", "1.2.3.4"), trusted) == "8.8.8.8"
    assert client_ip_mod.client_ip(_Req("10.0.0.5", "garbage"), trusted) == "10.0.0.5"
