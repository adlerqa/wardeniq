# Architecture & internals

### Mind Map reads the whole codebase

Coverage review is **exhaustive**. Every production chunk retrieved for a feature is
actually read: the corpus is swept in as many context-sized windows as it takes, and a
case is only reported `uncovered` after *every* window has failed to find its
implementation. Cases proven `covered` drop out early, so the sweep costs far less than
the worst case suggests.

This replaced a hard cap that showed the reviewer the first ~20 chunks and discarded the
rest — on a 101-file repository that meant judging 5% of the code and reporting the
result as a verdict about all of it. Expect more LLM calls per feature than before, and
correspondingly more trustworthy verdicts; `MINDMAP_MAX_WINDOWS` bounds it if needed.

> **Changing the test/spec exclusion rules re-indexes automatically.** A repo's code
> index records a fingerprint of the rules that produced it, so a rules change
> invalidates every stale index by itself — you do not have to know to rebuild. The
> `force_reindex: true` flag on `/api/code-analysis` remains for the unrelated case of
> wanting a fresh fetch at an unchanged branch head.

**Executing API tests for real** (off unless `API_EXEC_BASE_URL` is set - there is no
default target, so this can never accidentally fire traffic at production):

| Var | Default | Purpose |
|---|---|---|
| `API_EXEC_BASE_URL` | _(empty = disabled)_ | Base URL of a staging/sandbox environment to run API test cases against, turning them from a written expectation into an observed pass/fail |
| `API_EXEC_ALLOW_MUTATING` | `false` | Permit `POST`/`PUT`/`PATCH`/`DELETE`. Off by default because the usual target is shared |
| `API_EXEC_HEADERS` | _(empty)_ | JSON object of headers sent with every request, e.g. `{"Authorization":"Bearer ..."}` |
| `API_EXEC_TIMEOUT_SECONDS` / `API_EXEC_VERIFY_TLS` | `20` / `true` | Per-request timeout; set verify to `false` only for a self-signed staging cert |

**Optional deterministic scanners.** If `semgrep` and/or `gitleaks` are on `PATH`, their
findings are attached to coverage verdicts as *corroborating evidence* (they never change
a verdict). Neither is a dependency - with both absent, behaviour is unchanged. Set
`SEMGREP_CONFIG` to a local rules path for a strictly offline install, and
`SCANNER_TIMEOUT_SECONDS` / `SCANNER_MAX_BYTES` / `SCANNER_MAX_FINDINGS` to bound the run.

---

### Measuring accuracy

`tests/eval/` scores the coverage and dedup logic against hand-labelled ground truth, so a
prompt or model change produces a number instead of an impression:

```bash
python -m tests.eval.run_eval                      # offline: grounding probes + dedup
python -m tests.eval.run_eval --coverage \
    --provider ollama --model qwen2.5:7b           # real-model coverage accuracy
```

The offline sections are deterministic and expected to score `1.0`, so they're safe to
gate CI on (non-zero exit on regression). The `--coverage` section needs a reachable LLM
and reports per-status precision/recall plus an **overclaim rate** - how often a verdict
claimed *more* coverage than the truth, tracked separately because saying "tested" about
untested behaviour is a worse error than the reverse.

SMTP (for sign-in emails) is set under **Configuration → Email** (stored encrypted, takes
precedence) or via `SMTP_*` vars in `.env`. Until SMTP exists, the first admin's code is
printed to the server log (see [Signing in](#signing-in-the-very-first-time)). AWS Bedrock
credentials are **not** `.env` vars — set them under Configuration → LLM/Embeddings.

`MONGO_URI` can also be changed from **Configuration → Database** in the UI, which
writes it back into `.env` for you (restart applies it) and offers a **"Move my data
to another database"** option to copy your data over safely before switching.

---

---

## Architecture — one product container, the rest are upstream OSS

```
                 ┌──────────────────────────── wardenIQ (this repo) ───────────┐
   PRD/HLD/LLD ─►│  FastAPI app + React UI  (./app + ./frontend)                │
   GitHub repos ►│  generation · RAG · versioning · coverage · reports          │
                 └───────┬───────────────┬────────────────────┬────────────────┘
                         ▼               ▼                     ▼
              Ollama (LLM + embeddings)  mongot (search/vector)  MongoDB replica set
              ollama/ollama              mongodb-community-search  MongoDB Community (x3: 1P+2S)
```

Only **`./app`** (backend) and **`./frontend`** (React UI, built and served by the app)
are wardenIQ's code. MongoDB, mongot, and Ollama are mature projects maintained by others
— wardenIQ orchestrates them.

---

---

## High availability & production

For production, the recommended path is [Cloud / lightweight
deployment](#cloud--lightweight-deployment-recommended-for-real-use) — a managed
MongoDB (e.g. Atlas, which already gives you HA/backups/failover) plus a hosted LLM,
with just the app container to operate. The notes below are specifically for the
*optional* bundled demo stack, if you choose to self-host MongoDB instead of using a
managed one:

Ships as a **3-node replica set** (`rs0`): one primary, two secondaries — failover plus
backup/read from a secondary. For light dev, scale to one node (comment out
`mongod2`/`mongod3` and use a one-member `rs.initiate` in
`config/setup-replica-set.sh`). For production: put TLS in front of the app, set
`COOKIE_SECURE=true`, use a strong `APP_SECRET`, set `APP_ENV=production`, and enable
MongoDB authentication (below).

**Database ports are not published.** The bundled MongoDB (`27017`) and mongot
(`27027`/`9946`) are reachable only over the internal `warden-net` Docker network — the
app connects there, and nothing binds to the host. To attach a local `mongosh`/Compass
for debugging, opt in with the override:
`docker compose -f docker-compose.yml -f docker-compose.db-ports.yml up -d`.

**Optional MongoDB authentication.** The bundled set is unauthenticated by default (for
zero-config onboarding). To turn on auth, run `./scripts/enable-mongo-auth.sh`: it
generates a replica-set keyfile, provisions a root + app user (two-phase bootstrap:
create users, then restart with the keyfile to enforce them), writes an authenticated
`MONGO_URI` into `.env`, and sets `COMPOSE_FILE` so every later `docker compose` / `run.sh`
keeps auth on. mongot is unaffected (it already authenticates as `mongotUser`). See
`docker-compose.mongodb-auth.yml`.

---

---

## Project layout

```
app/            wardenIQ backend (FastAPI) + Dockerfile (also builds the UI)
                (organized as core/, workers/, background/, api/routes/, store/ — see
                PROJECT_CONTEXT.md §3 for the full annotated breakdown; invariants:
                no DB access outside store/, no route handlers in main.py)
frontend/       React UI (built into app/static-react/ and served by the app)
config/         mongod.conf, mongot.conf, replica-set init, mongot password file
docker-compose.yml        the app + Mongo replica set + mongot + Ollama
docker-compose.app.yml    the app alone (the only service a client needs)
docker-compose.mongodb.yml / docker-compose.ollama.yml   the bundled dependencies
install.sh / install.ps1  one-command setup for the published image (macOS/Linux / Windows)
run.sh          one-command launch + log capture (macOS/Linux)
collect-logs.sh dump all container logs/health into ./logs/ (macOS/Linux)
run.ps1         same as run.sh, for Windows
collect-logs.ps1 same as collect-logs.sh, for Windows
```

---
