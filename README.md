# wardenIQ — Test Intelligence Platform

[![CI](https://github.com/adlerqa/wardeniq/actions/workflows/ci.yml/badge.svg)](https://github.com/adlerqa/wardeniq/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **QC for AI-built software.** Point wardenIQ at your requirement docs and your
> code. It writes a structured test suite from the docs, then continuously checks
> your code against those tests — so you always know **what's covered,
> what's automated, and what's at risk.**

**`v0.2.3`** — early, evolving, open. Licensed **MIT**: fork it, run it
on-prem, use it commercially, no strings.

![Upload a PRD, wardenIQ generates a grounded test suite](docs/assets/demo.gif)

<sub>Create a project, attach a PRD, and wardenIQ generates a typed test suite from it — functional, E2E, API and non-functional.</sub>

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
that's the whole footprint (recommended — see
[Installation & deployment](docs/installation.md)). A fully
local, all-in-one demo mode (bundled MongoDB + local model, no cloud accounts needed)
is also available if you just want to try it out first — see
[Quick start](#quick-start-about-5-minutes) below.

---

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

A dashboard rolls coverage and automation up across every project:

![wardenIQ dashboard — coverage and automation rollups across projects](docs/assets/dashboard.png)

Generated cases land in a reviewable, filterable library — each one typed, prioritised, and
built from atomic steps you can edit once and reuse everywhere:

![Test Cases — generated suite with type, step count and execution status](docs/assets/test-cases.png)

---

## Quick start (about 5 minutes)

The fastest way to see it work: a fully local trial with a bundled MongoDB and a small
local model — no cloud accounts, no API keys.

### Clone and build from source

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

> **No PRD handy?** Upload [`examples/sample-prd.md`](examples/sample-prd.md) when
> you create your first feature — a small password-reset PRD detailed enough to
> generate Functional, E2E, API, and Non-functional test cases, so you can see the
> whole flow work without writing a requirement document of your own first.

---

Bring your own model — Ollama, OpenAI, Anthropic, Gemini, Mistral, Groq or Bedrock, all
configured in the same place:

![Configuration — LLM provider, model and embedding settings](docs/assets/configuration.png)

> **Running this for real?** Don't use the bundled stack. Point wardenIQ at a cloud
> MongoDB and a hosted LLM and the only thing you run is the app container itself.
> See **[Installation & deployment](docs/installation.md)**.

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

---

## Documentation

| Guide | What's in it |
|---|---|
| **[Installation & deployment](docs/installation.md)** | Requirements, cloud deployment (recommended), the local trial, running the pre-built image |
| **[Configuration](docs/configuration.md)** | Every `.env` value, bringing your own LLM, roles & access, accuracy knobs |
| **[Your first run](docs/getting-started.md)** | Guided tour — project, repos, first feature, generation, Mind Map |
| **[Architecture & internals](docs/architecture.md)** | How Mind Map reads your codebase, measuring accuracy, HA & production, project layout |
| **[Jira integration](docs/jira.md)** | Trigger feature creation and generation from Jira issues |
| **[Troubleshooting](docs/troubleshooting.md)** | Common problems and what they mean |

---

## Contributing

wardenIQ is MIT-licensed and contributions are genuinely welcome.

- **New here?** Start with the [good first issues](https://github.com/adlerqa/wardeniq/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) — each one has context, acceptance criteria and pointers to the relevant files.
- **Read** [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow. The whole stack runs in Docker Compose; you don't need Python, Node or MongoDB installed locally.
- **Found a security issue?** Don't open a public issue — see [SECURITY.md](SECURITY.md).

---

## Status & roadmap

Beta. Known rough edges: generation speed/quality scale with the local model; GitHub
analysis needs a PAT for private repos; LLM mapping is best with descriptive docs.
Contributions welcome.

See [ROADMAP.md](ROADMAP.md) for what's next and where you can help.

## License

[MIT](LICENSE) — free for commercial and non-commercial use.

> wardenIQ builds on MongoDB Community Server, mongot, and Ollama, each under its own
> license. wardenIQ does not redistribute those images; Compose pulls them at runtime.
