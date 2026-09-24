# Configuration

Environment variables, model providers, roles and the accuracy knobs.

---

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
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | WARDENIQ_MODE=byo bash
```

`WARDENIQ_MODE=byo` is required here: a piped install can't show the mode prompt and
otherwise defaults to the bundled stack, ignoring your `MONGO_URI`. The single-quoted
heredoc (`<<'EOF'`) is important — it stops the shell from expanding
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
powershell -c "$env:WARDENIQ_MODE='byo'; irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"
```

`$env:WARDENIQ_MODE='byo'` is required here: a piped install can't show the mode prompt
and otherwise defaults to the bundled stack, ignoring your `MONGO_URI`. The single-quoted
here-string (`@'…'@`) is important — it stops PowerShell from
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
apply with the command for **your install mode** (from the `wardeniq` folder):

```bash
cd wardeniq
docker compose -f docker-compose.app.yml up -d --no-build   # bring-your-own MongoDB
docker compose up -d --no-build                             # bundled all-in-one
```

Best when you already ran the installer and now want to change one or two values. To
*also* pull a newer image at the same time, add `--pull always` — see
[Updating to a new release](#updating-to-a-new-release).

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

The installer already pulled `adlerqa/wardeniq:latest`, so this starts from the
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

**Day to day:** `docker compose -f docker-compose.app.yml up -d --no-build` / `down` to
start or stop — from that same `wardeniq` folder. (Keep `--no-build` on `up` since this
folder has no source to build.)

#### Updating to a new release

You **don't** re-run the installer. From the `wardeniq` folder, run a single command — your
normal start command with `--pull always` added, which fetches the newest image and
recreates the container in one step:

```bash
# bring-your-own MongoDB
docker compose -f docker-compose.app.yml up -d --no-build --pull always

# bundled all-in-one stack
docker compose up -d --no-build --pull always
```

`--pull always` grabs the newest image for the tag pinned in `.env` (`APP_IMAGE`, default
`adlerqa/wardeniq:latest`) and `up -d` recreates only the app container — your database and
data are untouched. This works because `latest` is a **moving tag** that every release
(`vX.Y.Z`) overwrites, so the command always gets the newest code — no `.env` edit, no
re-install. Prune old layers with `docker image prune -f`. To **pin** a specific build
instead, set `APP_IMAGE=adlerqa/wardeniq:1.2.0` in `.env`, then run the same command.

> Installs from before this change are pinned to `:beta` in their `.env`; switch them to
> the release channel by setting `APP_IMAGE=adlerqa/wardeniq:latest` once, then pull.

> **Maintainers:** built and pushed by `.github/workflows/docker-publish.yml`
> (`linux/amd64` + `linux/arm64`). Pushing a `vX.Y.Z` git tag publishes both
> `adlerqa/wardeniq:X.Y.Z` and `adlerqa/wardeniq:latest` (the channel users track), so a
> version release reaches everyone on `pull`; a manual run publishes a one-off `<tag>`.
> Needs `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo secrets. Script source:
> [`install.sh`](../install.sh) / [`install.ps1`](../install.ps1).

---

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
| `GITLAB_BASE_URL` | `https://gitlab.com` | Point at a self-hosted GitLab instance (e.g. `https://gitlab.example.com`). Repo URLs, the API, and generated blob/commit links all follow this |
| `POLL_INTERVAL_SECONDS` | `1800` | How often watched repos are polled for new PRs/commits (30 min). Seed default only — also settable live in **Configuration → Sync & polling**, which overrides this |
| `WEBHOOK_SECRET` | _(empty)_ | Required only if you expose the Jira/GitHub webhook receiver |
| `GEN_TOTAL` | `16` | Baseline test-case count at "Standard" depth |
| `ADMIN_EMAIL` | _(empty)_ | Seeds the first admin; if blank, the first code-requester becomes admin |
| `ADMIN_PASSWORD` | _(empty)_ | Bootstrap password for the local `admin` login (the installer prompts for it). Set ⇒ replaces the `admin123` default. Blank ⇒ `admin123` with forced change on first login |
| `COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `SESSION_TTL_SECONDS` / `OTP_TTL_SECONDS` | `604800` / `600` | Session lifetime (7 d) / code lifetime (10 min) |
| `MONGO_URI` | _(empty = bundled DB)_ | Bring your own MongoDB; also settable in-app |
| `MONGO_IMAGE` / `MONGOT_IMAGE` | pinned | Override the bundled MongoDB / mongot images. Bundled MongoDB must be **8.1+** because `config/mongod.conf` enables `useGrpcForSearch` for mongot's gRPC transport |
| `APP_IMAGE` | `adlerqa/wardeniq:latest` _(set by the installer; empty = build from source)_ | Which published image tag to run. `latest` tracks every release; pin e.g. `adlerqa/wardeniq:0.2.0` to freeze a version |

### Accuracy & verification knobs

These control how much wardenIQ trusts its own LLM verdicts. Defaults are safe; raise the
strictness when a verdict is going in front of someone who will act on it.

| Var | Default | Purpose |
|---|---|---|
| `COVERAGE_REVIEW_THRESHOLD` | `0.7` | Coverage verdicts at or below this confidence are flagged **needs review** in the result instead of being trusted outright. Raise it to send more borderline verdicts to a human |
| `MINDMAP_SAMPLES` | `1` | How many independent passes the Mind Map reviewer makes per batch. `2`+ keeps a `covered` verdict **only when every pass agrees**, cutting hallucination variance - at N x the tokens |
| `WARDENIQ_REUSE_SIM_API` | `0.35` | Token-similarity floor for reusing an existing **API** test case (applied after method/endpoint/scenario must already match exactly) |
| `WARDENIQ_REUSE_SIM_GENERAL` | `0.65` | Same floor for non-API cases. **Not empirically calibrated** - see the measured trade-off in `tests/eval/dataset.py` (`KNOWN_LIMITATION_PAIRS`) before changing it |
| `NUMPY_FALLBACK_MAX_DOCS` | `20000` | Above this many cases, the in-memory exact-search fallback is skipped when vector search is down. Runs affected by this now carry an explicit `dedup_degraded` warning rather than looking clean |
| `MINDMAP_EXCERPT_PER_CHARS` | `4000` | Characters of a single source chunk shown to the reviewer. Chunks are whole function bodies, so a low value cuts them mid-function — the previous fixed 900 showed only 27% of a typical controller and produced false `uncovered` verdicts on endpoints that demonstrably exist |
| `MINDMAP_EXCERPT_TOTAL_CHARS` | _(derived)_ | Total code budget per review call. Left unset it is derived from the model's real context window, so the prompt cannot overflow. Set it only to override that calculation |
| `MINDMAP_EXCERPT_TOTAL_CHARS_HOSTED` | `60000` | Code budget when a hosted provider is configured (100k+ contexts, so far more source fits than a local model allows) |
| `MINDMAP_REVIEW_MAX_TOKENS` | `2000` | Output tokens reserved for the reviewer's reply. Every token reserved here is one fewer available for source code; the old 4000 crowded out the code it was meant to judge |
| `OLLAMA_MAX_NUM_CTX` | `8192` | Hard ceiling on the context requested from a local Ollama model. Raising it on a machine with spare RAM **automatically widens the code window** (the excerpt budget is derived from it), which is the single biggest lever on Mind Map accuracy for local models |

| `MINDMAP_MAX_WINDOWS` | `0` _(unlimited)_ | Safety valve on the exhaustive sweep. `0` reads the **entire** retrieved corpus, however many windows that takes. Set a number only if you need to bound cost |
| `MINDMAP_BATCH_SIZE` | `10` | Test cases judged per call. Lower it to give each case more of the model's attention |
