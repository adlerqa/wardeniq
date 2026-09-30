"""RBAC, the auth gateway middleware, security headers, and project-scope
access control.

Moved out of main.py (Phase 2 of REFACTOR_PLAN.md). `auth_gateway` and
`security_headers` are plain async functions here (no `@app.middleware`
decorator — that needs the `app` instance, which lives in main.py to avoid a
security<->main circular import). main.py registers them explicitly, in the
same order as the original decorators, via:

    app.middleware("http")(auth_gateway)
    app.middleware("http")(security_headers)

which is exactly equivalent to the original `@app.middleware("http")` usage.

Principal-resolver registry (REFACTOR_PLAN.md section 3.4): an upstream
extension point for a second authentication scheme (e.g. a bearer token)
alongside the cookie session, without patching this file. main.py registers
one resolver — core/token_auth.py's bearer_token_principal, for API tokens
(issue #37) — against the "/api/" prefix; a request with no Authorization
header (or one that doesn't resolve to an active token) falls through to
`_cookie_principal` exactly as before, so every existing cookie-based
route/test is unaffected.
"""
import re

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import auth
from core.config import IS_PRODUCTION
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)

# --------------------------------------------------------------- auth gateway
# Paths reachable without a session. The SPA itself is public (it shows the login
# screen); external webhooks carry their own secret/signature.
PUBLIC_EXACT = {"/", "/invite", "/favicon.ico", "/logo2.png", "/api/auth/request-otp", "/api/auth/verify-otp",
                "/api/auth/boot-status",
                "/api/auth/me", "/api/auth/logout", "/api/auth/smtp-status", "/api/auth/login-password",
                "/api/auth/request-password-reset", "/api/auth/reset-password", "/api/auth/reset-password-master",
                # Self-service invite endpoints: they authenticate the caller via the
                # session cookie themselves (_session_user), so they bypass the
                # role-based gateway (any signed-in user, incl. viewers, may accept
                # or decline THEIR OWN invite).
                "/api/auth/my-invite", "/api/auth/invite/accept",
                "/api/auth/invite/decline",
                # Public: resolve an invite token before login (the /invite landing).
                "/api/invite/verify",
                "/api/integrations/jira/webhook",
                "/api/webhook/github", "/api/webhook/gitlab"}
# Docs/OpenAPI are public only outside production (they don't exist in production —
# see the FastAPI(docs_url=None, ...) above).
PUBLIC_PREFIX = ("/assets/",) if IS_PRODUCTION else ("/assets/", "/docs", "/redoc", "/openapi")
# Admin-only areas (config + user management). Matched by exact or "<p>/..." prefix.
ADMIN_PATHS = ("/api/users", "/api/settings", "/api/llm/test", "/api/jira/test",
               "/api/smtp/test", "/api/settings/s3/test", "/api/audit-logs", "/api/db-status", "/api/db-config",
               "/api/db-migrate", "/api/api-tokens")
# Read-style POSTs that viewers are allowed to call.
VIEWER_POST_OK = ("/api/retrieve",)
# Secret-handling routes that live UNDER /api/projects/... (so they escape the
# ADMIN_PATHS prefixes) but must still require admin. Storing/clearing a Git PAT or
# creating a repo (which persists an encrypted webhook secret) is a credentials
# operation, equivalent in sensitivity to /api/settings. Matched as
# (write-methods, regex-over-path); read/status GETs are intentionally NOT listed
# so viewers/editors keep seeing "{configured: bool}" without touching the secret.
_ADMIN_WRITE_PATTERNS = (
    # /api/projects/{pid}/github/pat  and  /api/projects/{pid}/gitlab/pat
    re.compile(r"^/api/projects/[^/]+/(?:github|gitlab)/pat$"),
    # /api/projects/{pid}/repos  (POST persists webhook_secret_enc)
    re.compile(r"^/api/projects/[^/]+/repos$"),
)
_SECRET_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# High-blast-radius / sensitive operations that require ADMIN even though they'd
# otherwise be classed as an editor write. Editors keep create/edit/generate; these
# destructive or infrastructure actions are admin-only. Each entry is
# (allowed-methods, path-regex).
_ADMIN_ONLY_ROUTES = (
    ("DELETE", re.compile(r"^/api/projects/[^/]+$")),                 # delete a project
    ("DELETE", re.compile(r"^/api/repos/[^/]+$")),                    # delete a repo
    ("POST",   re.compile(r"^/api/repos/[^/]+/watch$")),             # start/stop watching a repo
    ("DELETE", re.compile(r"^/api/features/[^/]+$")),                 # delete a feature
    ("DELETE", re.compile(r"^/api/test-cases/[^/]+$")),              # delete a test case
    ("DELETE", re.compile(r"^/api/features/[^/]+/test-cases/[^/]+$")),# unlink case from feature
    ("DELETE", re.compile(r"^/api/steps/[^/]+$")),                    # delete a shared step
    ("DELETE", re.compile(r"^/api/test-cycles/[^/]+$")),            # delete a cycle
    ("DELETE", re.compile(r"^/api/test-cycles/[^/]+/items/[^/]+$")),  # delete a cycle item
    ("DELETE", re.compile(r"^/api/cycle-templates/[^/]+$")),        # delete a cycle template
    ("POST",   re.compile(r"^/api/develop$")),                        # Start Developing (writes to GitHub)
    ("POST",   re.compile(r"^/api/code-analysis$")),                 # heavy code analysis
    ("POST",   re.compile(r"^/api/analyze$")),                        # heavy commit analysis
    ("POST",   re.compile(r"^/api/analyze-pr$")),                    # PR analysis
)


