# wardenIQ — Project Context Map

> Working reference built while surveying the repo. Purpose: capture every moving part
> before we simplify setup, make the installer interactive, and do functional +
> security fixes. Two audiences: us (planning changes) and future contributors.

---

## 1. What it is

wardenIQ is a **Test Intelligence Platform**: a FastAPI backend + React SPA that ingests
product docs (PRD/HLD/LLD) and GitHub repos, then uses an LLM + vector search (RAG) to
generate, version, and analyze test cases, coverage, automation %, impact analysis, mind
maps, and release cycles.

Only two directories are wardenIQ's own code — **`app/`** (backend, also builds & serves
the UI) and **`frontend/`** (React). Everything else (MongoDB, mongot, Ollama) is upstream
open source that wardenIQ orchestrates via Docker Compose.

---

## 2. The three core layers

The whole product is deliberately three swappable layers wired together only by config.
This is the mental model the compose files encode.

| Layer | Role | Bundled default | Bring-your-own | Compose file |
|---|---|---|---|---|
| **1. App** (required) | FastAPI + React SPA; generation, RAG, versioning, coverage, reports | build from `./app` or pull `APP_IMAGE` | — (always needed) | `docker-compose.app.yml` |
| **2. Database + Search** | MongoDB stores data; **mongot** provides vector/full-text search | 3-node MongoDB Community replica set (`rs0`) + mongot | any MongoDB w/ Vector Search (Atlas M10+, or self-managed + mongot) via `MONGO_URI` | `docker-compose.mongodb.yml` |
| **3. AI (LLM + embeddings)** | Generation model + embedding model | Ollama container, pre-pulls `qwen2.5:3b` (gen) + `nomic-embed-text` (embed, 768-dim) | hosted provider (OpenAI/Anthropic/Gemini/Mistral/Groq/Bedrock/Voyage/OpenAI-compatible), configured in-app, or host Ollama via `OLLAMA_URL` | `docker-compose.ollama.yml` |

`docker-compose.yml` is just an `include:` of all three (needs Compose v2.20+).

**Wiring between layers is purely config**, which is what makes them swappable:
- `MONGO_URI` — points the app at layer 2. Blank ⇒ bundled replica set
  (`mongodb://mongod1.warden-net:27017,mongod2...,mongod3.../?replicaSet=rs0`).
- `OLLAMA_URL` — points the app at layer 3. Blank ⇒ `OLLAMA_URL_BUNDLED` fallback
  (bundled `http://ollama:11434`, or `http://host.docker.internal:11434` for app-only).
- An explicit value in `.env` **wins and locks the field in the UI**; left unset, the
  value is editable in-app and written back into `.env`.

```
                 ┌──────────── wardenIQ (this repo) ────────────┐
   PRD/HLD/LLD ─►│  FastAPI app + React UI  (./app + ./frontend) │
   GitHub repos ►│  generation · RAG · versioning · coverage     │
                 └───────┬──────────────┬───────────────┬────────┘
                         ▼              ▼               ▼
              Ollama (LLM+embed)   mongot (search)   MongoDB replica set (x3)
```

---

## 3. Repo layout (annotated)

**Updated post-refactor (REFACTOR_PLAN.md, Phases 1–6, 2026-08).** `app/main.py` was a
7,316-line monolith (165 route handlers + 43 Pydantic models interleaved) and `store.py`
was a 3,889-line, 257-member `Store` class. Both are now decomposed into packages — same
behavior, same API surface (OpenAPI spec is byte-identical pre/post-refactor; the `Store`
class still exposes the exact same 257 members), just organized. **New invariants: no DB
access outside `store/`; no route handlers in `main.py`.**

