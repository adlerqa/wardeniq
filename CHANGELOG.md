# Changelog

## Unreleased

### Security
- **Stronger encryption-key derivation for secrets at rest.** `app/crypto.py` now
  derives the Fernet key from `ENCRYPTION_KEY`/`APP_SECRET` with PBKDF2-HMAC-SHA256
  (200k iterations, fixed application salt) instead of a single unsalted SHA-256.
  Decryption uses a `MultiFernet` that falls back to the legacy SHA-256 key, so
  secrets stored by older versions keep decrypting; anything re-saved is written
  with the strong key. No data migration or re-entry of tokens is required.
- **`.env` writes are hardened against newline injection.** `_write_env_var`
  (`app/main.py`) now rejects any key/value containing CR, LF, or NUL, closing a
  path where an admin-supplied value (e.g. the MongoDB URI via `/api/db-config`
  or `/api/db-migrate`) could smuggle additional `KEY=value` lines into `.env`.
- **SSRF DNS-rebinding (TOCTOU) closed in the document link-follower.**
  `app/weblinks.py` now resolves each URL's host once, validates every resolved
  address is public, and connects to that pinned IP literal for the actual fetch
  (preserving the `Host` header and, for HTTPS, SNI/cert verification against the
  real hostname). Previously the safety check and the fetch resolved DNS
  independently, so a low-TTL attacker domain could pass the check with a public
  IP and then be fetched at an internal IP.
- **Malformed Mongo ids now return HTTP 400 instead of 500.** A single
  `bson.errors.InvalidId` exception handler (`app/main.py`) converts invalid id
  path params / body fields into a clean `400 invalid id format` across all
  routes, rather than the previous uncaught 500.
- **Note (accepted risk, no code change):** admin-configurable outbound endpoints
  (`llm_base_url`, `ollama_url`, `jira_base_url`) remain unrestricted by design —
  wardenIQ is single-tenant/on-prem and must be able to target self-hosted
  Ollama, custom LLM endpoints, and on-prem Jira. This is an admin-only,
  admin-trusted capability; egress allowlisting would break the product's core
  use case and is left to the operator's network policy.

### Changed
- **Installs now track the `latest` image tag so `docker compose pull` delivers new
  releases.** The installer previously pinned `adlerqa/wardeniq:beta`, but the publish
  workflow only updates `:beta` on a manual run — a version release (`vX.Y.Z`) publishes
  `:X.Y.Z` and `:latest`, so `:beta` users never got updates via `pull`. `install.sh` /
  `install.ps1` now default `WARDENIQ_TAG=latest`; existing `:beta` installs can move to
  the release channel by setting `APP_IMAGE=adlerqa/wardeniq:latest` in `.env` once. The
  README's quick-start now shows one install command per OS (the installer prompts for
  bundled vs bring-your-own, or takes `WARDENIQ_MODE`) instead of two, and a new
  "Updating to a new release" section documents the pull + recreate flow (no re-install).

### Fixed
- **Docs: the bring-your-own-MongoDB pre-seed examples piped the installer without a
  mode, which now defaults to the bundled stack and ignores `MONGO_URI`.** Updated those
  examples to pass `WARDENIQ_MODE=byo` (macOS/Linux) / `$env:WARDENIQ_MODE='byo'`
  (Windows) so a piped bring-your-own install actually uses the supplied database.
