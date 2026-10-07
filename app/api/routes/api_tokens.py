"""API token management routes (issue #37): admin-only CRUD for the bearer
tokens resolved by core/token_auth.py. Mirrors api/routes/users.py's shape
(project-access validation, audit logging) for a principal that is a service
account rather than a person.

/api/api-tokens is added to core/security.py's ADMIN_PATHS, so the gateway
already enforces admin-only here — no per-route role check needed, same as
/api/users.
"""
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import auth
from core.audit import _audit
from core.security import _current_user
from core.state import store

router = APIRouter()

# Service-account tokens are scoped to viewer/editor only (issue #37 scope: "a
# principal ... with a role (viewer / editor)") — no admin bearer tokens.
_TOKEN_ROLES = ("viewer", "editor")


@router.get("/api/api-tokens")
def list_api_tokens():
    return {"tokens": store.list_api_tokens()}


class ApiTokenIn(BaseModel):
    name: str
    role: str = "viewer"
    all_projects: bool = True
    project_ids: list[str] = []
    expires_in_days: int | None = None


@router.post("/api/api-tokens")
def create_api_token(body: ApiTokenIn, request: Request):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "a name is required")
    role = body.role if body.role in _TOKEN_ROLES else "viewer"
    all_projects = bool(body.all_projects)
    project_ids = [] if all_projects else [p for p in (body.project_ids or []) if store.get_project(p)]
    if not all_projects and not project_ids:
        raise HTTPException(400, "select at least one project, or grant access to all projects")
    expires_at = None
    if body.expires_in_days is not None:
        if body.expires_in_days <= 0:
            raise HTTPException(400, "expires_in_days must be positive")
        expires_at = time.time() + body.expires_in_days * 86400
    plaintext = "wq_" + auth.gen_invite_token()
    me = _current_user(request)
    token = store.create_api_token(
        name, auth.hash_token(plaintext), role=role, all_projects=all_projects,
        project_ids=project_ids, created_by=(me.get("id") if me else None),
        expires_at=expires_at)
    _audit(request, "api_token.created", target=name,
           new={"role": role, "all_projects": all_projects, "project_ids": project_ids})
    # The plaintext is returned exactly once, here — never stored, never logged,
    # never returned again by any other endpoint (list/get only ever return the hash-
    # backed _token_out shape, which has no plaintext field).
    return {"token": token, "plaintext": plaintext}


@router.delete("/api/api-tokens/{tid}")
def revoke_api_token(tid: str, request: Request):
    existing = store.get_api_token(tid)
    if not existing:
        raise HTTPException(404, "token not found")
    store.revoke_api_token(tid)
    _audit(request, "api_token.revoked", target=existing.get("name"))
    return {"revoked": tid}
