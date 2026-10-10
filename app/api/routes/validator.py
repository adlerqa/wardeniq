"""MCQ Validator API: generate a validator run for a feature, fetch the latest
or historical run state, submit answers, and export a scored run.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 10/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 5 routes were one contiguous block in the original main.py; no Pydantic
models or private helpers belong only to this domain, and no shared-helper
deviation was needed (store, launch_job, _oid, _svc_error, _current_user, and
_require_validator_run_project were all already centralized in earlier phases).
"""
import time

import validator

from fastapi import APIRouter, HTTPException, Request

from core.deps import _oid, _svc_error
from core.security import _current_user, _require_validator_run_project
from core.state import store
from workers.registry import launch_job

router = APIRouter()


@router.post("/api/features/{fid}/validator")
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


@router.get("/api/features/{fid}/validator/latest")
def get_validator_latest(fid: str):
    """Return the existing validator state (if any) WITHOUT launching generation."""
    try:
        existing = validator.get_existing_validator(store, fid)
        return existing or {"mode": "none"}
    except Exception as e:
        raise _svc_error("Validator", e)


@router.post("/api/validator/runs/{run_id}/submit")
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


@router.get("/api/features/{fid}/validator/history")
def get_validator_history(fid: str):
    try:
        return {"history": store.list_validator_runs(fid)}
    except Exception as e:
        raise _svc_error("Validator history", e)


@router.get("/api/validator/runs/{run_id}/export")
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