- **`install.ps1` could misreport "Docker daemon isn't running" when Docker was
  actually fine, then crash outright once that was "fixed."** The pre-flight
  check wrapped `docker info` in `try/catch`. Under this script's
  `$ErrorActionPreference = "Stop"`, any stderr output from a native command —
  even benign `WARNING:` lines `docker info` prints on success (blkio throttle
  support, cgroup v1 deprecation, etc.) — becomes a terminating error. This is
  general PowerShell native-command behavior, not a PS7-only
  `$PSNativeCommandUseErrorActionPreference` thing (reproduced on Windows
  PowerShell 5.1). First attempt removed the `try/catch` and checked
  `$LASTEXITCODE` instead, but that alone doesn't help — the stderr line still
  throws before the `$LASTEXITCODE` line is ever reached, so it just turned a
  misleading "daemon isn't running" message into an unhandled
  `NativeCommandError` crash, confirmed live on the same Windows machine.
  Fixed properly with a `RunNative` helper that temporarily sets
  `$ErrorActionPreference = "SilentlyContinue"` around each native `docker`/
  `docker compose` call (restoring it afterward) so stderr output no longer
  terminates the script, then checks `$LASTEXITCODE` for the real result.
  Applied to the pre-flight `docker compose version`/`docker info` checks and,
  proactively, to every other unguarded native call later in the script
  (`docker compose down`, `docker pull`, `docker compose pull`,
  `docker compose up`) since they were equally exposed and just hadn't been
  hit yet.

### Fixed
- **Usage & Cost mispriced every provider because the default price table was stale
  and its keys didn't match the models the UI actually offers.** Most visibly,
  `claude-opus-4-8` used the old Opus rate of $15/$75 per 1M tokens, so a job billed
  $2.42 by Anthropic showed as ~$7 in wardenIQ. `usage.py` DEFAULT_PRICES is now keyed
  to the exact model IDs in the Settings dropdown (`PREDEFINED_MODELS`) with rates
  verified from each provider's own pricing page (2026-07-22):
  - **Anthropic** — Opus 4.5–4.8 $5/$25, Haiku 4.5 $1/$5, Sonnet 5 $2/$10 (intro
    through 2026-08-31, then $3/$15), Sonnet 4.5/4.6 $3/$15, plus Fable 5, Mythos 5,
    Haiku 3.5, and legacy Opus 4.1.
  - **Google Gemini** — 2.5 Pro $1.25/$10, 2.5 Flash $0.30/$2.50, 2.5 Flash-Lite &
    2.0 Flash $0.10/$0.40, 3 Flash preview $0.50/$3, 3 Pro preview $2/$12.
  - **Mistral** — Large $0.50/$1.50, Medium $1.50/$7.50, Small $0.15/$0.60,
    Ministral 8B & Nemo $0.15/$0.15, Codestral $0.30/$0.90.
  - **Groq** — Llama 3.3 70B $0.59/$0.79, Llama 3.1 8B $0.05/$0.08 (older
    llama3/gemma2/mixtral kept at last-known legacy rates).
  - **OpenAI** — kept at established list prices (gpt-4o $2.50/$10, gpt-4o-mini
    $0.15/$0.60, gpt-4.1 $2/$8, gpt-4.1-mini $0.40/$1.60, gpt-5 $1.25/$10, gpt-5-mini
    $0.25/$2); these models are legacy on OpenAI's current page, so re-verify when the
    dropdown is refreshed.
  Family fallbacks were realigned to match. Token *counts* were already correct — the
  small delta vs a console is free local Ollama embedding tokens.
- **AWS Bedrock usage was silently priced at $0 for many model ids.** `price_for`
  treated any id containing a colon as a free local Ollama tag, but Bedrock version
  ids end in `-v1:0`, so Bedrock calls whose id didn't happen to substring-match a
  price key (e.g. `anthropic.claude-sonnet-4-20250514-v1:0`,
  `us.anthropic.claude-3-5-haiku-20241022-v1:0`) resolved to $0. The free-tag rule is
  now skipped for ids carrying a hosted-provider marker (`anthropic.`, `amazon.`,
  `arn:`, …), so Bedrock Claude ids fall through to the Claude family price
  (opus → $5/$25, sonnet → $3/$15, haiku → $1/$5); local Ollama tags stay free. Prompt-cache and
  Batch-API discounts are still not modelled (wardenIQ makes uncached, non-batch
  calls, so base rates match). Any model can still be overridden in Configuration →
  LLM pricing; when new models are added to the dropdown, add their rates here too.

