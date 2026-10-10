"""Manual test-cycle execution: create/list/get cycles, per-item status updates,
activity/report/CSV/PDF export, and cycle templates.

Moved out of main.py (Phase 6 of docs/internal/REFACTOR_PLAN.md — contiguous block, extracted early
per the plan's suggested order). Decorator changed from `@app.` to `@router.` only —
same 17 paths, same status codes, same response shapes. Local imports
(`from pymongo.errors import DuplicateKeyError`, `from fastapi.responses import
Response`, `import report`) are kept exactly where they were (inside the handler
body), not hoisted, so this diff is a pure move.
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from core.security import _current_user, _require_project
from core.state import store

router = APIRouter()


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


@router.post("/api/test-cycles")
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


@router.get("/api/projects/{pid}/test-cycles")
def list_cycles(pid: str, status: str | None = None):
    return {"cycles": store.list_cycles(pid, status)}


@router.get("/api/test-cycles/{cid}")
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


@router.patch("/api/test-cycles/{cid}/items")
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


@router.patch("/api/test-cycles/{cid}")
def update_cycle(cid: str, body: dict, request: Request):
    from pymongo.errors import DuplicateKeyError
    user = _current_user(request)
    try:
        return store.update_cycle(cid, body or {}, performed_by=(user or {}).get("email"))
    except DuplicateKeyError:
        raise HTTPException(409, "A test cycle with that name already exists in this project — pick a different name")


@router.post("/api/test-cycles/{cid}/items")
def add_cycle_items(cid: str, body: dict, request: Request):
    user = _current_user(request)
    try:
        count = store.add_cycle_items(
            cid, (body or {}).get("case_ids") or [],
            performed_by=(user or {}).get("email"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"added": count, "cycle": store.get_cycle(cid)}


@router.post("/api/test-cycles/{cid}/items/batch-status")
def batch_cycle_status(cid: str, body: dict, request: Request):
    user = _current_user(request)
    try:
        return store.batch_cycle_item_status(
            cid, (body or {}).get("item_ids") or [], (body or {}).get("status") or "",
            executed_by=(user or {}).get("email"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/test-cycles/{cid}/items/{item_id}")
def remove_cycle_item(cid: str, item_id: str, request: Request):
    user = _current_user(request)
    store.remove_cycle_item(cid, item_id, performed_by=(user or {}).get("email"))
    return {"ok": True}


@router.get("/api/test-cycles/{cid}/activity")
def cycle_activity(cid: str):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    return {"activity": list(reversed(c.get("activity", [])))}


@router.get("/api/test-cycles/{cid}/report")
def cycle_report(cid: str):
    report_data = store.cycle_report(cid)
    if not report_data:
        raise HTTPException(404, "cycle not found")
    return report_data


@router.get("/api/test-cycles/{cid}/export/csv")
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


@router.get("/api/test-cycles/{cid}/export/pdf")
def export_cycle_pdf(cid: str):
    c = store.get_cycle(cid)
    if not c:
        raise HTTPException(404, "cycle not found")
    import report
    pdf = report.build_cycle_pdf(c)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="test-cycle-{cid}.pdf"'})


@router.delete("/api/test-cycles/{cid}")
def del_cycle(cid: str):
    return store.delete_cycle(cid)


class TemplateIn(BaseModel):
    name: str


@router.post("/api/test-cycles/{cid}/save-template")
def save_cycle_template(cid: str, body: TemplateIn):
    tid = store.save_cycle_as_template(cid, body.name)
    if not tid:
        raise HTTPException(404, "cycle not found")
    return {"id": tid}


@router.get("/api/projects/{pid}/cycle-templates")
def list_cycle_templates(pid: str):
    return {"templates": store.list_cycle_templates(pid)}


@router.post("/api/cycle-templates/{tid}/create-cycle")
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


@router.delete("/api/cycle-templates/{tid}")
def delete_cycle_template(tid: str):
    return store.delete_cycle_template(tid)
