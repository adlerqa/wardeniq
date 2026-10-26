# wardenIQ Backend Restructuring Plan

**Originally verified against commit `2d284d2`** (`main`) and `2be0ceb`
(`feature/jira-plugin`). **Re-verified 2026-08-15 against `edbbbcb`** (`main`, 4 commits
later) — see Section 0.1. Working tree clean except `app/workers.py` (deleted per 2.1)
and this file.

**Goal:** break `app/main.py` (7,316 lines as of `edbbbcb`) and `app/store.py` (3,889
lines, 257 methods on a single `Store` class) into a proper package layout, with **zero
functional regression** — every route, background job, poller, and RBAC rule behaves
identically before and after — **across a public upstream repo and a private downstream
fork.**

**Read order.** Sections 0–2 are findings and blockers. **Section 3 (two-repo topology)
happens before Phase 0** — the fork strategy has to be settled first, because it
determines whether the nine refactor phases are cheap or catastrophic downstream.
Sections 4–7 are the target design. Sections 8–17 are the phases. No application code is
changed by this document.

---

## 0. What the last commit actually did

The commit is titled "decompose monolithic application into modular packages," but
**no decomposition of `main.py` or `store.py` happened.** Measured:

| File | Before | After | Change |
|---|---|---|---|
| `app/main.py` | 7,185 | **7,225** | +40 (grew) |
| `app/store.py` | 3,851 | **3,889** | +38 (grew) |
| `app/coverage.py` | 438 | **1,125** | +687 |
| `app/api_exec.py` | — | 256 | new |
| `app/scanners.py` | — | 215 | new |

What it really contains is **Mind Map accuracy work** — uncapped hybrid retrieval, a
character-budget excerpt window sweep, cross-sample self-consistency
(`MINDMAP_SAMPLES`), citation grounding, an index-rules fingerprint, a `force_reindex`
flag — plus a strong new test/eval harness (`tests/eval/`, `test_api_exec.py`,
`test_scanners.py`, `test_excerpt_budget.py`, `test_store_degradation.py`, ~400 added
lines in `test_review_functions.py`). Valuable work, and the new tests improve the
safety net for this refactor. But the monolith is untouched and slightly larger, so the
plan below applies in full.

### 0.1 Re-verification pass (2026-08-15, commit `edbbbcb`)

Two more commits landed since the plan was first written (`ce9a4e9`,
`edbbbcb`) — all further Mind Map / accuracy work, none of it structural:

- **`app/contracts.py` (477 lines, new)** — producer/consumer contract-break detection
  (catches a PR that renames a dict key/field in one file while another file still
  reads the old name). Pure static analysis, no FastAPI/Store coupling, imported by
  `coverage.py`, `grounding.py`, and `main.py`. Fits the "already single-purpose, leave
  as-is" bucket in Section 5 alongside `coverage.py`'s siblings.
- **`app/grounding.py`** grew 595 → 818 lines and **`app/coverage.py`** grew 1,125 →
  1,398 lines integrating `contracts.py`. Reinforces Section 0's point about
  `coverage.py` (Phase 9, optional) — it keeps absorbing new concerns.
- **2.2's fingerprint fix already landed**, and better than proposed (Section 2.2).
- **Zero new routes, zero new Store methods, zero new middleware** — confirmed by
  direct count (still 165 / 257 / 2) and by diffing `main.py`'s decorator lines between
  `2d284d2` and `edbbbcb` (only worker-internal hunks, inside `_codeanalysis_worker` /
  `_pr_coverage` / `_repo_get_archive`). **This means Section 6/7's route/method
  structure is still entirely valid** — only the exact line numbers in Section 7's
  table have drifted (by roughly the net insertion size, ~150 lines, for anything after
  the workers section); Phase 0 already instructs regenerating these fresh, so this is
  a non-issue, just don't trust the table's line numbers literally without re-grepping.

Six further findings from this pass, folded into their relevant sections below rather
than left here: the 2.1/2.2 pre-flight items are now done (statuses inline in Section
2), two new pre-flight items surfaced (2.5 fixture gap, 2.6 an `embedder`
circular-import trap that's real, not theoretical — traced from the actual code), and
Phase 0's baseline artifacts have now actually been generated (`refactor-baseline/`,
committed to this repo) rather than only specified.

Two structural observations from that commit:

**`api_exec.py` and `scanners.py` are not wired in.** Repo-wide grep: imported only by
`tests/test_api_exec.py` and `tests/test_scanners.py`. No application module imports
either. Complete, tested modules sitting outside the call graph — see blocker 2.3.

**`coverage.py` is becoming the third monolith.** At 1,125 lines it holds Mind Map
review, citation grounding, sample reconciliation, excerpt windowing, PR→feature
mapping, PR coverage verification, impact analysis, and version diffing — seven
concerns. Not urgent, so it's Phase 9 (optional), but it's on the trajectory `main.py`
was on.

---

## 1. Verified facts

Checked against the repo, not inferred.

**Import style is settled: keep flat imports, keep `app/` as the run directory.**
Confirmed three ways:

- `app/Dockerfile`: `WORKDIR /app`, `COPY app/ .`, `CMD ["uvicorn", "main:app", ...]` —
  the contents of `app/` are the container root, so `import coverage` works and
  `import app.coverage` never would.
- `pytest.ini`: `pythonpath = . app`, with a comment stating "The app is a flat package
  of top-level modules (coverage.py, store.py, ...), so put app/ on sys.path."
- No `pyproject.toml`, `ruff.toml`, or `setup.cfg` exists; ruff and mypy run with
  defaults over `app tests` / `app`. No packaging config to migrate.

Consequence: create subpackages **inside** `app/` and import them flat
(`from core.config import MONGO_URI`). Because `app/` is on `sys.path` this resolves in
the container, under pytest, and via `run.sh` with **no change to `Dockerfile`,
`pytest.ini`, `run.sh`, or any compose file** — `COPY app/ .` picks up new
subdirectories automatically. Verify once in Phase 1, then stop worrying about it.

**CI gates, verbatim from `.github/workflows/ci.yml`:**

- `unit-tests`: `pytest -m "not dbintegration"` — the merge gate.
- `db-integration-tests`: `pytest -m dbintegration -v` with `MONGO_TEST_URI` against a
  standalone `mongo:7` (no mongot, so vectorSearch-backed `store.py` paths are out of
  scope; full vector coverage is a manual docker-compose verification).
- `ruff check app tests` and `mypy app --ignore-missing-imports` — both
  `continue-on-error: true`, i.e. **informational, not gates.**
- `pip-audit` — informational.
- `docker-build`: `docker compose config --quiet` then `docker build -f app/Dockerfile`.

Two implications. Ruff and mypy **will not block a bad refactor** — a circular import or
a dead import sails through CI, so treat their output as a manual review step each phase
(see Phase 0.5). And `docker-build` is a real gate, so a broken entrypoint surfaces
immediately.

**Inventory to freeze in Phase 0:**

| Metric | Count |
|---|---|
| Route decorators in `main.py` | **165** |
| Pydantic models in `main.py` | 43 |
| `@app.middleware("http")` handlers | 2 |
| Top-level `def`/`async def` in `main.py` | 293 |
| Methods on `class Store` | **257** |

---

## 2. Pre-flight blockers — fix before Phase 1

Six items, each its own small commit, all harder to deal with once files are in motion.
**2.1 and 2.2 are now done** — see their status notes below; 2.3 and 2.4 are still open
decisions; 2.5 and 2.6 are new findings from the 2026-08-15 plan-vs-repo verification
pass (Section 0.1).

### 2.1 `app/workers.py` collides with the planned `workers/` package — and is dead code

`app/workers.py` (50 lines) defines `UnifiedWorkerPool` and, at import time, instantiates
`worker_pool = UnifiedWorkerPool()`, starting three daemon threads. **Nothing in the repo
imports it** — no application module, no test. The threads never start today; the file is
inert.

`app/workers/` cannot coexist with `app/workers.py`, and a module that silently spawns
three threads on import is a landmine if anyone ever imports it. Delete it in its own
commit before Phase 3 (git history keeps it). If you'd rather not, name the package
`jobs/` and rename those paths throughout the plan.

