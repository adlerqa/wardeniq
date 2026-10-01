"""Project CRUD: create/list/fetch/patch/delete a project (Jira/Confluence
linkage, default git provider, PAT-configured booleans surfaced via
_project_public).

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 13/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 5 routes + 2 models were two non-contiguous blocks in the original main.py
(create/list/get, then patch/delete ~400 lines later, interleaved with the
code_coverage and features domains). ``RenameIn`` and the "CRUD:
projects/features/cases/steps/repos" umbrella comment stay in main.py — they
belong to ``rename_feature``/``delete_feature`` (features.py, router 14, not yet
extracted).
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.audit import _audit
from core.security import _current_user, _filter_projects_for, _project_public, _require_project
from core.state import store

router = APIRouter()


class ProjectIn(BaseModel):
    name: str
    description: str | None = ""
    key: str | None = None
    jira_project_key: str | None = None
    jira_project_name: str | None = None
    confluence_space_key: str | None = None
    confluence_space_name: str | None = None
    default_git_provider: str | None = "github"  # 'github' | 'gitlab'


@router.post("/api/projects")
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


@router.get("/api/projects")
def list_projects(request: Request):
    # Only projects the current user may access (admins / all_projects see everything).
    return {"projects": _filter_projects_for(_current_user(request), store.list_projects())}


@router.get("/api/projects/{pid}")
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


class ProjectPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    key: str | None = None
    jira_project_key: str | None = None
    jira_project_name: str | None = None
    confluence_space_key: str | None = None
    confluence_space_name: str | None = None
    default_git_provider: str | None = None  # 'github' | 'gitlab'


@router.patch("/api/projects/{pid}")
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


@router.delete("/api/projects/{pid}")
def delete_project(pid: str, request: Request):
    proj = store.get_project(pid)
    result = store.delete_project(pid)
    if not result:
        raise HTTPException(404, "project not found")
    _audit(request, "project.deleted", target=(proj or {}).get("name") or pid,
           old={"name": (proj or {}).get("name")})
    return result
