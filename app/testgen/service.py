import concurrent.futures
import json
import os
import re
import time

import usage

from testgen.prompt_builder import (
    build_api_agent_prompt,
    build_business_test_prompt,
    build_crud_inference_prompt,
    build_e2e_agent_prompt,
    build_e2e_fallback_prompt,
    build_fusion_pass_prompt,
    build_grounded_extraction_prompt,
    build_individual_test_repair_prompt,
    build_raw_api_spec_from_documents,
    build_repair_prompt,
    build_ui_agent_prompt,
    filter_hallucinated_entities,
    filter_prompt_exemplar_copies_with_reasons,
    is_few_shot_leak,
    is_prompt_exemplar_copy,
    REASON_DUPLICATE,
    REASON_EDGE_SUPPRESSED,
    REASON_NO_SOURCE_GROUNDING,
)
from testgen.lineage import (
    REUSE_SIMILARITY_API,
    REUSE_SIMILARITY_GENERAL,
    derive_scenario_kind,
    generate_test_identity_hash,
    generate_test_slug,
    lineage_token_set,
    normalize_endpoint,
    referenced_routes,
    routes_incompatible,
    scenario_kinds_incompatible,
    token_set_similarity,
)
SYSTEM = (
    "You are a meticulous senior QA engineer. Read the supplied evidence and produce "
    "grounded, concrete, non-redundant test cases. Respond with one valid JSON object."
)

STEP_AUTO = 0.95
CASE_AUTO = 0.93
SUGGEST = 0.85
API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PRIORITY_ORDER = {"P0": 0, "HIGH": 0, "P1": 1, "MEDIUM": 1, "P2": 2, "LOW": 2, "P3": 3}
REQUIREMENT_MARKERS = re.compile(
    r"\b(must|shall|should|required|cannot|only|never|at least|at most|maximum|minimum|"
    r"reject|prevent|allow|deny|within|before|after)\b",
    re.IGNORECASE,
)


def log_progress(update_fn, stage: str, progress: int | None = None):
    suffix = f" ({progress}%)" if progress is not None else ""
    print(f"[TestGen] {stage}{suffix}", flush=True)
    if update_fn:
        try:
            update_fn(stage=stage, progress=progress)
        except TypeError:
            update_fn(stage)


def _as_list(value):
    return value if isinstance(value, list) else []


def _clean_requirement_narrative(value):
    """Keep source attribution in lineage, not in user-facing testcase prose."""
    text = str(value or "").strip()
    original = text.lower()
    source_name = (
        r"(?:"
        r"(?-i:[A-Z][A-Z0-9_-]{1,20})|"
        r"[\w.-]+\.(?:pdf|docx?|md|txt)|"
        r"(?:prd|hld|lld|spec|specification|document|requirements?|product|business|functional|technical|api|ui|ux|security|"
        r"compliance|architecture|design|uploaded|source|reference)"
        r"(?:\s+[\w.-]+){0,5})"
    )
    source_kind = (
        r"(?:document|docs?|spec(?:ification)?|requirements?|rules?|"
        r"design|architecture|guide|policy|story|ticket|epic|"
        r"acceptance\s+criteria)"
    )
    text = re.sub(
        rf"^according\s+to\s+(?:the\s+)?{source_name}"
        rf"(?:\s+{source_kind})?\s*[,;:]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"^(?:the\s+)?{source_name}(?:\s+{source_kind})?"
        r"\s*(?:rule|requirement)?(?:\s*:\s*|\s+-\s+)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"^(?:the\s+)?{source_name}(?:\s+{source_kind})?\s+"
        r"(?:requires?|states?|specifies?|defines?|indicates?|says?|suggests?|"
        r"allows?|documents?|mandates?|notes?|describes?)"
        r"\s+(?:that\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if "requires" in original:
        text = re.sub(r"\bto be\b", "must be", text, count=1, flags=re.IGNORECASE)
    return text[:1].upper() + text[1:] if text else text


def _json_object(raw):
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    
    # Attempt parsing using json-repair first for maximum robustness
    try:
        import json_repair
        parsed = json_repair.loads(text)
        if isinstance(parsed, dict) and parsed:
            return parsed
    except Exception as repair_exc:
        print(f"[TestGen] json-repair failed to parse raw text: {repair_exc}", flush=True)

    start, end = text.find("{"), text.rfind("}")
    candidate = text[start:end + 1] if start >= 0 and end > start else text
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("LLM response did not contain a non-empty JSON object")
    return parsed


def _raw_llm_call(llm, system_prompt, user_prompt, num_ctx, temperature,
                  max_tokens, timeout_seconds):
    try:
        return llm._raw_chat(
            system_prompt, user_prompt, num_ctx, temperature, max_tokens,
            timeout_seconds=timeout_seconds,
        )
    except TypeError as exc:
        # Test doubles and third-party adapters may still expose the older
        # five-argument method.
        if "timeout_seconds" not in str(exc):
            raise
        return llm._raw_chat(
            system_prompt, user_prompt, num_ctx, temperature, max_tokens
        )


def call_llm_json_with_repair(llm, system_prompt, user_prompt, max_tokens=4000,
                              attempts=2, timeout_seconds=300) -> dict:
    """Retry transport/parse failures and use the model itself to repair malformed JSON."""
    last_error = None
    for attempt in range(1, attempts + 1):
        raw_text = ""
        try:
            # Call _raw_chat directly so we have access to the raw response on parsing failure.
            # Capping context window to 8192 to prevent local Ollama CPU hangs.
            raw_text = _raw_llm_call(
                llm, system_prompt, user_prompt, 8192, 0.1, max_tokens,
                timeout_seconds,
            )
            return _json_object(raw_text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[TestGen] LLM attempt {attempt}/{attempts} failed: {exc}", flush=True)
            if (raw_text or "").strip():
                repair_prompt = (
                    "Repair the following malformed or truncated JSON. Preserve all recoverable "
                    "data and the requested schema. Return one JSON object only.\n\n"
                    f"PARSE ERROR:\n{last_error}\n\nINVALID RESPONSE:\n{raw_text}"
                )
                try:
                    print(f"[TestGen] Attempting to repair malformed JSON (length {len(raw_text)})...", flush=True)
                    repaired = _raw_llm_call(
                        llm,
                        "You repair JSON syntax and output JSON only.",
                        repair_prompt,
                        8192,
                        0.0,
                        max_tokens,
                        timeout_seconds,
                    )
                    return _json_object(repaired)
                except Exception as repair_exc:  # noqa: BLE001
                    print(f"[TestGen] Repair attempt failed: {repair_exc}", flush=True)
                    last_error = repair_exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError(f"LLM JSON generation failed after {attempts} attempts: {last_error}")


# Trailing/wrapping punctuation a regex or LLM extraction can pick up around an
# endpoint that was itself wrapped in markdown (inline code spans, emphasis, or a
# quoted string) in the source PRD/HLD text -- e.g. a line like "`POST /auth/refresh`"
# captures a stray trailing backtick into the endpoint string. Stripped at every site
# an endpoint is captured or normalized so a markdown-wrapped and a clean extraction
# of the SAME endpoint never look like two different endpoints.
_ENDPOINT_JUNK_CHARS = ".)]>`*'\""


def _clean_endpoint(endpoint: str) -> str:
    return str(endpoint or "").strip().strip(_ENDPOINT_JUNK_CHARS)


def _parse_raw_api_spec(raw_spec: str | None) -> list[dict]:
    found = {}
    for line in str(raw_spec or "").splitlines():
        match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s,;]+)", line, re.IGNORECASE)
        if not match:
            continue
        method = match.group(1).upper()
        endpoint = _clean_endpoint(match.group(2))
        key = f"{method}:{normalize_endpoint(endpoint)}"
        found[key] = {
            "method": method,
            "endpoint": endpoint,
            "complexity": "medium",
            "evidence_quote": f"Extracted from rawApiSpec: {method} {endpoint}",
        }
    return list(found.values())


def _api_key(value: dict) -> str:
    return f"{str(value.get('method') or 'GET').upper()}:{normalize_endpoint(value.get('endpoint'))}"


def _merge_api_candidates(*groups) -> list[dict]:
    merged = {}
    for item in (x for group in groups for x in _as_list(group)):
        if not isinstance(item, dict):
            continue
        method = str(item.get("method") or "").upper()
        endpoint = _clean_endpoint(item.get("endpoint") or item.get("path") or "")
        if method not in API_METHODS or not endpoint.startswith("/"):
            continue
        normalized = {**item, "method": method, "endpoint": endpoint}
        merged.setdefault(_api_key(normalized), normalized)
    return list(merged.values())


def _grounded_item_supported(item: dict, corpus: str) -> bool:
    quote = str(item.get("evidence_quote") or "").strip().lower()
    endpoint = str(item.get("endpoint") or item.get("path") or "").strip().lower()
    name = str(item.get("entity") or item.get("name") or "").strip().lower()
    if quote.startswith("extracted from rawapispec:"):
        return True
    if endpoint and endpoint in corpus:
        return True
    if quote and quote in corpus:
        return True
    return bool(name and name in corpus)


def _evidence_corpus(context: dict, rag_context: dict) -> str:
    parts = [
        context.get("featureName"),
        context.get("featureDescription"),
        *(context.get("summaries") or {}).values(),
        context.get("rawApiSpec"),
    ]
    for chunk in _as_list(rag_context.get("retrieved_chunks")):
        if isinstance(chunk, dict):
            parts.append(chunk.get("text") or chunk.get("content"))
    return "\n".join(
        json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        for value in parts if value
    )


# --- Category-specific generation retrieval -----------------------------------------
# Query-driven RAG for test-case GENERATION (as opposed to extraction/grounding, which
# keep using the broad `rag_context` above via _evidence_corpus() -- see the call sites
# in generate_fresh_testcases_pipeline() for the extraction-vs-generation rationale).
#
# Generation needs PRECISION: a small, ranked, category-scoped slice of this feature's
# own chunks, retrieved by an actual semantic query built from what Pass 0/1/2 already
# extracted (no extra LLM call). Extraction and post-generation grounding need RECALL:
# the full, unranked chunk corpus, so a real signal in the document isn't discarded just
# because it didn't match this run's particular query text. Both concepts are backed by
# the SAME store.fchunks collection -- only how much of it, and in what order, is used.
#
# K defaults are simple and static for now (per user instruction: no dynamic K selection
# yet, tune after evaluation) but Ollama-aware, mirroring the existing num_ctx=8192
# cap on call_llm_json_with_repair(): a CPU-bound local model gets fewer, tighter chunks
# so the category evidence block doesn't crowd out the rest of the prompt.
RAG_TOP_K_DEFAULTS = {"api": 8, "ui": 8, "e2e": 6, "business": 6}
RAG_TOP_K_OLLAMA_DEFAULTS = {"api": 4, "ui": 4, "e2e": 4, "business": 4}


