# Contributing to wardenIQ

Thanks for your interest in wardenIQ — an open-source, on-prem test
intelligence platform. This document is the short version of "how to work with
this codebase" so you don't have to guess.

wardenIQ is MIT-licensed. By submitting a contribution you agree it will be
released under the same license.

---

## Ways to contribute

- **Claim it before you start.** Comment on the issue before you start work — it takes
  ten seconds and stops two people independently building the same thing (it's happened
  more than once). Check [ROADMAP.md](ROADMAP.md) for where the project is going and
  which milestone an issue belongs to, and browse the
  [good first issues](https://github.com/adlerqa/wardeniq/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
  filter if you're new here. In return, maintainers aim to respond within a day or so and
  to close issues promptly once they ship.
- **Report a bug** — open a GitHub issue with steps to reproduce, expected vs.
  actual behavior, and your environment (OS, Docker version, LLM provider).
- **Request a feature** — open an issue describing the use case first; that
  saves everyone time before code is written.
- **Send a pull request** — see the workflow below.
- **Improve docs** — README, CHANGELOG, this file, or in-code comments are all
  fair game.
- **Report a security issue** — do **not** open a public issue. See
  [`SECURITY.md`](./SECURITY.md).

---

## Local development

The whole stack runs in Docker Compose. You do **not** need Python, Node, or
MongoDB installed locally.

```bash
git clone https://github.com/adlerqa/wardeniq.git wardenIQ
cd wardenIQ
cp .env.example .env    # then edit .env — at minimum, set a strong APP_SECRET
./run.sh                # builds and starts everything
```

Open <http://localhost:8001>. On first launch the MongoDB replica set
initializes and the local Ollama model is pulled — this takes a few minutes.

### Signing in without SMTP

If you don't want to set up email while developing, wardenIQ runs in **demo
mode**: your sign-in code is shown directly on the sign-in screen (and also
printed to the server log — `docker logs warden-app`). Configure SMTP under
*Configuration → Email* to turn the demo path off.

### Useful commands

- Restart the app after a code change: `docker compose restart wardeniq`
- Tail logs: `./collect-logs.sh` or `docker logs -f warden-app`
- Reset everything (destroys data): `docker compose down -v`

---

## Repository layout

See `PROJECT_CONTEXT.md` §3 for the full annotated breakdown. Highlights
(updated for the backend restructure — `app/main.py` and `app/store.py` were
split into packages; behavior is unchanged, see REFACTOR_PLAN.md):

- `app/main.py` (201 lines) — app assembly only: `FastAPI()`, middleware
  registration, the 20 `api/routes/` router includes. **No route handlers
  live here anymore** — see `app/api/routes/`.
- `app/api/routes/` — one file per route domain (auth, users, projects,
  features, code_coverage, …), 20 files total, each an `APIRouter` included
  in `main.py`. Routes orchestrate only.
- `app/store/` — **all** MongoDB and mongot access lives here (composed from
  per-domain mixin files behind one `Store` class, `store/__init__.py`). Do
  not add DB calls elsewhere.
- `app/core/` — cross-cutting singletons/helpers: `config.py` (env
  constants), `state.py` (the `store`/`SYNC` singletons), `security.py`
  (RBAC + `auth_gateway`/`security_headers` middleware), `deps.py` (LLM/git
  clients), `bootstrap.py` (startup sequence), `audit.py`, `exceptions.py`.
- `app/workers/` — the background job registry (`registry.py`) plus one file
  per job type (generation, validator, code_coverage, codeanalysis,
  repo_scan, test_import).
- `app/background/` — the GitHub/GitLab sync poller and the stale-job /
  imported-sheet-reanalysis schedulers.
- `app/llm.py`, `app/prompts.py` — pluggable LLM client and prompt strings.
- `app/coverage.py` — PR→feature mapping, PR coverage, Mind Map reviewer,
  impact analysis, version diff.
- `app/embeddings.py` — Ollama embeddings.
- `app/extract.py` — PDF/DOCX/Markdown extraction and chunking.
- `app/auth.py`, `app/email_send.py`, `app/crypto.py` — passwordless OTP,
  signed-cookie sessions, SMTP, Fernet encryption of secrets at rest.
- `app/static/index.html` and `frontend/` — UI (vanilla JS legacy shell plus a
  React port in progress).
- `config/` — `mongod.conf`, `mongot.conf`, replica-set init.
- `docker-compose.yml`, `run.sh`, `collect-logs.sh` — local dev entry points.
- `tests/` — pytest suite.

**Invariants (enforced by the restructure): no DB access outside `app/store/`;
no route handlers in `app/main.py`.**

---

## Coding conventions

Please follow the same rules the maintainers do — most of them exist for a
reason.

- **All database access lives in `app/store/`.** Add a helper to the mixin
  file for that domain (e.g. `store/projects.py` for project-related
  queries) and call it from your route; do not use `store.mongo`/`store.db`
  directly from `main.py`, `app/api/routes/`, or a feature module.
- **All LLM prompt logic lives in `app/coverage.py` and `app/prompts.py`.**
  Routes should orchestrate, not build prompts inline.
- **Secrets go through `app/crypto.py`** (Fernet, keyed by `APP_SECRET`) and
  are masked on read.
- **Embeddings and LLM calls go through the `Embedder` and `LLM` classes** so
  providers can be swapped without changes at the call site.
- **Mongo is schemaless — no migrations folder.** If you change the data
  model, update the `_ensure_*` helpers in `app/store/base.py` so fresh
  installs and existing databases converge, and document the change in
  `CHANGELOG.md`.
- **Keep diffs small and compatible.** wardenIQ is `v0.2.3`; users are
  running it. Prefer additive changes over breaking ones.
- **Do not commit generated artifacts, `.env` files, credentials, or
  vendored model weights.**
- **Environment variables and `.env.example` comments:** Keep comments on
  their own line above variables, never as inline comments on value lines
  (e.g. `KEY=val # comment`). Trailing inline comments leak into parsed values
  under Docker Compose `env_file`, shell `source`, or certain dotenv parsers
  (which caused issues like `.env comment leaked as ADMIN_EMAIL`).

Python code targets the version pinned in the Docker image. Match the style
of the file you are editing.

---

## Tests

The test suite is pytest, in `tests/`. Run it with:

```bash
docker compose exec wardeniq pytest
```

Or, if you have Python locally with the app requirements installed:

```bash
pytest
```

Guidelines:

- Add tests for new functionality where practical, especially in `app/store/`,
  `app/auth.py`, `app/coverage.py`, and any new `app/api/routes/` file.
- Do **not** rely on real external services in tests — mock GitHub, GitLab,
  SMTP, LLM providers, and Ollama.
- Prefer the fake-store pattern used in `tests/test_rbac_invite.py` for
  handler-level tests.

---

## Pull request workflow

1. Fork the repo and create a topic branch off `main`:
   `git checkout -b fix/short-description`.
2. Make your change. Keep unrelated changes out of the same PR.
3. Run the tests locally and update `CHANGELOG.md` if the change is
   user-visible.
4. Push and open a PR against `main`. In the description, cover:
   - What the change does and why.
   - Any migration or config implications.
   - How you tested it.
5. A maintainer will review. Please respond to review comments rather than
   force-pushing over them silently.
6. Squash-merge is preferred; the merger will squash on your behalf.

Please do not include unrelated formatting churn in a functional PR — it makes
the diff hard to review.

---

## Commit messages

Short, imperative, and specific. `fix: reject empty ADMIN_EMAIL` is better
than `bugfix`. If your commit references an issue, add `Closes #123` at the
bottom.

---

## Community

Please be respectful in issues and PRs. Assume good intent; disagree with
ideas, not people. Maintainers are volunteers.

Thanks again for contributing.