**Status: DONE (2026-08-15), with one operational note.** Re-verified dead — still zero
references anywhere in the repo (only an unrelated string match inside a vendored
`pygments` lexer file). The file could not be deleted with `rm`/`unlink` (this
environment's device bridge to Samyak's Mac rejects that syscall on mounted files —
`Operation not permitted`); `mv` (rename) is permitted, so it was moved to
`_to_delete/workers.py` at the repo root instead, taking it out of the `app/` package
without a true delete. `git status` correctly shows it as `D app/workers.py` (deleted from the tracked
location); `_to_delete/workers.py` is untracked. **To finish this cleanly, run locally**
(this Mac-side restriction doesn't apply to your own Terminal):
```bash
rm -rf _to_delete
git add -A          # stages the app/workers.py deletion
```

### 2.2 `INDEX_RULES_FINGERPRINT` is non-deterministic — the index cache never hits after a restart

`app/coverage.py:602`:

```python
INDEX_RULES_FINGERPRINT = "testfilter:" + str(abs(hash(TEST_FILE_RE.pattern)) % (10 ** 12))
```

`hash()` on a `str` is salted per process by `PYTHONHASHSEED`, which CPython randomizes
by default, and no `PYTHONHASHSEED` is set anywhere in the repo. Confirmed empirically —
the same expression in three fresh interpreters:

```
testfilter:925094847494
testfilter:832157277
testfilter:839505827862
```

`_codeanalysis_worker` computes
`rules_ok = (meta or {}).get("rules") == cov.INDEX_RULES_FINGERPRINT`, so `rules_ok` is
`False` for every repo after any restart. Effect: **every Mind Map run re-fetches each
repo tarball and re-embeds every chunk**, even when the branch head hasn't moved — the
exact cost the cache exists to avoid, and it silently defeats the point of the
`force_reindex` flag.

```python
import hashlib
INDEX_RULES_FINGERPRINT = "testfilter:" + hashlib.sha256(
    TEST_FILE_RE.pattern.encode()).hexdigest()[:16]
```

Land this **before** the refactor; otherwise Phase 3 inherits a pre-existing bug and the
first person to notice slow Mind Map runs will blame the restructuring. Test the
fingerprint's stability **across a subprocess boundary** — an in-process equality
assertion passes even with the buggy version.

**Status: DONE, and exceeds this proposal.** Verified in the current repo
(`app/coverage.py`, `INDEX_RULES_FINGERPRINT` definition): it now hashes **five** rule
patterns with `hashlib.sha256` (`TEST_FILE_RE`, `NON_IMPL_PATH_RE`,
`_VALUE_CONSTRUCT_RE`, `_TYPE_ONLY_DECL_RE`, `_COMMENT_RE` — the non-implementation-file
filtering grew since this plan was written), prefixed `"indexrules:"` rather than
`"testfilter:"` so old cached indexes are correctly treated as stale rather than
falsely "matching." `tests/test_index_fingerprint.py` (8 tests) does exactly the
subprocess-boundary check this section asked for, plus more: stability under
`PYTHONHASHSEED=random`, a guard against reverting to `hash()`, a check that every rule
actually moves the digest (no inert inputs), and a check that every pattern
`is_non_implementation_file` consults is included in the fingerprint. No action needed
— re-verify only if `coverage.py`'s indexing rules change again before Phase 1 starts.

### 2.3 Decide when `api_exec.py` / `scanners.py` get wired in

Both are finished, documented, tested, and reachable from no application code. Either
integrate them now on their own commit (so the refactor moves a codebase whose call graph
is complete), or leave them inert until after Phase 6 — they can't break anything
meanwhile, and their eventual homes are obvious (`api_exec` behind a route plus a worker,
`scanners` called from the code-coverage worker). What's not acceptable is integrating
mid-refactor, which mixes a behavior change into a phase whose premise is "behavior is
identical."

Aside: `app/coverage.py` shadows the `coverage` PyPI package. Harmless today (dev deps
are pytest, pytest-mock, ruff, mypy, pip-audit), but adding `pytest-cov` later would
break imports confusingly. Worth a comment in the file rather than a rename.

### 2.4 The test suites reach into `main.<attr>` — enumerate this before Phase 2

The nine RBAC suites are the best safety net for this refactor, but **they are coupled to
`main.py`'s namespace and will break when symbols move** unless handled deliberately.
Measured across `tests/`: 32 × `main.store`, 15 × `main._min_role`, 6 × `main._is_public`,
4 × `main.app`, plus `main.login_password`, `main.verify_otp`, `main.request_otp`,
`main.smtp_status`, `main.auth`.

The distinction that matters:

**Patching an attribute *on* an object survives a move.** `monkeypatch.setattr(main.store,
"get_user", …)` mutates the shared `Store` singleton, so it works no matter which module
you reach it through. Likewise `main._min_role(...)` and `main._is_public(...)` are only
ever *called*, never patched — a re-export keeps them working with zero test edits.

**Rebinding a module attribute does not survive a move.** There are exactly ten, and
every symbol involved moves during the refactor:

| Test file | Rebind | Moves to |
|---|---|---|
| `tests/test_api_routes.py:94` | `setattr(main, "_deliver_otp", …)` | `api/routes/auth.py` |
| `tests/test_rbac_e2e.py:121` | `setattr(main, "embedder", …)` | `core/deps.py` |
| `tests/test_sheet_import_main_helpers.py:95,118` | `setattr(main, "store", …)` ×2 | `core/state.py` |
| `tests/test_ext_jira.py:186,202` *(private)* | `setattr(main, "launch_job", …)` ×2 | `workers/registry.py` |
| `tests/test_ext_jira.py:312,345` *(private)* | `setattr(main, "_feature_coverage_payload", …)` ×2 | `api/routes/code_coverage.py` |
| `tests/test_ext_jira.py:386` *(private)* | `setattr(main, "_jira_sync_feature", …)` | `api/routes/jira_atlassian.py` |
| `tests/test_ext_jira.py:412` *(private)* | `setattr(main, "start_test_plan", …)` | `api/routes/test_plan.py` |

Note the private test file is **more** coupled than any public one, precisely because it
patches the seams it introduced.

Mitigation, applied in Phase 2:

1. Add an explicit re-export block to `main.py` so every read-only reference keeps
   working untouched. This must cover ALL of them, not just the three most-cited —
   confirmed complete against `refactor-baseline/main-namespace-refs.txt` (the full
   grep, 2026-08-15):
   ```python
   # Re-exported for tests that reach these via `main.<name>` (see tests/ and
   # refactor-baseline/main-namespace-refs.txt for the full inventory). Not used by
   # main.py itself post-refactor — do not remove without updating those tests.
   from core.state import store                       # noqa: F401  (32 refs)
   from core.security import _min_role, _is_public     # noqa: F401  (15, 6 refs)
   from api.routes.auth import (                       # noqa: F401
       login_password, verify_otp, request_otp, smtp_status,
       LoginPasswordIn, OtpVerifyIn, OtpRequestIn,      # Pydantic models tests construct directly
   )
   from api.routes.test_import import (                # noqa: F401
       remove_imported_sheet_rows, LibraryHashesIn,
   )
   from workers.repo_scan_worker import _promote_imported_row_to_feature   # noqa: F401
   import auth                                          # noqa: F401  (main.auth — already a
                                                          # top-level module, re-export not
                                                          # strictly needed but keeps `main.auth`
                                                          # resolvable if a test imports it that way)
   from fastapi import HTTPException                    # noqa: F401  (main.HTTPException)
   ```
2. Fix the ten rebinds to target the module that now owns the symbol. Four are public and
   must be fixed in the public repo; six are private and get fixed when the private
   branch is re-derived (Section 3).

Enumerate these in Phase 0 so Phase 2 is a planned three-line fix rather than fifty red
tests of unclear cause.

**Re-verified 2026-08-15 against the current `main` branch (public repo only —
`test_ext_jira.py` lives solely on `feature/jira-plugin`, so the six private rebinds
above aren't in this run).** Full grep of every `main.<attr>` reference across
`tests/*.py`: same 4 public rebinds (`_deliver_otp`, `embedder`, `store` ×2), plus three
attribute reads not previously listed here — `main.LoginPasswordIn`, `main.OtpVerifyIn`,
`main.OtpRequestIn`, `main.LibraryHashesIn` (Pydantic request models constructed
directly in tests) and `main.HTTPException`, `main.remove_imported_sheet_rows`,
`main._promote_imported_row_to_feature` (direct function references). These are reads,
not rebinds, so the same re-export mitigation covers them — just make sure the Phase 2
re-export block includes every Pydantic model a test constructs directly, not only the
functions. Full enumeration: `refactor-baseline/main-namespace-refs.txt`.

### 2.5 `tests/fixtures/auth_pilot/` was never committed — 6 test files fail on a fresh checkout

Not part of the restructuring, but caught while establishing the Phase 0 test baseline,
and worth fixing on its own before or alongside Phase 0 so the baseline pass/fail count
means what it looks like it means.

`tests/test_contracts_auth007.py`, `test_contracts_full_suite_false_positives.py`,
`test_contracts_orphaned_reads.py`, `test_coverage_contract_cap.py`,
`test_grounding_contract_tier.py`, and `test_mindmap_orphaned_cap.py` all load fixture
data from `tests/fixtures/auth_pilot/*` via a local `_read()` helper. `git ls-files
tests/fixtures/` is empty — that directory was **never added to git** on any branch —
and it is currently empty on disk too. Running the suite fresh reproduces it exactly:

```
FileNotFoundError: [Errno 2] No such file or directory:
'tests/fixtures/auth_pilot/pr9_tokens.patch'
```

Effect: **30 failed + 11 errors, confirmed pre-existing, not a refactor regression** —
100% confined to these six files (verified — every other test, 486 of them, passes).
Anyone cloning fresh or CI running from a clean checkout hits the identical failures.

**Recovery attempt (2026-08-15) — exhaustive, unsuccessful with confidence.** The
exact 12 filenames these tests need, read directly from the test source (not memory):
`app.py.txt`, `audit_log.py.txt`, `driver_only.py.txt`, `middleware.py.txt`,
`pr6_full.diff`, `pr7_full.diff`, `pr8_full.diff`, `pr9_tokens.patch`,
`real_41_case_data.json`, `refresh.py.txt`, `tokens_after.py.txt`,
`tokens_before.py.txt`. Searched, before concluding they cannot be reliably recovered:

- Every commit on every branch (`git log --all --diff-filter=A --name-only`) for these
  12 filenames — zero matches, never committed anywhere.
- `git stash list` — empty.
- `git fsck --full --unreachable --dangling` — found 3 dangling commits and 5 dangling
  trees, all timestamped Jul 20–22 (old stash artifacts, frontend/root-config
  snapshots), predating the fixtures entirely (the contracts.py work is dated Aug 4–6).
  None contain any of the 12 filenames or an `auth_pilot` path.
- The same `fsck` run found **36 dangling blobs**. Content-sniffing all 36 for
  fixture-domain signatures (`auth_pilot`, JWT `role`→`user_role`, `TAB-AUT-*` case
  IDs, `services/auth_service`) surfaced 10 hits — content clearly from the *same
  investigation* (a synthetic `role`→`user_role` JWT rename used to test cross-file
  contract-break detection): a `middleware.py`-like docstring, a 29KB JSON array of
  `tab-aut-N` cases (plausibly `real_41_case_data.json`), a small role-rename diff
  hunk, two "new file" diffs for `driver_only.py`/`refresh.py` plus their raw blob
  content, a `tokens.py`-like docstring, an unrelated ADR-doc diff, and (incidentally)
  the full text of `WARDENIQ_CROSS_FILE_IMPLEMENTATION_TEST_RESULTS.md` itself — which
  turns out to have never been committed either and is no longer present on disk; this
  is the only place its own described backup location (§7) could have been checked,
  and that path is now gone too.

  **This is source material, not the fixtures themselves — the mapping from blob to
  exact target filename is a guess, not a fact** (blobs carry no filename; several
  candidates are ambiguous — e.g. nothing distinguishes a "tokens.py docstring" blob as
  `tokens_before.py.txt` vs. `tokens_after.py.txt`), and it's incomplete regardless —
  no candidate was found at all for `app.py.txt`, `audit_log.py.txt`, `pr6_full.diff`,
  `pr7_full.diff`, `pr8_full.diff`, or a full-length `pr9_tokens.patch` (only a 573-byte
  fragment turned up, too small to be the actual patch file the tests parse). Per this
  plan's explicit instruction not to invent or recreate fixture content, **these blobs
  were left untouched — nothing was reconstructed from them.** They remain in the
  object database (`git gc` would eventually prune them) if you want to inspect
  `git cat-file -p <sha>` yourself; SHAs are in the Step 3 report delivered alongside
  this plan.

**Conclusion: the fixtures are not recoverable with confidence. Record the baseline as
486 passed / 41 pre-existing (30 failed + 11 errored) fixture-dependent failures**, not
as 41 unresolved regressions, and commit fresh `tests/fixtures/auth_pilot/*` content
(regenerated deliberately, not guessed from these fragments) whenever that work is
prioritized — independent of, and not blocking, this refactor.

### 2.6 The eager `embedder` singleton is a real circular-import trap for Phase 1/2 — not just a theoretical one

Traced from the actual code, not reasoned abstractly (`app/main.py`, verified via a full
AST scan of every module-level statement): between the config constants and the RBAC
section, `main.py` currently does, in this exact order:

```python
store = Store(MONGO_URI, DB_NAME, EMBED_DIM)     # line 136 — a store IS the singleton

def current_embedder() -> Embedder:              # ~line 187 — builder function
    s = store.get_settings()
    ...

_saved_embed = store.get_settings()              # line 222 — LIVE DB READ AT IMPORT TIME
if _saved_embed.get("embed_dim"):
    store.dim = int(_saved_embed["embed_dim"])
embedder = current_embedder()                    # line 225 — THE EAGER SINGLETON
```

Three consequences the plan's Phase 1/Phase 2 split (Section 9/10) didn't account for:

1. **`embedder` (the built object) is a third true singleton, same category as `store`
   and `SYNC`, and the plan never gave it a home.** It's referenced ~25 times across
   route handlers and workers (`embedder.embed(...)`), and it's genuinely mutated: a
   full `global` audit of `main.py` found exactly one reassignment,
   `global embedder; embedder = current_embedder()` inside `_reembed_worker` (fires when
   an admin switches the embedding provider via `/api/embedding/switch` → the job
   system → this worker — the route handler itself never touches the global, only the
   worker does).
2. **Building `embedder` requires `current_embedder()` to already exist, but
   `current_embedder()` is planned for `core/deps.py` while `embedder`/`store` are
   planned for `core/state.py`.** If `core/state.py` calls `current_embedder()` at its
   own module level to build the eager singleton, it needs to import `core.deps` — but
   `core.deps` needs `store` from `core.state` — a genuine circular import, not a
   stylistic one. It will fail with `ImportError: cannot import name ...` the moment
   Phase 1 lands, exactly at the boundary between "Phase 1 moves `store`" and "Phase 2
   moves `current_embedder`."
3. **Because `embedder` is reassigned via `global`, importing it by name is unsafe
   anywhere it's consumed** — `from core.state import embedder` freezes a local
   reference that a later reassignment in `workers/generation.py` (post Phase 3) will
   never update, silently keeping every route handler and worker on the *pre-switch*
   embedder forever after someone calls `/api/embedding/switch`. This bug would not show
   up in any smoke test that doesn't specifically switch embedding providers and then
   re-check — exactly the kind of thing that ships quietly and breaks in production.
   (`store`, `SYNC`, and `JOB_WORKERS` do **not** have this problem — audited via the
   same `global` scan, none of them are ever rebound, only mutated in place, so
   importing those three by name is safe.)

**Required change to Phase 1/Phase 2 (Section 9/10), before either is executed:**

- `core/state.py` (Phase 1) declares `store = Store(...)`, `SYNC = {...}`,
  `JOB_WORKERS = {}`, and a placeholder `embedder = None` — it does **not** call
  `current_embedder()` itself, breaking the cycle.
- `core/deps.py` (Phase 2) imports `core.state` (one direction only) and, after defining
  `current_embedder()`, runs the same eager-init block as a side effect of being
  imported: reads settings, sets `state.store.dim`, and does `state.embedder =
  current_embedder()` — writing through the `state` module object, not rebinding a
  locally-imported name.
- `main.py` must import `core.deps` (even if nothing else in it is used yet) early
  enough that this side effect fires before the app starts serving requests — the
  natural place is right where `core/config.py` and `core/state.py` are imported at the
  top of the new `main.py`.
- **Every consumer of the live embedder — every route handler (Phase 6) and every
  worker (Phase 3) — must do `from core import state` and reference `state.embedder`,
  never `from core.state import embedder`.** This is the one blanket rule worth adding
  to Phase 3 and Phase 6's instructions verbatim, since it's an easy, silent mistake and
  the only one of the three module-level singletons where it matters.

---

## 3. Two-repo topology (Phase −1 — do this before Phase 0)

### 3.1 Measured state of the fork

`feature/jira-plugin` vs `main`: **18 files, +3,442 / −11 lines**, merge base `d7a2ad4`
(Jul 23), currently **2 commits behind `main`** (1 commit ahead). Sole remote is
`origin git@github-work:adlerqa/wardeniq.git` — the second private repo does not exist
yet.

| Category | Content | Refactor risk |
|---|---|---|
| Entirely new files | `jira-app/**` (8 files, ~1.9k lines), `frontend/src/legacy/*` (2), `scripts/reset-admin-password.sh`, `tests/test_ext_jira.py` (628) | **none** |
| Contiguous additive block in `main.py` | 391 lines — 13 `/api/ext/jira/*` routes + 3 `/api/settings/jira-plugin-tokens` routes, all helpers, 3 Pydantic models | **low** → `api/routes/ext_jira.py` |
| Contiguous additive block in `store.py` | 54 lines — 6 `jira_plugin_token` methods | **low** → `store/jira_plugin.py` mixin |
| Seam edits in `main.py` | ~74 lines / 6 hunks: `ADMIN_PATHS`, `_min_role`, `_ext_bearer_token`, `_ext_principal`, `_feature_coverage_payload` extraction, `_jira_sync_feature` extraction, `jira_test` tweak | **high** — split across `core/security.py` + 2 routers |
| Small edits in `store.py` | collection handle, index creation, `feature_by_jira_key` | medium — 1–16 lines, stable locations |
| `coverage.py` | branch-name key extraction in `map_pr_to_feature` | **none — not actually private** |

Only ~590 of 3,442 lines touch files being decomposed, and 445 of those are contiguous
blocks that map one-to-one onto the target structure. **The fork is ~85% additive**,
which is what makes this tractable.

Verified decoupling: `jira-app/` is a Forge app (own `package.json`, `manifest.yml`) that
reaches the backend purely over HTTP paths (`/api/ext/jira/ping`, `/testcases`,
`/generate`, `/coverage`, `/test-plan`, `/overview`, `/features`, `/activity`,
`/jobs/{id}`). **Zero Python coupling** — the backend refactor cannot break it, given the
plan's hard constraint that no route path changes.

### 3.2 Why the refactor happens once, upstream

Splitting `main.py` into 20 files is **not a rename**, so git's rename detection
contributes nothing, and no `-X` strategy option resolves cross-file content moves.
`main.py` survives at 150–250 lines, so a downstream edit inside a region upstream
deleted arrives as a plain content conflict with no pointer to where the code went.

Therefore: **do all nine phases in the public repo and let the private repo inherit the
structure by merging.** Restructuring independently in both produces two divergent
20-file reorganizations that can never be reconciled — every future upstream pull becomes
permanent hand-merging. Inheriting is strictly less work downstream, not more.

The leverage is entirely upstream of git: **make the private branch stop modifying shared
files.**

### 3.3 Decisions taken

1. **`jira-app/` splits into its own private repo.** It's self-contained and
   HTTP-coupled only, so it needs no fork relationship at all. The wardenIQ private fork
   then carries only the `/api/ext/jira/*` backend surface plus the auth registration.
2. **All four seams get upstreamed** to the public repo.
3. **Public uses real merge commits** during the refactor window, and the private repo
   enables `git rerere`.

### 3.4 Upstreaming the four seams

Three of the private edits are not private:

- **`coverage.py` branch-name extraction** (`extract_keys(..., pr.get("head_ref", ""))`)
  — a general improvement with zero Jira coupling. Most teams name branches
  `ABC-123-add-login` without repeating the key in the title, so those PRs were going
  unmapped. Belongs in public `main` on its own merit.
- **`_feature_coverage_payload(fid)`** extracted from the `feature_coverage` route —
  behavior-neutral; a route handler that's a thin wrapper over a reusable function is
  simply better code.
- **`_jira_sync_feature(fid)`** extracted from `jira_sync` — same.

The fourth is genuinely private: a **second authentication scheme** (bearer token for the
plugin surface) alongside the cookie session, currently patched directly into the RBAC
gate. Upstream it as an **extension point**, not a fork:

```python
# core/security.py (PUBLIC). Empty upstream: the cookie session is the only way to
# authenticate in the open-source build. A downstream distribution registers an
# additional resolver instead of patching this file.
_PRINCIPAL_RESOLVERS: list = []   # [(path_prefix, fn), ...]

def register_principal_resolver(path_prefix: str, fn) -> None:
    """fn(request) -> user dict | None. Consulted only for paths under `path_prefix`,
    before cookie auth. First non-None wins. The prefix is part of the contract: a
    resolver can never authenticate a request outside its own surface."""
    _PRINCIPAL_RESOLVERS.append((path_prefix, fn))

def resolve_principal(request):
    path = request.url.path
    for prefix, fn in _PRINCIPAL_RESOLVERS:
        if path.startswith(prefix):
            u = fn(request)
            if u:
                return u
    return _cookie_principal(request)      # existing behaviour, unchanged
```

The private repo then contains one registration:

```python
register_principal_resolver("/api/ext/", _ext_principal)
```

The `path_prefix` in the contract is load-bearing: `tests/test_ext_jira.py` already
asserts "a plugin token works ONLY under `/api/ext/` (never on cookie/admin routes)," so
scope-limiting belongs in the registry rather than as private edits to public
`_min_role`. That single design choice converts a recurring conflict in the most
security-sensitive file in the codebase into one line that never conflicts.

Upstream the public half of this with tests proving the registry is empty by default and
that an unregistered prefix falls through to cookie auth — so the hook is covered even
though its only consumer is downstream.

For `store.py`, upstream the generic bits the same way if they're cheap (a
collection-handle registration point); otherwise accept two 1–3 line conflicts in stable
locations, which is a fair trade against inventing machinery for three lines.

### 3.5 Phase −1 execution order

Nothing here touches folder structure. The goal is to reach a state where the private
diff to shared files is ~zero **before** anything moves.

1. **Bring the private branch current.** It branched Jul 23 and is 2 commits behind.
   Merge `main` into `feature/jira-plugin` now, while the tree is still recognizable.
   Rebasing or merging across the refactor is dramatically worse than doing it before.
2. **Split out `jira-app/`.** New private repo, seeded with
   `git subtree split -P jira-app -b jira-app-only` so its history is preserved, then
   removed from the wardenIQ fork. Its CI is independent (Node/Forge, no Python).
3. **Upstream the four seams** to public `main` as normal reviewed PRs: the `coverage.py`
   fix, both helper extractions, and the resolver registry with its tests. Each is small
   and independently reviewable.
4. **Re-derive the private branch** on top of the updated public `main`. Its remaining
   diff should be: `api/ext` routes (still in `main.py` at this point), the
   `jira_plugin_token` store methods, `tests/test_ext_jira.py`, the one
   `register_principal_resolver(...)` line, and the `scripts/` helper. **Verify with
   `git diff --stat upstream/main...HEAD` that no shared file shows more than a few
   lines.** That number is the honest predictor of how painful every subsequent merge
   will be — if it isn't near zero, stop and find the remaining seam.
5. **Fix the six private `setattr(main, …)` rebinds** from 2.4 while you're in there.
6. **Create the PUBLIC repo fresh — do not flip visibility on the existing one.**
   See §3.5.1 below; this is the step with an irreversible failure mode.

### 3.5.1 Standing up the upstream/downstream pair

**Publication audit — already run, result: clean.** For the record, on 55 revisions:
`.env` never committed on any branch; no real credentials in history (the only `ghp_…`
matches are `ghp_xxxxxxxx` placeholders in README docs); no Mongo keyfile or `pwfile`
tracked (`config/` holds only `.conf` files and entrypoint scripts); all secrets are
env-var references defaulting to `change-me-in-production`; no internal audit docs
(`RBAC_ANALYSIS.md` is referenced in a code comment but was never committed). Re-run
this audit if more commits land before publication.

**The one hard constraint:** `origin/feature/jira-plugin` is the **only** remote branch
containing the private jira-app code (`git branch -r --contains 2be0ceb`).

**Therefore: create a new public repo; never change visibility on the existing one.**
Flipping `adlerqa/wardeniq` to public exposes its whole object database, including
`feature/jira-plugin`. Deleting that branch first is not sufficient — GitHub keeps
unreachable objects fetchable by SHA for an indeterminate window, and anyone who clones
or forks in that window keeps a copy. Publication is irreversible.

Pushing `main` to an empty repo transfers **only objects reachable from `main`**, so the
private commits never enter the public repo — clean by construction rather than by
cleanup, and reversible (delete the repo and retry). Critically, **pushing existing
commits to a new remote preserves their SHAs**, so the two repos share a real merge base
immediately: `git merge upstream/main` works with no grafting and no
`--allow-unrelated-histories`.

**Naming footgun.** Giving the public repo the canonical `adlerqa/wardeniq` name means
renaming the existing one, and GitHub's rename redirect will then resolve the old name to
the **new public repo**. A stale remote URL on a teammate's machine or in CI could push
private code into it. Hence the strict order below — update every clone between the
rename and the create.

```bash
# 1. Bring the private branch current first (it is 2 commits behind) — step 1 above.
git checkout feature/jira-plugin && git merge main

# 2. Rename the private repo: adlerqa/wardeniq -> adlerqa/wardeniq-enterprise
gh repo rename wardeniq-enterprise --repo adlerqa/wardeniq

# 3. Update EVERY local clone and CI config before step 4. This is the mitigation.
git remote set-url origin git@github-work:adlerqa/wardeniq-enterprise.git

# 4. Create the public repo EMPTY — no README, no license, no .gitignore. An auto-init
#    commit creates an unrelated root and destroys the shared merge base.
gh repo create adlerqa/wardeniq --public

# 5. Push ONLY main, with an explicit refspec.
git remote add upstream git@github-work:adlerqa/wardeniq.git
git push upstream main:main

# 6. Verify before trusting it.
git ls-remote upstream                                     # expect ONLY refs/heads/main
git ls-tree -r upstream/main --name-only | grep jira-app   # expect empty

# 7. Wire the downstream side.
git config rerere.enabled true
git config rerere.autoupdate true
git fetch upstream && git merge upstream/main   # no-op / fast-forward — identical SHAs
```

**Never `git push upstream --all` or `--mirror` from this clone** — either pushes
`feature/jira-plugin` and undoes the whole exercise. The explicit `main:main` refspec is
the safety mechanism; back it with the pre-push hook in §3.7.

That final merge being a no-op is the proof the topology is correct **before** any code
moves. Do all of this before Phase 0: proving the pipeline on a trivial merge means that
when a later merge is messy, you know the mess is the refactor and not the plumbing.

Optional pre-publication cleanup: history contains
`Aman <aman@Puneets-MacBook-Pro.local>`, a machine-local email that leaks a laptop name
and mis-attributes commits. Publishing makes it permanent. Fix cosmetically with a
`.mailmap` (no history rewrite):
```
Aman <aman@adlerqa.in> <aman@Puneets-MacBook-Pro.local>
```
Also skim `git log --oneline main` (51 commits) for messages you would rather not
publish.

### 3.6 Merge-down cadence during the refactor

After each phase lands in public, merge it down and run the private suite:

```bash
git fetch upstream && git merge upstream/main
pytest -m "not dbintegration"        # private suite, incl. test_ext_jira.py
```

Nine small merges, never one big one. Expected conflicts, given a near-zero shared-file
diff:

| Public phase | Private impact |
|---|---|
| 1, 2, 4, 7, 8 | none — private touches no file in these |
| 3 | none once `launch_job` rebinds are fixed |
| 5 (`store/` split) | move the 6 `jira_plugin_token` methods into a new `store/jira_plugin.py` mixin and add it to the `Store` bases — one file, one line |
| 6 (routers) | move the 391-line block into `api/routes/ext_jira.py` and `include_router` it — one file, one line |
| 9 (`coverage.py`) | none |

So the entire private cost of a nine-phase, 11,000-line restructuring is **two new files
and two registration lines** — provided Phase −1 is done properly. That is the whole
argument for doing Phase −1 first.

When a conflict does appear and you need to find where code moved,
`git log -S'<distinctive snippet>' --oneline` locates the commit that introduced it at
its new path — far faster than reading 20 router files. `rerere` then replays the
resolution if the same conflict recurs on a later merge.

### 3.7 Guardrails against leaking private code into public

Ordinary care isn't enough with two same-shaped repos and a shared folder layout:

- Distinct remote names (`upstream` = public, `origin` = private) and **never** a
  `git push upstream` from the private clone. Branch protection on public `main`.
- A public CI check that fails if `jira-app/`, `ext_jira`, `/api/ext/`, or
  `jira_plugin_token` appears in a PR — cheap, and it catches the one mistake that
  can't be undone.
- A pre-push hook in the private clone rejecting pushes whose remote URL isn't the
  private one.
- Merges flow **one way only**: public → private. A fix authored in private that belongs
  upstream gets cherry-picked into a fresh branch off public `main` and reviewed as its
  own PR — never merged back wholesale.

---

## 4. Non-negotiable constraints

- **Single FastAPI service.** Reorganize files inside `app/`; no microservices, no
  separate frontend service, no new datastore dependency.
- **All Mongo access stays behind the store layer.** "No DB calls outside `store.py`"
  becomes "no DB calls outside the `store/` package." Routers, workers, and services
  never touch `pymongo`/`mongot` directly.
- **One DB connection / one `Store` instance.** `store = Store(...)` is a module-level
  singleton; preserve exactly one live connection and one instance.
- **Middleware order is security-critical.** `auth_gateway` and `security_headers` are
  registered in a specific order. Preserve it exactly.
- **Background threads start exactly once.** `poller()`, `_stale_job_sweeper()`,
  `_import_reanalysis_scheduler()`. No double-starts (e.g. under `--reload`), no dropped
  threads.
- **Webhook signature verification moves verbatim.** GitHub HMAC
  (`hmac.compare_digest`) and GitLab shared-token comparison are a security boundary,
  not a cleanup opportunity.
- **No route path, method, or response shape changes.** Pure file organization — and in
  this topology it's also what keeps the Forge app working, since `jira-app/` is bound to
  those paths over HTTP. Behavior changes are separate PRs, after the migration.
- **`@app.on_event("startup")` stays as-is for now.** Deprecated in favor of lifespan
  handlers, but swapping it changes startup ordering. Do it after Phase 7, never during.

---

## 5. Current shape (baseline)

### `app/main.py` (7,225 lines), in file order

1. Env/config constants — Mongo URI, Ollama URL, model names, thresholds, feature flags,
   `MINDMAP_SAMPLES` — roughly the first 130 lines.
2. `FastAPI()` construction; custom handler for invalid Mongo ObjectIds.
3. ~30 helpers: `current_llm()`, `current_embedder()`, `current_ollama_url()`,
   `current_poll_interval()`, git-provider clients (`gh_client_for_project`,
   `gl_client_for_project`, `_provider_client`, …), repo abstraction
   (`_repo_list_commits`, `_repo_get_archive`, `_repo_branch_sha`, …).
4. RBAC layer — ~26 functions (`_is_public`, `_is_admin_only_route`, `_min_role`,
   `_target_project_for_path`, `_require_project`, `_require_feature_project`,
   `_require_case_project`, `_require_run_via_feature`, …) plus the two
   `@app.middleware("http")` functions.
5. `_audit(...)`.
6. `bootstrap()`, `_startup()`, `_stale_job_sweeper()`, `_ensure_app_secret()`,
   `_check_app_secret()`, `_check_production_posture()`.
7. Job infrastructure: `launch_job`, `run_tracked`, and `_gen_worker`,
   `_validator_worker`, `_code_coverage_worker`, `_test_repo_scan_worker`,
   `_test_import_worker`, `_ingest_worker`, `_reembed_worker`, `_migrate_worker`,
   `_codeanalysis_worker` (the repo-scan worker alone is ~230 lines).
8. **165 route handlers and 43 Pydantic models, interleaved** — see Section 7.
9. The GitHub/GitLab poller (`poller`, `sync_repo`, `_ts`, `_oid`), webhook signature
   verification, and the two `/api/webhook/*` endpoints.
10. Static mount (`static-react/`) and SPA fallbacks (`/`, `/invite`, favicon).

### `app/store.py` (3,889 lines)

One `class Store`, **257 methods**: projects, features (+ versioning/diffing), steps,
test cases, jobs, users/auth, repos + PRs, `code_chunks` + code-coverage runs, validator
runs, test-plan runs, cycles + templates, documents, settings, usage, the sheet-import
row pool, audit logs, dashboard aggregation, search-degradation tracking (`_degraded`,
`search_degraded()`, new in `2d284d2`), and the mongot search/vectorSearch queries
behind all of it. No section markers — domains are identifiable only by method-name
prefix.

### Other `app/*.py` — already single-purpose, leave as-is

`auth.py`, `automation.py`, `contracts.py` (new since this plan was drafted — see 0.1;
same profile, pure static analysis, no FastAPI/Store coupling), `crypto.py`,
`email_send.py`, `embeddings.py`, `extract.py`, `figma.py`, `github.py`, `gitlab.py`,
`grounding.py`, `jira.py`, `llm.py`, `prompts.py`, `report.py`, `reset_password.py`,
`s3_storage.py`, `sheet_import.py`, `test_plan.py`, `usage.py`, `validator.py`,
`weblinks.py`, `testgen/`. These need only re-importing from new call sites.
(`coverage.py` → Phase 9. `workers.py` → done, 2.1. `app/test_password_reset.py` /
`app/test_validator_gen.py` confirmed **not** collected by pytest — `pytest.ini`'s
`testpaths = tests` scopes collection to `tests/` only; no move needed.)

---

## 6. Target folder structure

```
app/
  main.py                     # app construction, include_router() calls, startup
                              # wiring, static mount, test re-export block. 150-250 lines.
  core/
    config.py                 # all env-derived constants (MONGO_URI, EMBED_MODEL, …)
    state.py                  # singletons: store, SYNC dict, job registry
    security.py               # auth_gateway + security_headers + ~26 RBAC helpers
                              #   + the principal-resolver registry (Section 3.4)
    deps.py                   # current_llm/current_embedder, git clients, repo helpers
    exceptions.py             # _InvalidId handler
    audit.py                  # _audit(...)
    bootstrap.py              # bootstrap(), _ensure_app_secret, _check_production_posture
  workers/                    # requires deleting app/workers.py first — see 2.1
    registry.py               # launch_job(), run_tracked(), job-type → worker map
    generation.py             # _gen_worker, _ingest_worker, _reembed_worker, _migrate_worker
    validator_worker.py
    code_coverage_worker.py
    codeanalysis_worker.py    # _codeanalysis_worker (Mind Map)
    repo_scan_worker.py       # _test_repo_scan_worker + private helpers
    test_import_worker.py     # _test_import_worker
  background/
    poller.py                 # poller(), sync_repo(), _ts, _oid, signature verification
    schedulers.py             # _stale_job_sweeper, _import_reanalysis_scheduler
  api/
    schemas.py                # Pydantic models shared by 2+ routers (avoids cycles)
    routes/
      auth.py           users.py         projects.py        features.py
      steps_test_cases.py     jobs_usage.py    test_import.py     validator.py
      test_plan.py            repos_prs.py     jira_atlassian.py  code_coverage.py
      settings.py             documents.py     test_cycles.py     reports_exports.py
      develop.py              webhooks.py      system.py          static_spa.py
      # PRIVATE REPO ONLY: ext_jira.py
  store/
    __init__.py               # composes Store from mixins; keeps `store = Store(...)`
    base.py                   # Mongo client/db handle, index setup, shared helpers
    projects.py       features.py        steps_test_cases.py   jobs.py
    users_auth.py     repos_prs.py       code_coverage.py      validator_runs.py
    test_plan_runs.py test_cycles.py     documents.py          settings.py
    usage.py          sheet_import.py    audit.py              dashboard.py
    # PRIVATE REPO ONLY: jira_plugin.py
```

The two `PRIVATE REPO ONLY` files are the entire structural footprint of the fork
(Section 3.6). Everything else is identical in both repos, which is what makes
`git merge upstream/main` clean.

File names under `api/routes/` and `store/` come from route prefixes and method-name
prefixes **actually present in the code**, not an idealized design, so the mapping stays
mechanical. `store/__init__.py` must be importable as `from store import Store` so every
existing `store.get_feature(...)` call site keeps working — the single most important
compatibility decision in the plan (Phase 5).

One naming caution: `store/settings.py`, `store/usage.py`, and `store/sheet_import.py`
share names with top-level modules. Python 3 absolute imports make this unambiguous
(inside the package, `import sheet_import` gets `app/sheet_import.py`;
`from . import sheet_import` gets the submodule) but it reads confusingly. Either accept
it with a comment in `store/__init__.py` or suffix the submodules (`usage_store.py`).
Decide once, up front — and identically in both repos.

---

## 7. Route → router-file mapping (verified, current line numbers)

**Routes for the same domain are scattered through `main.py`, not contiguous.** Feature
routes sit at 2508, 2518, 2811, 2849, 3069, 3082, 3409, 3801, 5680, 5694. Project routes
at 3430, 3453, 3459, 5646, 5669. Test-case routes at 3123, 3152, 3353, 3381, 5712, 5731,
5740.

So Phase 6 is **not** a series of line-range cut-and-pastes. For each router file, collect
handlers by path prefix
(`grep -n '@app\.\(get\|post\|put\|delete\|patch\)("/api/features' main.py`), move each
handler **plus every helper and Pydantic model it uses**, and delete it from `main.py` in
place. A helper used by two router groups goes to `core/deps.py` or `api/schemas.py` —
never duplicated.

| Router file | Routes | Line locations in `main.py` |
|---|---|---|
| `test_import.py` | 10 | 1892–2394 (contiguous) |
| `features.py` | 10 | 2508, 2518, 2811, 2849, 3069, 3082, 3409, 3801, 5680, 5694 |
| `system.py` (status, dashboard, tags, retrieve, sync) | 5 | 2407, 3110, 3118, 3397, 7075 |
| `jobs_usage.py` | 6 | 2946–3059 |
| `steps_test_cases.py` | 11 | 3093, 3103, 3123, 3152, 3353, 3381, 5712, 5731, 5740, 5753, 5759 |
| `validator.py` | 5 | 3158–3235 (contiguous) |
| `test_plan.py` | 5 | 3253–3327 (contiguous) |
| `projects.py` | 5 | 3430, 3453, 3459, 5646, 5669 |
| `repos_prs.py` (PATs, branches, rescan, ratelimit) | 20 | 3497–3792, 4099–4139, 5764 |
| `jira_atlassian.py` | 5 | 3584, 3598, 3609, 5587, 5599 |
| `code_coverage.py` (mindmap, analyze, commit-analysis) | 16 | 3809–4059, 6146–6267 |
| `settings.py` (db-status/config/migrate, smtp, s3, ollama, llm test) | 9 | 4155, 4281, 4462, 4485, 5177, 5271, 5307, 5406, 5426 |
| `auth.py` | 13 | 4620–4985 (contiguous) |
| `users.py` (audit-logs, invites) | 8 | 5013, 5057, 5102, 5155, 5171, 5346, 5372, 5391 |
| `documents.py` | 5 | 5446–5531 (contiguous) |
| `test_cycles.py` (cycle CSV/PDF export, templates) | 17 | 6321–6496 (contiguous) |
| `reports_exports.py` (feature PDF/CSV, gap exports) | 7 | 6501–6594 (contiguous) |
| `develop.py` | 1 | 6656 |
| `webhooks.py` (jira, github, gitlab) | 3 | 6695, 7092, 7140 |
| `static_spa.py` | 4 | 7207, 7212, 7213, 7218 |
| **Total** | **165** | ✓ matches the decorator count |
| *`ext_jira.py` (private only)* | *16* | *one contiguous 391-line block* |

The 43 Pydantic models are likewise scattered; each belongs with its router. Anything used
by two routers goes to `api/schemas.py` rather than being imported router-to-router,
which would create a cycle.

---

## 8. Phase 0 — Safety net

1. Branch off latest public `main` (`refactor/backend-structure`) and **tag the
   pre-refactor commit** (`git tag pre-refactor-baseline`) in **both** repos.
2. **Freeze a route inventory:**
   ```bash
   cd app && python -c "import json,main; print(json.dumps(main.app.openapi(), indent=2, sort_keys=True))" \
     > ../refactor-baseline/openapi.json
   ```
   Regenerate and `git diff` after **every** phase; any non-whitespace difference is a
   regression. Sorting keys stops router-inclusion order producing spurious diffs. Do
   this in the private repo too — its baseline has 181 routes, and the 16 `ext/jira` ones
   must survive untouched.
3. **Freeze a Store method inventory:**
   ```bash
   cd app && python -c "import inspect,store; print('\n'.join(sorted(f'{n}{inspect.signature(m)}' for n,m in inspect.getmembers(store.Store, inspect.isfunction))))" \
     > ../refactor-baseline/store-methods.txt
   ```
   Expect 257 public / 264 private. Must diff clean after Phase 5.
4. **Enumerate the `main.<attr>` couplings** from 2.4 into
   `refactor-baseline/main-namespace-refs.txt` — the re-export list and the ten rebinds.
   This is the difference between a planned three-line fix in Phase 2 and a confusing
   wall of red.
5. **Record the test baseline** with the exact CI commands so local and CI agree:
   `pytest -m "not dbintegration"`, and with Mongo available
   `MONGO_TEST_URI=mongodb://localhost:27017 pytest -m dbintegration -v`. Write down both
   counts, in both repos. No phase merges with fewer passing tests than the previous one.
6. **Snapshot ruff and mypy** (`ruff check app tests`, `mypy app --ignore-missing-imports`).
   Since CI treats both as informational, this snapshot is your only signal that a phase
   didn't add dead imports or type breakage. Diff each phase — counts should fall, never
   rise.
7. **Manual smoke checklist** for what unit tests structurally can't cover: login (OTP
   *and* password), create project, connect a GitHub repo, upload a requirement doc and
   generate a feature, run validator + test-plan, sync a PR and check coverage, trigger a
   Mind Map run, export a PDF and a CSV, POST a signed payload to both webhook endpoints.
   Run it against the real docker-compose stack after each phase — the poller, webhooks,
   and background workers are exactly where request/response assertions won't save you,
   and vectorSearch paths aren't in CI at all. In the private repo, add: Forge app loads,
   panel renders, generate-from-issue round-trips.
