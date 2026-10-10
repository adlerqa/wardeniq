"""Import Sheet API: upload a CSV/XLSX/TSV sheet of pre-existing tests, poll its
analysis status, review/correct the scorer's include/exclude decisions, and the
project-wide imported-sheet ("QA library") pool — list, add, remove, and
on-demand rescore/promote against a feature.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 12/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 10 routes + 3 models were one contiguous block in the original main.py.

Test-repo scanning + the imported-sheet pipeline itself lives in
app/workers/repo_scan_worker.py (Phase 3); the "test_import" job worker lives in
app/workers/test_import_worker.py. ``_case_exists``, ``_promote_imported_row_to_feature``,
and ``_sheet_steps_preview`` are imported here (not moved) because these route
handlers call them directly, matching the existing repo_scan_worker.py-is-the-
single-source pattern (background/schedulers.py's ``_import_reanalysis_scheduler``
and workers/generation.py's ``_gen_worker`` import the same helpers independently).
Importing ``workers.test_import_worker`` is required even though nothing here
binds its name: the import itself is what runs
``JOB_WORKERS["test_import"] = ...`` as a side effect, exactly like
workers.registry already does for JOB_WORKERS -- moved here (from main.py) since
this router's ``upload_test_sheet`` is the only launcher of "test_import" jobs.

Per docs/internal/REFACTOR_PLAN.md section 2.4, ``remove_imported_sheet_rows`` and
``LibraryHashesIn`` are re-exported from main.py (tests reach them via
``main.<name>``); see main.py's re-export block.
"""
import hashlib

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

import sheet_import as sheet_mod

from core.security import _current_user
from core.state import store
from workers import test_import_worker  # noqa: F401
from workers.registry import launch_job
from workers.repo_scan_worker import (
    _case_exists,
    _promote_imported_row_to_feature,
    _rescan_pool_for_feature,
    _sheet_steps_preview,
)

router = APIRouter()


@router.post("/api/projects/{pid}/features/{fid}/tests/import")
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


@router.get("/api/features/{fid}/tests/import/{import_id}/status")
def get_import_status(fid: str, import_id: str):
    status = store.get_import_analysis_status(import_id) or {}
    if not status:
        raise HTTPException(404, "import not found")
    return {"ok": True,
             "data": {"status": status.get("status", "PENDING"),
                      "details": status.get("details", ""),
                      "completed": bool(status.get("completed")),
                      "result_json": status.get("result_json")}}


@router.get("/api/features/{fid}/tests/import/{import_id}/analysis-result")
def get_import_analysis_result(fid: str, import_id: str):
    status = store.get_import_analysis_status(import_id) or {}
    if not status:
        raise HTTPException(404, "import not found")
    return {"ok": True, "data": status.get("result_json") or {}}


@router.get("/api/features/{fid}/tests/import/{import_id}/review")
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


@router.post("/api/features/{fid}/tests/import/{import_id}/review")
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


@router.get("/api/features/{fid}/tests/import/template")
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
@router.get("/api/features/{fid}/imported-sheets")
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


@router.post("/api/features/{fid}/imported-sheets/add")
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


@router.post("/api/features/{fid}/imported-sheets/remove")
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


# _import_reanalysis_scheduler moved to background/schedulers.py (Phase 4);
# imported at top of main.py alongside _stale_job_sweeper.


@router.post("/api/features/{fid}/imported-sheets/refresh")
def refresh_imported_sheet_library(fid: str):
    """On-demand: re-score every `unmatched_pool` row in this project against THIS
    feature's current context; newly-matching rows are auto-promoted."""
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    rescored, promoted = _rescan_pool_for_feature(feature)
    return {"ok": True, "data": {"rescored": rescored,
                                   "newly_promoted": len(promoted)}}
