#!/usr/bin/env python3
"""
Live-Atlas RAG evaluation harness for wardenIQ test-case generation.
=====================================================================

WHAT THIS DOES
--------------
Runs the REAL generate_fresh_testcases_pipeline() against REAL, already-ingested
feature documents in your live database, through the REAL currently-configured
embedding model and LLM (whatever Settings has selected right now -- nothing in
this script is hardcoded to Nomic or Ollama; it reads state.embedder.provider/
model/dim at runtime). For each selected feature it captures:

  - the exact retrieval query text built for each of the 4 retrieval categories
    (api / ui / e2e / business) -- _build_api_retrieval_query() etc. in
    testgen/service.py, unmodified
  - every retrieved chunk's id, document position (chunk_index), source, score,
    and full text, for every one of those 4 category retrievals
  - a POSITIONAL BASELINE per category/top_k: the first-N chunks for the same
    feature ordered by chunk_index ascending, with no category distinction and
    no semantic ranking -- this reproduces the retrieval strategy ("select the
    first chunks by document position") this RAG project replaced, so the
    report can show a real before/after rather than an assumed one
  - prompt size (characters) WITH vs WITHOUT the retrieved-evidence block, for
    every prompt-builder call that takes rag_context (business, e2e/edge/
    business combined call, api, ui) -- computed by calling the real,
    unmodified prompt-builder function twice (once with the real rag_context,
    once with rag_context forced to None), so this is a genuine before/after
    of the CURRENT code, not a guess
  - generated test counts by all 5 product test types (api_tests,
    ui_validations, e2e_tests, edge_cases, business_tests), read directly from
    the pipeline's own return value (out["by_type"])
  - the pipeline's own requirement-coverage-gap output (_requirement_gaps()),
    including the actual gap requirement text, not just the count
  - wall-clock latency per LLM call (labelled by the prompt's own "TASK: ..."
    header) and for the run as a whole
  - errors/warnings surfaced by the pipeline itself, including the
    "search degraded" dedup warning if it fires
  - the full raw stdout of the run (the existing [TestGen]/[TestGen][rag]/
    [store][feature_chunks] instrumentation already in the codebase), tee'd to
    both your terminal and the per-feature log file, so you get the atlas-vs-
    numpy-fallback source line and everything else for free

WHAT THIS DOES NOT DO
----------------------
- It does not modify any file under app/. Everything above is captured by
  monkeypatching function REFERENCES on already-imported module objects, in
  this process only, for the duration of this script, then restored. Nothing
  is written back to testgen/service.py, testgen/prompt_builder.py, or
  store/features.py. Run `git status` after this script exits -- it should
  show nothing changed under app/.
- It does not judge chunk relevance, grounding, or requirement coverage for
  you. It computes one cheap, transparent HEURISTIC signal per chunk (does the
  chunk contain the kind of language that category's evidence should contain)
  as a fast first pass, but the definitive judgment -- reading actual chunk
  text against actual query and category -- happens in the follow-up analysis
  pass over the JSON this script writes.
- It does not pick "representative" features for you unless you ask it to.
  Use --feature-ids to pin exact features you already know are good test
  cases, or --auto-select N to let a keyword/position heuristic propose N
  candidates from your live corpus (see SELECTION HEURISTIC below). Always
  eyeball --list-candidates output before trusting the auto-selection.

HOW TO RUN
----------
From the wardeniq repo root, with your venv activated and the docker stack
(mongod / mongot / ollama / backend) up and reachable the same way the app
itself reaches them (i.e. run this from wherever `python -m app.main` or your
worker process normally runs, so MONGO_URI / OLLAMA_URL resolve the same way):

    source .venv/bin/activate
    PYTHONPATH=app python scripts/eval_rag_live.py --list-candidates
    PYTHONPATH=app python scripts/eval_rag_live.py --auto-select 3
    PYTHONPATH=app python scripts/eval_rag_live.py --feature-ids <id1>,<id2>,<id3>

Add --retrieval-only to skip the full generation pipeline (no LLM generation
calls, just the 4 category retrievals + positional baseline + query text --
much faster, useful for a first pass before committing to full runs which
call your local LLM many times per feature).

Results: eval_runs/<feature_id>_<timestamp>.json (one per feature, full
capture) and eval_runs/<feature_id>_<timestamp>.log (raw stdout tee).
Nothing is printed that isn't also in the JSON/log -- console narration is
just so you can watch it work.

SELECTION HEURISTIC (only used without --feature-ids)
-------------------------------------------------------
Scans store.features for already-ingested documents (have >=1 fchunks row)
and scores each using the same kind of keyword families the pipeline itself
uses (REQUIREMENT_MARKERS-style rule language reused directly from
testgen.service, HTTP-method+path patterns, UI-control terms, flow/journey
terms), recording the POSITION of each hit within the raw text (0.0 = start,
1.0 = end), bucketed into thirds. It proposes:

  - "late_critical": the feature where at least one category's keyword hits
    are most concentrated in the LAST third -- the scenario the original
    position-based retrieval would have missed entirely
  - "distributed": the feature where hits for the most distinct categories
    (out of api/ui/e2e/business) appear in the most distinct thirds -- the
    scenario needed to check the 4 retrieval contexts actually differentiate
    evidence rather than all converging on the same chunks
  - "typical": the longest remaining candidate not already picked, as a
    plain baseline run

This is a pre-filter to point you at good candidates quickly, not a claim of
ground truth about any document's content -- always run --list-candidates
first and sanity-check the printed scores before trusting --auto-select.
"""
import argparse
import contextlib
import io
import json
import re
import sys
import time
from pathlib import Path

