# Changelog

## Unreleased

### Added
- **Zero-config `APP_SECRET` on first boot.** New `app/main.py::_ensure_app_secret()`,
  called at the top of `bootstrap()` (before the existing `_check_app_secret()` hard
  gate). If the effective secret is still unset/the shipped placeholder and no split
  `SESSION_SECRET`/`ENCRYPTION_KEY` is in progress, and `.env` is writable (the bind
  mount from `docker-compose.app.yml`), it generates a `secrets.token_urlsafe(32)`
  value, persists it via the existing `_write_env_var` upsert, sets it into
  `os.environ` for the current process, and logs once that it did so. If `.env` isn't
  writable, it does nothing and the existing `_check_app_secret()` fail-closed
  behavior is unchanged — this only removes a manual step, it never runs on a
  known/weak secret. README Quick start updated to reflect that `.env` no longer
  needs manual editing for a first local run (MongoDB/Ollama already had bundled
  fallbacks; `APP_SECRET` was the last manual requirement).
- **Published Docker image + CI publishing workflow.** Added
  `.github/workflows/docker-publish.yml`, which builds `app/Dockerfile` (repo-root
  context, so it also compiles `frontend/`) and pushes to Docker Hub as
  `adlerqa/wardeniq` — manual dispatch with any tag (defaults to `beta`), or a
  `vX.Y.Z` git tag for a version + `latest`. No app changes; `docker-compose.app.yml`
  already supported pulling via `APP_IMAGE` instead of building. README gained a
  "Prefer a pre-built image?" section documenting `docker pull adlerqa/wardeniq:beta`,
  the no-build/no-clone compose flow (curl just `docker-compose.app.yml` +
  `.env.example`), and a new "Cloud / lightweight deployment" section clarifying that
  MongoDB/the LLM don't need to run locally (cloud MongoDB Atlas M10+, or self-managed
  + mongot, plus any hosted LLM provider) — in which case only the app container runs
  (~2–4 GB RAM) instead of the full bundled demo stack (~8–10 GB). `Requirements`
  table updated to reflect both scenarios.

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