def _category_top_k(category: str, is_ollama: bool) -> int:
    table = RAG_TOP_K_OLLAMA_DEFAULTS if is_ollama else RAG_TOP_K_DEFAULTS
    return table.get(category, 8)


# Below this many discovered endpoints, an API-category query built from just
# "METHOD /path" strings is too narrow to differentiate from the E2E/business
# queries -- live-evaluation finding (Authentication feature, 1 discovered endpoint):
# the API-category retrieval converged on the SAME top chunks as the E2E category,
# because the query itself carried almost no distinguishing signal. See
# _api_adjacent_requirement_lines() below for the deterministic broadening.
API_QUERY_BROADEN_BELOW_ENDPOINTS = 2

# Vocabulary used to pick out the subset of already-extracted business requirement
# lines that read as API/state-mutation relevant (CRUD verbs, request/response/
# field/status-code language) -- deliberately narrower than the full description
# text _build_e2e_retrieval_query()/_build_business_retrieval_query() use, so
# broadening the API query doesn't just turn it into a copy of those.
_API_ADJACENT_KEYWORDS = (
    "endpoint", "api", "request", "response", "payload", "status code", "http",
    "create", "update", "delete", "fetch", "retrieve", "field", "parameter",
    "validate", "validation", "token", "header", "query param", "body",
)


def _api_adjacent_requirement_lines(business_context: dict | None) -> list[str]:
    """Deterministic filter over businessContext requirement lines (same source
    data _build_e2e_retrieval_query()/_build_business_retrieval_query() read --
    no new extraction, no new LLM call) for the subset that reads as API/
    state-mutation relevant. Used only to broaden the API-category query when Pass
    0/2 discovered too few explicit endpoints to build a differentiated query from
    endpoint strings alone."""
    ctx = business_context or {}
    requirements = _as_list(ctx.get("requirements"))
    prd = ctx.get("prd")
    if not requirements and isinstance(prd, dict):
        requirements = _as_list(prd.get("requirements"))
    lines = []
    for item in requirements:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in _API_ADJACENT_KEYWORDS):
            lines.append(text)
    return lines


def _build_api_retrieval_query(
    entities: list, api_surface: list, business_context: dict | None = None
) -> str:
    """Deterministic API-category retrieval query text: every known endpoint's
    "METHOD /path", followed by grounded entity names, in extraction order. Built
    entirely from Pass 1 (grounded_entities) and Pass 2 (api_surface) output that the
    pipeline has already computed by the time this is called -- no new LLM call.

    When Pass 0/2 discovered fewer than API_QUERY_BROADEN_BELOW_ENDPOINTS endpoints,
    the query above is broadened with the API-adjacent subset of businessContext's
    requirement lines (see _api_adjacent_requirement_lines()) -- still fully
    deterministic, still no new LLM call, and still a smaller/differently-shaped
    slice of the same requirement text than the E2E/business queries use, so this
    doesn't just make the API query converge with them instead."""
    parts = []
    endpoint_count = 0
    for api in _as_list(api_surface):
        if not isinstance(api, dict):
            continue
        endpoint = str(api.get("endpoint") or api.get("path") or "").strip()
        if not endpoint:
            continue
        method = str(api.get("method") or "").upper().strip()
        parts.append(f"{method} {endpoint}".strip())
        endpoint_count += 1
    for entity in _as_list(entities):
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("entity") or entity.get("name") or "").strip()
        if name:
            parts.append(name)
    if endpoint_count < API_QUERY_BROADEN_BELOW_ENDPOINTS:
        parts.extend(_api_adjacent_requirement_lines(business_context))
    return " ".join(parts).strip()


def _build_ui_retrieval_query(ui_components: list, feature_name: str) -> str:
    """Deterministic UI-category retrieval query text: the feature name plus every
    known UI element/screen label, in extraction order. Built from Pass 1's
    ui_components (LLM-grounded or the _derive_ui_components() fallback), both of
    which use the same "element"/"screen" shape -- no new LLM call."""
    parts = [str(feature_name or "").strip()]
    for component in _as_list(ui_components):
        if not isinstance(component, dict):
            continue
        screen = str(component.get("screen") or "").strip()
        element = str(component.get("element") or component.get("label") or component.get("name") or "").strip()
        if screen:
            parts.append(screen)
        if element:
            parts.append(element)
    return " ".join(p for p in parts if p).strip()


def _build_e2e_retrieval_query(business_context: dict, feature_name: str, feature_description: str) -> str:
    """Deterministic E2E/business-category retrieval query text: the feature name and
    description plus the business rule requirement lines already extracted into
    businessContext (build_unified_context() -> extract_business_context()). Built
    from data the pipeline already has -- no new LLM call."""
    parts = [str(feature_name or "").strip(), str(feature_description or "").strip()]
    requirements = []
    if isinstance(business_context, dict):
        prd_block = business_context.get("prd")
        if isinstance(prd_block, dict):
            requirements = _as_list(prd_block.get("requirements"))
        if not requirements:
            requirements = _as_list(business_context.get("requirements"))
    for requirement in requirements[:25]:
        text = str(requirement or "").strip()
        if text:
            parts.append(text)
    return " ".join(p for p in parts if p).strip()


def _build_business_retrieval_query(business_context: dict, feature_name: str, feature_description: str) -> str:
    """Deterministic business-category retrieval query text: feature name/description
    plus every already-extracted business-rule signal -- requirement lines, acceptance
    criteria, and user stories (all produced by extract_business_context() in
    store/features.py, part of build_unified_context()) -- in extraction order. Built
    from data the pipeline already has -- no new LLM call.

    Deliberately distinct from _build_e2e_retrieval_query(): that one stays close to
    plain requirement lines for user-journey framing, while this one also pulls
    acceptance-criteria and user-story lines, which are the stronger signal for
    "what business rule does this test enforce" -- the question business_tests answers.
    Handles both businessContext shapes seen in this codebase: the flat dict
    extract_business_context() actually returns (requirements/acceptanceCriteria/
    userStories at the top level) and a {"prd": {...}} nested variant some call sites
    (and the FakeStore test fixture) use -- same dual-shape handling as
    _build_e2e_retrieval_query() above.
    """
    parts = [str(feature_name or "").strip(), str(feature_description or "").strip()]
    requirements, acceptance_criteria, user_stories = [], [], []
    if isinstance(business_context, dict):
        prd_block = business_context.get("prd")
        source = prd_block if isinstance(prd_block, dict) else business_context
        requirements = _as_list(source.get("requirements"))
        acceptance_criteria = _as_list(source.get("acceptanceCriteria"))
        user_stories = _as_list(source.get("userStories"))
    for value in (*requirements[:15], *acceptance_criteria[:10], *user_stories[:10]):
        text = str(value or "").strip()
        if text:
            parts.append(text)
    return " ".join(p for p in parts if p).strip()


def _to_rag_context(summary: str, chunks: list) -> dict:
    """Adapt search_feature_chunks()'s [{chunk_id, chunk_index, source, text, score}]
    result rows into the {"summary", "retrieved_chunks":[{"sourceType","score","text"}]}
    shape build_rag_evidence_block() (and the broad `rag_context` above) already expect,
    so category contexts are drop-in compatible with the existing prompt-builder code."""
    return {
        "summary": summary,
        "retrieved_chunks": [
            {
                "sourceType": item.get("source") or "document",
                "score": item.get("score", 0.0),
                "text": item.get("text", ""),
            }
            for item in _as_list(chunks)
        ],
    }