### Added
- **Repo "kind" is now selectable everywhere and includes a dedicated `test`
  badge.** The kind classification (a display badge, independent of the app/test
  `repo_type` that governs webhooks) gained a `test` value and dropped `other` from
  the UI (canonical set is now `BE | FE | test | infra`; `other` is retained only as
  a legacy value so pre-existing repos still render). The create-project wizard now
  shows a per-repo **Kind** dropdown beside the display-name box (defaulting to
  Backend for app repos and Test for test repos) instead of hard-coding every repo to
  `BE`/`other`; the project-settings **Connect repository** panel's Kind dropdown adds
  Test in place of Other. Badges render via a shared label map (`test`→"Test",
  `infra`→"Infra", legacy `other`→"Other") in the repositories list, Change impact
  analysis, and the Implementation coverage map / Mind Map. Backend `POST /repos`
  normalizes incoming kinds case-insensitively (`_normalize_repo_kind`), and a
  one-time `store._converge_repo_kinds()` promotes existing test-type repos that were
  defaulted to `other` up to `test` so their badge reflects the new value without
  manual re-tagging. In the **Mind Map** and **Change impact analysis** repo pickers,
  `infra`-kind repos are now listed but left **unchecked by default** (infrastructure
  code, so you opt it in rather than out); backend, frontend, and test-kind repos stay
  pre-selected. Test-*type* repos remain excluded from these views entirely, as before.
- **The GitHub poll interval is now configurable in the UI (Configuration → Sync
  & polling) and defaults to 30 minutes.** Previously the poller cadence was fixed
  at import from `POLL_INTERVAL_SECONDS` (default 120s) and could only be changed by
  editing `.env` and restarting. Now `current_poll_interval()` resolves it live on
  every poll loop with precedence: the frontend-saved `settings.poll_interval_s`
  wins, else `POLL_INTERVAL_SECONDS` in `.env` (seed default), else a built-in
  1800s (30 min). Saved values are floored at `MIN_POLL_INTERVAL` (30s) so a stray
  small value can't hammer the GitHub API, and a change applies on the next loop
  with no restart. `.env`/`.env.example` defaults bumped 120 → 1800. Exposed via
  `GET /api/settings` (`poll_interval_s`, `poll_interval_s_effective`,
  `poll_interval_min_s`), settable via `PUT /api/settings` (`poll_interval_s`), and
  reflected in `GET /api/sync/status`. GitLab (webhook-driven) is unaffected.
  Saving from the UI also mirrors the value into `.env`
  (`POLL_INTERVAL_SECONDS`, via the existing `_write_env_var` helper used for
  `MONGO_URI`/`APP_SECRET`) so the config file never diverges from what's running;
  this is best-effort, so when `.env` isn't writable (not bind-mounted) the value
  still applies live from the `settings` doc and the UI says so.
- **Installer validates the bring-your-own `MONGO_URI` instead of accepting
  anything.** Previously the "Bring your own DB" prompt in `install.sh`/`install.ps1`
  saved whatever was typed verbatim — a typo or placeholder (e.g. pasting a random
  word) would install successfully and only surface as a broken, half-rendered UI
  once the app tried to actually connect. Now, interactively:
  - The value must at least look like a Mongo connection string
    (`mongodb://` or `mongodb+srv://`), re-prompting otherwise.
  - If `mongosh` is available on the machine running the installer, it does a quick
    (~10s capped) live `ping` against the URI and reports a clear connection error
    if it fails, offering to re-enter or continue anyway (network reachability from
    the installer's machine can legitimately differ from the container's, e.g. an
    Atlas IP allow-list, so this never hard-blocks).
  - If `mongosh` isn't available, the format check still applies and the live check
    is silently skipped (not treated as a failure).
  Follow-up fix: the live-check call site was a bare command under install.sh's
  `set -e`, so a genuine connection failure (the exact case this feature exists to
  catch) made the installer exit silently right after "checking the connection..."
  with no error message at all, instead of reporting it. Guarded with `|| rc=$?` so
  a real failure is reported and offers "use it anyway?" instead of killing the
  script. Verified directly: the old pattern provably dies silently under `set -e`
  on a failing check; the fixed one reaches the warning every time.
  Non-interactive runs (`WARDENIQ_MONGO_URI` / `-MongoUri`) only get the format
  check, with a clear warning if it fails, since there's no one to re-prompt.