```
app/                    FastAPI backend + Dockerfile (also builds UI)
  main.py       (201)   App assembly ONLY: FastAPI(), middleware registration, the 20
                        api/routes/ router includes (static_spa.py LAST — see its
                        docstring for a FastAPI include_router()/Mount gotcha), startup-
                        thread wiring. No route handlers, no direct DB access, no
                        business logic — down from 7,316 lines pre-refactor.
  core/                  cross-cutting singletons + helpers (no route handlers)
    config.py     (114) env-derived constants (MONGO_URI, EMBED_MODEL, thresholds…)
    state.py       (53) singletons: `store`, `SYNC` dict, embedder placeholder
    security.py   (435) auth_gateway + security_headers + ~26 RBAC helpers, the
                        principal-resolver registry
    deps.py       (609) current_llm/current_embedder, git clients, repo/document helpers
    exceptions.py  (18) `_InvalidId` handler
    audit.py       (29) `_audit(...)`
    bootstrap.py  (242) bootstrap(), secret checks, production-posture gate, admin seed
  workers/               background job registry + one file per job type
    registry.py    (68) launch_job(), run_tracked(), job-type → worker map
    generation.py (222) test-case generation, corpus ingestion, embed-switch, DB migration
    validator_worker.py (33), code_coverage_worker.py (363),
    codeanalysis_worker.py (433), repo_scan_worker.py (722), test_import_worker.py (214)
  background/            poller.py (96) GitHub/GitLab sync poller + webhook signature
                        verification; schedulers.py (62) stale-job sweeper + imported-
                        sheet re-analysis scheduler
  api/
    schemas.py     (21) Pydantic models shared by 2+ routers (avoids router-to-router
                        imports, which would create cycles)
    routes/               20 files, one `app.include_router(...)` per file in main.py.
                        Handler bodies are unchanged aside from the `@app.` -> `@router.`
                        decorator swap. Extraction order followed dependency depth
                        (security-sensitive auth/users first; static_spa.py always LAST):
      documents.py (110) test_cycles.py (210) reports_exports.py (114) auth.py (468)
      users.py (245) settings.py (577) jira_atlassian.py (187) repos_prs.py (334)
      steps_test_cases.py (187) validator.py (117) test_plan.py (110)
      test_import.py (401) projects.py (140) features.py (399) jobs_usage.py (149)
      code_coverage.py (538) develop.py (42) webhooks.py (130) system.py (87)
      static_spa.py (61) — LAST; owns the `/assets` StaticFiles mount + SPA fallback
                        routes (`/`, `/favicon.ico`, `/invite`)
  store/                 MongoDB data layer, composed from mixins behind one `Store` class
    __init__.py    (70) `class Store(...)` composes every mixin; `store = Store(...)`
                        (core/state.py) remains the single module-level singleton —
                        `from store import Store` still works, every existing
                        `store.get_feature(...)`-style call site is unchanged
    base.py       (423) Mongo client/db handle, index setup, shared helpers
    projects.py (139) features.py (505) steps_test_cases.py (876) jobs.py (177)
    users_auth.py (212) repos_prs.py (205) code_coverage.py (293) validator_runs.py (135)
    test_plan_runs.py (76) test_cycles.py (350) documents.py (62) settings.py (44)
    usage.py (122) sheet_import.py (514) audit.py (53) dashboard.py (121)
  sheet_import.py(1374) XLSX import feature (top-level module — distinct on purpose from
                        the same-named `store/sheet_import.py` mixin; Python's absolute
                        imports make `import sheet_import` vs. relative `from . import
                        sheet_import` unambiguous, see store/__init__.py's docstring)
  test_plan.py  (915)   test-plan generation
  validator.py  (732)   validator run (Q&A) logic
  report.py     (702)   report/export (reportlab PDF, docx)
  grounding.py  (625)   evidence-backed code grounding (tree-sitter, BM25)
  automation.py (507)   automation coverage
  coverage.py   (435)   coverage computation — still one file across 7 concerns; an
                        optional future split into `coverage/` is scoped in
                        REFACTOR_PLAN.md Phase 9 but not required
  extract.py    (290)   PRD/HLD/LLD extraction (pypdf, python-docx)
  email_send.py (276)   SMTP + OTP email
  llm.py        (218)   LLM provider abstraction (Ollama/OpenAI/Anthropic/Gemini/Bedrock…)
  auth.py       (192)   sessions (HMAC), OTP, invite tokens, local password (PBKDF2)
  embeddings.py (181)   embedding provider abstraction
  github.py/gitlab.py/jira.py/figma.py   integration clients
  crypto.py     (35)    Fernet-at-rest, keyed off APP_SECRET/ENCRYPTION_KEY
  usage.py, prompts.py, weblinks.py, testgen/, scanners.py, contracts.py, api_exec.py
  requirements.txt      fastapi, pymongo, httpx, tree-sitter, numpy, boto3(Bedrock), reportlab…

frontend/               React (Vite + Tailwind) → built into app/static-react/, served by app
  src/features/         dashboard, projects, features, cases, steps, testplan, validator,
                        cycles, coverage(gap), mindmap, usage, users, config, auth
  src/lib/api.js        API client;  src/hooks/useSession.js
  src/legacy/           older single-file app kept around

config/                 layer-2 bundled DB assets
  mongod.conf           mongod config
  mongot.conf           mongot config (points at private password path)
  setup-replica-set.sh  initiates 3-member rs0, creates mongotUser (searchCoordinator)
  mongot-entrypoint.sh  self-heals NUL-corrupted journal; copies pwfile to 0400 path
  pwfile                mongot password file (committed secret — see §6)

docker-compose.yml            include: app + mongodb + ollama (full bundled stack)
docker-compose.app.yml        app alone (only service a client strictly needs)
docker-compose.mongodb.yml    3x mongod + mongod-setup + mongot
docker-compose.ollama.yml     ollama + ollama-pull (pulls both models)

install.sh / install.ps1      one-command setup for PUBLISHED image (macOS/Linux / Windows)
run.sh / run.ps1              one-command build+launch from SOURCE + log capture
collect-logs.sh / .ps1        dump container logs/health to ./logs/
scripts/fix-rbac-users.sh, scripts/reset-smtp-secret.sh   ops helpers
.env.example                  template; run.sh/install copy to .env
tests/                        pytest suite (RBAC, pipeline, grounding, sheet import, …)
.github/workflows/            CI
```