# --- make the app package importable regardless of cwd ------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_APP_DIR_CANDIDATES = [_THIS_DIR.parent / "app", _THIS_DIR / "app", Path.cwd() / "app"]
for _candidate in _APP_DIR_CANDIDATES:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break

import core.state as state          # noqa: E402  -- real Store singleton, real Embedder
from core.deps import current_llm   # noqa: E402  -- real LLM, built from live Settings
import testgen.service as svc       # noqa: E402
import testgen.prompt_builder as pb # noqa: E402


# =====================================================================================
# Candidate selection heuristic (only used without --feature-ids)
# =====================================================================================

_API_PATTERN = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[^\s,;]+", re.IGNORECASE)
_UI_PATTERN = re.compile(
    r"\b(button|field|input|dropdown|checkbox|toggle|picker|selector|screen|"
    r"form|tap|click|modal|dialog|placeholder|label)\b", re.IGNORECASE,
)
_E2E_PATTERN = re.compile(
    r"\b(flow|journey|step|scenario|navigates?|redirect|then\s+the\s+user|"
    r"user\s+(?:clicks?|taps?|enters?|submits?)|end-to-end)\b", re.IGNORECASE,
)
_BUSINESS_PATTERN = svc.REQUIREMENT_MARKERS

CATEGORY_PATTERNS = {
    "api": _API_PATTERN,
    "ui": _UI_PATTERN,
    "e2e": _E2E_PATTERN,
    "business": _BUSINESS_PATTERN,
}


def _third(position_fraction: float) -> int:
    return 0 if position_fraction < 1 / 3 else (1 if position_fraction < 2 / 3 else 2)


def _score_feature_text(text: str) -> dict:
    """Per-category hit count and which document-thirds each category's hits land
    in. Used only to rank candidates for --auto-select / --list-candidates -- never
    used by the actual pipeline run itself."""
    n = max(1, len(text))
    per_category = {}
    for name, pattern in CATEGORY_PATTERNS.items():
        thirds_hit = set()
        count = 0
        last_third_count = 0
        for match in pattern.finditer(text):
            count += 1
            frac = match.start() / n
            third = _third(frac)
            thirds_hit.add(third)
            if third == 2:
                last_third_count += 1
        per_category[name] = {
            "hits": count,
            "thirds_hit": sorted(thirds_hit),
            "last_third_hits": last_third_count,
            "last_third_share": (last_third_count / count) if count else 0.0,
        }
    return per_category


