"""Repository connection management: per-project GitHub/GitLab PATs, accessible-repo
browsing, connecting a repo (with webhook registration), listing/branches/watch/sync,
deleting a repo, and GitHub rate-limit/my-repos lookups.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 8/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

DOCUMENTED DEVIATION — PR-workflow routes NOT moved here despite the "repos_prs"
name: `exclude_pr` (POST /api/prs/{pr_id}/exclude), `unmapped_prs` (GET
/api/projects/{pid}/unmapped-prs), and `assign_pr` (POST /api/prs/{pr_id}/assign) stay
in main.py for now. In the original file they're interleaved with (and, for
`assign_pr`, directly call) the PR-coverage computation pipeline — `_pr_coverage`,
`_fetch_pr_and_files`, `ingest_pr`, `run_tracked` — which are private helpers belonging
to the not-yet-extracted code_coverage domain (a later router per the plan's
"jobs_usage/code_coverage/develop" grouping). Moving `assign_pr` here now would force
this router to import private helpers back out of main.py, which the plan explicitly
forbids (it's the same router-to-router-cycle problem, just against main.py itself
instead of another router). These three routes will move together with
`_pr_coverage`/`_fetch_pr_and_files` when code_coverage.py is extracted.

`project_prs` (GET /api/projects/{pid}/prs, simple PR listing with no coverage
dependency) DOES move here, since it has no such coupling.
"""
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import crypto
import github
import gitlab as gitlab_mod
from background.poller import sync_repo
from core.config import GITHUB_API, GITHUB_TOKEN
from core.deps import (
    _ext_error, _oid, _repo_list_branches, _webhook_base_url,
    project_github_token, project_gitlab_token,
)
from core.logging_setup import get_logger
from core.state import store

log = get_logger("repos_prs")

router = APIRouter()


# ---- per-project GitHub PAT ------------------------------------------------
class PatIn(BaseModel):
    pat: str


@router.get("/api/projects/{pid}/github/pat")
def get_project_github_pat_status(pid: str):
    return {"configured": bool(store.get_project_github_pat_enc(pid))}


@router.put("/api/projects/{pid}/github/pat")
def save_project_github_pat(pid: str, body: PatIn):
    if not body.pat or not body.pat.strip():
        raise HTTPException(400, "pat required")
    store.set_project_github_pat_enc(pid, crypto.encrypt(body.pat.strip()))
    return {"ok": True}


@router.delete("/api/projects/{pid}/github/pat")
def clear_project_github_pat(pid: str):
    store.set_project_github_pat_enc(pid, "")
    return {"ok": True}


@router.get("/api/projects/{pid}/github/accessible-repos")
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
@router.get("/api/projects/{pid}/gitlab/pat")
def get_project_gitlab_pat_status(pid: str):
    return {"configured": bool(store.get_project_gitlab_pat_enc(pid))}


@router.put("/api/projects/{pid}/gitlab/pat")
def save_project_gitlab_pat(pid: str, body: PatIn):
    if not body.pat or not body.pat.strip():
        raise HTTPException(400, "pat required")
    store.set_project_gitlab_pat_enc(pid, crypto.encrypt(body.pat.strip()))
    return {"ok": True}


@router.delete("/api/projects/{pid}/gitlab/pat")
def clear_project_gitlab_pat(pid: str):
    store.set_project_gitlab_pat_enc(pid, "")
    return {"ok": True}


@router.get("/api/projects/{pid}/gitlab/accessible-repos")
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
@router.get("/api/git/accessible-repos")
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


# ---- project repos (with webhook registration) -----------------------------
# Repo "kind" is a display/badge classification, independent of repo_type (app/test,
# which governs webhooks). Canonical values: BE, FE, test, infra. "other" is a legacy
# value kept only so pre-existing repos still render; it is no longer offered in the UI.
_REPO_KINDS = {"BE", "FE", "test", "infra"}
_REPO_KIND_ALIASES = {
    "be": "BE", "backend": "BE",
    "fe": "FE", "frontend": "FE",
    "test": "test", "tests": "test", "testing": "test",
    "infra": "infra", "infrastructure": "infra",
    "other": "other",   # legacy passthrough
}


def _normalize_repo_kind(kind: str | None) -> str:
    """Coerce an incoming kind to a canonical value (BE/FE/test/infra, or legacy
    'other'), defaulting to BE. Accepts case-insensitive names/aliases so the API is
    forgiving regardless of how the client spells it."""
    k = (kind or "").strip()
    if k in _REPO_KINDS or k == "other":
        return k
    return _REPO_KIND_ALIASES.get(k.lower(), "BE")


class RepoIn(BaseModel):
    # Either provide an `url` (parsed) or `repo_full_name` (already-validated).
    url: str | None = None
    repo_full_name: str | None = None
    label: str | None = None
    kind: str = "BE"                  # BE | FE | test | infra  (badge; 'other' = legacy)
    repo_type: str = "app"            # app | test  (webhook behavior — separate axis)
    git_provider: str = "github"      # github | gitlab
    default_branch: str = "main"


@router.post("/api/projects/{pid}/repos")
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
                    log.warning("[webhook] list failed (continuing): %s", e)
                if existing:
                    webhook_id = existing.get("id")
                    try:
                        client.update_pr_webhook(owner, name, webhook_id, webhook_url, secret)
                    except Exception as e:  # noqa: BLE001
                        log.warning("[webhook] patch failed: %s", e)
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
            log.warning("[webhook] register failed: %s", e)

    rid = store.add_repo(pid, owner, name,
                         (body.url or f"https://{provider}.com/{full_name}"),
                         _normalize_repo_kind(body.kind), body.default_branch,
                         repo_type=repo_type, git_provider=provider,
                         label=label,
                         webhook_id=webhook_id, webhook_secret_enc=webhook_secret_enc)
    if repo_type == "app":
        threading.Thread(target=sync_repo, args=(rid,), daemon=True).start()
    return {"repo_id": rid, "full_name": full_name, "watching": True,
            "webhook_configured": bool(webhook_secret_enc)}


@router.get("/api/projects/{pid}/repos")
def list_repos(pid: str, repo_type: str | None = None):
    if repo_type in {"app", "test"}:
        return {"repos": store.repos_for_project(pid, repo_type=repo_type)}
    return {"repos": store.list_repos(pid)}


@router.get("/api/repos/{rid}/branches")
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


@router.post("/api/repos/{rid}/watch")
def set_watch(rid: str, body: dict):
    store.set_repo_watch(rid, bool((body or {}).get("watch", True)))
    return {"ok": True}


@router.post("/api/repos/{rid}/sync")
def sync_now(rid: str):
    threading.Thread(target=sync_repo, args=(rid,), daemon=True).start()
    return {"started": True}


@router.get("/api/projects/{pid}/prs")
def project_prs(pid: str):
    return {"prs": store.list_prs(project_id=pid)}


@router.get("/api/github/ratelimit")
def github_rate(project_id: str | None = None):
    token = project_github_token(project_id) if project_id else GITHUB_TOKEN
    if not token:
        raise HTTPException(400, "no GitHub PAT available")
    return github.GitHub(token, GITHUB_API).rate_limit()


@router.get("/api/github/my-repos")
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


@router.delete("/api/repos/{rid}")
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
            log.warning("[webhook] delete failed (continuing): %s", e)
    return store.delete_repo(rid)