def _priority(value) -> str:
    raw = str(value or "P2").strip().upper()
    return {"HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}.get(raw, raw if raw in {"P0", "P1", "P2", "P3"} else "P2")


def _normal_steps(case: dict) -> list[dict]:
    raw_steps = case.get("steps")
    if not raw_steps and isinstance(case.get("ui_journey_steps"), list):
        raw_steps = case["ui_journey_steps"]
    out = []
    for raw in _as_list(raw_steps):
        if isinstance(raw, str):
            action, expected = raw.strip(), "The described observable outcome occurs."
        elif isinstance(raw, dict):
            action = str(
                raw.get("action") or raw.get("content") or raw.get("step") or
                raw.get("description") or ""
            ).strip()
            expected = str(
                raw.get("expected") or raw.get("expectedResult") or
                raw.get("expected_result") or raw.get("expected_behavior") or ""
            ).strip()
        else:
            continue
        if action or expected:
            out.append({"action": action or "Verify the behavior", "expected": expected or "The behavior is correct."})
    if not out:
        action = str(case.get("description") or case.get("intent") or case.get("title") or "").strip()
        expected = case.get("expected_behavior") or case.get("expected_result") or "The expected behavior occurs."
        if isinstance(expected, dict):
            expected = json.dumps(expected, sort_keys=True)
        if action:
            out.append({"action": action, "expected": str(expected)})
    return out


def _deduplicate_with_reasons(cases: list, category: str) -> tuple[list[dict], list[tuple[dict, str]]]:
    seen_hashes = set()
    out, rejected = [], []
    for raw in cases:
        if not isinstance(raw, dict):
            continue
        case = dict(raw)
        case["category"] = category
        if category == "api_tests":
            if not str(case.get("endpoint") or "").startswith("/"):
                continue
            case["method"] = str(case.get("method") or "GET").upper()
        identity_hash = generate_test_identity_hash(case)
        slug = generate_test_slug(case)
        if identity_hash in seen_hashes:
            rejected.append((case, REASON_DUPLICATE))
            continue
        seen_hashes.add(identity_hash)
        case["identity_hash"] = identity_hash
        case["test_slug"] = slug
        out.append(case)
    out.sort(key=lambda c: PRIORITY_ORDER.get(str(c.get("priority") or "P2").upper(), 2))
    return out, rejected


def _deduplicate(cases: list, category: str) -> list[dict]:
    kept, _ = _deduplicate_with_reasons(cases, category)
    return kept


def _filter_api_tests(cases: list, api_surface: list[dict]) -> list[dict]:
    allowed = {_api_key(api) for api in api_surface}
    if not allowed:
        return []
    return [
        case for case in cases
        if isinstance(case, dict) and _api_key(case) in allowed
    ]


def _filter_ui_tests(cases: list, corpus: str, ui_components: list[dict]) -> list[dict]:
    allowed = set()
    for component in ui_components:
        for key in ("field", "element", "name", "title", "screen"):
            value = str(component.get(key) or "").strip().lower()
            if value:
                allowed.add(value)
    out = []
    for case in cases:
        field = str(case.get("field") or case.get("element") or "").strip().lower()
        if not field:
            continue
        if field in corpus or any(field in value or value in field for value in allowed):
            out.append(case)
    return out


# --- Category-agnostic content-level grounding guard --------------------------------
# _filter_api_tests()/_filter_ui_tests() above only check a case's SUBJECT is real (a
# real endpoint, a real field name) -- neither says anything about the case's CONTENT.
# A case can reference a genuinely real endpoint or field and still assert a specific
# numeric requirement (a length limit, a digit count, a timeout, a retry count, a
# percentage...) that nothing in the evidence actually states. This guard catches that
# narrower, content-level failure mode, applied uniformly across all five generated
# suites (api_tests/ui_validations/e2e_tests/edge_cases/business_tests) on any
# feature -- no category- or domain-specific keywords, no new LLM call, and no change
# to retrieval or embeddings (pure text comparison against the same broad `corpus`
# _evidence_corpus() already builds for entities/API grounding), so it works
# identically under any embedding provider/model configured through Settings.
#
# Design: only sentences that already read as an asserted RULE (the same
# REQUIREMENT_MARKERS vocabulary _requirement_gaps() uses to find requirement-shaped
# PRD lines, applied here to generated case text instead) AND that state a specific
# number are checked. A case describing a general, unnumbered scenario ("ensure a
# delivery address is provided") is a reasonable derived scenario and is left
# untouched -- only a specific, checkable numeric claim ("must not exceed 20 percent")
# is held to evidence. A number is considered supported when that same number occurs
# in the corpus with a matching qualifier word (its stem) among the few TOKENS
# immediately surrounding it -- not a bare digit, and not a raw character window
# (which can accidentally reach into an unrelated word earlier in the same sentence).
# Tokenizing on letters/digits (hyphens and other punctuation are not token
# characters) means real PRD prose that hyphenates or reorders a number and its unit
# ("10-minute window", "401-equivalent error") still matches -- "10-minute" tokenizes
# to adjacent tokens "10", "minute" -- while an unrelated fact that happens to share
# the same digit elsewhere in the document (a 15-MINUTE token lifetime "supporting"
# an invented 15-CHARACTER field limit, or an unrelated noun a few words earlier in
# the same sentence as an unrelated number) is correctly rejected.
_NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?")
_WORD_TOKEN = re.compile(r"[a-zA-Z]+")
_WORD_OR_NUMBER_TOKEN = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?")
_CLAIM_TOKEN_WINDOW = 2


def _stem(word: str) -> str:
    word = word.lower()
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _next_qualifier_word(text: str, end: int) -> str | None:
    match = _WORD_TOKEN.search(text, end)
    if match and match.start() - end <= 3:
        return match.group(0)
    return None


def _corpus_number_tokens(corpus: str) -> list[str]:
    return _WORD_OR_NUMBER_TOKEN.findall(corpus)


def _number_claim_supported(number: str, qualifier: str, corpus_tokens: list[str]) -> bool:
    qualifier_stem = _stem(qualifier)
    for idx, token in enumerate(corpus_tokens):
        if token != number:
            continue
        neighbors = (
            corpus_tokens[max(0, idx - _CLAIM_TOKEN_WINDOW): idx]
            + corpus_tokens[idx + 1: idx + 1 + _CLAIM_TOKEN_WINDOW]
        )
        if any(_stem(word) == qualifier_stem for word in neighbors if word.isalpha()):
            return True
    return False


def _case_claim_segments(case: dict) -> list[str]:
    """The parts of a case that ASSERT something about the system, kept separate.

    Two distinctions matter here, and collapsing the case into one blob got both wrong:

    1. A step's ACTION is an input the tester supplies, not a claim about the product.
       Probing a documented boundary reads "Enter 241 characters" against a grounded
       240-character limit, and treating that 241 as an asserted requirement drops a
       perfectly well-grounded negative test. Actions are therefore not evaluated;
       titles, intents, descriptions and step EXPECTATIONS -- where a fabricated limit
       actually gets asserted -- are.
    2. Segments are judged independently. Joined into one string they became a single
       marker-matching "sentence" (generated case text rarely ends in a period), so a
       "rejected" in one step licensed judging every number in the title, and vice
       versa."""
    segments = [
        str(case.get("title") or ""),
        str(case.get("intent") or ""),
        str(case.get("description") or ""),
    ]
    segments.extend(step["expected"] for step in _normal_steps(case))
    return [segment for segment in segments if segment.strip()]


def _unsupported_numeric_claims(case: dict, corpus) -> list[str]:
    """Return the specific number+qualifier claims this case states as a
    requirement (matched via REQUIREMENT_MARKERS) that the evidence corpus does not
    back. `corpus` may be a raw evidence-corpus string (matching
    _grounded_item_supported()'s convention -- tokenized internally, lowercased if
    not already) or a pre-tokenized/lowercased token list (see
    _corpus_number_tokens()), for callers that already tokenized once for a whole
    batch of cases."""
    corpus_tokens = corpus if isinstance(corpus, list) else _corpus_number_tokens(str(corpus or "").lower())
    unsupported = []
    for segment in _case_claim_segments(case):
        for sentence in re.split(r"[\n\r]+|(?<=[.!?])\s+", segment):
            clean = sentence.strip()
            if not clean or not REQUIREMENT_MARKERS.search(clean):
                continue
            lowered = clean.lower()
            for match in _NUMBER_TOKEN.finditer(lowered):
                qualifier = _next_qualifier_word(lowered, match.end())
                if not qualifier:
                    continue
                if not _number_claim_supported(match.group(0), qualifier, corpus_tokens):
                    unsupported.append(f"{match.group(0)} {qualifier}")
    return unsupported


def _filter_ungrounded_claims(cases: list[dict], corpus: str) -> list[dict]:
    """Drop any generated case -- from any of the five suites -- that states a
    specific numeric requirement whose value isn't backed anywhere in the evidence
    corpus. Cases with no such claim, including well-grounded cases and reasonable
    unnumbered derived scenarios, pass through unchanged. This is the single point
    where every suite is held to the same content-level grounding standard,
    regardless of category or feature."""
    corpus_tokens = _corpus_number_tokens(str(corpus or "").lower())
    return [
        case for case in cases
        if isinstance(case, dict) and not _unsupported_numeric_claims(case, corpus_tokens)
    ]


_SOURCE_GROUNDING_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9]{3,}")
_SOURCE_GROUNDING_STOP = {
    "must", "will", "with", "from", "that", "this", "when", "then", "into",
    "only", "also", "does", "done", "have", "been", "being", "they", "them",
    "their", "there", "these", "those", "same", "each", "both", "over",
    "after", "before", "still", "able", "used", "using", "make", "made",
}


def _case_grounding_text(case: dict) -> str:
    parts = [
        case.get("title"),
        case.get("intent"),
        case.get("description"),
        case.get("expected_behavior"),
    ]
    preconditions = case.get("preconditions") or []
    if isinstance(preconditions, (list, tuple)):
        parts.extend(preconditions)
    else:
        parts.append(preconditions)
    parts.extend(case.get("ui_journey_steps") or [])
    parts.extend(case.get("backend_assertions") or [])
    for step in case.get("steps") or []:
        if isinstance(step, dict):
            parts.append(step.get("content") or step.get("action"))
            parts.append(step.get("expectedResult") or step.get("expected"))
        else:
            parts.append(step)
    return " ".join(str(part) for part in parts if part)


def _case_has_source_grounding(case: dict, corpus: str) -> bool:
    """True when at least one content token from the case appears in the source corpus.

    e2e / nfr previously shipped on a category-level 'feature has a description'
    verdict even when the case itself had zero overlap with the documents. That
    let prompt few-shots persist as if they belonged to the user's feature."""
    if not isinstance(case, dict):
        return False
    corpus_l = str(corpus or "").lower()
    if not corpus_l.strip():
        return False
    tokens = {
        token.lower()
        for token in _SOURCE_GROUNDING_TOKEN.findall(_case_grounding_text(case))
        if token.lower() not in _SOURCE_GROUNDING_STOP
    }
    return any(re.search(rf"\b{re.escape(token)}\b", corpus_l) for token in tokens)


def _filter_ungrounded_suite_cases_with_reasons(
    cases: list[dict], corpus: str
) -> tuple[list[dict], list[tuple[dict, str]]]:
    kept, rejected = [], []
    for case in (cases or []):
        if not isinstance(case, dict):
            continue
        if _case_has_source_grounding(case, corpus):
            kept.append(case)
        else:
            rejected.append((case, REASON_NO_SOURCE_GROUNDING))
    return kept, rejected


def _filter_ungrounded_suite_cases(cases: list[dict], corpus: str) -> list[dict]:
    kept, _ = _filter_ungrounded_suite_cases_with_reasons(cases, corpus)
    return kept


# --- Category evidence sufficiency (deterministic, pre-generation) -------------------
# The grounding filters above are all POST-generation: they drop what the model already
# invented. That is the right shape for "this case's content isn't backed", but it is
# the wrong shape for the more basic failure the live Authentication validation exposed:
# a category with NO subject evidence at all still had its generation worker invoked,
# and a model asked to "generate UI validations" with nothing to ground against will
# produce plausible, standard-looking, entirely invented ones (a phone-length limit, an
# OTP digit count, a submit-button rule) rather than nothing. Filtering afterwards can
# only catch the subset of those inventions that is mechanically checkable.
#
# So the pipeline also needs a deterministic answer to "does this category have any
# evidence to generate FROM at all", computed BEFORE the call, from extraction output
# the pipeline already has (no new LLM call, no new retrieval, no embedding involved --
# therefore identical under every embedding provider/model configured through Settings).
# Where a category owns a standalone generation call, an insufficient verdict skips that
# call outright: nothing is invented, and an unnecessary LLM call is saved. Where a
# category shares a call with others (edge_cases/business_tests ride the E2E call), the
# verdict is reported rather than acted on destructively, because skipping would take
# the sibling categories down with it.
#
# Deliberately keyed on the COUNT of already-extracted, already-grounded subjects --
# never on keywords, category names, or feature-specific vocabulary -- so it behaves
# the same for Authentication, Ride Booking, Payments, or anything else:
#   api      -- grounded endpoints discovered by Pass 0/1/2 (api_surface)
#   ui       -- UI elements that survived Pass 1 grounding or _derive_ui_components(),
#               else any UI signal at all in the evidence corpus (see below)
#   e2e      -- the feature's own description/requirement lines (a feature always has a
#               description, so E2E journeys always have something to derive from)
#   edge     -- API/state-mutation evidence, matching what the edge block is actually
#               fed (api_rag_context) in the shared E2E call
#   business -- extracted business narrative: requirements, acceptance criteria, stories