def list_candidates(limit: int = 500) -> list:
    """Every ingested feature (has >=1 fchunks row), scored for selection."""
    out = []
    for f in state.store.features.find({}, {"text": 1, "name": 1, "project_id": 1}).limit(limit):
        fid = str(f["_id"])
        chunk_count = state.store.fchunks.count_documents({"feature_id": fid})
        if chunk_count == 0:
            continue
        text = str(f.get("text") or "")
        if len(text) < 500:
            continue
        scores = _score_feature_text(text)
        distinct_categories_with_hits = sum(1 for v in scores.values() if v["hits"] > 0)
        distinct_thirds_covered = len(set().union(*(set(v["thirds_hit"]) for v in scores.values())))
        max_last_third_share = max((v["last_third_share"] for v in scores.values()), default=0.0)
        out.append({
            "feature_id": fid,
            "name": f.get("name"),
            "project_id": f.get("project_id"),
            "text_chars": len(text),
            "chunk_count": chunk_count,
            "category_scores": scores,
            "distinct_categories_with_hits": distinct_categories_with_hits,
            "distinct_thirds_covered": distinct_thirds_covered,
            "max_last_third_share": round(max_last_third_share, 3),
        })
    return out


def auto_select(n: int) -> list:
    candidates = list_candidates()
    if not candidates:
        return []
    picked, picked_ids = [], set()

    late_critical = sorted(
        candidates, key=lambda c: (c["max_last_third_share"], c["text_chars"]), reverse=True,
    )
    if late_critical and late_critical[0]["max_last_third_share"] > 0:
        picked.append({**late_critical[0], "selection_reason": "late_critical"})
        picked_ids.add(late_critical[0]["feature_id"])

    remaining = [c for c in candidates if c["feature_id"] not in picked_ids]
    distributed = sorted(
        remaining,
        key=lambda c: (c["distinct_categories_with_hits"], c["distinct_thirds_covered"], c["text_chars"]),
        reverse=True,
    )
    if distributed and len(picked) < n:
        picked.append({**distributed[0], "selection_reason": "distributed"})
        picked_ids.add(distributed[0]["feature_id"])

    remaining = [c for c in candidates if c["feature_id"] not in picked_ids]
    typical = sorted(remaining, key=lambda c: c["text_chars"], reverse=True)
    for c in typical:
        if len(picked) >= n:
            break
        picked.append({**c, "selection_reason": "typical"})
        picked_ids.add(c["feature_id"])

    return picked[:n]


# =====================================================================================
# Positional baseline ("the original problem": first chunks by document position)
# =====================================================================================

def positional_baseline(feature_id: str, top_k: int) -> list:
    docs = list(
        state.store.fchunks.find(
            {"feature_id": feature_id}, {"chunk_index": 1, "source": 1, "text": 1},
        ).sort("chunk_index", 1).limit(top_k)
    )
    return [
        {
            "chunk_id": str(d["_id"]),
            "chunk_index": d.get("chunk_index"),
            "source": d.get("source"),
            "text": d.get("text", ""),
        }
        for d in docs
    ]


# =====================================================================================
# Lightweight relevance heuristic (first-pass signal only -- see module docstring)
# =====================================================================================

def _heuristic_relevance(category: str, text: str) -> dict:
    pattern = CATEGORY_PATTERNS.get(category)
    hits = len(pattern.findall(text)) if pattern else 0
    return {"category_keyword_hits": hits, "looks_relevant_heuristic": hits > 0}


# =====================================================================================
# Instrumentation: monkeypatch function REFERENCES on already-imported modules only.
# Nothing here writes to any file. Everything is restored in run_one_feature()'s
# `finally` block.
# =====================================================================================

class Recorder:
    def __init__(self):
        self.retrieval_calls = []       # one per search_feature_chunks() call
        self.query_texts = {}           # category -> query text
        self.prompt_sizes = []          # one per wrapped prompt-builder call
        self.llm_calls = []             # one per call_llm_json_with_repair call
        self.requirement_gaps = None    # captured return of _requirement_gaps()

    def as_dict(self):
        return {
            "retrieval_calls": self.retrieval_calls,
            "query_texts": self.query_texts,
            "prompt_sizes": self.prompt_sizes,
            "llm_calls": self.llm_calls,
            "requirement_gaps": self.requirement_gaps,
        }


