"""Feature CRUD: create a feature from uploaded docs/pasted text/external
sources (Figma/Confluence), list/fetch features, regenerate, version, rename,
delete, associate a case, set the manual PR match-key, and set the QA-readiness
threshold.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 14/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 10 routes + 4 models were scattered across 4 non-contiguous regions in the
original main.py (interleaved with the jobs_usage/system/code_coverage domains),
removed bottom-to-top with boundary assertions per region. Two now-fully-dead
leftover comments were removed along the way: the "CRUD: projects/features/
cases/steps/repos" umbrella comment (all five domains it named are now
extracted) and a stray "Phase 2: GitHub" comment that had been orphaned between
routes since an earlier phase.

``_fallback_feature_summary``, ``_generate_feature_summary``, ``_gather_external``,
and ``figma_client`` already live in core/deps.py (Phase 3, documented deviation
— also needed by workers/generation.py's ``_ingest_worker``); this router just
becomes one more importer, same as main.py did before.
"""
import json as _json
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

import coverage as cov
import extract as extractmod
import figma
from extract import chunk as chunk_doc, extract_text, UnsupportedDocumentError

from core import state
from core.config import GEN_TOTAL
from core.deps import (
    _fallback_feature_summary, _gather_external, _generate_feature_summary,
    current_llm, figma_client, jira_client,
)
from core.logging_setup import get_logger
from core.security import _allowed_project_ids, _current_user, _require_feature_project, _require_project
from core.state import store
from workers.registry import launch_job

log = get_logger("features")

router = APIRouter()


def _display_feature_summary(feature: dict) -> str:
    summary = " ".join(str(feature.get("summary") or "").split()).strip()
    looks_raw = (
        not summary
        or summary.startswith("###")
        or bool(re.search(r"\b(?:PRD|HLD|LLD|Document)\b", summary[:120], re.I))
        or bool(re.search(r"\b[\w.-]+\.(?:pdf|docx?|md|txt|markdown)\b", summary[:180], re.I))
    )
    if not looks_raw and len(summary) >= 40:
        return summary
    return _fallback_feature_summary(feature.get("name") or "Feature", feature.get("text") or summary)


class MatchKeyIn(BaseModel):
    match_key: str = ""


@router.post("/api/features/{fid}/match-key")
def set_feature_match_key(fid: str, body: MatchKeyIn):
    """Set/clear a feature's manual PR match tag (editor+, gated by auth_gateway).
    PRs whose title/body contain the bracketed tag (e.g. [HOLDS]) auto-map to this
    feature on the next poll -- for projects without a linked Jira epic."""
    if not store.get_feature(fid):
        raise HTTPException(404, "feature not found")
    return {"match_key": store.set_feature_match_key(fid, body.match_key)}