# The domain-independent vocabulary for "these documents describe a user interface at
# all". This is the SAME control-noun set _derive_ui_components() already mines for
# below, plus the three container words a UI is described in; it names UI machinery, not
# any product's subject matter, so it carries no feature-specific assumption (there is
# nothing here about phone numbers, codes, or what a button should do -- only that a
# document mentioning a button is a document with a UI in it). It answers a strictly
# narrower question than _derive_ui_components(), which additionally has to produce a
# usable component LABEL and so discards perfectly good UI evidence whose surrounding
# phrasing doesn't yield one -- fine when building component records, wrong when the
# question is merely "is there any UI evidence here".
#
# The failure modes are asymmetric on purpose: a false positive costs only the behavior
# the pipeline already had (the UI worker runs, and the existing subject/content filters
# handle the output), while a false negative would skip a UI suite the feature deserved.
# So this errs permissive.
_UI_EVIDENCE_SIGNAL = re.compile(
    r"\b(input|field|picker|selector|dropdown|toggle|checkbox|screen|form|button)s?\b",
    re.IGNORECASE,
)


def _has_ui_evidence_signal(text: str) -> bool:
    return bool(_UI_EVIDENCE_SIGNAL.search(str(text or "")))


def _business_narrative_lines(business_context: dict | None) -> list[str]:
    """Every already-extracted business-rule line, from both businessContext shapes this
    codebase uses (flat, as extract_business_context() returns, and the {"prd": {...}}
    nested variant) -- the same sources _build_business_retrieval_query() reads, so the
    sufficiency verdict and the business retrieval query agree on what "business
    evidence" means."""
    ctx = business_context if isinstance(business_context, dict) else {}
    prd_block = ctx.get("prd")
    source = prd_block if isinstance(prd_block, dict) else ctx
    lines = []
    for key in ("requirements", "acceptanceCriteria", "userStories"):
        for value in _as_list(source.get(key)):
            text = str(value or "").strip()
            if text:
                lines.append(text)
    if source is not ctx:
        for value in _as_list(ctx.get("requirements")):
            text = str(value or "").strip()
            if text:
                lines.append(text)
    return lines


def _category_evidence_sufficiency(
    api_surface: list, ui_components: list, business_context: dict | None,
    feature_description: str = "", evidence_text: str = "",
) -> dict:
    """Per-category "is there anything to generate from" verdict. See the block comment
    above -- deterministic, embedding-independent, feature-agnostic.

    The UI verdict deliberately looks WIDER than `ui_components`: that list is built from
    Pass 1's extraction plus a _derive_ui_components() pass over the feature's own `text`
    field, which is only one of the documents that can back a feature. A PRD that carries
    the UI description in a second, separately-ingested document would leave
    ui_components empty while the evidence corpus plainly contains UI material. So the
    verdict falls back to _has_ui_evidence_signal() over the whole evidence corpus (the
    identical text _evidence_corpus() already assembles for grounding -- no new
    retrieval, no embedding, no LLM call). ui_components itself is NOT widened by
    this: the retrieval query and _filter_ui_tests()'s allow-list keep using exactly the
    components they used before, so nothing downstream loosens. The verdict is only ever
    more permissive than a bare `bool(ui_components)`, which means it can never newly
    suppress a UI suite that would have been generated before -- it only says "no UI
    evidence" when there is no UI signal anywhere in the feature's evidence at all."""
    narrative = _business_narrative_lines(business_context)
    has_ui_evidence = (
        bool(_as_list(ui_components)) or _has_ui_evidence_signal(evidence_text)
    )
    return {
        "api": bool(_as_list(api_surface)),
        "ui": has_ui_evidence,
        "e2e": bool(str(feature_description or "").strip() or narrative),
        "edge": bool(_as_list(api_surface)),
        "business": bool(narrative),
    }


def _insufficient_evidence_warning(category: str) -> str:
    """User-facing explanation attached to the job result when a category had no
    evidence. The requirement is that the pipeline either generates only what the
    evidence supports OR says the evidence was insufficient -- this is that second
    branch, made visible on the job instead of silently returning an empty suite (which
    is indistinguishable from "the model produced nothing")."""
    return (
        f"{category}: no supporting evidence was found in this feature's documents, so "
        f"no {category} tests were generated from invented details. Add source material "
        f"covering this area to get {category} coverage."
    )


def _derive_ui_components(raw_text: str, limit: int = 40) -> list[dict]:
    """Recover explicit interactive controls when the discovery model misses them."""
    component_types = {
        "input": "input",
        "picker": "picker",
        "selector": "selector",
        "dropdown": "selector",
        "toggle": "selector",
        "checkbox": "selector",
    }
    found = {}
    for line in str(raw_text or "").splitlines():
        clean = " ".join(line.split()).strip("•- \t")
        if not clean or len(clean) > 180:
            continue
        camel_matches = re.findall(
            r"\b([A-Z][A-Za-z0-9]*(?:Input|Picker|Selector|Dropdown|Toggle|Checkbox))\b",
            clean,
        )
        for token in camel_matches:
            suffix = next((name for name in component_types if token.lower().endswith(name)), "input")
            label = re.sub(r"([a-z0-9]|[A-Z])([A-Z][a-z])", r"\1 \2", token)
            label = re.sub(
                r"\s+(Input|Picker|Selector|Dropdown|Toggle|Checkbox)$", "", label,
                flags=re.IGNORECASE,
            ).strip()
            if label:
                key = label.lower()
                found.setdefault(key, {
                    "screen": "",
                    "element": label,
                    "type": component_types[suffix],
                    "evidence_quote": clean,
                })
        phrase = re.search(
            r"\b([A-Za-z][A-Za-z0-9 /_-]{1,45}?)\s+"
            r"(input|field|picker|selector|dropdown|toggle|checkbox)\b",
            clean,
            re.IGNORECASE,
        )
        if phrase:
            label = phrase.group(1).strip(" :").split("•")[-1].strip()
            if 1 <= len(label.split()) <= 6:
                kind = phrase.group(2).lower()
                found.setdefault(label.lower(), {
                    "screen": "",
                    "element": label,
                    "type": component_types.get(kind, "input"),
                    "evidence_quote": clean,
                })
        if len(found) >= limit:
            break
    return list(found.values())[:limit]


def _default_success_status(method: str) -> int:
    return 201 if method == "POST" else 204 if method == "DELETE" else 200


def _ensure_api_endpoint_coverage(cases: list[dict], api_surface: list[dict]) -> list[dict]:
    covered = {_api_key(case) for case in cases}
    out = list(cases)
    for api in api_surface:
        key = _api_key(api)
        if key in covered:
            continue
        method, endpoint = api["method"], api["endpoint"]
        status = _default_success_status(method)
        module = next((part for part in endpoint.split("/") if part and part not in {"api", "v1", "v2"}), "core")
        out.append({
            "title": f"{method} {endpoint} accepts a valid request",
            "intent": f"Provide baseline grounded coverage for the discovered {method} {endpoint} endpoint",
            "method": method,
            "endpoint": endpoint,
            "priority": "High" if method in {"POST", "PUT", "PATCH", "DELETE"} else "Medium",
            "test_suite": "Smoke",
            "module": module.replace("-", " ").title(),
            "steps": [
                {"content": "Given valid authentication and endpoint preconditions", "expectedResult": "The request can be executed."},
                {"content": f"When {method} {endpoint} is called with a valid request", "expectedResult": f"The response status is {status}."},
            ],
            "expected_result": {
                "status_code": status,
                "db_changes": [] if method == "GET" else ["The expected state change is persisted"],
                "side_effects": [],
                "negative_assertions": ["No unexpected validation, authorization, or server error is returned"],
            },
            "tags": ["api-test", "baseline-coverage"],
        })
        covered.add(key)
    return out


def _requirement_gaps(raw_text: str, suites: dict) -> list[dict]:
    output_text = json.dumps(suites, sort_keys=True).lower()
    gaps = []
    seen = set()
    for line in re.split(r"[\n\r]+|(?<=[.!?])\s+", raw_text):
        clean = " ".join(line.split()).strip(" -*#\t")
        if not 30 <= len(clean) <= 300 or not REQUIREMENT_MARKERS.search(clean):
            continue
        tokens = {
            token for token in re.findall(r"[a-z0-9]{3,}", clean.lower())
            if token not in {"shall", "should", "must", "system", "user", "users", "feature", "when", "then"}
        }
        if len(tokens) < 3:
            continue
        signature = " ".join(sorted(tokens))
        if signature in seen:
            continue
        seen.add(signature)
        matched = sum(1 for token in tokens if token in output_text)
        if matched / len(tokens) < 0.55:
            gaps.append({"type": "missing_requirement_coverage", "requirement": clean})
        if len(gaps) >= 12:
            break
    return gaps


def _apply_delta(existing: list, delta: dict, category: str) -> list[dict]:
    hashes = {str(value) for value in _as_list(delta.get("tests_to_remove_by_hash"))}
    pairs = {
        (str(value.get("title") or ""), str(value.get("intent") or ""))
        for value in _as_list(delta.get("tests_to_remove")) if isinstance(value, dict)
    }
    kept = []
    for test in existing:
        short_hash = str(test.get("_hash") or test.get("identity_hash") or "")[:12]
        if short_hash in hashes:
            continue
        if (str(test.get("title") or ""), str(test.get("intent") or "")) in pairs:
            continue
        kept.append(test)
    return _deduplicate(kept + _as_list(delta.get("tests_to_add")), category)


FOCUS_NAMES = ("functional", "e2e", "api", "nfr", "ui")
_FOCUS_DEFAULT = 100.0 / len(FOCUS_NAMES)  # even split across the 5 sliders


