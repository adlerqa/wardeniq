"""Hardening for /api/db-migrate (issue #111): idle/quiescence check, refusing new work
while a migration runs, and post-copy verification that fails closed.

Everything here uses the CURRENT capability-probe contract (settings._probe_mongo()
returns a dict with reachable / search_ok / status / detail ...), stubbed at that
boundary; the probe itself is covered by tests/test_mongo_capability_probe.py.

Layers:
  * route tests          -- the idle check, override, and the start lock (fakes)
  * registry/state tests -- new-job refusal and "migration in progress" being cleared
                            (in-memory job store + real launch_job threads)
  * worker tests         -- what the caller/user sees when verification passes, fails,
                            or cannot run (fake store)
  * verify_migration     -- the counting rules themselves (fake Mongo clients)
  * dbintegration        -- the same against REAL servers:
        MONGO_TEST_URI     any reachable MongoDB (source)
        MONGO_TEST_URI_2   a second, separate MongoDB (target); tests skip without it
    Every real test uses throwaway database names and drops them afterwards.
"""
import os
import threading
import time
import uuid

import auth
import main
import pytest
from api.routes import settings as settings_mod
from api.routes import webhooks as webhooks_mod
from core import exceptions as exc_mod
from core.exceptions import MigrationInProgress
from fastapi import FastAPI
from fastapi.testclient import TestClient
from store import base as store_base
from workers import generation as gen
from workers import registry

client = TestClient(main.app)
URI = "mongodb://target.example.test:27017/?replicaSet=rs0"


# ================================================================== route tests
def _admin():
    return {"id": "u1", "email": "u1@example.com", "role": "admin",
            "active": True, "session_version": 0, "all_projects": True}


def _cookie():
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}


def _probe_result(**over):
    base = {"reachable": True, "replica_set": True, "server_version": "8.3.4",
            "search_ok": True, "status": "ok", "detail": "ok"}
    base.update(over)
    return base


class RouteEnv:
    """Stubs everything around /api/db-migrate: auth, .env, probe (current dict
    contract), target inspection, the job store's running-job lookup, SYNC and the
    job launch. `events` records the order of audit / probe / launch."""

    def __init__(self, monkeypatch, probe=None, running_jobs=None, migrating=False, sync=False):
        self.events, self.launched = [], []
        self.running_jobs = list(running_jobs or [])   # non-migrate running jobs
        self.migrating = migrating
        self.probe_calls = []
        monkeypatch.setattr(main.store, "get_user", lambda uid: _admin() if uid == "u1" else None)
        monkeypatch.setattr(main.store, "add_audit", lambda *a, **k: True)
        monkeypatch.setattr(main.store, "dim", 768, raising=False)
        monkeypatch.setattr(main.store, "target_has_data", lambda uri: False)
        monkeypatch.setattr(main.store, "has_running_job", self._has_running_job)
        monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
        monkeypatch.setitem(settings_mod.SYNC, "running", sync)
        monkeypatch.setattr(settings_mod, "_audit",
                            lambda *a, **k: self.events.append("audit"))
        self._probe = probe if probe is not None else _probe_result()
        monkeypatch.setattr(settings_mod, "_probe_mongo", self._probe_mongo)
        monkeypatch.setattr(settings_mod, "launch_job", self._launch_job)

    def _has_running_job(self, only_types=(), exclude_types=()):
        if only_types == ("migrate",):
            return {"id": "m1", "type": "migrate"} if self.migrating else None
        return self.running_jobs[0] if self.running_jobs else None

    def _probe_mongo(self, uri, dim=None):
        self.events.append("probe")
        self.probe_calls.append((uri, dim))
        return self._probe

    def _launch_job(self, jtype, params, label=""):
        self.events.append("launch")
        self.launched.append((jtype, params))
        return "job-1"

    def post(self, **body):
        body.setdefault("target_uri", URI)
        return client.post("/api/db-migrate", json=body, cookies=_cookie())


def test_idle_system_starts_the_migration(monkeypatch):
    env = RouteEnv(monkeypatch)
    r = env.post()
    assert r.status_code == 200 and r.json() == {"job_id": "job-1"}
    assert env.launched == [("migrate", {"target_uri": URI, "overwrite": False,
                                         "override_busy": False})]
    assert env.probe_calls == [(URI, 768)]          # current probe contract + store.dim


