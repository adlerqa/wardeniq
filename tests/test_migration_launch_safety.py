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
import os
import threading
import time
import uuid
from contextlib import nullcontext

import auth
import main
import pytest
from api.routes import jobs_usage as jobs_usage_mod
from api.routes import settings as settings_mod
from core.exceptions import MigrationBlocked, MigrationInProgress
from core.state import SYNC
from fastapi.testclient import TestClient
from store.base import SELF_TARGET_MSG
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
        self.same_database = False          # is the target the database the app is using?
        self.same_check_error = None
        self.same_checks = []
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
        monkeypatch.setattr(main.store, "target_is_this_database", self._target_is_this_database)
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

    def _target_is_this_database(self, uri):
        self.same_checks.append(uri)
        if self.same_check_error:
            raise self.same_check_error
        return self.same_database

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


def test_C_retry_with_override_proceeds_past_unrelated_work_and_keeps_only_the_target(live):
    failed = _failed_migrate(live, overwrite=True)             # the original attempt had replace=on
    live.add_job("generate", "running", label="Generate tests")
    r = live.retry(failed, override_busy="true")
    assert r.status_code == 200
    new = live.mem.jobs[r.json()["job_id"]]
    assert new["type"] == "migrate" and new["label"].endswith("(retry)")
    # The target is kept; the saved `overwrite` is NOT re-applied; override is this attempt's.
    assert new["params"] == {"target_uri": TARGET, "overwrite": False, "override_busy": True}
    assert live.wait_started() and live.started == [r.json()["job_id"]]
    assert live.probe_calls == [(TARGET, 768)]                 # re-validated, at the store dim
    assert "db.migrate.started" in live.audit                  # and audited like a normal start
    assert live.same_checks == [TARGET] and live.target_checks == [TARGET]   # both guards ran


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


def test_F4_retry_never_reapplies_a_saved_overwrite_against_a_non_empty_target(live):
    """Regression: a saved overwrite=True used to let a retry skip the non-empty-target guard
    and replace whatever the target holds NOW (another application's data, or this very
    database). A retry must never re-apply that destructive choice."""
    live.target_has_data = True                                # a foreign, non-empty target
    failed = _failed_migrate(live, overwrite=True)
    r = live.retry(failed)
    assert r.status_code == 409 and "already contains data" in r.json()["detail"]
    assert "never replaces" in r.json()["detail"]
    assert live.target_checks == [TARGET]                      # the guard DID run
    assert live.started == [] and live.count("migrate") == 1   # no migration, no new job
    _no_secrets(r)


def test_F4b_an_overwrite_query_parameter_on_retry_has_no_effect(live):
    live.target_has_data = True
    failed = _failed_migrate(live, overwrite=True)
    for q in ({"overwrite": "true"}, {"overwrite": "true", "override_busy": "true"}):
        r = live.retry(failed, **q)
        assert r.status_code == 409 and live.started == []
    assert live.count("migrate") == 1


def test_F4c_retry_still_works_for_a_legitimate_empty_target_and_runs_with_overwrite_off(live):
    live.target_has_data = False
    failed = _failed_migrate(live, overwrite=True)
    r = live.retry(failed)
    assert r.status_code == 200
    job = live.mem.jobs[r.json()["job_id"]]
    assert job["params"]["overwrite"] is False                 # never inherited
    assert live.wait_started()


def test_F4d_retry_with_saved_overwrite_false_against_a_non_empty_target_is_refused(live):
    live.target_has_data = True
    r = live.retry(_failed_migrate(live, overwrite=False))
    assert r.status_code == 409 and live.started == [] and live.target_checks == [TARGET]


def test_F4e_other_refusals_still_come_first_for_a_saved_overwrite(live):
    live.target_has_data = True
    failed = _failed_migrate(live, overwrite=True)
    live.add_job("generate", "running")
    assert live.retry(failed).status_code == 409               # busy
    assert live.probe_calls == [] and live.same_checks == [] and live.target_checks == []


def test_F5_retry_with_unusable_saved_params_is_a_400(live):
    for params in ({"target_uri": ""}, {"target_uri": "http://not-mongo/"}):
        jid = live.add_job("migrate", "failed", params)
        r = live.retry(jid)
        assert r.status_code == 400 and live.started == []
    assert live.probe_calls == []


def test_E5_retry_of_a_migration_fails_closed_if_its_handler_is_not_registered(live, monkeypatch):
    """The invariant "a retry never re-applies a saved overwrite" must not depend on the
    handler registry having been populated: without a handler, the generic retry path would
    re-launch the SAVED params (overwrite=True included) with no preflight at all."""
    monkeypatch.delitem(registry.JOB_RETRY_HANDLERS, "migrate")
    failed = _failed_migrate(live, overwrite=True)
    r = live.retry(failed)
    assert r.status_code == 400 and "cannot be retried" in r.json()["detail"]
    assert live.started == [] and live.count("migrate") == 1
    assert live.probe_calls == [] and live.target_checks == []
    _no_secrets(r)


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


