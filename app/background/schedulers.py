"""Periodic background schedulers: the stale-job sweeper and the imported-sheet
project-wide re-analysis sweep.

Moved out of main.py (Phase 4 of REFACTOR_PLAN.md). Both are started exactly
once per process by main.py's `@app.on_event("startup")` handler
(`threading.Thread(target=..., daemon=True).start()`) — this module only
defines the loop bodies, it does not start any threads itself.
"""
import time

from core.bootstrap import BOOT
from core.config import (
    STALE_JOB_SWEEP_INTERVAL_SECONDS, STALE_JOB_TTL_SECONDS,
)
from core.logging_setup import get_logger
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                               # mutated, never rebound)

from workers.registry import run_tracked
from workers.repo_scan_worker import _rescan_pool_for_feature

log = get_logger("schedulers")


def _stale_job_sweeper():
    """Periodically fail 'running' jobs whose worker thread died silently
    (OOM, C-level segfault, network deadlock) — startup recovery alone
    doesn't help when the process is still up. Keeps loaders from spinning
    forever on the client."""
    while True:
        try:
            time.sleep(max(15, STALE_JOB_SWEEP_INTERVAL_SECONDS))
            if not BOOT.get("ready"):
                continue
            store.sweep_stale_jobs(ttl_seconds=STALE_JOB_TTL_SECONDS)
        except Exception as e:  # noqa: BLE001
            log.error("[stale-sweeper] %s", e)


def _import_reanalysis_scheduler(interval_s: int = 300):
    """GAP2: every few minutes, take projects with imported-pool rows still awaiting
    project-wide analysis and re-scan them against every feature in the project,
    auto-promoting new matches. `_rescan_pool_for_feature` clears the pending flag as
    it goes, so each import batch is swept once."""
    while True:
        time.sleep(interval_s)
        try:
            pids = store.list_projects_with_pending_import_rows()
        except Exception as e:  # noqa: BLE001
            log.error("[import-scheduler] list failed: %s", e)
            continue
        for pid in pids:
            def _sweep(pid=pid):
                for feat in store.list_features(project_id=pid):
                    try:
                        _rescan_pool_for_feature(feat)
                    except Exception:  # noqa: BLE001
                        continue
            try:
                # Runs on this scheduler thread (no job recorder), and the rescan
                # embeds features/rows — wrap so any embedding cost is captured.
                run_tracked("import_reanalysis", _sweep,
                            label="Imported-library re-analysis", project_id=pid)
            except Exception as e:  # noqa: BLE001
                log.error("[import-scheduler] project %s: %s", pid, e)