---

## 4. Startup / bootstrap sequence (`core/bootstrap.py`, wired from `main.py`)

`main.py`'s `@app.on_event("startup")` handler starts a background `bootstrap()` thread
(the function itself now lives in `core/bootstrap.py`, not `main.py` — see §3), plus a
stale-job sweeper and import-reanalysis scheduler (`background/schedulers.py`).
`BOOT = {stage, ready, detail}` tracks progress for the UI. Order:

1. **`_ensure_app_secret()`** — zero-config: if the effective secret is still weak/unset
   AND `.env` is writable AND no `SESSION_SECRET`/`ENCRYPTION_KEY` split is in play,
   generate a strong `APP_SECRET`, persist to `.env`, set it in-process.
2. **`_check_app_secret()`** — fail closed if secret weak, unless `ALLOW_WEAK_SECRET=true`.
3. **`_check_production_posture()`** — when `APP_ENV=production`, refuse to boot unless
   `ALLOW_WEAK_SECRET=false`, `COOKIE_SECURE=true`, and SMTP configured. Also hides
   `/docs`, `/redoc`, `/openapi`.
4. `store.ping()` — retry up to 60× (2s) waiting for MongoDB.
5. `fail_orphaned_jobs()`.
6. If `AUTO_SETUP=true` (default): **`ensure_indexes()`** — creates all Mongo indexes +
   6 `vectorSearch` search indexes; retries up to 40× (3s) for a booting mongot. Two
   non-retryable failures reported clearly: search unsupported (`_SEARCH_REQUIRED_MSG`)
   and Atlas per-tier index cap (`_SEARCH_INDEX_LIMIT_MSG` — free M0 allows only 3, needs 6).
7. `migrate_legacy_features()`.
8. Seed first admin from `ADMIN_EMAIL` (validated; malformed value skipped with a warning).

Search: `store` uses mongot `$vectorSearch` (ANN) when available, and **falls back to an
in-memory numpy cosine** when mongot is down/rebuilding — so dev works without a search
cluster, degraded.

---

## 5. Current setup / install flows (the thing we're simplifying)

There are **two entry points**, and neither is truly interactive today.

### `install.sh` / `install.ps1` — published-image path (no source)
- Default (no flag): **bring-your-own MongoDB.** Downloads only `docker-compose.app.yml`
  + `.env.example`, creates `.env`, pulls `adlerqa/wardeniq:beta`, then **stops and prints
  instructions** telling the user to hand-edit `MONGO_URI` in `.env` and run a second
  command (`docker compose -f docker-compose.app.yml up -d --no-build`). → **Not one-click.**
