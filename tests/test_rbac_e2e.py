"""End-to-end auth / RBAC tests against the REAL `auth_gateway` middleware
(app/main.py) via FastAPI's TestClient — not just the pure-function unit
tests in tests/test_rbac_*.py, which exercise auth.py / helper functions in
isolation. Here every request goes through the actual ASGI middleware stack:
session verification -> role check -> project-scope check -> handler.

Only `main.store.*` is patched (never real Mongo); sessions are real
HMAC-signed cookies built with the real `auth.sign_session`.
"""
import auth
import main
from fastapi.testclient import TestClient

# See tests/test_api_routes.py for why: avoids a real (hanging) Mongo call
# from auth_gateway's audit logging on every 403. Only stubs the live
# singleton instance, not store.py's Store class.
main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)

SESSION_COOKIE = auth.SESSION_COOKIE


def _login(monkeypatch, users_by_id):
    """Patch main.store.get_user to serve from `users_by_id` (dict of uid -> user)."""
    monkeypatch.setattr(main.store, "get_user", lambda uid: users_by_id.get(uid))


def _cookie_for(uid, session_version=0):
    return {SESSION_COOKIE: auth.sign_session(uid, session_version)}


def _user(uid, role, **extra):
    base = {"id": uid, "email": f"{uid}@example.com", "role": role,
            "active": True, "session_version": 0, "all_projects": True}
    base.update(extra)
    return base


# --------------------------------------------------------------- unauthenticated
def test_no_cookie_is_401():
    r = client.get("/api/projects")
    assert r.status_code == 401
    assert r.json()["detail"] == "authentication required"


def test_garbage_cookie_is_401():
    r = client.get("/api/projects", cookies={SESSION_COOKIE: "not-a-real-token"})
    assert r.status_code == 401


def test_unknown_user_is_401(monkeypatch):
    _login(monkeypatch, {})   # verify_session succeeds, store.get_user finds nobody
    r = client.get("/api/projects", cookies=_cookie_for("ghost"))
    assert r.status_code == 401


def test_inactive_user_is_401(monkeypatch):
    u = _user("u1", "admin", active=False)
    _login(monkeypatch, {"u1": u})
    r = client.get("/api/projects", cookies=_cookie_for("u1"))
    assert r.status_code == 401


def test_stale_session_version_is_401(monkeypatch):
    # Token was minted at session_version=0; the user's role/session was since
    # bumped to 1 (role change / forced logout) -> old cookie must be rejected.
    u = _user("u1", "admin", session_version=1)
    _login(monkeypatch, {"u1": u})
    r = client.get("/api/projects", cookies=_cookie_for("u1", session_version=0))
    assert r.status_code == 401
    assert "expired" in r.json()["detail"]


# --------------------------------------------------------------------- roles
def test_viewer_forbidden_from_admin_path(monkeypatch):
    u = _user("u1", "viewer")
    _login(monkeypatch, {"u1": u})
    r = client.get("/api/settings", cookies=_cookie_for("u1"))
    assert r.status_code == 403
    assert "role" in r.json()["detail"]


def test_admin_allowed_admin_path(monkeypatch):
    u = _user("u1", "admin")
    _login(monkeypatch, {"u1": u})
    monkeypatch.setattr(main.store, "get_settings", lambda: {})
    r = client.get("/api/settings", cookies=_cookie_for("u1"))
    assert r.status_code == 200
    assert "configured" in r.json()


def test_editor_forbidden_from_admin_only_route(monkeypatch):
    # DELETE /api/projects/{pid} is in _ADMIN_ONLY_ROUTES: editors normally get
    # write access, but destructive project deletion is admin-only.
    u = _user("u1", "editor")
    _login(monkeypatch, {"u1": u})
    r = client.delete("/api/projects/p1", cookies=_cookie_for("u1"))
    assert r.status_code == 403


def test_admin_passes_admin_only_route_to_handler(monkeypatch):
    u = _user("u1", "admin")
    _login(monkeypatch, {"u1": u})
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    monkeypatch.setattr(main.store, "delete_project", lambda pid: False)
    r = client.delete("/api/projects/p1", cookies=_cookie_for("u1"))
    # Middleware let it through; handler's own 404 (not 401/403) proves it.
    assert r.status_code == 404


def test_viewer_allowed_on_viewer_post_allowlist(monkeypatch):
    # /api/retrieve is a read-style POST explicitly allowed for viewers.
    u = _user("u1", "viewer")
    _login(monkeypatch, {"u1": u})

    class _FakeEmbedder:
        def embed(self, text, task="query"):
            return [0.0] * 8

    monkeypatch.setattr(main, "embedder", _FakeEmbedder())
    monkeypatch.setattr(main.store, "search_cases", lambda emb, limit=5, ctype=None: ([], {}))
    r = client.post("/api/retrieve", json={"text": "login works", "limit": 3},
                     cookies=_cookie_for("u1"))
    assert r.status_code == 200


def test_viewer_forbidden_from_ordinary_write(monkeypatch):
    # Plain POST (not in VIEWER_POST_OK) defaults to "editor" minimum.
    u = _user("u1", "viewer")
    _login(monkeypatch, {"u1": u})
    r = client.post("/api/projects", json={"name": "New Project"}, cookies=_cookie_for("u1"))
    assert r.status_code == 403


def test_editor_allowed_ordinary_write(monkeypatch):
    u = _user("u1", "editor")
    _login(monkeypatch, {"u1": u})
    monkeypatch.setattr(main.store, "jira_project_in_use", lambda key: False)
    monkeypatch.setattr(main.store, "create_project", lambda *a, **kw: "new-pid")
    r = client.post("/api/projects", json={"name": "New Project"}, cookies=_cookie_for("u1"))
    assert r.status_code == 200
    assert r.json()["id"] == "new-pid"


# --------------------------------------------------------- project scoping
def test_restricted_user_denied_outside_their_projects(monkeypatch):
    u = _user("u1", "viewer", all_projects=False, project_ids=["p1"])
    _login(monkeypatch, {"u1": u})
    r = client.get("/api/projects/p2", cookies=_cookie_for("u1"))
    assert r.status_code == 403
    assert "access" in r.json()["detail"]


def test_restricted_user_allowed_into_their_project(monkeypatch):
    u = _user("u1", "viewer", all_projects=False, project_ids=["p1"])
    _login(monkeypatch, {"u1": u})
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    r = client.get("/api/projects/p1", cookies=_cookie_for("u1"))
    # Scope check passed (no 403); handler's own 404 proves we reached it.
    assert r.status_code == 404


def test_admin_bypasses_project_scope(monkeypatch):
    u = _user("u1", "admin", all_projects=False, project_ids=[])
    _login(monkeypatch, {"u1": u})
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    r = client.get("/api/projects/anything", cookies=_cookie_for("u1"))
    assert r.status_code == 404   # not 403 — admins always see every project
