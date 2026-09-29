"""Hardening for /api/db-migrate (issue #111): idle/quiescence checks,
post-copy verification, and refusing new background work while a migration
is in progress.

dbintegration tests below use two real, throwaway Store instances against
MONGO_TEST_URI (source + target), matching tests/test_db_integration.py's own
"real MongoDB, no mocks" pattern for store.py-level behavior. Route- and
worker-level tests (idle check, job-launch refusal, the MigrationInProgress ->
409 handler) don't need a live database at all and are mocked, matching
tests/test_db_config_migrate_routes.py's pattern for the sibling #110 routes.
"""
import os
import uuid

import pytest

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")


def _server_reachable() -> bool:
    try:
        from pymongo import MongoClient
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


# ============================================================ dbintegration
# store.has_running_job() against a REAL MongoDB.
if _server_reachable():
    from store import Store

    @pytest.fixture()
    def src_store():
        name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
        s = Store(MONGO_TEST_URI, name, dim=8)
        s.get_settings = lambda: s.db["settings"].find_one({"_id": "app"}) or {}
        try:
            yield s
        finally:
            s.client.drop_database(name)
            s.client.close()


    @pytest.mark.dbintegration
    def test_has_running_job_is_none_when_idle(src_store):
        assert src_store.has_running_job() is None


    @pytest.mark.dbintegration
    def test_has_running_job_finds_a_running_job(src_store):
        jid = src_store.create_job("generate", {}, label="a test generation job")
        found = src_store.has_running_job()
        assert found is not None
        assert found["id"] == jid
        assert found["type"] == "generate"
        # Params/logs are stripped -- callers only need enough to explain what's
        # running, not the full job document.
        assert "params" not in found
        assert "logs" not in found


    @pytest.mark.dbintegration
    def test_has_running_job_respects_exclude_types(src_store):
        src_store.create_job("migrate", {}, label="the migration itself")
        # The migration's own launch_job("migrate", ...) call is exempt from
        # seeing its own not-yet-existing row as "something else is running".
        assert src_store.has_running_job(exclude_types=("migrate",)) is None


    @pytest.mark.dbintegration
    def test_has_running_job_ignores_finished_jobs(src_store):
        jid = src_store.create_job("generate", {})
        src_store.update_job(jid, status="succeeded")
        assert src_store.has_running_job() is None


# migrate_to()/verify_migration() together, against TWO real, separate MongoDB
# servers -- migrate_to() intentionally reuses the SOURCE's own db name on
# whatever server target_uri points to (so the same DB_NAME convention applies
# on both sides of a real backend switch), which means a single shared mongod
# can't stand in for "a different target" -- to it, source and target would be
# the literal same database. Optional, separate env var (not the standard
# MONGO_TEST_URI CI already provides) since this needs a second server; skips
# cleanly when it isn't set. Run locally with two containers, e.g.:
#   docker run -d --rm -p 27017:27017 mongo:7
#   docker run -d --rm -p 27018:27017 mongo:7
#   MONGO_TEST_URI=mongodb://localhost:27017 \
#   MONGO_TEST_URI_2=mongodb://localhost:27018 pytest -m dbintegration
MONGO_TEST_URI_2 = os.getenv("MONGO_TEST_URI_2", "")


