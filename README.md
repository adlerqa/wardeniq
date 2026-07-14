# wardenIQ — Test Intelligence Platform

> **QC for AI-built software.** Point wardenIQ at your requirement docs and your
> code. It writes a structured test suite from the docs, then continuously checks
> your GitHub code against those tests — so you always know **what's covered,
> what's automated, and what's at risk.**

**`v0.1.0-beta`** — early, evolving, open. Licensed **MIT**: fork it, run it
on-prem, use it commercially, no strings.

---

## The idea in 30 seconds

You wrote requirements. An LLM (or a teammate) wrote the code. **Does the code
actually do what the requirements asked?** wardenIQ answers that:

```
  Your docs                    wardenIQ                       Your repos
  (PRD/HLD/LLD)  ───────►  turns them into  ───────►  and checks the real code
                            a test suite               against every test case
                                 │
                                 ▼
             a live map of coverage, risk, and gaps you can act on
```

Everything runs **on your machine** by default (local LLM + database). Nothing
leaves your infrastructure unless you choose a hosted LLM.

---

## What you can do with it

- **Generate test cases from docs** — upload PRD/HLD/LLD files (PDF, DOCX, Markdown);
  get **Functional, E2E, API, and Non-functional** cases. A *depth* dial sets how
  many; *focus sliders* set the mix.
- **Keep them clean & reusable** — cases are built from atomic **steps**; edit a step
  once and it updates everywhere. Duplicates are merged across features automatically.
- **Version safely** — re-upload changed docs as a new **version**; still-valid cases
  are kept, obsolete ones retired (in history), new ones added.
- **Analyze your code** — watch a project's repos and let the LLM map commits/PRs to
  the **test cases they impact** and the **coverage** a merged PR delivers.
- **Mind Map (deep analysis)** — reads your **actual production code** and, acting as
  an external reviewer, judges each feature: **covered / partial / uncovered**, with
  reasons and the exact files it read.
- **Track releases** — build a regression **cycle** from selected cases and track
  status per case.
- **Start Developing** — generate implementation code for a feature and open a PR
  (needs a write-scoped GitHub token).
- **See it all** — a dashboard with coverage %, automation %, per-project rollups, and
  a per-feature **PDF report**.

---

## Requirements

| You need | Why |
|---|---|
| **Docker** (Compose v2.20+ if using the bundled stack) | Runs the app; Compose only needed if you also want the bundled DB/models |
| **~8–10 GB free RAM** — *only* if running the **full bundled stack** locally | 3 MongoDB nodes + search + a small local model, all on your machine |
| **~2–4 GB free RAM** — if running **just the app** against a cloud database + hosted LLM | The app container itself is lightweight; the heavy pieces (DB, model) live elsewhere |
| **A few GB of disk** | Images + (if bundled) model downloads |
| *(optional)* **GitHub token (PAT)** | Needed to analyze private repos / open PRs |
| *(optional)* **SMTP details** | To email sign-in codes (you can skip this at first — see below) |
| *(optional)* **A hosted LLM API key** | Sharper results than the small local model |

That's it. You do **not** need Node, Python, or a database installed locally — it's
all in the container(s). Works the same on **macOS, Linux, and Windows** (Docker
Desktop) — Windows users run `run.ps1` instead of `run.sh`; see Quick start below.