### Changed
- **README install: `.env` configuration options documented for both platforms.** The
  published-image install section now shows the `--bundled` (macOS/Linux) and
  `WARDENIQ_BUNDLED=1` (Windows) variants directly next to the base install command
  so both paths are visible upfront (previously `--bundled` was only mentioned in a
  late callout). Added a new **"Setting your `.env` values — the ways to do it"**
  subsection covering six approaches, with pre-seeding `.env` before the installer
  runs as the recommended path — the installer skips overwriting `.env` when one
  already exists, so a heredoc/here-string drop-in works for both bundled and
  bring-your-own-Mongo flows. Also documents the common footgun of `cd wardeniq`
  before pre-seeding (installer's own `mkdir wardeniq && cd wardeniq` nests it) and
  the alternative `WARDENIQ_DIR=.` override. Other approaches listed: post-install
  edit + restart, `--env-file` for multi-env, shell env-var interpolation for CI,
  `docker-compose.override.yml`, and Docker/K8s secrets for production credentials.
  Includes both Bash (`<<'EOF'`) and PowerShell (`@'…'@` + `-Encoding ASCII`)
  examples with notes on why single-quoted heredocs matter (no `$` expansion).

### Fixed
- **`scripts/enable-mongo-auth.sh` could enforce MongoDB auth before the app/root
  users actually existed, breaking the app.** `config/setup-replica-set.sh` created
  its admin users by connecting directly to `mongod1` with no check that it was
  actually the current PRIMARY. On an already-initialized replica set (e.g. re-running
  the script, or right after `mongod-setup` restarts) `mongod1` can briefly be a
  secondary, so every `createUser`/`updateUser` call failed with `not primary` and was
  silently skipped — the script then proceeded to enforce keyfile auth anyway, leaving
  `warden-app` unable to authenticate (`Authentication failed`) with no automatic
  recovery short of a full `--reset`. A re-run then compounded it: once auth was
  enforced, the script's error handling treated any `Unauthorized` response as "user
  already exists," masking that the users were never created. Fixed:
  - `setup-replica-set.sh` now waits for an actual PRIMARY (mongod1 has the highest
    priority and reliably reclaims it) before any user-creation call, on both the
    fresh-init and already-initialized paths.
  - User creation now reports one of `created` / `synced` / `NEEDS_AUTH` / an explicit
    error instead of assuming success; on `NEEDS_AUTH` it retries authenticated as the
    root user (covering legitimate re-runs/rotation) and prints an actionable warning
    if that still fails, rather than silently claiming the user is fine.
  - Follow-up: the retry-as-root call itself could crash the whole script (uncaught
    `set -e` exit, surfacing as a raw Python traceback from the container entrypoint)
    when root doesn't exist yet — e.g. `MONGO_AUTH_ENABLED`/`COMPOSE_FILE` left pinned
    in `.env` from a prior `enable-mongo-auth.sh` run, then `run.sh --reset` wipes the
    data volume but boots mongod straight into keyfile auth with zero users, which
    can't be bootstrapped remotely (the localhost exception doesn't apply across the
    Docker network). Now every such mongosh call is guarded so a hard connection/auth
    failure can't kill the script, the replica-set state check no longer misclassifies
    an auth-required error as "already initialized," and this specific dead-end state
    prints one clear diagnostic (remove `config/keyfile` + the auth entries in `.env`,
    re-run) instead of a stack trace. Verified with a mocked `mongosh` covering the
    normal (auth off), fresh-auth-enabled, and this stuck-state path — all now exit 0
    with actionable output instead of crashing.
