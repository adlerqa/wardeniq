"""A database outage must not look like "you were signed out" (#282).

`Store.get_user` used to swallow every exception, so a down MongoDB became "no such user"
and every authenticated call answered 401. The UI reads a 401 as a sign-out and shows the
login screen, which cannot work either while the database is down. Now:

  * a malformed id (tampered cookie) is still "no such user" -> 401
  * a storage error propagates and the gateway, /api/auth/me and the session helpers answer
    503 with a clear message and `Retry-After`, which the UI shows without dropping the session
  * the same holds for a bearer API token whose lookup hits the outage

Only `main.store.*` is patched (never real Mongo), as in tests/test_rbac_e2e.py.
"""
import auth
import main
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

from core.security import DATABASE_UNAVAILABLE_DETAIL
from store.users_auth import UsersAuthMixin

main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)
SESSION_COOKIE = auth.SESSION_COOKIE


def _cookie(uid="u1", sv=0):
    return {SESSION_COOKIE: auth.sign_session(uid, sv)}


def _db_down(monkeypatch, exc=None):
    exc = exc or ServerSelectionTimeoutError("localhost:27017: [Errno 111] Connection refused")

    def boom(uid):
        raise exc

    monkeypatch.setattr(main.store, "get_user", boom)


# ------------------------------------------------------------------ Store.get_user itself
class _Users:
    def __init__(self, doc=None, exc=None):
        self.doc, self.exc, self.calls = doc, exc, 0

    def find_one(self, query):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.doc


def _store(doc=None, exc=None):
    fake = type("S", (), {})()
    fake.users = _Users(doc, exc)
    fake._user_out = UsersAuthMixin._user_out
    return fake


def test_get_user_returns_the_user():
    oid = ObjectId()
    s = _store({"_id": oid, "email": "a@example.com", "role": "admin"})
    u = UsersAuthMixin.get_user(s, str(oid))
    assert u["id"] == str(oid) and u["role"] == "admin"


def test_get_user_unknown_id_is_none():
    assert UsersAuthMixin.get_user(_store(None), str(ObjectId())) is None


@pytest.mark.parametrize("bad", ["not-an-object-id", "", "123", None, 12345, b"\xff"])
def test_get_user_malformed_id_is_none_without_touching_the_database(bad):
    s = _store(exc=AssertionError("the database must not be queried for a malformed id"))
    assert UsersAuthMixin.get_user(s, bad) is None
    assert s.users.calls == 0


@pytest.mark.parametrize("exc", [ServerSelectionTimeoutError("down"), AutoReconnect("reset")])
def test_get_user_lets_a_storage_error_propagate(exc):
    s = _store(exc=exc)
    with pytest.raises(type(exc)):
        UsersAuthMixin.get_user(s, str(ObjectId()))


# ------------------------------------------------------------------ the gateway
def test_gateway_answers_503_not_401_when_the_database_is_down(monkeypatch):
    _db_down(monkeypatch)
    r = client.get("/api/projects", cookies=_cookie())
    assert r.status_code == 503
    assert r.json()["detail"] == DATABASE_UNAVAILABLE_DETAIL
    assert r.headers["retry-after"] == "5"


def test_the_503_says_the_user_is_not_signed_out_and_leaks_nothing(monkeypatch):
    _db_down(monkeypatch, ServerSelectionTimeoutError("mongodb://admin:s3cret@db.internal:27017 timed out"))
    r = client.get("/api/projects", cookies=_cookie())
    assert "not signed out" in r.json()["detail"]
    assert "s3cret" not in r.text and "db.internal" not in r.text


def test_any_authenticated_route_gets_the_503(monkeypatch):
    _db_down(monkeypatch)
    for path in ("/api/projects", "/api/jobs", "/api/db-status"):
        assert client.get(path, cookies=_cookie()).status_code == 503, path