@router.post("/api/features")
async def create_feature(request: Request, name: str = Form(...), project_id: str = Form(""),
                         key: str = Form(""), match_key: str = Form(""), text: str = Form(""),
                         focus: str = Form(""), total: int = Form(16),
                         confluence_url: list[str] = Form(default=[]),
                         confluence_children: bool = Form(True),
                         figma_url: list[str] = Form(default=[]),
                         files: list[UploadFile] = File(None)):
    # Combine every uploaded doc (PRD/HLD/LLD/…) + pasted text into one corpus,
    # each section labelled so the LLM and the embeddings keep document context.
    parts, sources, pdf_urls = [], [], []
    raw_files_info = []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        raw_files_info.append((f.filename, data, getattr(f, "content_type", None)))
        try:
            txt = extract_text(f.filename, data)
        except UnsupportedDocumentError as exc:
            raise HTTPException(400, str(exc)) from exc
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
        if f.filename.lower().endswith(".pdf"):
            pdf_urls.extend(extractmod.pdf_links(data))
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    # Multiple Confluence / Figma links are supported (one field can carry several,
    # comma/space/newline-separated, and the field can be repeated). Split + de-dupe.
    confluence_urls = _split_links(confluence_url)
    figma_urls = _split_links(figma_url)
    # Figma links found inside PDFs are read via the API too; other PDF links get crawled.
    pdf_figma = [u for u in pdf_urls if "figma.com" in u.lower()]
    crawl_seeds = [u for u in pdf_urls if "figma.com" not in u.lower()]
    for u in figma_urls:
        if not figma.Figma.file_key_from_url(u):
            raise HTTPException(400, f"could not read a Figma file key from: {u[:80]}")
    has_figma = bool(figma_urls or pdf_figma)
    has_confluence = bool(confluence_urls)
    external = has_figma or has_confluence or bool(crawl_seeds)
    # Fail fast on missing config so the user gets immediate feedback (the fetching
    # itself happens in the background job below).
    if has_figma and not figma_client().ok():
        raise HTTPException(400, "Figma token not configured — add a Figma access token in Settings")
    if has_confluence and not jira_client().ok():
        raise HTTPException(400, "Confluence not configured — set Jira base URL, email & API token in Settings")
    if not parts and not external:
        raise HTTPException(400, "no document text provided")

    pid = project_id or store.get_or_default_project()
    _require_project(request, pid)   # can't create a feature in a project you can't access
    epic_key = (key or "").strip() or None
    if epic_key and store.epic_bound_group(pid, epic_key):
        raise HTTPException(409, f"Epic '{epic_key}' is already associated with another feature")
    try:
        focus_d = _json.loads(focus) if focus else None
    except Exception:  # noqa: BLE001
        focus_d = None

    base_raw = "\n\n".join(parts)
    summary = _generate_feature_summary(name, base_raw) if base_raw.strip() else name
    emb = state.embedder.embed((base_raw or name)[:2000])
    fid = store.create_feature(name, pid, sources, base_raw, summary, emb, key=epic_key,
                               match_key=((match_key or "").strip().upper() or None))

    # Auto-upload raw document files to AWS S3 if S3 document storage is configured
    from s3_storage import s3_storage
    if s3_storage.is_configured():
        for filename, content_bytes, content_type in raw_files_info:
            try:
                meta = s3_storage.upload_document(
                    filename=filename,
                    content=content_bytes,
                    content_type=content_type,
                    project_id=pid,
                    feature_id=fid,
                )
                meta["project_id"] = pid
                meta["feature_id"] = fid
                store.save_stored_document(meta)
            except Exception as e:
                log.warning("[s3-auto-upload-warn] %r", e)

    if not external:
        # Fast path: only local docs / pasted text — index + generate inline (unchanged).
        chunks = []
        for i, ch in enumerate(chunk_doc(base_raw, max_chars=1200, overlap=150)):
            chunks.append({"source": sources[0] if sources else "combined",
                           "chunk_index": i, "text": ch, "embedding": state.embedder.embed(ch)})
        store.add_feature_chunks(fid, pid, chunks)
        jid = launch_job("generate", {"feature_id": fid, "text": base_raw, "focus": focus_d,
                                      "total": int(total)},
                         label=f"Generate tests — {name}", project_id=pid, feature_id=fid)
        return {"feature_id": fid, "project_id": pid, "job_id": jid,
                "chars": len(base_raw), "sources": sources, "doc_count": len(sources),
                "chunks": len(chunks)}

    # External sources present → do the (potentially slow) fetching in a background
    # ingest job that reports progress and then chains generation on the same job.
    jid = launch_job("ingest", {
        "feature_id": fid, "project_id": pid, "name": name,
        "base_parts": parts, "base_sources": sources,
        "figma_urls": figma_urls, "pdf_figma": pdf_figma, "crawl_seeds": crawl_seeds,
        "confluence_urls": confluence_urls, "confluence_children": bool(confluence_children),
        "focus": focus_d, "total": int(total)},
        label=f"Ingest & generate — {name}", project_id=pid, feature_id=fid)
    doc_count = len(sources) + len(confluence_urls) + len(figma_urls) + (1 if pdf_figma else 0)
    return {"feature_id": fid, "project_id": pid, "job_id": jid,
            "chars": len(base_raw), "sources": sources, "doc_count": doc_count, "chunks": 0}


def _split_links(values) -> list:
    """Accept a str or list of strings (each possibly holding several URLs separated
    by newlines / commas / spaces) and return a de-duped, order-preserving URL list."""
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values or []:
        for piece in re.split(r"[\s,]+", (v or "").strip()):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return list(dict.fromkeys(out))