- **App-only install no longer points at a non-existent Ollama container.** The
  plain installer (`irm ... | iex` / `curl ... | bash`, no `-Bundled`/`--bundled`)
  downloads only `docker-compose.app.yml` — there is no bundled `ollama` service —
  yet the app still fell back to `OLLAMA_URL_BUNDLED=http://ollama:11434`, so an
  out-of-the-box run failed with a connection error until the user manually changed
  the endpoint or picked a hosted provider. Now:
  - `docker-compose.app.yml` makes `OLLAMA_URL_BUNDLED` interpolable
    (`${OLLAMA_URL_BUNDLED:-http://ollama:11434}`, default unchanged for the bundled
    full stack) and adds a `host.docker.internal:host-gateway` alias so the container
    can reach a natively-run Ollama on Linux too (Docker Desktop already provides it).
  - `install.sh` / `install.ps1` write `OLLAMA_URL_BUNDLED` into `.env` per mode:
    app-only -> `http://host.docker.internal:11434` (your own Ollama); bundled ->
    `http://ollama:11434` (the in-stack container). Re-running the installer re-points
    this line for the selected mode, avoiding stale cross-mode values.
  - `.env.example` notes that `OLLAMA_URL` pins/locks the endpoint and that the
    fallback is installer-managed per mode.
  The bundled Ollama option is unchanged and still pulls models via `ollama-pull`;
  only the app-only default was broken.

### Changed
- **README install made client-ready.** The published-image ("Option B") flow now
  spells out that it bundles neither MongoDB nor Ollama, and adds an explicit
  two-step setup: (1) database via `MONGO_URI`, (2) an AI backend — a hosted provider
  (recommended for clients) *or* your own host Ollama with the exact `ollama pull`
  commands — stressing that **both** a generation and an embedding model are required
  (embeddings drive the RAG store / dedup / PR mapping). The bundled stack is reframed
  as the zero-config evaluation path. The "Bring your own LLM" section now clarifies
  that the pre-pulled Ollama exists only in the bundled stack. Added a **"Using the
  bundled Ollama"** section covering how to confirm the models finished pulling
  (`ollama list` / `warden-ollama-pull` logs), pull and switch to a bigger model, and
  the CPU-only performance caveat.
- **README "Option B" simplified.** Had grown to ~125 lines across a 5-step numbered
  walkthrough, three separate Windows command blocks, a "day to day" aside, a
  collapsible manual-steps fallback, and a maintainers note — too much for what's a
  one-command flow. Condensed to: one command per OS, the `MONGO_URI` edit, the start
  command, a single callout for the `--bundled`/`$env:WARDENIQ_BUNDLED` local-demo
  variant, and a one-line day-to-day/maintainers note. All the same facts (image
  name, `MONGO_URI` requirement, auto-generated `APP_SECRET`, multi-arch build,
  required secrets) still present, just stated once. The collapsible "what does
  install.sh do" walkthrough was replaced with direct links to the script source
  instead of duplicating its contents in prose. No functional changes.