def _task_label(user_prompt: str) -> str:
    first_line = (user_prompt or "").strip().splitlines()[0] if user_prompt else ""
    return first_line[6:].strip() if first_line.startswith("TASK:") else first_line[:80]


def _prompt_char_len(prompt) -> int:
    """build_business_test_prompt()/build_e2e_agent_prompt() return a raw prompt
    string; build_api_agent_prompt()/build_ui_agent_prompt() return
    {"messages": [{"role", "content"}, ...]} instead -- measure whichever shape
    comes back by total character count of everything that will actually be sent
    to the LLM, not len() of the container itself (a dict's len() is its key
    count, not remotely a size in characters)."""
    if isinstance(prompt, str):
        return len(prompt)
    if isinstance(prompt, dict) and isinstance(prompt.get("messages"), list):
        return sum(len(str(m.get("content") or "")) for m in prompt["messages"] if isinstance(m, dict))
    return len(str(prompt))


@contextlib.contextmanager
def instrumented(rec: Recorder):
    originals = {}

    def _wrap_query_builder(name, category):
        original = getattr(svc, name)

        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            rec.query_texts[category] = result
            return result
        originals[("svc", name)] = original
        setattr(svc, name, wrapper)

    _wrap_query_builder("_build_api_retrieval_query", "api")
    _wrap_query_builder("_build_ui_retrieval_query", "ui")
    _wrap_query_builder("_build_e2e_retrieval_query", "e2e")
    _wrap_query_builder("_build_business_retrieval_query", "business")

    # search_feature_chunks: patched on the STORE INSTANCE (not the class), so only
    # this run's calls are captured and every other consumer of the same store object
    # elsewhere in a live process is unaffected once we restore it below.
    original_search = state.store.search_feature_chunks

    def wrapped_search(query_embedding, feature_id, limit=8, category=None):
        t0 = time.time()
        result = original_search(query_embedding, feature_id, limit=limit, category=category)
        elapsed = time.time() - t0
        rec.retrieval_calls.append({
            "category": category,
            "feature_id": feature_id,
            "top_k": limit,
            "query_embedding_dim": len(query_embedding) if query_embedding else 0,
            "elapsed_seconds": round(elapsed, 4),
            "results": [
                {
                    "chunk_id": r.get("chunk_id"),
                    "chunk_index": r.get("chunk_index"),
                    "source": r.get("source"),
                    "score": r.get("score"),
                    "text": r.get("text", ""),
                    **_heuristic_relevance(category, r.get("text", "")),
                }
                for r in result
            ],
        })
        return result
    originals[("store_instance", "search_feature_chunks")] = original_search
    state.store.search_feature_chunks = wrapped_search

    # Prompt-size before/after: wrap the prompt-builder names bound INTO svc's own
    # namespace (svc did `from testgen.prompt_builder import build_business_test_prompt`
    # etc., so patching pb.build_business_test_prompt would NOT affect svc's already-
    # bound name -- we patch svc.build_business_test_prompt directly).
    def _wrap_business_prompt():
        original = svc.build_business_test_prompt

        def wrapper(context, rag_context=None, top_k=6):
            after = original(context, rag_context, top_k=top_k)
            before = original(context, None, top_k=top_k)
            rec.prompt_sizes.append({
                "call": "build_business_test_prompt",
                "chars_before_rag": _prompt_char_len(before),
                "chars_after_rag": _prompt_char_len(after),
                "chars_added_by_rag": _prompt_char_len(after) - _prompt_char_len(before),
            })
            return after
        originals[("svc", "build_business_test_prompt")] = original
        svc.build_business_test_prompt = wrapper
    _wrap_business_prompt()

    def _wrap_e2e_prompt():
        original = svc.build_e2e_agent_prompt

        def wrapper(context, pruned_api_dictionary, pruned_ui_dictionary, rag_context,
                    discovered_api_surface=None, top_k=6, api_rag_context=None, api_top_k=8,
                    business_rag_context=None, business_top_k=6):
            after = original(
                context, pruned_api_dictionary, pruned_ui_dictionary, rag_context,
                discovered_api_surface, top_k, api_rag_context, api_top_k,
                business_rag_context, business_top_k,
            )
            before = original(
                context, pruned_api_dictionary, pruned_ui_dictionary, None,
                discovered_api_surface, top_k, None, api_top_k, None, business_top_k,
            )
            rec.prompt_sizes.append({
                "call": "build_e2e_agent_prompt",
                "chars_before_rag": _prompt_char_len(before),
                "chars_after_rag": _prompt_char_len(after),
                "chars_added_by_rag": _prompt_char_len(after) - _prompt_char_len(before),
            })
            return after
        originals[("svc", "build_e2e_agent_prompt")] = original
        svc.build_e2e_agent_prompt = wrapper
    _wrap_e2e_prompt()

    def _wrap_api_prompt():
        original = svc.build_api_agent_prompt

        def wrapper(context, rag_context, values, mode, top_k=8):
            after = original(context, rag_context, values, mode, top_k=top_k)
            before = original(context, None, values, mode, top_k=top_k)
            rec.prompt_sizes.append({
                "call": f"build_api_agent_prompt[{mode}]",
                "chars_before_rag": _prompt_char_len(before),
                "chars_after_rag": _prompt_char_len(after),
                "chars_added_by_rag": _prompt_char_len(after) - _prompt_char_len(before),
            })
            return after
        originals[("svc", "build_api_agent_prompt")] = original
        svc.build_api_agent_prompt = wrapper
    _wrap_api_prompt()

    def _wrap_ui_prompt():
        original = svc.build_ui_agent_prompt

        def wrapper(context, chunk, rag_context, top_k=8):
            after = original(context, chunk, rag_context, top_k=top_k)
            before = original(context, chunk, None, top_k=top_k)
            rec.prompt_sizes.append({
                "call": "build_ui_agent_prompt",
                "chars_before_rag": _prompt_char_len(before),
                "chars_after_rag": _prompt_char_len(after),
                "chars_added_by_rag": _prompt_char_len(after) - _prompt_char_len(before),
            })
            return after
        originals[("svc", "build_ui_agent_prompt")] = original
        svc.build_ui_agent_prompt = wrapper
    _wrap_ui_prompt()

    # LLM call latency + size, labelled by the prompt's own "TASK: ..." header.
    original_llm_call = svc.call_llm_json_with_repair

    def wrapped_llm_call(llm, system_prompt, user_prompt, max_tokens=4000, attempts=2, timeout_seconds=None):
        t0 = time.time()
        try:
            result = original_llm_call(llm, system_prompt, user_prompt, max_tokens, attempts, timeout_seconds)
            ok = True
        except Exception as exc:  # noqa: BLE001 -- record the failure, then re-raise
            elapsed = time.time() - t0
            rec.llm_calls.append({
                "task": _task_label(user_prompt),
                "prompt_chars": len(system_prompt or "") + len(user_prompt or ""),
                "elapsed_seconds": round(elapsed, 3),
                "ok": False,
                "error": str(exc),
            })
            raise
        elapsed = time.time() - t0
        rec.llm_calls.append({
            "task": _task_label(user_prompt),
            "prompt_chars": len(system_prompt or "") + len(user_prompt or ""),
            "elapsed_seconds": round(elapsed, 3),
            "ok": ok,
        })
        return result
    originals[("svc", "call_llm_json_with_repair")] = original_llm_call
    svc.call_llm_json_with_repair = wrapped_llm_call

    # Requirement-coverage gaps: capture the pipeline's own gap list (not just the
    # count already in out["rag_gap_count"]).
    original_gaps = svc._requirement_gaps

    def wrapped_gaps(raw_text, suites):
        result = original_gaps(raw_text, suites)
        rec.requirement_gaps = result
        return result
    originals[("svc", "_requirement_gaps")] = original_gaps
    svc._requirement_gaps = wrapped_gaps

    try:
        yield rec
    finally:
        for (target, name), original in originals.items():
            if target == "svc":
                setattr(svc, name, original)
            elif target == "store_instance":
                setattr(state.store, name, original)