def _is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX)


def _is_admin_secret_write(method: str, path: str) -> bool:
    if method not in _SECRET_WRITE_METHODS:
        return False
    return any(p.match(path) for p in _ADMIN_WRITE_PATTERNS)


def _is_admin_only_route(method: str, path: str) -> bool:
    return any(method == m and rx.match(path) for (m, rx) in _ADMIN_ONLY_ROUTES)


# Map a request path to the project it targets, for gateway-level access enforcement.
# Each pattern captures the id that identifies the project (directly or via a resource
# lookup). Collection routes (/api/projects, /api/features, ...) return None so the
# handler can apply list-filtering instead. Unknown/other paths return None (not
# project-scoped, or guarded elsewhere).
_PID_PATH_RE = re.compile(r"^/api/projects/([^/]+)(?:/.*)?$")
_FID_PATH_RE = re.compile(r"^/api/features/([^/]+)(?:/.*)?$")
_RID_PATH_RE = re.compile(r"^/api/repos/([^/]+)(?:/.*)?$")
_CYCLE_PATH_RE = re.compile(r"^/api/test-cycles/([^/]+)(?:/.*)?$")


def _target_project_for_path(method: str, path: str):
    """Return the project id this request targets, or None if not resolvable here.
    Raises HTTPException(404) if a referenced resource doesn't exist."""
    m = _PID_PATH_RE.match(path)
    if m:
        return m.group(1) or None
    m = _FID_PATH_RE.match(path)
    if m:
        return _project_of_feature(m.group(1))
    m = _RID_PATH_RE.match(path)
    if m:
        return _project_of_repo(m.group(1))
    m = _CYCLE_PATH_RE.match(path)
    if m:
        return _project_of_cycle(m.group(1))
    return None


def _min_role(method: str, path: str) -> str:
    for p in ADMIN_PATHS:
        if path == p or path.startswith(p + "/"):
            return "admin"
    if _is_admin_secret_write(method, path):
        return "admin"
    if _is_admin_only_route(method, path):
        return "admin"
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "viewer" if path in VIEWER_POST_OK else "editor"
    return "viewer"


# ----------------------------------------------------- principal-resolver registry
# Public upstream extension point (REFACTOR_PLAN.md 3.4): empty by default. A
# downstream distribution registers an additional resolver for a path prefix
# instead of patching this file. Consulted before the cookie session; the first
# non-None match wins. Falls through to the cookie session when the registry is
# empty (always true in this repo) or no resolver matches the path.
_PRINCIPAL_RESOLVERS: list = []   # [(path_prefix, fn), ...]


def register_principal_resolver(path_prefix: str, fn) -> None:
    """fn(request) -> user dict | None. Consulted only for paths under `path_prefix`,
    before cookie auth. First non-None wins. The prefix is part of the contract: a
    resolver can never authenticate a request outside its own surface."""
    _PRINCIPAL_RESOLVERS.append((path_prefix, fn))