def test_a_missing_cookie_is_still_401_when_the_database_is_down(monkeypatch):
    # No session to check, so the database is never consulted and 401 stays correct.
    _db_down(monkeypatch)
    assert client.get("/api/projects").status_code == 401


def test_a_garbage_cookie_is_still_401_when_the_database_is_down(monkeypatch):
    _db_down(monkeypatch)
    assert client.get("/api/projects", cookies={SESSION_COOKIE: "not-a-real-token"}).status_code == 401


def test_an_unknown_user_is_still_401_when_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main.store, "get_user", lambda uid: None)
    r = client.get("/api/projects", cookies=_cookie())
    assert r.status_code == 401 and r.json()["detail"] == "authentication required"


def test_the_session_works_again_once_the_database_is_back(monkeypatch):
    user = {"id": "u1", "email": "u@example.com", "role": "viewer", "active": True,
            "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "list_projects", lambda: [])
    _db_down(monkeypatch)
    assert client.get("/api/projects", cookies=_cookie()).status_code == 503
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)   # same cookie, DB is back
    assert client.get("/api/projects", cookies=_cookie()).status_code == 200


def test_a_disabled_user_is_still_401_when_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main.store, "get_user", lambda uid: {
        "id": "u1", "role": "viewer", "active": False, "session_version": 0})
    assert client.get("/api/projects", cookies=_cookie()).status_code == 401


# ------------------------------------------------------------------ /api/auth/me
def test_auth_me_is_503_when_the_database_is_down(monkeypatch):
    _db_down(monkeypatch)
    r = client.get("/api/auth/me", cookies=_cookie())
    assert r.status_code == 503
    assert r.json()["detail"] == DATABASE_UNAVAILABLE_DETAIL
    assert r.headers["retry-after"] == "5"


def test_auth_me_without_a_session_is_still_401(monkeypatch):
    _db_down(monkeypatch)
    assert client.get("/api/auth/me").status_code == 401


def test_auth_me_returns_the_user_when_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main.store, "get_user", lambda uid: {
        "id": "u1", "email": "u@example.com", "name": "U", "role": "viewer", "active": True,
        "session_version": 0, "all_projects": True})
    r = client.get("/api/auth/me", cookies=_cookie())
    assert r.status_code == 200 and r.json()["user"]["email"] == "u@example.com"


def test_my_invite_uses_the_same_503(monkeypatch):
    # /api/auth/my-invite resolves the user through _session_user, not the gateway.
    _db_down(monkeypatch)
    assert client.get("/api/auth/my-invite", cookies=_cookie()).status_code == 503


def test_logout_still_clears_the_cookie_when_the_database_is_down(monkeypatch):
    _db_down(monkeypatch)
    r = client.post("/api/auth/logout", cookies=_cookie())
    assert r.status_code == 200 and r.json() == {"ok": True}


# ------------------------------------------------------------------ bearer API tokens
def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_a_bearer_token_gets_503_when_the_token_lookup_hits_the_outage(monkeypatch):
    def boom(h):
        raise ServerSelectionTimeoutError("down")

    monkeypatch.setattr(main.store, "api_token_failure_count", lambda k, w: 0)
    monkeypatch.setattr(main.store, "get_api_token_by_hash", boom)
    r = client.get("/api/projects", headers=_bearer("wq_sometoken"))
    assert r.status_code == 503 and r.json()["detail"] == DATABASE_UNAVAILABLE_DETAIL


def test_an_unexpected_error_in_the_token_resolver_still_fails_closed_as_401(monkeypatch):
    # Only a database outage changed; any other failure keeps the old 401 (never a 500).
    def boom(h):
        raise RuntimeError("something else broke")

    monkeypatch.setattr(main.store, "api_token_failure_count", lambda k, w: 0)
    monkeypatch.setattr(main.store, "get_api_token_by_hash", boom)
    assert client.get("/api/projects", headers=_bearer("wq_sometoken")).status_code == 401