# ============== the target must never be the database the app is using
@pytest.mark.parametrize("overwrite", [False, True])
def test_S1_normal_route_refuses_the_database_the_app_is_using(live, overwrite):
    live.same_database = True
    r = live.migrate(overwrite=overwrite)
    assert r.status_code == 400 and r.json()["detail"] == SELF_TARGET_MSG
    assert live.started == [] and live.count("migrate") == 0     # no job at all
    assert live.audit == []                                       # nothing started, nothing audited
    assert live.target_checks == []                               # refused before the data guard
    _no_secrets(r)


@pytest.mark.parametrize("saved_overwrite", [True, False])
def test_S2_retry_refuses_the_database_the_app_is_using(live, saved_overwrite):
    """The reproduced data loss: after a switch, the live database contains the copied
    migrate job whose target is that same database; retrying it must be impossible."""
    live.same_database = True
    failed = _failed_migrate(live, overwrite=saved_overwrite)
    r = live.retry(failed)
    assert r.status_code == 400 and r.json()["detail"] == SELF_TARGET_MSG
    assert live.started == [] and live.count("migrate") == 1
    _no_secrets(r)


def test_S3_self_target_refused_even_with_override_busy(live):
    live.same_database = True
    live.add_job("generate", "running")
    failed = _failed_migrate(live, overwrite=True)
    assert live.retry(failed, override_busy="true").status_code == 400
    assert live.migrate(overwrite=True, override_busy=True).status_code == 400
    assert live.started == []


def test_S4_failing_to_tell_whether_the_target_is_this_database_fails_closed(live):
    live.same_check_error = RuntimeError("cannot write the scratch collection")
    for resp in (live.migrate(), live.retry(_failed_migrate(live))):
        assert resp.status_code == 400 and "Couldn't confirm" in resp.json()["detail"]
        _no_secrets(resp)
    assert live.started == [] and live.target_checks == []        # never got as far as copying


def test_S5_busy_is_still_reported_before_the_self_target_check(live):
    live.same_database = True
    live.add_job("generate", "running")
    assert live.migrate().status_code == 409
    assert live.same_checks == []


def test_S6_a_different_empty_target_still_migrates(live):
    live.same_database = False
    live.target_has_data = False
    r = live.migrate()
    assert r.status_code == 200 and live.wait_started()
    assert live.same_checks == [TARGET] and live.target_checks == [TARGET]


# ============== the normal route: overwrite is an explicit, per-request confirmation
def test_N1_normal_route_refuses_a_non_empty_target_without_overwrite(live):
    live.target_has_data = True
    r = live.migrate()
    assert r.status_code == 409 and "already contains data" in r.json()["detail"]
    assert live.started == []


def test_N2_normal_route_with_explicit_overwrite_replaces_a_non_empty_foreign_target(live):
    live.target_has_data = True                                # someone else's data, a different database
    r = live.migrate(overwrite=True)
    assert r.status_code == 200                                # the user's explicit confirmation
    assert live.mem.jobs[r.json()["job_id"]]["params"]["overwrite"] is True
    assert live.target_checks == []                            # (the guard exists to demand that choice)
    assert live.same_checks == [TARGET]                        # but never for this very database


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


# ===================================================================================
# REAL servers: the whole path (route / retry endpoint -> registry -> job thread ->
# worker -> migrate_to -> verification) against real MongoDB, with throwaway databases.
#   MONGO_TEST_URI    the "live" database the app is using (source)
#   MONGO_TEST_URI_2  a second, separate MongoDB used as a foreign target
# Only the capability probe (not under test here) and the .env writer are stubbed.
# ===================================================================================
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