def test_audit_entry_is_written_before_the_copy_starts(monkeypatch):
    # An audit insert AFTER the worker started copying would count as the source
    # changing mid-copy and fail verification of an otherwise clean migration.
    env = RouteEnv(monkeypatch)
    env.post()
    assert env.events.index("audit") < env.events.index("launch")


def test_running_job_refuses_the_migration_before_the_probe(monkeypatch):
    env = RouteEnv(monkeypatch, running_jobs=[{"id": "j1", "type": "generate",
                                               "label": "Generate tests"}])
    r = env.post()
    assert r.status_code == 409
    assert "busy" in r.json()["detail"] and "Generate tests" in r.json()["detail"]
    assert "start anyway" in r.json()["detail"]
    assert env.launched == [] and env.probe_calls == []     # cheap refusal first


def test_running_sync_refuses_the_migration(monkeypatch):
    env = RouteEnv(monkeypatch, sync=True)
    r = env.post()
    assert r.status_code == 409 and "sync is currently running" in r.json()["detail"]
    assert env.launched == [] and env.probe_calls == []


def test_override_busy_bypasses_a_running_job_and_is_passed_to_the_worker(monkeypatch):
    env = RouteEnv(monkeypatch, running_jobs=[{"id": "j1", "type": "generate"}])
    r = env.post(override_busy=True)
    assert r.status_code == 200
    assert env.launched[0][1]["override_busy"] is True


def test_override_busy_bypasses_a_running_sync(monkeypatch):
    env = RouteEnv(monkeypatch, sync=True)
    assert env.post(override_busy=True).status_code == 200


def test_a_migration_already_running_is_never_overridable(monkeypatch):
    env = RouteEnv(monkeypatch, migrating=True)
    for body in ({}, {"override_busy": True}, {"overwrite": True, "override_busy": True}):
        r = env.post(**body)
        assert r.status_code == 409 and "already in progress" in r.json()["detail"]
    assert env.launched == []


def test_overwrite_does_not_stand_in_for_override_busy(monkeypatch):
    env = RouteEnv(monkeypatch, running_jobs=[{"id": "j1", "type": "generate"}])
    assert env.post(overwrite=True).status_code == 409
    assert env.launched == []


def test_probe_failure_still_returns_the_current_probe_response(monkeypatch):
    # Current contract: a dict. An unreachable target and a search-incapable one keep
    # their specific messages, and nothing is launched.
    env = RouteEnv(monkeypatch, probe=_probe_result(reachable=False, search_ok=False,
                                                    status="unreachable", detail="refused"))
    r = env.post()
    assert r.status_code == 400 and "refused" in r.json()["detail"]
    assert "Nothing copied" in r.json()["detail"] and env.launched == []

    env = RouteEnv(monkeypatch, probe=_probe_result(search_ok=False, status="no_search",
                                                    detail="No vector search here."))
    r = env.post()
    assert r.status_code == 400 and "No vector search here." in r.json()["detail"]
    assert "nothing copied" in r.json()["detail"] and env.launched == []


def test_busy_check_runs_again_right_before_launch(monkeypatch):
    # The capability probe can take up to a minute: a job that starts meanwhile must
    # still block the migration.
    env = RouteEnv(monkeypatch)
    real_probe = env._probe_mongo

    def probe_then_job_starts(uri, dim=None):
        out = real_probe(uri, dim=dim)
        env.running_jobs.append({"id": "j2", "type": "generate", "label": "Late job"})
        return out
    monkeypatch.setattr(settings_mod, "_probe_mongo", probe_then_job_starts)
    r = env.post()
    assert r.status_code == 409 and "Late job" in r.json()["detail"]
    assert env.launched == [] and "audit" not in env.events


def test_concurrent_start_is_refused_by_the_start_lock(monkeypatch):
    env = RouteEnv(monkeypatch)
    assert settings_mod._MIGRATE_START_LOCK.acquire(blocking=False)
    try:
        r = env.post()
    finally:
        settings_mod._MIGRATE_START_LOCK.release()
    assert r.status_code == 409 and "already being started" in r.json()["detail"]
    assert env.launched == []


