"""Every way of launching a database migration must enforce the same safety rules (#111).

Regression for a review finding: POST /api/jobs/{id}/retry called launch_job("migrate", ...)
directly, so retrying a failed migration skipped the idle check, the "one migration at a
time" rule, the capability probe and the non-empty-target guard. (With a migration running,
a retry started a second one; with `overwrite` saved in the job's params the second run
could delete target collections the first was still copying into.)

These tests drive the REAL retry endpoint, the REAL /api/db-migrate route and the REAL
workers.registry over an in-memory job store (only the Mongo probe, the target inspection and
the migrate worker itself are stubbed), so nothing in the launch path is bypassed by a fake.
"""
import threading
import time
from contextlib import nullcontext

import auth
import main
import pytest
from api.routes import jobs_usage as jobs_usage_mod
from api.routes import settings as settings_mod
from core.exceptions import MigrationBlocked, MigrationInProgress
from core.state import SYNC
from fastapi.testclient import TestClient
from test_db_migration_hardening import MemoryJobs
from workers import registry

client = TestClient(main.app)
PW = "Pw0rdMarker"
TARGET = f"mongodb://admin:{PW}@target.example.test:27017/?replicaSet=rs0"


class Jobs(MemoryJobs):
    """MemoryJobs that also keeps params/label/project, like the real job store."""

    def create_job(self, jtype, params, label="", project_id=None, feature_id=None):
        jid = super().create_job(jtype, params, label, project_id, feature_id)
        self.jobs[jid].update(params=params, label=label, project_id=project_id,
                              feature_id=feature_id, stage="starting", progress=0)
        return jid


def _probe_ok(**over):
    base = {"reachable": True, "replica_set": True, "server_version": "8.3.4",
            "search_ok": True, "status": "ok", "detail": "ok"}
    base.update(over)
    return base


class Live:
    """The real launch path over an in-memory job store."""

    def __init__(self, monkeypatch, role="admin"):
        self.mem = Jobs()
        self.audit, self.probe_calls, self.target_checks, self.started = [], [], [], []
        self.target_has_data = False
        self.probe = _probe_ok()
        self.gate = threading.Event()
        self._baseline_threads = threading.active_count()
        self.user = {"id": "u1", "email": "u1@example.com", "role": role, "active": True,
                     "session_version": 0, "all_projects": True}
        for name in ("create_job", "update_job", "get_job", "has_running_job",
                     "get_settings", "set_job_usage"):
            monkeypatch.setattr(main.store, name, getattr(self.mem, name))
        monkeypatch.setattr(main.store, "get_user", lambda uid: self.user)
        monkeypatch.setattr(main.store, "add_audit",
                            lambda action, **kw: self.audit.append(action) or True)
        monkeypatch.setattr(main.store, "dim", 768, raising=False)
        monkeypatch.setattr(main.store, "target_has_data", self._target_has_data)
        monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
        monkeypatch.setattr(settings_mod, "_probe_mongo", self._probe_mongo)
        monkeypatch.setitem(SYNC, "running", False)
        monkeypatch.setattr(registry, "heartbeat", lambda jid, *a, **k: nullcontext())
        monkeypatch.setitem(registry.JOB_WORKERS, "migrate", self._migrate_worker)
        monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: None)

    # --- stubs
    def _probe_mongo(self, uri, dim=None):
        self.probe_calls.append((uri, dim))
        return self.probe

    def _target_has_data(self, uri):
        self.target_checks.append(uri)
        return self.target_has_data

    def _migrate_worker(self, jid, params):
        self.started.append(jid)
        self.gate.wait(10)

    # --- helpers
    def add_job(self, jtype, status="running", params=None, label=""):
        jid = self.mem.create_job(jtype, params if params is not None else {}, label)
        self.mem.jobs[jid]["status"] = status
        return jid

    def count(self, jtype):
        return sum(1 for j in self.mem.jobs.values() if j["type"] == jtype)

    def running(self, jtype):
        return [j for j in self.mem.jobs.values() if j["type"] == jtype and j["status"] == "running"]

    def retry(self, jid, **query):
        cookies = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}
        return client.post(f"/api/jobs/{jid}/retry", params=query, cookies=cookies)

    def migrate(self, **body):
        body.setdefault("target_uri", TARGET)
        cookies = {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}
        return client.post("/api/db-migrate", json=body, cookies=cookies)

    def wait_started(self, n=1, timeout=3):
        end = time.time() + timeout
        while time.time() < end and len(self.started) < n:
            time.sleep(0.01)
        return len(self.started) >= n

    def close(self):
        """Release every blocked worker and wait for its thread to finish, so no worker
        outlives this test and touches the real store after the patches are undone."""
        self.gate.set()
        end = time.time() + 5
        while time.time() < end and threading.active_count() > self._baseline_threads:
            time.sleep(0.01)


