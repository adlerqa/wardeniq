"""Stored-document upload/list/get/download/delete routes (AWS S3-backed).

Moved out of main.py (Phase 6 of REFACTOR_PLAN.md — first router extracted, per the
plan's suggested order: contiguous, few dependencies, ideal first PR). Decorator
changed from `@app.` to `@router.` only — same paths, same status codes, same
response shapes. `s3_storage` is imported locally inside each handler, exactly as it
was in main.py (not hoisted to module level), so this diff is a pure move.
"""
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from core.logging_setup import get_logger
from core.state import store

log = get_logger("documents")

router = APIRouter()


@router.post("/api/documents/upload")
async def upload_document_endpoint(
    request: Request,
    file: UploadFile = File(...),
    project_id: str = Form(""),
    feature_id: str = Form(""),
):
    from s3_storage import s3_storage
    if not file or not file.filename:
        raise HTTPException(400, detail="No file provided")
    content = await file.read()
    if not content:
        raise HTTPException(400, detail="File is empty")
    if not s3_storage.is_configured():
        raise HTTPException(400, detail="AWS S3 document storage is not configured or enabled in Settings")
    try:
        meta = s3_storage.upload_document(
            filename=file.filename,
            content=content,
            content_type=file.content_type,
            project_id=project_id,
            feature_id=feature_id,
        )
        meta["project_id"] = project_id
        meta["feature_id"] = feature_id
        doc_id = store.save_stored_document(meta)
        meta["id"] = doc_id
        try:
            meta["presigned_url"] = s3_storage.generate_presigned_url(meta["s3_key"])
        except Exception:
            meta["presigned_url"] = None
        return meta
    except Exception as e:
        log.error("[s3-upload-error] %r", e)
        raise HTTPException(500, detail=f"Failed to upload document to AWS S3: {e}")


@router.get("/api/documents")
def list_documents_endpoint(project_id: str = "", feature_id: str = ""):
    from s3_storage import s3_storage
    docs = store.list_stored_documents(project_id=project_id or None, feature_id=feature_id or None)
    is_s3 = s3_storage.is_configured()
    for d in docs:
        if is_s3 and d.get("s3_key"):
            try:
                d["presigned_url"] = s3_storage.generate_presigned_url(d["s3_key"])
            except Exception:
                d["presigned_url"] = None
    return {"documents": docs, "s3_enabled": is_s3}


@router.get("/api/documents/{doc_id}")
def get_document_endpoint(doc_id: str):
    from s3_storage import s3_storage
    doc = store.get_stored_document(doc_id)
    if not doc:
        raise HTTPException(404, detail="Document not found")
    if s3_storage.is_configured() and doc.get("s3_key"):
        try:
            doc["presigned_url"] = s3_storage.generate_presigned_url(doc["s3_key"])
        except Exception:
            doc["presigned_url"] = None
    return doc


@router.get("/api/documents/{doc_id}/download")
def download_document_endpoint(doc_id: str):
    from s3_storage import s3_storage
    doc = store.get_stored_document(doc_id)
    if not doc or not doc.get("s3_key"):
        raise HTTPException(404, detail="Document file not found")
    try:
        content = s3_storage.download_document(doc["s3_key"], bucket=doc.get("s3_bucket"))
        filename = doc.get("filename", "document")
        content_type = doc.get("content_type", "application/octet-stream")
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.error("[s3-download-error] %r", e)
        raise HTTPException(500, detail=f"Failed to download document from AWS S3: {e}")


@router.delete("/api/documents/{doc_id}")
def delete_document_endpoint(doc_id: str):
    from s3_storage import s3_storage
    doc = store.get_stored_document(doc_id)
    if not doc:
        raise HTTPException(404, detail="Document not found")
    if doc.get("s3_key"):
        s3_storage.delete_document(doc["s3_key"], bucket=doc.get("s3_bucket"))
    deleted = store.delete_stored_document(doc_id)
    return {"ok": deleted, "id": doc_id}