- `--bundled` (or `WARDENIQ_BUNDLED=1` on Windows): also downloads the mongodb/ollama
  compose + `config/`, then `docker compose up -d --no-build` — this one does auto-start.
- Both set `OLLAMA_URL_BUNDLED` per mode (in-stack container vs `host.docker.internal`).

### `run.sh` / `run.ps1` — source build path
- `docker compose up -d --build` (full bundled stack), `sleep 45`, capture logs.
- `--reset` wipes volumes.

### Friction points (candidates for the interactive installer)
- Default install path is a dead stop requiring manual `.env` editing + a second command.
- No prompts to choose: bundled-vs-BYO DB, bundled-vs-hosted AI, enter `MONGO_URI`,
  pick/enter a hosted LLM provider + key, set `ADMIN_EMAIL`, choose `--reset`.
- Bundled ↔ app-only mode selection is a CLI flag most users won't discover.
- First boot is slow (replica-set init + model pulls) with only log-tailing for feedback.
- No pre-flight checks beyond "is docker installed" (ports free? disk? RAM for 3 mongod + models?).
- In-app there IS a config UI (Database / LLM / Embeddings / Email tabs) that writes back
  to `.env` — an interactive installer should hand off to it cleanly rather than duplicate it.

---

## 6. Auth & security model (for the functional + security-fix pass)

**Auth is always on.** Two sign-in paths coexist (`frontend/.../auth/LoginPage.jsx`,
`app/auth.py`):
- **Passwordless email OTP** — `POST /api/auth/request-otp` → 6-digit code (SMTP or, with
  no SMTP, returned as `dev_code` / printed to log) → `POST /api/auth/verify-otp` → signed
  HTTP-only cookie session. OTP hashed with `APP_SECRET`, 10-min TTL, 5 attempts.
- **Local admin password** — bootstrap `admin` / `admin123` (`auth.DEFAULT_LOCAL_PASSWORD`),
  PBKDF2-HMAC-SHA256, 200k iters, per-password salt. Shown when SMTP isn't configured;
  drives a mandatory change-password flow.

Sessions: stateless HMAC tokens (`user_id.session_version.exp.sig`) keyed by
`SESSION_SECRET || APP_SECRET`. Bumping a user's `session_version` revokes their sessions
(used on role change / disable). Roles: **viewer < editor < admin**, server-enforced.
Secrets at rest: Fernet in `crypto.py`, keyed off `ENCRYPTION_KEY || APP_SECRET`.

### Security items — status

**FIXED (this pass):**
- **Committed mongot secret → auto-generated.** `config/pwfile` is now git-ignored and
  removed from tracking; a strong random value is generated at install/run time.
  `setup-replica-set.sh` reads that same file (mounted read-only into `mongod-setup` at
  `/run/secrets/mongot-pw`) instead of hard-coding `mongotPassword`, and `updateUser`s on
  re-run so rotation actually takes effect. `MONGOT_PASSWORD` env overrides if set.
- **`admin123` default → operator-chosen.** New `ADMIN_PASSWORD` env: the interactive
  installer prompts for it (policy-checked), the app seeds the local `admin` hash from it
  at boot, and `admin123` stops working once set. Blank keeps the old default + its forced
  change-on-first-login. Login/change endpoints compare against the configured default, not
  a hardcoded `admin123`.

**FIXED (this pass):**
- **DB ports no longer published.** Removed host publishing of mongod `27017` and mongot
  `27027`/`9946` from `docker-compose.mongodb.yml` — they're reachable only over
  `warden-net`. Opt back in for debugging via `docker-compose.db-ports.yml`.
- **Optional MongoDB auth.** New opt-in, default-off keyfile auth: `scripts/enable-mongo-auth.sh`
  (two-phase bootstrap) + `docker-compose.mongodb-auth.yml` (keyfile override) +
  `config/mongod-entrypoint.sh` (fixes the bind-mount keyfile-perms gotcha, mirroring the
  mongot entrypoint) + `setup-replica-set.sh` root/app user provisioning + `MONGO_AUTH_*`
  env vars. App user gets `root` (single-tenant; guarantees search-index creation works).
  **Not yet validated on a live Docker host — needs one real run to confirm.**

**Still open (candidates for a later pass):**
- **Weak-secret escape hatch.** `ALLOW_WEAK_SECRET=true` bypasses the boot gate; already
  blocked from combining with `APP_ENV=production` via `_check_production_posture`.
