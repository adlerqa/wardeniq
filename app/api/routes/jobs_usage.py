"""Background job listing/status/retry (SSE streaming included), the embedding-
model switch (which launches a re-embed migration job), and the usage/billing
dashboard.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 15/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 6 routes + 1 model were one contiguous block in the original main.py; no
shared-helper deviation was needed (store, launch_job, JOB_WORKERS,
_allowed_project_ids, _current_user, _require_job_project, current_ollama_url,
_ext_error, Embedder, and crypto were all already centralized in earlier phases).
"""
import json

import crypto
import usage
from embeddings import Embedder

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import GEN_TOTAL
from core.deps import _ext_error, current_ollama_url
from core.security import _allowed_project_ids, _current_user, _require_job_project
from core.state import store
from workers.registry import JOB_WORKERS, launch_job

router = APIRouter()


@router.get("/api/jobs")
def jobs_list(request: Request, status: str | None = None, type: str | None = None, limit: int = 60):
    jobs = store.list_jobs(limit=limit, status=status, jtype=type)
    allowed = _allowed_project_ids(_current_user(request))
    if allowed is not None:
        # Keep jobs whose project is allowed; hide global (project-less) jobs from
        # scoped users.
        jobs = [j for j in jobs if j.get("project_id") in allowed]
    return {"jobs": jobs}


@router.get("/api/usage")
def usage_dashboard(project_id: str | None = None):
    """LLM/embedding token usage + cost: totals, per-model, per-project, and
    recent processes. Cost is priced live from the current Settings price table."""
    prices = store.get_settings().get("llm_prices") or {}
    return store.usage_summary(project_id=project_id, prices=prices)


class CostEstimateIn(BaseModel):
    text_length: int = 0
    total: int | None = None


@router.post("/api/usage/estimate")
def estimate_cost(body: CostEstimateIn):
    """Pre-run cost estimate for a generation run (issue #22): a rough USD range
    (or an explanatory note when a dollar figure isn't meaningful) computed from
    the extracted document length and the target case count, using the same
    provider/model/pricing a real run would use right now."""
    s = store.get_settings()
    provider = s.get("llm_provider", "ollama")
    model = s.get("llm_model", "")
    prices = s.get("llm_prices") or {}
    total = body.total if body.total is not None else GEN_TOTAL
    return usage.estimate_generation_cost(
        text_length=max(0, body.text_length), total=total,
        provider=provider, model=model, prices=prices,
    )


class EmbeddingIn(BaseModel):
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    region: str | None = None


@router.post("/api/embedding/switch")
def switch_embedding(body: EmbeddingIn):
    """Validate a new embedding model (probe its true dimension), persist it, and
    launch the re-embed + reindex migration. Search is degraded until it completes."""
    provider = (body.provider or "ollama").strip()
    model = (body.model or "").strip()
    if not model:
        raise HTTPException(400, "an embedding model name is required")
    s = store.get_settings()
    # reuse the stored key if the caller didn't supply a new one
    key = (body.api_key or "").strip() or (
        crypto.decrypt(s.get("embed_api_key_enc", "")) if s.get("embed_api_key_enc") else "")
    region = (body.region or "").strip() if body.region is not None else s.get("embed_region", "")
    # Bedrock authenticates via region + (IAM role or access:secret in api_key),
    # so it doesn't require a standalone API key the way other hosted providers do.
    if provider not in ("ollama", "bedrock") and not key:
        raise HTTPException(400, f"{provider} needs an API key")
    trial = Embedder(provider=provider, model=model, api_key=key,
                     base_url=(body.base_url or "").strip(), ollama_url=current_ollama_url(),
                     region=region)
    # Probe: confirms connectivity/auth AND measures the true output dimension.
    try:
        dim = trial.probe_dim()
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Embedding provider", e)
    if not dim or dim < 8:
        raise HTTPException(400, "embedding provider returned an invalid vector")
    upd = {"embed_provider": provider, "embed_model": model,
           "embed_base_url": (body.base_url or "").strip(),
           "embed_region": region, "embed_dim": int(dim)}
    if body.api_key is not None:
        upd["embed_api_key_enc"] = crypto.encrypt(body.api_key) if body.api_key else ""
    store.save_settings(upd)
    jid = launch_job("reembed", {"dim": int(dim)},
                     label=f"Re-embed all vectors → {provider}/{model} ({dim}-d)")
    return {"job_id": jid, "provider": provider, "model": model, "dim": int(dim)}


@router.get("/api/jobs/{jid}")
def job_get(jid: str, request: Request):
    j = _require_job_project(request, jid)
    j.pop("params", None)   # may contain large text
    return j


@router.get("/api/jobs/{jid}/stream")
def job_stream(jid: str, request: Request):
    _require_job_project(request, jid)
    from fastapi.responses import StreamingResponse
    import asyncio

    async def events():
        last_signature = None
        while True:
            job = store.get_job(jid)
            if not job:
                yield f"event: error\ndata: {json.dumps({'status': 'not_found', 'job_id': jid})}\n\n"
                break
            payload = {
                "id": job["id"],
                "type": job.get("type"),
                "status": job.get("status"),
                "stage": job.get("stage"),
                "progress": job.get("progress", 0),
                "logs": job.get("logs", []),
                "result": job.get("result", {}),
                "error": job.get("error"),
            }
            signature = json.dumps(payload, sort_keys=True, default=str)
            if signature != last_signature:
                yield f"event: update\ndata: {json.dumps(payload, default=str)}\n\n"
                last_signature = signature
            else:
                yield ": keep-alive\n\n"
            if job.get("status") in {"succeeded", "failed"}:
                yield f"event: done\ndata: {json.dumps(payload, default=str)}\n\n"
                break
            await asyncio.sleep(0.75)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/jobs/{jid}/retry")
def job_retry(jid: str, request: Request):
    j = _require_job_project(request, jid)
    if j["type"] not in JOB_WORKERS:
        raise HTTPException(400, f"job type '{j['type']}' cannot be retried")
    nid = launch_job(j["type"], j.get("params", {}), label=j.get("label", "") + " (retry)",
                     project_id=j.get("project_id"), feature_id=j.get("feature_id"))
    return {"job_id": nid}