def test_start_lock_is_released_after_a_refusal_and_after_a_launch_error(monkeypatch):
    env = RouteEnv(monkeypatch, running_jobs=[{"id": "j1", "type": "generate"}])
    assert env.post().status_code == 409                       # early refusal
    env.running_jobs.clear()
    # launch itself blows up -> lock must still be released for the next request
    monkeypatch.setattr(settings_mod, "launch_job",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        TestClient(main.app, raise_server_exceptions=True).post(
            "/api/db-migrate", json={"target_uri": URI}, cookies=_cookie())
    assert settings_mod._MIGRATE_START_LOCK.acquire(blocking=False)
    settings_mod._MIGRATE_START_LOCK.release()
    monkeypatch.setattr(settings_mod, "launch_job", env._launch_job)
    assert env.post().status_code == 200


# ========================================================== registry / state tests
class MemoryJobs:
    """Just enough of the job store for launch_job()/run_tracked() and the guard."""

    def __init__(self):
        self.jobs = {}
        self._n = 0
        self.lock = threading.Lock()

    def create_job(self, jtype, params, label="", project_id=None, feature_id=None):
        with self.lock:
            self._n += 1
            jid = f"j{self._n}"
            self.jobs[jid] = {"id": jid, "type": jtype, "status": "running", "error": None}
            return jid

    def update_job(self, jid, **fields):
        self.jobs[jid].update(fields)

    def get_job(self, jid):
        return dict(self.jobs[jid])

    def get_settings(self):
        return {}

    def set_job_usage(self, jid, usage):
        pass

    def has_running_job(self, only_types=(), exclude_types=()):
        for j in self.jobs.values():
            if j["status"] != "running":
                continue
            if only_types and j["type"] not in only_types:
                continue
            if exclude_types and j["type"] in exclude_types:
                continue
            return dict(j)
        return None


@pytest.fixture()
def memjobs(monkeypatch):
    mem = MemoryJobs()
    monkeypatch.setattr(registry, "store", mem)
    from contextlib import nullcontext
    monkeypatch.setattr(registry, "heartbeat", lambda jid, *a, **k: nullcontext())
    return mem


def _wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_new_jobs_are_refused_while_a_migration_is_running(memjobs, monkeypatch):
    release = threading.Event()
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", lambda jid, p: release.wait(5))
    monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: None)
    registry.launch_job("migrate", {})
    try:
        with pytest.raises(MigrationInProgress):
            registry.launch_job("generate", {})
        with pytest.raises(MigrationInProgress):
            registry.run_tracked("pr_coverage", lambda: 1)
        # nothing was created for the refused attempts
        assert [j["type"] for j in memjobs.jobs.values()] == ["migrate"]
    finally:
        release.set()


def test_the_migration_itself_is_exempt_from_the_guard(memjobs, monkeypatch):
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", lambda jid, p: None)
    jid = registry.launch_job("migrate", {})
    assert jid == "j1"


def test_jobs_start_normally_when_no_migration_is_running(memjobs, monkeypatch):
    monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: None)
    jid = registry.launch_job("generate", {})
    assert _wait_for(lambda: memjobs.jobs[jid]["status"] == "succeeded")
    assert registry.run_tracked("pr_coverage", lambda: 42) == 42


def test_a_failed_migration_clears_the_in_progress_state(memjobs, monkeypatch):
    def failing_worker(jid, params):
        raise RuntimeError("verification failed")
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", failing_worker)
    monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: None)
    mjid = registry.launch_job("migrate", {})
    assert _wait_for(lambda: memjobs.jobs[mjid]["status"] == "failed")
    assert "verification failed" in memjobs.jobs[mjid]["error"]
    assert memjobs.has_running_job(only_types=("migrate",)) is None
    registry.launch_job("generate", {})                  # accepted again, no exception


def test_a_successful_migration_clears_the_in_progress_state(memjobs, monkeypatch):
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", lambda jid, p: None)
    monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: None)
    mjid = registry.launch_job("migrate", {})
    assert _wait_for(lambda: memjobs.jobs[mjid]["status"] == "succeeded")
    registry.launch_job("generate", {})


def test_migration_in_progress_becomes_a_clean_409():
    assert MigrationInProgress in main.app.exception_handlers
    app = FastAPI()
    app.exception_handler(MigrationInProgress)(exc_mod.migration_in_progress_handler)

    @app.get("/boom")
    def boom():
        raise MigrationInProgress(exc_mod.MIGRATION_IN_PROGRESS_MSG)
    r = TestClient(app).get("/boom")
    assert r.status_code == 409 and "migration is in progress" in r.json()["detail"]