The 8–10 GB figure is only for the all-local **demo** setup (3-node MongoDB replica
set + search + Ollama bundled in); if you point wardenIQ at a **cloud MongoDB** (e.g.
Atlas) and a **hosted LLM** (OpenAI/Anthropic/etc.) instead, the app itself needs only
a couple GB of RAM — see [Cloud / lightweight
deployment](#cloud--lightweight-deployment-recommended-for-real-use) below.

---

## Quick start (about 5 minutes)

There are two ways to run wardenIQ — pick whichever fits:

- **Have the source, or want to build it yourself?** Clone and build (below).
- **Just want to run it — no source needed?** Skip straight to [Prefer a pre-built
  image?](#prefer-a-pre-built-image-skip-the-local-build--recommended) — you only
  need one small config file and `docker pull`, nothing to clone or compile.

### Option A — Clone and build from source

```bash
git clone https://github.com/adlerqa/wardeniq.git wardenIQ && cd wardenIQ
cp .env.example .env        # no further edits needed — see note below
./run.sh                    # builds + starts everything
```

**On Windows**, use the PowerShell equivalent instead (no WSL or Git Bash
required — just Docker Desktop):

```powershell
git clone https://github.com/adlerqa/wardeniq.git wardenIQ; cd wardenIQ
Copy-Item .env.example .env
.\run.ps1
```

If Windows blocks the script from running, either run it once via
`powershell -ExecutionPolicy Bypass -File .\run.ps1`, or relax the policy for
your user one time with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Then open **http://localhost:8001**.

> **You don't have to touch `.env` for this first run.** If you leave `APP_SECRET`
> unset/default, wardenIQ generates a strong one automatically on first boot and
> saves it back into `.env` for you (logged once to `docker logs -f warden-app`).
> It never runs with a known/default secret — it either generates a real one or
> refuses to start, so this is a genuine zero-edit first run, not a weaker one. Before
> a real deployment, open `.env` and confirm `APP_SECRET` looks like a long random
> string (it will, if it was auto-generated) — back that file up, since losing it
> invalidates sessions and locks you out of any encrypted settings (API keys, SMTP
> password) already saved.

> **First launch takes a few minutes** — it initializes the MongoDB replica set and
> downloads the local models. Grab a coffee; it's a one-time cost.

### Signing in the very first time

wardenIQ always requires a login. When SMTP (email delivery) is not yet set up, the application displays a Username/Password screen.

To sign in the very first time:
1. On the login screen, enter the default administrator credentials:
   - **Username**: `admin`
   - **Password**: `admin123`
2. Once you are signed in, navigate to **Configuration → Email**.
3. Set up your SMTP details. Once email delivery is configured, wardenIQ will automatically disable password login and switch to the standard passwordless email OTP sign-in flow (emailing you a one-time 6-digit code for each login).

Prefer to seed the admin ahead of time? Set `ADMIN_EMAIL=you@company.com` in `.env`.

---

## Prefer a pre-built image? (skip the local build — recommended)

### Option B — Pull the pre-built image, no source needed

Don't build from source. wardenIQ publishes a ready-to-run image straight to Docker
Hub: **[`adlerqa/wardeniq`](https://hub.docker.com/r/adlerqa/wardeniq)**. Pulling it
gets you the exact same app, already compiled — no Node/Python toolchain, no waiting
on a build, no source code required at all.

```bash
docker pull adlerqa/wardeniq:beta
```

That single command always grabs the current published version. When a new one
ships, running it again pulls the update — you never rebuild anything yourself.

You do still need one small **recipe file** (Docker Compose file) that tells Docker
how to run the image (ports, env vars, and — if you want it — the bundled database).
That file is a few KB, separate from the app's source code, so "no repo" really means
"no source files," not "zero files." Grab just what you need without cloning:

```bash
mkdir wardeniq && cd wardeniq
curl -fsSLO https://raw.githubusercontent.com/adlerqa/wardeniq/main/docker-compose.app.yml
curl -fsSLO https://raw.githubusercontent.com/adlerqa/wardeniq/main/.env.example
cp .env.example .env
```

Then edit `.env` — this file is **yours**, it lives on your machine (or server), never
inside the image. The only line you actually *must* fill in here is `MONGO_URI` (this
flow has no bundled database to fall back to); `APP_SECRET` can be left as-is —
wardenIQ generates and saves a strong one on first boot if you don't set one (see the
note in Quick start above):

```
APP_IMAGE=adlerqa/wardeniq:beta
MONGO_URI=<your MongoDB connection string — see Cloud deployment below>
```

Start it — **no `--build`**, Compose just pulls the image since `APP_IMAGE` is set:

```bash
docker compose -f docker-compose.app.yml up -d
docker logs -f warden-app     # watch it come up / read the first sign-in code
```

Open **http://localhost:8001** (or your server's address). First sign-in works the
same as the Quick start above.

> Want the **bundled** MongoDB/Ollama too instead of your own? Also grab
> `docker-compose.yml`, `docker-compose.mongodb.yml`, `docker-compose.ollama.yml`, and
> the `config/` folder the same way, then run `docker compose up -d` (no `-f`,
> no `--build`) from that folder instead. This is the heavier, all-local demo path —
> see the RAM note in [Requirements](#requirements).

> **Maintainers:** the image is built and pushed by
> `.github/workflows/docker-publish.yml` — run it manually (any tag, defaults to
> `beta`) or push a `vX.Y.Z` git tag to publish a version + `latest`. Requires the
> `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo secrets.

---

## Cloud / lightweight deployment (recommended for real use)

The bundled 3-node MongoDB + local Ollama setup above is a **local demo/trial
convenience** — it's not what you'd actually run for a team. For real use, don't run
MongoDB or the model locally at all:

- **Database:** point `MONGO_URI` at a cloud MongoDB (e.g. **MongoDB Atlas**) instead
  of the bundled replica set. wardenIQ needs a *search-capable* database — Atlas has
  this built in, but wardenIQ creates **6 search indexes**, and Atlas caps that by
  cluster tier: the **free M0 tier only allows 3**, so it **won't work** — you need a
  **dedicated M10+ tier** (or your own self-managed MongoDB with `mongot`).
- **LLM/embeddings:** use a hosted provider (OpenAI, Anthropic, Gemini, Mistral, Groq,
  AWS Bedrock, or any OpenAI-compatible endpoint) under **Configuration** after first
  sign-in, instead of the bundled local Ollama model.

With both of those pointed at the cloud, you only ever run **one container** — the
app itself — which is why the RAM requirement drops to **~2–4 GB** instead of 8–10 GB:
there's no local database or model competing for your machine's resources. This is
also the natural setup for a **cloud deployment** (e.g. a single small VM/ECS/Cloud
Run instance running `adlerqa/wardeniq:beta`, with `MONGO_URI` pointing at Atlas) —
nobody running or connecting to the tool needs to provision a database or GPU/CPU
budget for a local model.

---

## Your first run: a guided tour

Here's the whole journey, then each step in detail:

```
  Sign in ─► Create a Project ─► Connect repos ─► Add a Feature (upload docs)
     │
     └─► Generate test cases ─► Review & edit ─► Analyze code ─► Mind Map
            │
            └─► Track in a Cycle ─► Export a report
```

The left sidebar has everything: **Dashboard · Projects & Repos · Test Cases ·
Code Analysis & Cycles · Mind Map · Step Library · Usage & Cost · Configuration**.

**Step 1 — Create a project.** Go to **Projects & Repos** and add a project. A project
is a product or team space that holds its features, repos, and results.

**Step 2 — Connect your repos (optional but recommended).** Add your GitHub (or GitLab)
repositories to the project and pick the **branch per repo** (leave blank for the
default). This is what powers code analysis and the Mind Map later. Private repos need
a token — paste it under **Configuration → Integrations**, or set `GITHUB_TOKEN` in `.env`.

**Step 3 — Add a feature = upload your docs.** Create a feature and upload one or more
requirement documents (PRD / HLD / LLD, as PDF / DOCX / Markdown). A "feature" is one
unit of behavior you want tested.

**Step 4 — Generate the test cases.** Choose a **coverage depth** (how thorough) and use
the **focus sliders** to weight Functional / E2E / API / Non-functional. Hit generate —
it runs as a background **job** you can watch live or come back to.

**Step 5 — Review & refine.** Open **Test Cases** to read, edit, filter, and organize the
generated cases. Cases are made of reusable **steps** (see **Step Library**) — edit a step
once and every case using it updates.

**Step 6 — Analyze your code.** In **Code Analysis & Cycles**, run analysis to map recent
commits/PRs to the **test cases they impact** and to see the **coverage** a merged PR
delivers (including developer-written automated tests), with linked-commit evidence.

**Step 7 — Run the Mind Map.** For the deepest check, open **Mind Map**. It reads your
actual production code and rates every feature **covered / partial / uncovered**, citing
the files it read. An empty result is explainable (wrong branch? logic only in tests?),
never a black box. Tip: a hosted LLM gives noticeably sharper verdicts than the small
local model.

**Step 8 — Track a release & report.** Assemble a regression **cycle** from the cases you
care about and track status per case. Export a per-feature **PDF report** to share.

**Step 9 (optional) — Start Developing.** Ask wardenIQ to generate implementation code
that satisfies a feature's requirements, push it to a feature-named branch, and open a
**pull request** (needs a write-scoped token). Then analyze that PR for coverage.

---

## Key concepts (glossary)

- **Project** — a workspace for one product/team: its features, repos, and results.
- **Feature** — one unit of behavior, created from your uploaded docs. Has **versions**.
- **Test case** — a typed check (Functional / E2E / API / Non-functional) built from **steps**.
- **Step** — an atomic, reusable action/expected-result. Shared and deduplicated across cases.
- **Coverage %** — how much of your test suite the code (via mapped PRs) actually exercises.
- **Automation %** — how much is covered by developer-written automated tests.
- **Impact analysis** — which test cases a given commit/PR touches.
- **Mind Map** — an external-reviewer pass over real production code: covered/partial/uncovered.
- **Cycle** — a release regression run assembled from selected cases, tracked per case.

---

## Bring your own LLM

The default is fully local via **Ollama** (`qwen2.5:3b` for generation,
`nomic-embed-text` for embeddings). Under **Configuration → LLM** you can switch
generation/analysis to a hosted provider — **OpenAI, Anthropic (Claude), Google Gemini,
Mistral, Groq, AWS Bedrock, or any OpenAI-compatible endpoint** — by picking the provider,
entering a model name, and pasting an API key (encrypted at rest). A **test** button does a
live round-trip. Under **Configuration → Embeddings** you can move the embedding model to a
hosted provider too (OpenAI, Gemini, Voyage AI, Bedrock, or OpenAI-compatible) — then
re-embed so the vector index stays on one consistent model/dimension. Everything stays
on-prem unless you choose a hosted provider.

---

## Roles & access

Passwordless email-OTP sign-in with signed, HTTP-only cookie sessions and three
server-enforced roles:

- **Viewer** — read-only.
- **Editor** — create / edit / generate.
- **Admin** — everything, plus **Users** and **Configuration**.

The first admin is seeded from `ADMIN_EMAIL`, or the first person to request a code
becomes admin. Admins invite others under **Users**.

---

## Configuration (`.env`)

Most things are configurable **in the app** (Configuration screen); `.env` covers
startup and secrets.

| Var | Default | Purpose |
|---|---|---|
| `APP_SECRET` | `change-me-in-production` | Signs sessions/OTPs **and** encrypts stored secrets. **Change it.** |
| `APP_ENV` | `development` | Set `production` to enforce hard startup gates (strong secret, `COOKIE_SECURE=true`, SMTP configured) and hide API docs |
| `SESSION_SECRET` / `ENCRYPTION_KEY` | _(empty)_ | Optional: split `APP_SECRET`'s two roles. Blank = both fall back to `APP_SECRET` |
| `GEN_MODEL` | `qwen2.5:3b` | Ollama generation model (swap in a bigger/hosted model for quality) |
| `EMBED_MODEL` / `EMBED_DIM` | `nomic-embed-text` / `768` | Embedding model + dimensions |
| `GITHUB_TOKEN` | _(empty)_ | Fine-grained PAT (PR + contents read); also settable in-app |
| `POLL_INTERVAL_SECONDS` | `120` | How often watched repos are polled |
| `WEBHOOK_SECRET` | _(empty)_ | Required only if you expose the Jira/GitHub webhook receiver |
| `GEN_TOTAL` | `16` | Baseline test-case count at "Standard" depth |
| `ADMIN_EMAIL` | _(empty)_ | Seeds the first admin; if blank, the first code-requester becomes admin |
| `COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `SESSION_TTL_SECONDS` / `OTP_TTL_SECONDS` | `604800` / `600` | Session lifetime (7 d) / code lifetime (10 min) |
| `MONGO_URI` | _(empty = bundled DB)_ | Bring your own MongoDB; also settable in-app |
| `MONGO_IMAGE` / `MONGOT_IMAGE` | pinned | Override the bundled MongoDB / mongot images |
| `APP_IMAGE` | _(empty = build from source)_ | Point at a published image instead of building |

SMTP (for sign-in emails) is set under **Configuration → Email** (stored encrypted, takes
precedence) or via `SMTP_*` vars in `.env`. Until SMTP exists, the first admin's code is
printed to the server log (see [Signing in](#signing-in-the-very-first-time)). AWS Bedrock
credentials are **not** `.env` vars — set them under Configuration → LLM/Embeddings.

---

## Troubleshooting

- **I can't sign in / SMTP is not configured.** If email delivery is not yet configured, make sure you log in using the default credentials: username `admin` and password `admin123`. Once logged in, configure SMTP in **Configuration → Email**.
- **First start is slow or the page won't load.** Give it a few minutes — the replica set
  and model downloads take time on first run. Check progress with
  `docker compose logs -f` or the captured logs in `./logs/`.
- **Mind Map result is empty for a feature.** Usually the wrong **branch** is selected for
  a repo, or the logic lives only in test files (excluded on purpose). The Mind Map shows
  exactly which files it read, so you can tell which.
- **Test generation is slow or shallow.** The default local model is CPU-friendly, not
  powerful. Switch to a bigger local model or a hosted provider under Configuration → LLM.
- **Fresh start / wipe everything:** `./run.sh --reset` (deletes the data volumes) —
  on Windows, `.\run.ps1 -Reset`.

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

## High availability & production

Ships as a **3-node replica set** (`rs0`): one primary, two secondaries — failover plus
backup/read from a secondary. For light dev, scale to one node (comment out
`mongod2`/`mongod3` and use a one-member `rs.initiate` in
`config/setup-replica-set.sh`). For production: put TLS in front of the app, set
`COOKIE_SECURE=true`, use a strong `APP_SECRET`, set `APP_ENV=production`, and enable
MongoDB authentication (`security.authorization: enabled` + a replica-set keyfile).

---

## Trigger from Jira

wardenIQ exposes an inbound webhook so Jira can drive it:

```
POST /api/integrations/jira/webhook?token=<WEBHOOK_SECRET>
```

In **Jira Automation** → *When issue created/transitioned* → *Send web request* to that
URL with the issue payload. wardenIQ creates a feature from the issue (key → feature key,
summary → name, description → requirement text; Cloud ADF descriptions supported) and
generates its test cases. Because the feature key matches the Jira key, PRs whose
branch/title contain the key auto-link back. Posting results back to Jira is on the roadmap.

---

## Project layout

```
app/            wardenIQ backend (FastAPI) + Dockerfile (also builds the UI)
frontend/       React UI (built into app/static-react/ and served by the app)
config/         mongod.conf, mongot.conf, replica-set init, mongot password file
docker-compose.yml        the app + Mongo replica set + mongot + Ollama
docker-compose.app.yml    the app alone (the only service a client needs)
docker-compose.mongodb.yml / docker-compose.ollama.yml   the bundled dependencies
run.sh          one-command launch + log capture (macOS/Linux)
collect-logs.sh dump all container logs/health into ./logs/ (macOS/Linux)
run.ps1         same as run.sh, for Windows (PowerShell — no WSL/Git Bash needed)
collect-logs.ps1 same as collect-logs.sh, for Windows
```

---

## Status & roadmap

Beta. Known rough edges: generation speed/quality scale with the local model; GitHub
analysis needs a PAT for private repos; LLM mapping is best with descriptive docs.
Contributions welcome.

## License

[MIT](LICENSE) — free for commercial and non-commercial use.

> wardenIQ builds on MongoDB Community Server, mongot, and Ollama, each under its own
> license. wardenIQ does not redistribute those images; Compose pulls them at runtime.