@pytest.fixture()
def live(monkeypatch):
    env = Live(monkeypatch)
    yield env
    env.close()


def _failed_migrate(live, **params):
    return live.add_job("migrate", "failed",
                        {"target_uri": TARGET, "overwrite": False, "override_busy": False, **params},
                        "Migrate data to a new database")


def _no_secrets(resp):
    assert PW not in resp.text and "target.example.test" not in resp.text


# ============================================================ the shared mechanism
def test_migrate_retry_handler_is_registered_with_the_registry():
    assert registry.JOB_RETRY_HANDLERS["migrate"] is settings_mod._retry_migration
    assert jobs_usage_mod.JOB_RETRY_HANDLERS is registry.JOB_RETRY_HANDLERS


def test_registry_refuses_a_second_migration_even_with_override(live):
    live.add_job("migrate", "running")
    for params in ({}, {"override_busy": True}):
        with pytest.raises(MigrationBlocked) as e:
            registry.launch_job("migrate", {"target_uri": TARGET, **params})
        assert "already in progress" in str(e.value)
    assert live.count("migrate") == 1


def test_registry_refuses_a_migration_while_busy_unless_overridden(live):
    live.add_job("generate", "running", label="Generate tests")
    with pytest.raises(MigrationBlocked, match="busy"):
        registry.launch_job("migrate", {"target_uri": TARGET})
    assert live.count("migrate") == 0
    jid = registry.launch_job("migrate", {"target_uri": TARGET, "override_busy": True})
    assert live.wait_started() and live.mem.jobs[jid]["type"] == "migrate"


def test_registry_refuses_a_migration_while_a_sync_is_running(live, monkeypatch):
    monkeypatch.setitem(SYNC, "running", True)
    with pytest.raises(MigrationBlocked, match="sync is currently running"):
        registry.launch_job("migrate", {"target_uri": TARGET})
    registry.launch_job("migrate", {"target_uri": TARGET, "override_busy": True})


def test_migration_blocked_is_a_migration_in_progress_so_one_handler_covers_it():
    assert issubclass(MigrationBlocked, MigrationInProgress)
    assert MigrationInProgress in main.app.exception_handlers


def test_before_start_runs_only_when_admitted_and_before_the_job_exists(live):
    seen = []
    registry.launch_job("generate", {}, before_start=lambda: seen.append(live.count("generate")))
    assert seen == [0]                                     # ran before the row was created
    live.add_job("migrate", "running")
    with pytest.raises(MigrationInProgress):
        registry.launch_job("generate", {}, before_start=lambda: seen.append("called"))
    assert seen == [0]                                     # never called for a refused launch


def test_a_failing_before_start_launches_nothing(live):
    def boom():
        raise RuntimeError("audit down")
    with pytest.raises(RuntimeError):
        registry.launch_job("migrate", {"target_uri": TARGET}, before_start=boom)
    assert live.count("migrate") == 0 and live.started == []


# ================================================================= concurrency
class SlowCheckJobs(Jobs):
    """Widens the gap between 'check for a running job' and 'create the row'."""

    def has_running_job(self, only_types=(), exclude_types=()):
        out = super().has_running_job(only_types, exclude_types)
        time.sleep(0.002)
        return out