# =====================================================================================
# Per-feature run
# =====================================================================================

def run_one_feature(feature_id: str, out_dir: Path, total: int, retrieval_only: bool) -> dict:
    feature = state.store.get_feature(feature_id)
    if not feature:
        return {"feature_id": feature_id, "error": "feature not found"}

    embedder = state.embedder
    settings = state.store.get_settings() if hasattr(state.store, "get_settings") else {}

    context = state.store.build_unified_context(feature_id, int(feature.get("version") or 1))
    context["previousVersionTests"] = []
    context.setdefault("flags", {})["smokeMode"] = False

    log_path = out_dir / f"{feature_id}_{int(time.time())}.log"
    json_path = out_dir / f"{feature_id}_{int(time.time())}.json"

    rec = Recorder()
    stdout_buffer = io.StringIO()
    result = {
        "feature_id": feature_id,
        "feature_name": feature.get("name"),
        "project_id": feature.get("project_id"),
        "raw_text_chars": len(str(feature.get("text") or "")),
        "embedding_config": {
            "provider": embedder.provider,
            "model": embedder.model,
            "dim": embedder.dim,
        },
        "llm_provider": (settings or {}).get("llm_provider", "ollama"),
    }

    class _Tee(io.TextIOBase):
        def __init__(self, *streams):
            self.streams = streams

        def write(self, s):
            for stream in self.streams:
                stream.write(s)
            return len(s)

        def flush(self):
            for stream in self.streams:
                stream.flush()

    with open(log_path, "w") as log_file:
        tee = _Tee(sys.__stdout__, log_file, stdout_buffer)
        with contextlib.redirect_stdout(tee), instrumented(rec):
            # --- positional baselines, one per category top_k, computed BEFORE the
            # real run so they reflect the untouched chunk store -----------------
            is_ollama = ((settings or {}).get("llm_provider", "ollama") == "ollama")
            positional = {
                category: positional_baseline(feature_id, svc._category_top_k(category, is_ollama))
                for category in ("api", "ui", "e2e", "business")
            }
            result["positional_baseline"] = positional

            if retrieval_only:
                # Retrieval-only mode: reproduce exactly what
                # generate_fresh_testcases_pipeline() does through Pass 0/1/2 and the
                # 4 category retrievals, WITHOUT the downstream generation LLM calls.
                # This intentionally duplicates that portion of the real pipeline
                # rather than calling it, so no test-generation LLM calls happen.
                raw_text = str(feature.get("text") or "")
                chunks = list(state.store.fchunks.find({"feature_id": feature_id}))
                rag_context = {
                    "summary": feature.get("summary") or raw_text[:1200],
                    "retrieved_chunks": [
                        {"sourceType": item.get("source", "document"), "score": 1.0, "text": item.get("text", "")}
                        for item in chunks
                    ],
                }
                llm = current_llm()
                t0 = time.time()
                raw_api_spec = pb.build_raw_api_spec_from_documents(context, rag_context)
                context["rawApiSpec"] = raw_api_spec
                spec_apis = svc._parse_raw_api_spec(raw_api_spec)
                grounded = svc.call_llm_json_with_repair(
                    llm, svc.SYSTEM, pb.build_grounded_extraction_prompt(context, rag_context), max_tokens=4000,
                )
                corpus = svc._evidence_corpus(context, rag_context).lower()
                entities = [
                    item for item in pb.filter_hallucinated_entities(
                        svc._as_list(grounded.get("grounded_entities")), corpus,
                    ) if svc._grounded_item_supported(item, corpus)
                ]
                explicit_apis = [
                    item for item in pb.filter_hallucinated_entities(svc._as_list(grounded.get("apis")), corpus)
                    if svc._grounded_item_supported(item, corpus)
                ]
                ui_components = [
                    v for v in svc._as_list(grounded.get("ui_components"))
                    if isinstance(v, dict) and not pb.is_few_shot_leak(v, corpus)
                ] or svc._derive_ui_components(raw_text)
                inferred = []
                if not spec_apis:
                    inferred_result = svc.call_llm_json_with_repair(
                        llm, svc.SYSTEM, pb.build_crud_inference_prompt(entities, context), max_tokens=3000,
                    )
                    inferred = [
                        v for v in svc._as_list(inferred_result.get("apis"))
                        if isinstance(v, dict) and not pb.is_few_shot_leak(v, corpus)
                    ]
                api_surface = svc._merge_api_candidates(explicit_apis, spec_apis, inferred)

                api_query = svc._build_api_retrieval_query(entities, api_surface)
                ui_query = svc._build_ui_retrieval_query(ui_components, context.get("featureName"))
                e2e_query = svc._build_e2e_retrieval_query(
                    context.get("businessContext"), context.get("featureName"), context.get("featureDescription"),
                )
                business_query = svc._build_business_retrieval_query(
                    context.get("businessContext"), context.get("featureName"), context.get("featureDescription"),
                )
                for category, query_text in (
                    ("api", api_query), ("ui", ui_query), ("e2e", e2e_query), ("business", business_query),
                ):
                    top_k = svc._category_top_k(category, is_ollama)
                    if not (query_text or "").strip():
                        continue
                    query_embedding = embedder.embed(query_text, task="query")
                    state.store.search_feature_chunks(query_embedding, feature_id, limit=top_k, category=category)
                result["mode"] = "retrieval_only"
                result["pipeline_out"] = None
                result["elapsed_seconds"] = round(time.time() - t0, 3)
            else:
                params = {"feature_id": feature_id, "total": total, "focus": None, "smoke_mode": False}
                t0 = time.time()
                try:
                    out = svc.generate_fresh_testcases_pipeline(
                        store=state.store, llm=current_llm(), embedder=embedder,
                        params=params, update_job_fn=None,
                    )
                    result["pipeline_out"] = out
                except Exception as exc:  # noqa: BLE001
                    result["pipeline_error"] = str(exc)
                result["mode"] = "full_pipeline"
                result["elapsed_seconds"] = round(time.time() - t0, 3)

    result["instrumentation"] = rec.as_dict()
    with open(json_path, "w") as jf:
        json.dump(result, jf, indent=2, default=str)
    print(f"[eval] wrote {json_path}", flush=True)
    print(f"[eval] wrote {log_path}", flush=True)
    return result


