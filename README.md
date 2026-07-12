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
| **Docker + Docker Compose** (v2.20+) | Runs the whole stack with one command |
| **~8–10 GB free RAM** | 3 MongoDB nodes + search + a small local model |
| **A few GB of disk** | Images + model downloads |
| *(optional)* **GitHub token (PAT)** | Needed to analyze private repos / open PRs |
| *(optional)* **SMTP details** | To email sign-in codes (you can skip this at first — see below) |
| *(optional)* **A hosted LLM API key** | Sharper results than the small local model |

That's it. You do **not** need Node, Python, or a database installed — it's all in
the containers.

---

## Quick start (about 5 minutes)

```bash
git clone https://github.com/adlerqa/wardeniq.git wardenIQ && cd wardenIQ
cp .env.example .env        # open .env and change APP_SECRET to any long random string
./run.sh                    # builds + starts everything
```

Then open **http://localhost:8001**.

> **First launch takes a few minutes** — it initializes the MongoDB replica set and
> downloads the local models. Grab a coffee; it's a one-time cost.

*(No source code, just a Docker image? Skip the clone — set `APP_IMAGE` in `.env` to
the published image. See the App image note in `.env.example`.)*

### Signing in the very first time

wardenIQ always requires a login (passwordless — it emails you a 6-digit code). But
you haven't set up email yet, so there's a built-in shortcut:

1. On the sign-in screen, enter your email. With no users yet, **you become the admin.**
2. wardenIQ prints your code to the **server log** instead of emailing it. Read it with:

   ```bash
   docker logs -f warden-app
   ```

   Look for a box like:

   ```
   ================================================================
   [wardenIQ] SMTP is not configured yet — one-time sign-in code
   [wardenIQ]   you@company.com: 481920
   ================================================================
   ```

3. Enter that code, and you're in. Now go to **Configuration → Email**, add your SMTP
   details, and from then on codes are emailed normally (and never logged again).

Prefer to seed the admin ahead of time? Set `ADMIN_EMAIL=you@company.com` in `.env`.

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

- **I can't sign in / "email delivery isn't set up yet."** You haven't configured SMTP.
  Read your one-time code from the log: `docker logs -f warden-app`. (Only admins get the
  log shortcut; regular users need SMTP configured first.)
- **First start is slow or the page won't load.** Give it a few minutes — the replica set
  and model downloads take time on first run. Check progress with
  `docker compose logs -f` or the captured logs in `./logs/`.
- **Mind Map result is empty for a feature.** Usually the wrong **branch** is selected for
  a repo, or the logic lives only in test files (excluded on purpose). The Mind Map shows
  exactly which files it read, so you can tell which.
- **Test generation is slow or shallow.** The default local model is CPU-friendly, not
  powerful. Switch to a bigger local model or a hosted provider under Configuration → LLM.
- **Fresh start / wipe everything:** `./run.sh --reset` (deletes the data volumes).

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
run.sh          one-command launch + log capture
collect-logs.sh dump all container logs/health into ./logs/
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