def test_webhook_thread_logs_a_dropped_event_instead_of_a_traceback(monkeypatch):
    lines = []

    class Rec:
        def warning(self, fmt, *a):
            lines.append(fmt % a)
    monkeypatch.setattr(webhooks_mod, "log", Rec())

    def refused(repo, pr):
        raise MigrationInProgress()
    monkeypatch.setattr(webhooks_mod, "ingest_pr_tracked", refused)
    webhooks_mod._ingest_pr_in_thread({"full_name": "acme/app"}, {"number": 1})   # no raise
    assert lines and "acme/app" in lines[0] and "migration is in progress" in lines[0]

    def broken(repo, pr):
        raise ValueError("real bug")
    monkeypatch.setattr(webhooks_mod, "ingest_pr_tracked", broken)
    with pytest.raises(ValueError):                    # other errors are NOT swallowed
        webhooks_mod._ingest_pr_in_thread({"full_name": "acme/app"}, {})


# ================================================================== worker tests
class WorkerStore:
    def __init__(self, counts=None, verification=None, verify_error=None, migrate_error=None):
        self.counts = counts if counts is not None else {"projects": 3, "test_cases": 10}
        self.verification = verification or {"ok": True, "failures": [], "warnings": [],
                                             "collections": {}}
        self.verify_error, self.migrate_error = verify_error, migrate_error
        self.progress, self.result, self.verify_args = [], {}, None

    def update_job_progress(self, jid, stage, progress=None):
        self.progress.append((stage, progress))

    def migrate_to(self, target, overwrite=False, progress=None):
        if self.migrate_error:
            raise self.migrate_error
        return dict(self.counts)

    def verify_migration(self, target, counts, allow_source_drift=False):
        self.verify_args = (target, counts, allow_source_drift)
        if self.verify_error:
            raise self.verify_error
        return self.verification

    def merge_job_result(self, jid, **fields):
        self.result.update(fields)


@pytest.fixture()
def worker_env(monkeypatch):
    env = type("E", (), {})()
    env.env_writes = []
    monkeypatch.setattr(gen, "_write_env_var",
                        lambda path, k, v: env.env_writes.append((k, v)) or (True, None))

    def use(store):
        monkeypatch.setattr(gen, "store", store)
        return store
    env.use = use
    return env


PARAMS = {"target_uri": URI, "overwrite": False, "override_busy": False}


def test_verified_migration_reports_a_normal_success(worker_env):
    st = worker_env.use(WorkerStore())
    gen._migrate_worker("j", dict(PARAMS))
    assert worker_env.env_writes == [("MONGO_URI", URI)]
    assert st.result["switched"] is True and st.result["restart_required"] is True
    assert st.result["verified"] is True and st.result["warnings"] == []
    assert st.result["apply_cmd"] == "docker compose up -d"
    assert st.result["total_docs"] == 13
    assert st.progress[-1] == ("done", 100)
    assert st.verify_args == (URI, {"projects": 3, "test_cases": 10}, False)


def test_count_mismatch_fails_the_job_and_does_not_switch(worker_env):
    verification = {"ok": False, "warnings": [],
                    "failures": ["'test_cases': 10 documents were copied but the target has 8"],
                    "collections": {"test_cases": {"copied": 10, "target_now": 8}}}
    st = worker_env.use(WorkerStore(verification=verification))
    with pytest.raises(RuntimeError) as e:
        gen._migrate_worker("j", dict(PARAMS))
    msg = str(e.value)
    assert "did not pass verification" in msg and "NOT switched" in msg
    assert "'test_cases': 10 documents were copied but the target has 8" in msg
    assert "Your current database is unchanged" in msg
    assert worker_env.env_writes == []                         # .env untouched
    assert st.result["switched"] is False and st.result["restart_required"] is False
    assert st.result["verified"] is False
    assert st.result["verification"]["failures"] == verification["failures"]   # details kept
    assert ("done", 100) not in st.progress                    # never reached "done"


def test_unverifiable_copy_fails_closed(worker_env):
    st = worker_env.use(WorkerStore(verify_error=ConnectionError("target went away")))
    with pytest.raises(RuntimeError) as e:
        gen._migrate_worker("j", dict(PARAMS))
    assert "could not be verified" in str(e.value) and "NOT switched" in str(e.value)
    assert worker_env.env_writes == []
    assert st.result["verified"] is False and st.result["switched"] is False
    assert st.result["restart_required"] is False


