"""Route-level tests for /api/db-config and /api/db-migrate (issue #110's other
half): both endpoints share app.api.routes.settings._probe_mongo(), so this
suite locks in that hardening one round trip out — an admin request that gets
a "reachable but not search-capable" (or replica-set/privilege/version)
result must see a clear, specific error and never persist/migrate anything.

Companion suite: tests/test_mongo_capability_probe.py covers _probe_mongo()
itself in depth via fakes; this file only exercises the two routes' own
branching around whatever _probe_mongo() returns (monkeypatched directly, so
these tests don't re-verify the probe's internals).
"""
import auth
import main
from api.routes import settings as settings_mod
from fastapi.testclient import TestClient

# See tests/test_api_routes.py for why: avoids a real (hanging) Mongo call from
# auth_gateway's audit logging against the placeholder Mongo URI these tests run with.
main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)


def _admin_cookie(monkeypatch):
    user = {"id": "u1", "email": "admin@example.com", "role": "admin",
            "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}


_OK_PROBE = {"reachable": True, "replica_set": True, "server_version": "8.3.1",
             "search_ok": True, "status": "ok", "detail": "ok"}


def _probe(status, **overrides):
    base = dict(_OK_PROBE, status=status, search_ok=(status == "ok"))
    base.update(overrides)
    return base


# --------------------------------------------------------------------- /api/db-config
def test_db_config_rejects_when_target_not_reachable(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo",
                         lambda uri, dim=None: _probe("unreachable", reachable=False,
                                                       replica_set=False, server_version=None,
                                                       detail="server selection timed out"))
    write_calls = []
    monkeypatch.setattr(settings_mod, "_write_env_var",
                         lambda *a, **kw: write_calls.append(a) or (True, ""))
    r = client.post("/api/db-config", json={"uri": "mongodb://unreachable/"}, cookies=cookie)
    assert r.status_code == 400
    assert "timed out" in r.json()["detail"]
    assert write_calls == []  # nothing persisted on a failed probe


def test_db_config_rejects_no_replica_set_with_specific_message(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo",
                         lambda uri, dim=None: _probe("no_replica_set", replica_set=False,
                                                       detail="this database is not a replica set."))
    r = client.post("/api/db-config", json={"uri": "mongodb://standalone/"}, cookies=cookie)
    assert r.status_code == 400
    assert "not a replica set" in r.json()["detail"]


def test_db_config_force_bypasses_a_failed_probe(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo",
                         lambda uri, dim=None: _probe("no_search", detail="no Vector Search"))
    written = {}
    monkeypatch.setattr(settings_mod, "_write_env_var",
                         lambda path, key, val: (written.__setitem__(key, val), (True, ""))[1])
    r = client.post("/api/db-config", json={"uri": "mongodb://force-me/", "force": True},
                     cookies=cookie)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert written["MONGO_URI"] == "mongodb://force-me/"


def test_db_config_accepts_fully_validated_target(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo", lambda uri, dim=None: _probe("ok"))
    monkeypatch.setattr(settings_mod, "_write_env_var", lambda *a, **kw: (True, ""))
    r = client.post("/api/db-config", json={"uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reachable"] is True
    assert body["search_available"] is True
    assert body["replica_set"] is True
    assert body["server_version"] == "8.3.1"


# --------------------------------------------------------------------- /api/db-migrate
def test_db_migrate_rejects_unreachable_target(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo",
                         lambda uri, dim=None: _probe("unreachable", reachable=False,
                                                       replica_set=False, server_version=None,
                                                       detail="connection refused"))
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: launched.append(a) or "job1")
    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://dead/"}, cookies=cookie)
    assert r.status_code == 400
    assert "connection refused" in r.json()["detail"]
    assert launched == []  # never started a migration job


def test_db_migrate_rejects_search_incapable_target_with_specific_detail(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo",
                         lambda uri, dim=None: _probe("insufficient_privileges",
                                                       detail="connected, but this user isn't "
                                                              "authorized to create search indexes"))
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: launched.append(a) or "job1")
    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://readonly/"}, cookies=cookie)
    assert r.status_code == 400
    assert "authorized" in r.json()["detail"]
    assert launched == []


def test_db_migrate_probes_at_the_current_store_dimension(monkeypatch):
    """/api/db-migrate must validate the TARGET at the dimension the app actually
    uses today (store.dim), not some other default — a target that only supports a
    different embedding size would otherwise pass validation and fail for real
    the moment the app tries to use it post-restart."""
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod.store, "dim", 1536)
    seen_dims = []

    def fake_probe(uri, dim=None):
        seen_dims.append(dim)
        return _probe("ok")
    monkeypatch.setattr(settings_mod, "_probe_mongo", fake_probe)
    monkeypatch.setattr(settings_mod.store, "target_has_data", lambda uri: False)
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: "job1")
    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 200
    assert seen_dims == [1536]


def test_db_migrate_starts_job_for_fully_validated_target(monkeypatch):
    cookie = _admin_cookie(monkeypatch)
    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod, "_probe_mongo", lambda uri, dim=None: _probe("ok"))
    monkeypatch.setattr(settings_mod.store, "target_has_data", lambda uri: False)
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job",
                         lambda jtype, params, label="": launched.append((jtype, params)) or "job1")
    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 200
    assert r.json()["job_id"] == "job1"
    assert launched == [("migrate", {"target_uri": "mongodb://good/", "overwrite": False})]