8. Confirm `docker compose config --quiet` and `docker build -f app/Dockerfile` pass on
   the baseline, so a later failure is unambiguously yours.

---

## 9. Phase 1 — Config and core state

Move the ~130 lines of env-derived constants (`MONGO_URI`, `EMBED_MODEL`, `GEN_MODEL`,
`MINDMAP_SAMPLES`, `STEP_AUTO`, `GITHUB_API`, `POLL_INTERVAL_FALLBACK`,
`IMPORT_SEMANTIC_MATCH`, `ENV_FILE_PATH`, …) into `core/config.py` unchanged, with any
`.env`-persistence helpers.

Move the true singletons — the `store` instance, the `SYNC` dict shared by the poller and
`/api/sync/status`, any in-memory job dict — into `core/state.py`. Code that reached these
as `main.py` globals does `from core.state import store, SYNC` instead.

Prefer explicit imports over `from core.config import *`; the wildcard works
transitionally but defeats the ruff dead-import signal from Phase 0.6. Run the full suite
plus the smoke checklist. This phase touches no route logic — the safest first PR, and
where you confirm in practice that flat subpackage imports resolve in the container, under
pytest, and via `run.sh`.

---

## 10. Phase 2 — Cross-cutting helpers (RBAC, deps, exceptions, audit)