def test_verification_error_message_never_contains_the_connection_string(worker_env):
    secret = "mongodb://user:Pw0rdMarker@db.example.test/"
    worker_env.use(WorkerStore(verify_error=ConnectionError("target went away")))
    with pytest.raises(RuntimeError) as e:
        gen._migrate_worker("j", {**PARAMS, "target_uri": secret})
    assert "Pw0rdMarker" not in str(e.value) and "db.example.test" not in str(e.value)


def test_override_busy_is_passed_to_verification_and_warnings_do_not_fail_the_job(worker_env):
    verification = {"ok": True, "failures": [],
                    "warnings": ["'jobs': 4 documents were copied but the source now has 5"],
                    "collections": {}}
    st = worker_env.use(WorkerStore(verification=verification))
    gen._migrate_worker("j", {**PARAMS, "override_busy": True})
    assert st.verify_args[2] is True
    assert worker_env.env_writes == [("MONGO_URI", URI)]
    assert st.result["switched"] is True
    assert st.result["warnings"] == verification["warnings"]   # surfaced, not dropped


def test_copy_failure_still_leaves_the_env_untouched(worker_env):
    worker_env.use(WorkerStore(migrate_error=RuntimeError("target full")))
    with pytest.raises(RuntimeError, match="target full"):
        gen._migrate_worker("j", dict(PARAMS))
    assert worker_env.env_writes == []


def test_env_write_failure_after_a_verified_copy_is_still_an_error(worker_env, monkeypatch):
    worker_env.use(WorkerStore())
    monkeypatch.setattr(gen, "_write_env_var", lambda *a: (False, "read-only"))
    with pytest.raises(RuntimeError, match="writing the config file failed"):
        gen._migrate_worker("j", dict(PARAMS))


# ========================================================= verify_migration (fakes)
class FakeColl:
    def __init__(self, n=None, error=None):
        self.n, self.error = n, error

    def count_documents(self, flt):
        if self.error:
            raise self.error
        return self.n


class FakeDatabase:
    def __init__(self, counts, name="wardeniq", extra_names=(), error=None):
        self.name, self.counts, self.extra, self.error = name, counts, list(extra_names), error

    def __getitem__(self, nm):
        return FakeColl(self.counts.get(nm, 0), self.error)

    def list_collection_names(self):
        return list(self.counts) + self.extra + ["system.views"]


class FakeTargetClient:
    def __init__(self, counts, error=None):
        self.db = FakeDatabase(counts, error=error)
        self.closed = False

    def __getitem__(self, name):
        return self.db

    def close(self):
        self.closed = True


class FakeSelf:
    def __init__(self, source_counts, extra_names=()):
        self.db = FakeDatabase(source_counts, extra_names=extra_names)


def _verify(monkeypatch, copied, target, source, allow=False, extra=(), target_error=None):
    client_ = FakeTargetClient(target, error=target_error)
    monkeypatch.setattr(store_base, "MongoClient", lambda *a, **k: client_)
    out = store_base.BaseStore.verify_migration(FakeSelf(source, extra), URI, copied,
                                                allow_source_drift=allow)
    assert client_.closed is True
    return out


def test_verify_ok_when_target_and_source_both_match_the_copy(monkeypatch):
    out = _verify(monkeypatch, {"a": 3, "b": 5}, {"a": 3, "b": 5}, {"a": 3, "b": 5})
    assert out["ok"] is True and out["failures"] == [] and out["warnings"] == []
    assert out["collections"]["a"] == {"copied": 3, "target_now": 3, "source_now": 3,
                                       "target_match": True, "source_match": True}


def test_verify_fails_when_the_target_is_short(monkeypatch):
    out = _verify(monkeypatch, {"a": 3, "b": 5}, {"a": 3, "b": 4}, {"a": 3, "b": 5})
    assert out["ok"] is False
    assert out["failures"] == ["'b': 5 documents were copied but the target has 4"]
    assert out["collections"]["b"]["target_match"] is False
    assert out["collections"]["a"]["target_match"] is True      # reported per collection


def test_target_shortfall_fails_even_with_override(monkeypatch):
    out = _verify(monkeypatch, {"b": 5}, {"b": 4}, {"b": 5}, allow=True)
    assert out["ok"] is False and "target has 4" in out["failures"][0]


def test_verify_fails_when_the_source_changed_during_the_copy(monkeypatch):
    out = _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 5})
    assert out["ok"] is False
    assert "the source now has 5" in out["failures"][0] and "changed during the copy" in out["failures"][0]
    assert out["collections"]["a"]["source_match"] is False