@router.post("/api/features/{fid}/regenerate")
def regenerate(fid: str, body: dict):
    """Re-run generation on an existing feature with a different depth/focus
    (adds new cases; dedup keeps existing ones)."""
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    focus = body.get("focus")
    if isinstance(focus, str):
        try:
            focus = _json.loads(focus)
        except Exception:  # noqa: BLE001
            focus = None
    total = int(body.get("total", GEN_TOTAL))
    jid = launch_job("generate", {"feature_id": fid, "text": f.get("text", ""),
                                  "focus": focus, "total": total},
                     label=f"Regenerate — {f.get('name')}", project_id=f.get("project_id"),
                     feature_id=fid)
    return {"job_id": jid}


async def _read_corpus(files, text):
    parts, sources = [], []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        try:
            txt = extract_text(f.filename, data)
        except UnsupportedDocumentError as exc:
            raise HTTPException(400, str(exc)) from exc
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    return "\n\n".join(parts), sources


@router.post("/api/features/{fid}/versions")
async def new_version(fid: str, text: str = Form(""), name: str = Form(""), key: str = Form(""),
                      focus: str = Form(""), total: int = Form(16), replace: str = Form("false"),
                      confluence_url: list[str] = Form(default=[]),
                      confluence_children: bool = Form(True),
                      figma_url: list[str] = Form(default=[]),
                      files: list[UploadFile] = File(None)):
    prev = store.get_feature(fid)
    if not prev:
        raise HTTPException(404, "feature not found")
    # Read uploaded docs + pasted text; collect any links embedded in PDFs.
    parts, sources, pdf_urls = [], [], []
    for f in (files or []):
        if not f or not f.filename:
            continue
        data = await f.read()
        try:
            txt = extract_text(f.filename, data)
        except UnsupportedDocumentError as exc:
            raise HTTPException(400, str(exc)) from exc
        if txt.strip():
            parts.append(f"### Document: {f.filename}\n{txt}")
            sources.append(f.filename)
        if f.filename.lower().endswith(".pdf"):
            pdf_urls.extend(extractmod.pdf_links(data))
    if (text or "").strip():
        parts.append(f"### Pasted requirement\n{text}")
        sources.append("pasted")
    # External sources: multiple Figma + Confluence links, plus links inside PDFs.
    confluence_urls = _split_links(confluence_url)
    figma_urls = _split_links(figma_url)
    pdf_figma = [u for u in pdf_urls if "figma.com" in u.lower()]
    crawl_seeds = [u for u in pdf_urls if "figma.com" not in u.lower()]
    for u in figma_urls:
        if not figma.Figma.file_key_from_url(u):
            raise HTTPException(400, f"could not read a Figma file key from: {u[:80]}")
    if (figma_urls or pdf_figma) and not figma_client().ok():
        raise HTTPException(400, "Figma token not configured — add a Figma access token in Settings")
    if confluence_urls and not jira_client().ok():
        raise HTTPException(400, "Confluence not configured — set Jira base URL, email & API token in Settings")
    figma_data, _warnings = _gather_external(
        parts, sources, figma_urls=figma_urls, pdf_figma=pdf_figma,
        confluence_urls=confluence_urls, confluence_children=bool(confluence_children),
        crawl_seeds=crawl_seeds)
    raw = "\n\n".join(parts)
    if not raw.strip():
        raise HTTPException(400, "no document text provided")
    emb = state.embedder.embed(raw[:2000])
    try:
        focus_d = _json.loads(focus) if focus else None
    except Exception:  # noqa: BLE001
        focus_d = None
    prev_cases = store.cases_brief(store.feature_test_case_ids(fid))
    is_replace = str(replace).lower() == "true"

    if is_replace:
        removed = store.reset_feature_content(fid)
        summary = _generate_feature_summary(prev.get("name", "Feature"), raw)
        store.update_feature_doc(fid, sources, raw, summary, emb)
        newfid = fid
        diff_summary = {"mode": "replace", "version": int(prev.get("version", 1)),
                        "kept": 0, "retired": [], "retired_orphans": removed}
    else:
        new_v = int(prev.get("version", 1)) + 1
        eff_key = (key or "").strip() or prev.get("key")
        prev_group = prev.get("group_id", fid)
        if eff_key and store.epic_bound_group(prev["project_id"], eff_key,
                                              exclude_group_id=prev_group):
            raise HTTPException(409, f"Epic '{eff_key}' is already associated with another feature")
        summary = _generate_feature_summary(name or prev["name"], raw)
        newfid = store.create_feature(name or prev["name"], prev["project_id"], sources, raw,
                                      summary, emb, key=eff_key, match_key=prev.get("match_key"),
                                      group_id=prev_group, version=new_v)
        diff = cov.diff_versions(current_llm(), prev.get("text", ""), raw, prev_cases)
        keep = set(diff.get("keep", []))
        for cid in keep:
            store.associate(newfid, cid, "carried", None)
        by_id = {c["id"]: c for c in prev_cases}
        retired = [{"id": r["id"], "title": (by_id.get(r["id"]) or {}).get("title"),
                    "reason": r.get("reason", "")} for r in diff.get("retire", [])]
        diff_summary = {"mode": "version", "version": new_v, "kept": len(keep), "retired": retired}
    store.set_version_diff(newfid, diff_summary)
    if figma_data:
        store.set_feature_figma(newfid, figma_data)

    chunks = []
    for i, ch in enumerate(chunk_doc(raw, max_chars=1200, overlap=150)):
        chunks.append({"source": sources[0] if sources else "combined", "chunk_index": i,
                       "text": ch, "embedding": state.embedder.embed(ch)})
    store.add_feature_chunks(newfid, prev["project_id"], chunks)
    jid = launch_job("generate", {"feature_id": newfid, "text": raw, "focus": focus_d,
                                  "total": int(total)},
                     label=f"Generate v{diff_summary['version']} — {prev.get('name')}",
                     project_id=prev["project_id"], feature_id=newfid)
    return {"feature_id": newfid, "version": diff_summary["version"], "diff": diff_summary,
            "job_id": jid}


