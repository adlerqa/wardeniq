# Changelog

## Unreleased

### Fixed
- Loaders in **Test Case Generation**, **Mind Map**, and **Step Library**
  no longer spin forever.
  - **Backend (`app/store.py`, `app/main.py`)**
    - Added a periodic *stale-job sweeper* (`store.sweep_stale_jobs`,
      wired into a 60s daemon thread from `main._stale_job_sweeper`) that
      fails any `status: "running"` job whose `updated_at` heartbeat is
      older than `STALE_JOB_TTL_SECONDS` (default 600s). Previous
      `fail_orphaned_jobs()` only ran at startup, so live-process hangs
      (Ollama socket stall, worker thread deadlock) left zombie
      "running" jobs that pinned the client loader indefinitely.
    - Rewrote `store.list_steps` to compute per-step usage counts in a
      single aggregation instead of `N` `count_documents` calls. The
      Step Library previously ran up to 1000 collection scans against
      unindexed `cases.step_ids`.
  - **Frontend (`frontend/src/legacy/legacyApp.js`)**
    - `loadMindmap()` now clears `#mm-map` on the no-project early
      return, so the loader from `#mm-analyze` doesn't outlive the job.
    - `watchJob()` gained a client-side stall detector: if `updated_at`
      stops advancing for 120s while the job is still `running`, the
      watcher delivers a synthetic `failed` tick so the loader is
      replaced with a retry-able error state.

### Schema
- New indexes (created by `store.ensure_indexes` on next boot; safe on
  existing installs):
  - `cases.step_ids` — backs the step-library usage count.
  - `jobs.status + jobs.updated_at` — supports the stale-job sweeper.