def _race(monkeypatch, launchers, rounds=25):
    results = []
    for _ in range(rounds):
        mem = SlowCheckJobs()
        for name in ("create_job", "update_job", "get_job", "has_running_job",
                     "get_settings", "set_job_usage"):
            monkeypatch.setattr(main.store, name, getattr(mem, name))
        barrier = threading.Barrier(len(launchers))
        outcome = [None] * len(launchers)

        def run(i, fn):
            barrier.wait()
            try:
                fn()
                outcome[i] = "admitted"
            except MigrationInProgress:
                outcome[i] = "refused"
        threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(launchers)]
        [t.start() for t in threads]
        [t.join(10) for t in threads]
        results.append(outcome)
    return results


def test_concurrent_migration_launches_admit_exactly_one(live, monkeypatch):
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", lambda jid, p: live.gate.wait(10))
    launch = lambda: registry.launch_job("migrate", {"target_uri": TARGET})  # noqa: E731
    for outcome in _race(monkeypatch, [launch] * 8, rounds=10):
        assert outcome.count("admitted") == 1 and outcome.count("refused") == 7


def test_a_migration_and_another_job_are_never_both_admitted(live, monkeypatch):
    monkeypatch.setitem(registry.JOB_WORKERS, "migrate", lambda jid, p: live.gate.wait(10))
    monkeypatch.setitem(registry.JOB_WORKERS, "generate", lambda jid, p: live.gate.wait(10))
    mig = lambda: registry.launch_job("migrate", {"target_uri": TARGET})  # noqa: E731
    gen = lambda: registry.launch_job("generate", {})                       # noqa: E731
    for outcome in _race(monkeypatch, [mig, gen], rounds=40):
        # Whichever creates its row first wins; the other must see it and be refused.
        assert sorted(outcome) == ["admitted", "refused"], outcome
        live.gate.set()
        live.gate.clear()


# ======================================== retry: A-D (the reproduced vulnerabilities)
def test_A_retry_is_rejected_while_another_migration_is_running(live):
    failed = _failed_migrate(live)
    live.add_job("migrate", "running")
    r = live.retry(failed)
    assert r.status_code == 409 and "already in progress" in r.json()["detail"]
    assert live.count("migrate") == 2 and len(live.running("migrate")) == 1   # no second migration
    assert live.started == [] and live.probe_calls == []


def test_A2_the_overwrite_variant_cannot_clobber_a_running_migrations_target(live):
    failed = _failed_migrate(live, overwrite=True)
    live.add_job("migrate", "running")
    assert live.retry(failed).status_code == 409
    assert live.started == [] and live.target_checks == [] and live.probe_calls == []


def test_B_retry_is_rejected_while_another_job_is_running(live):
    failed = _failed_migrate(live)
    live.add_job("generate", "running", label="Generate tests")
    normal = live.migrate()                                    # the normal route says no...
    r = live.retry(failed)                                     # ...and so must retry
    assert normal.status_code == r.status_code == 409
    assert "busy" in r.json()["detail"] and "Generate tests" in r.json()["detail"]
    assert live.count("migrate") == 1 and live.started == []


def test_B2_retry_is_rejected_while_a_sync_is_running(live, monkeypatch):
    failed = _failed_migrate(live)
    monkeypatch.setitem(SYNC, "running", True)
    r = live.retry(failed)
    assert r.status_code == 409 and "sync is currently running" in r.json()["detail"]
    assert live.started == []


def test_C_retry_with_override_proceeds_past_unrelated_work_and_keeps_the_parameters(live):
    failed = _failed_migrate(live, overwrite=True)
    live.add_job("generate", "running", label="Generate tests")
    r = live.retry(failed, override_busy="true")
    assert r.status_code == 200
    new = live.mem.jobs[r.json()["job_id"]]
    assert new["type"] == "migrate" and new["label"].endswith("(retry)")
    assert new["params"] == {"target_uri": TARGET, "overwrite": True, "override_busy": True}
    assert live.wait_started() and live.started == [r.json()["job_id"]]
    assert live.probe_calls == [(TARGET, 768)]                 # re-validated, at the store dim
    assert "db.migrate.started" in live.audit                  # and audited like a normal start
    assert live.target_checks == []                            # overwrite=True: no target guard


