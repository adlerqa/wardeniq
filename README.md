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

wardenIQ is a single lightweight app container — it doesn't bundle MongoDB into the
product itself. Point it at a **cloud MongoDB** (e.g. Atlas) and a hosted LLM and
that's the whole footprint (recommended — see [Cloud / lightweight
deployment](#cloud--lightweight-deployment-recommended-for-real-use) below). A fully
local, all-in-one demo mode (bundled MongoDB + local model, no cloud accounts needed)
is also available if you just want to try it out first — see [Requirements](#requirements).

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
| **Docker** (Compose v2.20+ only needed for the optional local-trial stack) | Runs the app container itself |
| **~2–4 GB free RAM** | The app container is lightweight; MongoDB and the LLM are **not** part of the product, they're external services you point it at |
| **A few GB of disk** | Images (plus local model downloads only if you use the optional local-trial stack) |
| *(optional)* **GitHub token (PAT)** | Needed to analyze private repos / open PRs |
| *(optional)* **SMTP details** | To email sign-in codes (you can skip this at first — see below) |
| *(optional)* **A hosted LLM API key** | Sharper results than the small local model |

That's it. You do **not** need Node, Python, or a database installed locally — it's
all in the container(s). Works the same on **macOS, Linux, and Windows** (Docker
Desktop) — Windows users run `run.ps1` instead of `run.sh` (one line works from
either Command Prompt or PowerShell; see Quick start below).

**MongoDB and the LLM are upstream dependencies wardenIQ talks to over a connection
string/API key — they are not shipped inside the app and don't need to run locally.**
The recommended, real-world setup is a **cloud MongoDB** (e.g. Atlas) and a **hosted
LLM** (OpenAI/Anthropic/etc.), in which case the only thing you ever run is the app
container itself — see [Cloud / lightweight
deployment](#cloud--lightweight-deployment-recommended-for-real-use) right below. An
all-local bundled stack (further down in [Quick start — local trial / all-in-one
demo](#quick-start--local-trial--all-in-one-demo-about-5-minutes)) is offered only as a
zero-signup way to try wardenIQ before deciding on a real database/LLM — it's not what
you'd run for actual use, and it naturally needs more resources since it runs
MongoDB and a model on your own machine too.

---

## Cloud / lightweight deployment (recommended for real use)

wardenIQ doesn't bundle MongoDB or an LLM into the product — they're upstream
services it connects to over `MONGO_URI` and an API key/endpoint. For real use
(a team, or any non-trial deployment), don't run either one locally:

- **Database:** point `MONGO_URI` at a cloud MongoDB (e.g. **MongoDB Atlas**) — no
  local MongoDB required. wardenIQ needs a *search-capable* database — Atlas has this
  built in, but wardenIQ creates **6 search indexes**, and Atlas caps that by cluster
  tier: the **free M0 tier only allows 3**, so it **won't work** — you need a
  **dedicated M10+ tier** (or your own self-managed MongoDB with `mongot`).
- **LLM/embeddings:** use a hosted provider (OpenAI, Anthropic, Gemini, Mistral, Groq,
  AWS Bedrock, or any OpenAI-compatible endpoint) under **Configuration** after first
  sign-in, instead of a local model.

With both of those pointed at the cloud, you only ever run **one container** — the
app itself — so there's no local database or model competing for your machine's (or
server's) resources. This is the natural shape for a **cloud deployment** too (e.g. a
single small VM/ECS/Cloud Run instance running `adlerqa/wardeniq:beta`, with
`MONGO_URI` pointing at Atlas) — nobody running or connecting to the tool needs to
provision a database or a GPU/CPU budget for a local model. See [Prefer a pre-built
image?](#prefer-a-pre-built-image-skip-the-local-build--recommended) below for the
exact commands (no clone needed) — just set `MONGO_URI` and skip the bundled-stack
compose files entirely.

---

## Quick start — local trial / all-in-one demo (about 5 minutes)

This path bundles MongoDB and a small local model into your own machine purely so you
can try wardenIQ with zero cloud accounts. It's **not** the recommended deployment —
see [Cloud / lightweight deployment](#cloud--lightweight-deployment-recommended-for-real-use)
above for that. Two ways to run this local trial:

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

**On Windows**, no WSL or Git Bash needed — just Docker Desktop. Clone the repo, then
run this one line — it works the same whether typed into **Command Prompt or
PowerShell** (it explicitly invokes `powershell.exe`, so it doesn't matter which
shell you're already in, and the execution policy is bypassed for this one run only):

```bat
git clone https://github.com/adlerqa/wardeniq.git wardenIQ && cd wardenIQ
copy .env.example .env
powershell -ExecutionPolicy Bypass -File run.ps1
```

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

### Using the bundled Ollama (local models)

In the bundled stack there's **nothing to configure for AI**. An Ollama container runs
alongside the app, and a one-shot `ollama-pull` service downloads the two default models
on first boot — `qwen2.5:3b` (generation) and `nomic-embed-text` (embeddings). The app
is already pointed at it (`OLLAMA_URL_BUNDLED=http://ollama:11434`), so once the pull
finishes, generation and embeddings just work.

- **Check it's ready.** From the same folder as your Compose files:
  ```bash
  docker compose exec ollama ollama list        # lists installed models
  docker logs -f warden-ollama-pull             # watch the first-boot download
  ```
  Generation will error until that first pull completes.
- **Use a bigger or different model.** Pull it into the same container, then tell
  wardenIQ to use it:
  ```bash
  docker compose exec ollama ollama pull qwen2.5:7b
  ```
  Then either pick it under **Configuration → LLM** (or **Embeddings**) in the app, or
  set `GEN_MODEL=qwen2.5:7b` (/ `EMBED_MODEL=...`) in `.env` and `docker compose up -d`.
  The bundled Ollama is **CPU-only** inside Docker, so larger models are noticeably
  slower — for higher quality use a hosted provider, or a natively-installed Ollama with
  a GPU.
- **Prefer a hosted provider instead?** Set it under **Configuration → LLM** and
  **Configuration → Embeddings**; the bundled Ollama is then simply left unused.

### Signing in the very first time

wardenIQ always requires a login. When SMTP (email delivery) is not yet set up, there's
no email to send a sign-in code to, so the application displays a Username/Password
screen for a single **local admin** account instead of the emailed-code screen.

To sign in the very first time:
1. On the login screen, enter the default administrator credentials:
   - **Username**: `admin`
   - **Password**: `admin123`
2. You'll immediately be asked to **set a new password**. This step is mandatory and
   can't be skipped or closed — `admin123` is a public, well-known default (it's in
   this very README), so wardenIQ won't let it stay active silently. Pick one (8+
   characters, with a letter and a number) and save it; that's what you'll use for
   local sign-in from then on.
3. Once you're in, navigate to **Configuration → Email** and set up your SMTP
   details. Once email delivery is configured, wardenIQ automatically disables
   password login entirely and switches every sign-in (including yours) to the
   standard passwordless email OTP flow — a one-time 6-digit code per login.

Prefer to seed the admin ahead of time? Set `ADMIN_EMAIL=you@company.com` in `.env`.

> **Changed your mind about your password later?** Use **Change password** in the
> profile menu (top-right, next to Sign out) — only shown for the local `admin`
> account; email-based users sign in with a code and have no password to change.

> **Only one admin, and want to disable/hand off that local account?** The Users
> page won't let the sole active admin disable themselves — that would lock
> everyone out of the app. Instead it shows **"Add admin to unlock"**: invite a real
> email address with the Admin role, have them accept the invite and sign in, and
> the local admin's Disable/Delete options unlock automatically once a second
> active admin exists.

---

## Prefer a pre-built image? (skip the local build — recommended)

### Option B — Run the published image, no source needed

wardenIQ publishes a ready-to-run image to Docker Hub:
**[`adlerqa/wardeniq`](https://hub.docker.com/r/adlerqa/wardeniq)**.

```bash
docker pull adlerqa/wardeniq:beta
```

The installer below pulls this same image automatically, plus the small Compose
file and `.env` it needs to run — no clone, no build. It has two variants:

- **Bring-your-own MongoDB (default, recommended for real use)** — pulls only the app
  image. You point it at your own MongoDB (Atlas or self-managed) and either a
  hosted LLM or a host-installed Ollama.
- **`--bundled` (macOS/Linux) / `WARDENIQ_BUNDLED=1` (Windows) — zero-cloud-accounts
  local demo** — additionally ships a 3-node MongoDB replica set + mongot + Ollama
  in the same Compose stack, with the two default models auto-pulled on first boot
  (~2 GB). Slower generation on CPU but nothing to sign up for.

**macOS/Linux:**
```bash
# Bring your own MongoDB (recommended)
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash

# All-in-one bundled demo (adds MongoDB + Ollama)
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash -s -- --bundled
```

**Windows** (Command Prompt or PowerShell — same command either way):
```bat
:: Bring your own MongoDB (recommended)
powershell -c "irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"

:: All-in-one bundled demo (adds MongoDB + Ollama)
powershell -c "$env:WARDENIQ_BUNDLED=1; irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"
```

This is the setup we recommend for client / production use: **you bring the database
and the AI backend**, and wardenIQ runs as a single lightweight container (no bundled
MongoDB or Ollama). There are **two** things to configure before the first start —
a database and an AI backend.

**1 — Database.** In `wardeniq/.env`, point it at your MongoDB (Atlas, or self-managed
with mongot):
```
MONGO_URI=<your MongoDB connection string>
```

**2 — AI backend (generation *and* embeddings).** This flow does **not** bundle Ollama,
so you must give wardenIQ a model backend. wardenIQ needs **both** a generation model
and an embedding model — embeddings power the RAG store, semantic dedup, and PR→feature
mapping, so the app is not usable until one of the options below is in place. Pick one:

- **Hosted provider — recommended for clients.** Nothing to install. Start the app,
  sign in, and under **Configuration → LLM** *and* **Configuration → Embeddings** choose
  a provider (OpenAI, Anthropic, Google Gemini, Mistral, Groq, AWS Bedrock, Voyage, or
  any OpenAI-compatible endpoint) and paste an API key (encrypted at rest). Leave the
  Ollama fields alone.
- **Your own Ollama — fully local, no accounts.** Install [Ollama](https://ollama.com)
  on the host machine and pull both models:
  ```bash
  ollama pull qwen2.5:3b        # generation
  ollama pull nomic-embed-text  # embeddings
  ```
  The container reaches it automatically at `http://host.docker.internal:11434` (the
  installer sets this for you). Verify with `ollama list`.

`.env` is a plain text file that stays on your machine (or server), not inside the
image — edit it any time. Changes take effect after a restart (see
[Configuration](#configuration-env) for the full list of settings).

### Setting your `.env` values — the ways to do it

`.env` is a plain-text `KEY=value` file the app reads at startup. You have several
options for getting your own values into it; **pre-seeding it before the installer
runs is recommended** because everything is correct on first boot with no restart.

#### 1) Pre-seed `.env` before the installer runs (recommended)

The installer only copies `.env.example → .env` when `.env` doesn't already exist —
so if you drop your own `.env` into the target folder first, the installer leaves it
alone and starts the stack with your values. You only need to include the variables
you want to override from defaults; everything else falls back to `.env.example` /
Compose defaults. `APP_SECRET` is auto-generated on first boot, so don't set it
by hand.

**macOS/Linux (bundled — zero cloud accounts):**
```bash
mkdir wardeniq
cat > wardeniq/.env <<'EOF'
ADMIN_EMAIL=you@company.com
GEN_MODEL=qwen2.5:7b
EMBED_MODEL=nomic-embed-text
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash -s -- --bundled
```

**macOS/Linux (bring your own MongoDB):**
```bash
mkdir wardeniq
cat > wardeniq/.env <<'EOF'
MONGO_URI=mongodb+srv://USER:PASS@your-cluster.mongodb.net/?retryWrites=true&w=majority
ADMIN_EMAIL=you@company.com
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash
```

The single-quoted heredoc (`<<'EOF'`) is important — it stops the shell from expanding
`$` inside your values, which matters if a token or connection string contains `$` or
other shell metacharacters.

**Windows (bundled):**
```powershell
New-Item -ItemType Directory -Force wardeniq | Out-Null
@'
ADMIN_EMAIL=you@company.com
GEN_MODEL=qwen2.5:7b
EMBED_MODEL=nomic-embed-text
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
'@ | Set-Content -Path wardeniq\.env -Encoding ASCII
powershell -c "$env:WARDENIQ_BUNDLED=1; irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"
```

**Windows (bring your own MongoDB):**
```powershell
New-Item -ItemType Directory -Force wardeniq | Out-Null
@'
MONGO_URI=mongodb+srv://USER:PASS@your-cluster.mongodb.net/?retryWrites=true&w=majority
ADMIN_EMAIL=you@company.com
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
'@ | Set-Content -Path wardeniq\.env -Encoding ASCII
powershell -c "irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"
```

The single-quoted here-string (`@'…'@`) is important — it stops PowerShell from
expanding `$env:` or other `$` references inside your values. `-Encoding ASCII`
avoids the UTF-8 BOM that some tools mis-parse.

> **Watch out — don't pre-seed inside a `cd`'d folder.** The installer itself does
> `mkdir wardeniq && cd wardeniq`, so if you `cd wardeniq` first and then write
> `.env` there, the installer will create a nested `wardeniq/wardeniq/` and ignore
> your file. Either pre-seed into the subdir *from outside* (as shown above), or
> `cd wardeniq && cat > .env <<'EOF' ... EOF` and add `WARDENIQ_DIR=.` (macOS/Linux)
> before `bash` in the pipe.

#### 2) Edit `.env` after install, then restart

Skip pre-seeding, run the installer, then open `wardeniq/.env` in your editor and
apply with:

```bash
cd wardeniq
docker compose up -d --no-build                            # bundled
# or:
docker compose -f docker-compose.app.yml up -d --no-build  # bring-your-own-Mongo
```

Best when you already ran the installer and now want to change one or two values.

#### 3) Multi-environment file (`--env-file`)

Keep `.env.dev`, `.env.staging`, `.env.prod` side-by-side and select per deploy:

```bash
docker compose --env-file .env.prod up -d
```

Same file format — Compose uses whichever file you point it at.

#### 4) Shell environment variables

For CI or one-off overrides, export variables in your shell first. Compose expands
`${VAR}` from the shell before falling back to `.env`:

```bash
export GEN_MODEL=qwen2.5:7b
docker compose up -d
```

On Windows PowerShell: `$env:GEN_MODEL = "qwen2.5:7b"; docker compose up -d`.

#### 5) Compose override file

Create `docker-compose.override.yml` next to the shipped Compose files with a
per-service `environment:` block — Compose auto-merges it on every `docker compose
up -d`, so you can layer per-environment settings without editing the shipped files
or `.env`.

#### 6) Docker/Kubernetes secrets

For production, don't put sensitive values (`APP_SECRET`, `GITHUB_TOKEN`, SMTP
credentials, API keys) in `.env` at all — mount them as Docker/K8s secrets, or
fetch them from a secret manager (Vault, AWS Secrets Manager, GCP Secret Manager)
at container start. `.env` is unencrypted plaintext on disk; secret managers give
you rotation and audit.

Start it:
```bash
cd wardeniq
docker compose -f docker-compose.app.yml up -d --no-build
```

The installer already pulled `adlerqa/wardeniq:beta`, so this starts from the
published image. The `--no-build` flag is a safety net: `docker-compose.app.yml`
also carries a `build:` section for contributors who have the source checked out,
and `--no-build` guarantees a no-source install never tries to build from a `./app`
directory that isn't there (it would fail with a clear error instead).

Open **http://localhost:8001** and sign in. `APP_SECRET` is generated automatically.

> **Using the bundled variant.** With `--bundled` (macOS/Linux) or
> `WARDENIQ_BUNDLED=1` (Windows) the installer starts the full stack for you — no
> separate `docker compose up -d` needed. First launch pulls a few GB (image +
> models) and takes a few minutes. See [Using the bundled
> Ollama](#using-the-bundled-ollama-local-models) for checking status and swapping
> models; see [Cloud / lightweight
> deployment](#cloud--lightweight-deployment-recommended-for-real-use) for why the
> bring-your-own path is preferred for real deployments.

**Day to day:** `docker compose -f docker-compose.app.yml up -d --no-build` / `down` /
`pull` to start, stop, or update — from that same `wardeniq` folder. (`pull` refreshes
the published image; keep `--no-build` on `up` since this folder has no source to build.)

> **Maintainers:** built and pushed by `.github/workflows/docker-publish.yml`
> (`linux/amd64` + `linux/arm64`) — trigger manually or push a `vX.Y.Z` tag. Needs
> `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo secrets. Script source:
> [`install.sh`](install.sh) / [`install.ps1`](install.ps1).

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

The default provider is **Ollama** (`qwen2.5:3b` for generation, `nomic-embed-text`
for embeddings). Ollama is included and pre-pulled only in the **bundled** stack; in
the published-image (bring-your-own) flow it points at an Ollama you run yourself on
the host — or switch to a hosted provider, below. Either way, remember to set **both**
generation and embeddings. Under **Configuration → LLM** you can switch
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
| `ADMIN_PASSWORD` | _(empty)_ | Bootstrap password for the local `admin` login (the installer prompts for it). Set ⇒ replaces the `admin123` default. Blank ⇒ `admin123` with forced change on first login |
| `COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `SESSION_TTL_SECONDS` / `OTP_TTL_SECONDS` | `604800` / `600` | Session lifetime (7 d) / code lifetime (10 min) |
| `MONGO_URI` | _(empty = bundled DB)_ | Bring your own MongoDB; also settable in-app |
| `MONGO_IMAGE` / `MONGOT_IMAGE` | pinned | Override the bundled MongoDB / mongot images |
| `APP_IMAGE` | _(empty = build from source)_ | Point at a published image instead of building |

SMTP (for sign-in emails) is set under **Configuration → Email** (stored encrypted, takes
precedence) or via `SMTP_*` vars in `.env`. Until SMTP exists, the first admin's code is
printed to the server log (see [Signing in](#signing-in-the-very-first-time)). AWS Bedrock
credentials are **not** `.env` vars — set them under Configuration → LLM/Embeddings.

`MONGO_URI` can also be changed from **Configuration → Database** in the UI, which
writes it back into `.env` for you (restart applies it) and offers a **"Move my data
to another database"** option to copy your data over safely before switching.

---

## Troubleshooting

- **I can't sign in / SMTP is not configured.** If email delivery is not yet configured, sign in with username `admin` and the password you set during install (`ADMIN_PASSWORD`). If you didn't set one, the bootstrap default `admin123` applies and you'll be forced to change it on first login. Once logged in, configure SMTP in **Configuration → Email**.
- **I'm the only admin and "Disable" doesn't show up on my own account.** That's by
  design — the sole active admin can't disable themselves (see
  [Signing in](#signing-in-the-very-first-time)). Use "Add admin to unlock" to invite
  a second admin first.
- **First start is slow or the page won't load.** Give it a few minutes — the replica set
  and model downloads take time on first run. Check progress with
  `docker compose logs -f` or the captured logs in `./logs/`.
- **Mind Map result is empty for a feature.** Usually the wrong **branch** is selected for
  a repo, or the logic lives only in test files (excluded on purpose). The Mind Map shows
  exactly which files it read, so you can tell which.
- **Test generation is slow or shallow.** The default local model is CPU-friendly, not
  powerful. Switch to a bigger local model or a hosted provider under Configuration → LLM.
- **Fresh start / wipe everything:** `./run.sh --reset` (deletes the data volumes) —
  on Windows, `powershell -ExecutionPolicy Bypass -File run.ps1 -Reset`.

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
install.sh / install.ps1  one-command setup for the published image (macOS/Linux / Windows)
run.sh          one-command launch + log capture (macOS/Linux)
collect-logs.sh dump all container logs/health into ./logs/ (macOS/Linux)
run.ps1         same as run.sh, for Windows
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
