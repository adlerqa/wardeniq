"""System/misc endpoints: health/status (Mongo connectivity, embedding + LLM
health, thresholds), the dashboard summary, the global tag list, RAG
"retrieve" (find existing test cases relevant to a new requirement), and the
GitHub sync-poller status.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router
19/20). Handler bodies are unchanged aside from the ``@app.`` -> ``@router.``
decorator swap.

These 5 routes + 1 model were three non-contiguous blocks in the original
main.py (status; then dashboard/tags/RetrieveIn/retrieve; then sync_status,
~20 lines later, past the now-extracted develop/webhook routes). ``_trunc``
(only used by ``retrieve``) moves with it. No new shared-helper deviation was
needed: store, BOOT, current_llm/current_poll_interval, and the core.config
constants were already centralized in earlier phases.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import state
from core.bootstrap import BOOT
from core.config import CASE_AUTO, GITHUB_TOKEN, STEP_AUTO, SUGGEST, VERSION
from core.deps import current_llm, current_poll_interval
from core.state import SYNC, store

router = APIRouter()


@router.get("/api/healthz")
def healthz():
    """Lightweight readiness probe for the app container."""
    try:
        ready = store.ping()
    except Exception:  # noqa: BLE001
        ready = False
    if not ready:
        raise HTTPException(503, "datastore unavailable")
    return {"status": "ok"}


@router.get("/api/status")
def status():
    ok = False
    try:
        ok = store.ping()
    except Exception:  # noqa: BLE001
        pass
    return {"app": "wardenIQ", "version": VERSION, "boot": BOOT, "mongo_connected": ok,
            "counts": store.counts() if ok else {},
            "indexes": store.index_status() if ok else {},
            "embedding": {"provider": state.embedder.provider, "model": state.embedder.model,
                          "dims": state.embedder.dim, "health": state.embedder.health()},
            "llm": (lambda lm: {"model": lm.model, "provider": lm.provider, "health": lm.health()})(current_llm()),
            "thresholds": {"step_auto_reuse": STEP_AUTO, "case_auto_reuse": CASE_AUTO,
                           "suggest": SUGGEST}}


@router.get("/api/dashboard")
def dashboard():
    try:
        return store.dashboard()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))


@router.get("/api/tags")
def tags():
    return {"tags": store.all_tags()}


class RetrieveIn(BaseModel):
    text: str
    type: str | None = None
    limit: int = 8


@router.post("/api/retrieve")
def retrieve(req: RetrieveIn):
    """RAG: find existing test cases relevant to a new requirement (for reuse)."""
    emb = state.embedder.embed(req.text, task="query")
    results, pipeline = store.search_cases(emb, limit=req.limit, ctype=req.type)
    return {"query": req.text, "results": results, "pipeline": _trunc(pipeline)}


@router.get("/api/sync/status")
def sync_status():
    return {**SYNC, "poll_interval_s": current_poll_interval(),
            "github_authenticated": bool(GITHUB_TOKEN)}


def _trunc(pipeline):
    import copy
    p = copy.deepcopy(pipeline)
    for st in p:
        vs = st.get("$vectorSearch")
        if vs and isinstance(vs.get("queryVector"), list):
            full = vs["queryVector"]
            vs["queryVector"] = [round(v, 4) for v in full[:6]] + [f"...({len(full)} dims)"]
    return p