@router.get("/api/features")
def list_features(request: Request, project_id: str | None = None):
    user = _current_user(request)
    if project_id is not None:
        _require_project(request, project_id)
        return {"features": store.list_features(project_id)}
    feats = store.list_features(None)
    allowed = _allowed_project_ids(user)
    if allowed is not None:
        feats = [f for f in feats if f.get("project_id") in allowed]
    return {"features": feats}


@router.get("/api/features/{fid}")
def get_feature(fid: str, request: Request):
    _require_feature_project(request, fid)
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    f["summary"] = _display_feature_summary(f)
    f["test_cases"] = store.get_feature_cases(fid)
    return f


class AssociateIn(BaseModel):
    case_id: str


@router.post("/api/features/{fid}/associate")
def associate(fid: str, body: AssociateIn):
    store.associate(fid, body.case_id, "manual", None)
    return {"associated": body.case_id}


class ReadyThresholdIn(BaseModel):
    threshold: int = 80


@router.post("/api/features/{fid}/ready-threshold")
def set_ready_threshold(fid: str, body: ReadyThresholdIn):
    """Set the feature's QA-readiness threshold (percent code coverage; editor+)."""
    if not store.get_feature(fid):
        raise HTTPException(404, "feature not found")
    return {"ready_threshold": store.set_feature_ready_threshold(fid, body.threshold)}


class RenameIn(BaseModel):
    name: str | None = None
    key: str | None = None


@router.patch("/api/features/{fid}")
def rename_feature(fid: str, body: RenameIn):
    if body.key is not None and (body.key or "").strip():
        f = store.get_feature(fid)
        if not f:
            raise HTTPException(404, "feature not found")
        ek = body.key.strip()
        if store.epic_bound_group(f["project_id"], ek,
                                  exclude_group_id=f.get("group_id", fid)):
            raise HTTPException(409, f"Epic '{ek}' is already associated with another feature")
    store.rename_feature(fid, body.name, body.key)
    return {"ok": True}


@router.delete("/api/features/{fid}")
def delete_feature(fid: str):
    result = store.delete_feature(fid)
    if not result:
        raise HTTPException(404, "feature not found")
    return result