def test_D_retry_with_override_is_still_rejected_while_a_migration_is_running(live):
    failed = _failed_migrate(live)
    live.add_job("migrate", "running")
    live.add_job("generate", "running")
    r = live.retry(failed, override_busy="true")
    assert r.status_code == 409 and "already in progress" in r.json()["detail"]
    assert len(live.running("migrate")) == 1 and live.started == []


def test_retry_of_the_running_migration_itself_is_rejected(live):
    running = live.add_job("migrate", "running", {"target_uri": TARGET, "overwrite": False})
    r = live.retry(running, override_busy="true")
    assert r.status_code == 409 and len(live.running("migrate")) == 1 and live.started == []


def test_retry_never_inherits_an_earlier_override(live):
    failed = _failed_migrate(live, override_busy=True)         # the original run had accepted it
    live.add_job("generate", "running")
    r = live.retry(failed)                                     # this attempt did not
    assert r.status_code == 409 and live.started == []


def test_retry_does_not_leave_the_system_blocked_afterwards(live):
    failed = _failed_migrate(live)
    r = live.retry(failed)
    assert r.status_code == 200
    live.gate.set()
    assert _wait(lambda: live.mem.jobs[r.json()["job_id"]]["status"] == "succeeded")
    registry.launch_job("generate", {})                        # accepted again