def _budget_suites(suites: dict, total: int, focus: dict, smoke_mode=False) -> dict:
    """Trim each generated suite so the final case counts track the user's
    focus weights (functional / e2e / api / nfr / ui), instead of only gating
    whole categories on/off. A weight of 0 drops a category entirely. Nonzero
    weights cap how large a category's share of the pool can be, scaled by
    weight, relative to the OTHER categories that were actually produced —
    equal weights should mean no one category can dominate the results.

    This only ever trims; it never invents tests to pad a thin category up to
    its target. A lightly-documented feature with 3 grounded business rules
    stays at 3 business tests even at 100% functional weight — the point is to
    stop an over-represented category (typically API, since it scales with
    discovered endpoints) from drowning out the others, not to fabricate
    ungrounded content just to hit a number.
    """
    natural = {
        "api": suites["api_tests"],
        "ui": suites["ui_validations"],
        "functional": suites["business_tests"],
        "e2e": suites["e2e_tests"],
        "nfr": suites["edge_cases"],
    }
    weights = {name: max(0.0, float((focus or {}).get(name, _FOCUS_DEFAULT))) for name in FOCUS_NAMES}

    # A weight of 0 means "skip this category" in every mode.
    for name in FOCUS_NAMES:
        if weights[name] <= 0:
            natural[name] = []

    weight_sum = sum(weights.values()) or 100.0
    api_endpoint_count = len({_api_key(case) for case in natural["api"]})

    # smoke_mode keeps its small explicit-total behavior (e.g. a quick
    # preview run); everything else scales caps off the pool the agents
    # actually produced, so overall volume isn't arbitrarily shrunk to a
    # fixed number — only redistributed relative to the chosen emphasis.
    pool_total = max(0, int(total)) if smoke_mode else sum(len(v) for v in natural.values())

    if pool_total > 0:
        for name in FOCUS_NAMES:
            if weights[name] <= 0:
                continue
            target = max(0, round(pool_total * weights[name] / weight_sum))
            if name == "api":
                # The API pass is per-endpoint coverage, not a fixed count —
                # never cut below one test per discovered endpoint.
                target = max(target, api_endpoint_count)
            # Never zero out a nonzero-weight category purely from rounding
            # when there's genuine material for it.
            keep = max(target, min(len(natural[name]), 3))
            if keep < len(natural[name]):
                natural[name] = natural[name][:keep]

    return {
        "api_tests": natural["api"],
        "ui_validations": natural["ui"],
        "business_tests": natural["functional"],
        "e2e_tests": natural["e2e"],
        "edge_cases": natural["nfr"],
    }


def _chunks(items: list, size: int) -> list[list]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _risky_api(api: dict) -> bool:
    method = str(api.get("method") or "").upper()
    text = json.dumps(api).lower()
    return method in {"POST", "PUT", "PATCH", "DELETE"} or any(
        word in text for word in ("payment", "auth", "retry", "queue", "rate", "concurrent", "upload")
    )


def _project_existing_tests(store, project_id) -> list[dict]:
    try:
        brief = store.list_test_cases(project_id=project_id, status="all", limit=200)
    except TypeError:
        brief = store.list_test_cases(project_id=project_id)
    out = []
    for item in _as_list((brief or {}).get("items")):
        detail = store.get_case(item["id"]) if hasattr(store, "get_case") else None
        case = detail or item
        out.append({
            "id": item["id"],
            "reference_key": item["id"],
            "title": case.get("title"),
            "type": case.get("type"),
            "priority": case.get("priority"),
            "steps": _as_list(case.get("steps"))[:8],
            "identity_hash": case.get("identity_hash"),
            "test_slug": case.get("test_slug"),
        })
    return out


# --- Fusion payload size safety -------------------------------------------------------
# build_fusion_pass_prompt() serializes _project_existing_tests()'s output (up to 200
# project-wide cases, each up to 8 steps) directly into the Fusion prompt. Case count is
# not a safe proxy for prompt size: step count and step-text length vary per case, so a
# fixed COUNT cap (prompt_builder's existing `[:100]` slice) can still pass through a
# payload large enough to blow a real model's context window -- exactly what happened
# live (173 project cases produced a 232,629-token prompt against a 128K-token model).
#
# The fix bounds by actual SERIALIZED SIZE, not count, and it is deliberately not sized
# to any one model: this codebase has no per-provider context-window registry to consult
# (Settings lets the user pick Nomic/OpenAI/Voyage/Bedrock/Gemini for EMBEDDINGS, and
# num_ctx below is Ollama-only -- cloud generation providers receive the full prompt
# text and are bounded only by their own real limit, which this process cannot see). A
# fixed conservative character budget therefore has to be safe under the smallest
# context window in realistic use while leaving the rest of the Fusion prompt (PRD text,
# siblings, graph context, previous-version tests, system/output-schema overhead, and
# room for the response) comfortable headroom under even a small hosted model's limit.
#
# No new LLM call: the same project_tests list _project_existing_tests() already fetched
# is reused; when it already fits, nothing is trimmed or reordered, so small/typical
# projects see byte-identical Fusion behavior to before this change.
_FUSION_EXISTING_TESTS_CHAR_BUDGET = 40_000  # ~10K tokens at a conservative 4 chars/token


def _case_relevance_score(case: dict, query_tokens: set) -> int:
    """Cheap, deterministic overlap between a candidate case's own title and the
    current feature's text -- no LLM call, no embedding, just the same token-overlap
    technique _requirement_gaps() already uses elsewhere in this file. Good enough to
    prefer cases that are actually about the current feature's subject matter over
    unrelated project noise when not everything fits."""
    if not query_tokens:
        return 0
    tokens = set(re.findall(r"[a-z0-9]{3,}", str(case.get("title") or "").lower()))
    return len(tokens & query_tokens)


def _bound_project_tests_for_fusion(
    project_tests: list[dict], feature_text: str,
    budget_chars: int = _FUSION_EXISTING_TESTS_CHAR_BUDGET,
) -> tuple[list[dict], int]:
    """Trim project_tests to fit budget_chars of serialized JSON, keeping the
    most-relevant-to-this-feature cases when not everything fits, and keeping
    project_tests completely UNCHANGED (same list, same order) when it already fits --
    so a typical/small project's Fusion prompt is byte-identical to before this change.
    Returns (bounded_list, dropped_count)."""
    if not project_tests:
        return project_tests, 0
    if len(json.dumps(project_tests, indent=2)) <= budget_chars:
        return project_tests, 0

    query_tokens = set(re.findall(r"[a-z0-9]{3,}", str(feature_text or "").lower()))
    ranked = sorted(
        enumerate(project_tests),
        key=lambda pair: (-_case_relevance_score(pair[1], query_tokens), pair[0]),
    )
    kept_ids = set()
    running = 2  # "[]"
    for index, case in ranked:
        size = len(json.dumps(case, indent=2)) + 2  # ",\n" separator, approximated
        if running + size > budget_chars:
            continue  # a smaller, lower-ranked case later may still fit
        kept_ids.add(index)
        running += size

    bounded = [case for index, case in enumerate(project_tests) if index in kept_ids]
    return bounded, len(project_tests) - len(bounded)


def _semantic_reuse_compatible(candidate: dict, case: dict, test_type: str) -> bool:
    if str(candidate.get("type") or "") != test_type:
        return False
    previous = {
        **(candidate.get("metadata") or {}),
        "title": candidate.get("title") or "",
        "category": {
            "api": "api_tests",
            "ui": "ui_validations",
            "e2e": "e2e_tests",
            "functional": "business_tests",
            "nfr": "edge_cases",
        }.get(test_type, ""),
    }
    current = dict(case)
    if test_type == "api":
        if str(previous.get("method") or "").upper() != str(current.get("method") or "").upper():
            return False
        if normalize_endpoint(previous.get("endpoint")) != normalize_endpoint(current.get("endpoint")):
            return False
        if scenario_kinds_incompatible(
            derive_scenario_kind(previous), derive_scenario_kind(current)
        ):
            return False
        return token_set_similarity(
            lineage_token_set(previous), lineage_token_set(current)
        ) >= REUSE_SIMILARITY_API
    if test_type == "ui":
        return (
            str(previous.get("field") or previous.get("element") or "").strip().lower()
            == str(current.get("field") or current.get("element") or "").strip().lower()
            and str(previous.get("validation_type") or "").strip().lower()
            == str(current.get("validation_type") or "").strip().lower()
        )
    if scenario_kinds_incompatible(
        derive_scenario_kind(previous), derive_scenario_kind(current)
    ):
        return False
    if routes_incompatible(referenced_routes(previous), referenced_routes(current)):
        return False
    return token_set_similarity(
        lineage_token_set(previous), lineage_token_set(current)
    ) >= REUSE_SIMILARITY_GENERAL


def _persist_case(store, embedder, feature_id, project_id, case: dict, test_type: str,
                  origin: str = "generated", score=None) -> tuple[str, bool, int, int]:
    category = {
        "api": "api_tests",
        "ui": "ui_validations",
        "e2e": "e2e_tests",
        "functional": "business_tests",
        "nfr": "edge_cases",
    }.get(test_type, "business_tests")
    normalized = {**case, "category": category}
    identity_hash = case.get("identity_hash") or generate_test_identity_hash(normalized)
    test_slug = case.get("test_slug") or generate_test_slug(normalized)

    existing = store.find_case_by_identity(project_id, identity_hash, test_slug)
    if existing:
        store.associate(feature_id, existing["id"], "reused" if origin == "generated" else origin, score)
        return existing["id"], True, 0, 0

    steps_new = steps_reused = 0
    step_ids = []
    steps = _normal_steps(case)
    for step in steps:
        embedding = embedder.embed(f"{step['action']}. Expected: {step['expected']}")
        result = store.get_or_create_step(step["action"], step["expected"], embedding, STEP_AUTO)
        step_ids.append(result["step_id"])
        if result.get("origin") == "reused":
            steps_reused += 1
        else:
            steps_new += 1

    title = _clean_requirement_narrative(
        case.get("title") or case.get("intent") or case.get("field") or "Untitled test case"
    )
    case_text = title + " " + " ".join(f"{step['action']} {step['expected']}" for step in steps)
    embedding = embedder.embed(case_text)
    similar = store.find_similar_cases(embedding, SUGGEST, project_id=project_id)
    reusable = next(
        (
            candidate for candidate in similar
            if candidate["score"] >= CASE_AUTO
            and _semantic_reuse_compatible(candidate, normalized, test_type)
        ),
        None,
    )
    if reusable:
        store.associate(feature_id, reusable["case_id"], "reused", reusable["score"])
        return reusable["case_id"], True, steps_new, steps_reused

    tags = list(dict.fromkeys([str(tag) for tag in _as_list(case.get("tags")) if tag]))
    marker = {"api": "api-test", "ui": "ui-validation"}.get(test_type)
    if marker and marker not in tags:
        tags.append(marker)
    metadata = {
        key: value for key, value in case.items()
        if key not in {"title", "priority", "preconditions", "steps", "tags", "identity_hash", "test_slug"}
    }
    for narrative_field in ("description", "intent", "scenario"):
        if narrative_field in metadata:
            metadata[narrative_field] = _clean_requirement_narrative(
                metadata[narrative_field]
            )
    case_id = store.create_case(
        title,
        test_type,
        _priority(case.get("priority")),
        case.get("preconditions") or "",
        step_ids,
        tags,
        embedding,
        feature_id,
        similar_to=similar,
        project_id=project_id,
        identity_hash=identity_hash,
        test_slug=test_slug,
        metadata=metadata,
    )
    store.associate(feature_id, case_id, origin, score)
    return case_id, False, steps_new, steps_reused


