# Changelog

## Unreleased

### Added

- **A warning before a long generation on a CPU.** On a machine with no GPU the bundled
  model can take from about 20 minutes to over an hour for a full run, and nothing said so
  until it was under way. The Generate page now shows an amber notice as soon as it opens,
  before any document is added, when the local Ollama model runs on CPU: how long it can
  take, and the ways out (a hosted provider, Ollama on a GPU, or a larger
  `LLM_TIMEOUT_SECONDS` if calls time out). It also says that the bundled Ollama container
  never uses a GPU, on any operating system, so Ollama should run natively to use one. The app asks Ollama's `/api/ps` where the
  loaded model runs (CPU, GPU, or split between them). On a first run nothing is loaded
  yet, so it loads the small embedding model the app uses anyway, which takes well under a
  second, and asks again. It never guesses from the URL, because the "bundled" Ollama URL
  can point at the CPU-only container or at a native Ollama on the host, which is often a
  GPU. When Ollama cannot be reached, the model cannot be loaded or the answer is not
  understood, nothing is claimed, so there is no warning. Hosted providers are unchanged.
  `POST /api/usage/estimate` gains `accelerator` and, when relevant, `warning` for a local
  model. The text is deliberately not a computed number of minutes: the existing token
  estimate covers only part of what a real run produces and would promise a run far
  shorter than people see. The worker concurrency default is unchanged (#249).
- **Configurable LLM timeout.** New `LLM_TIMEOUT_SECONDS` setting replaces the timeout of
  every LLM call (test generation and every other model call) on every provider,
  including AWS Bedrock. Unset, the previous built-in values still apply (180 to 300 s
  for generation, 300 s for Ollama and 120 s for hosted providers elsewhere; Bedrock
  keeps the AWS SDK's 60 s), so existing installs are unchanged. Raise it on
  CPU-only machines, where the bundled model can take several minutes per call and
  passes used to fail on working installs. Documented in `.env.example` and
  `docs/configuration.md` (Part of #130, #138).
- **Coverage report parser (groundwork, not wired into the app yet).** New
  `app/coverage_reports.py` reads lcov, Cobertura, JaCoCo and coverage.py XML reports
  through `parse(path)` and returns one model with per-file line and branch hits, so the
  same project gives the same numbers in every format. Unknown or malformed files raise
  a typed `CoverageParseError` instead of crashing. Sample reports live in
  `tests/fixtures/coverage/`. It is the first building block for the unit-test coverage
  validator agent (#250, #245).

### Changed

- **Clearer notifications.** Toasts now have a warning style for an action that worked
  but not completely. It is used when a user is created but the invitation email could
  not be sent (on invite and on resend), and when a project is created but its access
  token could not be saved or a repository could not be connected. Errors on the user,
  project and settings screens now carry a specific title, such as "Couldn't invite
  user" or "Couldn't save SMTP settings", instead of "Something went wrong". Other
  screens keep the old title for now (#272, #274, #278).
- **Smaller frontend build.** The production frontend build no longer emits a JavaScript
  sourcemap, so the built output drops by about 1.3 MB (2.9 MB to 1.7 MB on disk). The
  JavaScript the browser downloads is unchanged (about 198 kB gzipped). If the
  compatibility runtime cannot be started, the app now shows a "could not initialize"
  panel with a Retry button instead of staying blank (#265).

### Fixed

- **The combined E2E call: copied titles are dropped, its repeated evidence is printed once, and a context
  overflow is reported.** A tester's run on a CPU-only machine (qwen2.5:3b, `examples/sample-prd.md`) kept 16
  cases with only 11 distinct titles. The combined E2E call had written five business tests that were
  word-for-word copies of its own E2E titles (four were kept again as e2e and one as nfr). The copies also
  used the business suite's slots, so the five distinct tests the business fallback wrote next were trimmed
  away. The same call sent 5,117 prompt tokens and wrote 4,250 in an 8,192-token window; Ollama logged
  `truncated = 1`, dropped part of the earlier text, and wardenIQ said nothing. Now: a business test or edge
  case whose title is already an API, E2E or edge test's title is dropped (`copy-of-another-suite` in the job
  result), before the business fallback counts what it has, so the fallback asks for what is really missing,
  and the fallback's own copies are dropped too; the prompt asks for distinct business titles; the three
  retrieved-evidence blocks of that prompt, which shared 10 of their 13 distinct lines, now print each
  passage once (a real prompt went from 5,862 to 4,870 tokens, so about 1,000 more tokens of room for the
  reply); and an Ollama call whose prompt plus reply is larger than its context window is logged and listed
  in the job log and in `context_overflows` in the job result. Measured with the real prompt on a GPU: the
  shortened prompt gave the same kind of output as the original (3 to 6 E2E and 3 to 5 business tests, no
  copied titles, 3 runs against 3). Forcing a context shift with a smaller window cut the business tests to 1
  in all three runs, against 3 to 10 in seven normal runs. Not shown: the copied titles and the 4,250-token
  reply did not occur in these GPU runs (replies were 834 to 1,309 tokens), so the overflow is reported and
  made less likely, but I could not show that it caused the copies. Not changed: a UI test is still kept only
  if its field label appears literally in the documents, which is why most of the UI tests a model writes are
  discarded (22 written, 5 kept in one run) (part of #249).
- **Embedding calls now have a configurable timeout, and a timeout is reported clearly.** A tester on a
  CPU-only machine could not create a feature: the first embedding call took about 4 minutes, but
  every embedding call was cut off after a fixed 120 seconds, and `POST /api/features` answered a
  bare HTTP 500 before any job existed. The docs and the CPU notice both say to raise
  `LLM_TIMEOUT_SECONDS` on a slow machine, and that setting did not reach embeddings, so the advice
  could not have worked. Reproduced with a fake Ollama that answers after 130 seconds: with
  `LLM_TIMEOUT_SECONDS=1800` set the call still failed at 120.0 seconds. Now the limit is
  `EMBED_TIMEOUT_SECONDS` if set, otherwise `LLM_TIMEOUT_SECONDS` if set (so the documented advice
  covers embeddings), otherwise 120 seconds as before. It applies to Ollama, OpenAI-compatible
  providers (OpenAI, Gemini and the like) and Voyage; AWS Bedrock keeps the AWS SDK's own timeout, as
  it does for generation. A call that runs out of time raises an error that names both settings and
  the hosted-provider option, and the API answers it with HTTP 504 and that message instead of a bare
  500; a failed job shows the same text. An invalid value is ignored with a warning that names the
  right variable. In Docker, `docker-compose.app.yml` passes `EMBED_TIMEOUT_SECONDS` to the container
  like `LLM_TIMEOUT_SECONDS` (found by a tester: the app never reads `.env` itself, so a variable the
  compose file does not forward cannot be set there). Trade-offs: a larger limit means a hung embedding endpoint can hold a request for
  that long, and a machine whose embedding call is this slow will still be slow, as this fixes the
  failure, not the speed (part of #249).
- **Assigning a PR to a feature on a private repository no longer saves empty coverage.**
  `POST /api/prs/{pr_id}/assign` fetched the PR's changed files with the instance-wide
  `GITHUB_TOKEN` instead of the project's own GitHub PAT, and swallowed the failure. On
  the normal setup (PAT stored per project, `GITHUB_TOKEN` unset) the fetch was refused,
  the file list became empty and the job ended as `succeeded` in about a second with no
  covered cases. It now fetches the files the same way the manual run does (project PAT,
  GitHub or GitLab), and when the fetch fails the job is `failed` with the reason and the
  failure is logged, so no empty result is stored.
- Repository connections now infer GitHub/GitLab from HTTPS and scp-style SSH
  URL hosts, and project settings switch the provider and PAT panel accordingly.
  Detection respects `GITLAB_BASE_URL` and accepts `www.github.com`; bare paths
  retain the selected provider. GitLab URL parsing preserves nested namespaces
  and removes browser UI paths after `/-/` (provider detection part of #185).
- **A test from another feature is no longer carried over unless this feature's documents are about
  it.** A real run on a product-search feature (Elasticsearch, brand filters, sort, suggestions), in a
  project whose Login feature already had Google-login tests, attached nine of those login tests to the
  search feature. The Fusion step shows a model every test already in the project and attached
  whatever it named (`INHERIT_EXACT`) with no check, and its prompt pushed it ("you MUST inherit",
  "aim to inherit ~90%"). Replaying the real step with the 16 login tests, qwen2.5:3b carried over 14
  of them, qwen2.5:7b none, gemma3:4b 3 and llama3.2:3b 8; the right answer is none. Now a test of
  another feature is carried over (exact or adapted) only when this feature's own documents are about
  it, by plain text comparison with no model call: if the test names an endpoint and the documents
  name endpoints, one must be the same endpoint (another API version is another endpoint); otherwise
  at least two of its words, and 30% of them, must occur in the documents. Tests from the feature's
  own previous version are carried as before. A test that is not carried is listed in the job result
  as `inherited_rejected` with the reason. The model's `already_covered_summary` (handed to the
  agents that write the feature's tests as "do not write tests for X") is now used only when a test
  was really carried over; in the replay two models had copied the prompt's placeholder text and two
  had claimed the feature's own endpoints were already covered. The prompt's placeholder example for
  that summary is neutral now. With the gate, all four models carried over none of the unrelated
  tests, and on a control feature that really is a variation of Login (V4: Apple sign in on the same
  OAuth flow) 29 of the 33 tests they picked were kept. Trade-offs: a test that is truly reusable but
  whose words are not in the new documents (shared infrastructure the documents never mention) is
  no longer reused, and a project's reuse now depends on the documents naming what it reuses
  (part of #249).
- **PR coverage verdicts must now cite numbered code hunks that show the behaviour.** A real run
  on a product-search feature (seven tests written for `GET /api/v2/search`, `/api/v2/suggest`, a
  brand filter and a sort control) marked tests covered that the pull request does not implement:
  against a PR that only has the v1 search (`GET /v1/search`), qwen2.5:3b marked five tests covered
  and llama3.2:3b marked all seven. Four things caused it: the model was shown only the first
  6,000 characters of the diff (about 12% of a 1,200-line PR, and the route file was not in it);
  "covered" was the model's word, checked only as "a file that is in the diff"; a test for
  `/api/v2/search` was paired with a PR that defines `/v1/search` by function name; and a route
  written over several lines (`router.get(` then the path on the next line) was not recognised as
  a route at all. Now the diff is split into numbered hunks, each batch of tests is shown the hunks
  that match its own tests (a test's own route first; seed data, config, type files and tests are
  not offered), and a verdict must cite the numbers of the hunks that show the behaviour. The app
  checks that by text comparison with no model call: a verdict that cites no real hunk cannot be
  covered, a claim whose cited hunks share almost nothing with the test is dropped, a test for an
  endpoint the PR does not define cannot be covered, and a test for an endpoint the PR only defines
  under another API version is left out. Multi-line routes are now found. The saved record lists
  the hunks each verdict rests on. Replayed on qwen2.5 3b and 7b, gemma3 4b and llama3.2 3b against
  both PRs (one run per model and PR, 56 verdicts), tests wrongly marked covered went from 14 to 0,
  and tests correctly marked covered did not go down (4 to 5). Trade-offs: a function-name match
  can still report a test as partial ("the PR touches related code"), which is not the same as
  implemented; many tests the code really does implement are reported partial rather than covered
  (most models cite the right route but rarely carry the rest); and whether the code does what the
  test says beyond the words it shares with it is not checked (part of #249).
- **UI tests must now cite the document lines that state their rule.** A real run on a
  product-search feature kept three UI validations the documents never state ("Sort by is
  required", "Other brands must be unchecked", "select at least one brand"): the documents
  name a Sort by control and a brand filter but give no rule for either. Three things caused
  it: the UI prompt demanded at least 4 to 8 validations whatever the evidence said, its worked
  example (an "Event Title" field) leaked into answers, and the only check was whether the
  field's name appeared in the documents. Now the app splits the feature's own documents into
  numbered lines ([E1], [E2], ...) and the UI prompt shows them; there is no minimum, an empty
  list is a correct answer, and the example is placeholders. Every UI validation must cite the
  numbers of the lines that state its rule. Citing a number works on any model; copying a
  sentence exactly does not. The app then checks the validation against the lines it cites, by
  text comparison with no model call: the lines must exist, mention the field, contain every
  number the case claims, and contain nearly all the words of its intent. A validation that
  fails is dropped and counted in the job result as `ui-rule-not-in-documents`; a kept one
  stores the line numbers it cited. The repair pass follows the same rule. Replayed on
  qwen2.5 3b and 7b, gemma3 4b and llama3.2 3b with the real documents, the invented rules
  were dropped on all four, and on a document that states its rules every validation the
  models wrote was kept. Trade-offs: UI validations built only from field labels, with no rule
  stated in the documents, are no longer generated. A statement the documents do make can
  still be turned into a UI validation of the wrong kind (a caching sentence as a form rule):
  the check proves the documents support the claim, not that it belongs to a screen. Error
  message wording is not checked (part of #249).
- `LLM_TIMEOUT_SECONDS` now rejects non-finite values such as `nan`, `inf` and
  `1e400`. The setting's use by Configuration Save/Test provider checks is documented,
  and the Bedrock timeout selection is expressed explicitly without changing its
  existing precedence (#267).

- `run.ps1` now checks the native `docker compose up -d --build` exit code and stops immediately with a clear error instead of entering the five-minute readiness wait when the build/start command fails (#284).

- **A local Ollama model is now held to the output limit the code asks for.** Test generation
  asks for a limit on every call (3,000 to 10,000 tokens), but only Anthropic and Bedrock were
  given it; Ollama never received `num_predict`, so a small model that fell into a repetition
  loop kept writing until the call timed out (about 20,000 tokens in 30 minutes in one observed
  run), which on CPU is exactly where people are told to raise the timeout. A limit a caller
  chose is now sent to Ollama. `chat_json` and `call_llm_json_with_repair` no longer default to
  4000: a caller that never chose a limit (the code generator, the Mind Map reviewers that use
  the default) is not limited on Ollama, as before, and Anthropic and Bedrock still receive 4000
  for those callers. OpenAI-compatible providers are unchanged. A reply cut off at its limit is
  logged and is usually salvaged by the existing JSON repair, which keeps the entries completed
  before the cut; if the model has to repair it, that call gets a quarter more room so the
  repair is not cut off at the same place. The limit of the business-tests fallback rises from
  6,000 to 8,000 tokens, because its real replies reached 87% to 96% of the old limit. The Mind
  Map reviewer's limit is `MINDMAP_REVIEW_MAX_TOKENS` (default 2000) and can be raised (#249).
- **The business-tests fallback no longer asks for one test per requirement.** When the
  combined E2E call wrote too few business tests, a second call was told to write exactly one
  test per extracted requirement (about 20 for a typical PRD). The business suite is later
  trimmed to its focus share (about 8 or 9 with the default split), and a small model asked
  for more distinct tests than it can think of repeats itself: in two measured runs it wrote
  4,784 and 3,946 tokens (34% to 40% of the whole run's output and about a third of its time),
  and in one of them 19 of its 20 tests had the same title. It now asks for what will be
  used: the larger of the suite size the code already calls acceptable and what the focus
  budget keeps, minus the business tests already written, never more than the number of
  requirements. A heavy functional focus still asks for every requirement. In three
  measured runs the call fell to 327 to 1,763 tokens and the duplicates to 2 per run. It
  does not make a CPU-only run fast; that needs a GPU or a hosted provider (Part of #249).
- Generation skips Fusion when neither the project nor the previous feature version
  has reusable test candidates, and skips generation workers/fallbacks for zero-focus
  categories. The shared E2E/edge/business call still runs if any of its outputs is
  requested, avoiding wasted model calls on CPU-only installations (#139).

- On Windows, `run.ps1` no longer loses most of the collected logs. It calls
  `collect-logs.ps1` with `$ErrorActionPreference = "Stop"`, which the script inherited,
  so the first container whose `docker logs` reported an error (mongot prints a Java
  warning to stderr) ended the whole collection. `warden-ollama.log`, `warden-app.log`
  and the rest were never written, and the only message was "log collection failed".
  The script now keeps going and keeps what each command printed, and its web request
  still falls back to "app unreachable" (#286).
- The log collectors write cleaner, more useful files. On Windows PowerShell 5.1,
  `collect-logs.ps1` wrapped the first stderr line of each container log in a
  "NativeCommandError / CategoryInfo" block; each log is now just the text the container
  printed. `app_status.json` was filled from `/api/status`, which needs a login, so it
  said "app unreachable" (or held a 401) for a running app. Both `collect-logs.ps1` and
  `collect-logs.sh` now read the public `/api/auth/boot-status`, which shows the startup
  stage (for example "indexing" when mongot is not up), and the PowerShell script records
  "app answered with HTTP <code>" for an HTTP error instead of "app unreachable"
  (reported by connabyss on #286).
- The bundled stack no longer fails to start on a Linux host whose user is not uid 1000.
  `run.sh` and `install.sh` keep the mongot password file (`config/pwfile`, and
  `config/pwfile-percona` for the Percona stack) at mode 400, owned by whoever ran
  them. The one-shot setup container ran as the image's default user (uid 1000, and
  uid 1001 for Percona), could not read a file owned by another uid, and stopped with
  `/run/secrets/mongot-pw: Permission denied`. mongot then never started and boot sat
  at "indexing" with a message that pointed at the admin password. The setup
  containers now run as root, as mongot already does, so the secret stays private on
  the host and no `chown` workaround is needed. Docker Desktop was not affected, which
  is why it only showed up on native Linux (#285).
- The headline code coverage no longer counts a "partial" PR hit as covered. A PR
  that touches code relevant to a test case, without the model confirming the
  implementation, is stored as `partial`, but the feature report and the dashboard
  added every entry to the covered set whatever its status, so linking one unrelated
  PR could read as 100% coverage and "ready for manual QA". Only a confirmed
  `covered` verdict counts now. Partial hits are reported separately (`partial` and
  `partial_pct` on the feature coverage report, `partial_cases` in the coverage
  summary and the dashboard, and a `partial_count` next to each PR's `covered_count`,
  which now counts confirmed hits only) and shown on the feature page as "N partial (not
  counted)". A case that one PR confirms and another only touches still counts as
  covered once. Coverage entries saved before the status existed still count as
  covered. The percentage is computed when the page loads, so features that were
  reading too high show the lower number straight away, with no re-run (#287).
- The Gap Analysis run screens no longer count a "partial" PR hit as covered either.
  The run card's `tests_covered` / `gaps_found`, the run detail's "Tests covered" and
  Covered/Missing lists, and the comparison with the previous run (`newly_covered` /
  `no_longer_covered`, the up and down arrows) all treated a partial entry like a
  confirmed one, so an unrelated PR matched loosely read "3/3, 100%" and a loose match
  that disappeared was reported as lost coverage. Only a confirmed `covered` verdict
  counts now. Partial hits are shown separately: the card says "N partial, not counted"
  (new `tests_partial` field), and the detail view lists a partial case under Missing
  with a "Partial match, not confirmed" note and the model's rationale. Partial cases
  remain gaps until confirmed. Runs saved before this fix are corrected when they are
  served, from their stored entries, so no re-run or migration is needed; an entry
  saved before the status existed counts as covered (#291).
- The feature PDF report now prints the real coverage numbers. Its "Code coverage" and
  "Automation Test Coverage" cards read keys the coverage report never returns
  (`code_pct`, `automation_pct`), so both showed 0% on every export. They now show the
  confirmed code coverage and the same automation figure as the feature page (the
  test-repo scan), and the PR count comes from the report instead of a fallback
  (#287).
- The step library is now ordered by the number of test cases it shows for a
  step, not by the stored reuse counter. The counter is incremented on every
  reuse of a step and never decremented - not when a case stops using the
  step, not when the case is deleted - so a step that was reused a lot in the
  past used to sit above a step that is used by more cases today, and a page
  of N could leave out a step with a higher real count. The list and its
  paging follow the distinct-case count now, with the step id as the
  tie-break, so the order agrees with the count on screen and with the
  "shared by N testcases" note of the step editor (#270). The counting is
  one aggregation over the cases that groups them by step_ids with
  `$addToSet` on the case's own id, then the ordering and the paging happen
  in Python - the step ids in `cases.step_ids` are strings while the steps
  collection's `_id` is an ObjectId, so a `$lookup` between the two never
  matches on a real database; mongomock matches across the types, which is
  why this now has a dbintegration test that runs against a real MongoDB
  with string step ids (`tests/test_step_library_ordering_db.py`).
- `install.sh` no longer stops with a bare status 141 on a host that has no
  `openssl`. The random secret is then read from `/dev/urandom`, where the
  reader dies of SIGPIPE once `head` has its bytes - under `set -euo pipefail`
  that failed the whole pipeline and stopped the installer without a word.
  The reader's status is now kept out of the pipeline, the same guard
  `scripts/enable-mongo-auth.sh` already used, and a host with neither
  `openssl` nor `/dev/urandom` gets a message instead of a silent failure
  (#271). The `APP_SECRET` step now stops when the secret cannot be
  generated, instead of writing an empty one.
- Boot no longer bounces the admin back to Configuration on every refresh and deep link
  when the LLM section was never saved but the bundled defaults work: `needsConfig()`
  now treats a passing `GET /api/status` health check as configured and redirects only
  when the model is actually unreachable (#169).
- The LLM settings card no longer marks the API key and endpoint as required for
  Ollama. Placeholders are now provider-specific and update when you change the
  provider; for Ollama with a saved URL, the endpoint placeholder explains that
  leaving it blank resets to the bundled Ollama instance (#188).
- The case editor's "shared by N testcases" note counts distinct test cases:
  a case that uses one step twice no longer counts twice, and the count drops
  when a case stops using the step (#175).
- `install.sh` now probes `/dev/tty` by opening it before enabling interactive prompts. Runs without a controlling terminal use the existing non-interactive defaults instead of failing while opening the terminal (#220).
- Test-case priority is stored in one vocabulary, High/Medium/Low, whichever
  path wrote it (generation, the editor, sheet import); existing cases are
  converted on startup, so exports no longer mix P1 and HIGH (#174). Upgrading
  rewrites stored priorities once, on first start, and this can't be undone: P0
  and P1 both become High, and P3 and P4 both become Low.
- Users limited to specific projects now see those projects' features in the
  Features list. It used to come back empty for them (#221).
- OpenAPI YAML extraction now reports every method of a path, not just the first
  one, when an operation has nested keys such as `summary:` or `responses:` (#221).
- Fix nested objects in test case expected responses displaying as `[object Object]`; render them as formatted, escaped JSON.
- A wrong password on a fresh install, before the admin account exists, now says
  "Invalid username or password" like everywhere else. It used to answer 503 with
  "No user accounts exist. Run scripts/reset-admin-password.sh", which sent people to
  a recovery they did not need: the default admin login still creates the admin. The
  recovery hint is still part of the public boot status that the sign-in page shows
  while the app is starting. These failed attempts now count toward the sign-in
  limit like any other: by default ten wrong tries lock the account for 15 minutes
  (`AUTH_MAX_FAILURES_PER_ACCOUNT`, `AUTH_LOCKOUT_SECONDS`), which includes `admin` on a
  fresh install (#172).

## v0.3.0 — 2026-11-04

### Security

- Hardened authorization: the embedding-model switch is admin-only, stored
  provider credentials are only reused for the endpoint they were saved for,
  and project scoping is enforced on the remaining by-id, by-body and aggregate
  routes (documents, PRs, coverage runs, cycle templates, sheet imports,
  dashboard, tags, case retrieval, usage).
- Hardened rendering of user/LLM-supplied values in the web UI and validated
  test-case types server-side.
- Hardened Git provider requests (repository path, owner/name and branch
  validation) for Start Developing and repository access.
- Added brute-force throttling to sign-in, code verification and password-reset
  routes; OTP and reset-code issuance limits are now atomic. New settings:
  `AUTH_MAX_FAILURES_PER_ACCOUNT`, `AUTH_MAX_FAILURES_PER_IP`,
  `AUTH_FAILURE_WINDOW_SECONDS`, `AUTH_LOCKOUT_SECONDS`,
  `RESET_CODE_MAX_PER_WINDOW`, `TRUSTED_PROXIES` (set it when running behind a
  reverse proxy, otherwise all users share the proxy's address). The throttle
  counters are not copied by the database migration.
- Without SMTP, sign-in codes are no longer returned to the browser; only the
  bootstrap admin's code is printed to the server log. Demo installs can opt in
  with `OTP_DEV_CODES=true` (ignored when `APP_ENV=production`).
- The master-secret password reset is limited to administrator accounts and is
  audited; sign-in successes/failures are audited; API-token actions record the
  token as the actor; users with a pending invitation must accept it before
  using the API; logout revokes the session server-side; viewers can change
  their own password.
- Added size limits for uploads (`MAX_UPLOAD_MB`, HTTP 413), unpacked
  `.docx`/`.xlsx` content (`MAX_ARCHIVE_UNCOMPRESSED_MB`) and repository
  archives (`MAX_REPO_ARCHIVE_MB`, streamed to a temporary file).
- Hardened the link follower's address checks, download filenames, storage
  error messages, defect-link URLs and Ollama model listing.
- Updated dependencies to patched releases (fastapi/starlette, pypdf 6,
  cryptography, python-multipart, pymongo, json-repair, pytest, vite,
  source-map-js).

### Added

- **Model selection guidance.** New "Choosing a model" section in `docs/configuration.md`
  with measured results for `qwen2.5:3b`, `llama3.2:3b`, `gemma3:4b` and `qwen2.5:7b`
  on one document and one machine (3 repeats each, all complete), a recommendation, and
  the limits of the evidence. The bundled default is unchanged and hosted models were not
  benchmarked. The Configuration screen now points to it. Adds `scripts/eval_generation.py`
  to reproduce the measurements locally and the result files under `docs/eval-results/`
  (Part of #43).

### Fixed

- **Malformed LLM JSON no longer crashes analysis or leaves orphan feature versions.**
  JSON responses are required to be objects, nullable list fields are normalized at
  the shared generation/coverage boundaries, and version diffs complete before a new
  feature version is persisted (#147).
- **Capability probe reports the curated message for MongoDB without mongot.**
  A stock replica set without mongot rejects search-index creation with error
  code 31082 ("requires additional configuration"); the probe previously fell
  through to the generic branch and showed truncated raw driver text. Code
  31082 (or the message on its own) now classifies as search-unsupported, so
  the probe returns the "requires a MongoDB with Vector Search" message (#204).
- Ollama health checks now send the configured bearer token, matching generation requests (#180).
- Replaced the deprecated FastAPI `@app.on_event("startup")` handlers in
  `app/main.py` with a `lifespan` context manager (no more deprecation
  warnings on import/startup; same bootstrap, scheduler, and poller threads
  in the same order) (#198).
- `run.sh` no longer fails with `/dev/tty: No such device or address` when run
  without a terminal (CI, cron, new session): it now probes `/dev/tty` by
  opening it, and otherwise takes the non-interactive default database and says
  so (#191).
- Five small fixes found by a QA run:
  - `is_test_file` no longer flags production files that merely end in `it`/`test`/`spec`
    (`audit.go`, `limit.go`, `edit.rb`, `Commit.cs`); the CamelCase suffix rule
    (`FooTest.go`, `BarIT.java`) is now case-sensitive.
  - Key-write extraction records every keyword of `dict(...)`, not just the first.
  - `scripts/enable-mongo-auth.sh` no longer exits 141 when `openssl` is missing.
  - `scripts/reset-smtp-secret.sh` clears only the stored SMTP password, as its header
    says; a configured SMTP user with no password is now treated as unusable, so the
    bootstrap admin's sign-in code is still printed to the server log afterwards.
  - `install.ps1` no longer aborts when an existing `.env` has no `APP_SECRET`.
- Percona Server for MongoDB + Percona Search is documented as an opt-in technical preview
  (not the default, not recommended for production), with its known limitations; the
  ROADMAP no longer claims it sidesteps the kernel ≥ 6.19 guard. HA/load validation and
  the supported-or-default decision are tracked in #222 and #223 (#41).

- Fixed the installer script links in `docs/configuration.md` to resolve to the
  repository root after the documentation move (#61).

- **Generation no longer persists prompt few-shot exemplars as real test cases.**
  Cases whose title, intent, or preconditions copy the examples in
  `app/testgen/prompt_builder.py` (including hybrid titles that keep the
  event-host scaffolding) are dropped before persist. When edge evidence is
  insufficient the shared E2E call's `edge_cases` block is discarded instead of
  being stored as `nfr`, and e2e/nfr cases with zero overlap against the source
  documents are rejected.

- **Boot / Vector Search failure copy no longer overlays the sticky header.** Long
  `boot.detail` text was injected into absolutely-centered `#status` (`min-width:
  max-content` + `nowrap`), covering the logo, page title, and Sign out / Change
  password. Non-ready boot messaging now renders in a wrapping document-flow
  banner above the header; `#status` keeps compact service chips only. Raw driver
  exceptions are not the primary visible text — they sit behind a Details control
  (and the console).

- **Boot failures are visible before sign-in.** The login screen now shows safe
  startup diagnostics and names `scripts/reset-admin-password.sh` when no users
  exist. Empty-user password attempts report recovery instructions instead of
  invalid credentials. Raw driver exceptions are never exposed by the public
  boot-status endpoint; healthy sign-in keeps its existing appearance.

## v0.2.3 — 2026-08-26

_No changelog-worthy entries were recorded for this release; see the commit range `v0.2.2..v0.2.3`._

## v0.2.2 — 2026-08-25

### Added

- **The Mind Map is now an interactive coverage MAP that stays legible at enterprise
  scale.** The old view was expandable feature cards — no structure, no priority. It is
  now a node map over the same `/api/projects/{pid}/mindmap` payload:
  **PROJECT → REPOSITORY → FEATURE → STATUS → test cases**, hand-rolled SVG + vanilla JS
  (no CDN/D3, so it still works air-gapped).
  - **Two layouts, auto-selected so the map can never crowd.** *Radial* is used for small
    projects (≤9 features, single repo) and its ring radius is derived from the real node
    widths — needed circumference ÷ 2π — so boxes are mathematically incapable of
    overlapping. Anything larger switches to a *tidy tree* whose row for every node comes
    from its subtree's leaf count, giving a fixed 30px pitch for 22px nodes at any size;
    the canvas grows and the stage scrolls instead of blurring. A radial map with 40+
    features would have to shrink text below legibility, which is why the switch exists.
    An `auto / radial / tree` toggle lets the user override.
  - **Repositories are a real layer**, not a tooltip footnote: in tree mode features are
    grouped under the repo they were reviewed against (a feature spanning several repos
    appears under each), with a column header showing the repo count.
  - Each feature node carries a wrapped label, version, case count, coverage % and a
    covered/partial/uncovered bar; edge thickness scales with case count. Clicking a
    feature expands its cases inline (tree) or re-roots the map on it (radial); clicking a
    status cluster jumps straight to those cases. Large features cap at 48 drawn cases
    with a `+N more` node so the canvas can't explode.
  - Selecting a feature opens the **evidence panel**: each case with the reviewer's
    rationale and the **source files cited as proof**, filterable by status; cases with no
    implementing file say so explicitly. With nothing selected the panel ranks **evidence
    hotspots** — the files cited most often, i.e. the riskiest places to change.
  Duplicate feature names are numbered ("… (2/3)") since several features previously
  truncated to the same label. Interim Sankey-flow, feature/file-matrix and ranked-bar
  views were built during this work and removed: with features that share most of their
  files those degrade to a single blob, a uniform grid, and a table respectively.

### Fixed

- **A saved Jira (or LLM/SMTP) integration could silently disappear later, with
  no error at save time and no sign-out in between.** `app/store/base.py`
  connected to MongoDB with pymongo's default write concern (`w=1`,
  acknowledged by the primary only). On the bundled 3-node replica set, a
  routine primary election shortly after a `/api/settings` save (a container
  restart, a brief network blip, a laptop suspending mid-session) rolls back
  any write that reached the old primary but hadn't yet replicated when it
  stepped down — even though the client already got back `200 OK`. Since
  Jira/LLM/SMTP credentials are saved once and read much later (e.g. "Create
  Feature"'s Jira epic picker), this showed up as "the config isn't there
  anymore," fixable only by re-opening Settings and saving again (which
  happened to catch a stable primary). User sessions were unaffected, since
  they're looked up from user documents written well before the rollback
  window, which is why the symptom tracked with a browser restart rather than
  a sign-out. `BaseStore.__init__` now runs every Mongo URI (bundled default or
  bring-your-own) through `_with_durable_write_concern`, which adds
  `w=majority&retryWrites=true` unless the URI already specifies its own —
  making a save durable across a primary failover instead of appearing to
  succeed and quietly reverting.

## v0.2.1 — 2026-07-23

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

## v0.2.0 — 2026-07-20

### Added

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
