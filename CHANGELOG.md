# Changelog

## Unreleased

### Added
- **README "Option B" rewritten as an explicit numbered walkthrough.** Previously the
  install-script command and the rationale were interleaved as prose; now it's a
  literal Step 1–5 sequence (pull → one-time `install.sh` setup → set `MONGO_URI` →
  start → watch logs and sign in), plus a separate "day to day" block (`up -d` /
  `down` / `pull`) making clear Steps 1–3 are one-time only. The `--bundled` zero-cloud
  variant and the fully-manual fallback (now shown as exactly what `install.sh` does,
  for transparency) are both kept, just reorganized under the same step numbering.
  No code changes — README only.
- **`install.sh` / `install.ps1` — one-command installer for the pre-built image.**
  The previous "no source needed" flow required 3-5 manual `curl`/`cp` steps, which
  felt heavy for what's supposed to be the easy path. Added `install.sh` (bash) and
  `install.ps1` (PowerShell) at the repo root: `curl ... | bash` downloads
  `docker-compose.app.yml` + `.env.example`, creates `.env`, sets `APP_IMAGE`, and
  prints the one remaining manual step (`MONGO_URI`, since this flow brings your own
  database). A `--bundled` / `-Bundled` flag also grabs the demo stack's compose
  files + `config/` folder and starts it immediately, for a true zero-cloud-accounts
  trial. Verified both modes end-to-end against the real repo files (network calls
  stubbed to local copies since the script isn't published yet) — correct file sets,
  `.env` created with `APP_IMAGE` set exactly once (no duplicate lines on re-run
  logic), and `config/pwfile`/`setup-replica-set.sh`/`mongot-entrypoint.sh`
  permissions matching what `run.sh` already sets. README's "Option B" now leads with
  the one-liner, with the previous manual steps kept in a collapsible `<details>` for
  anyone who wants to see exactly what it does before piping to `bash`.
- **README repositioned around cloud deployment, not the bundled local stack.**
  Previous wording led with the bundled 3-node MongoDB + local Ollama setup as if it
  were the default, with the cloud/lightweight path mentioned as an aside — several
  rounds of review feedback flagged this as misleading, since MongoDB/the LLM are
  upstream dependencies wardenIQ connects to, not part of the product, and aren't
  expected to run locally for real use. Reworked: the top pitch, the Requirements
  table (cloud row now first and labeled "recommended", bundled row now explicitly
  "optional"), and section order (moved "Cloud / lightweight deployment" up to
  directly follow Requirements, ahead of "Quick start", which is now titled "local
  trial / all-in-one demo" to make clear it's a trial convenience, not the
  recommended shape). Added a similar framing note to "High availability &
  production". No functional/code changes — README only.
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
