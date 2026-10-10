"""Start Developing: launch the "develop" background job that has an LLM draft
an implementation PR for a feature against one of its linked (non-test) repos.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 17/20).
Handler body is unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

Single route + its one Pydantic model; no shared-helper deviation was needed —
``current_token``/``_is_app_repo``/``_oid`` (core/deps.py) and ``launch_job``
(workers/registry.py) were already centralized in earlier phases.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.deps import _is_app_repo, _oid, current_token
from core.state import store
from workers.registry import launch_job

router = APIRouter()


class DevIn(BaseModel):
    feature_id: str
    repo_id: str
    base_branch: str = "main"
    language: str = "python"


@router.post("/api/develop")
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