def _cookie_principal(request):
    """Existing cookie-session based principal resolution, unchanged. Returns
    (user, token_session_version)."""
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    return user, tok_sv


def resolve_principal(request):
    """Resolve the request's principal via any registered resolver whose prefix
    matches the path, else the cookie session. With an empty registry (the
    public-repo default) this is always exactly `_cookie_principal(request)`."""
    path = request.url.path
    for prefix, fn in _PRINCIPAL_RESOLVERS:
        if path.startswith(prefix):
            u = fn(request)
            if u is not None:
                return u, u.get("session_version")
    return _cookie_principal(request)


async def auth_gateway(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or _is_public(path):
        return await call_next(request)
    user, tok_sv = resolve_principal(request)
    if not user or not user.get("active"):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    # Reject sessions minted before the user's session_version was bumped (role
    # change / disable / forced logout). The user must re-authenticate.
    if int(user.get("session_version", 0)) != int(tok_sv):
        return JSONResponse({"detail": "session expired — please sign in again"},
                            status_code=401)
    if not auth.has_role(user.get("role", "viewer"), _min_role(request.method, path)):
        # Local import: core/audit.py imports _current_user from this module for its
        # generic actor-resolution fallback, so a module-level import here (security
        # -> audit -> security) would cycle. This is the one documented exception
        # (REFACTOR_PLAN.md: "no function-level imports to hide cycles unless
        # absolutely unavoidable and documented").
        from core.audit import _audit
        _audit(request, "permission.denied", target=f"{request.method} {path}",
               actor=user, detail="insufficient role")
        return JSONResponse({"detail": "your role doesn't permit this action"}, status_code=403)
    request.state.user = user
    # Project-scope enforcement. For users limited to specific projects, resolve the
    # project this request targets (from the path shape) and deny if not allowed.
    # Admins / all_projects users skip this entirely. Covers the pid-in-path routes
    # and the common resource-by-id shapes (feature, repo, cycle) centrally; the few
    # remaining by-id routes (cases, coverage runs, validator/test-plan runs) are
    # guarded in their handlers.
    if not _user_all_projects(user):
        try:
            pid = _target_project_for_path(request.method, path)
        except HTTPException:
            pid = None   # unknown/missing resource → let the handler 404 naturally
        if pid is not None and not _user_can_access_project(user, pid):
            return JSONResponse({"detail": "you don't have access to this project"},
                                status_code=403)
    return await call_next(request)


# Content-Security-Policy for the single-file UI. The app relies on inline <script>
# blocks and inline event handlers, so script/style must allow 'unsafe-inline' (and
# 'unsafe-eval' for its runtime templating) — but everything is same-origin, so we
# still lock the origins down and forbid framing (clickjacking). HSTS is only sent
# when cookies are already HTTPS-only, to avoid breaking plain-HTTP local runs.
_CSP = ("default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'")


async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    if auth.COOKIE_SECURE:   # only meaningful (and safe) over HTTPS
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp


def _current_user(request: Request):
    return getattr(request.state, "user", None)


# --------------------------------------------------------------- project access control
# Users are scoped to projects: admins and users with all_projects=True see everything;
# others only their project_ids. Enforcement is centralized here so every project-scoped
# route can guard consistently. When AUTH is disabled, the synthetic dev user is admin,
# so access is unrestricted.
def _user_all_projects(user) -> bool:
    if not user:
        return True                       # AUTH disabled / no gateway → unrestricted
    if user.get("role") == "admin":
        return True                       # admins always see every project
    return bool(user.get("all_projects", True))


def _user_can_access_project(user, pid) -> bool:
    if _user_all_projects(user):
        return True
    return pid in set(user.get("project_ids") or [])


def _allowed_project_ids(user):
    """Return the set of project ids the user may see, or None meaning 'all'."""
    if _user_all_projects(user):
        return None
    return set(user.get("project_ids") or [])


def _require_project(request: Request, pid: str):
    """403 if the current user can't access project `pid`. Returns the user."""
    user = _current_user(request)
    if not _user_can_access_project(user, pid):
        raise HTTPException(403, "you don't have access to this project")
    return user


# ---- resource → project_id resolvers (raise 404 if the resource is missing) ----
def _project_of_feature(fid):
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    return f.get("project_id")


def _project_of_repo(rid):
    r = store.get_repo(rid)
    if not r:
        raise HTTPException(404, "repo not found")
    return r.get("project_id")


def _project_of_cycle(cid):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    return c.get("project_id")


def _require_feature_project(request, fid):
    _require_project(request, _project_of_feature(fid))


def _require_repo_project(request, rid):
    _require_project(request, _project_of_repo(rid))


def _require_cycle_project(request, cid):
    _require_project(request, _project_of_cycle(cid))


def _case_project_ids(cid):
    """Project ids a test case belongs to (via its feature associations)."""
    c = store.get_case(cid)
    if not c:
        raise HTTPException(404, "test case not found")
    return {f.get("project_id") for f in (c.get("features") or []) if f.get("project_id")}, c


def _require_case_project(request, cid):
    """Allow if the user can access ANY project the case is associated with."""
    pids, c = _case_project_ids(cid)
    user = _current_user(request)
    if _user_all_projects(user):
        return c
    if not (pids & set(user.get("project_ids") or [])):
        raise HTTPException(403, "you don't have access to this test case")
    return c


# ---- by-id run/job → project guards -----------------------------------------
# The auth gateway can only scope paths shaped like /api/projects|features|repos|
# test-cycles/<id>. Runs and jobs are addressed by their OWN id (/api/jobs/<id>,
# /api/validator/runs/<id>, ...), so a scoped user who knows/guesses an id could
# otherwise read another project's data. These resolve the run back to its project
# and reuse the same access check. All-projects users / AUTH-disabled short-circuit.
def _require_job_project(request, jid):
    j = store.get_job(jid)
    if not j:
        raise HTTPException(404, "job not found")
    user = _current_user(request)
    if _user_all_projects(user):
        return j
    pid = j.get("project_id")
    if not pid and j.get("feature_id"):
        pid = _project_of_feature(j["feature_id"])
    if pid is None or not _user_can_access_project(user, pid):
        raise HTTPException(403, "you don't have access to this job")
    return j


def _require_run_via_feature(request, run, what):
    """Guard a run that carries a feature_id (validator / test-plan / code-coverage)."""
    user = _current_user(request)
    if _user_all_projects(user):
        return run
    fid = run.get("feature_id")
    if not fid:
        raise HTTPException(403, f"you don't have access to this {what}")
    _require_feature_project(request, fid)   # resolves feature→project, 403 if denied
    return run


def _require_validator_run_project(request, run_id):
    run = store.get_validator_run(run_id)
    if not run:
        raise HTTPException(404, "Validator run not found")
    return _require_run_via_feature(request, run, "validator run")


def _require_test_plan_run_project(request, run_id):
    run = store.get_test_plan_run(run_id)
    if not run:
        raise HTTPException(404, "Test plan run not found")
    return _require_run_via_feature(request, run, "test plan run")


def _require_code_coverage_run_project(request, rid):
    run = store.get_code_coverage_run(rid)
    if not run:
        raise HTTPException(404, "run not found")
    return _require_run_via_feature(request, run, "coverage run")


def _require_commit_analysis_project(request, run_id):
    run = store.get_commit_analysis(run_id)
    if not run:
        raise HTTPException(404, "commit-analysis run not found")
    user = _current_user(request)
    if _user_all_projects(user):
        return run
    pid = run.get("project_id")
    if not pid and run.get("feature_id"):
        pid = _project_of_feature(run["feature_id"])
    if pid is None or not _user_can_access_project(user, pid):
        raise HTTPException(403, "you don't have access to this analysis")
    return run


def _filter_projects_for(user, projects):
    """Filter a list of project dicts to those the user may access."""
    allowed = _allowed_project_ids(user)
    if allowed is None:
        return projects
    return [p for p in projects if (p.get("id") or p.get("_id")) in allowed]


def _project_public(p):
    """Serialize a project for API responses. Strips every encrypted-secret blob
    (any *_enc key) and surfaces `github_pat_set` / `gitlab_pat_set` booleans instead,
    so a raw PAT ciphertext can never appear in a Network response. Returns None for a
    falsy input so callers can 404 uniformly."""
    if not p:
        return None
    out = {k: v for k, v in p.items() if not k.endswith("_enc")}
    out["github_pat_set"] = bool(p.get("github_pat_enc"))
    out["gitlab_pat_set"] = bool(p.get("gitlab_pat_enc"))
    return out