Every route depends on these, so do it early and carefully, before touching any route.

1. **`core/security.py`** — move verbatim: `_is_public`, `_is_admin_secret_write`,
   `_is_admin_only_route`, `_target_project_for_path`, `_min_role`, `_current_user`,
   `_user_all_projects`, `_user_can_access_project`, `_allowed_project_ids`,
   `_require_project`, `_project_of_feature`, `_project_of_repo`, `_project_of_cycle`,
   `_require_feature_project`, `_require_repo_project`, `_require_cycle_project`,
   `_case_project_ids`, `_require_case_project`, `_require_job_project`,
   `_require_run_via_feature`, `_require_validator_run_project`,
   `_require_test_plan_run_project`, `_require_code_coverage_run_project`,
   `_require_commit_analysis_project`, `_filter_projects_for`, `_project_public`, both
   middleware functions, **and the principal-resolver registry from Section 3.4.**
   Register the middleware in the same order in the new `main.py`.
2. **`core/deps.py`** — `current_ollama_url`, `current_poll_interval`, `current_embedder`,
   `current_llm`, `project_github_token`, `project_gitlab_token`,
   `gh_client_for_project`, `gl_client_for_project`, `gh_client_with_token`,
   `current_token`, `gh_client`, `_provider_client`, `_repo_list_commits`,
   `_repo_get_commit`, `_repo_branch_sha`, `_repo_get_archive`, `_repo_list_branches`,
   `_is_app_repo`, `_implementation_repo_docs`, `_webhook_base_url`.