# =====================================================================================
# CLI
# =====================================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feature-ids", type=str, default="", help="Comma-separated feature ids to run exactly.")
    parser.add_argument("--auto-select", type=int, default=0, help="Auto-pick N candidate features (see SELECTION HEURISTIC).")
    parser.add_argument("--list-candidates", action="store_true", help="Print candidate scores and exit -- no generation runs.")
    parser.add_argument("--retrieval-only", action="store_true", help="Skip full generation; capture retrieval + prompt-size deltas only.")
    parser.add_argument("--total", type=int, default=16, help="`total` param passed to the pipeline (default 16, matches app default).")
    parser.add_argument("--output-dir", type=str, default="eval_runs")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.list_candidates:
        candidates = list_candidates()
        print(json.dumps(candidates, indent=2, default=str))
        print(f"\n{len(candidates)} ingested candidate feature(s) found.", flush=True)
        return

    if args.feature_ids:
        feature_ids = [f.strip() for f in args.feature_ids.split(",") if f.strip()]
        selection_meta = [{"feature_id": fid, "selection_reason": "explicit"} for fid in feature_ids]
    elif args.auto_select:
        picked = auto_select(args.auto_select)
        feature_ids = [c["feature_id"] for c in picked]
        selection_meta = picked
        print(json.dumps(picked, indent=2, default=str))
    else:
        parser.error("Pass --feature-ids, --auto-select N, or --list-candidates.")
        return

    print(f"\n[eval] embedding config: provider={state.embedder.provider} "
          f"model={state.embedder.model} dim={state.embedder.dim}", flush=True)
    print(f"[eval] running {len(feature_ids)} feature(s), "
          f"mode={'retrieval_only' if args.retrieval_only else 'full_pipeline'}\n", flush=True)

    results = []
    for fid in feature_ids:
        print(f"\n{'=' * 88}\n[eval] feature_id={fid}\n{'=' * 88}", flush=True)
        result = run_one_feature(fid, out_dir, args.total, args.retrieval_only)
        results.append(result)

    summary_path = out_dir / f"summary_{int(time.time())}.json"
    with open(summary_path, "w") as sf:
        json.dump({"selection": selection_meta, "results": results}, sf, indent=2, default=str)
    print(f"\n[eval] wrote {summary_path}", flush=True)


if __name__ == "__main__":
    main()
