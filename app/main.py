import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from store import Store
import extract as extractmod
from embeddings import Embedder
from llm import LLM, TEST_TYPES
from extract import extract_text
import github
import gitlab as gitlab_mod
import coverage as cov
import grounding
import automation as auto_cov
import sheet_import as sheet_mod
import crypto
import jira
import figma
import usage
import auth
import email_send
import validator
import test_plan
from testgen.service import generate_fresh_testcases_pipeline

# Database + Ollama endpoints are configurable two ways (Joomla-style): an explicit
# value in .env WINS (and shows as "configured" / locked in the UI); otherwise the
# bundled default is used and the value is editable from the frontend, which persists
# it back into .env. Compose injects the .env value (empty if the user hasn't set one)
# plus a *_BUNDLED fallback so we can tell "user-configured" from "using the default".
_ENV_MONGO = (os.getenv("MONGO_URI") or "").strip()
MONGO_URI_BUNDLED = os.getenv(
    "MONGO_URI_BUNDLED",
    "mongodb://mongod1.warden-net:27017,mongod2.warden-net:27017,"
    "mongod3.warden-net:27017/?replicaSet=rs0")
MONGO_URI = _ENV_MONGO or MONGO_URI_BUNDLED

_ENV_OLLAMA = (os.getenv("OLLAMA_URL") or "").strip()
OLLAMA_URL_BUNDLED = os.getenv("OLLAMA_URL_BUNDLED", "http://ollama:11434")