### Fixed
- **`install.ps1` failed to parse on real Windows machines** with `Missing closing
  ')' in expression` / `Missing closing '}' in statement block`, even though the
  script was syntactically valid. Cause: the file contained em dashes (`—`) with no
  byte-order mark, and Windows PowerShell 5.1 (the default `powershell.exe` on most
  Windows installs) doesn't reliably auto-detect UTF-8 in a BOM-less `.ps1` file —
  it falls back to the system codepage, misreading the UTF-8 em-dash bytes and
  corrupting the string literals around them enough to break the tokenizer. A
  download via `curl`/`Invoke-WebRequest` doesn't add a BOM either, so this hit every
  real user, not just an edge case. Fixed by stripping all non-ASCII characters from
  `install.ps1`, `run.ps1`, and `collect-logs.ps1` (em dashes to `-`, documented at
  the top of each file so it isn't reintroduced) — sidesteps the encoding question
  entirely rather than depending on a BOM surviving every possible transfer path.

### Added
- **Real password change for the local admin account, and safer admin hand-off.**
  The local `admin` / `admin123` bootstrap login previously had no way to actually
  change its password — `login-password` compared against the literal string
  `"admin123"` forever, so a "changed" password never persisted. Added a
  `password_hash` field on the user doc (PBKDF2-HMAC-SHA256, stdlib-only, per-user
  salt; see `auth.hash_password`/`password_matches`) plus a new
  `POST /api/auth/change-password` endpoint; `login-password` now checks the stored
  hash once one exists, falling back to the shipped default only until it's set.
  The UI now shows a mandatory "change your password" prompt on first local-admin
  login (only relevant while SMTP isn't configured, i.e. while password login is
  active), and a "Change password" action in the profile menu afterwards.
  Separately, the Users page no longer shows "Disable" on your own row when you're
  the only active admin (backend already refused this via
  `count_active_admins() <= 1`, but the button was still shown, so clicking it just
  produced a raw error) — it's replaced with an "Add another admin to unlock"
  action that explains why and jumps to the existing invite form (preset to the
  Admin role). Once a second admin accepts and signs in, the Disable option
  reappears normally. No new collections; existing users are unaffected (no
  `password_hash` field = OTP-only / still on the default local password).
  Documented in the README under "Signing in the very first time" and
  Troubleshooting.
- **Shorter Windows one-liner using `irm | iex`.** The documented Windows command was
  a two-step download-then-run (`iwr ... -OutFile install.ps1; .\install.ps1`).
  Switched to PowerShell's `irm <url> | iex` idiom — the direct equivalent of
  `curl | bash` — which downloads and executes in one step, no intermediate file.
  Since a piped `iex` can't bind a `-Bundled` switch parameter the way running a
  saved `.ps1` file can, `install.ps1`'s `param()` block now also reads
  `$env:WARDENIQ_BUNDLED` as a fallback default, so the bundled variant is
  `$env:WARDENIQ_BUNDLED=1; irm ... | iex` instead. The old
  download-then-run-as-a-file form still works unchanged for anyone who'd rather
  inspect the script before running it, or re-run it with different flags.
- **Windows install commands now work from Command Prompt without a separate `.bat`
  file.** `install.ps1`/`run.ps1` need PowerShell; a Command Prompt user typing
  `iwr ...` or `.\install.ps1` gets "not recognized" errors, and many Windows users
  default to `cmd.exe` without knowing PowerShell exists or how to switch. First
  attempt added `install.bat`/`run.bat` wrapper files, but that meant three installer
  scripts to keep in sync (`.sh`/`.ps1`/`.bat`) for what's really only two platforms.
  Replaced with a single documented command per Windows path:
  `powershell -ExecutionPolicy Bypass -File run.ps1` (build from source) and
  `powershell -Command "iwr .../install.ps1 -OutFile install.ps1; .\install.ps1"`
  (published image) — both work unchanged whether typed into Command Prompt or
  PowerShell, since they explicitly invoke `powershell.exe` rather than relying on
  the calling shell to understand PowerShell syntax. No extra files to maintain.
  `install.bat`/`run.bat` removed.
- **Multi-arch Docker Hub image (`linux/amd64` + `linux/arm64`).** The published
  `adlerqa/wardeniq` image was initially built by `docker-publish.yml` on GitHub's
  standard `ubuntu-latest` runner, which only produces `linux/amd64` — fine for most
  cloud VMs, but not native on ARM hosts (Apple Silicon without emulation, AWS
  Graviton, Raspberry Pi). Added a `docker/setup-qemu-action@v3` step and
  `platforms: linux/amd64,linux/arm64` to the existing `docker/build-push-action@v6`
  step, so both architectures are built and pushed under the same tag in one run;
  Docker automatically pulls the right one for the host. No Dockerfile changes needed
  — both base images (`node:20-slim`, `python:3.11-slim`) already publish official
  `arm64` variants. First build under QEMU emulation will be noticeably slower than a
  native `amd64`-only build; subsequent builds benefit from the existing `type=gha`
  layer cache.
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
