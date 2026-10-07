"""End-to-end bearer-token auth tests (issue #37) against the REAL
`auth_gateway` middleware + the registered bearer_token_principal resolver,
via FastAPI's TestClient — same shape as tests/test_rbac_e2e.py, but exercising
`Authorization: Bearer <token>` instead of the session cookie.

Only `main.store.*` is patched (never real Mongo). The resolver itself
(core/token_auth.py) calls `store.get_api_token_by_hash` /
`store.api_token_failure_count` / `store.record_api_token_failure` /
`store.touch_api_token_last_used` — all monkeypatched here to isolate the
gateway/resolver wiring from the store implementation (which
tests/test_api_tokens.py already covers directly).
"""
import auth
import main
from fastapi.testclient import TestClient

main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _serve_token(monkeypatch, plaintext, token_doc, *, no_failures=True):
    """Wire main.store so a bearer of `plaintext` resolves to `token_doc` (a
    dict already shaped like ApiTokensMixin._token_out's output)."""
    expected_hash = auth.hash_token(plaintext)

    def _get_by_hash(h):
        return token_doc if h == expected_hash else None

    monkeypatch.setattr(main.store, "get_api_token_by_hash", _get_by_hash)
    monkeypatch.setattr(main.store, "touch_api_token_last_used", lambda tid: None)
    monkeypatch.setattr(main.store, "record_api_token_failure", lambda key, window: 1)
    if no_failures:
        monkeypatch.setattr(main.store, "api_token_failure_count", lambda key, window: 0)


def _token_doc(role="viewer", **extra):
    base = {"id": "t1", "name": "CI runner", "role": role,
            "all_projects": True, "project_ids": [], "active": True,
            "created_at": 0, "created_by": None, "last_used_at": None,
            "expires_at": None, "revoked_at": None}
    base.update(extra)
    return base


# --------------------------------------------------------------------------- basics
def test_no_authorization_header_falls_through_to_401():
    # No cookie, no bearer header -- unchanged 401 behavior (cookie path unaffected).
    r = client.get("/api/projects")
    assert r.status_code == 401


def test_valid_viewer_token_reads_projects(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc(role="viewer"))
    monkeypatch.setattr(main.store, "list_projects", lambda: [])
    r = client.get("/api/projects", headers=_bearer("wq_goodtoken"))
    assert r.status_code == 200


def test_unknown_bearer_token_is_401(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc())
    r = client.get("/api/projects", headers=_bearer("wq_totally-different-token"))
    assert r.status_code == 401


def test_malformed_authorization_header_falls_through(monkeypatch):
    # Not "Bearer <token>" shape at all -- resolver returns None, falls through
    # to the (absent) cookie -> 401, never a 500.
    r = client.get("/api/projects", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_revoked_token_is_401_not_500(monkeypatch):
    # get_api_token_by_hash already encodes "active" filtering server-side (see
    # tests/test_api_tokens.py) -- a revoked token's hash simply resolves to
    # nothing, which the resolver (and here, the fake) reports as None.
    monkeypatch.setattr(main.store, "get_api_token_by_hash", lambda h: None)
    monkeypatch.setattr(main.store, "api_token_failure_count", lambda key, window: 0)
    monkeypatch.setattr(main.store, "record_api_token_failure", lambda key, window: 1)
    r = client.get("/api/projects", headers=_bearer("wq_was-revoked"))
    assert r.status_code == 401


def test_expired_token_is_401(monkeypatch):
    # Same reasoning as revoked: store-level expiry filtering means an expired
    # token's hash resolves to nothing at the resolver's call site.
    monkeypatch.setattr(main.store, "get_api_token_by_hash", lambda h: None)
    monkeypatch.setattr(main.store, "api_token_failure_count", lambda key, window: 0)
    monkeypatch.setattr(main.store, "record_api_token_failure", lambda key, window: 1)
    r = client.get("/api/projects", headers=_bearer("wq_was-expired"))
    assert r.status_code == 401


def test_too_many_recent_failures_locks_out_even_a_valid_token(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc())
    monkeypatch.setattr(main.store, "api_token_failure_count", lambda key, window: 999)
    r = client.get("/api/projects", headers=_bearer("wq_goodtoken"))
    assert r.status_code == 401


# --------------------------------------------------------------------------- roles
def test_viewer_token_forbidden_from_admin_path(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc(role="viewer"))
    r = client.get("/api/settings", headers=_bearer("wq_goodtoken"))
    assert r.status_code == 403


def test_editor_token_allowed_ordinary_write(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc(role="editor"))
    monkeypatch.setattr(main.store, "jira_project_in_use", lambda key: False)
    monkeypatch.setattr(main.store, "create_project", lambda *a, **kw: "new-pid")
    r = client.post("/api/projects", json={"name": "New Project"}, headers=_bearer("wq_goodtoken"))
    assert r.status_code == 200


def test_viewer_token_forbidden_from_ordinary_write(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken", _token_doc(role="viewer"))
    r = client.post("/api/projects", json={"name": "New Project"}, headers=_bearer("wq_goodtoken"))
    assert r.status_code == 403


# --------------------------------------------------------------------- project scoping
def test_token_scoped_to_one_project_denied_on_another(monkeypatch):
    # "Wrong project": a token limited to p1 must not reach p2 -- enforced by the
    # SAME _require_project / gateway project-scope code a cookie user goes
    # through, with zero new code for token principals.
    _serve_token(monkeypatch, "wq_goodtoken",
                 _token_doc(role="viewer", all_projects=False, project_ids=["p1"]))
    r = client.get("/api/projects/p2", headers=_bearer("wq_goodtoken"))
    assert r.status_code == 403


def test_token_scoped_to_one_project_allowed_into_it(monkeypatch):
    _serve_token(monkeypatch, "wq_goodtoken",
                 _token_doc(role="viewer", all_projects=False, project_ids=["p1"]))
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    r = client.get("/api/projects/p1", headers=_bearer("wq_goodtoken"))
    # Scope check passed (no 403); handler's own 404 proves we reached it.
    assert r.status_code == 404


# ------------------------------------------------------------- cookie auth unaffected
def test_cookie_auth_still_works_unchanged(monkeypatch):
    # Proves the resolver registration is purely additive: an ordinary cookie
    # session, with NO Authorization header at all, behaves exactly as before.
    u = {"id": "u1", "email": "u1@example.com", "role": "admin",
         "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: u)
    monkeypatch.setattr(main.store, "get_settings", lambda: {})
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}
    r = client.get("/api/settings", cookies=cookie)
    assert r.status_code == 200
