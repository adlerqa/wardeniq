import threading

from fastapi import FastAPI, HTTPException  # noqa: F401  (HTTPException: re-exported
                                                            # for tests/test_rbac_project_access.py's
                                                            # `pytest.raises(M.HTTPException)` —
                                                            # main.py's own code has no remaining
                                                            # `raise HTTPException(...)` call site
                                                            # since router 19/20; it's the same
                                                            # class object fastapi exposes anywhere,
                                                            # so re-exporting it is safe.
from llm import TEST_TYPES

# Phase 1 (REFACTOR_PLAN.md): env-derived config constants and the true
# application singletons (store, SYNC, embedder-placeholder) now live in
# core/config.py and core/state.py respectively. Explicit imports (not `*`)
# so ruff's dead-import signal keeps working. MONGO_URI, DB_NAME, EMBED_DIM,
# EMBED_MODEL, ENV_FILE_PATH, GEN_MODEL, MIN_POLL_INTERVAL, PROVIDER_LOCK,
# _ENV_MONGO, and _ENV_OLLAMA are consumed by core/state.py's Store(...)
# construction and/or the (now-extracted) api/routes/settings.py router only,
# and are not re-imported here since main.py has no other reference to them.
from core.config import GEN_TOTAL, IS_PRODUCTION, VERSION
# `store` is re-exported for tests (Phase 6, router 19/20 removed main.py's own
# last direct users of it — status/dashboard/tags/retrieve/sync_status all
# moved to api/routes/system.py). Dozens of tests patch attributes directly on
# the shared singleton via `main.store.<method> = ...` /
# `monkeypatch.setattr(main.store, "<method>", ...)` (test_api_routes.py,
# test_rbac_e2e.py, test_s3_storage.py, …) — never a full-module rebind — so
# keeping this bare name-import is required, not just historical. See
# core/state.py's docstring for why bare name-imports of `store` are safe in
# general (mutated in place, never rebound).
from core.state import store  # noqa: F401

# In production, disable the interactive API docs / OpenAPI schema — they expose
# every route shape, parameter and model to anonymous callers. Local/dev keeps them.
_docs_kwargs = ({"docs_url": None, "redoc_url": None, "openapi_url": None}
                if IS_PRODUCTION else {})
app = FastAPI(title="wardenIQ — Test Intelligence Platform", version=VERSION,
              **_docs_kwargs)


# Phase 2 (REFACTOR_PLAN.md): the InvalidId exception + its handler now live in
# app/core/exceptions.py. Registration stays here — it needs the `app` instance.
from core.exceptions import _InvalidId, invalid_id_handler  # noqa: E402

app.exception_handler(_InvalidId)(invalid_id_handler)


# Phase 2 (REFACTOR_PLAN.md): RBAC, the auth gateway + security-headers
# middleware, project-access-control helpers, and the principal-resolver
# registry now live in app/core/security.py. The audit-log writer lives in
# app/core/audit.py. Bootstrap (secret checks, DB connect/index retry loop,
# admin seeding) lives in app/core/bootstrap.py. Middleware is registered here
# since it needs the `app` instance; `bootstrap` is read by `_startup` below.
# `state`/`current_llm`/`current_poll_interval`/`BOOT` (formerly re-imported
# here alongside these) were main.py's last direct users of the embedder/LLM
# health check and poll-interval/boot-status fields — status()/sync_status()
# moved to api/routes/system.py (Phase 6, router 19/20), so main.py has no
# remaining reference to any of them.
from core.bootstrap import bootstrap  # noqa: E402
from core.security import (  # noqa: E402
    auth_gateway, security_headers,
)
# Re-exported for tests that reach these via `main.<name>` (Phase 6, routers
# 13/20, 15/20, and 16/20: api/routes/projects.py, api/routes/jobs_usage.py,
# api/routes/code_coverage.py). Not used by main.py itself post-refactor — each
# takes (request, ...) and reads no main.py module-global, so a direct
# re-export is safe (unlike store-backed handlers).
from core.security import _filter_projects_for, _allowed_project_ids, _require_project  # noqa: E402,F401
# Re-exported for tests that reach these via `main.<name>` even though main.py's own
# code no longer calls them directly (the logic that used to live here — auth_gateway
# — now lives entirely in core/security.py). See refactor-baseline/main-namespace-refs.txt.
from core.security import (  # noqa: E402,F401
    VIEWER_POST_OK, _is_public, _min_role, _target_project_for_path,
    _user_all_projects, _user_can_access_project,
    register_principal_resolver, resolve_principal,
)
# API-token bearer authentication (issue #37): the one call site that populates
# the principal-resolver registry above. Registered against "/api/" (every API
# path) rather than a narrower prefix — the resolver itself already fails
# closed on any request without a valid Authorization: Bearer token, and a
# token's own role (viewer/editor only — see api/routes/api_tokens.py) is what
# actually limits which endpoints it can use, exactly like a cookie user.
from core.token_auth import bearer_token_principal  # noqa: E402
register_principal_resolver("/api/", bearer_token_principal)

# Registration order preserved exactly: auth_gateway was declared (and thus
# registered) before security_headers in the original file.
app.middleware("http")(auth_gateway)
app.middleware("http")(security_headers)

