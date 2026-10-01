"""/api/db-config and /api/db-migrate now consume the structured result of
settings._probe_mongo() (issue #110) instead of a (reachable, search_ok, detail)
tuple. The probe itself is covered by tests/test_mongo_capability_probe.py; here it
is stubbed so only the routes' handling of each probe outcome is exercised.
"""
import auth
import main
from api.routes import settings as settings_mod
from core.state import SYNC
from fastapi.testclient import TestClient

client = TestClient(main.app)

SESSION_COOKIE = auth.SESSION_COOKIE
URI = "mongodb://db.example.test:27017/?replicaSet=rs0"


def _admin():
    return {"id": "u1", "email": "u1@example.com", "role": "admin",
            "active": True, "session_version": 0, "all_projects": True}


def _cookie():
    return {SESSION_COOKIE: auth.sign_session("u1", 0)}


def _probe_result(**over):
    base = {"reachable": True, "replica_set": True, "server_version": "8.3.4",
            "search_ok": True, "status": "ok", "detail": "ok"}
    base.update(over)
    return base


class _Env:
    """Stubs everything around the probe so no real DB or .env is touched."""
    def __init__(self, monkeypatch, probe):
        self.probe_calls = []
        self.env_writes = []
        self.jobs = []
        monkeypatch.setattr(main.store, "get_user", lambda uid: _admin() if uid == "u1" else None)
        monkeypatch.setattr(main.store, "add_audit", lambda *a, **kw: True)
        monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
        monkeypatch.setattr(settings_mod, "_write_env_var",
                            lambda path, k, v: self.env_writes.append((k, v)) or (True, None))
        monkeypatch.setattr(main.store, "target_has_data", lambda uri: False)
        # /api/db-migrate's idle check (#111) consults the job store and SYNC; an idle
        # system is the baseline for these probe-outcome tests.
        monkeypatch.setattr(main.store, "has_running_job", lambda **kw: None)
        monkeypatch.setitem(SYNC, "running", False)
        monkeypatch.setattr(settings_mod, "launch_job",
                            lambda t, params, label="", before_start=None: self.jobs.append((t, params)) or "job1")

        def fake_probe(uri, dim=None):
            self.probe_calls.append((uri, dim))
            return probe
        monkeypatch.setattr(settings_mod, "_probe_mongo", fake_probe)


def test_db_config_rejects_unreachable_target(monkeypatch):
    env = _Env(monkeypatch, _probe_result(reachable=False, replica_set=False, search_ok=False,
                                          status="unreachable", detail="connection refused"))
    r = client.post("/api/db-config", json={"uri": URI}, cookies=_cookie())
    assert r.status_code == 400
    assert "connection refused" in r.json()["detail"] and "Nothing was saved" in r.json()["detail"]
    assert env.env_writes == []


def test_db_config_rejects_search_incapable_target_with_the_probes_specific_detail(monkeypatch):
    env = _Env(monkeypatch, _probe_result(replica_set=False, search_ok=False,
                                          status="no_replica_set", detail="this database is not a replica set."))
    r = client.post("/api/db-config", json={"uri": URI}, cookies=_cookie())
    assert r.status_code == 400
    assert "not a replica set" in r.json()["detail"]
    assert env.env_writes == []


def test_db_config_force_bypasses_a_failed_probe(monkeypatch):
    env = _Env(monkeypatch, _probe_result(search_ok=False, status="no_search", detail="x"))
    r = client.post("/api/db-config", json={"uri": URI, "force": True}, cookies=_cookie())
    assert r.status_code == 200
    assert env.env_writes == [("MONGO_URI", URI)]
    assert r.json()["search_available"] is False


def test_db_config_accepts_a_fully_validated_target(monkeypatch):
    env = _Env(monkeypatch, _probe_result())
    r = client.post("/api/db-config", json={"uri": URI}, cookies=_cookie())
    assert r.status_code == 200
    body = r.json()
    assert body["reachable"] and body["search_available"] and body["replica_set"]
    assert body["server_version"] == "8.3.4" and body["restart_required"] is True
    assert env.env_writes == [("MONGO_URI", URI)]


def test_db_config_probes_at_the_stores_embedding_dimension(monkeypatch):
    env = _Env(monkeypatch, _probe_result())
    monkeypatch.setattr(main.store, "dim", 1536, raising=False)
    client.post("/api/db-config", json={"uri": URI}, cookies=_cookie())
    assert env.probe_calls == [(URI, 1536)]


def test_db_migrate_rejects_unreachable_target(monkeypatch):
    env = _Env(monkeypatch, _probe_result(reachable=False, search_ok=False,
                                          status="unreachable", detail="connection refused"))
    r = client.post("/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert r.status_code == 400 and "Nothing copied" in r.json()["detail"]
    assert env.jobs == []


def test_db_migrate_rejects_search_incapable_target_with_specific_detail(monkeypatch):
    env = _Env(monkeypatch, _probe_result(search_ok=False, status="insufficient_privileges",
                                          detail="this user isn't authorized to create search indexes."))
    r = client.post("/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert r.status_code == 400
    assert "isn't authorized" in r.json()["detail"] and "nothing copied" in r.json()["detail"]
    assert env.jobs == []


def test_db_migrate_probes_at_the_stores_embedding_dimension(monkeypatch):
    env = _Env(monkeypatch, _probe_result())
    monkeypatch.setattr(main.store, "dim", 384, raising=False)
    client.post("/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert env.probe_calls == [(URI, 384)]


def test_db_migrate_starts_the_job_for_a_fully_validated_target(monkeypatch):
    env = _Env(monkeypatch, _probe_result())
    r = client.post("/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert r.status_code == 200 and r.json() == {"job_id": "job1"}
    assert env.jobs == [("migrate", {"target_uri": URI, "overwrite": False,
                                     "override_busy": False})]


def test_db_migrate_surfaces_the_curated_index_limit_message(monkeypatch):
    from core.bootstrap import _SEARCH_INDEX_LIMIT_MSG
    env = _Env(monkeypatch, _probe_result(search_ok=False, status="no_search",
                                          detail=_SEARCH_INDEX_LIMIT_MSG))
    r = client.post("/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert r.status_code == 400
    assert _SEARCH_INDEX_LIMIT_MSG in r.json()["detail"] and "nothing copied" in r.json()["detail"]
    assert env.jobs == []


def test_db_config_surfaces_the_curated_index_limit_message(monkeypatch):
    from core.bootstrap import _SEARCH_INDEX_LIMIT_MSG
    env = _Env(monkeypatch, _probe_result(search_ok=False, status="no_search",
                                          detail=_SEARCH_INDEX_LIMIT_MSG))
    r = client.post("/api/db-config", json={"uri": URI}, cookies=_cookie())
    assert r.status_code == 400 and _SEARCH_INDEX_LIMIT_MSG in r.json()["detail"]
    assert env.env_writes == []
