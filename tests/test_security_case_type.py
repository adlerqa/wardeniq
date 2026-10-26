"""Test-case `type` is validated against the known categories on create and edit."""
import auth
import main
import pytest
from fastapi.testclient import TestClient

from core import state

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)


@pytest.fixture
def editor(monkeypatch):
    user = {"id": "u1", "email": "u1@example.com", "role": "editor", "active": True,
            "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    monkeypatch.setattr(main.store, "get_feature", lambda fid: {"id": fid, "project_id": "p1"})
    monkeypatch.setattr(main.store, "get_case",
                        lambda cid: {"id": cid, "features": [{"project_id": "p1"}]})
    monkeypatch.setattr(state, "embedder", type("E", (), {"embed": lambda self, t: [0.0]})())
    calls = []
    monkeypatch.setattr(main.store, "create_case", lambda *a, **kw: calls.append(a) or "c1")
    monkeypatch.setattr(main.store, "update_case", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(main.store, "associate", lambda *a, **kw: None)
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}, calls


BAD = ['functional" onmouseover="x', "<b>", "unknown"]


@pytest.mark.parametrize("bad", BAD)
def test_create_case_rejects_unknown_type(editor, bad):
    cookie, calls = editor
    r = client.post("/api/test-cases", cookies=cookie,
                    json={"feature_id": "f1", "title": "t", "type": bad})
    assert r.status_code == 422
    assert calls == []


@pytest.mark.parametrize("bad", BAD)
def test_update_case_rejects_unknown_type(editor, bad):
    cookie, calls = editor
    r = client.put("/api/test-cases/c1", cookies=cookie, json={"title": "t", "type": bad})
    assert r.status_code == 422
    assert calls == []


@pytest.mark.parametrize("good", ["functional", "e2e", "api", "ui", "nfr", "API"])
def test_known_types_are_accepted(editor, good):
    cookie, calls = editor
    r = client.post("/api/test-cases", cookies=cookie,
                    json={"feature_id": "f1", "title": "t", "type": good})
    assert r.status_code == 200, r.text
    assert calls[-1][1] == good.lower()