def _second_server_reachable() -> bool:
    if not MONGO_TEST_URI_2:
        return False
    try:
        from pymongo import MongoClient
        MongoClient(MONGO_TEST_URI_2, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if _server_reachable() and _second_server_reachable():
    @pytest.fixture()
    def cross_server_stores():
        name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
        src = Store(MONGO_TEST_URI, name, dim=8)
        src.get_settings = lambda: src.db["settings"].find_one({"_id": "app"}) or {}
        try:
            yield src
        finally:
            src.client.drop_database(name)
            from pymongo import MongoClient
            MongoClient(MONGO_TEST_URI_2).drop_database(name)
            src.client.close()


    @pytest.mark.dbintegration
    def test_migrate_to_and_verify_migration_confirm_a_real_full_copy(cross_server_stores):
        src = cross_server_stores
        src.projects.insert_many([{"name": "a"}, {"name": "b"}, {"name": "c"}])
        counts = src.migrate_to(MONGO_TEST_URI_2, overwrite=False)
        assert counts["projects"] == 3
        result = src.verify_migration(MONGO_TEST_URI_2, counts)
        assert result["ok"] is True
        assert result["collections"]["projects"]["match"] is True
        assert result["collections"]["projects"]["target_now"] == 3
        assert result["collections"]["projects"]["source_now"] == 3


# ---------------------------------------- verify_migration's comparison logic
# Fake-based (no live Mongo needed at all): deterministic coverage of the exact
# comparison verify_migration does, independent of any real-infrastructure
# constraints above. This is what actually proves the #111 testing-plan
# requirement ("post-migration count verification catches a deliberately-
# induced short copy") without depending on a second server being available.
class _FakeCountColl:
    def __init__(self, count):
        self._count = count

    def count_documents(self, _query):
        return self._count


class _FakeCountDB:
    def __init__(self, counts, name):
        self._counts = counts
        self.name = name

    def __getitem__(self, nm):
        return _FakeCountColl(self._counts.get(nm, 0))


class _FakeSelfStore:
    """Enough of a Store to call BaseStore.verify_migration(self, ...) on
    unbound -- verify_migration only ever touches self.db."""
    def __init__(self, source_counts, db_name="wardeniq"):
        self.db = _FakeCountDB(source_counts, db_name)


class _FakeTargetClient:
    def __init__(self, target_counts, db_name="wardeniq"):
        self._db = _FakeCountDB(target_counts, db_name)

    def __getitem__(self, _name):
        return self._db

    def close(self):
        pass


def test_verify_migration_ok_when_target_exactly_matches(monkeypatch):
    from store import base as store_base
    monkeypatch.setattr(store_base, "MongoClient", lambda *a, **kw: _FakeTargetClient({"projects": 3}))
    fake_self = _FakeSelfStore(source_counts={"projects": 3})
    result = store_base.BaseStore.verify_migration(fake_self, "mongodb://fake-target/", {"projects": 3})
    assert result == {"ok": True, "collections": {
        "projects": {"copied": 3, "target_now": 3, "source_now": 3, "match": True}}}


def test_verify_migration_catches_a_deliberately_induced_short_copy(monkeypatch):
    """The exact scenario #111's testing plan calls for: a copy that CLAIMS to
    have copied N docs but the target doesn't actually have N."""
    from store import base as store_base
    monkeypatch.setattr(store_base, "MongoClient", lambda *a, **kw: _FakeTargetClient({"projects": 2}))
    fake_self = _FakeSelfStore(source_counts={"projects": 5})  # source moved on since the copy
    result = store_base.BaseStore.verify_migration(fake_self, "mongodb://fake-target/", {"projects": 3})
    assert result["ok"] is False
    assert result["collections"]["projects"] == {
        "copied": 3, "target_now": 2, "source_now": 5, "match": False}


def test_verify_migration_reports_per_collection_not_just_overall(monkeypatch):
    """One mismatched collection among several must not be masked by the others
    matching -- `ok` is False and the mismatch is identifiable by name."""
    from store import base as store_base
    monkeypatch.setattr(store_base, "MongoClient",
                        lambda *a, **kw: _FakeTargetClient({"projects": 3, "features": 1}))
    fake_self = _FakeSelfStore(source_counts={"projects": 3, "features": 4})
    result = store_base.BaseStore.verify_migration(
        fake_self, "mongodb://fake-target/", {"projects": 3, "features": 4})
    assert result["ok"] is False
    assert result["collections"]["projects"]["match"] is True
    assert result["collections"]["features"]["match"] is False


# ================================================================== mocked
# workers/registry.py's launch_job()/run_tracked() refusing new work while a
# migration is running -- no live database needed.
def test_launch_job_refuses_when_a_migration_is_running(monkeypatch):
    from core.exceptions import MigrationInProgress
    from workers import registry

    class FakeJobs:
        def find_one(self, query, *a, **kw):
            assert query == {"type": "migrate", "status": "running"}
            return {"_id": "x"}   # something IS running

    monkeypatch.setattr(registry.store, "db", {"jobs": FakeJobs()})
    with pytest.raises(MigrationInProgress):
        registry.launch_job("generate", {}, label="should be refused")


def test_launch_job_allows_the_migration_itself(monkeypatch):
    from workers import registry

    class FakeJobs:
        def find_one(self, *a, **kw):
            raise AssertionError("must not even check for jtype == 'migrate'")

    monkeypatch.setattr(registry.store, "db", {"jobs": FakeJobs()})
    # Should not raise, and must not touch the jobs collection at all for its
    # own type -- the caller (db_migrate route) already did the idle check.
    registry._refuse_if_migrating("migrate")


def test_launch_job_allows_new_work_when_idle(monkeypatch):
    from workers import registry

    class FakeJobs:
        def find_one(self, query, *a, **kw):
            return None   # nothing running

    monkeypatch.setattr(registry.store, "db", {"jobs": FakeJobs()})
    registry._refuse_if_migrating("generate")   # must not raise


def test_run_tracked_also_refuses_during_a_migration(monkeypatch):
    from core.exceptions import MigrationInProgress
    from workers import registry

    class FakeJobs:
        def find_one(self, *a, **kw):
            return {"_id": "x"}

    monkeypatch.setattr(registry.store, "db", {"jobs": FakeJobs()})
    with pytest.raises(MigrationInProgress):
        registry.run_tracked("pr_coverage", lambda: None)


# ------------------------------------------------ MigrationInProgress -> 409
def test_migration_in_progress_becomes_a_clean_409(monkeypatch):
    import auth
    import main
    from core.exceptions import MigrationInProgress
    from fastapi.testclient import TestClient

    main.store.add_audit = lambda *a, **kw: True
    user = {"id": "u1", "email": "u1@example.com", "role": "admin",
           "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}

    # A path outside ADMIN_PATHS/PUBLIC_EXACT so the auth gateway just requires
    # "signed in", matching how a real launch_job()-calling route (e.g. /api/generate)
    # is gated -- this route only exists to exercise the registered exception
    # handler itself, not to re-test auth_gateway's own admin-path logic.
    @main.app.get("/__test_migration_in_progress")
    def _boom():  # pragma: no cover -- exercised only via the test client below
        raise MigrationInProgress("a database migration is in progress — try again once it finishes")

    client = TestClient(main.app)
    r = client.get("/__test_migration_in_progress", cookies=cookie)
    assert r.status_code == 409
    assert "migration is in progress" in r.json()["detail"]


# ------------------------------------------------------- /api/db-migrate route
def test_db_migrate_refuses_while_sync_poller_is_running(monkeypatch):
    import auth
    import main
    from api.routes import settings as settings_mod
    from fastapi.testclient import TestClient

    main.store.add_audit = lambda *a, **kw: True
    client = TestClient(main.app)
    user = {"id": "u1", "email": "admin@example.com", "role": "admin",
           "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}

    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setitem(settings_mod.SYNC, "running", True)
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: launched.append(a) or "job1")

    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 409
    assert "sync is currently running" in r.json()["detail"]
    assert launched == []


def test_db_migrate_refuses_while_a_job_is_running(monkeypatch):
    import auth
    import main
    from api.routes import settings as settings_mod
    from fastapi.testclient import TestClient

    main.store.add_audit = lambda *a, **kw: True
    client = TestClient(main.app)
    user = {"id": "u1", "email": "admin@example.com", "role": "admin",
           "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}

    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod.store, "has_running_job",
                        lambda: {"type": "generate", "label": "Generate test cases"})
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: launched.append(a) or "job1")

    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 409
    assert "wardenIQ is currently busy" in r.json()["detail"]
    assert launched == []


def test_db_migrate_override_busy_bypasses_the_idle_check(monkeypatch):
    import auth
    import main
    from api.routes import settings as settings_mod
    from fastapi.testclient import TestClient

    main.store.add_audit = lambda *a, **kw: True
    client = TestClient(main.app)
    user = {"id": "u1", "email": "admin@example.com", "role": "admin",
           "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}

    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setattr(settings_mod.store, "has_running_job",
                        lambda: {"type": "generate", "label": "Generate test cases"})
    monkeypatch.setattr(settings_mod, "_probe_mongo", lambda uri: (True, True, "ok"))
    monkeypatch.setattr(settings_mod.store, "target_has_data", lambda uri: False)
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job", lambda *a, **kw: launched.append(a) or "job1")

    r = client.post("/api/db-migrate",
                    json={"target_uri": "mongodb://good/", "override_busy": True}, cookies=cookie)
    assert r.status_code == 200
    assert launched != []


def test_db_migrate_proceeds_when_idle(monkeypatch):
    import auth
    import main
    from api.routes import settings as settings_mod
    from fastapi.testclient import TestClient

    main.store.add_audit = lambda *a, **kw: True
    client = TestClient(main.app)
    user = {"id": "u1", "email": "admin@example.com", "role": "admin",
           "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    cookie = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}

    monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
    monkeypatch.setitem(settings_mod.SYNC, "running", False)
    monkeypatch.setattr(settings_mod.store, "has_running_job", lambda: None)
    monkeypatch.setattr(settings_mod, "_probe_mongo", lambda uri: (True, True, "ok"))
    monkeypatch.setattr(settings_mod.store, "target_has_data", lambda uri: False)
    launched = []
    monkeypatch.setattr(settings_mod, "launch_job",
                        lambda jtype, params, label="": launched.append((jtype, params)) or "job1")

    r = client.post("/api/db-migrate", json={"target_uri": "mongodb://good/"}, cookies=cookie)
    assert r.status_code == 200
    assert r.json()["job_id"] == "job1"
    assert launched == [("migrate", {"target_uri": "mongodb://good/", "overwrite": False})]