# Phase 6 (REFACTOR_PLAN.md): routers extracted from main.py. Each router file's
# handlers are byte-identical to their old main.py bodies (only the decorator changed
# from @app. to @router.); include_router here preserves the same paths/behavior.
from api.routes import documents as _documents_routes  # noqa: E402
from api.routes import test_cycles as _test_cycles_routes  # noqa: E402
from api.routes import reports_exports as _reports_exports_routes  # noqa: E402
from api.routes import auth as _auth_routes  # noqa: E402
from api.routes import users as _users_routes  # noqa: E402
from api.routes import api_tokens as _api_tokens_routes  # noqa: E402
from api.routes import settings as _settings_routes  # noqa: E402
from api.routes import jira_atlassian as _jira_routes  # noqa: E402
from api.routes import repos_prs as _repos_prs_routes  # noqa: E402
from api.routes import steps_test_cases as _steps_test_cases_routes  # noqa: E402
from api.routes import validator as _validator_routes  # noqa: E402
from api.routes import test_plan as _test_plan_routes  # noqa: E402
from api.routes import test_import as _test_import_routes  # noqa: E402
from api.routes import projects as _projects_routes  # noqa: E402
from api.routes import features as _features_routes  # noqa: E402
from api.routes import jobs_usage as _jobs_usage_routes  # noqa: E402
from api.routes import code_coverage as _code_coverage_routes  # noqa: E402
from api.routes import develop as _develop_routes  # noqa: E402
from api.routes import webhooks as _webhooks_routes  # noqa: E402
from api.routes import system as _system_routes  # noqa: E402
# static_spa.py must be included LAST (REFACTOR_PLAN.md section 7/14) — it's
# where the /assets mount + SPA fallback routes sat at the end of the
# original main.py.
from api.routes import static_spa as _static_spa_routes  # noqa: E402
app.include_router(_documents_routes.router)
app.include_router(_test_cycles_routes.router)
app.include_router(_reports_exports_routes.router)
app.include_router(_auth_routes.router)
app.include_router(_users_routes.router)
app.include_router(_api_tokens_routes.router)
app.include_router(_settings_routes.router)
app.include_router(_jira_routes.router)
app.include_router(_repos_prs_routes.router)
app.include_router(_steps_test_cases_routes.router)
app.include_router(_validator_routes.router)
app.include_router(_test_plan_routes.router)
app.include_router(_test_import_routes.router)
app.include_router(_projects_routes.router)
app.include_router(_features_routes.router)
app.include_router(_jobs_usage_routes.router)
app.include_router(_code_coverage_routes.router)
app.include_router(_develop_routes.router)
app.include_router(_webhooks_routes.router)
app.include_router(_system_routes.router)
app.include_router(_static_spa_routes.router)  # LAST — see import comment above
# The /assets StaticFiles mount can't travel through include_router() (FastAPI
# silently drops Mounts registered on a sub-router — see
# api/routes/static_spa.py's module docstring), so it's applied directly to
# the real `app` instance here instead.
_static_spa_routes.mount_assets(app)

# Re-exported for tests that reach these via `main.<name>` (REFACTOR_PLAN.md section
# 2.4; Phase 6, router 12/20: api/routes/test_import.py). Not used by main.py itself
# post-refactor — do not remove without updating tests/test_sheet_import_main_helpers.py.
from api.routes.test_import import (  # noqa: E402,F401
    remove_imported_sheet_rows, LibraryHashesIn,
)
from workers.repo_scan_worker import _promote_imported_row_to_feature  # noqa: E402,F401


# Phase 4 (REFACTOR_PLAN.md): the stale-job sweeper and the imported-sheet
# project-wide re-analysis scheduler now live in app/background/schedulers.py.
# Re-imported here because `_startup` (below) starts both as daemon threads —
# same wiring, same order, same count as before the move.
from background.schedulers import _import_reanalysis_scheduler, _stale_job_sweeper  # noqa: E402


@app.on_event("startup")
def _startup():
    threading.Thread(target=bootstrap, daemon=True).start()
    threading.Thread(target=_stale_job_sweeper, daemon=True).start()
    # GAP2: periodic project-wide re-analysis of the imported-sheet pool.
    threading.Thread(target=_import_reanalysis_scheduler, daemon=True).start()


# --------------------------------------------------------------- generation pipeline
def step_text(s):
    return f"{s['action']}. Expected: {s['expected']}"


def _targets_from_focus(focus: dict, total: int = GEN_TOTAL) -> dict:
    """Turn a {type: percent} focus + a total budget into per-type case counts."""
    f = {t: max(0.0, float(focus.get(t, 25))) for t in TEST_TYPES}
    s = sum(f.values()) or 1.0
    return {t: round(f[t] / s * total) for t in TEST_TYPES}


# Phase 3 (REFACTOR_PLAN.md): the "validator" job now lives in
# app/workers/validator_worker.py. Importing it is required even though
# nothing here binds a name from it: the import itself is what runs
# `JOB_WORKERS["validator"] = _validator_worker` as a side effect.
from workers import validator_worker  # noqa: E402,F401


# Phase 3 (REFACTOR_PLAN.md): test-case generation, corpus ingestion, the
# embedding-model switch, and DB migration job workers now live in
# app/workers/generation.py. Importing it is required even though nothing
# here binds a name from it: the import itself is what runs
# `JOB_WORKERS["generate"/"ingest"/"reembed"/"migrate"] = ...` as a side
# effect, exactly like workers.registry already does for JOB_WORKERS.
from workers import generation  # noqa: E402,F401


# sync_repo, _ts, and poller moved to background/poller.py (Phase 4). sync_repo's own
# direct callers (the /api/projects/{pid}/repos and /api/repos/{rid}/sync route
# handlers) moved to api/routes/repos_prs.py (Phase 6, router 8/20) and import it
# there directly now, so only `poller` (used by the startup handler below) is needed
# here.
from background.poller import poller  # noqa: E402


@app.on_event("startup")
def _start_poller():
    threading.Thread(target=poller, daemon=True).start()


# RBAC hardening pass (2026-07): see RBAC_ANALYSIS.md and CHANGELOG for details.
