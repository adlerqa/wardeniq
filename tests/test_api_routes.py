"""API-level tests against the real FastAPI app (app/main.py) via TestClient.

These hit real routes and real ASGI middleware (auth_gateway, security_headers),
but never touch a real MongoDB or LLM: `tests/conftest.py` patches
`Store.get_settings` before `main` is imported (so the module-level
`embedder = current_embedder()` in main.py doesn't try to dial out), and each
test patches whichever `main.store.*` methods its route needs.

We instantiate `TestClient(main.app)` WITHOUT the `with` context manager on
purpose: that skips FastAPI's startup lifespan (`@app.on_event("startup")`),
which otherwise spawns background threads that retry a real Mongo connection.
HTTP middleware (auth_gateway, security_headers) still runs on every request
either way — only the startup/shutdown event handlers are skipped.

Companion suites:
  tests/test_rbac_e2e.py     — role/session/project-scope enforcement in depth.
  tests/test_db_integration.py — same store.py surface against a real MongoDB.
"""
import main
from fastapi.testclient import TestClient

# main.py's auth_gateway middleware calls store.add_audit(...) on every
# permission-denied response (see _audit() in main.py). Against the
# unreachable placeholder Mongo URI these tests run with, that real
# `insert_one` call makes pymongo wait out its full server-selection timeout
# (tens of seconds) before giving up. It's an already best-effort, swallowed
# side effect (main.py wraps it in try/except), so the singleton `main.store`
# instance gets a no-op stand-in here. This only replaces the instance method
# on the app's live Store object — store.py's real `add_audit` is untouched,
# so tests/test_rbac_hardening.py::TestAudit still exercises the real thing.
main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)


# --------------------------------------------------------------------- public
def test_unauthenticated_unknown_route_is_401_not_404():
    # auth_gateway runs before route matching, so even a path that doesn't
    # exist is gated by auth first — it must never leak a 404 (route exists)
    # vs 401 (route doesn't exist) distinction to an unauthenticated caller.
    r = client.get("/api/this-route-does-not-exist")
    assert r.status_code == 401


def test_authenticated_unknown_route_is_404(monkeypatch):
    import auth as auth_mod
    user = {"id": "u1", "email": "u1@example.com", "role": "admin",
            "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth_mod.SESSION_COOKIE: auth_mod.sign_session("u1", 0)}
    r = client.get("/api/this-route-does-not-exist", cookies=cookie)
    assert r.status_code == 404


def test_security_headers_present_on_every_response():
    # security_headers middleware (main.py) should stamp a CSP on responses,
    # including ones the auth gateway rejects outright.
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "content-security-policy" in {k.lower() for k in r.headers.keys()}


def test_request_otp_rejects_invalid_email():
    r = client.post("/api/auth/request-otp", json={"email": "not-an-email"})
    assert r.status_code == 400


def test_request_otp_does_not_reveal_existing_accounts(monkeypatch):
    # A second, unknown requester when real users already exist gets the same
    # generic {"sent": true} — the route must not leak account existence.
    monkeypatch.setattr(main.store, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(
        main.store, "list_users",
        lambda: [{"email": "someone-else@example.com"}],
    )
    r = client.post("/api/auth/request-otp", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert r.json() == {"sent": True}


def test_request_otp_bootstraps_first_admin(monkeypatch):
    created = {}

    def fake_create_user(email, name, role="viewer", active=True, **kw):
        created.update(email=email, name=name, role=role)
        return {"id": "u1", "email": email, "name": name, "role": role, "active": True}

    monkeypatch.setattr(main.store, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(main.store, "list_users", lambda: [])
    monkeypatch.setattr(main.store, "create_user", fake_create_user)
    monkeypatch.setattr(main.store, "otp_recent_issue_count", lambda uid, window: 0)
    monkeypatch.setattr(main.store, "set_otp", lambda uid, h, exp: None)
    # No SMTP configured -> "logged" delivery path, code returned in dev_code.
    monkeypatch.setattr(main, "_deliver_otp", lambda *a, **kw: ("logged", "123456"))

    r = client.post("/api/auth/request-otp", json={"email": "first@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] is True
    assert body["bootstrap"] is True
    assert body["delivery"] == "log"
    assert body["dev_code"] == "123456"
    assert created["role"] == "admin"


def test_auth_me_without_cookie_is_401():
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_cookie():
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ------------------------------------------------------------------- OpenAPI
def test_openapi_schema_is_served_in_dev_mode():
    # main.py only disables docs/openapi when APP_ENV=production; the test
    # process runs with the default "development" posture.
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"].startswith("wardenIQ")
