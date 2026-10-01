
import threading
from collections.abc import Callable

import usage
from core.exceptions import MIGRATION_IN_PROGRESS_MSG, MigrationBlocked, MigrationInProgress
from core.logging_setup import get_logger
from core.state import SYNC, store  # noqa: F401  (bare name-import is safe: store is
                                                  # mutated, never rebound)
from workers.heartbeat import heartbeat

log = get_logger("jobs")

JOB_WORKERS = {}   # job type -> worker(jid, params)

# Job types whose launch has preconditions beyond "a worker exists" register a retry
# handler here (job type -> handler(request, job, override_busy) -> new job id), so that
# POST /api/jobs/{id}/retry re-runs them through the SAME checks as their normal entry
# point instead of calling launch_job() directly. See api/routes/settings.py (migrate).
JOB_RETRY_HANDLERS: dict[str, Callable[..., str]] = {}

# Serialises "may this job start?" with "create its job row" for EVERY launch path. That
# is what makes the migration invariants race-free within a process: whichever of
# {a migration, any other job} creates its row first is seen by the other's check. The
# critical section is one find + one insert; nothing slow (probe, copy) runs under it.
# Process-local: the shipped container runs a single uvicorn process, and this does NOT
# make multi-process deployments safe.
_LAUNCH_LOCK = threading.Lock()


def migration_blocker(override_busy: bool = False) -> str | None:
    """Why a migration may not start right now, or None if it may (#111).

    migrate_to() streams the live source database with no isolation, so anything writing
    during the copy can yield a partial capture:
      * another migration already running -- never overridable;
      * a GitHub/GitLab sync (core.state.SYNC["running"]) or any other `jobs` row with
        status "running" -- refused unless `override_busy` (a best-effort snapshot)."""
    if store.has_running_job(only_types=("migrate",)):
        return "A database migration is already in progress. Wait for it to finish."
    if override_busy:
        return None
    if SYNC.get("running"):
        return ("A GitHub/GitLab sync is currently running. Wait for it to finish, or start "
                "anyway (best-effort snapshot, not guaranteed-consistent).")
    busy = store.has_running_job(exclude_types=("migrate",))
    if busy:
        what = busy.get("label") or busy.get("type") or "a job"
        return (f"wardenIQ is currently busy ({what}). Wait for it to finish, or start "
                "anyway (best-effort snapshot, not guaranteed-consistent).")
    return None


def _admit_and_create_job(jtype, params, label, project_id, feature_id, before_start=None):
    """The single place a job row is created for launch_job()/run_tracked(), so the
    migration rules hold no matter which route, retry or internal caller asked (#111):

      * a MIGRATION is admitted only if migration_blocker() is clear (another migration
        running is never overridable; `override_busy` in its params only waives the
        "something else is running" check);
      * every OTHER job is refused while a migration is running, because migrate_to()
        streams the live source with no isolation and a job inserting mid-copy would
        produce a partial capture.

    The "migration in progress" state is a `jobs` row of type "migrate" with status
    "running": cleared by the launch_job() wrapper when the worker succeeds OR raises,
    and by fail_orphaned_jobs() / sweep_stale_jobs() if the process died mid-copy, so a
    failed migration can never leave the app permanently blocked.

    `before_start` runs after admission and before the row exists (used to write the
    audit entry before the copy can begin); if it raises, nothing is launched."""
    with _LAUNCH_LOCK:
        if jtype == "migrate":
            blocker = migration_blocker(bool((params or {}).get("override_busy")))
            if blocker:
                raise MigrationBlocked(blocker)
        elif store.has_running_job(only_types=("migrate",)):
            raise MigrationInProgress(MIGRATION_IN_PROGRESS_MSG)
        if before_start:
            before_start()
        return store.create_job(jtype, params, label, project_id, feature_id)


def launch_job(jtype, params, label="", project_id=None, feature_id=None, before_start=None):
    """Create a persisted job and run its worker in a background thread."""
    jid = _admit_and_create_job(jtype, params, label, project_id, feature_id, before_start)

    def run():
        usage.start()   # record all LLM/embedding tokens spent by this job's thread
        try:
            # Wraps the ENTIRE worker call, not just the pieces that already call
            # update_job_progress() themselves — a worker's single long blocking
            # call (an LLM generation, an archive fetch) would otherwise leave
            # updated_at stale long enough to look "unresponsive" to the frontend's
            # stall detector or the backend's own stale-job sweep, even though it's
            # still working. See workers/heartbeat.py for the full rationale.
            with heartbeat(jid):
                JOB_WORKERS[jtype](jid, params)
            j = store.get_job(jid)
            if j and j.get("status") == "running":
                store.update_job(jid, status="succeeded", stage="done", progress=100)
        except Exception as e:  # noqa: BLE001
            store.update_job(jid, status="failed", stage="error", error=str(e))
        finally:
            try:
                prices = store.get_settings().get("llm_prices") or {}
                store.set_job_usage(jid, usage.summarize(usage.stop(), prices))
            except Exception as ue:  # noqa: BLE001
                log.warning("[usage] failed to record job %s: %s", jid, ue)

    threading.Thread(target=run, daemon=True).start()
    return jid


def run_tracked(jtype, fn, *, label="", project_id=None, feature_id=None):
    """Run ``fn()`` on the CURRENT thread inside a usage-recording context and
    persist a lightweight job record with the token/cost summary.

    Used for AI work that happens OUTSIDE ``launch_job`` — poller/webhook-driven
    PR coverage, manual PR-assign coverage, and test-plan generation — so their
    LLM/embedding spend still shows up in Usage & Cost. Must only be called from
    a bare background thread that has no active recorder; never from inside a
    ``launch_job`` worker (which already records) or recording would nest.
    """
    jid = _admit_and_create_job(jtype, {}, label, project_id, feature_id)
    result = None
    usage.start()
    try:
        # Same reasoning as launch_job's heartbeat wrap above: `fn()` here is
        # typically a single long LLM-judged coverage/impact call (PR coverage,
        # test-plan generation) with no internal progress ticks of its own.
        with heartbeat(jid):
            result = fn()
        j = store.get_job(jid)
        if j and j.get("status") == "running":
            store.update_job(jid, status="succeeded", stage="done", progress=100)
    except Exception as e:  # noqa: BLE001
        store.update_job(jid, status="failed", stage="error", error=str(e)[:300])
    finally:
        try:
            prices = store.get_settings().get("llm_prices") or {}
            store.set_job_usage(jid, usage.summarize(usage.stop(), prices))
        except Exception as ue:  # noqa: BLE001
            log.warning("[usage] failed to record tracked %s %s: %s", jtype, jid, ue)
    return result
