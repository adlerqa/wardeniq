"""Test steps and test cases: step CRUD/edit, case CRUD/edit, case execution
status updates, and unlinking a case from a feature.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 9/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 11 routes + 5 models were spread across 4 non-contiguous blocks in the
original main.py (interleaved with the features/system/validator/test_plan/
code_coverage domains), consolidated into one router file here since they're
all genuinely the same domain (steps + test cases).
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import state
from core.config import STEP_AUTO
from core.security import (
    _allowed_project_ids, _current_user, _require_case_project,
    _require_feature_project, _require_project,
)
from core.state import store

router = APIRouter()


@router.get("/api/steps")
def list_steps(limit: int = 200, skip: int = 0):
    return {"steps": store.list_steps(limit, skip)}


class StepEdit(BaseModel):
    action: str
    expected: str


@router.patch("/api/steps/{sid}")
def edit_step(sid: str, body: StepEdit):
    emb = state.embedder.embed(f"{body.action}. Expected: {body.expected}")
    return store.update_step(sid, body.action, body.expected, emb)


@router.get("/api/test-cases")
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


@router.get("/api/test-cases/{cid}")
def get_case(cid: str, request: Request):
    return _require_case_project(request, cid)


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


@router.put("/api/test-cases/{cid}")
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
        emb = state.embedder.embed(f"{action}. Expected: {expected}")
        sid = s.get("id")
        if sid:
            r = store.update_step(sid, action, expected, emb)  # propagates
            propagated += max(0, r["affected_cases"] - 1)
            step_ids.append(sid)
        else:
            r = store.get_or_create_step(action, expected, emb, STEP_AUTO)
            step_ids.append(r["step_id"])
    cemb = state.embedder.embed(body.title + " " + " ".join(
        f"{s.get('action','')} {s.get('expected','')}" for s in body.steps))
    store.update_case(cid, body.title, body.type, body.priority,
                      body.preconditions, body.tags, step_ids, cemb)
    return {"updated": cid, "steps": len(step_ids),
            "other_cases_affected_by_step_edits": propagated}


@router.patch("/api/test-cases/{cid}/execution")
def update_case_execution(cid: str, body: CaseExecutionUpdate, request: Request):
    _require_case_project(request, cid)
    if body.status not in {"untested", "passed", "failed", "blocked"}:
        raise HTTPException(422, "status must be untested, passed, failed, or blocked")
    if not store.update_case_execution(cid, body.status, body.note.strip()):
        raise HTTPException(404, "test case not found")
    return {"updated": cid, "execution_status": body.status}


class NewCaseIn(BaseModel):
    feature_id: str
    title: str
    type: str = "functional"
    priority: str = "P2"
    preconditions: str = ""
    tags: list[str] = []
    steps: list[dict] = []


@router.post("/api/test-cases")
def create_test_case(body: NewCaseIn, request: Request):
    _require_feature_project(request, body.feature_id)   # scope to the case's feature
    step_ids = []
    for s in body.steps:
        a = (s.get("action") or "").strip(); e = (s.get("expected") or "").strip()
        if not (a or e):
            continue
        emb = state.embedder.embed(f"{a}. Expected: {e}")
        step_ids.append(store.get_or_create_step(a, e, emb, STEP_AUTO)["step_id"])
    cemb = state.embedder.embed(body.title + " " + " ".join(
        f"{s.get('action','')} {s.get('expected','')}" for s in body.steps))
    cid = store.create_case(body.title, body.type, body.priority, body.preconditions,
                            step_ids, body.tags, cemb, body.feature_id)
    store.associate(body.feature_id, cid, "manual", None)
    created = store.get_case(cid) or {}
    return {"id": cid, "display_id": created.get("display_id")}


@router.delete("/api/test-cases/{cid}")
def delete_test_case(cid: str, request: Request, force: bool = False):
    _require_case_project(request, cid)
    result = store.delete_case(cid, force)
    if result.get("requires_force"):
        raise HTTPException(409, detail=result)
    return result


@router.delete("/api/features/{fid}/test-cases/{cid}")
def unlink_test_case_from_feature(fid: str, cid: str):
    result = store.unlink_case_from_feature(fid, cid)
    if not result.get("removed"):
        raise HTTPException(404, result.get("reason", "association not found"))
    return result


class NewStepIn(BaseModel):
    action: str
    expected: str


@router.post("/api/steps")
def create_step(body: NewStepIn):
    emb = state.embedder.embed(f"{body.action}. Expected: {body.expected}")
    return {"id": store.create_step(body.action, body.expected, emb)}


@router.delete("/api/steps/{sid}")
def delete_step(sid: str):
    return store.delete_step(sid)
