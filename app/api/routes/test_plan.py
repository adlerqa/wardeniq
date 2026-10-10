"""Test Plan API: generate a test-plan run for a feature, fetch the latest run,
stream run progress via SSE, and export a completed run as CSV/PDF.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 11/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 5 routes were one contiguous block in the original main.py; no Pydantic
models or private helpers belong only to this domain, and no shared-helper
deviation was needed (store, current_llm, run_tracked, _current_user, and
_require_test_plan_run_project were all already centralized in earlier phases).
"""
import json
import threading

import test_plan

from fastapi import APIRouter, HTTPException, Request

from core.deps import current_llm
from core.security import _current_user, _require_test_plan_run_project
from core.state import store
from workers.registry import run_tracked

router = APIRouter()


@router.post("/api/features/{fid}/test-plan")
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
        run_tracked(
            "test_plan",
            lambda: test_plan.generate_test_plan_job(store, current_llm(), run_id, fid),
            label=f"Test plan · {feature.get('name', '')}",
            project_id=feature.get("project_id"), feature_id=fid)

    threading.Thread(target=run_gen, daemon=True).start()
    return {"runId": run_id, "runNumber": run_number, "status": "PROCESSING"}


@router.get("/api/features/{fid}/test-plan/latest")
def get_latest_test_plan(fid: str):
    run = store.get_latest_test_plan_run(fid)
    if not run:
        return {"run": None}
    return {"run": run}


@router.get("/api/test-plan/runs/{run_id}/stream")
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


@router.get("/api/test-plan/runs/{run_id}/export/csv")
def export_test_plan_csv(run_id: str, request: Request):
    run = _require_test_plan_run_project(request, run_id)
    if not run or not run.get("content"):
        raise HTTPException(404, "Test plan content not found")
    csv_str = test_plan.build_test_plan_csv(run["content"])
    from fastapi.responses import Response
    return Response(content=csv_str, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=test_plan_{run_id}.csv"
    })


@router.get("/api/test-plan/runs/{run_id}/export/pdf")
def export_test_plan_pdf(run_id: str, request: Request):
    run = _require_test_plan_run_project(request, run_id)
    if not run or not run.get("content"):
        raise HTTPException(404, "Test plan content not found")
    pdf_bytes = test_plan.build_test_plan_pdf(run["content"])
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=test_plan_{run_id}.pdf"
    })