# Path to the .env file the app persists frontend config into. In Docker this is a
# bind-mount of the project's ./.env (see docker-compose.app.yml); changes apply on
# the next `docker compose up -d` (compose re-reads .env and re-injects the vars).
ENV_FILE_PATH = os.getenv("ENV_FILE_PATH", "/app/.env")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
GEN_MODEL = os.getenv("GEN_MODEL", "qwen2.5:3b")
DB_NAME = os.getenv("DB_NAME", "wardeniq")
VERSION = "0.1.0-beta"
AUTO_SETUP = os.getenv("AUTO_SETUP", "true").lower() == "true"
STEP_AUTO = float(os.getenv("STEP_AUTO_REUSE", "0.95"))
CASE_AUTO = float(os.getenv("CASE_AUTO_REUSE", "0.93"))
SUGGEST = float(os.getenv("SUGGEST_THRESHOLD", "0.85"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API = os.getenv("GITHUB_API", "https://api.github.com")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
MAP_AUTO = float(os.getenv("MAP_AUTO_THRESHOLD", "0.86"))
# GAP8 (opt-in): use embeddings to semantically match imported-pool rows to features
# during the background re-scan, as an ADDITIONAL promotion path beyond the algorithmic
# scorer. OFF by default (the token scorer already works and per-row embedding has cost).
IMPORT_SEMANTIC_MATCH = os.getenv("IMPORT_SEMANTIC_MATCH", "false").lower() == "true"
IMPORT_SEMANTIC_THRESHOLD = float(os.getenv("IMPORT_SEMANTIC_THRESHOLD", "0.78"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
MONGOT_METRICS = os.getenv("MONGOT_METRICS", "http://mongot.warden-net:9946")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
# Installer-chosen bootstrap password for the local `admin` account. When set (and
# it passes the password policy), it REPLACES the shipped `admin123` default: the
# admin row is seeded with this password's hash at boot and admin123 stops working.
# Left empty (pure source dev), the legacy admin123 default applies with its
# mandatory change-on-first-login. Never logged.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
# The effective default password accepted for the bootstrap admin before any
# in-app change: the operator's ADMIN_PASSWORD if valid, else the shipped default.
DEFAULT_ADMIN_PASSWORD = (
    ADMIN_PASSWORD if (ADMIN_PASSWORD and not auth.password_policy_errors(ADMIN_PASSWORD))
    else auth.DEFAULT_LOCAL_PASSWORD)
# Auth is ALWAYS enforced — there is no bypass flag. The first admin bootstraps
# without SMTP by reading a one-time code printed to the server log (see
# _deliver_otp), then configures email in-app.
# Deployment posture. "production" turns on hard startup gates (see
# _check_production_posture) and disables the public API docs. Anything else
# (default "development") keeps the zero-config local behaviour.
APP_ENV = os.getenv("APP_ENV", os.getenv("ENV", "development")).strip().lower()
IS_PRODUCTION = APP_ENV in ("production", "prod")
# When auth is on, a weak/default APP_SECRET is disqualifying (it signs sessions
# AND derives the secret-at-rest key). We refuse to boot in that case unless the
# operator explicitly opts out for a local/dev run.
ALLOW_WEAK_SECRET = os.getenv("ALLOW_WEAK_SECRET", "false").lower() == "true"
# Display label for this single-tenant instance (shown on the invite banner). Not a
# tenant/org — just a name for the deployment.
APP_WORKSPACE_NAME = os.getenv("APP_WORKSPACE_NAME", "WardenIQ").strip() or "WardenIQ"
# Optional deploy-time lock to a single AI provider (e.g. "bedrock" for an
# air-gapped enterprise install). Empty = no lock; the UI shows every provider.
PROVIDER_LOCK = os.getenv("LLM_PROVIDER_LOCK", "").strip().lower()
# OTP request throttle: at most OTP_MAX_PER_WINDOW codes issued to one account within
# OTP_WINDOW_SECONDS (stops email-bombing / code brute-force churn).
OTP_WINDOW_SECONDS = int(os.getenv("OTP_WINDOW_SECONDS", "900"))   # 15 min
OTP_MAX_PER_WINDOW = int(os.getenv("OTP_MAX_PER_WINDOW", "5"))

# In production, disable the interactive API docs / OpenAPI schema — they expose
# every route shape, parameter and model to anonymous callers. Local/dev keeps them.
_docs_kwargs = ({"docs_url": None, "redoc_url": None, "openapi_url": None}
                if IS_PRODUCTION else {})
app = FastAPI(title="wardenIQ — Test Intelligence Platform", version=VERSION,
              **_docs_kwargs)
store = Store(MONGO_URI, DB_NAME, EMBED_DIM)

# Known embedding models per provider (id + native dimension) for the UI. The real
# dimension is always measured (probe_dim) at switch time, so these are just hints.
EMBED_MODEL_OPTIONS = {
    "ollama": [{"id": "nomic-embed-text", "dim": 768}, {"id": "mxbai-embed-large", "dim": 1024}],
    "openai": [{"id": "text-embedding-3-small", "dim": 1536}, {"id": "text-embedding-3-large", "dim": 3072}],
    "gemini": [{"id": "gemini-embedding-001", "dim": 3072}, {"id": "text-embedding-004", "dim": 768}],
    "voyage": [{"id": "voyage-3", "dim": 1024}, {"id": "voyage-3-lite", "dim": 512},
               {"id": "voyage-3-large", "dim": 1024}],
    "openai-compatible": [],
    "bedrock": [{"id": "amazon.titan-embed-text-v2:0", "dim": 1024},
                {"id": "amazon.titan-embed-text-v1", "dim": 1536},
                {"id": "cohere.embed-english-v3", "dim": 1024},
                {"id": "cohere.embed-multilingual-v3", "dim": 1024}],
}


def current_ollama_url() -> str:
    """Resolve the Ollama endpoint. Precedence: OLLAMA_URL in .env WINS (locked in
    the UI); else the value saved from the frontend (settings); else the bundled
    default. Read fresh so an in-app change applies immediately (no restart)."""
    if _ENV_OLLAMA:
        return _ENV_OLLAMA
    try:
        saved = (store.get_settings().get("ollama_url") or "").strip()
    except Exception:  # noqa: BLE001
        saved = ""
    return saved or OLLAMA_URL_BUNDLED


def current_embedder() -> Embedder:
    """Build the embedding client from saved settings (local Ollama by default).
    Read fresh so a model switch takes effect for subsequent calls."""
    s = store.get_settings()
    # Embeddings are NOT hard-pinned by PROVIDER_LOCK — the admin chooses Bedrock or
    # the local bundled Ollama (both air-gapped-safe). We only clamp away internet
    # providers when a lock is active, so a locked install can never call out.
    provider = s.get("embed_provider") or "ollama"
    if PROVIDER_LOCK and provider not in ("ollama", PROVIDER_LOCK):
        provider = "ollama"
    key = crypto.decrypt(s.get("embed_api_key_enc", "")) if s.get("embed_api_key_enc") else ""
    return Embedder(provider=provider,
                    model=s.get("embed_model") or EMBED_MODEL,
                    dim=int(s.get("embed_dim") or EMBED_DIM),
                    api_key=key, base_url=s.get("embed_base_url", ""), ollama_url=current_ollama_url(),
                    region=s.get("embed_region", ""))


# Align the store's index dimension with the saved embedding model, then build the
# active embedder. (Indexes for an already-switched model exist at the right dim,
# so Store.__init__'s _ensure_vector left them untouched.)
_saved_embed = store.get_settings()
if _saved_embed.get("embed_dim"):
    store.dim = int(_saved_embed["embed_dim"])
embedder = current_embedder()


def current_llm() -> LLM:
    """Build the LLM client from saved settings (local Ollama by default, or a
    hosted provider with an API key). Read fresh each call so config changes apply."""
    s = store.get_settings()
    provider = PROVIDER_LOCK or s.get("llm_provider", "ollama")
    key = crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
    return LLM(provider=provider, model=(s.get("llm_model") or GEN_MODEL),
               api_key=key, base_url=s.get("llm_base_url", ""), ollama_url=current_ollama_url(),
               region=s.get("llm_region", ""))


def project_github_token(pid: str) -> str:
    """Project-level GitHub PAT (encrypted at rest). Falls back to env for compat."""
    enc = store.get_project_github_pat_enc(pid)
    return (crypto.decrypt(enc) if enc else "") or GITHUB_TOKEN


def project_gitlab_token(pid: str) -> str:
    enc = store.get_project_gitlab_pat_enc(pid)
    return crypto.decrypt(enc) if enc else ""


def gh_client_for_project(pid: str) -> github.GitHub:
    return github.GitHub(project_github_token(pid), GITHUB_API)


def gl_client_for_project(pid: str) -> "gitlab_mod.GitLab":
    return gitlab_mod.GitLab(project_gitlab_token(pid))


def gh_client_with_token(token: str) -> github.GitHub:
    return github.GitHub(token or GITHUB_TOKEN, GITHUB_API)


# Back-compat aliases (older code paths reference these names).
def current_token() -> str:
    return GITHUB_TOKEN


def gh_client() -> github.GitHub:
    return github.GitHub(GITHUB_TOKEN, GITHUB_API)


gh = github.GitHub(GITHUB_TOKEN, GITHUB_API)


def _provider_client(repo: dict):
    provider = (repo.get("git_provider") or "github").lower()
    pid = repo.get("project_id")
    if provider == "gitlab":
        token = project_gitlab_token(pid)
        if not token:
            raise RuntimeError("no GitLab PAT configured for this project")
        return provider, gitlab_mod.GitLab(token)
    token = project_github_token(pid)
    if not token:
        raise RuntimeError("no GitHub PAT configured for this project")
    return provider, github.GitHub(token, GITHUB_API)


def _repo_list_commits(repo: dict, since_iso: str, ref: str = "", per_page: int = 50):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.list_commits(repo["full_name"], since_iso, per_page=per_page, ref=ref)
    return client.list_commits(repo["owner"], repo["name"], since_iso, per_page=per_page, ref=ref)


def _repo_get_commit(repo: dict, sha: str, max_files: int = 40):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.get_commit(repo["full_name"], sha, max_files=max_files)
    return client.get_commit(repo["owner"], repo["name"], sha, max_files=max_files)


def _repo_branch_sha(repo: dict, ref: str):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.branch_sha(repo["full_name"], ref)
    return client.branch_sha(repo["owner"], repo["name"], ref)


def _repo_get_archive(repo: dict, ref: str = ""):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.get_archive(repo["full_name"], ref)
    return client.get_archive(repo["owner"], repo["name"], ref)


def _repo_list_branches(repo: dict):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.list_branches(repo["full_name"])
    return client.list_branches(repo["owner"], repo["name"])


def _is_app_repo(repo: dict | None) -> bool:
    return bool(repo) and (repo.get("repo_type") or "app") == "app"


def _implementation_repo_docs(project_id: str, repo_ids=None):
    """Implementation repos only.

    Test repos are reserved for automation coverage and must not participate in
    commit analysis, code coverage / mind map, or code generation flows.
    """
    repo_ids = repo_ids or []
    if repo_ids:
        docs = [store.repos.find_one({"_id": _oid(r)}) for r in repo_ids]
    else:
        docs = list(store.repos.find({"project_id": project_id, "repo_type": "app"}))
    return [r for r in docs if _is_app_repo(r)]


def _webhook_base_url(request: Request | None = None) -> str:
    """Pick the public API base URL for webhooks. Honors env first, falls back
    to the inbound request's host."""
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("API_BASE_URL") or "").rstrip("/")
    if base:
        return base
    if request is not None:
        # `request.base_url` ends with `/`.
        base_url = getattr(request, "base_url", None)
        if base_url:
            return str(base_url).rstrip("/")
    return ""

# --------------------------------------------------------------- auth gateway
# Paths reachable without a session. The SPA itself is public (it shows the login
# screen); external webhooks carry their own secret/signature.
PUBLIC_EXACT = {"/", "/invite", "/favicon.ico", "/logo2.png", "/api/auth/request-otp", "/api/auth/verify-otp",
                "/api/auth/me", "/api/auth/logout", "/api/auth/smtp-status", "/api/auth/login-password",
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
               "/api/smtp/test", "/api/audit-logs", "/api/db-status", "/api/db-config",
               "/api/db-migrate")
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


@app.middleware("http")
async def auth_gateway(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or _is_public(path):
        return await call_next(request)
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    if not user or not user.get("active"):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    # Reject sessions minted before the user's session_version was bumped (role
    # change / disable / forced logout). The user must re-authenticate.
    if int(user.get("session_version", 0)) != int(tok_sv):
        return JSONResponse({"detail": "session expired — please sign in again"},
                            status_code=401)
    if not auth.has_role(user.get("role", "viewer"), _min_role(request.method, path)):
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


@app.middleware("http")
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


def _audit(request, action, target=None, old=None, new=None, actor=None, detail=None):
    """Best-effort audit-log write. Captures actor (from session), IP and user-agent.
    Never raises — auditing must not break the action it records."""
    try:
        actor = actor if actor is not None else _current_user(request)
        ip = None
        ua = None
        if request is not None:
            ip = (request.headers.get("x-forwarded-for") or
                  (request.client.host if request.client else None))
            ua = request.headers.get("user-agent")
        store.add_audit(action, actor=actor, target=target, old=old, new=new,
                        ip=ip, user_agent=ua, detail=detail)
    except Exception as e:  # noqa: BLE001
        print(f"[wardenIQ][audit] failed to record {action}: {e}", flush=True)


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


BOOT = {"stage": "starting", "ready": False, "detail": ""}


def _ensure_app_secret():
    """Zero-config first run: if no real secret has been configured at all, generate a
    strong one automatically and persist it into .env, so a first-time user never has
    to hand-edit anything just to get past the weak-secret gate below.

    This does NOT weaken `_check_app_secret()` — it only fires when the effective
    secret is still unset/the shipped placeholder, and only when we can durably
    persist the generated value to .env (bind-mounted per docker-compose.app.yml), so
    the SAME secret survives a restart (sessions and encrypted-at-rest settings depend
    on that). If persistence isn't possible, we deliberately do nothing and let
    `_check_app_secret()` fail closed with its existing clear error, rather than run on
    a secret that would silently change on every restart.

    If an operator has already started customizing via SESSION_SECRET/ENCRYPTION_KEY,
    we leave it alone entirely — auto-filling just one half of an intentional split
    would be more confusing than helpful.
    """
    if not auth.secret_is_weak():
        return
    if os.getenv("SESSION_SECRET") or os.getenv("ENCRYPTION_KEY"):
        return
    if not _env_file_writable():
        return
    generated = secrets.token_urlsafe(32)
    ok, err = _write_env_var(ENV_FILE_PATH, "APP_SECRET", generated)
    if not ok:
        print(f"[wardenIQ][WARNING] could not persist an auto-generated APP_SECRET: {err}",
              flush=True)
        return
    os.environ["APP_SECRET"] = generated
    print("[wardenIQ] No APP_SECRET was set — generated a strong one automatically and "
          "saved it to .env. This key signs sessions and encrypts stored secrets: back "
          "up your .env file, and set your own APP_SECRET explicitly before going to "
          "production.", flush=True)


def _check_app_secret():
    """Fail closed (or loudly warn) if APP_SECRET is weak.

    APP_SECRET signs sessions/OTPs and derives the Fernet key for secrets at rest,
    so a default/short value lets anyone forge an admin session and decrypt stored
    credentials. Auth is always on, so we refuse to boot on a weak secret; set
    ALLOW_WEAK_SECRET=true to override for a trusted local run.
    """
    if not auth.secret_is_weak():
        return
    msg = ("APP_SECRET is unset, the shipped placeholder, or shorter than "
           f"{auth.MIN_SECRET_LEN} chars. It signs login sessions and encrypts "
           "stored secrets — a weak value is a critical vulnerability.")
    if not ALLOW_WEAK_SECRET:
        BOOT.update(stage="error", ready=False,
                    detail=f"insecure APP_SECRET: {msg} Set a strong APP_SECRET "
                           "(or ALLOW_WEAK_SECRET=true for a trusted local run).")
        raise RuntimeError(f"[wardenIQ] refusing to start — {msg}")
    print(f"[wardenIQ][WARNING] {msg} (allowed because ALLOW_WEAK_SECRET=true)",
          flush=True)


def _check_production_posture():
    """In a production posture (APP_ENV=production) refuse to boot with settings that
    are acceptable only for local development. Fails closed so an insecure instance
    never comes up on the public internet by accident."""
    if not IS_PRODUCTION:
        return
    problems = []
    if ALLOW_WEAK_SECRET:
        problems.append("ALLOW_WEAK_SECRET=true (must be false)")
    if not auth.COOKIE_SECURE:
        problems.append("COOKIE_SECURE=false (sessions must be HTTPS-only)")
    if not _smtp_cfg():
        problems.append("SMTP not configured (email sign-in would be unavailable)")
    if problems:
        detail = ("insecure production configuration: " + "; ".join(problems) +
                  ". Fix these, or unset APP_ENV=production for a local run.")
        BOOT.update(stage="error", ready=False, detail=detail)
        raise RuntimeError(f"[wardenIQ] refusing to start — {detail}")


def _search_unsupported(e) -> bool:
    """Heuristic: does the connected MongoDB clearly LACK Search/Vector Search (as
    opposed to a search service that's merely still starting)? A search-less server
    rejects the search-index commands outright ('no such command' / 'unrecognized'),
    which is worth failing fast on — unlike 'connecting to Search Index Management
    service', which is transient while a bundled mongot boots."""
    m = str(e).lower()
    return any(s in m for s in (
        "no such command", "unrecognized", "command not found",
        "notimplemented", "atlas search is not", "search is not supported",
    ))


def _search_index_limit(e) -> bool:
    """The connected DB supports search but won't allow enough indexes — the classic
    MongoDB Atlas per-tier cap ('maximum number of FTS indexes ... for this instance
    size'). No point retrying; the fix is a bigger tier or self-managed mongot."""
    m = str(e).lower()
    return ("maximum number of fts indexes" in m
            or ("fts index" in m and "instance size" in m)
            or "maximum number of search indexes" in m)


_SEARCH_REQUIRED_MSG = (
    "wardenIQ requires a MongoDB with Vector Search — it's where embeddings are "
    "searched. The database at MONGO_URI doesn't have it. Use MongoDB Atlas (search "
    "built in) or a self-managed MongoDB running mongot, then restart."
)

_SEARCH_INDEX_LIMIT_MSG = (
    "This MongoDB Atlas cluster doesn't allow enough search indexes. wardenIQ needs 6, "
    "but your tier caps them (the free M0 tier allows only 3). Fix: upgrade to a "
    "dedicated Atlas tier (M10 or higher), or use a self-managed MongoDB with mongot "
    "(no such limit), then restart."
)


def bootstrap():
    _ensure_app_secret()
    _check_app_secret()
    _check_production_posture()
    BOOT.update(stage="connecting")
    for _ in range(60):
        try:
            store.ping(); break
        except Exception as e:  # noqa: BLE001
            BOOT["detail"] = str(e); time.sleep(2)
    try:
        store.fail_orphaned_jobs()
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"job recovery: {e}"
    if AUTO_SETUP:
        BOOT.update(stage="indexing")
        idx_err = None
        # Generous retry: a bundled mongot can take a while to sync + build indexes.
        for _ in range(40):
            try:
                store.ensure_indexes(); idx_err = None; break
            except Exception as e:  # noqa: BLE001
                idx_err = e
                # These two won't resolve by waiting → stop retrying and report clearly.
                if _search_unsupported(e) or _search_index_limit(e):
                    break
                BOOT["detail"] = f"index retry: {e}"; time.sleep(3)
        if idx_err is not None:
            # Refuse to serve, with a message that matches the actual cause rather than
            # a raw driver dump. The Atlas per-tier index cap is a distinct, common case.
            if _search_index_limit(idx_err):
                detail = _SEARCH_INDEX_LIMIT_MSG
                reason = "too few search indexes allowed by the Atlas tier"
            else:
                detail = _SEARCH_REQUIRED_MSG
                reason = "Vector Search unavailable"
            BOOT.update(stage="error", ready=False, detail=detail)
            print(f"[wardenIQ] refusing to serve — {reason}: {idx_err}", flush=True)
            return
    # Adopt features created before project_id existed into a default project.
    try:
        store.migrate_legacy_features()
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"migrate: {e}"
    # Seed the first admin from ADMIN_EMAIL (if set and not already present).
    # Validate it first: a malformed value (e.g. a leaked .env comment) must NOT be
    # inserted as a user — warn loudly and skip instead.
    try:
        if ADMIN_EMAIL:
            if not auth.is_valid_email(ADMIN_EMAIL):
                print(f"[wardenIQ][WARNING] ADMIN_EMAIL is not a valid email "
                      f"({ADMIN_EMAIL!r}); skipping admin seed. Fix ADMIN_EMAIL in "
                      f".env (no inline comments on the value line).", flush=True)
            elif not store.get_user_by_email(ADMIN_EMAIL):
                store.create_user(ADMIN_EMAIL, ADMIN_EMAIL.split("@")[0], "admin")
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"admin seed: {e}"
    # Seed the local `admin` account's password from ADMIN_PASSWORD (installer-chosen)
    # so a provisioned deployment ships with NO well-known default. Only sets a
    # password when the admin has none yet — it never clobbers one the operator has
    # already changed in-app. A value that fails the policy is ignored with a warning
    # (the account then keeps the admin123 default + its forced-change flow).
    try:
        if ADMIN_PASSWORD:
            errs = auth.password_policy_errors(ADMIN_PASSWORD)
            if errs:
                print("[wardenIQ][WARNING] ADMIN_PASSWORD does not meet the policy "
                      f"({', '.join(errs)}); ignoring it — the bootstrap admin keeps "
                      "the default until changed.", flush=True)
            else:
                admin = store.get_user_by_email("admin")
                if not admin:
                    admin = store.create_user("admin", "Admin", "admin")
                if not admin.get("password_hash"):
                    store.set_user_password(admin["id"], auth.hash_password(ADMIN_PASSWORD))
                    print("[wardenIQ] Seeded the local admin password from ADMIN_PASSWORD "
                          "(the shipped default is disabled).", flush=True)
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"admin password seed: {e}"
    BOOT.update(stage="ready", ready=True, detail="")


STALE_JOB_TTL_SECONDS = int(os.getenv("STALE_JOB_TTL_SECONDS", "600"))
STALE_JOB_SWEEP_INTERVAL_SECONDS = int(os.getenv("STALE_JOB_SWEEP_INTERVAL_SECONDS", "60"))


def _stale_job_sweeper():
    """Periodically fail 'running' jobs whose worker thread died silently
    (OOM, C-level segfault, network deadlock) — startup recovery alone
    doesn't help when the process is still up. Keeps loaders from spinning
    forever on the client."""
    while True:
        try:
            time.sleep(max(15, STALE_JOB_SWEEP_INTERVAL_SECONDS))
            if not BOOT.get("ready"):
                continue
            store.sweep_stale_jobs(ttl_seconds=STALE_JOB_TTL_SECONDS)
        except Exception as e:  # noqa: BLE001
            print(f"[stale-sweeper] {e}", flush=True)


@app.on_event("startup")
def _startup():
    threading.Thread(target=bootstrap, daemon=True).start()
    threading.Thread(target=_stale_job_sweeper, daemon=True).start()
    # GAP2: periodic project-wide re-analysis of the imported-sheet pool.
    threading.Thread(target=_import_reanalysis_scheduler, daemon=True).start()


# --------------------------------------------------------------- generation pipeline
def step_text(s):
    return f"{s['action']}. Expected: {s['expected']}"


GEN_TOTAL = int(os.getenv("GEN_TOTAL", "16"))  # total target cases across all types


def _targets_from_focus(focus: dict, total: int = GEN_TOTAL) -> dict:
    """Turn a {type: percent} focus + a total budget into per-type case counts."""
    f = {t: max(0.0, float(focus.get(t, 25))) for t in TEST_TYPES}
    s = sum(f.values()) or 1.0
    return {t: round(f[t] / s * total) for t in TEST_TYPES}


JOB_WORKERS = {}   # job type -> worker(jid, params)


def launch_job(jtype, params, label="", project_id=None, feature_id=None):
    """Create a persisted job and run its worker in a background thread."""
    jid = store.create_job(jtype, params, label, project_id, feature_id)

    def run():
        import usage
        usage.start()   # record all LLM/embedding tokens spent by this job's thread
        try:
            JOB_WORKERS[jtype](jid, params)
            j = store.get_job(jid)
            if j and j.get("status") == "running":
                store.update_job(jid, status="succeeded", stage="done", progress=100)
        except Exception as e:  # noqa: BLE001
            store.update_job(jid, status="failed", stage="error", error=str(e))
        finally:
            try:
                prices = store.get_settings().get("llm_prices") or {}
                store.set_job_usage(jid, usage.summarize(usage.stop(), prices))
            except Exception as ue:  # noqa: BLE001
                print(f"[usage] failed to record job {jid}: {ue}", flush=True)

    threading.Thread(target=run, daemon=True).start()
    return jid


def _gen_worker(jid, params):
    try:
        def update_fn(stage, progress=None):
            store.update_job_progress(jid, stage, progress)

        res = generate_fresh_testcases_pipeline(
            store=store,
            llm=current_llm(),
            embedder=embedder,
            params=params,
            update_job_fn=update_fn
        )
        store.merge_job_result(jid, **res)

        # Auto-trigger automation coverage for any connected test repos so the
        # Gap Analysis pane is fresh as soon as the user opens it. Scoped to
        # this single feature to keep LLM cost bounded.
        try:
            fid = params.get("feature_id")
            feature = store.get_feature(fid) if fid else None
            if feature and feature.get("project_id"):
                test_repos = store.repos_for_project(
                    feature["project_id"], repo_type="test")
                for tr in test_repos:
                    if tr.get("scan_status") == "running":
                        continue
                    launch_job("test_repo_scan", {
                        "repo_id": tr["id"], "feature_id": fid},
                        label=f"Auto-scan · {tr.get('full_name')}",
                        project_id=feature["project_id"], feature_id=fid)
        except Exception as auto_e:  # noqa: BLE001
            print(f"[auto-scan] skipped: {auto_e}", flush=True)
        # GAP4: a freshly (re)generated feature may now match rows sitting in the
        # imported pool — rescan and promote the evidence-backed ones.
        try:
            fid2 = params.get("feature_id")
            feat2 = store.get_feature(fid2) if fid2 else None
            if feat2:
                _rescan_pool_for_feature(feat2)     # GAP4
                _apply_import_overlays(feat2)         # GAP3
        except Exception as re_e:  # noqa: BLE001
            print(f"[import-recheck] skipped: {re_e}", flush=True)
    except Exception as e:
        store.update_job(jid, status="failed", stage="error", error=str(e))
        raise e


JOB_WORKERS["generate"] = _gen_worker


def _validator_worker(jid, params):
    run_id = params["run_id"]

    def update_fn(stage, progress=None):
        store.update_job_progress(jid, stage, progress)

    result = validator.generate_validator_run(
        store=store,
        llm=current_llm(),
        feature_id=params["feature_id"],
        run_id=run_id,
        progress_fn=update_fn,
    )
    store.merge_job_result(
        jid,
        run_id=run_id,
        question_count=len(result.get("questions") or []),
    )


JOB_WORKERS["validator"] = _validator_worker


def _code_coverage_worker(jid, params):
    """Manual PR/MR coverage run, provider-aware. Dispatches GitHub vs GitLab
    by repo.git_provider so a GitLab MR doesn't hit the GitHub API."""
    repo_id = params["repo_id"]
    pr_number = int(params["pr_number"])
    store.update_job_progress(jid, "Fetching PR…", 10)
    repo = store.get_repo(repo_id)
    if not repo:
        store.update_job(jid, status="failed", stage="error", error="repo not found")
        return
    try:
        pr, files, _sha = _fetch_pr_and_files(repo, pr_number)
    except Exception as e:  # noqa: BLE001
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return
    pr["_files"] = files     # avoid re-fetching in ingest_pr
    store.update_job_progress(jid, "Running LLM coverage…", 40)
    # PIN to the user's chosen feature on manual runs.
    pr_id = ingest_pr(repo, pr, feature_id_override=params.get("feature_id"))
    store.update_job_progress(jid, "Persisting…", 90)
    store.merge_job_result(jid, pr_id=pr_id, repo_full_name=repo["full_name"])


JOB_WORKERS["code_coverage"] = _code_coverage_worker


def _test_repo_scan_worker(jid, params):
    """Scan a connected test repo, extract test titles, run hybrid matching
    against generated cases.

    Params:
      repo_id (required)       — which test repo to scan
      feature_id (optional)    — when set, only match for this feature (used by
                                 the auto-trigger after generate)
      project_features (bool)  — when set False, skip the matching loop entirely
    """
    repo_id = params["repo_id"]
    scoped_fid = params.get("feature_id")
    store.update_job_progress(jid, "Loading repo…", 5)
    repo = store.get_repo(repo_id)
    if not repo:
        store.update_job(jid, status="failed", stage="error", error="repo not found")
        return
    pid = repo["project_id"]
    provider = repo.get("git_provider", "github")
    if repo.get("repo_type") != "test":
        store.update_job(jid, status="failed", stage="error",
                         error="rescan only applies to test repos")
        return
    store.set_repo_scan_status(repo_id, "running", scan_error="")

    try:
        token = (project_gitlab_token(pid) if provider == "gitlab"
                 else project_github_token(pid))
        if not token:
            raise RuntimeError(f"no {provider} PAT configured for this project")
        store.update_job_progress(jid, "Downloading tarball…", 15)

        # Fetch tarball + remember the HEAD SHA we just scanned.
        default_branch = repo.get("default_branch") or "main"
        if provider == "github":
            client = github.GitHub(token, GITHUB_API)
            tar_bytes = client.get_archive(repo["owner"], repo["name"])
            # capture commit sha at head
            try:
                head = client.list_commits(repo["owner"], repo["name"],
                                           since_iso="1970-01-01T00:00:00Z",
                                           per_page=1, ref=default_branch)
                commit_sha = (head[0].get("sha") if head else "") or ""
            except Exception:  # noqa: BLE001
                commit_sha = ""
        else:
            # GitLab tarball endpoint
            import httpx as _httpx
            import urllib.parse as _up
            store.update_job_progress(jid, "Downloading GitLab archive…", 18)
            url = (f"https://gitlab.com/api/v4/projects/"
                   f"{_up.quote(repo['full_name'], safe='')}"
                   f"/repository/archive.tar.gz")
            r = _httpx.get(url, headers={"PRIVATE-TOKEN": token},
                           params={"sha": default_branch}, timeout=120.0,
                           follow_redirects=True)
            if r.status_code == 404:
                # Try the repo's default branch from /projects endpoint.
                try:
                    proj = _httpx.get(
                        f"https://gitlab.com/api/v4/projects/"
                        f"{_up.quote(repo['full_name'], safe='')}",
                        headers={"PRIVATE-TOKEN": token}, timeout=30.0).json()
                    db = proj.get("default_branch") or "main"
                    if db != default_branch:
                        default_branch = db
                        r = _httpx.get(url, headers={"PRIVATE-TOKEN": token},
                                       params={"sha": default_branch},
                                       timeout=120.0, follow_redirects=True)
                except Exception:  # noqa: BLE001
                    pass
            r.raise_for_status()
            tar_bytes = r.content
            # Capture HEAD SHA for the chosen branch so commit links work.
            try:
                commits = _httpx.get(
                    f"https://gitlab.com/api/v4/projects/"
                    f"{_up.quote(repo['full_name'], safe='')}/repository/commits",
                    headers={"PRIVATE-TOKEN": token},
                    params={"ref_name": default_branch, "per_page": 1},
                    timeout=30.0).json()
                commit_sha = (commits[0].get("id") if commits else "") or ""
            except Exception:  # noqa: BLE001
                commit_sha = ""
    except Exception as e:  # noqa: BLE001
        store.set_repo_scan_status(repo_id, "failed", scan_error=str(e)[:300])
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return

    # Anything past this point may take minutes and may call out to an LLM;
    # if it raises, we MUST flip scan_status off `running` so the user isn't
    # stuck. The whole block is wrapped in try/finally for that reason.
    scan_outcome = {"status": "failed", "error": "scan never completed"}
    files_seen = 0
    scanned = []
    matched_total = 0
    try:
        store.update_job_progress(jid, "Parsing test files…", 35)
        for rel, text in auto_cov.files_from_tarball(tar_bytes):
            files_seen += 1
            fw = auto_cov.detect_framework(rel, text)
            for t in auto_cov.extract_tests(rel, text, fw):
                scanned.append({
                    "id": f"trc:{repo_id}:{len(scanned)+1}",
                    "title": t["title"],
                    "file_path": rel,
                    "line": t.get("line") or 0,
                    "framework": fw,
                    "repo_id": repo_id,
                    "repo_full_name": repo["full_name"],
                    "git_provider": provider,
                    "default_branch": default_branch,
                    "commit_sha": commit_sha,
                })
        store.replace_test_repo_cases(pid, repo_id, scanned)
        print(f"[scan] {repo['full_name']}: {files_seen} files seen, "
              f"{len(scanned)} tests extracted", flush=True)

        store.update_job_progress(jid, "Matching to generated cases…", 60)
        all_features = store.list_features(project_id=pid)
        features = [f for f in all_features
                    if (not scoped_fid or f["id"] == scoped_fid)]
        llm = current_llm()
        all_scanned = store.list_test_repo_cases(project_id=pid)
        clean_scanned = [{**c, "id": c.get("id") or c.get("_id") or ""}
                         for c in all_scanned]
        for f_idx, f in enumerate(features):
            fid = f["id"]
            case_ids = store.feature_test_case_ids(fid)
            gen = store.cases_brief(case_ids)
            if not gen:
                continue

            def _prog(done, total, _fname=f.get("name", ""),
                      _fi=f_idx, _ftot=len(features)):
                base = 60 + (35 * _fi // max(1, _ftot))
                inc = (35 // max(1, _ftot)) * done // max(1, total)
                store.update_job_progress(
                    jid, f"Matching {_fname or 'feature'} · {done}/{total}",
                    min(95, base + inc))

            # Default to Jaccard-only matching to match Node's behavior +
            # eliminate any LLM-stall risk. Set AUTOMATION_USE_LLM=true on the
            # container to enable the slower, semantically-richer LLM verifier.
            use_llm = os.getenv("AUTOMATION_USE_LLM", "false").lower() == "true"
            try:
                matches = auto_cov.hybrid_match_generated_to_scanned(
                    llm, gen, clean_scanned, use_llm=use_llm,
                    progress_fn=_prog)
            except Exception as match_err:  # noqa: BLE001
                # Match failure on one feature must NOT kill the whole scan.
                print(f"[scan] match error on feature {f.get('name')}: "
                      f"{match_err}", flush=True)
                matches = [{"generated_id": g["id"], "match": None}
                           for g in gen]

            idx = {c["id"]: c for c in clean_scanned}
            covered_count = 0
            items = []
            for g, m in zip(gen, matches):
                mt = m.get("match")
                if mt:
                    covered_count += 1
                    sc = idx.get(mt["id"]) or {}
                    file_url = auto_cov.build_blob_url(
                        sc.get("git_provider", "github"),
                        sc.get("repo_full_name", ""),
                        sc.get("default_branch", "main"),
                        sc.get("file_path", ""),
                        sc.get("line") or None)
                    items.append({
                        "generated_id": g["id"],
                        "generated_title": g["title"],
                        "generated_type": g.get("type", ""),
                        "priority": g.get("priority"),
                        "display_id": g.get("display_id"),
                        "status": "covered",
                        "match": {**mt, "file_url": file_url,
                                  "repo_full_name": sc.get("repo_full_name", ""),
                                  "commit_sha": sc.get("commit_sha", ""),
                                  "line": sc.get("line") or 0}})
                else:
                    items.append({
                        "generated_id": g["id"],
                        "generated_title": g["title"],
                        "generated_type": g.get("type", ""),
                        "priority": g.get("priority"),
                        "display_id": g.get("display_id"),
                        "status": "missing",
                        "match": None})
            matched_total += covered_count
            store.save_automation_coverage(fid, pid, f.get("version", 1), {
                "total_generated": len(gen),
                "covered_count": covered_count,
                "missing_count": len(gen) - covered_count,
                "coverage_pct": (round(100 * covered_count / len(gen), 1)
                                  if gen else 0.0),
                "items": items,
                "scanned_repo_id": repo_id,
                "scanned_repo_full_name": repo["full_name"],
            })
        scan_outcome = {"status": "done", "error": ""}
    except Exception as scan_err:  # noqa: BLE001
        import traceback as _tb
        print(f"[scan] FATAL: {scan_err}\n{_tb.format_exc()}", flush=True)
        scan_outcome = {"status": "failed",
                        "error": f"{type(scan_err).__name__}: {scan_err}"[:300]}
    finally:
        # GUARANTEED status update — repo can never remain stuck "running".
        store.set_repo_scan_status(
            repo_id, scan_outcome["status"],
            scan_files_found=files_seen,
            scan_cases_count=len(scanned),
            scan_error=scan_outcome["error"],
            default_branch=default_branch,
            last_scan_at=time.time())
        store.merge_job_result(jid, files_seen=files_seen,
                               cases_extracted=len(scanned),
                               features_matched=matched_total,
                               scan_outcome=scan_outcome["status"])
        if scan_outcome["status"] == "failed":
            store.update_job(jid, status="failed", stage="error",
                             error=scan_outcome["error"])


JOB_WORKERS["test_repo_scan"] = _test_repo_scan_worker


# --------------------------------------------------------------- Import Sheet
def _create_imported_testcase(feature_id: str, row_dict: dict,
                                origin: str = "imported",
                                inherited_from: dict | None = None,
                                project_id: str | None = None,
                                project_imported_row_id: str | None = None,
                                identity_hash: str | None = None,
                                score: float | None = None) -> str:
    """Materialize a parsed sheet row into a wardenIQ test case + association.
    Returns the new case_id."""
    feature = store.get_feature(feature_id) or {}
    project_id = project_id or feature.get("project_id")
    identity_hash = identity_hash or row_dict.get("identity_hash")
    if not identity_hash:
        identity_hash = sheet_mod.identity_hash(row_dict)
    if project_id and identity_hash:
        existing = store.find_case_by_identity(project_id, identity_hash=identity_hash)
        if existing:
            store.associate(feature_id, existing["id"], origin, score)
            return existing["id"]

    title = row_dict.get("title") or "Imported test case"
    type_raw = (row_dict.get("category") or "").lower()
    case_type = "functional"
    for k, v in (("api", "api"), ("e2e", "e2e"), ("end-to-end", "e2e"),
                  ("ui", "ui"), ("edge", "nfr"), ("nfr", "nfr"),
                  ("functional", "functional"), ("business", "functional")):
        if k in type_raw:
            case_type = v
            break
    pri_norm = {"High": "P1", "Mid": "P2", "Low": "P3"}.get(
        row_dict.get("priority", "Mid"), "P2")
    pre = row_dict.get("preconditions") or ""
    raw_steps = row_dict.get("steps") or []
    expected = row_dict.get("expected_result") or ""
    step_pairs = []
    for i, raw_step in enumerate(raw_steps):
        if isinstance(raw_step, dict):
            action = raw_step.get("content") or raw_step.get("step") or ""
            exp = raw_step.get("expectedResult") or raw_step.get("expected_result") or ""
        else:
            action = str(raw_step or "")
            exp = ""
        if not exp and i == len(raw_steps) - 1 and expected:
            exp = expected
        if action:
            step_pairs.append({"action": action, "expected": exp})
    if not step_pairs:
        step_pairs = [{"action": title,
                        "expected": expected or "Behaviour observed as described"}]
    step_ids = []
    for s in step_pairs:
        emb = embedder.embed(f"{s['action']}. Expected: {s['expected']}")
        step_ids.append(store.get_or_create_step(s["action"], s["expected"],
                                                  emb, STEP_AUTO)["step_id"])
    cemb = embedder.embed(title + " " + " ".join(s["action"] for s in step_pairs))
    metadata = {
        "source_type": "manual_import",
        "identity_hash": identity_hash,
        "project_imported_row_id": project_imported_row_id,
        "inherited_from_feature_id": (inherited_from or {}).get("feature_id"),
    }
    cid = store.create_case(title, case_type, pri_norm, pre, step_ids,
                             row_dict.get("tags") or [], cemb, feature_id,
                             project_id=project_id,
                             identity_hash=identity_hash,
                             metadata=metadata)
    store.associate(feature_id, cid, origin, score)
    return cid


def _case_exists(case_id: str | None) -> bool:
    return store.case_exists(case_id)


def _promote_imported_row_to_feature(row_id: str, feature: dict, payload: dict,
                                      origin: str, score: float = 0.0,
                                      inherited_from: dict | None = None) -> str:
    """Link a canonical imported row to a feature, reusing a prior testcase."""
    feature_id = str(feature.get("id") or feature.get("_id"))
    project_id = feature.get("project_id")
    version = feature.get("version", 1)
    same_feature = store.get_row_promotion(row_id, feature_id)
    if same_feature and _case_exists(same_feature.get("promoted_testcase_id")):
        cid = same_feature["promoted_testcase_id"]
        store.associate(feature_id, cid, origin, score)
    else:
        prior = store.get_row_promotion(row_id)
        if prior and _case_exists(prior.get("promoted_testcase_id")):
            cid = prior["promoted_testcase_id"]
            store.associate(feature_id, cid, origin, score)
        else:
            cid = _create_imported_testcase(
                feature_id, payload, origin=origin,
                inherited_from=inherited_from, project_id=project_id,
                project_imported_row_id=row_id,
                identity_hash=payload.get("identity_hash") or sheet_mod.identity_hash(payload),
                score=score)
    store.link_row_to_feature(row_id, feature_id)
    store.record_row_promotion(row_id, project_id, feature_id, version, cid, score)
    return cid


def _parsed_row_from_payload(payload: dict) -> sheet_mod.ParsedRow:
    return sheet_mod.ParsedRow(
        sheet=payload.get("sheet", ""),
        row_number=payload.get("row_number", 0),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        intent=payload.get("intent", ""),
        category=payload.get("category"),
        suite=payload.get("suite", ""),
        priority=payload.get("priority", "Mid"),
        endpoint=payload.get("endpoint", ""),
        method=payload.get("method", ""),
        steps=payload.get("steps") or [],
        expected_result=payload.get("expected_result", ""),
        module=payload.get("module", ""),
        tags=payload.get("tags") or [],
        preconditions=payload.get("preconditions", ""),
        test_id=payload.get("test_id", ""),
        status=payload.get("status", ""),
    )


def _sheet_steps_preview(steps, limit: int = 4) -> list[str]:
    out = []
    for step in steps or []:
        if isinstance(step, dict):
            text = step.get("content") or step.get("step") or step.get("action") or ""
        else:
            text = str(step or "")
        text = " ".join(text.split())
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _feature_doc_for_import_context(feature: dict) -> dict:
    """Enrich feature scoring context from the stored unified context surface."""
    if not feature:
        return {}
    merged = dict(feature)
    feature_id = str(feature.get("id") or feature.get("_id") or "")
    version = feature.get("version", 1)
    try:
        unified = store.build_unified_context(feature_id, version) if feature_id else {}
    except Exception as exc:  # noqa: BLE001
        print(f"[import] unified context unavailable; using feature doc: {exc}", flush=True)
        unified = {}

    text_parts = [
        feature.get("text") or "",
        feature.get("summary") or "",
        unified.get("summaries", {}).get("prd") or "",
    ]
    for group in (unified.get("requirements") or {}).values():
        if isinstance(group, list):
            text_parts.extend(str(item) for item in group)
    business = unified.get("businessContext") or unified.get("business_context") or {}
    for key in ("userStories", "acceptanceCriteria", "assumptions", "risks", "requirements"):
        values = business.get(key) or []
        if isinstance(values, list):
            text_parts.extend(str(item) for item in values)
    technical = unified.get("technicalContext") or {}
    for section in ("prd", "hld", "lld"):
        block = technical.get(section) or {}
        text_parts.extend(str(item) for item in block.get("technicalLines") or [])
        text_parts.extend(str(item) for item in block.get("endpoints") or [])
    for chunk in (unified.get("rag") or {}).get("retrieved_chunks") or []:
        if isinstance(chunk, dict):
            text_parts.append(str(chunk.get("text") or ""))

    seen_text = set()
    merged_text = []
    for part in text_parts:
        compact = " ".join(str(part or "").split()).strip()
        if not compact:
            continue
        key = compact.lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        merged_text.append(compact)
    if merged_text:
        merged["text"] = "\n".join(merged_text)
    merged["description"] = (
        feature.get("description")
        or feature.get("summary")
        or unified.get("featureDescription")
        or ""
    )

    raw_api = []
    existing_api = feature.get("raw_api_spec") or unified.get("rawApiSpec") or []
    if isinstance(existing_api, list):
        raw_api.extend(ep for ep in existing_api if isinstance(ep, dict))
    endpoint_strings = []
    for section in ("prd", "hld", "lld"):
        block = technical.get(section) or {}
        endpoint_strings.extend(str(item) for item in block.get("endpoints") or [])
    for value in endpoint_strings:
        m = re.match(r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", value, re.I)
        if m:
            raw_api.append({"method": m.group(1).upper(), "path": m.group(2)})
        elif value.strip().startswith("/"):
            raw_api.append({"method": "", "path": value.strip()})
    if raw_api:
        deduped_api = []
        seen_api = set()
        for ep in raw_api:
            key = (str(ep.get("method") or "").upper(), str(ep.get("path") or "").lower())
            if not key[1] or key in seen_api:
                continue
            seen_api.add(key)
            deduped_api.append(ep)
        merged["raw_api_spec"] = deduped_api
    return merged


def _reuse_existing_import_rows(jid, feature_import_id: str, project_id: str,
                                feature_id: str, duplicate_of: str) -> None:
    """No-parse exact duplicate path: reuse canonical rows from old upload."""
    feature = store.get_feature(feature_id) or {}
    fi = store.get_feature_import(feature_import_id) or {}
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    import_batch_id = fi.get("import_batch_id") or feature_import_id
    rows = store.list_imported_rows_for_feature_import(duplicate_of)
    matched = 0
    stored = 0
    promoted_case_ids = []
    items = []
    store.update_job_progress(jid, "Reusing already uploaded sheet…", 35)
    for idx, r in enumerate(rows):
        payload = sheet_mod.normalize_imported_payload_shape(
            dict(r.get("normalized_payload") or {}))
        if not payload.get("title"):
            continue
        ihash = r.get("identity_hash") or payload.get("identity_hash") or sheet_mod.identity_hash(payload)
        payload["identity_hash"] = ihash
        row_obj = _parsed_row_from_payload(payload)
        result = sheet_mod.score_row(row_obj, ctx)
        store.add_imported_row_source(
            r["id"], feature_import_id, import_batch_id, feature_id,
            fi.get("original_filename", "") or payload.get("original_filename", ""),
            payload.get("sheet", "Sheet1"), payload.get("row_number", idx + 1))
        store.touch_imported_row_seen(
            r["id"],
            relevance_score=max(result.score, r.get("latest_relevance_score", 0) or 0),
            relevance_feature_id=feature_id)
        item = {
            "row_index": idx,
            "identity_hash": ihash,
            "project_imported_row_id": r["id"],
            "title": payload.get("title", ""),
            "category": payload.get("category"),
            "priority": payload.get("priority", "Mid"),
            "sheet": payload.get("sheet", ""),
            "row_number": payload.get("row_number", idx + 1),
            "endpoint": payload.get("endpoint", ""),
            "method": payload.get("method", ""),
            "steps_count": len(payload.get("steps") or []),
            "steps_preview": _sheet_steps_preview(payload.get("steps") or []),
            "expected_result": (payload.get("expected_result") or "")[:160],
            "score": result.score,
            "action": result.action,
            "breakdown": result.breakdown,
            "already_uploaded": True,
        }
        if result.action == "matched":
            cid = _promote_imported_row_to_feature(
                r["id"], feature, payload, origin="inherited",
                score=result.score,
                inherited_from={"feature_id": r.get("latest_relevance_feature_id")})
            item["promoted_testcase_id"] = cid
            promoted_case_ids.append(cid)
            matched += 1
        else:
            stored += 1
        items.append(item)
    store.update_feature_import(feature_import_id, row_count=len(items),
                                  accepted_count=matched, flagged_count=stored,
                                  rejected_count=0)
    store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                      f"Already uploaded · {matched} matched · {stored} stored",
                                      completed=True,
                                      result_json={"items": items,
                                                   "alreadyUploaded": True,
                                                   "duplicate_of": duplicate_of,
                                                   "import_batch_id": import_batch_id})
    store.merge_job_result(jid, row_count=len(items), matched=matched,
                            stored=stored, promoted_case_ids=promoted_case_ids,
                            alreadyUploaded=True, duplicate_of=duplicate_of,
                            import_batch_id=import_batch_id)


def _import_evidence_ok(row, ctx) -> bool:
    """GAP5 evidence gate: a matched row is only promoted when the feature's actual
    API surface backs it. A row WITH an endpoint must hit an endpoint in the feature's
    spec (and, for api_tests, its method must be in the spec too). Rows without an
    endpoint, or features with no API spec to check against, are not gated (so UI/
    business tests and spec-less features still promote on score alone)."""
    ep = (getattr(row, "endpoint", "") or "").strip()
    if not ep or not getattr(ctx, "endpoints", None):
        return True
    if sheet_mod._endpoint_match(ep, ctx.endpoints) <= 0:
        return False
    cat = (getattr(row, "category", "") or "").lower()
    method = (getattr(row, "method", "") or "").upper().strip()
    if cat in ("api_tests", "api") and method and ctx.methods and method not in ctx.methods:
        return False
    return True


def _test_import_worker(jid, params):
    """Parse the uploaded sheet, score rows against the feature, store
    canonical rows in the project pool, promote matches into the feature."""
    feature_import_id = params["feature_import_id"]
    project_id = params["project_id"]
    feature_id = params["feature_id"]
    fi = store.get_feature_import(feature_import_id)
    if not fi:
        store.update_job(jid, status="failed", stage="error",
                         error="feature_import not found")
        return
    duplicate_of = fi.get("duplicate_of_import_id")
    if duplicate_of:
        store.set_import_analysis_status(feature_import_id, "PROCESSING",
                                           "Reusing already uploaded sheet…")
        _reuse_existing_import_rows(jid, feature_import_id, project_id,
                                    feature_id, duplicate_of)
        return
    store.set_import_analysis_status(feature_import_id, "PROCESSING",
                                       "Parsing sheet…")
    store.update_job_progress(jid, "Parsing sheet…", 10)

    file_bytes = fi.get("file_bytes")
    if isinstance(file_bytes, str):
        import base64 as _b64
        file_bytes = _b64.b64decode(file_bytes)

    # ---- Pass 1: parse the sheet (header detect, merge propagation, group) ----
    try:
        rows = sheet_mod.parse_sheet(file_bytes,
                                       fi.get("original_filename", ""))
        content_signature = sheet_mod.content_signature(rows)
        store.update_feature_import(
            feature_import_id,
            content_signature_sha256=content_signature)
        duplicate_import = store.find_feature_import_by_signature(
            project_id, sig=content_signature, exclude_id=feature_import_id)
        if duplicate_import:
            store.update_feature_import(
                feature_import_id,
                duplicate_of_import_id=duplicate_import["id"])
            _reuse_existing_import_rows(jid, feature_import_id, project_id,
                                        feature_id, duplicate_import["id"])
            return
    except Exception as e:  # noqa: BLE001
        store.set_import_analysis_status(feature_import_id, "FAILED",
                                           f"parse error: {e}", completed=True)
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return

    feature = store.get_feature(feature_id) or {}
    feat_name = feature.get("name", "")
    feat_desc = (feature.get("description") or feature.get("summary") or "")[:600]

    # ---- Pass 2: QA-relevance gate (short LLM + hard-coded fallback) -------
    # Mirrors Node's `isQARelatedSpreadsheet`. The LLM gets the RAW cell
    # preview (same shape Node uses) so the prompt judges actual upload
    # content rather than already-cleaned rows. On LLM failure we fall back
    # to the deterministic keyword heuristic.
    if rows:
        store.update_job_progress(jid, "Classifying sheet (LLM)…", 25)
        raw_tables = sheet_mod.raw_tables(file_bytes,
                                           fi.get("original_filename", ""))
        preview = sheet_mod.build_tables_preview(raw_tables)
        try:
            is_qa, reason = sheet_mod.classify_sheet_is_qa(
                current_llm(), preview, feat_name, feat_desc)
        except Exception as e:  # noqa: BLE001
            is_qa, reason = None, f"classifier failed: {e}"
        if is_qa is None:
            # LLM unreachable → fall back to deterministic heuristic.
            is_qa = sheet_mod.looks_like_qa_sheet_heuristic(raw_tables)
            reason = (reason or "") + " · heuristic fallback"
        if not is_qa:
            store.set_import_analysis_status(
                feature_import_id, "COMPLETED",
                f"Not a QA sheet — {reason}",
                completed=True, result_json={"items": [], "rejected_reason": reason})
            store.update_feature_import(feature_import_id, row_count=0,
                                          rejected_count=len(rows))
            store.merge_job_result(jid, row_count=0, matched=0, stored=0,
                                     rejected=len(rows), rejected_reason=reason)
            return

    # ---- Pass 3: LLM polish in concurrent batches of 8 ---------------------
    # Drops metadata-only rows (is_testcase=false), normalizes title/category/
    # priority/steps, rewrites Gherkin-style narrative noise. Mirrors Node's
    # `polishImportedRowsWithAI`.
    if rows:
        store.update_job_progress(jid, "Polishing rows (LLM, batched)…", 35)
        def _polish_progress(done, total):
            store.update_job_progress(
                jid, f"Polishing rows · {done}/{total} batches",
                35 + (15 * done // max(1, total)))
        try:
            rows = sheet_mod.polish_all_rows(
                current_llm(), rows, feat_name, feat_desc,
                batch_size=8, max_workers=6, progress_fn=_polish_progress)
        except Exception as e:  # noqa: BLE001
            print(f"[import] polish failed (using parser output): {e}", flush=True)

    if not rows:
        store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                           "No test rows recognized",
                                           completed=True, result_json={"items": []})
        store.update_feature_import(feature_import_id, row_count=0)
        store.merge_job_result(jid, row_count=0, matched=0, stored=0)
        return

    # ---- Pass 4: algorithmic scoring + project-pool storage ----------------
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    store.update_job_progress(jid, "Scoring rows…", 55)

    import_batch_id = fi.get("import_batch_id") or feature_import_id
    matched = 0
    stored = 0
    promoted_case_ids = []
    items = []
    for idx, row in enumerate(rows):
        ihash = sheet_mod.identity_hash(row)
        payload = row.to_dict()
        payload["identity_hash"] = ihash
        result = sheet_mod.score_row(row, ctx)
        # GAP5 evidence gate: downgrade a "matched" row to the pool when the feature's
        # API surface doesn't actually back it (keeps unsupported endpoints out).
        action = result.action
        if action == "matched" and not _import_evidence_ok(row, ctx):
            action = "stored_for_later"
        match_status = "matched_feature" if action == "matched" else "unmatched_pool"
        prid = store.upsert_project_imported_row(
            project_id, ihash, payload,
            match_status=match_status, latest_score=result.score,
            latest_feature_id=feature_id,
            needs_project_analysis=(action != "matched"))
        store.add_imported_row_source(
            prid, feature_import_id, import_batch_id, feature_id,
            fi.get("original_filename", ""), row.sheet, row.row_number)
        item = {
            "row_index": idx,
            "identity_hash": ihash,
            "project_imported_row_id": prid,
            "title": row.title,
            "category": row.category,
            "priority": row.priority,
            "sheet": row.sheet,
            "row_number": row.row_number,
            "endpoint": row.endpoint,
            "method": row.method,
            "steps_count": len(row.steps),
            "steps_preview": _sheet_steps_preview(row.steps),
            "expected_result": row.expected_result[:160],
            "score": result.score,
            "action": action,
            "scorer_action": result.action,   # pre-evidence-gate (for review UI)
            "breakdown": result.breakdown,
        }
        if action == "matched":
            # Promote into the feature now.
            cid = _promote_imported_row_to_feature(
                prid, feature, payload, origin="imported", score=result.score)
            promoted_case_ids.append(cid)
            item["promoted_testcase_id"] = cid
            matched += 1
        else:
            stored += 1
        items.append(item)

    # GAP9: promoting imported rows changed this feature's test cases → its stored
    # test-plan runs are now out of date; flag them for regeneration.
    if promoted_case_ids:
        try:
            store.mark_feature_test_plans_stale(feature_id)
        except Exception:  # noqa: BLE001
            pass

    store.update_feature_import(feature_import_id, row_count=len(rows),
                                  accepted_count=matched, flagged_count=stored,
                                  rejected_count=0)
    store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                       f"{matched} matched · {stored} stored",
                                       completed=True,
                                       result_json={"items": items,
                                                      "import_batch_id": import_batch_id})
    store.merge_job_result(jid, row_count=len(rows), matched=matched,
                            stored=stored, promoted_case_ids=promoted_case_ids,
                            import_batch_id=import_batch_id)


JOB_WORKERS["test_import"] = _test_import_worker


# --- Import Sheet API --------------------------------------------------------
@app.post("/api/projects/{pid}/features/{fid}/tests/import")
async def upload_test_sheet(pid: str, fid: str, file: UploadFile = File(...)):
    """Upload a CSV/XLSX/TSV sheet of pre-existing tests. Returns a job_id +
    feature_import_id the UI uses for polling."""
    if not file.filename:
        raise HTTPException(400, "filename required")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")
    # Compute fingerprints for dedup
    file_sha = hashlib.sha256(raw).hexdigest()
    # Exact duplicate same feature: return the saved import state and do not
    # parse, classify, or call the LLM again.
    existing = store.find_feature_import_by_file_sha(pid, file_sha, feature_id=fid)
    if existing:
        eid = existing["id"]
        status = store.get_import_analysis_status(eid)
        result_json = dict((status or {}).get("result_json") or {})
        result_json["alreadyUploaded"] = True
        if status:
            store.set_import_analysis_status(
                eid, status.get("status", "COMPLETED"),
                status.get("details") or "Already uploaded",
                completed=bool(status.get("completed")),
                result_json=result_json)
        return {"ok": True, "feature_import_id": eid,
                 "duplicate_of": eid,
                 "alreadyUploaded": True,
                 "status": (status or {}).get("status", "PENDING"),
                 "completed": bool((status or {}).get("completed"))}

    import uuid as _uuid
    batch_id = _uuid.uuid4().hex
    # Exact duplicate elsewhere in the same project: create a lightweight import
    # record and reuse canonical imported rows in the worker. This keeps the no-
    # parse guarantee while still allowing feature-specific linking.
    existing_project = store.find_feature_import_by_file_sha(pid, file_sha)
    if existing_project:
        fid_doc = store.create_feature_import({
            "project_id": pid, "feature_id": fid,
            "original_filename": file.filename,
            "file_sha256": file_sha,
            "duplicate_of_import_id": existing_project["id"],
            "import_batch_id": batch_id,
            "row_count": 0, "accepted_count": 0,
            "flagged_count": 0, "rejected_count": 0,
        })
        store.set_import_analysis_status(
            fid_doc, "PENDING", "Queued duplicate reuse", completed=False,
            result_json={"items": [], "alreadyUploaded": True,
                         "duplicate_of": existing_project["id"]})
        jid = launch_job("test_import", {
            "feature_import_id": fid_doc, "project_id": pid, "feature_id": fid},
            label=f"Reuse imported sheet · {file.filename}",
            project_id=pid, feature_id=fid)
        return {"ok": True, "feature_import_id": fid_doc, "job_id": jid,
                "import_batch_id": batch_id, "alreadyUploaded": True,
                "duplicate_of": existing_project["id"]}

    import base64 as _b64
    encoded = _b64.b64encode(raw).decode("ascii")
    fid_doc = store.create_feature_import({
        "project_id": pid, "feature_id": fid,
        "original_filename": file.filename,
        "file_sha256": file_sha, "file_bytes": encoded,
        "import_batch_id": batch_id,
        "row_count": 0, "accepted_count": 0,
        "flagged_count": 0, "rejected_count": 0,
    })
    store.set_import_analysis_status(fid_doc, "PENDING", "Queued",
                                       completed=False)
    jid = launch_job("test_import", {
        "feature_import_id": fid_doc, "project_id": pid, "feature_id": fid},
        label=f"Import sheet · {file.filename}",
        project_id=pid, feature_id=fid)
    return {"ok": True, "feature_import_id": fid_doc, "job_id": jid,
             "import_batch_id": batch_id}


@app.get("/api/features/{fid}/tests/import/{import_id}/status")
def get_import_status(fid: str, import_id: str):
    status = store.get_import_analysis_status(import_id) or {}
    if not status:
        raise HTTPException(404, "import not found")
    return {"ok": True,
             "data": {"status": status.get("status", "PENDING"),
                      "details": status.get("details", ""),
                      "completed": bool(status.get("completed")),
                      "result_json": status.get("result_json")}}


@app.get("/api/features/{fid}/tests/import/{import_id}/analysis-result")
def get_import_analysis_result(fid: str, import_id: str):
    status = store.get_import_analysis_status(import_id) or {}
    if not status:
        raise HTTPException(404, "import not found")
    return {"ok": True, "data": status.get("result_json") or {}}


@app.get("/api/features/{fid}/tests/import/{import_id}/review")
def get_import_review(fid: str, import_id: str):
    """Return each imported row with its EFFECTIVE decision — the scorer's action
    (matched/stored_for_later) overridden by any reviewer correction — so the UI can
    render an editable Include / Keep-for-later toggle + note per row."""
    status = store.get_import_analysis_status(import_id) or {}
    if not status:
        raise HTTPException(404, "import not found")
    result = status.get("result_json") or {}
    batch_id = result.get("import_batch_id") or import_id
    corrections = store.import_corrections_for_batch(batch_id)
    items = []
    for it in (result.get("items") or []):
        rid = it.get("project_imported_row_id")
        ih = it.get("identity_hash")
        corr = corrections.get(rid) or corrections.get(ih)
        scorer_included = (it.get("action") == "matched")
        if corr:
            included = corr.get("action") == "include"
        else:
            included = scorer_included
        items.append({**it,
                      "included": included,
                      "scorer_action": it.get("action"),
                      "overridden": bool(corr),
                      "review_note": (corr or {}).get("note", "")})
    return {"ok": True, "data": {"items": items, "import_batch_id": batch_id}}


class ImportReviewItem(BaseModel):
    project_imported_row_id: str | None = None
    identity_hash: str | None = None
    action: str            # "include" | "exclude"
    note: str | None = None


class ImportReviewIn(BaseModel):
    reviews: list[ImportReviewItem] = []


@app.post("/api/features/{fid}/tests/import/{import_id}/review")
def submit_import_review(fid: str, import_id: str, body: ImportReviewIn, request: Request):
    """Apply reviewer decisions: 'include' promotes a stored row into this feature;
    'exclude' removes a previously-promoted row. Every decision is recorded as a
    correction so later re-checks respect it. Idempotent per row."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature["project_id"]
    status = store.get_import_analysis_status(import_id) or {}
    result = status.get("result_json") or {}
    batch_id = result.get("import_batch_id") or import_id
    included = excluded = 0
    for rv in (body.reviews or []):
        action = (rv.action or "").strip().lower()
        if action not in ("include", "exclude"):
            continue
        row = None
        if rv.project_imported_row_id:
            row = store.get_project_imported_row(rv.project_imported_row_id)
        if not row and rv.identity_hash:
            row = store.get_project_imported_row_by_hash(pid, rv.identity_hash)
        if not row or row.get("project_id") != pid:
            continue
        rid = row["id"]
        promotion = store.get_row_promotion(rid, fid)
        is_promoted = bool(promotion and _case_exists(promotion.get("promoted_testcase_id")))
        if action == "include" and not is_promoted:
            payload = sheet_mod.normalize_imported_payload_shape(
                row.get("normalized_payload") or {})
            if payload.get("title"):
                payload = dict(payload)
                payload["identity_hash"] = row.get("identity_hash")
                _promote_imported_row_to_feature(
                    rid, feature, payload, origin="reviewed",
                    score=row.get("latest_relevance_score", 0) or 0)
                included += 1
        elif action == "exclude" and is_promoted:
            store.unlink_imported_row_from_feature(rid, fid)
            excluded += 1
        store.record_import_correction(
            pid, batch_id, fid, rid, row.get("identity_hash"),
            action, rv.note or "", actor=(_current_user(request) or {}).get("email"))
    return {"ok": True, "data": {"included": included, "excluded": excluded}}


@app.get("/api/features/{fid}/tests/import/template")
def download_import_template(fid: str, format: str = "xlsx"):
    if format == "csv":
        body = sheet_mod.build_csv_template()
        headers = {"Content-Disposition": 'attachment; filename="wardeniq-import-template.csv"'}
        return Response(content=body, media_type="text/csv", headers=headers)
    body = sheet_mod.build_xlsx_template()
    headers = {"Content-Disposition": 'attachment; filename="wardeniq-import-template.xlsx"'}
    return Response(content=body,
                     media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     headers=headers)


# --- Project-wide imported-sheet library ------------------------------------
@app.get("/api/features/{fid}/imported-sheets")
def list_imported_sheet_library(fid: str):
    """Return the project-wide pool of imported rows + which ones are already
    linked to this feature. Used by the Reuse-imported-sheets modal."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature["project_id"]
    rows = store.list_project_imported_rows(pid, feature_id=fid)
    out = []
    for r in rows:
        payload = sheet_mod.normalize_imported_payload_shape(
            r.get("normalized_payload") or {})
        source = r.get("latest_source") or {}
        out.append({
            "id": r["id"],
            "identity_hash": r.get("identity_hash"),
            "title": payload.get("title", ""),
            "category": payload.get("category"),
            "priority": payload.get("priority", "Mid"),
            "sheet": source.get("sheet_name") or payload.get("sheet", ""),
            "original_filename": source.get("original_filename", ""),
            "feature_import_id": source.get("feature_import_id", ""),
            "import_batch_id": source.get("import_batch_id", ""),
            "source_row_number": source.get("row_number"),
            "endpoint": payload.get("endpoint", ""),
            "method": payload.get("method", ""),
            "steps_count": len(payload.get("steps") or []),
            "steps_preview": _sheet_steps_preview(payload.get("steps") or []),
            "expected_result": (payload.get("expected_result") or "")[:160],
            "score": r.get("latest_relevance_score", 0),
            "match_status": r.get("current_match_status"),
            "is_in_feature": bool(r.get("mapped_to_feature")),
            "times_seen": r.get("times_seen", 1),
        })
    return {"ok": True, "data": {"project_id": pid, "feature_id": fid,
                                    "count": len(out),
                                    "imported_sheet_tests": out}}


class LibraryHashesIn(BaseModel):
    identity_hashes: list[str] | None = None
    project_imported_row_ids: list[str] | None = None
    delete_from_system: bool = False
    feature_import_id: str | None = None
    original_filename: str | None = None
    sheet_name: str | None = None


@app.post("/api/features/{fid}/imported-sheets/add")
def add_imported_sheet_rows(fid: str, body: LibraryHashesIn):
    """Pull selected rows from the project pool into THIS feature's test cases."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature["project_id"]
    target_rows = []
    for h in (body.identity_hashes or []):
        r = store.get_project_imported_row_by_hash(pid, h)
        if r:
            target_rows.append(r)
    for rid in (body.project_imported_row_ids or []):
        r = store.get_project_imported_row(rid)
        if r and r.get("project_id") == pid:
            target_rows.append(r)
    if not target_rows:
        return {"ok": True, "data": {"promoted_count": 0, "testcase_ids": []}}
    deduped = {}
    for r in target_rows:
        deduped[r["id"]] = r
    promoted = []
    for r in deduped.values():
        payload = sheet_mod.normalize_imported_payload_shape(
            r.get("normalized_payload") or {})
        if not payload.get("title"):
            continue
        payload = dict(payload)
        payload["identity_hash"] = r.get("identity_hash") or payload.get("identity_hash")
        cid = _promote_imported_row_to_feature(
            r["id"], feature, payload, origin="inherited",
            score=r.get("latest_relevance_score", 0) or 0,
            inherited_from={"feature_id": r.get("latest_relevance_feature_id")})
        promoted.append(cid)
    return {"ok": True, "data": {"promoted_count": len(promoted),
                                   "testcase_ids": promoted}}


@app.post("/api/features/{fid}/imported-sheets/remove")
def remove_imported_sheet_rows(fid: str, body: LibraryHashesIn):
    """Remove selected rows from THIS feature. With delete_from_system=true the
    canonical row is also dropped from the project pool entirely."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature["project_id"]
    target_rows = []
    for h in (body.identity_hashes or []):
        r = store.get_project_imported_row_by_hash(pid, h)
        if r:
            target_rows.append(r)
    for rid in (body.project_imported_row_ids or []):
        r = store.get_project_imported_row(rid)
        if r and r.get("project_id") == pid:
            target_rows.append(r)
    if body.delete_from_system and (
        body.feature_import_id or body.original_filename or body.sheet_name
    ):
        source_ids = store.list_project_imported_row_ids_for_source(
            pid,
            feature_import_id=body.feature_import_id,
            original_filename=body.original_filename,
            sheet_name=body.sheet_name)
        for rid in source_ids:
            r = store.get_project_imported_row(rid)
            if r and r.get("project_id") == pid:
                target_rows.append(r)
    removed_cases = 0
    deleted_imports = []
    affected_features = set()
    deduped = {}
    for r in target_rows:
        deduped[r["id"]] = r
    for r in deduped.values():
        if body.delete_from_system:
            result = store.delete_imported_row_from_project(pid, r["id"])
            removed_cases += result.get(
                "removed_testcase_links",
                len(result.get("deleted_testcase_ids") or []))
            deleted_imports.extend(result.get("deleted_feature_import_ids") or [])
            affected_features.update(result.get("affected_feature_ids") or [])
        else:
            result = store.unlink_imported_row_from_feature(r["id"], fid)
            removed_cases += result.get("removed_testcases", 0)
            affected_features.add(fid)
    return {"ok": True, "data": {"removed_count": len(deduped),
                                   "removed_testcases": removed_cases,
                                   "deleted_feature_imports": deleted_imports,
                                   "affected_features": sorted(affected_features)}}


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _feature_embedding(feature):
    text = ((feature.get("name") or "") + " " +
            (feature.get("description") or feature.get("summary") or ""))[:2000]
    try:
        return embedder.embed(text, task="query") if text.strip() else None
    except Exception:  # noqa: BLE001
        return None


def _pool_row_embedding(row):
    """GAP8: embedding for a pool row, cached on the row so we embed it once."""
    emb = row.get("embedding")
    if emb:
        return emb
    p = row.get("normalized_payload") or {}
    steps_txt = " ".join((s.get("content") if isinstance(s, dict) else str(s))
                         for s in (p.get("steps") or []))
    text = f"{p.get('title', '')} {p.get('description', '')} {steps_txt}".strip()[:2000]
    if not text:
        return None
    try:
        emb = embedder.embed(text)
        store.set_imported_row_embedding(row["id"], emb)
        return emb
    except Exception:  # noqa: BLE001
        return None


def _rescan_pool_for_feature(feature) -> tuple[int, list[str]]:
    """Re-score this project's unlinked imported-pool rows against `feature` and
    promote newly-matching, evidence-backed rows into it. Returns (rescored,
    promoted_case_ids). Shared by: the on-demand refresh endpoint, the post-generation
    recheck (GAP4), and the scheduled project-wide re-analysis (GAP2)."""
    if not feature:
        return 0, []
    fid = str(feature.get("id") or feature.get("_id"))
    pid = feature.get("project_id")
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    pool = store.list_project_imported_rows(pid, feature_id=fid, unlinked_only=True)
    # GAP8 (opt-in): embed the feature once for the semantic-match path.
    feat_emb = _feature_embedding(feature) if IMPORT_SEMANTIC_MATCH else None
    promoted, rescored = [], 0
    for r in pool:
        payload = sheet_mod.normalize_imported_payload_shape(
            r.get("normalized_payload") or {})
        if not payload.get("title"):
            continue
        row_obj = _parsed_row_from_payload(payload)
        res = sheet_mod.score_row(row_obj, ctx)
        rescored += 1
        store.update_imported_row_relevance(
            r["id"], relevance_score=res.score, relevance_feature_id=fid,
            needs_project_analysis=False)
        # Promote if the algorithmic scorer matched (GAP5-gated) OR, when semantic
        # matching is enabled, if the embedding similarity clears the threshold.
        promote_it = (res.action == "matched")
        if not promote_it and IMPORT_SEMANTIC_MATCH and feat_emb:
            remb = _pool_row_embedding(r)
            if remb and _cosine(feat_emb, remb) >= IMPORT_SEMANTIC_THRESHOLD:
                promote_it = True
        if promote_it and _import_evidence_ok(row_obj, ctx):
            payload = dict(payload)
            payload["identity_hash"] = r.get("identity_hash") or payload.get("identity_hash")
            cid = _promote_imported_row_to_feature(
                r["id"], feature, payload, origin="inherited", score=res.score,
                inherited_from={"feature_id": r.get("latest_relevance_feature_id")})
            promoted.append(cid)
    if promoted:
        try:
            store.mark_feature_test_plans_stale(fid)
        except Exception:  # noqa: BLE001
            pass
    return rescored, promoted


def _apply_import_overlays(feature) -> int:
    """GAP3: flag GENERATED test cases that are also backed by an imported QA-library
    row (strong token overlap on title+steps), so the UI can badge "matches imported
    QA library". Pure annotation — never changes the case content. Returns count."""
    if not feature:
        return 0
    fid = str(feature.get("id") or feature.get("_id"))
    pid = feature.get("project_id")
    try:
        cases = store.get_feature_cases(fid)
        pool = store.list_project_imported_rows(pid)
    except Exception:  # noqa: BLE001
        return 0
    if not cases or not pool:
        return 0
    pool_tok = []
    for r in pool:
        p = r.get("normalized_payload") or {}
        steps_txt = " ".join((s.get("content") if isinstance(s, dict) else str(s))
                             for s in (p.get("steps") or []))
        toks = sheet_mod.tokenize(f"{p.get('title', '')} {steps_txt}")
        if toks:
            pool_tok.append((r, p, toks))
    if not pool_tok:
        return 0
    stamped = 0
    for case in cases:
        # Overlay is for genuinely GENERATED cases, not ones already sourced from imports.
        if (case.get("association") or {}).get("origin") in ("imported", "inherited", "reviewed"):
            continue
        steps_txt = " ".join(f"{s.get('action', '')} {s.get('expected', '')}"
                             for s in (case.get("steps") or []) if isinstance(s, dict))
        ctok = sheet_mod.tokenize(f"{case.get('title', '')} {steps_txt}")
        if not ctok:
            continue
        best, best_p, best_score = None, None, 0.0
        for r, p, toks in pool_tok:
            j = sheet_mod._jaccard(ctok, toks)
            if j > best_score:
                best, best_p, best_score = r, p, j
        if best and best_score >= 0.5:
            store.set_case_import_overlay(case["id"], {
                "confidence": round(best_score, 3),
                "matched_pool_row_id": best["id"],
                "matched_title": (best_p.get("title") or "")[:160],
                "basis": "title+steps overlap",
            })
            stamped += 1
    return stamped


def _import_reanalysis_scheduler(interval_s: int = 300):
    """GAP2: every few minutes, take projects with imported-pool rows still awaiting
    project-wide analysis and re-scan them against every feature in the project,
    auto-promoting new matches. `_rescan_pool_for_feature` clears the pending flag as
    it goes, so each import batch is swept once."""
    while True:
        time.sleep(interval_s)
        try:
            pids = store.list_projects_with_pending_import_rows()
        except Exception as e:  # noqa: BLE001
            print(f"[import-scheduler] list failed: {e}", flush=True)
            continue
        for pid in pids:
            try:
                for feat in store.list_features(project_id=pid):
                    try:
                        _rescan_pool_for_feature(feat)
                    except Exception:  # noqa: BLE001
                        continue
            except Exception as e:  # noqa: BLE001
                print(f"[import-scheduler] project {pid}: {e}", flush=True)


@app.post("/api/features/{fid}/imported-sheets/refresh")
def refresh_imported_sheet_library(fid: str):
    """On-demand: re-score every `unmatched_pool` row in this project against THIS
    feature's current context; newly-matching rows are auto-promoted."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    rescored, promoted = _rescan_pool_for_feature(feature)
    return {"ok": True, "data": {"rescored": rescored,
                                   "newly_promoted": len(promoted)}}


# --------------------------------------------------------------- API
@app.get("/api/status")
def status():
    ok = False
    try:
        ok = store.ping()
    except Exception:  # noqa: BLE001
        pass
    return {"app": "wardenIQ", "version": VERSION, "boot": BOOT, "mongo_connected": ok,
            "counts": store.counts() if ok else {},
            "indexes": store.index_status() if ok else {},
            "embedding": {"provider": embedder.provider, "model": embedder.model,
                          "dims": embedder.dim, "health": embedder.health()},
            "llm": (lambda lm: {"model": lm.model, "provider": lm.provider, "health": lm.health()})(current_llm()),
            "thresholds": {"step_auto_reuse": STEP_AUTO, "case_auto_reuse": CASE_AUTO,
                           "suggest": SUGGEST}}


from extract import chunk as chunk_doc

def _fallback_feature_summary(name: str, raw: str) -> str:
    original = str(raw or "")
    lower_original = original.lower()
    if "profile" in lower_original and "event" in lower_original and ("join" in lower_original or "create" in lower_original):
        return (
            "Users can join or create events while completing required profile information inline. "
            "The feature gates event actions on required profile fields, shows clear prompts or errors, "
            "and avoids forcing users through a separate onboarding flow."
        )
    def clean_piece(value: str) -> str:
        value = re.sub(r"###\s*(?:Document|Uploaded Documents?|Pasted requirement)\s*:?.*?(?=\n|$)", " ", value, flags=re.I)
        value = re.sub(r"\b[\w.-]+\.(?:pdf|docx?|md|txt|markdown)\b", " ", value, flags=re.I)
        value = re.sub(r"\b(?:PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}", " ", value, flags=re.I)
        value = re.sub(r"\b(?:PRD|HLD|LLD)\b\s*:?", " ", value, flags=re.I)
        return " ".join(value.replace("#", " ").split())

    raw_lines = [clean_piece(x) for x in original.splitlines()]
    product_terms = re.compile(r"\b(user|customer|profile|event|join|create|select|submit|validate|must|should|required|allow|prevent|display|error)\b", re.I)
    bad_terms = re.compile(r"\b(architecture|monolith|database|table|redis|queue|deployment|module|component|system overview)\b", re.I)
    candidates = []
    for line in raw_lines:
        if 60 <= len(line) <= 360 and product_terms.search(line) and not bad_terms.search(line):
            candidates.append(line)
        if len(candidates) >= 2:
            break
    if candidates:
        clean = " ".join(candidates)
    else:
        clean = clean_piece(original)
    if len(clean) > 260:
        clean = clean[:260].rsplit(" ", 1)[0] + "…"
    return clean or f"{name} is ready for QA review with generated test coverage."


def _display_feature_summary(feature: dict) -> str:
    summary = " ".join(str(feature.get("summary") or "").split()).strip()
    looks_raw = (
        not summary
        or summary.startswith("###")
        or bool(re.search(r"\b(?:PRD|HLD|LLD|Document)\b", summary[:120], re.I))
        or bool(re.search(r"\b[\w.-]+\.(?:pdf|docx?|md|txt|markdown)\b", summary[:180], re.I))
    )
    if not looks_raw and len(summary) >= 40:
        return summary
    return _fallback_feature_summary(feature.get("name") or "Feature", feature.get("text") or summary)


def _generate_feature_summary(name: str, raw: str) -> str:
    """Generate a clean product summary for UI/reporting; never block creation."""
    prompt = f"""
Create a clean feature summary for a QA workspace.

Rules:
- 2 to 3 concise sentences.
- Describe product/user behavior, not document filenames.
- Do not mention PRD, HLD, LLD, source document, uploaded file, or markdown headings.
- Do not include test-case counts.
- Return JSON only: {{"summary": "..."}}

Feature name: {name}

Evidence:
{(raw or '')[:6000]}
""".strip()
    try:
        data = current_llm().chat_json(
            "You write concise feature summaries for QA managers.",
            prompt,
            temperature=0.1,
        )
        summary = " ".join(str((data or {}).get("summary") or "").split()).strip()
        if summary and len(summary) >= 40:
            return summary[:700]
    except Exception:  # noqa: BLE001
        pass
    return _fallback_feature_summary(name, raw)


class MatchKeyIn(BaseModel):
    match_key: str = ""


@app.post("/api/features/{fid}/match-key")
def set_feature_match_key(fid: str, body: MatchKeyIn):
    """Set/clear a feature's manual PR match tag (editor+, gated by auth_gateway).
    PRs whose title/body contain the bracketed tag (e.g. [HOLDS]) auto-map to this
    feature on the next poll -- for projects without a linked Jira epic."""
    if not store.get_feature(fid):
        raise HTTPException(404, "feature not found")
    return {"match_key": store.set_feature_match_key(fid, body.match_key)}


@app.post("/api/features")
async def create_feature(request: Request, name: str = Form(...), project_id: str = Form(""),
                         key: str = Form(""), match_key: str = Form(""), text: str = Form(""),
                         focus: str = Form(""), total: int = Form(16),
                         confluence_url: list[str] = Form(default=[]),
                         confluence_children: bool = Form(True),
                         figma_url: list[str] = Form(default=[]),
                         files: list[UploadFile] = File(None)):
    # Combine every uploaded doc (PRD/HLD/LLD/…) + pasted text into one corpus,
    # each section labelled so the LLM and the embeddings keep document context.
    parts, sources, pdf_urls = [], [], []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        txt = extract_text(f.filename, data)
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
        if f.filename.lower().endswith(".pdf"):
            pdf_urls.extend(extractmod.pdf_links(data))
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    # Multiple Confluence / Figma links are supported (one field can carry several,
    # comma/space/newline-separated, and the field can be repeated). Split + de-dupe.
    confluence_urls = _split_links(confluence_url)
    figma_urls = _split_links(figma_url)
    # Figma links found inside PDFs are read via the API too; other PDF links get crawled.
    pdf_figma = [u for u in pdf_urls if "figma.com" in u.lower()]
    crawl_seeds = [u for u in pdf_urls if "figma.com" not in u.lower()]
    for u in figma_urls:
        if not figma.Figma.file_key_from_url(u):
            raise HTTPException(400, f"could not read a Figma file key from: {u[:80]}")
    has_figma = bool(figma_urls or pdf_figma)
    has_confluence = bool(confluence_urls)
    external = has_figma or has_confluence or bool(crawl_seeds)
    # Fail fast on missing config so the user gets immediate feedback (the fetching
    # itself happens in the background job below).
    if has_figma and not figma_client().ok():
        raise HTTPException(400, "Figma token not configured — add a Figma access token in Settings")
    if has_confluence and not jira_client().ok():
        raise HTTPException(400, "Confluence not configured — set Jira base URL, email & API token in Settings")
    if not parts and not external:
        raise HTTPException(400, "no document text provided")

    pid = project_id or store.get_or_default_project()
    _require_project(request, pid)   # can't create a feature in a project you can't access
    epic_key = (key or "").strip() or None
    if epic_key and store.epic_bound_group(pid, epic_key):
        raise HTTPException(409, f"Epic '{epic_key}' is already associated with another feature")
    import json as _json
    try:
        focus_d = _json.loads(focus) if focus else None
    except Exception:  # noqa: BLE001
        focus_d = None

    base_raw = "\n\n".join(parts)
    summary = _generate_feature_summary(name, base_raw) if base_raw.strip() else name
    emb = embedder.embed((base_raw or name)[:2000])
    fid = store.create_feature(name, pid, sources, base_raw, summary, emb, key=epic_key,
                               match_key=((match_key or "").strip().upper() or None))

    if not external:
        # Fast path: only local docs / pasted text — index + generate inline (unchanged).
        chunks = []
        for i, ch in enumerate(chunk_doc(base_raw, max_chars=1200, overlap=150)):
            chunks.append({"source": sources[0] if sources else "combined",
                           "chunk_index": i, "text": ch, "embedding": embedder.embed(ch)})
        store.add_feature_chunks(fid, pid, chunks)
        jid = launch_job("generate", {"feature_id": fid, "text": base_raw, "focus": focus_d,
                                      "total": int(total)},
                         label=f"Generate tests — {name}", project_id=pid, feature_id=fid)
        return {"feature_id": fid, "project_id": pid, "job_id": jid,
                "chars": len(base_raw), "sources": sources, "doc_count": len(sources),
                "chunks": len(chunks)}

    # External sources present → do the (potentially slow) fetching in a background
    # ingest job that reports progress and then chains generation on the same job.
    jid = launch_job("ingest", {
        "feature_id": fid, "project_id": pid, "name": name,
        "base_parts": parts, "base_sources": sources,
        "figma_urls": figma_urls, "pdf_figma": pdf_figma, "crawl_seeds": crawl_seeds,
        "confluence_urls": confluence_urls, "confluence_children": bool(confluence_children),
        "focus": focus_d, "total": int(total)},
        label=f"Ingest & generate — {name}", project_id=pid, feature_id=fid)
    doc_count = len(sources) + len(confluence_urls) + len(figma_urls) + (1 if pdf_figma else 0)
    return {"feature_id": fid, "project_id": pid, "job_id": jid,
            "chars": len(base_raw), "sources": sources, "doc_count": doc_count, "chunks": 0}


def _split_links(values) -> list:
    """Accept a str or list of strings (each possibly holding several URLs separated
    by newlines / commas / spaces) and return a de-duped, order-preserving URL list."""
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values or []:
        for piece in re.split(r"[\s,]+", (v or "").strip()):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return list(dict.fromkeys(out))


def _gather_external(parts, sources, *, figma_urls=(), pdf_figma=(), confluence_urls=(),
                     confluence_children=True, crawl_seeds=(), jid=None):
    """Fetch external evidence (multiple Figma designs, multiple Confluence pages +
    children, and non-Figma links) and append it to `parts`/`sources` in place.
    Best-effort: a source that fails is skipped and recorded in the returned
    warnings list. Returns (figma_data, warnings). Shared by the ingest worker
    (background, with progress) and the new-version endpoint (synchronous)."""
    def prog(stage, pct):
        if jid:
            store.update_job_progress(jid, stage, pct)

    warnings = []
    figma_data = None

    # ---- Figma designs (explicit links + figma.com links found in PDFs) ----
    figma_keys = []
    for u in list(figma_urls) + list(pdf_figma):
        k = figma.Figma.file_key_from_url(u)
        if k:
            figma_keys.append(k)
    figma_keys = list(dict.fromkeys(figma_keys))
    if figma_keys:
        prog(f"Reading {len(figma_keys)} Figma design(s)", 8)
        fc = figma_client()
        summaries = []
        if fc.ok():
            for k in figma_keys:
                try:
                    summaries.append(fc.read_design(k))
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"Figma {k}: {e}")
        figma_data = figma.Figma.merge_summaries(summaries)
        if figma_data:
            scr = "; ".join(s.get("name", "") for s in (figma_data.get("sampleScreens") or [])[:20])
            uitext = " | ".join((figma_data.get("textBlocks") or [])[:60])
            parts.append(f"### Document: Figma — {figma_data.get('fileName', 'design')}\n"
                         f"Screens: {scr}\nUI text: {uitext}")
            sources.append("figma")

    # ---- Confluence pages (each with its child pages) ----
    confluence_urls = list(confluence_urls)
    if confluence_urls:
        prog(f"Reading {len(confluence_urls)} Confluence page(s)", 20)
        j = jira_client()
        if j.ok():
            for url in confluence_urls:
                page_id = extractmod.confluence_page_id_from_url(url)
                if not page_id:
                    warnings.append(f"Confluence: unreadable link {url[:60]}")
                    continue
                try:
                    page = j.get_confluence_page(page_id)
                    ptxt = extractmod.html_to_text(page.get("html", ""))
                    if ptxt.strip():
                        parts.append(f"### Document: Confluence — {page.get('title', 'page')}\n{ptxt}")
                        sources.append(f"confluence:{page.get('id')}")
                    if confluence_children:
                        for child in j.get_confluence_children(page_id):
                            cp = j.get_confluence_page(child["id"])
                            ctxt = extractmod.html_to_text(cp.get("html", ""))
                            if ctxt.strip():
                                parts.append(f"### Document: Confluence — {cp.get('title', 'subpage')}\n{ctxt}")
                                sources.append(f"confluence:{cp.get('id')}")
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"Confluence {page_id}: {e}")

    # ---- Follow the remaining (non-Figma) links ----
    crawl_seeds = list(dict.fromkeys(crawl_seeds))
    if crawl_seeds:
        prog("Following linked pages", 30)
        import weblinks
        try:
            for pg in weblinks.crawl(crawl_seeds):
                parts.append(f"### Document: Linked page — {pg['url']}\n{pg['text'][:20000]}")
                sources.append(f"link:{pg['url'][:80]}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Link crawl: {e}")

    return figma_data, warnings


def _ingest_worker(jid, params):
    """Background ingestion for external sources; augments the feature's corpus with
    progress updates, then chains generation on the same job."""
    fid = params["feature_id"]
    pid = params["project_id"]
    name = params.get("name") or ""
    parts = list(params.get("base_parts") or [])
    sources = list(params.get("base_sources") or [])

    figma_data, warnings = _gather_external(
        parts, sources,
        figma_urls=params.get("figma_urls") or [], pdf_figma=params.get("pdf_figma") or [],
        confluence_urls=params.get("confluence_urls") or [],
        confluence_children=params.get("confluence_children", True),
        crawl_seeds=params.get("crawl_seeds") or [], jid=jid)
    if figma_data:
        store.set_feature_figma(fid, figma_data)

    # ---- Rebuild corpus, update the feature, re-index for RAG ----
    store.update_job_progress(jid, "Indexing evidence", 40)
    raw = "\n\n".join(parts)
    if not raw.strip():
        store.update_job(jid, status="failed", stage="error",
                         error="No readable content from the provided sources. " + "; ".join(warnings[:3]))
        return
    summary = _generate_feature_summary(name, raw)
    emb = embedder.embed(raw[:2000])
    store.update_feature_doc(fid, sources, raw, summary, emb)
    chunks = []
    for i, ch in enumerate(chunk_doc(raw, max_chars=1200, overlap=150)):
        chunks.append({"source": sources[0] if sources else "combined",
                       "chunk_index": i, "text": ch, "embedding": embedder.embed(ch)})
    store.add_feature_chunks(fid, pid, chunks)
    if warnings:
        store.update_job_progress(jid, "Some sources skipped — " + "; ".join(warnings[:3]), 45)

    # ---- Generate on the SAME job (reuses the generate worker + auto test-repo scan) ----
    _gen_worker(jid, {"feature_id": fid, "text": raw,
                      "focus": params.get("focus"), "total": params.get("total")})


JOB_WORKERS["ingest"] = _ingest_worker


def _reembed_worker(jid, params):
    """Switch the embedding model: rebuild all vector indexes at the new dimension
    and re-embed every stored vector. Search/dedup/Mind-Map are degraded until this
    finishes (the vectors and indexes are being replaced)."""
    global embedder
    embedder = current_embedder()          # now points at the newly-saved model
    dim = int(params.get("dim") or embedder.dim)
    store.update_job_progress(jid, "Dropping old vector indexes", 3)
    store.drop_vector_indexes()
    counts = store.reembed_all(lambda t: embedder.embed(t),
                               progress=lambda s, p: store.update_job_progress(jid, s, p))
    store.update_job_progress(jid, "Building vector indexes at new dimension", 96)
    store.create_vector_indexes(dim)
    store.merge_job_result(jid, reembedded=counts, dim=dim,
                           provider=embedder.provider, model=embedder.model)
    store.update_job_progress(jid, "done", 100)


JOB_WORKERS["reembed"] = _reembed_worker


def _migrate_worker(jid, params):
    """Copy the whole database to a target MongoDB, then point MONGO_URI at it (.env).
    The app keeps running on the CURRENT database until the user restarts, so a failed
    or partial copy never strands them — the source stays authoritative."""
    target = params["target_uri"]
    overwrite = bool(params.get("overwrite"))
    store.update_job_progress(jid, "Starting migration", 2)
    counts = store.migrate_to(
        target, overwrite=overwrite,
        progress=lambda s, p: store.update_job_progress(jid, s, p))
    store.update_job_progress(jid, "Pointing wardenIQ at the new database (.env)", 97)
    ok, err = _write_env_var(ENV_FILE_PATH, "MONGO_URI", target)
    if not ok:
        raise RuntimeError(f"data was copied, but writing the config file failed: {err}")
    store.merge_job_result(jid, copied=counts, total_docs=sum(counts.values()),
                           restart_required=True, apply_cmd="docker compose up -d")
    store.update_job_progress(jid, "done", 100)


JOB_WORKERS["migrate"] = _migrate_worker


@app.post("/api/features/{fid}/regenerate")
def regenerate(fid: str, body: dict):
    """Re-run generation on an existing feature with a different depth/focus
    (adds new cases; dedup keeps existing ones)."""
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    import json as _json
    focus = body.get("focus")
    if isinstance(focus, str):
        try:
            focus = _json.loads(focus)
        except Exception:  # noqa: BLE001
            focus = None
    total = int(body.get("total", GEN_TOTAL))
    jid = launch_job("generate", {"feature_id": fid, "text": f.get("text", ""),
                                  "focus": focus, "total": total},
                     label=f"Regenerate — {f.get('name')}", project_id=f.get("project_id"),
                     feature_id=fid)
    return {"job_id": jid}


async def _read_corpus(files, text):
    parts, sources = [], []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        txt = extract_text(f.filename, data)
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    return "\n\n".join(parts), sources


@app.post("/api/features/{fid}/versions")
async def new_version(fid: str, text: str = Form(""), name: str = Form(""), key: str = Form(""),
                      focus: str = Form(""), total: int = Form(16), replace: str = Form("false"),
                      confluence_url: list[str] = Form(default=[]),
                      confluence_children: bool = Form(True),
                      figma_url: list[str] = Form(default=[]),
                      files: list[UploadFile] = File(None)):
    prev = store.get_feature(fid)
    if not prev:
        raise HTTPException(404, "feature not found")
    # Read uploaded docs + pasted text; collect any links embedded in PDFs.
    parts, sources, pdf_urls = [], [], []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        txt = extract_text(f.filename, data)
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
        if f.filename.lower().endswith(".pdf"):
            pdf_urls.extend(extractmod.pdf_links(data))
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    # External sources: multiple Figma + Confluence links, plus links inside PDFs.
    confluence_urls = _split_links(confluence_url)
    figma_urls = _split_links(figma_url)
    pdf_figma = [u for u in pdf_urls if "figma.com" in u.lower()]
    crawl_seeds = [u for u in pdf_urls if "figma.com" not in u.lower()]
    for u in figma_urls:
        if not figma.Figma.file_key_from_url(u):
            raise HTTPException(400, f"could not read a Figma file key from: {u[:80]}")
    if (figma_urls or pdf_figma) and not figma_client().ok():
        raise HTTPException(400, "Figma token not configured — add a Figma access token in Settings")
    if confluence_urls and not jira_client().ok():
        raise HTTPException(400, "Confluence not configured — set Jira base URL, email & API token in Settings")
    figma_data, _warnings = _gather_external(
        parts, sources, figma_urls=figma_urls, pdf_figma=pdf_figma,
        confluence_urls=confluence_urls, confluence_children=bool(confluence_children),
        crawl_seeds=crawl_seeds)
    raw = "\n\n".join(parts)
    if not raw.strip():
        raise HTTPException(400, "no document text provided")
    emb = embedder.embed(raw[:2000])
    import json as _json
    try:
        focus_d = _json.loads(focus) if focus else None
    except Exception:  # noqa: BLE001
        focus_d = None
    prev_cases = store.cases_brief(store.feature_test_case_ids(fid))
    is_replace = str(replace).lower() == "true"

    if is_replace:
        removed = store.reset_feature_content(fid)
        summary = _generate_feature_summary(prev.get("name", "Feature"), raw)
        store.update_feature_doc(fid, sources, raw, summary, emb)
        newfid = fid
        diff_summary = {"mode": "replace", "version": int(prev.get("version", 1)),
                        "kept": 0, "retired": [], "retired_orphans": removed}
    else:
        new_v = int(prev.get("version", 1)) + 1
        eff_key = (key or "").strip() or prev.get("key")
        prev_group = prev.get("group_id", fid)
        if eff_key and store.epic_bound_group(prev["project_id"], eff_key,
                                              exclude_group_id=prev_group):
            raise HTTPException(409, f"Epic '{eff_key}' is already associated with another feature")
        summary = _generate_feature_summary(name or prev["name"], raw)
        newfid = store.create_feature(name or prev["name"], prev["project_id"], sources, raw,
                                      summary, emb, key=eff_key, match_key=prev.get("match_key"),
                                      group_id=prev_group, version=new_v)
        diff = cov.diff_versions(current_llm(), prev.get("text", ""), raw, prev_cases)
        keep = set(diff.get("keep", []))
        for cid in keep:
            store.associate(newfid, cid, "carried", None)
        by_id = {c["id"]: c for c in prev_cases}
        retired = [{"id": r["id"], "title": (by_id.get(r["id"]) or {}).get("title"),
                    "reason": r.get("reason", "")} for r in diff.get("retire", [])]
        diff_summary = {"mode": "version", "version": new_v, "kept": len(keep), "retired": retired}
    store.set_version_diff(newfid, diff_summary)
    if figma_data:
        store.set_feature_figma(newfid, figma_data)

    chunks = []
    for i, ch in enumerate(chunk_doc(raw, max_chars=1200, overlap=150)):
        chunks.append({"source": sources[0] if sources else "combined", "chunk_index": i,
                       "text": ch, "embedding": embedder.embed(ch)})
    store.add_feature_chunks(newfid, prev["project_id"], chunks)
    jid = launch_job("generate", {"feature_id": newfid, "text": raw, "focus": focus_d,
                                  "total": int(total)},
                     label=f"Generate v{diff_summary['version']} — {prev.get('name')}",
                     project_id=prev["project_id"], feature_id=newfid)
    return {"feature_id": newfid, "version": diff_summary["version"], "diff": diff_summary,
            "job_id": jid}


# --------------------------------------------------------------- jobs API
@app.get("/api/jobs")
def jobs_list(request: Request, status: str | None = None, type: str | None = None, limit: int = 60):
    jobs = store.list_jobs(limit=limit, status=status, jtype=type)
    allowed = _allowed_project_ids(_current_user(request))
    if allowed is not None:
        # Keep jobs whose project is allowed; hide global (project-less) jobs from
        # scoped users.
        jobs = [j for j in jobs if j.get("project_id") in allowed]
    return {"jobs": jobs}


@app.get("/api/usage")
def usage_dashboard(project_id: str | None = None):
    """LLM/embedding token usage + cost: totals, per-model, per-project, and
    recent processes. Cost is priced live from the current Settings price table."""
    prices = store.get_settings().get("llm_prices") or {}
    return store.usage_summary(project_id=project_id, prices=prices)


class EmbeddingIn(BaseModel):
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    region: str | None = None


@app.post("/api/embedding/switch")
def switch_embedding(body: EmbeddingIn):
    """Validate a new embedding model (probe its true dimension), persist it, and
    launch the re-embed + reindex migration. Search is degraded until it completes."""
    provider = (body.provider or "ollama").strip()
    model = (body.model or "").strip()
    if not model:
        raise HTTPException(400, "an embedding model name is required")
    s = store.get_settings()
    # reuse the stored key if the caller didn't supply a new one
    key = (body.api_key or "").strip() or (
        crypto.decrypt(s.get("embed_api_key_enc", "")) if s.get("embed_api_key_enc") else "")
    region = (body.region or "").strip() if body.region is not None else s.get("embed_region", "")
    # Bedrock authenticates via region + (IAM role or access:secret in api_key),
    # so it doesn't require a standalone API key the way other hosted providers do.
    if provider not in ("ollama", "bedrock") and not key:
        raise HTTPException(400, f"{provider} needs an API key")
    trial = Embedder(provider=provider, model=model, api_key=key,
                     base_url=(body.base_url or "").strip(), ollama_url=current_ollama_url(),
                     region=region)
    # Probe: confirms connectivity/auth AND measures the true output dimension.
    try:
        dim = trial.probe_dim()
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Embedding provider", e)
    if not dim or dim < 8:
        raise HTTPException(400, "embedding provider returned an invalid vector")
    upd = {"embed_provider": provider, "embed_model": model,
           "embed_base_url": (body.base_url or "").strip(),
           "embed_region": region, "embed_dim": int(dim)}
    if body.api_key is not None:
        upd["embed_api_key_enc"] = crypto.encrypt(body.api_key) if body.api_key else ""
    store.save_settings(upd)
    jid = launch_job("reembed", {"dim": int(dim)},
                     label=f"Re-embed all vectors → {provider}/{model} ({dim}-d)")
    return {"job_id": jid, "provider": provider, "model": model, "dim": int(dim)}


@app.get("/api/jobs/{jid}")
def job_get(jid: str, request: Request):
    j = _require_job_project(request, jid)
    j.pop("params", None)   # may contain large text
    return j


@app.get("/api/jobs/{jid}/stream")
def job_stream(jid: str, request: Request):
    _require_job_project(request, jid)
    from fastapi.responses import StreamingResponse
    import asyncio

    async def events():
        last_signature = None
        while True:
            job = store.get_job(jid)
            if not job:
                yield f"event: error\ndata: {json.dumps({'status': 'not_found', 'job_id': jid})}\n\n"
                break
            payload = {
                "id": job["id"],
                "type": job.get("type"),
                "status": job.get("status"),
                "stage": job.get("stage"),
                "progress": job.get("progress", 0),
                "logs": job.get("logs", []),
                "result": job.get("result", {}),
                "error": job.get("error"),
            }
            signature = json.dumps(payload, sort_keys=True, default=str)
            if signature != last_signature:
                yield f"event: update\ndata: {json.dumps(payload, default=str)}\n\n"
                last_signature = signature
            else:
                yield ": keep-alive\n\n"
            if job.get("status") in {"succeeded", "failed"}:
                yield f"event: done\ndata: {json.dumps(payload, default=str)}\n\n"
                break
            await asyncio.sleep(0.75)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{jid}/retry")
def job_retry(jid: str, request: Request):
    j = _require_job_project(request, jid)
    if j["type"] not in JOB_WORKERS:
        raise HTTPException(400, f"job type '{j['type']}' cannot be retried")
    nid = launch_job(j["type"], j.get("params", {}), label=j.get("label", "") + " (retry)",
                     project_id=j.get("project_id"), feature_id=j.get("feature_id"))
    return {"job_id": nid}


@app.get("/api/features")
def list_features(request: Request, project_id: str | None = None):
    user = _current_user(request)
    if project_id is not None:
        _require_project(request, project_id)
        return {"features": store.list_features(project_id)}
    feats = store.list_features(None)
    allowed = _allowed_project_ids(user)
    if allowed is not None:
        feats = [f for f in feats if f.get("project_id") in allowed]
    return {"features": feats}


@app.get("/api/features/{fid}")
def get_feature(fid: str, request: Request):
    _require_feature_project(request, fid)
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    f["summary"] = _display_feature_summary(f)
    f["test_cases"] = store.get_feature_cases(fid)
    return f


@app.get("/api/steps")
def list_steps(limit: int = 200, skip: int = 0):
    return {"steps": store.list_steps(limit, skip)}


class StepEdit(BaseModel):
    action: str
    expected: str


@app.patch("/api/steps/{sid}")
def edit_step(sid: str, body: StepEdit):
    emb = embedder.embed(f"{body.action}. Expected: {body.expected}")
    return store.update_step(sid, body.action, body.expected, emb)


# --------------------------------------------------------------- test-case mgmt
@app.get("/api/dashboard")
def dashboard():
    try:
        return store.dashboard()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))


@app.get("/api/tags")
def tags():
    return {"tags": store.all_tags()}


@app.get("/api/test-cases")
def list_test_cases(request: Request, project_id: str | None = None,
                    feature_id: str | None = None,
                    type: str | None = None, tag: str | None = None,
                    q: str | None = None, status: str = "active",
                    execution_status: str | None = None,
                    lineage: str | None = None, step_id: str | None = None,
                    limit: int = 50, skip: int = 0):
    if execution_status and execution_status not in {"untested", "passed", "failed", "blocked"}:
        raise HTTPException(422, "invalid execution status")
    if lineage and lineage not in {"created", "inherited"}:
        raise HTTPException(422, "invalid lineage filter")
    user = _current_user(request)
    if project_id is not None:
        _require_project(request, project_id)
    res = store.list_test_cases(
        project_id, feature_id, type, tag, q, status, execution_status, lineage,
        step_id, limit, skip
    )
    # Restrict to cases in the user's allowed projects (case may span projects; keep
    # it if it touches any allowed one).
    allowed = _allowed_project_ids(user)
    if allowed is not None and isinstance(res, dict) and isinstance(res.get("cases"), list):
        res["cases"] = [c for c in res["cases"]
                        if any((f.get("project_id") in allowed)
                               for f in (c.get("features") or []))]
    return res


@app.get("/api/test-cases/{cid}")
def get_case(cid: str, request: Request):
    return _require_case_project(request, cid)


# ---- MCQ Validator API ------------------------------------------------------
@app.post("/api/features/{fid}/validator")
def start_validator(fid: str, body: dict = None):
    force_new = False
    if body and isinstance(body, dict):
        force_new = body.get("forceNew") or body.get("force_new") or False
    try:
        existing = validator.get_existing_validator(store, fid, force_new=force_new)
        if existing:
            return existing
        feature = store.get_feature(fid)
        if not feature:
            raise HTTPException(404, "Feature not found")
        previous_runs = store.list_validator_runs(fid)
        run_id = store.create_validator_run(
            fid,
            is_retake=bool(previous_runs),
            version_number=int(feature.get("version", 1)),
        )
        jid = launch_job(
            "validator",
            {"feature_id": fid, "run_id": run_id},
            label=f"Generate validator — {feature.get('name')}",
            project_id=feature.get("project_id"),
            feature_id=fid,
        )
        store.validator_runs.update_one(
            {"_id": _oid(run_id)},
            {"$set": {"job_id": jid, "updated_at": time.time()}},
        )
        return {
            "run": store.get_validator_run(run_id),
            "versionNumber": int(feature.get("version", 1)),
            "questions": [],
            "answers": [],
            "mode": "generating",
            "job_id": jid,
        }
    except Exception as e:
        raise _svc_error("Validator", e)


@app.get("/api/features/{fid}/validator/latest")
def get_validator_latest(fid: str):
    """Return the existing validator state (if any) WITHOUT launching generation."""
    try:
        existing = validator.get_existing_validator(store, fid)
        return existing or {"mode": "none"}
    except Exception as e:
        raise _svc_error("Validator", e)


@app.post("/api/validator/runs/{run_id}/submit")
def submit_validator_answers(run_id: str, body: dict, request: Request):
    _require_validator_run_project(request, run_id)
    answers = body.get("answers") or []
    user = _current_user(request)
    user_email = user.get("email") if user else "anonymous"
    try:
        score = validator.submit_validator(
            store=store,
            run_id=run_id,
            answers=answers,
            answered_by=user_email
        )
        return score
    except Exception as e:
        raise _svc_error("Answer submission", e)


@app.get("/api/features/{fid}/validator/history")
def get_validator_history(fid: str):
    try:
        return {"history": store.list_validator_runs(fid)}
    except Exception as e:
        raise _svc_error("Validator history", e)


@app.get("/api/validator/runs/{run_id}/export")
def export_validator_run(run_id: str, request: Request):
    run = _require_validator_run_project(request, run_id)
    questions = store.get_validator_questions(run_id)
    answers = store.get_validator_answers(run_id)
    scoring = validator.compute_validator_score(questions, answers)
    validated_output = validator.build_validated_output(questions, answers)
    ans_map = {str(a["question_id"]): a for a in answers}
    question_results = [validator.build_question_result(q, ans_map.get(str(q["id"]))) for q in questions]
    return {
        "run": run,
        "summary": scoring,
        "questions": question_results,
        "validatedOutput": validated_output
    }


# ---- Test Plan API ----------------------------------------------------------
@app.post("/api/features/{fid}/test-plan")
def start_test_plan(fid: str, body: dict = None, request: Request = None):
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "Feature not found")
    version_number = int(feature.get("version", 1))
    user = _current_user(request) if request else None
    user_email = user.get("email") if user else "anonymous"
    
    run_id, run_number = store.create_test_plan_run(
        feature_id=fid,
        version_number=version_number,
        created_by=user_email
    )
    
    def run_gen():
        test_plan.generate_test_plan_job(store, current_llm(), run_id, fid)
        
    threading.Thread(target=run_gen, daemon=True).start()
    return {"runId": run_id, "runNumber": run_number, "status": "PROCESSING"}


@app.get("/api/features/{fid}/test-plan/latest")
def get_latest_test_plan(fid: str):
    run = store.get_latest_test_plan_run(fid)
    if not run:
        return {"run": None}
    return {"run": run}


@app.get("/api/test-plan/runs/{run_id}/stream")
def test_plan_stream(run_id: str, request: Request):
    _require_test_plan_run_project(request, run_id)
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def event_generator():
        yield "event: connected\ndata: {\"ok\": true, \"runId\": \"" + run_id + "\"}\n\n"
        while True:
            run = store.get_test_plan_run(run_id)
            if not run:
                yield "event: error\ndata: {\"ok\": false, \"message\": \"Run not found\"}\n\n"
                break
            payload = {
                "ok": True,
                "runId": run["id"],
                "status": run.get("status", "PROCESSING"),
                "testPlan": run.get("content") or {}
            }
            yield f"event: status\ndata: {json.dumps(payload)}\n\n"
            if run.get("status") in ["COMPLETED", "FAILED"]:
                yield f"event: done\ndata: {json.dumps({'ok': True, 'runId': run_id, 'status': run['status']})}\n\n"
                break
            await asyncio.sleep(1.5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/test-plan/runs/{run_id}/export/csv")
def export_test_plan_csv(run_id: str, request: Request):
    run = _require_test_plan_run_project(request, run_id)
    if not run or not run.get("content"):
        raise HTTPException(404, "Test plan content not found")
    csv_str = test_plan.build_test_plan_csv(run["content"])
    from fastapi.responses import Response
    return Response(content=csv_str, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=test_plan_{run_id}.csv"
    })


@app.get("/api/test-plan/runs/{run_id}/export/pdf")
def export_test_plan_pdf(run_id: str, request: Request):
    run = _require_test_plan_run_project(request, run_id)
    if not run or not run.get("content"):
        raise HTTPException(404, "Test plan content not found")
    pdf_bytes = test_plan.build_test_plan_pdf(run["content"])
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=test_plan_{run_id}.pdf"
    })


class CaseEdit(BaseModel):
    title: str
    type: str
    priority: str = "P2"
    preconditions: str = ""
    tags: list[str] = []
    steps: list[dict] = []   # [{id?, action, expected}] — order is preserved


class CaseExecutionUpdate(BaseModel):
    status: str
    note: str = ""


@app.put("/api/test-cases/{cid}")
def update_case(cid: str, body: CaseEdit, request: Request):
    _require_case_project(request, cid)
    """Full edit: metadata + steps (add/remove/reorder). Editing an existing
    step updates the shared step → propagates to every case that references it."""
    step_ids, propagated = [], 0
    for s in body.steps:
        action = (s.get("action") or "").strip()
        expected = (s.get("expected") or "").strip()
        if not (action or expected):
            continue
        emb = embedder.embed(f"{action}. Expected: {expected}")
        sid = s.get("id")
        if sid:
            r = store.update_step(sid, action, expected, emb)  # propagates
            propagated += max(0, r["affected_cases"] - 1)
            step_ids.append(sid)
        else:
            r = store.get_or_create_step(action, expected, emb, STEP_AUTO)
            step_ids.append(r["step_id"])
    cemb = embedder.embed(body.title + " " + " ".join(
        f"{s.get('action','')} {s.get('expected','')}" for s in body.steps))
    store.update_case(cid, body.title, body.type, body.priority,
                      body.preconditions, body.tags, step_ids, cemb)
    return {"updated": cid, "steps": len(step_ids),
            "other_cases_affected_by_step_edits": propagated}


@app.patch("/api/test-cases/{cid}/execution")
def update_case_execution(cid: str, body: CaseExecutionUpdate, request: Request):
    _require_case_project(request, cid)
    if body.status not in {"untested", "passed", "failed", "blocked"}:
        raise HTTPException(422, "status must be untested, passed, failed, or blocked")
    if not store.update_case_execution(cid, body.status, body.note.strip()):
        raise HTTPException(404, "test case not found")
    return {"updated": cid, "execution_status": body.status}


class RetrieveIn(BaseModel):
    text: str
    type: str | None = None
    limit: int = 8


@app.post("/api/retrieve")
def retrieve(req: RetrieveIn):
    """RAG: find existing test cases relevant to a new requirement (for reuse)."""
    emb = embedder.embed(req.text, task="query")
    results, pipeline = store.search_cases(emb, limit=req.limit, ctype=req.type)
    return {"query": req.text, "results": results, "pipeline": _trunc(pipeline)}


class AssociateIn(BaseModel):
    case_id: str


@app.post("/api/features/{fid}/associate")
def associate(fid: str, body: AssociateIn):
    store.associate(fid, body.case_id, "manual", None)
    return {"associated": body.case_id}


# --------------------------------------------------------------- Phase 2: GitHub
SYNC = {"running": False, "last": None, "ingested": 0, "mapped": 0, "errors": []}


class ProjectIn(BaseModel):
    name: str
    description: str | None = ""
    key: str | None = None
    jira_project_key: str | None = None
    jira_project_name: str | None = None
    confluence_space_key: str | None = None
    confluence_space_name: str | None = None
    default_git_provider: str | None = "github"  # 'github' | 'gitlab'


@app.post("/api/projects")
def create_project(body: ProjectIn):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    provider = (body.default_git_provider or "github").lower()
    if provider not in ("github", "gitlab"):
        provider = "github"
    jkey = (body.jira_project_key or "").strip()
    if jkey and store.jira_project_in_use(jkey):
        raise HTTPException(409, f"Jira project '{jkey}' is already linked to another project")
    pid = store.create_project(
        name, key=body.key, description=(body.description or "").strip(),
        jira_project_key=body.jira_project_key, jira_project_name=body.jira_project_name,
        confluence_space_key=body.confluence_space_key,
        confluence_space_name=body.confluence_space_name,
        default_git_provider=provider)
    return {"id": pid, "name": name, "description": body.description or "",
            "default_git_provider": provider,
            "jira_project_key": body.jira_project_key,
            "confluence_space_key": body.confluence_space_key}


@app.get("/api/projects")
def list_projects(request: Request):
    # Only projects the current user may access (admins / all_projects see everything).
    return {"projects": _filter_projects_for(_current_user(request), store.list_projects())}


@app.get("/api/projects/{pid}")
def get_project_one(pid: str, request: Request):
    _require_project(request, pid)
    raw = store.get_project(pid)
    if not raw:
        raise HTTPException(404, "project not found")
    # Mask encrypted PAT blobs; surface only "configured" booleans.
    p = _project_public(raw)

    # Backfill provider for projects created before default_git_provider existed.
    # Order of inference: (1) saved field, (2) most common repo provider,
    # (3) whichever PAT is configured, (4) default github.
    if not p.get("default_git_provider"):
        repos = store.list_repos(pid)
        counts = {"github": 0, "gitlab": 0}
        for r in repos:
            gp = (r.get("git_provider") or "github").lower()
            if gp in counts:
                counts[gp] += 1
        if counts["gitlab"] > counts["github"]:
            inferred = "gitlab"
        elif counts["github"] > 0:
            inferred = "github"
        elif p["gitlab_pat_set"] and not p["github_pat_set"]:
            inferred = "gitlab"
        else:
            inferred = "github"
        p["default_git_provider"] = inferred
        # Persist so subsequent reads don't have to re-infer.
        store.update_project(pid, {"default_git_provider": inferred})
    return p


# ---- per-project GitHub PAT ------------------------------------------------
class PatIn(BaseModel):
    pat: str


@app.get("/api/projects/{pid}/github/pat")
def get_project_github_pat_status(pid: str):
    return {"configured": bool(store.get_project_github_pat_enc(pid))}


@app.put("/api/projects/{pid}/github/pat")
def save_project_github_pat(pid: str, body: PatIn):
    if not body.pat or not body.pat.strip():
        raise HTTPException(400, "pat required")
    store.set_project_github_pat_enc(pid, crypto.encrypt(body.pat.strip()))
    return {"ok": True}


@app.delete("/api/projects/{pid}/github/pat")
def clear_project_github_pat(pid: str):
    store.set_project_github_pat_enc(pid, "")
    return {"ok": True}


@app.get("/api/projects/{pid}/github/accessible-repos")
def list_accessible_github_repos(pid: str, request: Request, page: int = 1):
    # Allow a one-shot PAT override (sent via X-Provider-PAT header) so the
    # CreateProject UI can list repos before the PAT has been persisted. This
    # mirrors the Node controller's security note: PAT must NOT be in the URL.
    header_pat = request.headers.get("X-Provider-PAT", "").strip()
    token = header_pat or project_github_token(pid)
    if not token:
        raise HTTPException(400, "GitHub PAT not configured for this project")
    try:
        return {"repos": github.GitHub(token, GITHUB_API).list_accessible_repos_page(page)}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("GitHub", e)


# ---- per-project GitLab PAT ------------------------------------------------
@app.get("/api/projects/{pid}/gitlab/pat")
def get_project_gitlab_pat_status(pid: str):
    return {"configured": bool(store.get_project_gitlab_pat_enc(pid))}


@app.put("/api/projects/{pid}/gitlab/pat")
def save_project_gitlab_pat(pid: str, body: PatIn):
    if not body.pat or not body.pat.strip():
        raise HTTPException(400, "pat required")
    store.set_project_gitlab_pat_enc(pid, crypto.encrypt(body.pat.strip()))
    return {"ok": True}


@app.delete("/api/projects/{pid}/gitlab/pat")
def clear_project_gitlab_pat(pid: str):
    store.set_project_gitlab_pat_enc(pid, "")
    return {"ok": True}


@app.get("/api/projects/{pid}/gitlab/accessible-repos")
def list_accessible_gitlab_repos(pid: str, request: Request, page: int = 1):
    header_pat = request.headers.get("X-Provider-PAT", "").strip()
    token = header_pat or project_gitlab_token(pid)
    if not token:
        raise HTTPException(400, "GitLab PAT not configured for this project")
    try:
        return {"repos": gitlab_mod.GitLab(token).list_accessible_projects_page(page)}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("GitLab", e)


# ---- preview repo list (used by Create Project before any project exists) --
@app.get("/api/git/accessible-repos")
def list_git_accessible_repos(request: Request, provider: str = "github", page: int = 1):
    """Paginated repo listing using a PAT supplied via X-Provider-PAT header.
    Used by the Create Project wizard before the project (and its persisted
    PAT) exist. The PAT is never logged and never read from the URL."""
    pat = request.headers.get("X-Provider-PAT", "").strip()
    if not pat:
        raise HTTPException(400, "X-Provider-PAT header required")
    if len(pat) > 512:
        raise HTTPException(400, "PAT too long")
    p = (provider or "github").lower()
    try:
        if p == "gitlab":
            return {"repos": gitlab_mod.GitLab(pat).list_accessible_projects_page(page)}
        return {"repos": github.GitHub(pat, GITHUB_API).list_accessible_repos_page(page)}
    except Exception as e:  # noqa: BLE001
        raise _ext_error(p, e)


# ---- atlassian helpers (settings-level creds) ------------------------------
@app.get("/api/atlassian/accessible-jira-projects")
def list_accessible_jira_projects():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured in Settings")
    try:
        projects = j.list_projects()
        for p in projects:
            p["in_use"] = bool(store.jira_project_in_use(p.get("key")))
        return {"projects": projects}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


@app.get("/api/atlassian/accessible-confluence-spaces")
def list_accessible_confluence_spaces():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira/Confluence not configured in Settings")
    try:
        return {"spaces": j.list_confluence_spaces()}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Confluence", e)


@app.get("/api/projects/{pid}/jira-issues")
def list_project_jira_issues(pid: str, exclude_feature_id: str | None = None):
    """Epics available to associate with a feature: every Epic in the linked Jira
    project MINUS any Epic already bound to a feature (1 Epic : 1 feature).
    `exclude_feature_id` keeps the epic already bound to that feature visible
    (so its own selection shows when editing / re-versioning)."""
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    project_key = (p.get("jira_project_key") or "").strip()
    if not project_key:
        return {"project_key": "", "issues": []}
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured in Settings")
    exclude_group = None
    if exclude_feature_id:
        f = store.get_feature(exclude_feature_id)
        if f:
            exclude_group = f.get("group_id", f.get("id"))
    try:
        epics = j.list_project_epics(project_key)
        bound = store.bound_epic_keys(pid, exclude_group_id=exclude_group)
        available = [e for e in epics if e.get("key") not in bound]
        return {"project_key": project_key, "issues": available}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


# ---- project repos (with webhook registration) -----------------------------
class RepoIn(BaseModel):
    # Either provide an `url` (parsed) or `repo_full_name` (already-validated).
    url: str | None = None
    repo_full_name: str | None = None
    label: str | None = None
    kind: str = "BE"                  # BE | FE | infra | other (legacy)
    repo_type: str = "app"            # app | test
    git_provider: str = "github"      # github | gitlab
    default_branch: str = "main"


@app.post("/api/projects/{pid}/repos")
def add_repo(pid: str, body: RepoIn, request: Request):
    provider = (body.git_provider or "github").lower()
    repo_type = "test" if (body.repo_type or "").lower() == "test" else "app"

    # Resolve owner/name
    if provider == "gitlab":
        path = body.repo_full_name or body.url or ""
        try:
            full = gitlab_mod.parse_repo_url(path) if "://" in path or path.endswith(".git") else path
        except ValueError as e:
            raise HTTPException(400, str(e))
        if "/" not in full:
            raise HTTPException(400, "GitLab project path must include namespace/name")
        owner, name = full.rsplit("/", 1)
    else:
        src = body.repo_full_name or body.url or ""
        try:
            owner, name = github.parse_repo_url(src)
        except ValueError as e:
            raise HTTPException(400, str(e))

    full_name = f"{owner}/{name}"
    label = (body.label or full_name).strip()

    webhook_id = None
    webhook_secret_enc = ""

    if repo_type == "app":
        webhook_base = _webhook_base_url(request)
        webhook_url = (f"{webhook_base}/api/webhook/{provider}" if webhook_base
                       else f"/api/webhook/{provider}")
        import secrets as _secrets
        secret = _secrets.token_hex(32)
        try:
            if provider == "github":
                token = project_github_token(pid)
                if not token:
                    raise HTTPException(400, "GitHub PAT not configured for this project")
                client = github.GitHub(token, GITHUB_API)
                # Reuse existing webhook for the same target_url if one exists.
                existing = None
                try:
                    for hook in client.list_webhooks(owner, name) or []:
                        if (hook.get("config") or {}).get("url") == webhook_url:
                            existing = hook
                            break
                except Exception as e:  # noqa: BLE001
                    print(f"[webhook] list failed (continuing): {e}", flush=True)
                if existing:
                    webhook_id = existing.get("id")
                    try:
                        client.update_pr_webhook(owner, name, webhook_id, webhook_url, secret)
                    except Exception as e:  # noqa: BLE001
                        print(f"[webhook] patch failed: {e}", flush=True)
                else:
                    hook = client.register_pr_webhook(owner, name, webhook_url, secret)
                    webhook_id = hook.get("id")
                webhook_secret_enc = crypto.encrypt(secret)
            else:  # gitlab
                token = project_gitlab_token(pid)
                if not token:
                    raise HTTPException(400, "GitLab PAT not configured for this project")
                client = gitlab_mod.GitLab(token)
                hook = client.register_mr_webhook(full_name, webhook_url, secret)
                webhook_id = hook.get("id")
                webhook_secret_enc = crypto.encrypt(secret)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            # Don't fail the whole connect; persist the repo without webhook so the
            # user can retry later from the UI.
            print(f"[webhook] register failed: {e}", flush=True)

    rid = store.add_repo(pid, owner, name,
                         (body.url or f"https://{provider}.com/{full_name}"),
                         body.kind, body.default_branch,
                         repo_type=repo_type, git_provider=provider,
                         label=label,
                         webhook_id=webhook_id, webhook_secret_enc=webhook_secret_enc)
    if repo_type == "app":
        threading.Thread(target=sync_repo, args=(rid,), daemon=True).start()
    return {"repo_id": rid, "full_name": full_name, "watching": True,
            "webhook_configured": bool(webhook_secret_enc)}


@app.get("/api/projects/{pid}/repos")
def list_repos(pid: str, repo_type: str | None = None):
    if repo_type in {"app", "test"}:
        return {"repos": store.repos_for_project(pid, repo_type=repo_type)}
    return {"repos": store.list_repos(pid)}


@app.get("/api/repos/{rid}/branches")
def repo_branches(rid: str):
    repo = store.repos.find_one({"_id": _oid(rid)})
    if not repo:
        raise HTTPException(404, "repo not found")
    try:
        repo_doc = {**repo, "id": str(repo["_id"])}
        names = _repo_list_branches(repo_doc)
    except Exception as e:  # noqa: BLE001
        provider = (repo.get("git_provider") or "github").lower()
        raise _ext_error(provider, e)
    return {"branches": names, "default": repo.get("default_branch", "")}


@app.post("/api/repos/{rid}/watch")
def set_watch(rid: str, body: dict):
    store.set_repo_watch(rid, bool((body or {}).get("watch", True)))
    return {"ok": True}


@app.post("/api/repos/{rid}/sync")
def sync_now(rid: str):
    threading.Thread(target=sync_repo, args=(rid,), daemon=True).start()
    return {"started": True}


@app.get("/api/projects/{pid}/prs")
def project_prs(pid: str):
    return {"prs": store.list_prs(project_id=pid)}


class ReadyThresholdIn(BaseModel):
    threshold: int = 80


@app.post("/api/features/{fid}/ready-threshold")
def set_ready_threshold(fid: str, body: ReadyThresholdIn):
    """Set the feature's QA-readiness threshold (percent code coverage; editor+)."""
    if not store.get_feature(fid):
        raise HTTPException(404, "feature not found")
    return {"ready_threshold": store.set_feature_ready_threshold(fid, body.threshold)}


@app.get("/api/features/{fid}/coverage")
def feature_coverage(fid: str):
    rep = store.feature_coverage_report(fid)
    f = store.get_feature(fid)
    snap = store.get_automation_coverage(fid, version=(f or {}).get("version", 1)) or {}
    total = rep.get("total_test_cases", 0) or 0
    covered = rep.get("covered", 0) or 0
    code_pct = rep.get("coverage_pct", 0)
    # Holistic view: a case is covered once ANY linked PR implements it (union).
    # QA-readiness is a per-feature strategy (PM/Lead defined, stored on the
    # feature): "ready for manual testing" once CODE coverage meets the threshold.
    _thr = (f or {}).get("ready_threshold")
    threshold = int(_thr) if _thr is not None else 80
    rep["summary"] = {
        "total_cases": total,
        "code_pct": code_pct,
        "covered_cases": covered,
        "automation_pct": snap.get("coverage_pct", 0),
        "automated_cases": snap.get("covered_count", 0),
        "ready_threshold": threshold,
        "ready": bool(total and code_pct >= threshold),
    }
    return rep


def _decorate_coverage_run(r: dict) -> dict:
    """Add needs_rerun + commit_url, hydrate covered case titles + comparison."""
    if not r:
        return r
    fid = r.get("feature_id")
    if fid:
        feature = store.get_feature(fid)
        if feature:
            run_done = r.get("completed_at") or r.get("created_at") or 0
            r["needs_rerun"] = bool(feature.get("updated_at") and
                                    feature["updated_at"] > run_done)
            r["feature_name"] = feature.get("name", "")
    r["commit_url"] = auto_cov.build_commit_url(
        r.get("git_provider", "github"),
        r.get("repo_full_name", ""),
        r.get("head_sha", "")) if r.get("head_sha") else ""
    return r


def _hydrate_case_titles(ids: list) -> dict:
    """Bulk-resolve {case_id: {title,type,display_id}} for a list of ids."""
    from bson import ObjectId as _OID
    valid = [_OID(i) for i in ids if i and _OID.is_valid(i)]
    out = {}
    if not valid:
        return out
    for case in store.cases.find({"_id": {"$in": valid}},
                                 {"title": 1, "type": 1, "display_id": 1,
                                  "priority": 1, "step_ids": 1}):
        out[str(case["_id"])] = {"title": case.get("title", ""),
                                  "type": case.get("type", ""),
                                  "display_id": case.get("display_id", ""),
                                  "priority": case.get("priority", "P2"),
                                  "steps": store.resolve_steps(case.get("step_ids", []))}
    return out


# --- Gap Analysis: PR Code Coverage ------------------------------------------
@app.get("/api/features/{fid}/code-coverage/runs")
def list_feature_code_coverage_runs(fid: str, limit: int = 50):
    runs = store.list_code_coverage_runs(feature_id=fid, limit=limit)
    feature = store.get_feature(fid)
    feat_updated = (feature or {}).get("updated_at", 0)
    excluded_keys = store.excluded_pr_run_keys(fid)
    for r in runs:
        run_done = r.get("completed_at") or r.get("created_at") or 0
        r["needs_rerun"] = bool(feat_updated and feat_updated > run_done)
        r["excluded"] = (r.get("repo_id"), str(r.get("pr_number"))) in excluded_keys
    return {"runs": runs}


@app.get("/api/code-coverage/runs/{rid}")
def get_code_coverage_run_detail(rid: str, request: Request):
    r = _require_code_coverage_run_project(request, rid)
    result = r.get("result") or {}
    covered = result.get("covered") or []

    # Hydrate covered cases titles
    if covered:
        all_ids = [c.get("test_case_id") for c in covered if c.get("test_case_id")]
        titles = _hydrate_case_titles(all_ids)
        result["covered"] = [{**c, **titles.get(c.get("test_case_id"), {})}
                              for c in covered]

    # Hydrate comparison id → title pairs so the UI can render with context.
    comparison = result.get("comparison") or {}
    if comparison:
        diff_ids = list(comparison.get("newly_covered") or []) + \
                   list(comparison.get("no_longer_covered") or [])
        diff_titles = _hydrate_case_titles(diff_ids)
        comparison["newly_covered_detail"] = [
            {"id": i, **diff_titles.get(i, {})}
            for i in (comparison.get("newly_covered") or [])]
        comparison["no_longer_covered_detail"] = [
            {"id": i, **diff_titles.get(i, {})}
            for i in (comparison.get("no_longer_covered") or [])]
        result["comparison"] = comparison

    # Include the full case list for the feature so the UI can render BOTH
    # covered (Done) and missing (Missing) per type — matching Node's view.
    feature_cases = []
    fid = r.get("feature_id")
    if fid:
        try:
            case_ids = store.feature_test_case_ids(fid)
            from bson import ObjectId as _OID
            valid = [_OID(i) for i in case_ids if i and _OID.is_valid(i)]
            for c in store.cases.find({"_id": {"$in": valid}},
                                       {"title": 1, "type": 1, "display_id": 1,
                                        "priority": 1, "step_ids": 1}):
                feature_cases.append({
                    "id": str(c["_id"]),
                    "title": c.get("title", ""),
                    "type": c.get("type", "other"),
                    "display_id": c.get("display_id", ""),
                    "priority": c.get("priority", "P2"),
                    "steps": store.resolve_steps(c.get("step_ids", [])),
                })
        except Exception:  # noqa: BLE001
            pass
    r["feature_cases"] = feature_cases

    r["result"] = result
    return _decorate_coverage_run(r)


class ReassignIn(BaseModel):
    feature_id: str


@app.post("/api/code-coverage/runs/{rid}/reassign")
def reassign_code_coverage_run(rid: str, body: ReassignIn):
    """Manually override the auto-resolved feature for a PR run, and re-run
    coverage against the chosen feature's current version (sticky binding)."""
    run = store.get_code_coverage_run(rid)
    if not run:
        raise HTTPException(404, "run not found")
    feature = store.get_feature(body.feature_id)
    if not feature:
        raise HTTPException(404, "feature not found")
    store.update_code_coverage_run(rid, feature_id=body.feature_id,
                                   feature_version=feature.get("version", 1),
                                   confidence="manual")
    if not run.get("repo_id") or not run.get("pr_number"):
        raise HTTPException(400, "run is missing repo_id / pr_number — cannot re-run")
    jid = launch_job("code_coverage", {
        "repo_id": run["repo_id"], "pr_number": int(run["pr_number"]),
        "feature_id": body.feature_id},
        label=f"Coverage · reassign to {feature.get('name')}",
        project_id=run.get("project_id"), feature_id=body.feature_id)
    return {"ok": True, "job_id": jid}


class ExcludePrIn(BaseModel):
    excluded: bool = True


@app.post("/api/prs/{pr_id}/exclude")
def exclude_pr(pr_id: str, body: ExcludePrIn):
    """Exclude (or re-include) a PR from a feature's Gap Analysis coverage.

    Excluded PRs stay visible in the Gap Analysis list (flagged) but no longer
    contribute to the feature's aggregate code coverage — lets a QA lead drop
    an outdated/junk PR and have coverage recompute immediately."""
    res = store.set_pr_excluded(pr_id, body.excluded)
    if res is None:
        raise HTTPException(404, "PR not found")
    return res


_GH_PR_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", re.IGNORECASE)
_GL_MR_RE = re.compile(r"gitlab\.com/(.+?)/-/merge_requests/(\d+)", re.IGNORECASE)


def parse_pr_url(url: str) -> dict | None:
    """Returns {repo_full_name, number, provider} or None if not a PR/MR URL."""
    if not url:
        return None
    url = url.strip()
    m = _GH_PR_RE.search(url)
    if m:
        return {"provider": "github", "repo_full_name": m.group(1),
                "number": int(m.group(2))}
    m = _GL_MR_RE.search(url)
    if m:
        return {"provider": "gitlab", "repo_full_name": m.group(1),
                "number": int(m.group(2))}
    return None


class ManualCovIn(BaseModel):
    feature_id: str
    # Accept either an explicit repo_id+pr_number OR a PR/MR URL.
    repo_id: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None


@app.post("/api/code-coverage/runs/manual")
def manual_code_coverage(body: ManualCovIn):
    """Manually run PR code coverage. Accepts either:
       - {feature_id, repo_id, pr_number}, OR
       - {feature_id, pr_url}  with a github.com/.../pull/N or
                                gitlab.com/.../-/merge_requests/N URL.
    The URL form looks up the connected repo on this project by full_name."""
    feature = store.get_feature(body.feature_id)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature.get("project_id")

    repo_id = body.repo_id
    pr_number = body.pr_number

    if body.pr_url:
        parsed = parse_pr_url(body.pr_url)
        if not parsed:
            raise HTTPException(400, "URL must be a GitHub PR or GitLab MR link")
        pr_number = parsed["number"]
        # Find a connected repo on this project that matches the URL.
        candidates = [r for r in store.list_repos(pid)
                      if r.get("full_name") == parsed["repo_full_name"]
                      and r.get("git_provider") == parsed["provider"]]
        if not candidates:
            raise HTTPException(
                400,
                f"repository '{parsed['repo_full_name']}' "
                f"is not connected to this project — connect it first")
        repo_id = candidates[0]["id"]

    if not repo_id or not pr_number:
        raise HTTPException(400, "provide pr_url or (repo_id + pr_number)")

    repo = store.get_repo(repo_id)
    if not repo:
        raise HTTPException(404, "repo not found")
    jid = launch_job("code_coverage", {
        "repo_id": repo_id, "pr_number": pr_number,
        "feature_id": body.feature_id},
        label=f"Coverage · {repo.get('full_name')} #{pr_number}",
        project_id=repo.get("project_id"), feature_id=body.feature_id)
    return {"job_id": jid, "repo_full_name": repo.get("full_name"),
            "pr_number": pr_number}


# --- Gap Analysis: Automation Coverage ---------------------------------------
@app.get("/api/features/{fid}/automation-coverage")
def get_feature_automation_coverage(fid: str):
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    snapshot = store.get_automation_coverage(fid, version=feature.get("version", 1))
    if not snapshot:
        # Surface the current state even when no scan has run yet, so the UI
        # can render "no test repo connected / rescan to begin" guidance.
        test_repos = store.repos_for_project(feature["project_id"], repo_type="test")
        return {
            "feature_id": fid,
            "total_generated": len(store.feature_test_case_ids(fid)),
            "covered_count": 0,
            "missing_count": len(store.feature_test_case_ids(fid)),
            "coverage_pct": 0.0,
            "items": [],
            "scan_status": "never",
            "test_repos": [{
                "id": r["id"], "full_name": r["full_name"],
                "scan_status": r.get("scan_status", "never"),
                "scan_files_found": r.get("scan_files_found", 0),
                "scan_cases_count": r.get("scan_cases_count", 0),
                "scan_error": r.get("scan_error", ""),
                "last_scan_at": r.get("last_scan_at"),
            } for r in test_repos],
        }
    snapshot["id"] = str(snapshot.pop("_id"))
    test_repos = store.repos_for_project(feature["project_id"], repo_type="test")
    snapshot["test_repos"] = [{
        "id": r["id"], "full_name": r["full_name"],
        "scan_status": r.get("scan_status", "never"),
        "scan_files_found": r.get("scan_files_found", 0),
        "scan_cases_count": r.get("scan_cases_count", 0),
        "scan_error": r.get("scan_error", ""),
        "last_scan_at": r.get("last_scan_at"),
    } for r in test_repos]
    return snapshot


@app.post("/api/projects/{pid}/repos/{rid}/rescan")
def rescan_test_repo(pid: str, rid: str, feature_id: str | None = None):
    repo = store.get_repo(rid)
    if not repo or repo.get("project_id") != pid:
        raise HTTPException(404, "repo not found in this project")
    if repo.get("repo_type") != "test":
        raise HTTPException(400, "rescan only applies to test repos")
    # If a scan is already running we surface that instead of stacking jobs.
    if repo.get("scan_status") == "running":
        return {"already_running": True, "repo_id": rid}
    params = {"repo_id": rid}
    if feature_id:
        params["feature_id"] = feature_id
    jid = launch_job("test_repo_scan", params,
                     label=f"Rescan · {repo.get('full_name')}",
                     project_id=pid, feature_id=feature_id)
    return {"job_id": jid, "status": "running"}


@app.post("/api/projects/{pid}/repos/{rid}/scan/reset")
def reset_stuck_scan(pid: str, rid: str):
    """Force-clear a stuck `running` scan_status so the user can retry."""
    repo = store.get_repo(rid)
    if not repo or repo.get("project_id") != pid:
        raise HTTPException(404, "repo not found in this project")
    if repo.get("scan_status") != "running":
        return {"ok": True, "was_running": False}
    store.set_repo_scan_status(rid, "failed",
                               scan_error="manually reset — previous scan was stuck")
    return {"ok": True, "was_running": True}


@app.get("/api/github/ratelimit")
def github_rate(project_id: str | None = None):
    token = project_github_token(project_id) if project_id else GITHUB_TOKEN
    if not token:
        raise HTTPException(400, "no GitHub PAT available")
    return github.GitHub(token, GITHUB_API).rate_limit()


@app.get("/api/github/my-repos")
def my_repos(project_id: str | None = None, request: Request = None):
    # Prefer a project-scoped PAT; allow an X-Provider-PAT override.
    header_pat = ""
    if request is not None:
        header_pat = request.headers.get("X-Provider-PAT", "").strip()
    token = header_pat or (project_github_token(project_id) if project_id else GITHUB_TOKEN)
    if not token:
        raise HTTPException(400, "no GitHub PAT — configure one on the project (or pass X-Provider-PAT)")
    try:
        return {"repos": github.GitHub(token, GITHUB_API).list_user_repos()}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("GitHub", e)


# --------------------------------------------------------------- settings (Config)
@app.get("/api/settings")
def get_settings():
    s = store.get_settings()
    return {
        # First-run gate: the UI lands on Configuration until the required LLM
        # section has been saved at least once (set in put_settings).
        "configured": bool(s.get("configured")),
        "llm_provider": s.get("llm_provider", "ollama"),
        "llm_base_url": s.get("llm_base_url", ""),
        "llm_model": s.get("llm_model", GEN_MODEL),
        "llm_region": s.get("llm_region", ""),
        "llm_api_key_set": bool(s.get("llm_api_key_enc")),
        # Deploy-time lock: pin the whole app to a single provider (e.g. an
        # air-gapped Bedrock-only client). Empty string = no lock (OSS build).
        "provider_lock": PROVIDER_LOCK,
        # Ollama endpoint: .env wins (locked); else the frontend-saved value; else bundled.
        "ollama_url": ("" if _ENV_OLLAMA else s.get("ollama_url", "")),
        "ollama_url_effective": current_ollama_url(),
        "ollama_url_env_locked": bool(_ENV_OLLAMA),
        "poll_interval_s": POLL_INTERVAL,
        "jira_base_url": s.get("jira_base_url", ""),
        "jira_email": s.get("jira_email", ""),
        "jira_token_set": bool(s.get("jira_api_token_enc")),
        "jira_configured": bool(s.get("jira_base_url") and s.get("jira_email")
                                and s.get("jira_api_token_enc")),
        "smtp_host": s.get("smtp_host", ""),
        "smtp_port": s.get("smtp_port", ""),
        "smtp_user": s.get("smtp_user", ""),
        "smtp_from": s.get("smtp_from", ""),
        "smtp_tls": s.get("smtp_tls", True),
        "smtp_ssl": s.get("smtp_ssl", False),
        "smtp_pass_set": bool(s.get("smtp_pass_enc")),
        "smtp_configured": bool(s.get("smtp_host")),
        "figma_token_set": bool(s.get("figma_api_token_enc")),
        # LLM cost model: per-1M-token prices, plus the built-in defaults for the editor.
        "llm_prices": s.get("llm_prices", {}),
        "llm_price_defaults": usage.DEFAULT_PRICES,
        # Embedding model (switching it rebuilds indexes + re-embeds everything).
        "embed_provider": s.get("embed_provider", "ollama"),
        "embed_model": s.get("embed_model", EMBED_MODEL),
        "embed_dim": int(s.get("embed_dim") or EMBED_DIM),
        "embed_base_url": s.get("embed_base_url", ""),
        "embed_region": s.get("embed_region", ""),
        "embed_api_key_set": bool(s.get("embed_api_key_enc")),
        "embed_model_options": EMBED_MODEL_OPTIONS,
    }


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_region: str | None = None
    ollama_url: str | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str | None = None
    smtp_tls: bool | None = None
    smtp_ssl: bool | None = None
    figma_api_token: str | None = None
    llm_prices: dict | None = None


def _merged_settings_dict(body: SettingsIn):
    s = store.get_settings()
    return {
        "llm_provider": body.llm_provider if body.llm_provider is not None else s.get("llm_provider", "ollama"),
        "llm_base_url": body.llm_base_url.strip() if body.llm_base_url is not None else s.get("llm_base_url", ""),
        "llm_model": body.llm_model if body.llm_model is not None else s.get("llm_model", GEN_MODEL),
        "llm_region": body.llm_region.strip() if body.llm_region is not None else s.get("llm_region", ""),
        "llm_api_key": body.llm_api_key.strip() if body.llm_api_key is not None else (
            crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
        ),
        "jira_base_url": body.jira_base_url.strip() if body.jira_base_url is not None else s.get("jira_base_url", ""),
        "jira_email": body.jira_email.strip() if body.jira_email is not None else s.get("jira_email", ""),
        "jira_api_token": body.jira_api_token.strip() if body.jira_api_token is not None else (
            crypto.decrypt(s.get("jira_api_token_enc", "")) if s.get("jira_api_token_enc") else ""
        ),
        "smtp_host": body.smtp_host.strip() if body.smtp_host is not None else s.get("smtp_host", ""),
        "smtp_port": body.smtp_port if body.smtp_port is not None else s.get("smtp_port", ""),
        "smtp_user": body.smtp_user.strip() if body.smtp_user is not None else s.get("smtp_user", ""),
        "smtp_pass": body.smtp_pass if body.smtp_pass is not None else (
            crypto.decrypt(s.get("smtp_pass_enc", "")) if s.get("smtp_pass_enc") else ""
        ),
        "smtp_from": body.smtp_from.strip() if body.smtp_from is not None else s.get("smtp_from", ""),
        "smtp_tls": body.smtp_tls if body.smtp_tls is not None else s.get("smtp_tls", True),
        "smtp_ssl": body.smtp_ssl if body.smtp_ssl is not None else s.get("smtp_ssl", False),
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn, request: Request):
    merged = _merged_settings_dict(body)
    # LLM connectivity validation if updated
    llm_updated = (
        body.llm_provider is not None or
        body.llm_base_url is not None or
        body.llm_model is not None or
        body.llm_api_key is not None or
        body.llm_region is not None
    )
    if llm_updated:
        # Validate against the Ollama URL being submitted now (if any), not the stale
        # saved one — otherwise a combined provider+endpoint change pings the old host.
        _val_ollama = (body.ollama_url.strip() if body.ollama_url is not None else "") or current_ollama_url()
        temp_llm = LLM(
            provider=merged["llm_provider"],
            model=merged["llm_model"],
            api_key=merged["llm_api_key"],
            base_url=merged["llm_base_url"],
            ollama_url=_val_ollama,
            region=merged["llm_region"],
        )
        try:
            temp_llm.ping()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"LLM validation failed: {e}")

    jira_updated = (
        body.jira_base_url is not None or
        body.jira_email is not None or
        body.jira_api_token is not None
    )
    if jira_updated:
        jira_values = [merged["jira_base_url"], merged["jira_email"], merged["jira_api_token"]]
        if any(jira_values):
            if not all(jira_values):
                raise HTTPException(status_code=400, detail="Jira validation failed: base URL, email, and API token are all required")
            try:
                me = jira.Jira(
                    merged["jira_base_url"],
                    merged["jira_email"],
                    merged["jira_api_token"],
                ).myself()
                if not me:
                    raise HTTPException(status_code=400, detail="Jira validation failed: could not verify account")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Jira validation failed: {e}")

    smtp_updated = (
        body.smtp_host is not None or
        body.smtp_port is not None or
        body.smtp_user is not None or
        body.smtp_pass is not None or
        body.smtp_from is not None or
        body.smtp_tls is not None or
        body.smtp_ssl is not None
    )
    if smtp_updated and merged["smtp_host"]:
        # Gmail always requires an authenticated App Password; catch the missing-
        # credentials case up front so validation doesn't "pass" on a bare connect.
        if email_send.is_gmail(merged["smtp_host"]) and not (merged["smtp_user"] and merged["smtp_pass"]):
            raise HTTPException(status_code=400, detail="SMTP validation failed: Gmail "
                "requires a username (your full Gmail address) and a 16-character App "
                "Password (with 2-Step Verification enabled on the account).")
        # Validate with the SAME normalized password we'll persist — otherwise a
        # Gmail App Password pasted with its display spaces ("abcd efgh …") is sent
        # verbatim and Gmail rejects it (535 BadCredentials) even though it's valid.
        validate_pass = email_send.normalize_smtp_password(merged["smtp_host"], merged["smtp_pass"])
        ok, err = email_send.validate_config({
            "host": merged["smtp_host"],
            "port": merged["smtp_port"],
            "user": merged["smtp_user"],
            "password": validate_pass,
            "from": merged["smtp_from"],
            "tls": merged["smtp_tls"],
            "ssl": merged["smtp_ssl"],
        })
        if not ok:
            raise HTTPException(status_code=400, detail=f"SMTP validation failed: {err}")

    upd = {}
    if body.llm_provider is not None:
        upd["llm_provider"] = body.llm_provider
    if body.llm_base_url is not None:
        upd["llm_base_url"] = body.llm_base_url
    if body.llm_model is not None:
        upd["llm_model"] = body.llm_model
    if body.llm_region is not None:
        upd["llm_region"] = body.llm_region.strip()
    if body.llm_api_key is not None:
        upd["llm_api_key_enc"] = crypto.encrypt(body.llm_api_key) if body.llm_api_key else ""
    if body.ollama_url is not None:
        # Ignored when OLLAMA_URL is locked by .env; otherwise applies live (no restart).
        upd["ollama_url"] = body.ollama_url.strip()
    if llm_updated:
        # Saving the required LLM section marks first-run setup complete, so the UI
        # stops force-landing on Configuration after sign-in.
        upd["configured"] = True
    if body.jira_base_url is not None:
        upd["jira_base_url"] = body.jira_base_url
    if body.jira_email is not None:
        upd["jira_email"] = body.jira_email
    if body.jira_api_token is not None:
        upd["jira_api_token_enc"] = crypto.encrypt(body.jira_api_token) if body.jira_api_token else ""
    if body.smtp_host is not None:
        upd["smtp_host"] = body.smtp_host.strip()
    if body.smtp_port is not None:
        upd["smtp_port"] = body.smtp_port
    if body.smtp_user is not None:
        upd["smtp_user"] = body.smtp_user.strip()
    if body.smtp_pass is not None:
        clean_pass = email_send.normalize_smtp_password(merged["smtp_host"], body.smtp_pass)
        upd["smtp_pass_enc"] = crypto.encrypt(clean_pass) if clean_pass else ""
    if body.smtp_from is not None:
        upd["smtp_from"] = body.smtp_from.strip()
    if body.smtp_tls is not None:
        upd["smtp_tls"] = body.smtp_tls
    if body.smtp_ssl is not None:
        upd["smtp_ssl"] = body.smtp_ssl
    if body.figma_api_token is not None:
        upd["figma_api_token_enc"] = crypto.encrypt(body.figma_api_token) if body.figma_api_token else ""
    if body.llm_prices is not None:
        # keep only well-formed {model: {in, out}} entries
        clean = {}
        for m, p in (body.llm_prices or {}).items():
            if isinstance(p, dict):
                try:
                    clean[str(m)] = {"in": float(p.get("in", 0)), "out": float(p.get("out", 0))}
                except (TypeError, ValueError):
                    continue
        upd["llm_prices"] = clean
    if upd:
        store.save_settings(upd)
        # Record which settings groups changed (never the secret values themselves).
        changed = sorted({k.replace("_enc", "").split("_")[0] for k in upd})
        _audit(request, "settings.updated", detail=", ".join(changed))
    return get_settings()


@app.get("/api/ollama/models")
def ollama_models():
    """List the models actually installed in the connected Ollama, so the UI can offer
    only real choices (avoids picking a model that isn't downloaded). Uses the effective
    Ollama URL + the saved LLM token (for a secured/remote Ollama). Best-effort."""
    url = current_ollama_url().rstrip("/")
    s = store.get_settings()
    key = crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        import httpx
        r = httpx.get(f"{url}/api/tags", timeout=8.0, headers=headers)
        r.raise_for_status()
        models = sorted(m.get("name") for m in r.json().get("models", []) if m.get("name"))
        return {"ok": True, "models": models, "url": url}
    except Exception as e:  # noqa: BLE001
        print(f"[wardenIQ][ollama-tags] {url}: {e!r}", flush=True)
        return {"ok": False, "models": [], "url": url,
                "error": "could not reach Ollama at this URL"}


@app.post("/api/llm/test")
def llm_test():
    try:
        return {"ok": True, **current_llm().ping()}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("LLM", e)


# --------------------------------------------------------------- auth + users
def _smtp_cfg_from_env():
    """SMTP config from environment variables, if SMTP_HOST is set.

    This lets an operator configure email delivery entirely from .env so OTP emails
    work from first boot — no in-app setup, and the password is never encrypted with
    APP_SECRET (so rotating APP_SECRET can't break email). Env takes precedence over
    the in-app (DB) config below.
    """
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        return None
    port_raw = (os.getenv("SMTP_PORT") or "").strip()
    ssl_flag = (os.getenv("SMTP_SSL", "false").strip().lower() == "true")
    tls_flag = (os.getenv("SMTP_TLS", "true").strip().lower() == "true")
    # Normalize the password: Gmail shows App Passwords as "abcd efgh ijkl mnop" for
    # readability, but the real secret is 16 chars with NO spaces. Leaving spaces in
    # is the #1 cause of Gmail's "535 Username and Password not accepted". Always trim
    # ends; for Gmail, strip all internal whitespace too.
    raw_pass = (os.getenv("SMTP_PASS") or "").strip()
    is_gmail = host.lower().endswith(("gmail.com", "googlemail.com"))
    if is_gmail:
        password = re.sub(r"\s+", "", raw_pass)
        # Gmail App Passwords are exactly 16 chars. A wrong length is a config error
        # that would otherwise surface as an opaque "535 BadCredentials" — warn early.
        if password and len(password) != 16:
            print(f"[wardenIQ][SMTP][WARNING] SMTP_PASS is {len(password)} chars after "
                  "removing spaces, but a Gmail App Password must be exactly 16. "
                  "Gmail will reject this with 535 BadCredentials. Re-copy the 16-char "
                  "App Password from Google → Security → App passwords.", flush=True)
    else:
        password = raw_pass
    return {
        "host": host,
        "port": int(port_raw) if port_raw.isdigit() else (465 if ssl_flag else 587),
        "user": (os.getenv("SMTP_USER") or "").strip(),
        "password": password,
        "from": (os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "").strip(),
        "tls": tls_flag,
        "ssl": ssl_flag,
    }


def _smtp_cfg():
    # In-app SMTP (saved in the DB) takes precedence when configured — "what you set in
    # the app is what's used". .env SMTP is the FALLBACK: it bootstraps OTP email for the
    # very first admin login (before anyone can sign in to configure it in-app), and it
    # covers the case where the DB value can't be decrypted (e.g. after APP_SECRET rotation).
    s = store.get_settings()
    if s.get("smtp_host"):
        pw = ""
        if s.get("smtp_pass_enc"):
            pw = crypto.decrypt(s.get("smtp_pass_enc", ""))
            # crypto.decrypt() swallows its own failures and returns "" rather than
            # raising — so we can't catch an exception here. But crypto.encrypt() only
            # ever produces "" from an empty plaintext, so a non-empty smtp_pass_enc
            # that decrypts to "" can only mean the key no longer matches (APP_SECRET
            # rotated) — treat that as unreadable and fall back to .env, same as if
            # decrypt() had raised.
            if not pw:
                pw = None
        if pw is not None:
            return {"host": s.get("smtp_host"), "port": s.get("smtp_port"),
                    "user": s.get("smtp_user"), "password": pw,
                    "from": s.get("smtp_from"), "tls": s.get("smtp_tls", True),
                    "ssl": s.get("smtp_ssl", False)}
    # No usable in-app SMTP → fall back to environment (.env) config, if any.
    return _smtp_cfg_from_env()

def _deliver_otp(email, code, recipient_name="", is_admin=False):
    """Returns ('sent'|'logged'|'error', detail).
    - 'sent'    : emailed via SMTP.
    - 'logged'  : no SMTP configured -> the code is printed to the server log AND
                  returned to the caller so the sign-in screen can display it
                  directly. This is the demo/dev-mode path: it makes wardenIQ
                  usable without configuring email so contributors and evaluators
                  can sign in and try the app. Once SMTP is configured every code
                  is emailed and never logged or returned.
    - 'error'   : SMTP configured but the send failed.

    The `is_admin` argument is retained for callers/log context but no longer
    gates the 'logged' path — see the note above on demo-mode behavior.
    """
    cfg = _smtp_cfg()
    if not cfg:
        # No SMTP -> demo/dev mode. Log the code (operators reading `docker logs`
        # can still fetch it) and return it so the UI can show it inline. Anyone
        # who can hit the sign-in endpoint on this host is trusted at this point:
        # a public deployment must configure SMTP before exposing wardenIQ.
        role_hint = "admin" if is_admin else "user"
        print("\n" + "=" * 64 +
              f"\n[wardenIQ] SMTP is not configured — one-time sign-in code"
              f"\n[wardenIQ]   {email} ({role_hint}): {code}"
              f"\n[wardenIQ] The code is also shown on the sign-in screen. Set up"
              f"\n[wardenIQ] email under Configuration → Email to disable this"
              f"\n[wardenIQ] demo path (codes will then only be emailed).\n"
              + "=" * 64 + "\n",
              flush=True)
        return "logged", code

    ok, err = email_send.send_otp(cfg, email, code, recipient_name)
    if ok:
        return "sent", ""

    print(f"[wardenIQ][OTP send failed for {email}: {err}]", flush=True)
    return "error", err

class OtpRequestIn(BaseModel):
    email: str


@app.post("/api/auth/request-otp")
def request_otp(body: OtpRequestIn):
    email = (body.email or "").strip().lower()
    if not auth.is_valid_email(email):
        raise HTTPException(400, "a valid email is required")
    user = store.get_user_by_email(email)
    bootstrap = False
    if not user:
        # First-run convenience: with no users with valid emails yet, the first requester becomes admin.
        has_real_users = any(auth.is_valid_email(u.get("email")) for u in store.list_users())
        if not has_real_users:
            user = store.create_user(email, email.split("@")[0], "admin"); bootstrap = True
        else:
            # Don't reveal whether an account exists.
            return {"sent": True}
    if not user.get("active"):
        return {"sent": True}
    # Rate-limit code issuance per account. Return the generic {"sent": True} on limit
    # so we don't reveal that the account exists or is being targeted.
    if store.otp_recent_issue_count(user["id"], OTP_WINDOW_SECONDS) > OTP_MAX_PER_WINDOW:
        print(f"[wardenIQ][OTP throttled] {email} exceeded "
              f"{OTP_MAX_PER_WINDOW}/{OTP_WINDOW_SECONDS}s", flush=True)
        return {"sent": True}
    code = auth.gen_otp()
    store.set_otp(user["id"], auth.hash_otp(code), time.time() + auth.OTP_TTL)
    mode, detail = _deliver_otp(email, code, user.get("name") or email.split("@")[0],
                                is_admin=(user.get("role") == "admin"))
    if mode == "error":
        raise HTTPException(502, "could not send the sign-in email — please try again "
                                 "or contact your administrator")
    # delivery: "email" (SMTP) or "log" (demo/dev mode — no SMTP configured, code
    # is printed to the server log AND returned in `dev_code` for the sign-in UI).
    resp = {"sent": True, "bootstrap": bootstrap,
            "delivery": "log" if mode == "logged" else "email"}
    if mode == "logged":
        # `detail` holds the plaintext code in this mode (see _deliver_otp).
        resp["dev_code"] = detail
    return resp


class OtpVerifyIn(BaseModel):
    email: str
    code: str


@app.post("/api/auth/verify-otp")
def verify_otp(body: OtpVerifyIn, response: Response):
    email = (body.email or "").strip().lower()
    user = store.get_user_by_email(email)
    migrating = False
    if not user:
        # Check if there are no users with a valid email yet
        has_real_users = any(auth.is_valid_email(u.get("email")) for u in store.list_users())
        if not has_real_users:
            user = store.get_user_by_email("admin")
            if user:
                migrating = True

    if not user or not user.get("active"):
        raise HTTPException(401, "invalid email or code")
    if not user.get("otp_hash") or user.get("otp_expires", 0) < time.time():
        raise HTTPException(401, "code expired — request a new one")
    if user.get("otp_attempts", 0) >= auth.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "too many attempts — request a new code")
    if not auth.otp_matches(user["otp_hash"], body.code):
        store.inc_otp_attempts(user["id"])
        raise HTTPException(401, "invalid email or code")
        
    store.clear_otp(user["id"])
    if migrating:
        store.update_user(user["id"], {"email": email, "name": email.split("@")[0]})
        
    store.touch_login(user["id"])
    
    fresh = store.get_user(user["id"]) or user
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(user["id"], fresh.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"user": _user_public(fresh)}


@app.get("/api/auth/smtp-status")
def smtp_status():
    cfg = _smtp_cfg()
    return {"smtp_setup": cfg is not None}


class LoginPasswordIn(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login-password")
def login_password(body: LoginPasswordIn, response: Response):
    cfg = _smtp_cfg()
    if cfg is not None:
        raise HTTPException(400, "Password login is disabled because SMTP is configured. Please use email OTP.")

    username = (body.username or "").strip()
    password = body.password or ""

    if username != "admin":
        raise HTTPException(401, "Invalid username or password")

    user = store.get_user_by_email("admin")
    if not user:
        # First boot: no local admin row yet, so only the configured default works
        # (ADMIN_PASSWORD if the operator set one, else the shipped admin123).
        if password != DEFAULT_ADMIN_PASSWORD:
            raise HTTPException(401, "Invalid username or password")
        user = store.create_user("admin", "Admin", "admin")
    else:
        stored_hash = user.get("password_hash")
        # Once a real password has been set (via ADMIN_PASSWORD seeding or
        # /api/auth/change-password), it's the only one accepted — the shipped
        # default stops working so it can't be bypassed with the old admin123.
        ok = (auth.password_matches(stored_hash, password) if stored_hash
              else password == DEFAULT_ADMIN_PASSWORD)
        if not ok:
            raise HTTPException(401, "Invalid username or password")

    if not user.get("active"):
        raise HTTPException(401, "User account is deactivated")

    store.touch_login(user["id"])
    fresh = store.get_user(user["id"]) or user
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(user["id"], fresh.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"user": _user_public(fresh)}


class ChangePasswordIn(BaseModel):
    current_password: str = ""
    new_password: str


@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordIn, request: Request, response: Response):
    """Self-service password change for the local admin account. Only meaningful for
    the bootstrap `admin` / admin123 account — email-based accounts sign in with a
    one-time code and have no password to change. Requires an authenticated session
    (this route is NOT public — the auth_gateway already resolved request.state.user)."""
    user = _current_user(request)
    if not user:
        raise HTTPException(401, "not authenticated")
    if user.get("email") != "admin":
        raise HTTPException(400, "password sign-in is only available for the local admin "
                                 "account — email accounts sign in with a one-time code and "
                                 "have no password to change")
    full = store.get_user_by_email("admin") or user
    stored_hash = full.get("password_hash")
    current = body.current_password or ""
    current_ok = (auth.password_matches(stored_hash, current) if stored_hash
                  else current == DEFAULT_ADMIN_PASSWORD)
    if not current_ok:
        raise HTTPException(400, "current password is incorrect")

    errs = auth.password_policy_errors(body.new_password)
    if errs:
        raise HTTPException(400, "Password must have " + ", ".join(errs) + ".")
    if body.new_password == current:
        raise HTTPException(400, "new password must be different from the current one")

    updated = store.set_user_password(full["id"], auth.hash_password(body.new_password))
    _audit(request, "user.password_changed", target="admin", actor=user)
    # set_user_password() bumps session_version, invalidating every session this
    # user holds — including the one making this request — so re-issue a fresh
    # cookie for THIS session immediately, or the caller would be logged out by
    # their own password change.
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(full["id"], updated.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"changed": True, "user": _user_public(updated)}


@app.get("/api/auth/me")
def auth_me(request: Request):
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    if not user or not user.get("active"):
        raise HTTPException(401, "not authenticated")
    if int(user.get("session_version", 0)) != int(tok_sv):
        raise HTTPException(401, "session expired — please sign in again")
    return {"user": _user_public(user), "auth_enabled": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


def _session_user(request: Request):
    """Resolve the current user from the session cookie for self-service /api/auth
    endpoints (these are public-prefixed, so the gateway hasn't populated
    request.state.user). Enforces the same session_version check as the gateway."""
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    if not user or not user.get("active"):
        raise HTTPException(401, "not authenticated")
    if int(user.get("session_version", 0)) != int(tok_sv):
        raise HTTPException(401, "session expired — please sign in again")
    return user


def _invite_view(user):
    """Shape a pending invite for the invited user's banner, with inviter info."""
    inviter = None
    try:
        inviter = store.invite_inviter_info(user["id"])
    except Exception:  # noqa: BLE001
        inviter = None
    return {
        "pending": user.get("invite_status") == "pending",
        "role": user.get("role", "viewer"),
        "invited_at": user.get("invited_at"),
        "invited_by": inviter,               # {email, name} or None
        "workspace": APP_WORKSPACE_NAME,     # single-tenant label
    }


@app.get("/api/auth/my-invite")
def my_invite(request: Request):
    """The current user's own invite state (for the post-login invite banner)."""
    user = _session_user(request)
    return {"invite": _invite_view(user)}


@app.post("/api/auth/invite/accept")
def accept_my_invite(request: Request):
    user = _session_user(request)
    if user.get("invite_status") != "pending":
        # Idempotent: nothing to do if already resolved.
        return {"invite": _invite_view(store.get_user(user["id"]))}
    updated = store.accept_invite(user["id"])
    store.clear_invite_token(user["id"])   # consume the single-use invite token
    _audit(request, "invite.accepted", target=user.get("email"), actor=user)
    return {"invite": _invite_view(updated), "user": _user_public(updated)}


@app.post("/api/auth/invite/decline")
def decline_my_invite(request: Request, response: Response):
    user = _session_user(request)
    if user.get("invite_status") != "pending":
        return {"declined": False}
    store.decline_invite(user["id"])
    store.clear_invite_token(user["id"])   # consume the single-use invite token
    _audit(request, "invite.declined", target=user.get("email"), actor=user)
    # Declining deactivates the account; end the session too.
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"declined": True}


def _user_public(u):
    return {"id": u["id"], "email": u["email"], "name": u.get("name"),
            "role": u.get("role", "viewer"), "active": u.get("active", True),
            "created_at": u.get("created_at"), "last_login": u.get("last_login"),
            "invite_status": u.get("invite_status", "active"),
            "invited_at": u.get("invited_at"),
            "all_projects": u.get("all_projects", True),
            "project_ids": u.get("project_ids", []),
            # True only for the local "admin" bootstrap account while it's still on
            # the shipped default password — drives the mandatory change-password
            # prompt on first login. Always False for email-based accounts (they
            # sign in with a one-time code and have no password at all).
            "must_change_password": u.get("email") == "admin" and not bool(u.get("password_hash"))}


@app.get("/api/users")
def list_users():
    return {"users": [_user_public(u) for u in store.list_users()]}


class UserIn(BaseModel):
    email: str
    name: str | None = None
    role: str = "viewer"
    # Project access: all_projects=True (default) grants every project; otherwise the
    # user is limited to project_ids. Admins always have all projects regardless.
    all_projects: bool = True
    project_ids: list[str] = []


INVITE_TTL = int(os.getenv("INVITE_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days


def _issue_invite_link(u, request=None, inviter_name=""):
    """Generate a single-use, time-limited invite TOKEN and email an invite LINK
    (NOT a login OTP — the two are separate now, so a later login can't overwrite the
    invite). Returns ((delivery_mode, detail), token).

    delivery_mode: 'sent' (emailed) | 'refused' (no SMTP) | 'error' (send failed).
    The invite link is never logged or returned over the network.
    """
    token = auth.gen_invite_token()
    store.set_invite_token(u["id"], auth.hash_token(token), time.time() + INVITE_TTL)
    base = _webhook_base_url(request)
    link = f"{base}/invite?token={token}" if base else f"/invite?token={token}"
    cfg = _smtp_cfg()
    if not cfg:
        print(f"[wardenIQ][invite refused] SMTP not configured for {u['email']}", flush=True)
        return ("refused", "smtp not configured"), token
    ok, err = email_send.send_invite(
        cfg, u["email"], link, inviter=inviter_name,
        role=u.get("role", "viewer"), workspace=APP_WORKSPACE_NAME,
        recipient_name=u.get("name") or "")
    if ok:
        return ("sent", link), token
    print(f"[wardenIQ][invite send failed for {u['email']}: {err}]", flush=True)
    return ("error", err), token


@app.post("/api/users")
def invite_user(body: UserIn, request: Request):
    email = (body.email or "").strip().lower()
    if not auth.is_valid_email(email):
        raise HTTPException(400, "a valid email is required")
    if store.get_user_by_email(email):
        raise HTTPException(409, "a user with that email already exists")
    role = body.role if body.role in auth.ROLES else "viewer"
    me = _current_user(request)
    # Admins implicitly have all projects; for others honor the selection. Validate
    # that any specified project ids actually exist.
    all_projects = True if role == "admin" else bool(body.all_projects)
    project_ids = [] if all_projects else [p for p in (body.project_ids or []) if store.get_project(p)]
    if not all_projects and not project_ids:
        raise HTTPException(400, "select at least one project, or grant access to all projects")
    u = store.create_user(email, (body.name or email.split("@")[0]), role,
                          invite_status="pending",
                          invited_by=(me.get("id") if me else None),
                          all_projects=all_projects, project_ids=project_ids)
    _audit(request, "user.invited", target=email,
           new={"role": role, "all_projects": all_projects, "project_ids": project_ids})
    (mode, detail), token = _issue_invite_link(
        u, request, inviter_name=(me.get("name") or me.get("email")) if me else "")
    # Report delivery honestly. A failed/absent email must NOT be reported as sent,
    # but the user is still created (admin can resend once SMTP is fixed).
    resp = {"user": _user_public(store.get_user(u["id"])), "delivery": mode}
    if mode == "sent":
        resp["message"] = f"Invite sent — an invitation link was emailed to {email}."
    elif mode == "refused":
        resp["message"] = ("User created, but no invitation email was sent: SMTP is "
                           "not configured. Configure email, then use Resend.")
    else:  # error
        resp["message"] = ("User created, but the invitation email failed to send. "
                           "Check the SMTP configuration and use Resend.")
    return resp


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    name: str | None = None
    all_projects: bool | None = None
    project_ids: list[str] | None = None


@app.patch("/api/users/{uid}")
def patch_user(uid: str, body: UserPatch, request: Request):
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    upd = {}
    if body.name is not None:
        upd["name"] = body.name
    if body.role is not None and body.role in auth.ROLES:
        upd["role"] = body.role
    if body.active is not None:
        upd["active"] = body.active
    # Don't let the last active admin be demoted or disabled (lockout guard).
    demoting = (upd.get("role") and upd["role"] != "admin") or (upd.get("active") is False)
    if target.get("role") == "admin" and target.get("active") and demoting \
            and store.count_active_admins() <= 1:
        raise HTTPException(400, "cannot demote or disable the last active admin")
    # Project access change. An admin always has all projects, so if the resulting
    # role is admin we force all_projects. Otherwise honor the payload.
    projects_changed = body.all_projects is not None or body.project_ids is not None
    if projects_changed:
        result_role = upd.get("role", target.get("role"))
        if result_role == "admin":
            all_proj, pids = True, []
        else:
            all_proj = target.get("all_projects", True) if body.all_projects is None else bool(body.all_projects)
            pids = ([] if all_proj
                    else [p for p in (body.project_ids if body.project_ids is not None
                                      else target.get("project_ids", [])) if store.get_project(p)])
            if not all_proj and not pids:
                raise HTTPException(400, "select at least one project, or grant access to all projects")
    updated = store.update_user(uid, upd) if upd else target
    if projects_changed:
        updated = store.set_user_projects(uid, all_proj, pids)
    # A role/active/project change must take effect immediately: bump session_version
    # so existing sessions re-auth with the new authorization. (Name-only doesn't.)
    role_changed = "role" in upd and upd["role"] != target.get("role")
    active_changed = "active" in upd and upd["active"] != target.get("active")
    if role_changed or active_changed or projects_changed:
        updated = store.bump_session_version(uid)
    if role_changed:
        _audit(request, "user.role_changed", target=target.get("email"),
               old={"role": target.get("role")}, new={"role": upd.get("role")})
    if active_changed:
        _audit(request, "user.enabled" if upd.get("active") else "user.disabled",
               target=target.get("email"))
    if projects_changed:
        _audit(request, "user.projects_changed", target=target.get("email"),
               old={"all_projects": target.get("all_projects"), "project_ids": target.get("project_ids")},
               new={"all_projects": all_proj, "project_ids": pids})
    return {"user": _user_public(updated)}


@app.delete("/api/users/{uid}")
def remove_user(uid: str, request: Request):
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    me = _current_user(request)
    if me and me.get("id") == uid:
        raise HTTPException(400, "you can't delete your own account")
    if target.get("role") == "admin" and target.get("active") \
            and store.count_active_admins() <= 1:
        raise HTTPException(400, "cannot delete the last active admin")
    _audit(request, "user.deleted", target=target.get("email"),
           old={"role": target.get("role")})
    return store.delete_user(uid)


@app.get("/api/audit-logs")
def audit_logs(limit: int = 100, action: str | None = None, actor: str | None = None):
    """Admin-only audit trail (gated by ADMIN_PATHS)."""
    return {"logs": store.list_audit(limit=limit, action=action, actor_email=actor)}


@app.get("/api/db-status")
def db_status():
    """Read-only database snapshot for the Configuration UI (admin-only, gated by
    ADMIN_PATHS). No credentials are returned — the database is configured via the
    MONGO_URI env var, not here; this is observability only. Includes whether the
    bundled/managed search engine is available and whether the URI is externally set."""
    info = store.db_info()
    info["db_name"] = DB_NAME
    # Bundled vs bring-your-own is inferred from the actual connected host, not from
    # the env var (compose always injects MONGO_URI, so its mere presence is not a
    # reliable signal). The bundled nodes live on the internal *.warden-net aliases.
    hosts = info.get("hosts") or []
    info["managed"] = not any(".warden-net" in h for h in hosts)
    info["boot"] = BOOT
    # Frontend-config capabilities: whether MONGO_URI is pinned in .env, and whether
    # we can persist a new one (the .env bind-mount must be writable).
    info["configured_via_env"] = bool(_ENV_MONGO)
    info["env_file"] = ENV_FILE_PATH
    info["env_writable"] = _env_file_writable()
    return info


def _env_file_writable() -> bool:
    """True if we can persist config into the .env file (it exists & is writable, or
    its directory is writable so we could create it). In Docker this requires the
    ./.env bind-mount from docker-compose.app.yml."""
    try:
        if os.path.exists(ENV_FILE_PATH):
            return os.access(ENV_FILE_PATH, os.W_OK)
        return os.access(os.path.dirname(ENV_FILE_PATH) or ".", os.W_OK)
    except Exception:  # noqa: BLE001
        return False


def _write_env_var(path: str, key: str, value: str):
    """Upsert `KEY=value` in a .env file, preserving all other lines and comments.
    Only an ACTIVE assignment is replaced; commented example lines are left intact.
    Returns (ok, error)."""
    try:
        lines = []
        if os.path.exists(path):
            with open(path, "r") as f:
                lines = f.read().splitlines()
        prefix = key + "="
        out, found = [], False
        for ln in lines:
            if ln.lstrip().startswith(prefix):
                out.append(f"{key}={value}"); found = True
            else:
                out.append(ln)
        if not found:
            out.append(f"{key}={value}")
        with open(path, "w") as f:
            f.write("\n".join(out) + "\n")
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _probe_mongo(uri: str):
    """Best-effort connectivity + Vector Search check for a candidate URI, so we never
    persist a connection string that would brick startup. Returns (reachable, search_ok, detail)."""
    try:
        from pymongo import MongoClient
        c = MongoClient(uri, serverSelectionTimeoutMS=3500)
        try:
            c.admin.command("ping")
            search_ok = True
            try:
                list(c[DB_NAME]["test_cases"].list_search_indexes())
            except Exception as e:  # noqa: BLE001
                # A search-less server rejects the command outright; a missing namespace
                # (fresh DB) does NOT mean search is unsupported.
                search_ok = not _search_unsupported(e)
            return True, search_ok, "ok"
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        return False, False, str(e)[:200]


class DbConfigIn(BaseModel):
    uri: str | None = None
    force: bool | None = False   # save even if the connection test fails


@app.post("/api/db-config")
def set_db_config(body: DbConfigIn, request: Request):
    """Persist a new MongoDB connection string into .env (admin-only). Joomla-style:
    the value is written to the config file, never echoed back, and takes effect on the
    next `docker compose up -d`. We test-connect first and refuse to save an unreachable
    or search-incapable DB unless `force` is set."""
    uri = (body.uri or "").strip()
    if not uri:
        raise HTTPException(400, "Enter a MongoDB connection string.")
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        raise HTTPException(400, "Connection string must start with mongodb:// or mongodb+srv://")
    if not _env_file_writable():
        raise HTTPException(500, f"Cannot write to the config file ({ENV_FILE_PATH}). In Docker, "
                                 "the ./.env bind-mount in docker-compose.app.yml must be present "
                                 "and writable.")
    reachable, search_ok, detail = _probe_mongo(uri)
    if not reachable and not body.force:
        raise HTTPException(400, f"Could not connect to that database: {detail}. Nothing was saved. "
                                 "Re-submit with 'save anyway' to store it regardless.")
    if reachable and not search_ok and not body.force:
        raise HTTPException(400, "That database connected but has no Vector Search (not Atlas and no "
                                 "mongot). wardenIQ requires search. Nothing was saved. Use 'save "
                                 "anyway' only if search will be enabled before restart.")
    ok, err = _write_env_var(ENV_FILE_PATH, "MONGO_URI", uri)
    if not ok:
        raise HTTPException(500, f"Failed to write the config file: {err}")
    _audit(request, "db.config.updated", detail="MONGO_URI changed via UI")
    return {"ok": True, "restart_required": True, "reachable": reachable,
            "search_available": search_ok, "apply_cmd": "docker compose up -d"}


class DbMigrateIn(BaseModel):
    target_uri: str | None = None
    overwrite: bool | None = False


@app.post("/api/db-migrate")
def db_migrate(body: DbMigrateIn, request: Request):
    """Copy ALL data from the current database into a target MongoDB and point
    MONGO_URI at it (admin-only). Runs as a background job; the app stays on the
    current DB until the user restarts, so a partial copy never loses data."""
    uri = (body.target_uri or "").strip()
    if not uri:
        raise HTTPException(400, "Enter the target MongoDB connection string.")
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        raise HTTPException(400, "Connection string must start with mongodb:// or mongodb+srv://")
    if not _env_file_writable():
        raise HTTPException(500, f"Cannot write to the config file ({ENV_FILE_PATH}); the ./.env "
                                 "bind-mount in docker-compose.app.yml must be present and writable.")
    # The target must be reachable AND search-capable — otherwise the copy would land
    # in a database the app can't actually run on.
    reachable, search_ok, detail = _probe_mongo(uri)
    if not reachable:
        raise HTTPException(400, f"Couldn't connect to the target database: {detail}. Nothing copied.")
    if not search_ok:
        raise HTTPException(400, "The target has no Vector Search (not Atlas, and no mongot), so "
                                 "wardenIQ couldn't run on it. Migration cancelled — nothing copied.")
    # Guard against clobbering a target that already has data (unless the caller insists).
    try:
        if not body.overwrite and store.target_has_data(uri):
            raise HTTPException(409, "The target database already contains data. Re-run with "
                                     "'overwrite' to replace it, or pick an empty database.")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[wardenIQ][db-config] target inspection failed: {e!r}", flush=True)
        raise HTTPException(400, "Couldn't inspect the target database — check the "
                                 "connection string, credentials and network access "
                                 "(details in the server logs)")
    jid = launch_job("migrate", {"target_uri": uri, "overwrite": bool(body.overwrite)},
                     label="Migrate data to a new database")
    _audit(request, "db.migrate.started", detail="migration to a new MongoDB started")
    return {"job_id": jid}


@app.post("/api/users/{uid}/resend-invite")
def resend_invite(uid: str, request: Request):
    """Re-issue and re-deliver the invitation LINK for a user (e.g. after SMTP was
    fixed, or the link expired). Admin-only. Reports delivery honestly."""
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    if not target.get("active"):
        raise HTTPException(400, "user is disabled — enable them before resending")
    me = _current_user(request)
    (mode, detail), token = _issue_invite_link(
        target, request, inviter_name=(me.get("name") or me.get("email")) if me else "")
    resp = {"user": _user_public(store.get_user(uid)), "delivery": mode}
    if mode == "sent":
        resp["message"] = f"Invitation link re-sent to {target['email']}."
    elif mode == "refused":
        resp["message"] = "Could not send: SMTP is not configured."
    else:
        resp["message"] = "Email failed to send. Check the SMTP configuration."
    return resp


class InviteVerifyIn(BaseModel):
    token: str


@app.get("/api/invite/verify")
def verify_invite(token: str):
    """Public: resolve an invite token to its invite view (who/role/workspace) + the
    invited email, so the /invite landing page can prompt the right login. Does NOT
    consume the token. Returns 404 for unknown/expired tokens (no enumeration)."""
    u = store.get_user_by_invite_token(token)
    if not u or u.get("invite_status") != "pending":
        raise HTTPException(404, "this invitation link is invalid or has expired")
    inviter = None
    try:
        inviter = store.invite_inviter_info(u["id"])
    except Exception:  # noqa: BLE001
        inviter = None
    return {"email": u["email"], "invite": {
        "pending": True, "role": u.get("role", "viewer"),
        "invited_at": u.get("invited_at"), "invited_by": inviter,
        "workspace": APP_WORKSPACE_NAME}}


@app.post("/api/users/{uid}/cancel-invite")
def cancel_invite(uid: str):
    """Cancel a still-pending invite by deleting the user record. Only valid while
    the invite is pending (the user has never signed in). Admin-only."""
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    if target.get("invite_status") != "pending":
        raise HTTPException(400, "this user has already accepted — use disable/delete instead")
    # Invalidate any outstanding code, then remove the pending record.
    store.clear_otp(uid)
    store.delete_user(uid)
    return {"cancelled": uid}


@app.post("/api/smtp/test")
def smtp_test(body: OtpRequestIn):
    cfg = _smtp_cfg()
    if not cfg:
        raise HTTPException(400, "SMTP is not configured — add email settings to send sign-in codes")
    ok, err = email_send.send_otp(cfg, (body.email or "").strip(), auth.gen_otp())
    if not ok:
        print(f"[wardenIQ][smtp-test] send failed: {err}", flush=True)
        raise HTTPException(502, "could not send the test email — check the SMTP host, "
                                 "port, credentials and TLS/SSL settings")
    return {"ok": True, "sent_to": body.email}


def _svc_error(prefix, e, code=500):
    """Log an internal exception server-side and return a generic HTTPException.
    Prevents raw stack/exception text (which can reveal internals) reaching clients."""
    if isinstance(e, HTTPException):
        return e   # already a clean, intentional status/message — pass through
    print(f"[wardenIQ][{prefix}] {e!r}", flush=True)
    return HTTPException(code, f"{prefix} failed — please try again or check the logs")


def _ext_error(prefix, e):
    """Map an external-service exception to a clean, user-facing HTTPException (no raw
    httpx URLs / MDN links reaching the UI)."""
    import httpx as _hx
    if isinstance(e, _hx.HTTPStatusError):
        sc = e.response.status_code
        table = {
            400: (400, "the request was rejected — check the link or id"),
            401: (400, "authentication failed — check the token in Configuration"),
            403: (403, "access denied — the token lacks permission for this resource"),
            404: (404, "not found — check the link is correct and the token can access it"),
            429: (429, "rate limited — please try again shortly"),
        }
        code, msg = table.get(sc, (502, f"service returned HTTP {sc}"))
    elif isinstance(e, _hx.RequestError):
        code, msg = 502, "could not reach the service (network or timeout)"
    else:
        # Never reflect a raw exception (may carry internal URLs, hostnames, provider
        # errors, or credential hints). Log the detail server-side; return a safe message.
        print(f"[wardenIQ][ext-error] {prefix}: {e!r}", flush=True)
        code, msg = 502, "the request failed unexpectedly — see server logs for details"
    return HTTPException(code, f"{prefix}: {msg}")


def jira_client():
    s = store.get_settings()
    return jira.Jira(s.get("jira_base_url", ""), s.get("jira_email", ""),
                     crypto.decrypt(s.get("jira_api_token_enc", "")))


def figma_client():
    s = store.get_settings()
    return figma.Figma(crypto.decrypt(s.get("figma_api_token_enc", "")))


@app.post("/api/jira/test")
def jira_test():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured (base URL, email, API token)")
    try:
        me = j.myself()
        return {"ok": True, "user": me.get("displayName") or me.get("emailAddress")}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


@app.post("/api/features/{fid}/jira-sync")
def jira_sync(fid: str):
    """Write the feature's current coverage + open PRs back to its Jira issue."""
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    key = f.get("key")
    if not key:
        raise HTTPException(400, "feature has no Jira key (set a ticket key on the feature)")
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured")
    cov_rep = store.feature_coverage_report(fid)
    open_prs = [p for p in store.list_prs(feature_id=fid) if p.get("state") == "open"]
    lines = [
        f"*wardenIQ* — feature *{f.get('name')}* (v{f.get('version', 1)})",
        f"Test cases: {cov_rep['total_test_cases']} · code coverage: {cov_rep['coverage_pct']}% "
        f"· automation: {cov_rep['dev_test_pct']}%",
        f"PRs mapped: {cov_rep['pr_count']} across {cov_rep['repos_touched']} repo(s); "
        f"{len(open_prs)} still open.",
    ]
    for p in open_prs[:10]:
        lines.append(f"- open PR #{p.get('number')} ({p.get('repo_full_name')}): {p.get('url')}")
    try:
        j.add_comment(key, "\n".join(lines))
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)
    return {"ok": True, "issue": key}


# --------------------------------------------------------------- CRUD: projects/features/cases/steps/repos
class RenameIn(BaseModel):
    name: str | None = None
    key: str | None = None


class ProjectPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    key: str | None = None
    jira_project_key: str | None = None
    jira_project_name: str | None = None
    confluence_space_key: str | None = None
    confluence_space_name: str | None = None
    default_git_provider: str | None = None  # 'github' | 'gitlab'


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: ProjectPatchIn):
    fields = {}
    if body.name is not None:
        store.rename_project(pid, body.name.strip())
    for f in ("description", "key", "jira_project_key", "jira_project_name",
              "confluence_space_key", "confluence_space_name"):
        v = getattr(body, f)
        if v is not None:
            fields[f] = v.strip() if isinstance(v, str) else v
    jkey = fields.get("jira_project_key")
    if jkey and store.jira_project_in_use(jkey, exclude_pid=pid):
        raise HTTPException(409, f"Jira project '{jkey}' is already linked to another project")
    if body.default_git_provider is not None:
        p = body.default_git_provider.strip().lower()
        if p not in ("github", "gitlab"):
            raise HTTPException(400, "default_git_provider must be 'github' or 'gitlab'")
        fields["default_git_provider"] = p
    if fields:
        store.update_project(pid, fields)
    return {"ok": True, "project": _project_public(store.get_project(pid))}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, request: Request):
    proj = store.get_project(pid)
    result = store.delete_project(pid)
    if not result:
        raise HTTPException(404, "project not found")
    _audit(request, "project.deleted", target=pid,
           old={"name": (proj or {}).get("name")})
    return result


@app.patch("/api/features/{fid}")
def rename_feature(fid: str, body: RenameIn):
    if body.key is not None and (body.key or "").strip():
        f = store.get_feature(fid)
        if not f:
            raise HTTPException(404, "feature not found")
        ek = body.key.strip()
        if store.epic_bound_group(f["project_id"], ek,
                                  exclude_group_id=f.get("group_id", fid)):
            raise HTTPException(409, f"Epic '{ek}' is already associated with another feature")
    store.rename_feature(fid, body.name, body.key)
    return {"ok": True}


@app.delete("/api/features/{fid}")
def delete_feature(fid: str):
    result = store.delete_feature(fid)
    if not result:
        raise HTTPException(404, "feature not found")
    return result


class NewCaseIn(BaseModel):
    feature_id: str
    title: str
    type: str = "functional"
    priority: str = "P2"
    preconditions: str = ""
    tags: list[str] = []
    steps: list[dict] = []


@app.post("/api/test-cases")
def create_test_case(body: NewCaseIn, request: Request):
    _require_feature_project(request, body.feature_id)   # scope to the case's feature
    step_ids = []
    for s in body.steps:
        a = (s.get("action") or "").strip(); e = (s.get("expected") or "").strip()
        if not (a or e):
            continue
        emb = embedder.embed(f"{a}. Expected: {e}")
        step_ids.append(store.get_or_create_step(a, e, emb, STEP_AUTO)["step_id"])
    cemb = embedder.embed(body.title + " " + " ".join(
        f"{s.get('action','')} {s.get('expected','')}" for s in body.steps))
    cid = store.create_case(body.title, body.type, body.priority, body.preconditions,
                            step_ids, body.tags, cemb, body.feature_id)
    store.associate(body.feature_id, cid, "manual", None)
    created = store.get_case(cid) or {}
    return {"id": cid, "display_id": created.get("display_id")}


@app.delete("/api/test-cases/{cid}")
def delete_test_case(cid: str, request: Request, force: bool = False):
    _require_case_project(request, cid)
    result = store.delete_case(cid, force)
    if result.get("requires_force"):
        raise HTTPException(409, detail=result)
    return result


@app.delete("/api/features/{fid}/test-cases/{cid}")
def unlink_test_case_from_feature(fid: str, cid: str):
    result = store.unlink_case_from_feature(fid, cid)
    if not result.get("removed"):
        raise HTTPException(404, result.get("reason", "association not found"))
    return result


class NewStepIn(BaseModel):
    action: str
    expected: str


@app.post("/api/steps")
def create_step(body: NewStepIn):
    emb = embedder.embed(f"{body.action}. Expected: {body.expected}")
    return {"id": store.create_step(body.action, body.expected, emb)}


@app.delete("/api/steps/{sid}")
def delete_step(sid: str):
    return store.delete_step(sid)


@app.delete("/api/repos/{rid}")
def delete_repo(rid: str):
    repo = store.get_repo(rid)
    if repo and repo.get("repo_type") == "app" and repo.get("webhook_id"):
        provider = (repo.get("git_provider") or "github").lower()
        pid = repo.get("project_id")
        try:
            if provider == "gitlab":
                token = project_gitlab_token(pid)
                if token:
                    gitlab_mod.GitLab(token).delete_webhook(repo["full_name"], repo["webhook_id"])
            else:
                token = project_github_token(pid)
                if token:
                    github.GitHub(token, GITHUB_API).delete_webhook(
                        repo["owner"], repo["name"], repo["webhook_id"])
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] delete failed (continuing): {e}", flush=True)
    return store.delete_repo(rid)


# --------------------------------------------------------------- code analysis + test cycles
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.responses import Response

def _project_case_briefs(pid, limit=80):
    res = store.list_test_cases(project_id=pid, limit=limit)
    return store.cases_brief([i["id"] for i in res["items"]])


def _commit_change_summary(commits, max_chars=8000):
    """Structured per-commit summary for the LLM tier — keeps commit boundaries intact
    (the old build's flat-merge lost these, so matches couldn't be tied to a commit)."""
    parts = []
    for c in commits:
        head = f"COMMIT {c.get('short', '')} [{c.get('repo', '')}] {c.get('message', '')}"
        body = [f"  {f['filename']} ({f.get('status', '')}, "
                f"+{f.get('additions', 0)}/-{f.get('deletions', 0)})\n{(f.get('patch') or '')[:800]}"
                for f in (c.get("files") or [])[:8]]
        parts.append(head + "\n" + "\n".join(body))
    return "\n\n".join(parts)[:max_chars]


def _analyze_worker(jid, params):
    """Grounded impact / commit analysis.

    For each commit we extract endpoints + symbols (with file:line evidence) and match them
    to test cases by tier (endpoint-exact > endpoint-path > guarded-symbol). Cases not matched
    by grounded signals get a bounded LLM pass over a *per-commit* summary. Every impacted case
    carries a verdict, confidence/tier and the exact commit/file/line proof.
    """
    days = params["days"]
    repo_ids = params.get("repo_ids") or []
    branches = params.get("branches") or {}          # {repo_id: branch}
    project_id = params["project_id"]
    feature_id = params.get("feature_id")
    docs = _implementation_repo_docs(project_id, repo_ids)
    repos = [{**r, "id": str(r["_id"])} for r in docs]
    if not repos:
        store.merge_job_result(
            jid,
            impacted=[],
            results=[],
            grounded=0,
            ai=0,
            note="no implementation repos selected — test repos are only used for automation coverage",
        )
        return
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    commits, per_repo, errors, changed = [], [], [], set()
    for repo in repos:
        provider = (repo.get("git_provider") or "github").lower()
        ref = (branches.get(repo["id"]) or "").strip() or repo.get("default_branch", "")
        store.update_job(jid, stage=f"fetching {provider} commits — {repo['full_name']}@{ref or 'default'}")
        try:
            raw = _repo_list_commits(repo, since, ref=ref)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{repo['full_name']}@{ref}: {e}"); raw = []
        per_repo.append({"repo": repo["full_name"], "branch": ref or "default", "commits": len(raw), "git_provider": provider})
        for c in raw[:40]:
            sha = c.get("sha") or ""
            try:
                files = _repo_get_commit(repo, sha)
            except Exception:  # noqa: BLE001
                files = []
            for f in files:
                changed.add(f"{repo['full_name']}:{f['filename']}")
            commits.append({
                "repo": repo["full_name"], "sha": sha, "short": sha[:7],
                "url": c.get("html_url"),
                "message": ((c.get("commit", {}).get("message") or "").splitlines() or [""])[0][:90],
                "files": files})
    store.merge_job_result(jid, commit_count=sum(p["commits"] for p in per_repo),
                           per_repo=per_repo,
                           commits=[{"repo": c["repo"], "sha": c["short"], "url": c["url"],
                                     "message": c["message"]} for c in commits][:60],
                           changed_files=sorted(changed), errors=errors)
    if not commits:
        store.merge_job_result(jid, impacted=[], results=[], grounded=0, ai=0,
                               note="no changes in window")
        return

    cases = (store.cases_brief(store.feature_test_case_ids(feature_id)) if feature_id
             else _project_case_briefs(project_id))
    by_id = {c["id"]: c for c in cases}

    # 1) grounded tiers (no LLM) — exact, evidence-backed
    store.update_job(jid, stage="grounded matching (endpoints + symbols)")
    gm = grounding.match_commit_changes(commits, cases)
    results = []
    for cid, m in gm["matches"].items():
        c = by_id[cid]
        results.append({"case_id": cid, "display_id": c.get("display_id"),
                        "title": c["title"], "type": c["type"], "steps": c.get("steps"),
                        "status": m["status"], "tier": m["tier"], "confidence": m["confidence"],
                        "signal": m["signal"], "signal_type": m["signal_type"],
                        "risk": m["risk"], "reason": m["reason"], "evidence": m["evidence"]})

    # 2) LLM tier on the remainder only (semantic impacts) -> review_needed
    remaining = [c for c in cases if c["id"] not in gm["matched_ids"]]
    ai_count = 0
    if remaining:
        store.update_job(jid, stage=f"LLM impact analysis ({len(remaining)} remaining cases)")
        res = cov.analyze_impact(current_llm(), _commit_change_summary(commits), remaining)
        for x in res.get("impacted", []):
            cid = x.get("test_case_id")
            if cid in by_id and cid not in gm["matched_ids"]:
                c = by_id[cid]
                results.append({"case_id": cid, "display_id": c.get("display_id"),
                                "title": c["title"], "type": c["type"], "steps": c.get("steps"),
                                "status": "review_needed", "tier": 5, "confidence": None,
                                "signal": None, "signal_type": "ai",
                                "risk": x.get("risk", "medium"),
                                "reason": x.get("reason", ""), "evidence": []})
                ai_count += 1

    results.sort(key=lambda r: (r.get("tier") or 9))
    compact = [{"repo": c["repo"], "sha": c["short"], "url": c["url"], "message": c["message"]}
               for c in commits]
    run_id = store.save_commit_analysis(
        project_id, feature_id,
        {"days": days, "repo_ids": repo_ids, "branches": branches}, compact, results)
    # `impacted` kept for the existing cycle-builder/UI; now enriched with evidence
    store.merge_job_result(jid, run_id=run_id, impacted=results, results=results,
                           grounded=len(gm["matches"]), ai=ai_count)


JOB_WORKERS["analyze"] = _analyze_worker


# ---- deep code analysis + cross-repo mind map -------------------------------
def _codeanalysis_worker(jid, params):
    """External-reviewer pass: read the ACTUAL repo code, embed it, and map every
    active feature's test cases to covered / partial / uncovered against the code."""
    project_id = params["project_id"]
    repo_ids = params.get("repo_ids") or []
    branches = params.get("branches") or {}          # {repo_id: branch}
    branch_override = (params.get("branch") or "").strip()   # legacy global fallback
    docs = _implementation_repo_docs(project_id, repo_ids)
    repos = [{**r, "id": str(r["_id"])} for r in docs]
    if not repos:
        raise RuntimeError("no implementation repos selected — test repos are only used for automation coverage")
    mem = []          # in-memory [(repo_full, path, text, embedding)] for cosine retrieval
    total, tests_skipped, errors, per_repo = 0, 0, [], []
    for repo in repos:
        provider = (repo.get("git_provider") or "github").lower()
        ref = (branches.get(repo["id"]) or "").strip() or branch_override \
            or repo.get("default_branch", "")
        # Incremental reuse: if the branch head hasn't changed since we last indexed this
        # repo, reuse the stored chunks instead of re-fetching the tarball + re-embedding.
        try:
            head = _repo_branch_sha(repo, ref) if ref else None
        except Exception:  # noqa: BLE001
            head = None
        meta = store.get_code_index(repo["id"])
        if head and meta and meta.get("sha") == head and \
                store.code_chunks.count_documents({"repo_id": repo["id"]}) > 0:
            store.update_job(jid, stage=f"reusing index — {repo['full_name']}@{ref} (unchanged)")
            paths = set()
            for d in store.code_chunks_for_repo(repo["id"]):
                mem.append((d["repo"], d["path"], d["text"], d["embedding"]))
                paths.add(d["path"]); total += 1
            per_repo.append({"repo": repo["full_name"], "branch": ref or "default",
                             "impl_files": len(paths), "reused": True, "git_provider": provider})
            print(f"[wardenIQ][mindmap] {repo['full_name']}@{ref}: reused index "
                  f"({len(paths)} impl files, head {head[:7]})", flush=True)
            continue
        store.update_job(jid, stage=f"fetching {provider} code — {repo['full_name']}@{ref or 'default'}")
        try:
            data = _repo_get_archive(repo, ref)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{repo['full_name']}@{ref}: {e}")
            per_repo.append({"repo": repo["full_name"], "branch": ref, "error": str(e)[:200]})
            continue
        files, stats = extractmod.source_files_from_tar(data, return_stats=True)
        store.clear_code_chunks(repo["id"])
        batch = []
        repo_paths, repo_tests, repo_chunks = [], 0, 0
        for path, text in files:
            # Mind Map judges IMPLEMENTATION coverage only. Test/spec files are
            # excluded — whether an automated test exists is tracked separately.
            if cov.is_test_file(path):
                tests_skipped += 1; repo_tests += 1
                continue
            repo_paths.append(path)
            for i, ch in enumerate(grounding.chunk_code_by_function(text, path)):
                emb = embedder.embed(ch)
                mem.append((repo["full_name"], path, ch, emb))
                batch.append({"project_id": project_id, "repo_id": repo["id"],
                              "repo": repo["full_name"], "path": path, "chunk_index": i,
                              "text": ch, "embedding": emb})
                total += 1; repo_chunks += 1
                if len(batch) >= 100:
                    store.add_code_chunks(batch); batch = []
        if batch:
            store.add_code_chunks(batch)
        if head:
            store.set_code_index(repo["id"], head, repo_chunks, len(repo_paths))
        per_repo.append({"repo": repo["full_name"], "branch": ref or "default",
                         "git_provider": provider,
                         "files_in_repo": stats["total_files"], "code_matched": len(files),
                         "impl_files": len(repo_paths), "test_files": repo_tests,
                         "extensions": stats["top_ext"],
                         "impl_sample": repo_paths[:40],
                         "sample": stats["sample"] if not files else []})
        print(f"[wardenIQ][mindmap] {repo['full_name']}@{ref or 'default'}: "
              f"{len(repo_paths)} impl files, {repo_tests} tests skipped, "
              f"{stats['total_files']} total. files={repo_paths[:60]}", flush=True)
        store.update_job(jid, stage=f"indexed {repo['full_name']} — {len(repo_paths)} impl files, "
                                     f"{repo_tests} tests skipped ({stats['total_files']} total)")
    store.merge_job_result(jid, code_chunks=total, tests_skipped=tests_skipped,
                           repos=[r["full_name"] for r in repos], errors=errors,
                           per_repo=per_repo)
    if not mem:
        note = ("only test/spec files found — connect the implementation repo(s) to "
                "measure code coverage" if tests_skipped else
                "no recognized source files found — see per-repo diagnostics below")
        store.merge_job_result(jid, features_mapped=0, note=note)
        return
    feats = store.list_features(project_id)
    lm = current_llm()
    repo_names = [r["full_name"] for r in repos]
    mapped = 0

    def likely_impl_path(path: str) -> bool:
        p = (path or "").lower()
        noisy_parts = (
            "/load-test/", "/loadtest/", "/benchmark/", "/bench/", "/perf/", "/performance/",
            "/storybook/", "/fixtures/", "/fixture/", "/mocks/", "/mock/", "/examples/",
            "/sample/", "/samples/", "/docs/", "/doc/", "/prisma/migrations/", "/migrations/",
            "/seed/", "/seeds/",
        )
        noisy_suffixes = (".snap", ".md", ".txt", ".sql")
        if any(part in p for part in noisy_parts):
            return False
        if p.endswith(noisy_suffixes):
            return False
        return True

    def impl_path_score(path: str, kws: list[str]) -> int:
        """Language-agnostic implementation-file scoring.

        The goal is not to guess a framework, but to prefer likely source files over
        docs, fixtures, migrations, examples, load scripts, and other low-signal paths.
        """
        p = (path or "").lower().strip("/")
        score = 0
        segs = p.split("/") if p else []
        base = segs[-1] if segs else p

        preferred_dirs = {
            "src", "app", "lib", "core", "pkg", "internal", "cmd", "server", "api",
            "services", "service", "handlers", "handler", "controllers", "controller",
            "routes", "router", "models", "domain", "modules", "features", "components",
            "views", "pages",
        }
        de_emphasize_dirs = {
            "docs", "doc", "examples", "example", "samples", "sample", "fixtures", "fixture",
            "mocks", "mock", "bench", "benchmark", "perf", "performance", "scripts",
            "seed", "seeds", "migration", "migrations",
        }
        config_names = {
            "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "cargo.lock",
            "composer.lock", "poetry.lock", "pipfile.lock", "dockerfile", "makefile",
            "tsconfig.json", "vite.config.ts", "vite.config.js", "webpack.config.js",
        }

        for seg in segs:
            if seg in preferred_dirs:
                score += 3
            if seg in de_emphasize_dirs:
                score -= 4
        if base in config_names:
            score -= 5
        if base.startswith("index.") or base.startswith("main.") or base.startswith("server."):
            score += 2
        if base.endswith((".controller.ts", ".service.ts", ".route.ts", ".router.ts",
                          ".view.tsx", ".page.tsx", ".component.tsx")):
            score += 2
        score += sum(2 for k in kws if k and k in p)
        return score

    for f in feats:
        fid = f["id"]
        cids = store.feature_test_case_ids(fid)
        if not cids:
            continue
        cases = store.cases_brief(cids)
        store.update_job(jid, stage=f"reviewing — {f['name']}")
        full = store.get_feature(fid) or {}
        # Hybrid retrieval: BM25 (lexical — exact endpoint/identifier hits) fused with cosine
        # (semantic) via RRF over the in-memory code index. The query includes the requirement,
        # every test-case title, AND the endpoints the cases reference, so API cases retrieve the
        # right routes. Chunks are whole function/route bodies (tree-sitter), so the reviewer sees
        # complete implementations rather than arbitrary windows.
        case_titles = [c.get("title", "") for c in cases]
        eps = [ep["path"] for c in cases for ep in grounding.case_endpoints(c) if ep.get("path")]
        query_text = " ".join([full.get("text") or f["name"]] + case_titles + eps)[:3500]
        q = embedder.embed(query_text[:3000], task="query")
        pool = [(r, p, t, e) for (r, p, t, e) in mem if likely_impl_path(p)] or list(mem)
        texts = [f"{p} {t}" for (r, p, t, e) in pool]      # path + code = lexical document
        vecs = [e for (r, p, t, e) in pool]
        order = grounding.hybrid_rank_indices(query_text, texts, q, vecs, top_k=min(len(pool), 24))
        chosen, per_file = [], {}
        for i in order:
            r, p, t, e = pool[i]
            if per_file.get((r, p), 0) >= 2:      # ≤2 chunks per file, keep breadth
                continue
            per_file[(r, p)] = per_file.get((r, p), 0) + 1
            chosen.append((r, p, t, e))
            if len(chosen) >= 20:
                break
        excerpts = [{"repo": r, "path": p, "text": t} for (r, p, t, _e) in chosen]
        reviewed_files = sorted({f"{r}:{p}" for (r, p, _t, _e) in chosen})
        res = cov.review_code_coverage(lm, f["name"], full.get("text", ""), cases, excerpts)
        res["reviewed_files"] = reviewed_files
        store.save_code_coverage(fid, project_id, res, repo_names)
        print(f"[wardenIQ][mindmap] feature '{f['name']}': reviewed {len(reviewed_files)} "
              f"implementation files (hybrid retrieval); files={reviewed_files}", flush=True)
        mapped += 1
        store.merge_job_result(jid, features_mapped=mapped)
    store.merge_job_result(jid, features_mapped=mapped)


JOB_WORKERS["codeanalysis"] = _codeanalysis_worker


class CodeAnalyzeIn(BaseModel):
    project_id: str
    repo_ids: list[str] = []          # empty → all repos in the project
    branches: dict[str, str] = {}     # {repo_id: branch}; missing → repo's default
    branch: str = ""                  # legacy global override (applied if no per-repo branch)


@app.post("/api/code-analysis")
def code_analysis(body: CodeAnalyzeIn, request: Request):
    _require_project(request, body.project_id)
    repos = _implementation_repo_docs(body.project_id, body.repo_ids)
    if not repos:
        raise HTTPException(404, "no implementation repos to analyze")
    jid = launch_job("codeanalysis", {"project_id": body.project_id, "repo_ids": body.repo_ids,
                                      "branches": body.branches, "branch": body.branch.strip()},
                     label=f"Mind Map — {len(repos)} repo(s)",
                     project_id=body.project_id)
    return {"job_id": jid}


@app.get("/api/features/{fid}/code-coverage")
def feature_code_coverage(fid: str):
    return store.get_code_coverage(fid) or {"feature_id": fid, "result": {"cases": []},
                                            "repos": [], "analyzed": False}


@app.get("/api/projects/{pid}/mindmap")
def project_mindmap(pid: str):
    out = []
    for f in store.list_features(pid):
        cc = store.get_code_coverage(f["id"])
        cases = (cc or {}).get("result", {}).get("cases", [])
        counts = {"covered": 0, "partial": 0, "uncovered": 0}
        for c in cases:
            counts[c.get("status", "uncovered")] = counts.get(c.get("status", "uncovered"), 0) + 1
        out.append({"feature": f["name"], "feature_id": f["id"], "version": f.get("version", 1),
                    "case_count": f.get("case_count", len(cases)), "counts": counts,
                    "cases": cases, "repos": (cc or {}).get("repos", []),
                    "reviewed_files": (cc or {}).get("result", {}).get("reviewed_files", []),
                    "analyzed": bool(cc), "updated_at": (cc or {}).get("updated_at")})
    return {"project_id": pid, "features": out}


class AnalyzeIn(BaseModel):
    project_id: str
    repo_ids: list[str] = []          # empty → all repos in the project
    branches: dict[str, str] = {}     # {repo_id: branch}; missing → repo's default
    days: int = 14
    feature_id: str | None = None     # optional: scope impact to one feature's cases


@app.post("/api/analyze")
def analyze(body: AnalyzeIn, request: Request):
    _require_project(request, body.project_id)
    repos = _implementation_repo_docs(body.project_id, body.repo_ids)
    if not repos:
        raise HTTPException(404, "no implementation repos to analyze")
    jid = launch_job("analyze", {"project_id": body.project_id, "repo_ids": body.repo_ids,
                                 "branches": body.branches, "days": body.days,
                                 "feature_id": body.feature_id},
                     label=f"Change impact analysis — {len(repos)} repo(s), {body.days}d",
                     project_id=body.project_id)
    return {"job_id": jid}


@app.get("/api/commit-analysis/{run_id}")
def get_commit_analysis(run_id: str, request: Request):
    return _require_commit_analysis_project(request, run_id)


@app.get("/api/projects/{pid}/commit-analysis/latest")
def latest_commit_analysis(pid: str, feature_id: str | None = None):
    return store.latest_commit_analysis(pid, feature_id) or {"results": [], "commits": []}


class AnalyzePRIn(BaseModel):
    repo_id: str
    number: int


@app.post("/api/analyze-pr")
def analyze_pr(body: AnalyzePRIn):
    """Fetch a specific PR, map it to a feature, review which test cases it covers."""
    repo = store.repos.find_one({"_id": _oid(body.repo_id)})
    if not repo:
        raise HTTPException(404, "repo not found")
    if not _is_app_repo(repo):
        raise HTTPException(400, "PR coverage only applies to implementation repos; test repos are used for automation coverage")
    repo = {**repo, "id": str(repo["_id"])}
    try:
        pr, files, _sha = _fetch_pr_and_files(repo, body.number)
        pr["_files"] = files
    except Exception as e:  # noqa: BLE001
        provider = (repo.get("git_provider") or "github").lower()
        raise _ext_error(provider, e)
    pr_id = ingest_pr(repo, pr)                 # stores PR + mapping + coverage
    pdoc = store.prs.find_one({"_id": _oid(pr_id)})
    fid = pdoc.get("feature_id") if pdoc else None
    feature = store.get_feature(fid) if fid else None
    covdoc = store.coverage.find_one({"pr_id": pr_id}) or {}
    covered = []
    for c in covdoc.get("covered", []):
        case = store.cases.find_one({"_id": _oid(c["test_case_id"])}, {"title": 1, "type": 1})
        if case:
            covered.append({"title": case.get("title"), "type": case.get("type"),
                            "status": c.get("status", "covered"), "tier": c.get("tier"),
                            "confidence": c.get("confidence"), "signal_type": c.get("signal_type"),
                            "signal": c.get("signal"), "evidence": c.get("evidence", []),
                            "rationale": c.get("rationale", ""), "by_dev_test": c.get("by_dev_test")})
    return {"pr": {"number": pdoc.get("number"), "title": pdoc.get("title"), "url": pdoc.get("url"),
                   "repo": repo["full_name"]},
            "feature": {"id": fid, "name": feature.get("name") if feature else None,
                        "mapping": pdoc.get("mapping_method")},
            "notice": covdoc.get("notice", ""),
            "dev_test_files": covdoc.get("dev_test_files", []),
            "covered": covered}


class AssignPRIn(BaseModel):
    feature_id: str


@app.get("/api/projects/{pid}/unmapped-prs")
def unmapped_prs(pid: str):
    return {"prs": store.list_unmapped_prs(pid)}


@app.post("/api/prs/{pr_id}/assign")
def assign_pr(pr_id: str, body: AssignPRIn):
    """Manually map an unmatched PR to a feature, then compute its coverage in the background.

    Mapping is persisted immediately (so the PR leaves the unmapped queue at once); the coverage
    pass — which may call the LLM and take a while — runs in a daemon thread so the UI stays snappy.
    """
    p = store.prs.find_one({"_id": _oid(pr_id)})
    if not p:
        raise HTTPException(404, "PR not found")
    store.set_pr_mapping(pr_id, body.feature_id, 1.0, "manual")
    repo = store.repos.find_one({"_id": _oid(p["repo_id"])}) if p.get("repo_id") else None
    pdoc = {**p, "id": pr_id}

    def _bg():
        files = []
        if repo:
            try:
                provider = (repo.get("git_provider") or "github").lower()
                if provider == "gitlab":
                    _, files, _ = _fetch_pr_and_files({**repo, "id": str(repo["_id"])}, p["number"])
                else:
                    files = gh_client().get_pull_files(repo["owner"], repo["name"], p["number"])
            except Exception:  # noqa: BLE001
                files = []
        try:
            _pr_coverage(pr_id, pdoc, files, body.feature_id)
        except Exception as e:  # noqa: BLE001
            print(f"[wardenIQ][assign] coverage failed for PR {pr_id}: {e}", flush=True)

    threading.Thread(target=_bg, daemon=True).start()
    return {"ok": True, "feature_id": body.feature_id, "status": "computing"}




class CycleIn(BaseModel):
    project_id: str
    name: str
    case_ids: list[str] = []
    source: dict = {}
    description: str = ""
    environment: str = ""
    build_version: str = ""
    assigned_to: str | None = None
    scheduled_start_at: str | None = None
    scheduled_end_at: str | None = None


@app.post("/api/test-cycles")
def create_cycle(body: CycleIn, request: Request):
    user = _current_user(request)
    _require_project(request, body.project_id)
    try:
        cid = store.create_cycle(
            body.project_id, body.name, body.case_ids, body.source,
            description=body.description, environment=body.environment,
            build_version=body.build_version, assigned_to=body.assigned_to,
            scheduled_start_at=body.scheduled_start_at,
            scheduled_end_at=body.scheduled_end_at,
            created_by=(user or {}).get("email"),
        )
        return {"id": cid}
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:  # noqa: BLE001
        from pymongo.errors import DuplicateKeyError
        if isinstance(exc, DuplicateKeyError):
            raise HTTPException(409, "A test cycle with that name already exists in this project — pick a different name")
        raise


@app.get("/api/projects/{pid}/test-cycles")
def list_cycles(pid: str, status: str | None = None):
    return {"cycles": store.list_cycles(pid, status)}


@app.get("/api/test-cycles/{cid}")
def get_cycle(cid: str):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    return c


class CycleStatusIn(BaseModel):
    case_id: str | None = None
    item_id: str | None = None
    status: str
    actual_result: str = ""
    defect_link: str = ""
    notes: str = ""


@app.patch("/api/test-cycles/{cid}/items")
def set_cycle_status(cid: str, body: CycleStatusIn, request: Request):
    user = _current_user(request)
    try:
        item = store.set_cycle_item_status(
            cid, body.item_id or body.case_id or "", body.status,
            body.actual_result, body.defect_link, body.notes,
            executed_by=(user or {}).get("email"),
        )
        return {"ok": True, "item": item, "cycle": store.get_cycle(cid)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/test-cycles/{cid}")
def update_cycle(cid: str, body: dict, request: Request):
    from pymongo.errors import DuplicateKeyError
    user = _current_user(request)
    try:
        return store.update_cycle(cid, body or {}, performed_by=(user or {}).get("email"))
    except DuplicateKeyError:
        raise HTTPException(409, "A test cycle with that name already exists in this project — pick a different name")


@app.post("/api/test-cycles/{cid}/items")
def add_cycle_items(cid: str, body: dict, request: Request):
    user = _current_user(request)
    count = store.add_cycle_items(
        cid, (body or {}).get("case_ids") or [],
        performed_by=(user or {}).get("email"),
    )
    return {"added": count, "cycle": store.get_cycle(cid)}


@app.post("/api/test-cycles/{cid}/items/batch-status")
def batch_cycle_status(cid: str, body: dict, request: Request):
    user = _current_user(request)
    try:
        return store.batch_cycle_item_status(
            cid, (body or {}).get("item_ids") or [], (body or {}).get("status") or "",
            executed_by=(user or {}).get("email"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/test-cycles/{cid}/items/{item_id}")
def remove_cycle_item(cid: str, item_id: str, request: Request):
    user = _current_user(request)
    store.remove_cycle_item(cid, item_id, performed_by=(user or {}).get("email"))
    return {"ok": True}


@app.get("/api/test-cycles/{cid}/activity")
def cycle_activity(cid: str):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    return {"activity": list(reversed(c.get("activity", [])))}


@app.get("/api/test-cycles/{cid}/report")
def cycle_report(cid: str):
    report_data = store.cycle_report(cid)
    if not report_data:
        raise HTTPException(404, "cycle not found")
    return report_data


@app.get("/api/test-cycles/{cid}/export/csv")
def cycle_export_csv(cid: str):
    from fastapi.responses import Response
    content = store.cycle_csv(cid)
    if content is None:
        raise HTTPException(404, "cycle not found")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="test-cycle-{cid}.csv"'},
    )


@app.get("/api/test-cycles/{cid}/export/pdf")
def export_cycle_pdf(cid: str):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    import report
    pdf = report.build_cycle_pdf(c)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="test-cycle-{cid}.pdf"'})


@app.delete("/api/test-cycles/{cid}")
def del_cycle(cid: str):
    return store.delete_cycle(cid)


class TemplateIn(BaseModel):
    name: str


@app.post("/api/test-cycles/{cid}/save-template")
def save_cycle_template(cid: str, body: TemplateIn):
    tid = store.save_cycle_as_template(cid, body.name)
    if not tid:
        raise HTTPException(404, "cycle not found")
    return {"id": tid}


@app.get("/api/projects/{pid}/cycle-templates")
def list_cycle_templates(pid: str):
    return {"templates": store.list_cycle_templates(pid)}


@app.post("/api/cycle-templates/{tid}/create-cycle")
def create_cycle_from_template(tid: str, body: TemplateIn, request: Request):
    from pymongo.errors import DuplicateKeyError
    user = _current_user(request)
    try:
        cid = store.create_cycle_from_template(tid, body.name, created_by=(user or {}).get("email"))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except DuplicateKeyError:
        raise HTTPException(409, "A test cycle with that name already exists in this project — pick a different name")
    if not cid:
        raise HTTPException(404, "template not found")
    return {"id": cid}


@app.delete("/api/cycle-templates/{tid}")
def delete_cycle_template(tid: str):
    return store.delete_cycle_template(tid)


@app.get("/api/features/{fid}/report.pdf")
def feature_report(fid: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    project = store.get_project(f.get("project_id")) if f.get("project_id") else None
    if project and project.get("name"):
        f["project_name"] = project["name"]
    cov_rep = store.feature_coverage_report(fid)
    cases = store.get_feature_cases(fid)
    prs = store.list_prs(feature_id=fid)
    pdf = report.build_feature_pdf(f, cov_rep, cases, prs)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="feature_{fid}.pdf"'})


def _selected_feature_cases(fid: str, selected_ids: list[str] | None = None):
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    project = store.get_project(f.get("project_id")) if f.get("project_id") else None
    if project and project.get("name"):
        f["project_name"] = project["name"]
    cases = store.get_feature_cases(fid)
    if selected_ids:
        wanted = {str(x) for x in selected_ids}
        cases = [c for c in cases if c.get("id") in wanted or c.get("display_id") in wanted]
    if not cases:
        raise HTTPException(400, "no test cases selected")
    return f, cases


@app.get("/api/features/{fid}/export/pdf")
def feature_export_pdf(fid: str):
    import report
    f, cases = _selected_feature_cases(fid)
    pdf = report.build_testcase_pdf(f, cases)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="test_cases_{fid}.pdf"'})


@app.post("/api/features/{fid}/export/pdf-selected")
def feature_export_selected_pdf(fid: str, body: dict):
    import report
    f, cases = _selected_feature_cases(fid, body.get("testCaseIds") or body.get("test_case_ids") or [])
    pdf = report.build_testcase_pdf(f, cases)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="selected_test_cases_{fid}.pdf"'})


@app.get("/api/features/{fid}/gap/pr-coverage/export/{fmt}")
def export_gap_pr_coverage(fid: str, fmt: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    runs = store.list_code_coverage_runs(feature_id=fid, limit=500)
    cases = store.cases_brief(store.feature_test_case_ids(fid))
    if fmt == "csv":
        return Response(content=report.build_gap_pr_csv(f, runs, cases), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="gap-pr-coverage-{fid}.csv"'})
    if fmt == "pdf":
        return Response(content=report.build_gap_pr_pdf(f, runs, cases), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="gap-pr-coverage-{fid}.pdf"'})
    raise HTTPException(400, "format must be csv or pdf")


@app.get("/api/features/{fid}/gap/automation/export/{fmt}")
def export_gap_automation(fid: str, fmt: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    snap = store.get_automation_coverage(fid, version=f.get("version", 1)) or {}
    if fmt == "csv":
        return Response(content=report.build_gap_automation_csv(f, snap), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="gap-automation-{fid}.csv"'})
    if fmt == "pdf":
        return Response(content=report.build_gap_automation_pdf(f, snap), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="gap-automation-{fid}.pdf"'})
    raise HTTPException(400, "format must be csv or pdf")


@app.get("/api/features/{fid}/export/csv")
def feature_export_csv(fid: str):
    import report
    f, cases = _selected_feature_cases(fid)
    csv_bytes = report.build_testcase_csv(f, cases)
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="test_cases_{fid}.csv"'})


@app.post("/api/features/{fid}/export/csv-selected")
def feature_export_selected_csv(fid: str, body: dict):
    import report
    f, cases = _selected_feature_cases(fid, body.get("testCaseIds") or body.get("test_case_ids") or [])
    csv_bytes = report.build_testcase_csv(f, cases)
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="selected_test_cases_{fid}.csv"'})


# --------------------------------------------------------------- Start Developing
def _develop_worker(jid, params):
    feature = store.get_feature(params["feature_id"])
    cases = store.get_feature_cases(params["feature_id"])
    if not feature or not cases:
        raise RuntimeError("feature has no test cases")
    repo = store.repos.find_one({"_id": _oid(params["repo_id"])})
    if not repo:
        raise RuntimeError("repo not found")
    owner, name = repo["owner"], repo["name"]
    base_branch, language = params["base_branch"], params["language"]
    fname = feature.get("name", "feature")
    store.update_job(jid, stage="generating implementation code")
    gen = cov.generate_feature_code(current_llm(), language, fname, feature.get("text", ""), cases)
    if gen.get("error") or not gen.get("files"):
        raise RuntimeError(gen.get("error", "no code generated"))
    files = gen["files"]
    store.merge_job_result(jid, files=[f["path"] for f in files], notes=gen.get("notes", ""))
    slug = re.sub(r"[^a-z0-9]+", "-", fname.lower()).strip("-")[:40] or "feature"
    branch = f"wardeniq/{slug}-v{feature.get('version', 1)}"
    store.update_job(jid, stage=f"creating branch {branch}")
    base_sha = gh_client().branch_sha(owner, name, base_branch)
    try:
        gh_client().create_branch(owner, name, branch, base_sha)
    except Exception:  # branch exists → unique suffix
        branch = f"{branch}-{int(time.time())}"
        gh_client().create_branch(owner, name, branch, base_sha)
    for i, f in enumerate(files):
        store.update_job(jid, stage=f"committing {i+1}/{len(files)}: {f['path']}")
        gh_client().put_file(owner, name, f["path"], f["content"],
                             f"wardenIQ: implement {fname} ({f['path']})", branch)
    store.update_job(jid, stage="opening pull request")
    body = (f"Implementation generated by **wardenIQ** for feature **{fname}** "
            f"(v{feature.get('version', 1)}).\n\n{gen.get('notes','')}\n\n"
            f"Built to satisfy {len(cases)} acceptance test cases:\n"
            + "\n".join(f"- {c['title']}" for c in cases[:40]))
    pr = gh_client().create_pull(owner, name, f"wardenIQ: implement {fname}",
                                 branch, base_branch, body)
    store.merge_job_result(jid, pr_number=pr.get("number"), pr_url=pr.get("html_url"),
                           branch=branch, repo_id=str(repo["_id"]), cases=len(cases),
                           file_count=len(files))


JOB_WORKERS["develop"] = _develop_worker


class DevIn(BaseModel):
    feature_id: str
    repo_id: str
    base_branch: str = "main"
    language: str = "python"


@app.post("/api/develop")
def develop(body: DevIn):
    if not current_token():
        raise HTTPException(400, "a GitHub token with write access is required (Configuration)")
    repo = store.repos.find_one({"_id": _oid(body.repo_id)})
    if not repo:
        raise HTTPException(404, "repo not found")
    if not _is_app_repo(repo):
        raise HTTPException(400, "Start Developing targets implementation repos only; test repos are reserved for automation coverage")
    feature = store.get_feature(body.feature_id)
    jid = launch_job("develop", {"feature_id": body.feature_id, "repo_id": body.repo_id,
                                 "base_branch": body.base_branch, "language": body.language},
                     label=f"Develop — {(feature or {}).get('name','feature')}",
                     project_id=(feature or {}).get("project_id"), feature_id=body.feature_id)
    return {"job_id": jid}


# --------------------------------------------------------------- Jira (inbound)
def _jira_text(desc):
    """Extract plain text from a Jira description (string, or Cloud ADF JSON)."""
    if not desc:
        return ""
    if isinstance(desc, str):
        return desc
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                out.append(node["text"])
            for v in node.get("content", []) or []:
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(desc)
    return "\n".join(out)


@app.post("/api/integrations/jira/webhook")
async def jira_webhook(request: Request):
    """Create a wardenIQ feature from a Jira issue. Wire via Jira Automation
    ('Send web request' on issue create/transition).

    Auth: requires WEBHOOK_SECRET, supplied ONLY in the `X-Webhook-Token` header
    (headers, unlike query strings, aren't captured in proxy/access logs). Comparison
    is constant-time. This endpoint creates features and launches generate jobs, so
    with no secret configured it refuses (rather than silently accepting
    unauthenticated writes)."""
    if not WEBHOOK_SECRET:
        print("[wardenIQ][jira-webhook] refused: WEBHOOK_SECRET not configured",
              flush=True)
        raise HTTPException(503, "webhook receiver not configured (set WEBHOOK_SECRET)")
    supplied = request.headers.get("X-Webhook-Token", "") or ""
    if not hmac.compare_digest(supplied, WEBHOOK_SECRET):
        raise HTTPException(401, "bad token")
    payload = await request.json()
    issue = payload.get("issue", {}) if isinstance(payload, dict) else {}
    fields = issue.get("fields", {}) or {}
    key = issue.get("key") or payload.get("key")
    name = fields.get("summary") or key or "Jira issue"
    text = _jira_text(fields.get("description")) or name
    pid = store.get_or_default_project()
    if key and store.epic_bound_group(pid, key):
        raise HTTPException(409, f"Epic '{key}' is already associated with another feature")
    emb = embedder.embed(text[:2000])
    fid = store.create_feature(name, pid, [f"jira:{key}"], text, text[:600], emb, key=key)
    chunks = [{"source": f"jira:{key}", "chunk_index": i, "text": ch, "embedding": embedder.embed(ch)}
              for i, ch in enumerate(chunk_doc(text, max_chars=1200, overlap=150))]
    store.add_feature_chunks(fid, pid, chunks)
    launch_job("generate", {"feature_id": fid, "text": text, "focus": None, "total": GEN_TOTAL},
               label=f"Generate (Jira {key})", project_id=pid, feature_id=fid)
    return {"created_feature": fid, "jira_key": key, "name": name}


def _pr_coverage(pr_id, pr_doc, files, fid):
    """Grounded + implementation-verified PR coverage for one mapped PR.

    Implementation coverage (does the PR's PRODUCTION code build each case?) is computed by the
    grounded tiers first (endpoint/symbol with file:line evidence), then an implementation-focused
    LLM verify on the remainder. Automation (dev-test) signal is tracked separately. Test-only PRs
    are flagged and get no implementation-coverage number.
    """
    cases = store.cases_brief(store.feature_test_case_ids(fid))
    prod, test_files, infra = grounding.classify_diff_files(files)
    dev_test_files = test_files
    if not cases:
        store.save_coverage(pr_id, fid, [], dev_test_files, 0.0)
        return {"covered": [], "dev_test_files": dev_test_files, "confidence": 0.0, "notice": ""}
    if grounding.is_test_only(files):
        store.save_coverage(pr_id, fid, [], dev_test_files, 0.0, notice="test_only_pr")
        return {"covered": [], "dev_test_files": dev_test_files, "confidence": 0.0, "notice": "test_only_pr"}

    prod_set = set(prod)
    prod_files = [f for f in files if f["filename"] in prod_set]
    pseudo = [{"repo": pr_doc.get("repo_full_name"), "sha": str(pr_doc.get("number")),
               "url": pr_doc.get("url"), "message": pr_doc.get("title", ""), "files": prod_files}]
    # Grounding gives SCOPE (which cases the PR touches, with file:line evidence) — NOT a verdict.
    gm = grounding.match_commit_changes(pseudo, cases)
    # The LLM decides the actual verdict over ALL cases: does the diff IMPLEMENT the behaviour?
    llm_v = {}
    if prod_files:
        res = cov.verify_pr_implementation(current_llm(), pr_doc, prod_files, cases)
        llm_v = {x["test_case_id"]: x for x in res.get("covered", [])}
    by_id = {c["id"]: c for c in cases}
    covered = []
    for cid in by_id:
        m = gm["matches"].get(cid)     # grounded scope hit (endpoint/symbol) or None
        v = llm_v.get(cid)             # LLM verdict or None
        if v and v.get("status") == "covered":
            status = "covered"          # only the LLM confirming implementation earns "covered"
        elif m or (v and v.get("status") == "partial"):
            status = "partial"          # in scope (code touched) but implementation not confirmed
        else:
            continue                    # neither touched nor implemented → not covered
        covered.append({
            "test_case_id": cid, "status": status,
            "tier": (m.get("tier") if m else 5),
            "confidence": (v.get("confidence") if v else (m.get("confidence") if m else None)),
            "signal_type": (m.get("signal_type") if m else "ai"),
            "signal": (m.get("signal") if m else None),
            "evidence": (m.get("evidence") if m else []),
            "rationale": (v.get("rationale") if v else
                          "PR changes touch code relevant to this case; specific implementation not confirmed"),
            "by_dev_test": False})
    dev_ids = grounding.dev_tested_cases(dev_test_files, cases)
    for c in covered:
        if c["test_case_id"] in dev_ids:
            c["by_dev_test"] = True
    overall = max([c["confidence"] for c in covered if c.get("confidence") is not None], default=0.0)
    store.save_coverage(pr_id, fid, covered, dev_test_files, overall)
    return {"covered": covered, "dev_test_files": dev_test_files, "confidence": overall, "notice": ""}


def _gitlab_mr_to_pr_shape(mr: dict, changes: dict) -> tuple[dict, list]:
    """Translate a GitLab MR + changes payload into the GitHub-PR-ish dict and
    file list that the rest of ingest_pr already understands."""
    iid = mr.get("iid") or 0
    pseudo_pr = {
        "number": iid,
        "title": mr.get("title") or "",
        "body": mr.get("description") or "",
        "user": {"login": (mr.get("author") or {}).get("username") or ""},
        "head": {"ref": mr.get("source_branch") or "",
                 "sha": mr.get("sha") or mr.get("last_commit_sha") or ""},
        "state": "merged" if mr.get("merged_at") else (mr.get("state") or "opened"),
        "html_url": mr.get("web_url") or "",
        "updated_at": mr.get("updated_at") or "",
        "merged_at": mr.get("merged_at"),
    }
    files = []
    for ch in (changes.get("changes") or [])[:50]:
        path = ch.get("new_path") or ch.get("old_path") or ""
        if not path:
            continue
        status = ("added" if ch.get("new_file") else
                  "removed" if ch.get("deleted_file") else
                  "renamed" if ch.get("renamed_file") else
                  "modified")
        diff = (ch.get("diff") or "")[:1500]
        adds = sum(1 for ln in diff.splitlines()
                   if ln.startswith("+") and not ln.startswith("+++"))
        dels = sum(1 for ln in diff.splitlines()
                   if ln.startswith("-") and not ln.startswith("---"))
        files.append({"filename": path, "status": status,
                      "additions": adds, "deletions": dels, "patch": diff})
    return pseudo_pr, files


def _fetch_pr_and_files(repo: dict, pr_number: int) -> tuple[dict, list, str]:
    """Provider-aware fetch. Returns (pr_dict, files, head_sha)."""
    provider = (repo.get("git_provider") or "github").lower()
    pid = repo.get("project_id")
    if provider == "gitlab":
        token = project_gitlab_token(pid)
        if not token:
            raise RuntimeError("no GitLab PAT configured for this project")
        client = gitlab_mod.GitLab(token)
        mr = client.get_mr(repo["full_name"], pr_number)
        changes = client.get_mr_changes(repo["full_name"], pr_number)
        pr, files = _gitlab_mr_to_pr_shape(mr, changes)
        return pr, files, (pr.get("head") or {}).get("sha", "")
    # GitHub default
    token = project_github_token(pid)
    if not token:
        raise RuntimeError("no GitHub PAT configured for this project")
    client = github.GitHub(token, GITHUB_API)
    pr = client.get_pull(repo["owner"], repo["name"], pr_number)
    files = client.get_pull_files(repo["owner"], repo["name"], pr_number)
    return pr, files, (pr.get("head") or {}).get("sha", "")


def ingest_pr(repo: dict, pr: dict, feature_id_override: str | None = None):
    """Fetch a PR's files, store it, auto-map to a feature (unless overridden),
    review coverage, and persist a `code_coverage_runs` row.

    When `feature_id_override` is provided (manual run from a specific feature
    page), we PIN the run to that feature and skip the LLM/heuristic mapping —
    so the run shows up on the feature the user was on, every time."""
    owner, name = repo["owner"], repo["name"]
    number = pr["number"]
    provider = (repo.get("git_provider") or "github").lower()
    head_sha = ""
    head = pr.get("head") or {}
    if isinstance(head, dict):
        head_sha = head.get("sha", "") or ""
    head_ref = (pr.get("head") or {}).get("ref", "") if isinstance(pr.get("head"), dict) else pr.get("head_ref", "")

    # ---- Phase 1: register the PR + a RUNNING coverage row UP FRONT -----------
    # Done before fetching files / running the LLM (the slow parts) so the UI
    # shows "gap analysis running" the moment the webhook lands. Mapping only
    # needs the PR title/body, which the webhook payload already carries.
    base_doc = {
        "project_id": repo["project_id"], "repo_id": repo["id"],
        "repo_full_name": repo["full_name"], "number": number,
        "title": pr.get("title"), "author": (pr.get("user") or {}).get("login"),
        "head_ref": head_ref, "state": "merged" if pr.get("merged_at") else pr.get("state"),
        "url": pr.get("html_url"), "body": pr.get("body"),
        "updated_at": pr.get("updated_at"), "merged_at": pr.get("merged_at"),
    }
    pr_id = store.upsert_pr(base_doc)
    SYNC["ingested"] += 1

    # Manual runs from a specific feature page pin to that feature; otherwise
    # preserve an existing manual assignment before falling back to auto-map.
    if feature_id_override:
        fid, score, method = feature_id_override, 1.0, "manual"
    else:
        prev = store.prs.find_one({"_id": _oid(pr_id)},
                                  {"mapping_method": 1, "feature_id": 1, "mapping_confidence": 1})
        if prev and prev.get("mapping_method") == "manual" and prev.get("feature_id"):
            fid, score, method = prev["feature_id"], prev.get("mapping_confidence", 1.0), "manual"
        else:
            fid, score, method = cov.map_pr_to_feature(
                store, jira_client(), base_doc, repo["project_id"])
    store.set_pr_mapping(pr_id, fid, score, method)

    feature = store.get_feature(fid) if fid else None
    version = (feature or {}).get("version", 1) if feature else None
    run_id = store.create_code_coverage_run({
        "project_id": repo["project_id"],
        "feature_id": fid,
        "feature_version": version,
        "pr_id": pr_id,
        "repo_id": repo["id"],
        "repo_full_name": repo["full_name"],
        "git_provider": repo.get("git_provider", "github"),
        "pr_number": number,
        "pr_title": pr.get("title", ""),
        "pr_branch": head_ref,
        "pr_url": pr.get("html_url"),
        "head_sha": head_sha,
        "source": "webhook",
        "confidence": method,
        "mapping_score": score,
        "status": "running",
    })

    # ---- Phase 2: fetch changed files (slow / network) ------------------------
    files = pr.get("_files")  # caller may pre-fetch (provider dispatch)
    if files is None:
        try:
            if provider == "gitlab":
                fetched_pr, files, fetched_head_sha = _fetch_pr_and_files(repo, number)
                head_sha = fetched_head_sha or head_sha
                if fetched_pr:
                    pr = {**fetched_pr, **pr}
            else:
                token = project_github_token(repo.get("project_id"))
                files = github.GitHub(token, GITHUB_API).get_pull_files(owner, name, number)
        except Exception as e:  # noqa: BLE001
            files = []
            SYNC["errors"].append(f"{repo['full_name']}#{number} files: {e}")
    if files is None:
        files = []

    # Enrich the PR row now that files (and, for GitLab, richer PR data) exist.
    head_ref = (pr.get("head") or {}).get("ref", "") if isinstance(pr.get("head"), dict) else pr.get("head_ref", head_ref)
    doc = {
        **base_doc,
        "title": pr.get("title"), "head_ref": head_ref,
        "state": "merged" if pr.get("merged_at") else pr.get("state"),
        "url": pr.get("html_url"), "body": pr.get("body"),
        "changed_files": [f["filename"] for f in files],
        "additions": sum(f["additions"] for f in files),
        "deletions": sum(f["deletions"] for f in files),
        "updated_at": pr.get("updated_at"), "merged_at": pr.get("merged_at"),
    }
    store.upsert_pr(doc)

    # Providers whose webhook payload lacked title/body (e.g. GitLab) may have
    # missed the provisional mapping; re-map now that the PR is enriched and move
    # the (already-visible) running row onto the resolved feature.
    if not feature_id_override and method != "manual" and not fid:
        fid, score, method = cov.map_pr_to_feature(store, jira_client(), doc, repo["project_id"])
        if fid:
            store.set_pr_mapping(pr_id, fid, score, method)
            feature = store.get_feature(fid)
            version = (feature or {}).get("version", 1) if feature else None
            store.update_code_coverage_run(run_id, feature_id=fid, feature_version=version,
                                           confidence=method, mapping_score=score,
                                           head_sha=head_sha)
        else:
            store.update_code_coverage_run(run_id, head_sha=head_sha)
    elif head_sha:
        store.update_code_coverage_run(run_id, head_sha=head_sha)

    if fid:
        SYNC["mapped"] += 1
        cases = store.cases_brief(store.feature_test_case_ids(fid))
        if cases:
            try:
                result = _pr_coverage(pr_id, doc, files, fid)
                tests_covered = len([c for c in result.get("covered", [])
                                     if c.get("status") in ("covered", "partial")])

                # Cross-version comparison vs the previous done run on this feature.
                prev = store.previous_done_run_for_feature(fid, exclude_id=run_id)
                comparison = cov.diff_runs(prev, result.get("covered", []))

                # Code changes that didn't map to any covered/partial test case.
                unmapped = cov.compute_unmapped_changes(files, result.get("covered", []))

                store.update_code_coverage_run(run_id,
                    status="done",
                    completed_at=time.time(),
                    tests_total=len(cases),
                    tests_covered=tests_covered,
                    gaps_found=max(0, len(cases) - tests_covered),
                    result={"covered": result.get("covered", []),
                            "dev_test_files": result.get("dev_test_files", []),
                            "confidence": result.get("confidence", 0.0),
                            "notice": result.get("notice", ""),
                            "changed_files": [f["filename"] for f in files][:50],
                            "comparison": comparison,
                            "unmapped_changes": unmapped})
            except Exception as e:  # noqa: BLE001
                store.update_code_coverage_run(run_id, status="failed",
                                               error=str(e)[:300],
                                               completed_at=time.time())
        else:
            store.update_code_coverage_run(run_id, status="done",
                                           completed_at=time.time(),
                                           tests_total=0, tests_covered=0,
                                           result={"no_cases": True})
    else:
        store.update_code_coverage_run(run_id, status="done",
                                       completed_at=time.time(),
                                       tests_total=0, tests_covered=0,
                                       result={"unmatched": True,
                                               "mapping_score": score})
    return pr_id


def sync_repo(rid: str):
    repo = next((r for r in store.repos.find({"_id": _oid(rid)})), None)
    if not repo:
        return
    repo = {**repo, "id": str(repo["_id"])}
    provider = (repo.get("git_provider") or "github").lower()
    if provider != "github":
        # GitLab MR polling is webhook-driven; skip in the poller.
        return
    try:
        token = project_github_token(repo.get("project_id"))
        # Ingest ALL PRs (including already-merged ones) — a feature may have
        # merged PRs from before it was tracked in wardenIQ. Users can exclude
        # individual PRs from Gap Analysis afterwards (see set_pr_excluded).
        pulls = github.GitHub(token, GITHUB_API).list_pulls(
            repo["owner"], repo["name"], state="all", per_page=30)
    except Exception as e:  # noqa: BLE001
        SYNC["errors"].append(f"{repo['full_name']} list: {e}")
        return
    last = repo.get("last_synced", 0)
    newest = last
    for pr in pulls:
        upd = _ts(pr.get("updated_at"))
        if upd <= last:
            continue
        ingest_pr(repo, pr)
        newest = max(newest, upd)
    store.set_repo_synced(repo["id"], newest)


def _oid(s):
    from bson import ObjectId
    return ObjectId(s)


def _ts(iso):
    if not iso:
        return 0
    try:
        from datetime import datetime
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except Exception:  # noqa: BLE001
        return 0


def poller():
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            SYNC["running"] = True
            for r in store.repos_watching():
                sync_repo(str(r["_id"]))
            SYNC["last"] = time.time()
        except Exception as e:  # noqa: BLE001
            SYNC["errors"].append(f"poller: {e}")
        finally:
            SYNC["running"] = False


@app.on_event("startup")
def _start_poller():
    threading.Thread(target=poller, daemon=True).start()


@app.get("/api/sync/status")
def sync_status():
    return {**SYNC, "poll_interval_s": POLL_INTERVAL,
            "github_authenticated": bool(GITHUB_TOKEN)}


_ACCEPTED_GH_ACTIONS = {"opened", "synchronize", "reopened"}
_ACCEPTED_GL_ACTIONS = {"open", "update", "reopen"}


def _verify_github_signature(secret: str, raw_body: bytes, sig_header: str) -> bool:
    if not secret or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


@app.post("/api/webhook/github")
async def github_webhook(request: Request):
    """Per-repo secret webhook. Verifies HMAC against each registered repo's
    own webhook secret; fans the event out to all matching projects."""
    body = await request.body()
    event = request.headers.get("X-GitHub-Event", "")
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if event != "pull_request":
        # Drop opaquely (200 so we don't leak which events we accept).
        return {"ok": True}
    try:
        payload = json.loads(body or b"{}")
    except Exception:  # noqa: BLE001
        return {"ok": True}
    action = payload.get("action", "")
    if action not in _ACCEPTED_GH_ACTIONS:
        return {"ok": True}
    full = (payload.get("repository") or {}).get("full_name", "")
    if not full:
        return {"ok": True}
    candidates = store.repos_by_fullname_app(full, git_provider="github")
    if not candidates:
        # Legacy fallback: try env secret + single repo lookup.
        if WEBHOOK_SECRET and _verify_github_signature(WEBHOOK_SECRET, body, sig_header):
            repo = store.repo_by_fullname(full)
            if repo:
                threading.Thread(target=ingest_pr, args=(repo, payload.get("pull_request", {})),
                                 daemon=True).start()
                return {"handled": True, "repo": full}
        return {"ok": True}
    verified = []
    for c in candidates:
        enc = c.get("webhook_secret_enc") or ""
        secret = crypto.decrypt(enc) if enc else ""
        if secret and _verify_github_signature(secret, body, sig_header):
            verified.append(c)
    if not verified:
        return {"ok": True}
    seen = set()
    for repo in verified:
        if repo["project_id"] in seen:
            continue
        seen.add(repo["project_id"])
        threading.Thread(target=ingest_pr, args=(repo, payload.get("pull_request", {})),
                         daemon=True).start()
    return {"handled": True, "projects": len(seen), "repo": full}


@app.post("/api/webhook/gitlab")
async def gitlab_webhook(request: Request):
    """GitLab uses a shared `X-Gitlab-Token` header (no HMAC). We compare it
    against the per-repo encrypted secret stored at connect time."""
    body = await request.body()
    token_header = request.headers.get("X-Gitlab-Token", "") or ""
    event = request.headers.get("X-Gitlab-Event", "")
    if "Merge Request Hook" not in event and event != "Merge Request Hook":
        return {"ok": True}
    try:
        payload = json.loads(body or b"{}")
    except Exception:  # noqa: BLE001
        return {"ok": True}
    attrs = payload.get("object_attributes") or {}
    action = attrs.get("action") or ""
    if action not in _ACCEPTED_GL_ACTIONS:
        return {"ok": True}
    full = (payload.get("project") or {}).get("path_with_namespace") or ""
    if not full:
        return {"ok": True}
    candidates = store.repos_by_fullname_app(full, git_provider="gitlab")
    verified = []
    for c in candidates:
        enc = c.get("webhook_secret_enc") or ""
        secret = crypto.decrypt(enc) if enc else ""
        if secret and hmac.compare_digest(secret, token_header):
            verified.append(c)
    if not verified:
        return {"ok": True}
    # Translate the MR payload into the same shape ingest_pr expects.
    iid = attrs.get("iid")
    pseudo_pr = {
        "number": iid,
        "title": attrs.get("title") or "",
        "user": {"login": (payload.get("user") or {}).get("username") or ""},
        "head": {"ref": attrs.get("source_branch") or ""},
        "state": "merged" if action == "merge" else attrs.get("state") or "open",
        "html_url": attrs.get("url") or "",
        "body": attrs.get("description") or "",
        "updated_at": attrs.get("updated_at") or "",
        "merged_at": attrs.get("merged_at") or None,
    }
    seen = set()
    for repo in verified:
        if repo["project_id"] in seen:
            continue
        seen.add(repo["project_id"])
        threading.Thread(target=ingest_pr, args=(repo, pseudo_pr), daemon=True).start()
    return {"handled": True, "projects": len(seen), "repo": full}


def _trunc(pipeline):
    import copy
    p = copy.deepcopy(pipeline)
    for st in p:
        vs = st.get("$vectorSearch")
        if vs and isinstance(vs.get("queryVector"), list):
            full = vs["queryVector"]
            vs["queryVector"] = [round(v, 4) for v in full[:6]] + [f"...({len(full)} dims)"]
    return p


# Serve the built React SPA. `frontend/` is compiled to `static-react/` at image
# build time (see app/Dockerfile) — hashed JS/CSS live under static-react/assets.
app.mount("/assets", StaticFiles(directory="static-react/assets", check_dir=False), name="assets")


@app.get("/")
def index():
    return FileResponse("static-react/index.html")


@app.get("/favicon.ico")
@app.get("/logo2.png")
def favicon():
    return FileResponse("static-react/logo2.png")


@app.get("/invite")
def invite_landing():
    # Serve the SPA for invitation links (/invite?token=…). The frontend reads the
    # token and drives the verify → login → accept/decline flow. Client routing is
    # hash-based (#dashboard, …), so no path catch-all is needed.
    return FileResponse("static-react/index.html")

# RBAC hardening pass (2026-07): see RBAC_ANALYSIS.md and CHANGELOG for details.
