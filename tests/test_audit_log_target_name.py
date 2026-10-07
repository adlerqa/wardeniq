"""Issue #118: the Users audit log's Target column showed the raw project _id
("6a7edbdd...") for project.deleted entries instead of a human-readable name,
making it hard to tell which project an entry refers to.

Root cause: app/api/routes/projects.py's delete_project() already fetches the
project (to capture its name under `old`) before deleting it, but passed the
raw `pid` as the audit `target` instead of that same name.

Same e2e shape as tests/test_rbac_e2e.py (real auth_gateway middleware, real
signed session cookie, only main.store.* patched -- never real Mongo), since
the bug lives in the route handler, not the store layer.
"""
import auth
import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

SESSION_COOKIE = auth.SESSION_COOKIE


def _login(monkeypatch, users_by_id):
    monkeypatch.setattr(main.store, "get_user", lambda uid: users_by_id.get(uid))


def _cookie_for(uid, session_version=0):
    return {SESSION_COOKIE: auth.sign_session(uid, session_version)}


def _admin(uid):
    return {"id": uid, "email": f"{uid}@example.com", "role": "admin",
            "active": True, "session_version": 0, "all_projects": True}


def _capture_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.store, "add_audit",
        lambda action, **kw: calls.append({"action": action, **kw}) or True,
    )
    return calls


def test_deleting_a_project_records_its_name_as_the_audit_target(monkeypatch):
    _login(monkeypatch, {"u1": _admin("u1")})
    calls = _capture_audit(monkeypatch)
    monkeypatch.setattr(main.store, "get_project", lambda pid: {"id": pid, "name": "Near-U"})
    monkeypatch.setattr(main.store, "delete_project", lambda pid: {"ok": True})

    r = client.delete("/api/projects/6a7edbddc0ffee1234567890", cookies=_cookie_for("u1"))

    assert r.status_code == 200
    assert len(calls) == 1
    # The exact ticket symptom: target must be the readable name, not the id.
    assert calls[0]["target"] == "Near-U"
    assert calls[0]["target"] != "6a7edbddc0ffee1234567890"
    assert calls[0]["action"] == "project.deleted"
    # `old` already carried the name before this fix -- still does, unchanged.
    assert calls[0]["old"] == {"name": "Near-U"}


def test_deleting_an_unresolvable_project_falls_back_to_the_id(monkeypatch):
    # get_project() returns None (e.g. a race with another delete) -- target
    # must still be set to *something* identifying, not crash or go blank.
    _login(monkeypatch, {"u1": _admin("u1")})
    calls = _capture_audit(monkeypatch)
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    monkeypatch.setattr(main.store, "delete_project", lambda pid: {"ok": True})

    r = client.delete("/api/projects/deadbeefdeadbeefdeadbeef", cookies=_cookie_for("u1"))

    assert r.status_code == 200
    assert calls[0]["target"] == "deadbeefdeadbeefdeadbeef"
    assert calls[0]["old"] == {"name": None}


def test_delete_of_a_missing_project_still_404s_without_auditing(monkeypatch):
    # Unchanged existing behavior: delete_project() returning falsy -> 404,
    # and (per the existing code path) no audit entry is written at all.
    _login(monkeypatch, {"u1": _admin("u1")})
    calls = _capture_audit(monkeypatch)
    monkeypatch.setattr(main.store, "get_project", lambda pid: None)
    monkeypatch.setattr(main.store, "delete_project", lambda pid: False)

    r = client.delete("/api/projects/doesnotexist", cookies=_cookie_for("u1"))

    assert r.status_code == 404
    assert calls == []


def test_editor_still_forbidden_from_deleting_a_project(monkeypatch):
    # Unrelated existing authorization behavior must be untouched by this fix.
    u = {"id": "u1", "email": "u1@example.com", "role": "editor",
         "active": True, "session_version": 0, "all_projects": True}
    _login(monkeypatch, {"u1": u})
    r = client.delete("/api/projects/p1", cookies=_cookie_for("u1"))
    assert r.status_code == 403