- **`COOKIE_SECURE=false` default** (correct for local; production gate forces true).
- Scope the bundled app DB user down from `root` to least-privilege once search-index
  privileges under auth are confirmed on a live run.
- `WEBHOOK_SECRET` needed only when exposing the Jira/GitHub inbound webhook.

---

## 7. Key env vars (see `.env.example` + README "Configuration")

| Var | Default | Purpose |
|---|---|---|
| `APP_SECRET` | `change-me-in-production` | Signs sessions/OTP **and** derives encryption key. Auto-generated on first boot if writable. |
| `SESSION_SECRET` / `ENCRYPTION_KEY` | empty | Optional split of `APP_SECRET`'s two roles (both must be strong if set). |
| `APP_ENV` | `development` | `production` ⇒ hard startup gates + hide API docs. |
| `ALLOW_WEAK_SECRET` | `false` | Local-only bypass of weak-secret gate. |
| `MONGO_URI` / `MONGO_URI_BUNDLED` | empty / bundled rs0 | Layer-2 endpoint; explicit value locks UI field. |
| `OLLAMA_URL` / `OLLAMA_URL_BUNDLED` | empty / per-mode | Layer-3 endpoint. |
| `GEN_MODEL` / `EMBED_MODEL` / `EMBED_DIM` | `qwen2.5:3b` / `nomic-embed-text` / `768` | Models. |
| `GEN_TOTAL` | `16` | Baseline case count at "Standard" depth. |
| `ADMIN_EMAIL` | empty | Seeds first admin; else first code-requester becomes admin. |
| `COOKIE_SECURE` | `false` | true over HTTPS. |
| `SESSION_TTL_SECONDS` / `OTP_TTL_SECONDS` | `604800` / `600` | 7 days / 10 min. |
| `GITHUB_TOKEN` / `POLL_INTERVAL_SECONDS` / `WEBHOOK_SECRET` | — | GitHub integration. |
| `SMTP_*` | empty | OTP email fallback (in-app config takes precedence). |
| `APP_IMAGE` / `MONGO_IMAGE` / `MONGOT_IMAGE` | pinned | Image overrides; bundled MongoDB must be **8.1+** because `config/mongod.conf` enables `useGrpcForSearch` for mongot's gRPC transport. |
| `AUTO_SETUP` | `true` | Run index/search setup on boot. |

Ports: app `8001`, mongod `27017`, mongot `27027`/`9946`, ollama `11434`.
Images pinned: `mongodb-community-server:8.3-ubi9` (MongoDB 8.1+ required), `mongodb-community-search:0.65.1`,
`ollama/ollama:latest`, app `wardeniq:0.2.3` (source) / `adlerqa/wardeniq:beta` (published).

---

## 8. What changed (this pass) & what's next

**Done:**
1. **Interactive installer** (`install.sh` + `install.ps1`) — prompts (via `/dev/tty`, so
   `curl | bash` still works) for mode (bundled vs bring-your-own DB), `MONGO_URI`, and the
   admin password; runs pre-flight checks (docker/compose/daemon); detects an existing
   install and asks keep-vs-wipe; cleans up old containers and pulls fresh images
   (`down [--remove-orphans/-v]` → `pull` → `up --pull always`); assembles the right compose
   selection automatically; then prints the URL. Env vars (`WARDENIQ_MODE`,
   `WARDENIQ_MONGO_URI`, `WARDENIQ_ADMIN_PASSWORD`, `WARDENIQ_WIPE`, `WARDENIQ_ASSUME_YES`)
   keep it fully non-interactive for CI.
2. **mongot secret** auto-generated & git-ignored (see §6).
3. **`ADMIN_PASSWORD`** operator-chosen bootstrap admin password (see §6). `run.sh`/`run.ps1`
   also generate the pwfile now that it isn't committed.

**Next candidates:**
- Don't publish DB ports (`27017/27027/9946`) in the bundled demo; optionally enable Mongo
  auth (keyfile + `authorization: enabled`) for a hardened self-host profile.
- Pre-flight for free host ports + available RAM/disk before starting the heavy stack.
- In-installer choice to configure a hosted LLM/embedding provider (key) vs deferring to the
  in-app Configuration screen.