def _wait(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


# ============== retry: E (other job types unchanged)
def test_E_retrying_a_non_migration_job_is_unchanged(live):
    failed = live.add_job("generate", "failed", {"feature_id": "f1", "text": "x"}, "Generate tests")
    r = live.retry(failed)
    assert r.status_code == 200
    new = live.mem.jobs[r.json()["job_id"]]
    assert new["type"] == "generate" and new["label"] == "Generate tests (retry)"
    assert new["params"] == {"feature_id": "f1", "text": "x"}
    assert live.probe_calls == [] and live.target_checks == []   # no migration machinery involved


def test_E2_unknown_job_types_still_cannot_be_retried(live):
    jid = live.add_job("no_such_type", "failed")
    r = live.retry(jid)
    assert r.status_code == 400 and "cannot be retried" in r.json()["detail"]


def test_E3_ordinary_retry_is_still_refused_while_a_migration_runs(live):
    failed = live.add_job("generate", "failed", {"feature_id": "f1"})
    live.add_job("migrate", "running")
    r = live.retry(failed)
    assert r.status_code == 409 and "migration is in progress" in r.json()["detail"]


def test_E4_override_query_has_no_effect_on_other_job_types(live):
    failed = live.add_job("generate", "failed", {"feature_id": "f1"})
    assert live.retry(failed, override_busy="true").status_code == 200


# ============== retry: F (probe / target protections cannot be bypassed)
def test_F_retry_runs_the_capability_probe_and_refuses_an_unreachable_target(live):
    live.probe = _probe_ok(reachable=False, search_ok=False, status="unreachable",
                           detail="connection refused")
    r = live.retry(_failed_migrate(live))
    assert r.status_code == 400 and "connection refused" in r.json()["detail"]
    assert "Nothing copied" in r.json()["detail"]
    assert len(live.probe_calls) == 1 and live.started == [] and live.count("migrate") == 1


def test_F2_retry_refuses_a_target_without_vector_search(live):
    live.probe = _probe_ok(search_ok=False, status="no_search", detail="No vector search here.")
    r = live.retry(_failed_migrate(live))
    assert r.status_code == 400 and "No vector search here." in r.json()["detail"]
    assert live.started == []


def test_F3_retry_keeps_the_non_empty_target_guard_and_explains_how_to_replace(live):
    live.target_has_data = True
    r = live.retry(_failed_migrate(live, overwrite=False))
    assert r.status_code == 409
    assert "already contains data" in r.json()["detail"]
    assert "Configuration > Database" in r.json()["detail"]    # retry cannot choose to replace
    assert live.target_checks == [TARGET] and live.started == [] and live.count("migrate") == 1


def test_F4_retry_with_saved_overwrite_may_replace_but_only_after_every_other_check(live):
    live.target_has_data = True
    failed = _failed_migrate(live, overwrite=True)
    live.add_job("generate", "running")
    assert live.retry(failed).status_code == 409               # still busy -> still refused
    assert live.probe_calls == []                               # refused before probing
    live.mem.jobs[[k for k, j in live.mem.jobs.items() if j["type"] == "generate"][0]]["status"] = "succeeded"
    r = live.retry(failed)
    assert r.status_code == 200 and live.probe_calls                # idle now: probe ran, copy starts
    assert live.target_checks == []                              # explicit overwrite: no guard


def test_F5_retry_with_unusable_saved_params_is_a_400(live):
    for params in ({"target_uri": ""}, {"target_uri": "http://not-mongo/"}):
        jid = live.add_job("migrate", "failed", params)
        r = live.retry(jid)
        assert r.status_code == 400 and live.started == []
    assert live.probe_calls == []


# ============== retry: G (responses do not expose secrets) and access control
def test_G_rejected_retries_do_not_expose_the_target_uri_or_credentials(live):
    failed = _failed_migrate(live)
    live.add_job("migrate", "running")
    _no_secrets(live.retry(failed))                                     # already in progress
    live.mem.jobs[[k for k, j in live.mem.jobs.items() if j["type"] == "migrate" and j["status"] == "running"][0]]["status"] = "succeeded"
    live.add_job("generate", "running")
    _no_secrets(live.retry(failed))                                     # busy
    live.mem.jobs[[k for k, j in live.mem.jobs.items() if j["type"] == "generate"][0]]["status"] = "succeeded"
    live.probe = _probe_ok(reachable=False, search_ok=False, status="unreachable", detail="refused")
    _no_secrets(live.retry(failed))                                     # probe failure
    live.probe = _probe_ok()
    live.target_has_data = True
    _no_secrets(live.retry(failed))                                     # non-empty target
    ok = _failed_migrate(live, overwrite=True)
    live.target_has_data = False
    live.gate.set()
    _no_secrets(live.retry(ok))                                         # and a success body


def test_a_non_admin_cannot_retry_a_migration(monkeypatch):
    env = Live(monkeypatch, role="editor")
    try:
        r = env.retry(_failed_migrate(env))
        assert r.status_code == 403 and "admin" in r.json()["detail"]
        _no_secrets(r)
        assert env.started == [] and env.probe_calls == [] and env.count("migrate") == 1
    finally:
        env.close()


# ============== the normal route still works, through the same shared mechanism
def test_the_normal_route_still_starts_an_idle_migration(live):
    r = live.migrate()
    assert r.status_code == 200
    job = live.mem.jobs[r.json()["job_id"]]
    assert job["type"] == "migrate"
    assert job["params"] == {"target_uri": TARGET, "overwrite": False, "override_busy": False}
    assert live.wait_started() and live.probe_calls == [(TARGET, 768)]
    assert live.audit == ["db.migrate.started"]


def test_the_normal_route_and_retry_cannot_both_start_a_migration(live):
    failed = _failed_migrate(live)
    first = live.migrate()
    assert first.status_code == 200
    assert live.wait_started()
    second = live.retry(failed)
    third = live.migrate(overwrite=True, override_busy=True)
    assert second.status_code == third.status_code == 409
    assert len(live.running("migrate")) == 1


def test_a_migration_refused_at_admission_writes_no_audit_entry(live):
    live.add_job("migrate", "running")
    live.migrate()
    assert live.audit == []