def test_source_drift_is_only_a_warning_with_override(monkeypatch):
    out = _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 5}, allow=True)
    assert out["ok"] is True and out["failures"] == []
    assert "the source now has 5" in out["warnings"][0]


def test_collection_created_on_the_source_during_the_copy_is_flagged(monkeypatch):
    out = _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 3}, extra=["late_collection"])
    assert out["ok"] is False and "'late_collection' was created on the source" in out["failures"][0]
    out = _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 3}, extra=["late_collection"], allow=True)
    assert out["ok"] is True and out["warnings"]


def test_system_collections_are_not_counted_as_drift(monkeypatch):
    out = _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 3})     # fake adds system.views
    assert out["ok"] is True and out["warnings"] == []


def test_verify_raises_when_counts_cannot_be_obtained(monkeypatch):
    with pytest.raises(ConnectionError):
        _verify(monkeypatch, {"a": 3}, {"a": 3}, {"a": 3},
                target_error=ConnectionError("lost"))


def test_verify_messages_never_contain_the_connection_string(monkeypatch):
    out = _verify(monkeypatch, {"a": 3}, {"a": 1}, {"a": 4})
    assert "example.test" not in repr(out) and "target." not in repr(out)


# ======================================================== dbintegration (real servers)
MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")
MONGO_TEST_URI_2 = os.getenv("MONGO_TEST_URI_2", "")