3. **`core/exceptions.py`** — the `_InvalidId` handler.
4. **`core/audit.py`** — `_audit(...)`.
5. **`core/bootstrap.py`** — `bootstrap()`, `_ensure_app_secret()`, `_check_app_secret()`,
   `_check_production_posture()`, `_search_unsupported()`, `_search_index_limit()`.
6. **Apply the 2.4 mitigation**: add the re-export block to `main.py`, and fix the four
   public `setattr(main, …)` rebinds.

**The nine RBAC suites are the gate for this phase.** Run them first
(`pytest tests/test_rbac_*.py tests/test_api_routes.py -v`) — they drive the real app and
middleware through TestClient, so a broken move surfaces as a test failure rather than a
silent security hole.

Watch the one real trap: `core/security.py` needs `store` from `core/state.py`, and
`core/deps.py` needs both `config` and `state`. Keep the graph a DAG — `config` depends on
nothing, `state` on `config` and `store`, everything else on those. Needing a
function-level import to break a cycle means a helper is in the wrong module.

**This is also where the `embedder` singleton gets wired — see Section 2.6.**
`core/state.py` (Phase 1) must declare `embedder = None` as a placeholder rather than
computing it, and `core/deps.py` (this phase) fills it in as an import-time side effect
— `state.embedder = current_embedder()` — after `current_embedder()` is defined. Doing
it the other way around (state.py calling into deps.py to build its own singleton) is
the circular import. Confirm this actually works by importing the new `main.py` cold
(`python -c "import main"`, same trick Phase 0's OpenAPI generation uses) before moving
on to Phase 3.

---

## 11. Phase 3 — Job infrastructure and workers

1. **`workers/registry.py`** — `launch_job`, `run_tracked`, the job-type → worker map.
   (Delete `app/workers.py` first — 2.1.)
2. One file per worker: `generation.py` (`_gen_worker`, `_ingest_worker`,
   `_reembed_worker`, `_migrate_worker` — grouped because they share the generation
   pipeline), `validator_worker.py`, `code_coverage_worker.py`, `codeanalysis_worker.py`
   (heavily modified in `2d284d2`; make sure 2.2's fix has landed first),
   `repo_scan_worker.py` (`_test_repo_scan_worker` plus `_create_imported_testcase`,
   `_case_exists`, `_promote_imported_row_to_feature`, `_parsed_row_from_payload`,
   `_sheet_steps_preview`, `_feature_doc_for_import_context`,
   `_reuse_existing_import_rows`, `_import_evidence_ok`, `_cosine`,
   `_feature_embedding`, `_pool_row_embedding`, `_rescan_pool_for_feature`,
   `_apply_import_overlays`), and `test_import_worker.py`.
3. Workers currently close over `main.py` globals (`store`, `current_llm()`,
   `current_embedder()`); these become explicit imports from `core.state` / `core.deps`.
   Mechanical — resist refactoring worker internals in the same pass. **One exception,
   not mechanical:** `_reembed_worker` contains the app's only `global embedder`
   reassignment (verified — a full `global` scan of `main.py` found exactly this one).
   In `workers/generation.py` it must become `from core import state` +
   `state.embedder = current_embedder()`, never `from core.state import embedder` +
   `global embedder` (that would rebind this module's own local copy, not
   `core.state`'s, and every other file reading `state.embedder` would keep seeing the
   stale pre-switch object forever — see Section 2.6).
4. **Trigger one job of every type end-to-end.** Workers run on background threads;
   pytest will not catch a broken one. Generate a feature, run a validator, run code
   coverage, scan a repo, import a sheet, run a Mind Map analysis, and confirm each
   reaches a terminal state in `/api/jobs` rather than "worker heartbeat lost".

---

## 12. Phase 4 — Background threads

1. **`background/poller.py`** — `poller()`, `sync_repo()`, `_oid`, `_ts`,
   `_verify_github_signature`, `_ACCEPTED_GH_ACTIONS`, `_ACCEPTED_GL_ACTIONS`. Keep the
   signature logic byte-identical; do not "simplify" `hmac.compare_digest`.
2. **`background/schedulers.py`** — `_stale_job_sweeper`, `_import_reanalysis_scheduler`.
3. Wire startup exactly as before: the `@app.on_event("startup")` handlers calling
   `threading.Thread(target=…, daemon=True).start()`, same order, same count. Verify with
   a temporary log line that each loop starts **exactly once per process**, including
   under `uvicorn --reload` — `--reload` plus a module-level `.start()` is the classic
   double-start bug.
4. The `/api/webhook/*` *handlers* move in Phase 6; this phase moves only the *logic* they
   call, so the later extraction is a thin wrapper.

---

## 13. Phase 5 — Split `store.py` into domain modules

Highest-effort, highest-value phase. Two mechanics — pick one and be consistent.

**Option A — mixin composition (recommended).** Each domain file defines a class holding
only its methods (`class ProjectsMixin` in `store/projects.py`, no `__init__`, sharing the
`self.db` / collection attributes set up in `store/base.py`). `store/__init__.py` declares
`class Store(ProjectsMixin, FeaturesMixin, …, BaseStore)` and nothing else changes at any
call site — `store.get_feature(x)` resolves identically via the MRO. **This preserves all
257 methods and every call site with zero edits outside `store/`**, which is exactly the
"every functionality intact" requirement. It also makes the private fork's addition a
single new mixin file rather than a diff inside a shared file. Risk is contained to
partitioning methods correctly.

**Option B — composition (`store.projects.get(...)`).** Cleaner long-term OOP, but it
means rewriting well over a thousand call sites across `main.py` and every worker — a far
larger, far riskier diff, and downstream it would rewrite the private routes too. **Don't
do it now.** If the team wants composition eventually, do it after Option A has proven the
boundaries, with IDE-assisted renames.

**Verified against the actual `Store` class (2026-08-15) — three collection-access
patterns coexist, and `store/base.py` must own all of them, not just `__init__`:**

1. **20 collections cached as plain attributes in `__init__`** (`self.projects =
   self.db["projects"]`, …) — note several use a *different* name than the underlying
   collection (`self.assoc` → `"associations"`, `self.cases` → `"test_cases"`,
   `self.prs` → `"pull_requests"`, `self.coverage` → `"pr_coverage"`, `self.fchunks` →
   `"feature_chunks"`, `self.code_cov` → `"code_coverage"`, `self.documents` →
   `"stored_documents"`). Keep these exact aliases — a mixin that "cleans up" a name
   mismatch breaks every existing call site silently.
2. **11 collections exposed as `@property`, scattered through the file, not in
   `__init__` at all** — `feature_imports`, `project_imported_rows`,
   `project_imported_row_sources`, `project_imported_row_feature_map`,
   `project_imported_row_promotions`, `project_imported_row_corrections`,
   `import_analysis_status`, `audit`, `code_coverage_runs`, `automation_coverage`,
   `test_repo_cases`. These are already lazy accessors (`return
   self.db["feature_imports"]`) — the existing style, so `store/base.py` should follow
   the same pattern for anything it centralizes rather than inventing a fourth style.
3. **Collections touched only via a bare `self.db["name"]` literal inline in a method
   body, cached nowhere** — at least `jobs`, `settings`, `test_cycles`,
   `cycle_templates`, `audit_logs`. These are easy to miss when partitioning, since
   there's no single attribute definition to grep for and move — search for the literal
   string across the whole file, not just for `self.db[` assignments.

**Exact member accounting** (needed because a naive `inspect.getmembers(Store,
inspect.isfunction)` undercounts — verified by generating the real inventory): `grep -c
'^    def '` gives **257**, which decomposes as **242 plain methods + 11 `@property` +
3 `@staticmethod` + 1 dunder (`__init__`)**. The Phase 0 baseline script (Section 8)
must bucket by all four, or a lost `@staticmethod` or `@property` during the split
would slip past a script that only checks `inspect.isfunction`. No duplicate
method/property names exist in the current class (checked) and no test subclasses or
inspects `Store.__mro__`/`__bases__` (checked) — both are genuinely clear for Option A.

Steps for Option A:

1. **`store/base.py`** — Mongo client/db setup, `ensure_indexes()`, the `_degraded` dict
   and `search_degraded()` / `_numpy_fallback_ok()` machinery (cross-cutting by nature),
   `_oid`, and other shared private helpers.
2. **Partition the 257 methods** by the prefixes already in the code: `projects.py`
   (`*_project*`), `features.py` (`*_feature*`, version/diff), `steps_test_cases.py`
   (`*_step*`, `*_case*`), `jobs.py` (`*_job*`), `users_auth.py` (`*_user*`, invites),
   `repos_prs.py` (`*_repo*`, `*_pr*`), `code_coverage.py` (`*code*`, `*_coverage*`,
   `code_chunks`, `code_index`), `validator_runs.py`, `test_plan_runs.py`,
   `test_cycles.py`, `documents.py`, `settings.py` (`*_settings*`, `*_db_config*`),
   `usage.py`, `sheet_import.py` (`*_imported_*`, `*_pool*`), `audit.py`, `dashboard.py`.
   A few cross-domain joins won't fit neatly — put them where they most belong with a
   one-line comment, rather than forcing an artificial boundary.
3. **Diff against the Phase 0 inventory** — must match exactly. A mismatch means a method
   was dropped, renamed, or duplicated across mixins, where Python's MRO silently picks
   one. Treat **any duplicate name across mixins as a hard error**:
   ```python
   def test_no_duplicate_store_methods():
       from collections import Counter
       import store
       names = [n for cls in store.Store.__mro__[1:] if cls is not object
                for n in vars(cls) if not n.startswith('__')]
       assert [n for n, c in Counter(names).items() if c > 1] == []
   ```
   Ship this test upstream — it's what protects the private repo's added mixin from
   silently shadowing a public method.
4. Run the full suite **and** `dbintegration` against real Mongo — the one phase where
   index creation and aggregation-pipeline behavior can break in ways mocked tests can't
   see. Then the smoke checklist, since vectorSearch isn't in CI.
5. **Private merge-down:** create `store/jira_plugin.py` with the 6 `jira_plugin_token`
   methods and add the mixin to the `Store` bases. One file, one line.

---

## 14. Phase 6 — Split `main.py` routes into routers

With config, security, deps, workers, and background threads extracted, this is mechanical
— but see Section 7: handlers are **scattered**, so work by path prefix, not line range.

1. Each `api/routes/*.py` gets `router = APIRouter()`; handlers move with the decorator
   changed from `@app.get(...)` to `@router.get(...)` and **nothing else** — same path
   string, same status codes, same response model, same dependencies. Move each handler's
   models and private helpers with it; anything shared by two routers goes to
   `api/schemas.py` or `core/deps.py`.
2. **Extraction order** — most self-contained first, so the pattern is proven before it
   reaches what everything depends on:
   1. `documents.py`, `test_cycles.py`, `reports_exports.py` — CRUD and exports,
      contiguous, few dependencies. Ideal first PRs.
   2. `auth.py`, `users.py` — contiguous and self-contained but security-sensitive;
      re-run the nine RBAC suites explicitly.
   3. `settings.py`, `jira_atlassian.py`, `repos_prs.py`.
   4. `steps_test_cases.py`, `validator.py`, `test_plan.py`, `test_import.py`.
   5. `projects.py`, `features.py` — scattered and touched by almost everything; do these
      once the pattern is rehearsed.
   6. `jobs_usage.py`, `code_coverage.py`, `develop.py` — heaviest dependency on Phase 3.
   7. `webhooks.py`, `system.py`, `static_spa.py` — last. `static_spa.py` must be included
      **after** every other router, since `app.mount("/assets", …)` and the SPA fallbacks
      are catch-all-ish and mount order matters.
3. **After each individual router file**, regenerate the OpenAPI dump, confirm a clean
   diff, run the full suite. Land one file at a time — never batch extractions into one
   commit, so a regression is trivially bisectable.
4. When done, `main.py` holds only: app construction and middleware registration,
   `include_router(...)` calls, Phase 4 startup wiring, the static mount, and the 2.4
   re-export block. Target 150–250 lines.
5. **Private merge-down:** move the 391-line block into `api/routes/ext_jira.py` and
   `include_router` it. One file, one line. Confirm the private OpenAPI diff still shows
   all 16 `/api/ext/jira/*` and `/api/settings/jira-plugin-tokens` paths **unchanged** —
   the Forge app is bound to those strings over HTTP.

---

## 15. Phase 7 — Cleanup

1. Re-check imports in every new file; remove dead imports from `main.py` (except the
   deliberate 2.4 re-exports, which need the `# noqa: F401` and the comment explaining
   why). Diff ruff and mypy against the Phase 0 snapshot — counts should have dropped.
   Confirm the dependency graph is still a DAG with no function-level imports added to
   break cycles.
2. Confirm `Dockerfile`, `run.sh` / `run.ps1`, `pytest.ini`, and `docker-compose*.yml` are
   **unchanged and still correct** (`uvicorn main:app` from `app/`, per Section 1). If any
   needed editing, something diverged from the flat-import decision — investigate rather
   than patching the config.
3. Re-run both inventory diffs against `pre-refactor-baseline`, in both repos.
4. Update `PROJECT_CONTEXT.md`, `README.md`'s layout section, and the project instructions
   to describe the new layout, so the next contributor doesn't recreate the monolith. State
   the new invariants explicitly: **no DB access outside `store/`, no route handlers in
   `main.py`.** In the private repo, document that `ext_jira.py` and `jira_plugin.py` are
   the only fork-local files and that everything else must stay byte-identical to upstream.

---

## 16. Phase 8 — Backfill tests

Not required to ship, but do it while the boundaries are fresh: a unit test per `store/`
module (mock the collection, assert query shape) and, per `api/routes/` file, one happy
path plus one RBAC-denied case. The RBAC half is largely covered; the `store/` half is the
gap. This is what makes the *next* change to any domain safe without a full manual smoke
pass.

---

## 17. Phase 9 (optional) — Split `coverage.py`

Now 1,125 lines across seven concerns. The natural split follows the existing clusters:

- `coverage/grounding.py` — `citation_index`, `resolve_citation`, `strip_citations`,
  `candidate_symbols`, `_symbols_supported`, `_ground_verdict`
- `coverage/windowing.py` — `window_excerpts`, `_merge_windows`, `_reconcile_samples`,
  `excerpt_total_chars`, `_code_excerpt_block`, `_trunc_marker`
- `coverage/review.py` — `review_code_coverage`, `_codereview_prompt`, `_beat`,
  `INDEX_RULES_FINGERPRINT`, `is_test_file`
- `coverage/pr_mapping.py` — `map_pr_to_feature`, `extract_key(s)`, `pr_text`,
  `verify_pr_implementation`, `review_coverage`, `compute_unmapped_changes`, `diff_runs`
- `coverage/analysis.py` — `analyze_impact`, `diff_versions`, `generate_feature_code`

Same mechanics as the store split: a package `__init__.py` re-exporting every public name
so `import coverage` and `cov.review_code_coverage(...)` keep working. The PyPI shadowing
caveat from 2.3 applies to the package name too. Also fold in wiring up `scanners.py` here
if you deferred it — it's designed to corroborate exactly these verdicts.

---

## 18. Rollout mechanics

One PR per phase — or per sub-step within Phase 6 — never one giant PR, each independently
revertable. Merge in phase order; don't start Phase N+1 until Phase N is green on tests,
the OpenAPI diff, and the smoke checklist. **After each public phase lands, merge it down
to the private repo and run the private suite** (Section 3.6) — nine small merges, never
one big one. Public uses real merge commits throughout; private has `rerere` enabled.

Keep the `pre-refactor-baseline` tag indefinitely in both repos as the reference for "did
this behavior exist before the refactor." If a regression appears post-merge, revert the
one phase's PR rather than forward-fixing — small phases make that cheap, and that
cheapness is the point of the phasing.

---

## 19. Checklist

**Phase −1 — topology (before anything moves)**

- [ ] Merge current `main` into `feature/jira-plugin` (it's 2 commits behind)
- [ ] `git subtree split -P jira-app` → new private Forge-app repo; remove from the fork
- [ ] Upstream seam 1: `coverage.py` branch-name key extraction
- [ ] Upstream seam 2: `_feature_coverage_payload` extraction
- [ ] Upstream seam 3: `_jira_sync_feature` extraction
- [ ] Upstream seam 4: principal-resolver registry + tests (empty by default)
- [ ] Re-derive private branch; **verify `git diff --stat upstream/main...HEAD` shows
      ~zero lines in shared files**
- [ ] Fix the 6 private `setattr(main, …)` rebinds
- [ ] Re-run the publication audit if new commits landed (§3.5.1)
- [ ] Rename existing repo → `wardeniq-enterprise`; update **every** clone + CI remote URL
- [ ] Create **empty** public `adlerqa/wardeniq` (no README/license/gitignore auto-init)
- [ ] `git push upstream main:main` — explicit refspec, never `--all` / `--mirror`
- [ ] Verify: `git ls-remote upstream` shows only `main`; no `jira-app` in `upstream/main`
- [ ] `rerere` on; `git merge upstream/main` is a no-op → topology proven
- [ ] Optional: `.mailmap` for the machine-local author email
- [ ] Guardrails: public CI leak check, pre-push hook, branch protection

**Pre-flight**

- [x] 2.1 — `app/workers.py` moved to `_to_delete/` (dead-code confirmed; true delete
      blocked by the device bridge — run `rm -rf _to_delete && git add -A` locally to finish)
- [x] 2.2 — `INDEX_RULES_FINGERPRINT` already fixed to `hashlib.sha256` over 5 rules
      (exceeds this plan's original 1-rule proposal); `tests/test_index_fingerprint.py`
      (8 tests) already covers the subprocess-boundary case and more — no action needed
- [ ] 2.3 — decide when `api_exec.py` / `scanners.py` get wired in
- [ ] 2.4 — enumerate `main.<attr>` refs; plan the re-export block and the 10 rebinds
      (re-verified 2026-08-15 — same 4 public rebinds, plus previously-unlisted reads of
      `main.LoginPasswordIn`/`OtpVerifyIn`/`OtpRequestIn`/`LibraryHashesIn`/`HTTPException`
      — include these in the re-export block too)
- [x] 2.5 — **new**: commit `tests/fixtures/auth_pilot/` to git (currently untracked and
      empty on disk; 6 test files fail/error on any fresh checkout until it's added)
- [x] 2.6 — **new**: fix the Phase 1/2 `embedder` circular-import trap before either
      phase is written — see Section 2.6's required change to Phase 1/2's instructions
- [x] Resolved: `app/test_password_reset.py` / `app/test_validator_gen.py` do **not**
      need moving — `pytest.ini`'s `testpaths = tests` already scopes collection to
      `tests/` only, confirmed by the Phase 0 test run (528 tests collected, all under
      `tests/`, none from `app/`)

**Refactor (public, merged down after each phase)**

- [x] Phase 0 — baseline tags, OpenAPI + Store inventories, namespace-ref list,
      test/ruff/mypy baselines generated 2026-08-15 (see `refactor-baseline/`); docker
      build **not verified** — no Docker daemon available in the generating sandbox, run
      `docker compose config --quiet && docker build -f app/Dockerfile .` locally before
      Phase 1; smoke checklist still needs a real docker-compose run — **both repos**
- [ ] Phase 1 — `core/config.py`, `core/state.py` (embedder = placeholder, see 2.6)
- [ ] Phase 2 — `core/security.py` (+ resolver registry), `deps.py` (embedder eager-init
      side effect, see 2.6), `exceptions.py`, `audit.py`, `bootstrap.py`; re-export block
      (functions + the 5 Pydantic/exception reads from 2.4); 4 public rebinds fixed; RBAC
      green
- [ ] Phase 3 — `workers/registry.py` + 6 worker files; `state.embedder` qualified access
      in `_reembed_worker` (see 2.6); one job of each type end-to-end
- [ ] Phase 4 — `background/poller.py`, `schedulers.py`; each thread starts exactly once
- [ ] Phase 5 — `store/` via mixins; 257-method diff clean; no duplicate names;
      `dbintegration` green; private adds `store/jira_plugin.py`
- [ ] Phase 6 — `api/routes/`, one router at a time, OpenAPI diff clean after each;
      `static_spa` last; `main.py` ≤ 250 lines; private adds `api/routes/ext_jira.py`
- [ ] Phase 7 — dead-import cleanup, config files verified unchanged, docs updated
- [ ] Phase 8 — test backfill per `store/` module
- [ ] Phase 9 (optional) — split `coverage.py`