class RealHttp:
    def __init__(self, monkeypatch):
        from core import audit as audit_mod
        from core import security as security_mod
        from pymongo import MongoClient
        from store import Store
        from workers import generation as gen_mod
        self.name = f"wardeniq_http_{uuid.uuid4().hex[:10]}"
        self.src = Store(MONGO_TEST_URI, self.name, dim=8)
        self.src.get_settings = lambda: {}
        self.src.get_user = lambda uid: {"id": "u1", "email": "a@b.c", "role": "admin",
                                         "active": True, "session_version": 0, "all_projects": True}
        self.foreign = MongoClient(MONGO_TEST_URI_2) if _reachable(MONGO_TEST_URI_2) else None
        self.env_writes = []
        self._baseline_threads = threading.active_count()
        for mod in (settings_mod, registry, security_mod, audit_mod, gen_mod):
            monkeypatch.setattr(mod, "store", self.src)
        monkeypatch.setattr(settings_mod, "_env_file_writable", lambda: True)
        monkeypatch.setattr(settings_mod, "_probe_mongo", lambda uri, dim=None: _probe_ok())
        monkeypatch.setattr(gen_mod, "_write_env_var",
                            lambda path, k, v: self.env_writes.append((k, v)) or (True, None))
        monkeypatch.setattr(registry, "heartbeat", lambda jid, *a, **k: nullcontext())
        monkeypatch.setitem(SYNC, "running", False)

    # --- seeding / inspection
    def seed_live(self, overwrite):
        self.src.db["projects"].insert_many([{"name": f"live-{i}"} for i in range(5)])
        self.src.db["features"].insert_many([{"title": f"f{i}"} for i in range(7)])
        # what a switch leaves behind: the copied migrate job, whose target is THIS database
        jid = self.src.create_job("migrate", {"target_uri": MONGO_TEST_URI, "overwrite": overwrite},
                                  "Migrate data to a new database")
        self.src.update_job(jid, status="failed", error="interrupted by application restart")
        return jid

    def failed_job(self, target_uri, overwrite):
        jid = self.src.create_job("migrate", {"target_uri": target_uri, "overwrite": overwrite},
                                  "Migrate data to a new database")
        self.src.update_job(jid, status="failed", error="earlier attempt")
        return jid

    def live_counts(self):
        return (self.src.db["projects"].count_documents({}), self.src.db["features"].count_documents({}))

    def foreign_db(self):
        return self.foreign[self.name]

    def wait(self, jid, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            j = self.src.get_job(jid)
            if j is None or j["status"] != "running":
                return j
            time.sleep(0.05)
        raise AssertionError("job did not finish")

    def retry(self, jid, **q):
        return client.post(f"/api/jobs/{jid}/retry", params=q,
                           cookies={auth.SESSION_COOKIE: auth.sign_session("u1", 0)})

    def migrate(self, target, **body):
        return client.post("/api/db-migrate", json={"target_uri": target, **body},
                           cookies={auth.SESSION_COOKIE: auth.sign_session("u1", 0)})

    def close(self):
        end = time.time() + 10
        while time.time() < end and threading.active_count() > self._baseline_threads:
            time.sleep(0.02)
        self.src.client.drop_database(self.name)
        self.src.client.close()
        if self.foreign is not None:
            self.foreign.drop_database(self.name)
            self.foreign.close()


@pytest.fixture()
def real(monkeypatch):
    if not _reachable(MONGO_TEST_URI):
        pytest.skip(f"no MongoDB reachable at MONGO_TEST_URI={MONGO_TEST_URI!r}")
    env = RealHttp(monkeypatch)
    yield env
    env.close()


@pytest.fixture()
def real_pair(real):
    if real.foreign is None:
        pytest.skip("set MONGO_TEST_URI_2 to a second, separate MongoDB to run this")
    return real


@pytest.mark.dbintegration
@pytest.mark.parametrize("saved_overwrite", [True, False])
def test_real_retry_of_the_copied_job_cannot_migrate_the_database_onto_itself(real, saved_overwrite):
    """The reproduced data loss, end to end (real route, retry, jobs, worker): 5 projects /
    7 features became 0 / 0, the job row vanished and verification passed."""
    jid = real.seed_live(saved_overwrite)
    before_jobs = real.src.db["jobs"].count_documents({})
    r = real.retry(jid)
    assert r.status_code == 400 and r.json()["detail"] == SELF_TARGET_MSG
    assert real.live_counts() == (5, 7)                          # the live data is untouched
    assert real.src.db["jobs"].count_documents({}) == before_jobs and real.src.get_job(jid)
    assert real.env_writes == []
    assert not [n for n in real.src.db.list_collection_names() if n.startswith("wardeniq_selfcheck_")]


@pytest.mark.dbintegration
@pytest.mark.parametrize("target", ["same", "alias"])
def test_real_normal_route_cannot_migrate_the_database_onto_itself(real, target):
    real.seed_live(True)
    uri = MONGO_TEST_URI if target == "same" else MONGO_TEST_URI.replace("localhost", "127.0.0.1")
    r = real.migrate(uri, overwrite=True)                        # even with an explicit "replace"
    assert r.status_code == 400 and r.json()["detail"] == SELF_TARGET_MSG
    assert real.live_counts() == (5, 7) and real.env_writes == []


@pytest.mark.dbintegration
def test_real_retry_with_saved_overwrite_cannot_replace_a_non_empty_foreign_target(real_pair):
    real_pair.seed_live(False)
    real_pair.foreign_db()["projects"].insert_many([{"name": f"SOMEONE-ELSES-{i}"} for i in range(3)])
    failed = real_pair.failed_job(MONGO_TEST_URI_2, overwrite=True)    # saved with replace=on
    r = real_pair.retry(failed)
    assert r.status_code == 409 and "already contains data" in r.json()["detail"]
    assert real_pair.foreign_db()["projects"].count_documents({"name": {"$regex": "^SOMEONE"}}) == 3
    assert real_pair.env_writes == []
    assert real_pair.live_counts() == (5, 7)


@pytest.mark.dbintegration
def test_real_retry_with_saved_overwrite_false_against_a_non_empty_target_is_refused(real_pair):
    real_pair.seed_live(False)
    real_pair.foreign_db()["projects"].insert_one({"name": "SOMEONE-ELSES"})
    r = real_pair.retry(real_pair.failed_job(MONGO_TEST_URI_2, overwrite=False))
    assert r.status_code == 409 and real_pair.foreign_db()["projects"].count_documents({}) == 1


@pytest.mark.dbintegration
def test_real_normal_route_without_overwrite_refuses_a_non_empty_target(real_pair):
    real_pair.seed_live(False)
    real_pair.foreign_db()["projects"].insert_one({"name": "SOMEONE-ELSES"})
    r = real_pair.migrate(MONGO_TEST_URI_2)
    assert r.status_code == 409 and real_pair.foreign_db()["projects"].count_documents({}) == 1


@pytest.mark.dbintegration
def test_real_normal_route_with_explicit_overwrite_still_replaces_a_foreign_target(real_pair):
    """The designed, confirmed path keeps working: overwrite is the user's explicit choice
    for THIS request, and the target is a different database."""
    real_pair.seed_live(False)
    real_pair.foreign_db()["projects"].insert_many([{"name": f"OLD-{i}"} for i in range(3)])
    r = real_pair.migrate(MONGO_TEST_URI_2, overwrite=True)
    assert r.status_code == 200
    job = real_pair.wait(r.json()["job_id"])
    assert job["status"] == "succeeded" and job["result"]["verified"] and job["result"]["switched"]
    assert real_pair.foreign_db()["projects"].count_documents({"name": {"$regex": "^live-"}}) == 5
    assert real_pair.foreign_db()["projects"].count_documents({"name": {"$regex": "^OLD-"}}) == 0
    assert real_pair.env_writes == [("MONGO_URI", MONGO_TEST_URI_2)]


@pytest.mark.dbintegration
def test_real_migration_to_a_legitimate_empty_target_succeeds_and_verifies(real_pair):
    real_pair.seed_live(False)
    r = real_pair.migrate(MONGO_TEST_URI_2)
    assert r.status_code == 200
    job = real_pair.wait(r.json()["job_id"])
    res = job["result"]
    assert job["status"] == "succeeded" and res["verified"] is True and res["switched"] is True
    assert res["verification"]["ok"] is True and res["warnings"] == []
    assert real_pair.foreign_db()["projects"].count_documents({}) == 5
    assert real_pair.foreign_db()["features"].count_documents({}) == 7
    assert real_pair.live_counts() == (5, 7)                      # the source is untouched
    assert real_pair.env_writes == [("MONGO_URI", MONGO_TEST_URI_2)]


@pytest.mark.dbintegration
def test_real_retry_to_a_legitimate_empty_target_still_works_with_overwrite_off(real_pair):
    real_pair.seed_live(False)
    failed = real_pair.failed_job(MONGO_TEST_URI_2, overwrite=True)    # saved replace=on is ignored
    r = real_pair.retry(failed)
    assert r.status_code == 200
    job = real_pair.wait(r.json()["job_id"])
    assert job["status"] == "succeeded" and job["result"]["verified"] is True
    assert real_pair.src.get_job(r.json()["job_id"])["params"]["overwrite"] is False
    assert real_pair.foreign_db()["projects"].count_documents({}) == 5


@pytest.mark.dbintegration
def test_real_verification_still_fails_closed_after_the_safety_checks(real_pair, monkeypatch):
    real_pair.seed_live(False)
    real_copy = real_pair.src.migrate_to

    def copy_then_lose_one(target, **kw):
        out = real_copy(target, **kw)
        real_pair.foreign_db()["features"].delete_one({})
        return out
    monkeypatch.setattr(real_pair.src, "migrate_to", copy_then_lose_one)
    r = real_pair.migrate(MONGO_TEST_URI_2)
    assert r.status_code == 200
    job = real_pair.wait(r.json()["job_id"])
    assert job["status"] == "failed" and "NOT switched" in job["error"]
    assert job["result"]["switched"] is False and real_pair.env_writes == []

