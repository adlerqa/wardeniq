
import threading

import usage
from core.logging_setup import get_logger
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)
from workers.heartbeat import heartbeat

log = get_logger("jobs")

JOB_WORKERS = {}   # job type -> worker(jid, params)


def launch_job(jtype, params, label="", project_id=None, feature_id=None):
    """Create a persisted job and run its worker in a background thread."""
    jid = store.create_job(jtype, params, label, project_id, feature_id)

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
    jid = store.create_job(jtype, {}, label, project_id, feature_id)
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