def generate_fresh_testcases_pipeline(store, llm, embedder, params, update_job_fn=None) -> dict:
    feature_id = params["feature_id"]
    feature = store.get_feature(feature_id)
    if not feature:
        raise ValueError(f"Feature with id {feature_id} not found")

    project_id = feature.get("project_id")
    raw_text = str(feature.get("text") or params.get("text") or "")
    version = int(feature.get("version") or 1)
    total = max(1, int(params.get("total") or 16))
    focus = params.get("focus") or {name: _FOCUS_DEFAULT for name in FOCUS_NAMES}

    chunks = list(store.fchunks.find({"feature_id": feature_id}))
    rag_context = {
        "summary": feature.get("summary") or raw_text[:1200],
        "retrieved_chunks": [
            {"sourceType": item.get("source", "document"), "score": 1.0, "text": item.get("text", "")}
            for item in chunks
        ],
    }
    previous_cases = []
    if version > 1 and feature.get("group_id"):
        previous = store.features.find_one({
            "group_id": feature["group_id"],
            "version": version - 1,
        })
        if previous:
            previous_cases = store.get_feature_cases(str(previous["_id"]))

    context = store.build_unified_context(feature_id, version)
    context["previousVersionTests"] = previous_cases
    context["flags"]["smokeMode"] = bool(params.get("smoke_mode"))

    evidence_length = len(_evidence_corpus(context, rag_context))
    if evidence_length < 200 and os.getenv("TESTGEN_ALLOW_THIN_DOCS", "").lower() not in {"1", "true", "yes"}:
        raise ValueError(
            "InsufficientEvidenceError: feature evidence is too short for grounded generation. "
            "Add PRD/HLD/LLD content or set TESTGEN_ALLOW_THIN_DOCS=true for development."
        )

    log_progress(update_job_fn, "Pass 0: extracting verbatim API specification", 5)
    raw_api_spec = build_raw_api_spec_from_documents(context, rag_context)
    context["rawApiSpec"] = raw_api_spec
    spec_apis = _parse_raw_api_spec(raw_api_spec)
    context["flags"]["hasApiEvidence"] = bool(spec_apis)
    log_progress(
        update_job_fn,
        f"Pass 0 complete: {len(spec_apis)} verbatim API endpoint(s) found",
        9,
    )

    log_progress(update_job_fn, "Pass 1: grounded entity and API extraction", 12)
    grounded = call_llm_json_with_repair(
        llm, SYSTEM, build_grounded_extraction_prompt(context, rag_context), max_tokens=4000
    )
    # Original-case evidence is kept alongside the lowercased grounding corpus: the
    # category evidence verdict below runs a case-sensitive derivation over it, while
    # every grounding comparison keeps using the lowercased form exactly as before.
    evidence_text = _evidence_corpus(context, rag_context)
    corpus = evidence_text.lower()
    entities = [
        item for item in filter_hallucinated_entities(
            _as_list(grounded.get("grounded_entities")), corpus
        )
        if _grounded_item_supported(item, corpus)
    ]
    explicit_apis = [
        item for item in filter_hallucinated_entities(_as_list(grounded.get("apis")), corpus)
        if _grounded_item_supported(item, corpus)
    ]
    ui_components = [
        value for value in _as_list(grounded.get("ui_components"))
        if isinstance(value, dict) and not is_few_shot_leak(value, corpus)
        and _grounded_item_supported(value, corpus)
    ]
    if not ui_components:
        ui_components = _derive_ui_components(raw_text)
    log_progress(
        update_job_fn,
        f"Pass 1 complete: {len(entities)} entities, {len(explicit_apis)} APIs, "
        f"{len(ui_components)} UI components survived sanitization",
        17,
    )

    log_progress(update_job_fn, "Pass 2: constrained CRUD inference", 20)
    inferred = []
    if not spec_apis:
        inferred_result = call_llm_json_with_repair(
            llm, SYSTEM, build_crud_inference_prompt(entities, context), max_tokens=3000
        )
        inferred = [
            value for value in _as_list(inferred_result.get("apis"))
            if isinstance(value, dict) and not is_few_shot_leak(value, corpus)
        ]
    api_surface = _merge_api_candidates(explicit_apis, spec_apis, inferred)
    log_progress(
        update_job_fn,
        f"Discovery complete: {len(api_surface)} grounded API endpoint(s)",
        24,
    )

    # Per-category evidence verdict (see _category_evidence_sufficiency' block comment):
    # computed once, from what Pass 0/1/2 already extracted, and consulted below wherever
    # a category owns a generation call it should not make with nothing to ground against.
    evidence_sufficient = _category_evidence_sufficiency(
        api_surface, ui_components, context.get("businessContext"),
        context.get("featureDescription"), evidence_text,
    )
    insufficient = [name for name, ok in evidence_sufficient.items() if not ok]
    if insufficient:
        log_progress(
            update_job_fn,
            "Evidence check: insufficient source evidence for "
            f"{', '.join(sorted(insufficient))} -- these categories will not be "
            "generated from invented details",
            26,
        )

    # --- Category-specific generation retrieval (query-driven RAG) -------------------
    # Runs exactly once per category, using information Pass 0/1/2 already extracted
    # above (entities, api_surface, ui_components, businessContext) -- no extra LLM call
    # to synthesize a retrieval query. Every worker within a category (e.g. every API
    # chunk's happy/negative/chaos worker) reuses this SAME result rather than each
    # retrieving on its own. This is deliberately separate from the broad `rag_context`
    # built above: that one keeps feeding Pass 0/1 and _evidence_corpus()/grounding
    # unchanged (recall), while api_rag_context/ui_rag_context/e2e_rag_context below feed
    # only the generation workers (precision). See the module-level comment above
    # RAG_TOP_K_DEFAULTS for the full rationale.
    settings = store.get_settings() if hasattr(store, "get_settings") else {}
    is_ollama = ((settings or {}).get("llm_provider", "ollama") == "ollama")

    def _retrieve_category_context(category: str, query_text: str) -> dict:
        top_k = _category_top_k(category, is_ollama)
        query_text = (query_text or "").strip()
        if not query_text:
            print(
                f"[TestGen][rag] category={category} feature_id={feature_id} "
                f"k={top_k} query_chars=0 results=0 note=empty_query_no_retrieval",
                flush=True,
            )
            return _to_rag_context(rag_context.get("summary", ""), [])
        # Retrieval degrades, it never crashes generation. Store.search_feature_chunks()
        # already has this posture internally for its own two paths (a mongot outage
        # falls through to numpy cosine; an embedding-DIMENSION mismatch between the
        # query vector and the stored chunk vectors -- the realistic shape of a
        # partially-applied embedding-model switch through Settings -- degrades that one
        # retrieval to empty). The embed() call itself sat OUTSIDE that protection: a
        # provider timeout, an auth failure, or a model swapped mid-run raised straight
        # out of the pipeline and killed the whole job, including the four categories
        # that had nothing wrong with them. Both halves are now inside the same guard,
        # so a category that cannot retrieve falls back to an empty evidence block --
        # which the grounding filters then treat as "no evidence", the correct and safe
        # reading -- instead of taking the run down.
        try:
            query_embedding = embedder.embed(query_text, task="query")
            chunks = store.search_feature_chunks(
                query_embedding, feature_id, limit=top_k, category=category
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[TestGen][rag] category={category} feature_id={feature_id} k={top_k} "
                f"query_chars={len(query_text)} results=0 "
                f"note=retrieval_failed_degraded_to_empty error={exc}",
                flush=True,
            )
            return _to_rag_context(rag_context.get("summary", ""), [])
        print(
            f"[TestGen][rag] category={category} feature_id={feature_id} k={top_k} "
            f"query_chars={len(query_text)} results={len(chunks)} "
            f"chunk_ids={[c.get('chunk_id') for c in chunks]} "
            f"chunk_indexes={[c.get('chunk_index') for c in chunks]} "
            f"scores={[c.get('score') for c in chunks]}",
            flush=True,
        )
        return _to_rag_context(rag_context.get("summary", ""), chunks)

    api_query_text = _build_api_retrieval_query(entities, api_surface, context.get("businessContext"))
    ui_query_text = _build_ui_retrieval_query(ui_components, context.get("featureName"))
    e2e_query_text = _build_e2e_retrieval_query(
        context.get("businessContext"), context.get("featureName"), context.get("featureDescription")
    )
    business_query_text = _build_business_retrieval_query(
        context.get("businessContext"), context.get("featureName"), context.get("featureDescription")
    )
    api_rag_context = _retrieve_category_context("api", api_query_text)
    ui_rag_context = _retrieve_category_context("ui", ui_query_text)
    e2e_rag_context = _retrieve_category_context("e2e", e2e_query_text)
    # Business generation (both the primary combined E2E/edge/business call and the
    # build_business_test_prompt() fallback) gets its own category retrieval, computed
    # once here and reused by both call sites -- same "retrieve once per category per
    # run" rule as api/ui/e2e above.
    business_rag_context = _retrieve_category_context("business", business_query_text)

    log_progress(update_job_fn, "Fusion: analyzing previous and project test coverage", 28)
    project_tests = _project_existing_tests(store, project_id)
    project_tests, fusion_tests_dropped = _bound_project_tests_for_fusion(
        project_tests,
        f"{context.get('featureName', '')} {context.get('featureDescription', '')}",
    )
    if fusion_tests_dropped:
        log_progress(
            update_job_fn,
            f"Fusion: {fusion_tests_dropped} project test case(s) left out of cross-"
            "feature reuse analysis to keep the request within a safe size",
            29,
        )
    inherited_reused = inherited_rebuilt = 0
    errors = []
    fusion = {}
    try:
        fusion = call_llm_json_with_repair(
            llm, SYSTEM, build_fusion_pass_prompt(context, project_tests), max_tokens=6000
        )
    except Exception as exc:  # noqa: BLE001 -- Fusion is an optimization (cross-feature
        # reuse detection), not a requirement for generating this feature's own tests.
        # A failure here -- an oversized prompt the budget above didn't fully prevent, a
        # transient provider error, anything -- must not take the whole run down; it
        # degrades to "no inheritance candidates this run" and fresh generation
        # continues normally, exactly like the E2E/business worker failures below
        # already degrade instead of crashing the pipeline.
        errors.append(f"Fusion pass failed: {exc}")
    context["summaries"]["alreadyCovered"] = str(fusion.get("already_covered_summary") or "")
    log_progress(
        update_job_fn,
        f"Fusion complete: {len(_as_list(fusion.get('inherited_tests')))} inheritance candidate(s)",
        33,
    )

    for reference in _as_list(fusion.get("inherited_tests")):
        if not isinstance(reference, dict):
            continue
        original = next(
            (
                case for case in previous_cases
                if case.get("id") == reference.get("reference_key") or
                case.get("title") == reference.get("title")
            ),
            None,
        )
        if not original:
            original = store.resolve_case_reference(
                reference.get("reference_key"), reference.get("title"), project_id
            )
            if original and not original.get("steps") and hasattr(store, "get_case"):
                original = store.get_case(original["id"]) or original
        if not original:
            continue
        mode = str(reference.get("mode") or "").upper()
        if mode == "INHERIT_EXACT":
            store.associate(feature_id, original["id"], "carried", None)
            inherited_reused += 1
        elif mode == "INHERIT_ADAPTED" and reference.get("repair_instructions"):
            try:
                repaired = call_llm_json_with_repair(
                    llm,
                    SYSTEM,
                    build_individual_test_repair_prompt(
                        context, original, reference["repair_instructions"]
                    ),
                    max_tokens=3500,
                )
                # The Fusion inheritance path persists directly, bypassing the suite
                # filters every freshly generated case passes through -- it was the one
                # route by which a model-written specific could reach the store
                # unchecked. An adapted case is adapted TO this version, so this
                # version's evidence is the right standard, and it is the same standard
                # the rest of the run is held to.
                if _unsupported_numeric_claims(repaired, corpus):
                    errors.append(
                        "Inherited test not carried over: the adapted version asserts "
                        "specifics this version's evidence does not support "
                        f"({original.get('title') or original.get('id')})"
                    )
                    continue
                if is_prompt_exemplar_copy(repaired, corpus):
                    errors.append(
                        "Inherited test not carried over: the adapted version copied "
                        "a prompt few-shot exemplar "
                        f"({original.get('title') or original.get('id')})"
                    )
                    continue
                _persist_case(
                    store,
                    embedder,
                    feature_id,
                    project_id,
                    repaired,
                    str(original.get("type") or "functional"),
                    origin="carried_repaired",
                )
                inherited_rebuilt += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Inherited test repair failed: {exc}")

    log_progress(update_job_fn, "DAG layer 1: generating API and UI tests", 38)
    api_chunks = _chunks(api_surface, 8) or [[]]
    # UI generation is conditioned on UI evidence actually existing. When ui_components
    # is empty -- Pass 1 grounded no UI element AND _derive_ui_components() found no
    # control in the raw document -- the previous `else [[]]` still queued one UI worker
    # whose prompt carried no UI subject at all, and a model asked for UI validations
    # with nothing to ground against answers with standard-looking invented form rules
    # (the field-length limits and button behavior found during live validation). That
    # vector is closed here, at the source, instead of being filtered after the fact --
    # and the otherwise-wasted LLM call is saved. When UI evidence DOES exist this is
    # byte-for-byte the previous behavior (one broad worker plus one per component
    # group), so genuine UI generation is untouched: an evidence-conditioned trigger,
    # not a suppression of the UI category.
    ui_chunks = [[], *_chunks(ui_components, 25)] if evidence_sufficient["ui"] else []
    jobs = []
    # These LLM calls run on ThreadPoolExecutor child threads; the token recorder
    # is thread-local, so bind the parent job's recorder inside each worker or the
    # (often dominant) generation cost is lost from Usage & Cost.
    _parent_rec = usage.current()

    def run_api_worker(values, mode, max_tokens):
        usage.bind(_parent_rec)
        prompt = build_api_agent_prompt(
            context, api_rag_context, values, mode, top_k=_category_top_k("api", is_ollama)
        )
        return call_llm_json_with_repair(
            llm,
            prompt["messages"][0]["content"],
            prompt["messages"][1]["content"],
            max_tokens=max_tokens,
            timeout_seconds=180,
        )

    def run_ui_worker(chunk):
        usage.bind(_parent_rec)
        prompt = build_ui_agent_prompt(
            context, chunk, ui_rag_context, top_k=_category_top_k("ui", is_ollama)
        )
        return call_llm_json_with_repair(
            llm,
            prompt["messages"][0]["content"],
            prompt["messages"][1]["content"],
            6500,
            2,
            180,
        )

    concurrency = max(1, min(6, int(os.getenv("TESTGEN_WORKER_CONCURRENCY", "3"))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        for chunk in api_chunks:
            if not chunk:
                continue
            jobs.append(("api", executor.submit(
                run_api_worker, chunk, "happy", 6500
            )))
            jobs.append(("api", executor.submit(
                run_api_worker, chunk, "negative", 6500
            )))
            risky = [api for api in chunk if _risky_api(api)]
            if risky:
                jobs.append(("api", executor.submit(
                    run_api_worker, risky, "chaos", 5000
                )))
        for chunk in ui_chunks:
            jobs.append(("ui", executor.submit(run_ui_worker, chunk)))

        api_tests, ui_tests = [], []
        future_kinds = {future: kind for kind, future in jobs}
        completed = 0
        for future in concurrent.futures.as_completed(future_kinds):
            kind = future_kinds[future]
            try:
                result = future.result()
                if kind == "api":
                    api_tests.extend(_as_list(result.get("api_tests")))
                else:
                    ui_tests.extend(_as_list(result.get("ui_validations")))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{kind.upper()} worker failed: {exc}")
            completed += 1
            progress = 38 + round(14 * completed / max(1, len(jobs)))
            log_progress(
                update_job_fn,
                f"DAG layer 1: completed {completed}/{len(jobs)} API/UI workers",
                progress,
            )

    api_tests = _ensure_api_endpoint_coverage(
        _filter_api_tests(_deduplicate(api_tests, "api_tests"), api_surface),
        api_surface,
    )
    ui_tests = _filter_ui_tests(
        _deduplicate(ui_tests, "ui_validations"), corpus, ui_components
    )
    log_progress(
        update_job_fn,
        f"DAG layer 1 complete: {len(api_tests)} API tests and "
        f"{len(ui_tests)} UI validations",
        53,
    )

    log_progress(update_job_fn, "DAG layer 2: generating E2E, edge, and business tests", 58)
    e2e_result = {}
    try:
        e2e_result = call_llm_json_with_repair(
            llm,
            SYSTEM,
            build_e2e_agent_prompt(
                context, api_surface[:80], ui_tests[:100], e2e_rag_context, len(api_surface),
                top_k=_category_top_k("e2e", is_ollama),
                # edge_cases and business_tests are produced by this SAME call
                # (build_e2e_agent_prompt's output has all three keys) but neither has
                # its own worker/LLM call, so each gets its own labeled evidence block
                # here instead of a dedicated retrieval call: edge_cases needs
                # API/state-mutation evidence (not journey evidence), business_tests
                # needs the business-category evidence also used by the
                # build_business_test_prompt() fallback below.
                api_rag_context=api_rag_context,
                api_top_k=_category_top_k("api", is_ollama),
                business_rag_context=business_rag_context,
                business_top_k=_category_top_k("business", is_ollama),
            ),
            max_tokens=10000,
            timeout_seconds=300,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"E2E worker failed: {exc}")

    e2e_tests = _as_list(e2e_result.get("e2e_tests"))
    if len(e2e_tests) < 5 and len(api_surface) > 10 and not params.get("smoke_mode"):
        try:
            fallback = call_llm_json_with_repair(
                llm,
                SYSTEM,
                build_e2e_fallback_prompt(
                    context, api_surface[:80], ui_tests[:100], e2e_rag_context,
                    top_k=_category_top_k("e2e", is_ollama),
                ),
                max_tokens=8000,
                timeout_seconds=240,
            )
            e2e_tests.extend(_as_list(fallback.get("e2e_tests")))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"E2E fallback failed: {exc}")

    business_tests = _as_list(e2e_result.get("business_tests"))
    business_context = context.get("businessContext") or {}
    requirement_count = len(_as_list(business_context.get("requirements")))
    if isinstance(business_context.get("prd"), dict):
        requirement_count = max(
            requirement_count,
            len(_as_list(business_context["prd"].get("requirements"))),
        )
    # The floor exists to top a thin business suite up against a feature that HAS
    # business rules to cover. When nothing business-shaped was extracted at all -- no
    # requirement lines, no acceptance criteria, no user stories -- there is nothing to
    # top up against, yet the unconditional max(3, ...) floor still fired this fallback:
    # a second LLM call whose only possible output is invented business rules, on any
    # feature whose documents happen to be purely technical. No evidence now means no
    # floor, so the fallback does not run. A feature WITH business evidence keeps the
    # previous floor formula and the previous behavior exactly.
    acceptable_business_min = (
        min(10, max(3, round(requirement_count * 0.6)))
        if evidence_sufficient["business"] else 0
    )
    if len(business_tests) < acceptable_business_min:
        try:
            fallback = call_llm_json_with_repair(
                llm, SYSTEM,
                build_business_test_prompt(
                    context, business_rag_context, top_k=_category_top_k("business", is_ollama)
                ),
                max_tokens=6000,
                timeout_seconds=240,
            )
            business_tests.extend(_as_list(fallback.get("business_tests")))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Business fallback failed: {exc}")

    # #64: every case a filter below drops is recorded here as (case, reason), so the
    # run can report a generated/persisted/rejected summary instead of dropping cases
    # silently. Reasons are the fixed REASON_* vocabulary from prompt_builder.py.
    filter_rejections: list[tuple[dict, str]] = []

    def _dedup_tracked(cases, category):
        kept, rejected = _deduplicate_with_reasons(cases, category)
        filter_rejections.extend(rejected)
        return kept

    suites = {
        "api_tests": _dedup_tracked(api_tests, "api_tests"),
        "ui_validations": ui_tests,
        "e2e_tests": _dedup_tracked(e2e_tests, "e2e_tests"),
        "edge_cases": _dedup_tracked(_as_list(e2e_result.get("edge_cases")), "edge_cases"),
        "business_tests": _dedup_tracked(business_tests, "business_tests"),
    }
    log_progress(
        update_job_fn,
        "DAG layer 2 complete: "
        f"{len(suites['e2e_tests'])} E2E, {len(suites['edge_cases'])} edge, "
        f"{len(suites['business_tests'])} business tests",
        66,
    )

    log_progress(update_job_fn, "RAG validation: checking requirement coverage", 70)
    gaps = _requirement_gaps(raw_text, suites)
    log_progress(
        update_job_fn,
        f"RAG validation complete: {len(gaps)} coverage gap(s) detected",
        73,
    )
    if gaps and not params.get("smoke_mode"):
        try:
            hashed = {
                key: [{**test, "_hash": test["identity_hash"][:12]} for test in values]
                for key, values in suites.items()
            }
            repair = call_llm_json_with_repair(
                llm,
                SYSTEM,
                build_repair_prompt({
                    "unifiedContext": context,
                    # Repair patches gaps across ALL FIVE suite types (api/ui/e2e/edge/
                    # business) in one response, not one category -- so unlike the API/UI/
                    # E2E generation prompts above it is deliberately NOT narrowed to a
                    # single category's evidence, and its raw PRD block is left in place
                    # (see build_repair_prompt()'s docstring for the full reasoning). Its
                    # ragContext channel is still swapped from the broad `rag_context` to
                    # `e2e_rag_context`, matching the explicit "E2E/fallback/repair -> E2E
                    # retrieval context" grouping in the approved architecture.
                    "ragContext": e2e_rag_context,
                    "topK": _category_top_k("e2e", is_ollama),
                    "currentResult": hashed,
                    "ragValidation": {
                        "status": "needs_repair",
                        "missing_count": len(gaps),
                        "issues": gaps,
                    },
                }),
                max_tokens=7000,
                attempts=2,
            )
            for suite_name in suites:
                delta_name = f"{suite_name}_delta"
                suites[suite_name] = _apply_delta(
                    hashed[suite_name], repair.get(delta_name) or {}, suite_name
                )
            suites["api_tests"] = _filter_api_tests(suites["api_tests"], api_surface)
            suites["api_tests"] = _dedup_tracked(
                _ensure_api_endpoint_coverage(suites["api_tests"], api_surface), "api_tests"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RAG delta repair failed: {exc}")

    # Category-agnostic content-level grounding guard (see _filter_ungrounded_claims'
    # module comment): applied to every suite, after any repair-pass additions above,
    # so fabricated content can't re-enter through that path either. Runs against the
    # same broad `corpus` used for entities/API grounding -- preserves the existing
    # broad-RAG-context-for-grounding architecture, adds no LLM call.
    suites = {
        name: _filter_ungrounded_claims(cases, corpus)
        for name, cases in suites.items()
    }
    # Prompt few-shots are examples, not the user's feature. Reject verbatim and
    # hybrid copies on every suite before persist (issue #36).
    for name, cases in suites.items():
        kept, rejected = filter_prompt_exemplar_copies_with_reasons(cases, corpus)
        suites[name] = kept
        filter_rejections.extend(rejected)
    # e2e / nfr must have some source overlap. Category-level "feature has a
    # description" was enough to let an ungrounded E2E exemplar ship.
    for suite_name in ("e2e_tests", "edge_cases"):
        kept, rejected = _filter_ungrounded_suite_cases_with_reasons(suites[suite_name], corpus)
        suites[suite_name] = kept
        filter_rejections.extend(rejected)
    # When edge evidence was insufficient we still ran the shared E2E call, and
    # whatever came back in edge_cases was persisted as nfr. Drop that suppressed
    # block; copies stuffed into e2e_tests are already removed above.
    if not evidence_sufficient.get("edge"):
        filter_rejections.extend((case, REASON_EDGE_SUPPRESSED) for case in suites["edge_cases"])
        suites["edge_cases"] = []

    suites = _budget_suites(
        suites, total, focus, smoke_mode=bool(params.get("smoke_mode"))
    )
    generated_count = sum(len(values) for values in suites.values())
    if generated_count == 0 and inherited_reused + inherited_rebuilt == 0:
        raise RuntimeError("EmptyGenerationError: no valid test cases survived normalization and evidence guards")

    # #64: log one line per rejected case (id/reason/title), plus a summary of
    # candidates -> persisted, so silent over- or under-filtering is visible instead
    # of only showing up as a smaller-than-expected suite with no explanation.
    for case, reason in filter_rejections:
        case_id = case.get("id") or case.get("test_slug") or "?"
        title = case.get("title") or ""
        print(f'[TestGen][filter] rejected id={case_id} reason={reason} title="{title}"', flush=True)
    rejected_by_reason: dict[str, int] = {}
    for _case, reason in filter_rejections:
        rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
    total_candidates = generated_count + len(filter_rejections)
    if filter_rejections:
        breakdown = ", ".join(f"{count} {reason}" for reason, count in sorted(rejected_by_reason.items()))
        log_progress(
            update_job_fn,
            f"Filter: {total_candidates} generated, {generated_count} persisted ({breakdown})",
            80,
        )

    log_progress(update_job_fn, "Persisting normalized and deduplicated test cases", 82)
    cases_new = cases_reused = steps_new = steps_reused = 0
    type_map = {
        "api_tests": "api",
        "ui_validations": "ui",
        "e2e_tests": "e2e",
        "edge_cases": "nfr",
        "business_tests": "functional",
    }
    by_type = {}
    for suite_name, cases in suites.items():
        new_for_type = reused_for_type = 0
        for case in cases:
            _, reused, new_steps, reused_steps = _persist_case(
                store, embedder, feature_id, project_id, case, type_map[suite_name]
            )
            steps_new += new_steps
            steps_reused += reused_steps
            if reused:
                cases_reused += 1
                reused_for_type += 1
            else:
                cases_new += 1
                new_for_type += 1
        by_type[type_map[suite_name]] = {
            "new": by_type.get(type_map[suite_name], {}).get("new", 0) + new_for_type,
            "reused": by_type.get(type_map[suite_name], {}).get("reused", 0) + reused_for_type,
        }

    log_progress(update_job_fn, "Generation complete", 100)
    out = {
        "cases_new": cases_new,
        "cases_reused": cases_reused,
        "steps_new": steps_new,
        "steps_reused": steps_reused,
        "by_type": by_type,
        "inherited_reused": inherited_reused,
        "inherited_rebuilt": inherited_rebuilt,
        "discovered_api_count": len(api_surface),
        "rag_gap_count": len(gaps),
        "errors": errors,
        # #64: generated/persisted/rejected summary for the exemplar/grounding/dedup
        # filters above, so the UI can show why a run produced fewer cases than
        # candidates without anyone having to read container logs.
        "testgen_filter": {
            "generated": total_candidates,
            "persisted": generated_count,
            "rejected": len(filter_rejections),
            "rejected_by_reason": rejected_by_reason,
        },
    }
    # "Either generate only what the evidence supports, or say the evidence was
    # insufficient" -- this is that second branch made visible. An empty suite on the job
    # is otherwise indistinguishable from "the model happened to return nothing", so the
    # reason is reported explicitly, per category, with the count that actually survived:
    # a category whose own call was skipped reports zero and why, while a category that
    # rides another category's call (edge_cases) and still produced something is flagged
    # for review rather than silently trusted.
    if insufficient:
        suite_of = {
            "api": "api_tests", "ui": "ui_validations", "e2e": "e2e_tests",
            "edge": "edge_cases", "business": "business_tests",
        }
        notes = []
        for name in sorted(insufficient):
            produced = len(suites.get(suite_of[name], []))
            notes.append(
                f"{name}: {produced} test(s) were generated although this feature's "
                f"documents contain no dedicated {name} evidence -- review their "
                "specifics before relying on them."
                if produced else _insufficient_evidence_warning(name)
            )
        out["evidence_insufficient"] = sorted(insufficient)
        out["warnings"] = (out.get("warnings") or []) + notes
    # "Degrade gracefully with a warning rather than letting the request fail" -- the
    # size budget above prevents the oversized-prompt failure, but silently dropping
    # part of the project's test history from reuse analysis is still a real,
    # user-visible change in what Fusion could see this run, so it is reported exactly
    # like the evidence-insufficiency notes above rather than only appearing in logs.
    if fusion_tests_dropped:
        out["fusion_context_truncated"] = fusion_tests_dropped
        out["warnings"] = (out.get("warnings") or []) + [
            f"fusion: {fusion_tests_dropped} project test case(s) were left out of "
            "cross-feature reuse analysis to keep the request within a safe size "
            "(the most relevant ones for this feature were kept). Some reuse "
            "opportunities in this large project may have been missed this run."
        ]
    # Semantic dedup silently returns nothing when vector search is down and the case
    # store is too big for the in-memory fallback. Surface that on the job instead of
    # letting the run look clean — otherwise near-duplicates land with no warning.
    degraded = getattr(store, "search_degraded", lambda *_a, **_k: None)("dedup")
    if degraded:
        out["dedup_degraded"] = degraded
        out["warnings"] = (out.get("warnings") or []) + [
            "Semantic de-duplication was SKIPPED for this run: vector search was "
            f"unavailable and the case store ({degraded.get('docs')} cases) exceeds the "
            f"in-memory fallback cap ({degraded.get('cap')}). Near-duplicate cases may "
            "have been created. Restore mongot and re-run to de-duplicate."
        ]
        log_progress(update_job_fn, "WARNING: semantic de-duplication was skipped (search degraded)")
    return out
