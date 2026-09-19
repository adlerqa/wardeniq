# Installation & deployment

All the ways to run wardenIQ — cloud (recommended), local trial, and the pre-built image.
For the five-minute path, see the [README](../README.md).

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
single small VM/ECS/Cloud Run instance running `adlerqa/wardeniq:latest`, with
`MONGO_URI` pointing at Atlas) — nobody running or connecting to the tool needs to
provision a database or a GPU/CPU budget for a local model. See [Prefer a pre-built
image?](#prefer-a-pre-built-image-skip-the-local-build--recommended) below for the
exact commands (no clone needed) — just set `MONGO_URI` and skip the bundled-stack
compose files entirely.

---

---

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

---

## Prefer a pre-built image? (skip the local build — recommended)

### Option B — Run the published image, no source needed

wardenIQ publishes a ready-to-run image to Docker Hub:
**[`adlerqa/wardeniq`](https://hub.docker.com/r/adlerqa/wardeniq)**.

The installer below pulls this image automatically, plus the small Compose
file and `.env` it needs to run — no clone, no build, no separate `docker pull`
step. It has two variants:

- **Bring-your-own MongoDB (default, recommended for real use)** — pulls only the app
  image. You point it at your own MongoDB (Atlas or self-managed) and either a
  hosted LLM or a host-installed Ollama.
- **`--bundled` (macOS/Linux) / `WARDENIQ_BUNDLED=1` (Windows) — zero-cloud-accounts
  local demo** — additionally ships a 3-node MongoDB replica set + mongot + Ollama
  in the same Compose stack, with the two default models auto-pulled on first boot
  (~2 GB). Slower generation on CPU but nothing to sign up for.

One command per OS — the installer picks the mode:

**macOS/Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.sh | bash
```

**Windows** (Command Prompt or PowerShell — same command either way):
```bat
powershell -c "irm https://raw.githubusercontent.com/adlerqa/wardeniq/main/install.ps1 | iex"
```

Run in a terminal, the installer **asks** which mode you want: **bring-your-own MongoDB**
(recommended) or the **all-in-one bundled demo** (adds MongoDB + Ollama). To choose without
the prompt (piped installs / CI, which default to bundled), set the mode up front —
`WARDENIQ_MODE=byo` or `WARDENIQ_MODE=bundled` (macOS/Linux), or `$env:WARDENIQ_BUNDLED=1`
before the Windows command for the bundled demo.

This is the setup we recommend for client / production use: **you bring the database
and the AI backend**, and wardenIQ runs as a single lightweight container (no bundled
MongoDB or Ollama). There are **two** things to configure before the first start —
a database and an AI backend.

**1 — Database.** In `wardeniq/.env`, point it at your MongoDB (Atlas, or self-managed
with mongot):
```
MONGO_URI=<your MongoDB connection string>
```
If you paste this into the installer's interactive prompt instead, it checks the
format (must start with `mongodb://` or `mongodb+srv://`) and, if `mongosh` is
available locally, does a quick live connection test before saving it —
re-prompting on a bad format, and warning (not blocking) on a failed connection,
since your machine's network access can legitimately differ from the container's
(e.g. an Atlas IP allow-list).

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