def _reachable(uri):
    if not uri:
        return False
    try:
        from pymongo import MongoClient
        MongoClient(uri, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture()
def real_source():
    if not _reachable(MONGO_TEST_URI):
        pytest.skip(f"no MongoDB reachable at MONGO_TEST_URI={MONGO_TEST_URI!r}")
    from store import Store
    name = f"wardeniq_mig_{uuid.uuid4().hex[:10]}"
    s = Store(MONGO_TEST_URI, name, dim=8)
    try:
        yield s
    finally:
        s.client.drop_database(name)
        s.client.close()


@pytest.fixture()
def real_pair(real_source):
    if not _reachable(MONGO_TEST_URI_2):
        pytest.skip("set MONGO_TEST_URI_2 to a second, separate MongoDB to run this")
    from pymongo import MongoClient
    tgt = MongoClient(MONGO_TEST_URI_2)
    try:
        yield real_source, tgt
    finally:
        tgt.drop_database(real_source.db.name)
        tgt.close()


@pytest.mark.dbintegration
def test_real_has_running_job(real_source):
    s = real_source
    assert s.has_running_job() is None
    gen_id = s.create_job("generate", {}, label="Generate tests")
    mig_id = s.create_job("migrate", {}, label="Migrate")
    assert s.has_running_job()["type"] in ("generate", "migrate")
    assert s.has_running_job(only_types=("migrate",))["id"] == mig_id
    assert s.has_running_job(exclude_types=("migrate",))["id"] == gen_id
    s.update_job(gen_id, status="succeeded")
    assert s.has_running_job(exclude_types=("migrate",)) is None
    s.update_job(mig_id, status="failed")
    assert s.has_running_job() is None                      # failed != in progress


@pytest.mark.dbintegration
def test_real_copy_verifies_clean(real_pair):
    src, tgt = real_pair
    src.projects.insert_many([{"name": "a"}, {"name": "b"}, {"name": "c"}])
    counts = src.migrate_to(MONGO_TEST_URI_2)
    v = src.verify_migration(MONGO_TEST_URI_2, counts)
    assert v["ok"] is True and v["failures"] == [] and v["warnings"] == []
    assert v["collections"]["projects"] == {"copied": 3, "target_now": 3, "source_now": 3,
                                            "target_match": True, "source_match": True}


@pytest.mark.dbintegration
def test_real_short_target_is_detected(real_pair):
    src, tgt = real_pair
    src.projects.insert_many([{"name": n} for n in "abcde"])
    counts = src.migrate_to(MONGO_TEST_URI_2)
    tgt[src.db.name]["projects"].delete_one({"name": "c"})        # lose one on the way
    v = src.verify_migration(MONGO_TEST_URI_2, counts)
    assert v["ok"] is False
    assert v["failures"] == ["'projects': 5 documents were copied but the target has 4"]


@pytest.mark.dbintegration
def test_real_source_written_after_the_copy_is_detected_and_overridable(real_pair):
    src, tgt = real_pair
    src.projects.insert_many([{"name": "a"}, {"name": "b"}])
    counts = src.migrate_to(MONGO_TEST_URI_2)
    src.projects.insert_one({"name": "late"})                      # lands after the copy
    strict = src.verify_migration(MONGO_TEST_URI_2, counts)
    assert strict["ok"] is False and "the source now has 3" in strict["failures"][0]
    lenient = src.verify_migration(MONGO_TEST_URI_2, counts, allow_source_drift=True)
    assert lenient["ok"] is True and "the source now has 3" in lenient["warnings"][0]


def _run_real_worker(monkeypatch, src, tmp_path, params, after_copy=None):
    """Run the real _migrate_worker against real source + target servers; return
    (job_dict, env_file_text_or_None, raised_exception_or_None)."""
    env_file = tmp_path / ".env"
    writes = []
    monkeypatch.setattr(gen, "store", src)
    monkeypatch.setattr(gen, "_write_env_var",
                        lambda path, k, v: writes.append((k, v)) or (True, None))
    if after_copy:
        real_copy = src.migrate_to

        def copy_then_tamper(target, **kw):
            out = real_copy(target, **kw)
            after_copy()
            return out
        monkeypatch.setattr(src, "migrate_to", copy_then_tamper)
    jid = src.create_job("migrate", dict(params), label="Migrate")
    err = None
    try:
        gen._migrate_worker(jid, dict(params))
    except Exception as e:  # noqa: BLE001
        err = e
    return src.get_job(jid), writes, err, env_file


@pytest.mark.dbintegration
def test_real_worker_success_switches_and_reports_verified(real_pair, monkeypatch, tmp_path):
    src, tgt = real_pair
    src.projects.insert_many([{"name": "a"}, {"name": "b"}])
    job, writes, err, _ = _run_real_worker(
        monkeypatch, src, tmp_path,
        {"target_uri": MONGO_TEST_URI_2, "overwrite": False, "override_busy": False})
    assert err is None
    assert writes == [("MONGO_URI", MONGO_TEST_URI_2)]
    r = job["result"]
    assert r["verified"] is True and r["switched"] is True and r["restart_required"] is True
    assert r["verification"]["ok"] is True and r["warnings"] == []
    assert tgt[src.db.name]["projects"].count_documents({}) == 2


@pytest.mark.dbintegration
def test_real_worker_mismatch_fails_closed_with_details(real_pair, monkeypatch, tmp_path):
    src, tgt = real_pair
    src.projects.insert_many([{"name": n} for n in "abcd"])
    job, writes, err, _ = _run_real_worker(
        monkeypatch, src, tmp_path,
        {"target_uri": MONGO_TEST_URI_2, "overwrite": False, "override_busy": False},
        after_copy=lambda: tgt[src.db.name]["projects"].delete_one({"name": "b"}))
    assert isinstance(err, RuntimeError)
    assert "NOT switched" in str(err) and "'projects': 4 documents were copied but the target has 3" in str(err)
    assert writes == []                                             # .env never written
    r = job["result"]
    assert r["switched"] is False and r["restart_required"] is False and r["verified"] is False
    assert r["verification"]["failures"] == ["'projects': 4 documents were copied but the target has 3"]
    assert job.get("stage") != "done"


@pytest.mark.dbintegration
def test_real_worker_source_drift_fails_by_default_and_warns_with_override(
        real_pair, monkeypatch, tmp_path):
    src, tgt = real_pair
    src.projects.insert_many([{"name": "a"}, {"name": "b"}])
    base = {"target_uri": MONGO_TEST_URI_2, "overwrite": False}
    job, writes, err, _ = _run_real_worker(
        monkeypatch, src, tmp_path, {**base, "override_busy": False},
        after_copy=lambda: src.projects.insert_one({"name": "late1"}))
    assert isinstance(err, RuntimeError) and "changed during the copy" in str(err)
    assert writes == [] and job["result"]["switched"] is False

    # Same situation, but the user accepted a best-effort snapshot: succeeds WITH a warning.
    # (overwrite: the first attempt already put data in the target)
    job, writes, err, _ = _run_real_worker(
        monkeypatch, src, tmp_path, {**base, "overwrite": True, "override_busy": True},
        after_copy=lambda: src.projects.insert_one({"name": "late2"}))
    assert err is None and writes == [("MONGO_URI", MONGO_TEST_URI_2)]
    assert job["result"]["switched"] is True
    assert any("changed during the copy" in w for w in job["result"]["warnings"])
