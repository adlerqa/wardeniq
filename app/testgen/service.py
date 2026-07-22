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
    is_few_shot_leak,
)
from testgen.lineage import (
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
            if raw_text.strip():
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


def _parse_raw_api_spec(raw_spec: str | None) -> list[dict]:
    found = {}
    for line in str(raw_spec or "").splitlines():
        match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s,;]+)", line, re.IGNORECASE)
        if not match:
            continue
        method = match.group(1).upper()
        endpoint = match.group(2).rstrip(".)]>")
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
        endpoint = str(item.get("endpoint") or item.get("path") or "").strip()
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


def _deduplicate(cases: list, category: str) -> list[dict]:
    seen_hashes = set()
    out = []
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
            continue
        seen_hashes.add(identity_hash)
        case["identity_hash"] = identity_hash
        case["test_slug"] = slug
        out.append(case)
    return sorted(out, key=lambda c: PRIORITY_ORDER.get(str(c.get("priority") or "P2").upper(), 2))


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


def _budget_suites(suites: dict, total: int, focus: dict, smoke_mode=False) -> dict:
    # The Node DAG treats worker ceilings as coverage controls. Its normal path
    # does not truncate the completed category suites to one global test count.
    # Preserve that behavior; only the explicit smoke path uses the small budget.
    if not smoke_mode:
        enabled = {
            name: float((focus or {}).get(name, 25)) > 0
            for name in ("functional", "e2e", "api", "nfr")
        }
        return {
            "api_tests": suites["api_tests"] if enabled["api"] else [],
            "ui_validations": suites["ui_validations"] if enabled["functional"] else [],
            "business_tests": suites["business_tests"] if enabled["functional"] else [],
            "e2e_tests": suites["e2e_tests"] if enabled["e2e"] else [],
            "edge_cases": suites["edge_cases"] if enabled["nfr"] else [],
        }
    if total <= 0:
        return suites
    weights = {name: max(0.0, float((focus or {}).get(name, 25))) for name in ("functional", "e2e", "api", "nfr")}
    weight_sum = sum(weights.values()) or 100.0
    targets = {name: max(0, round(total * value / weight_sum)) for name, value in weights.items()}
    api_endpoint_count = len({_api_key(case) for case in suites["api_tests"]})
    api_allowance = max(targets["api"], api_endpoint_count)

    functional_total = targets["functional"]
    has_ui = bool(suites["ui_validations"])
    has_business = bool(suites["business_tests"])
    if has_ui and has_business and functional_total > 1:
        ui_allowance = (functional_total + 1) // 2
        business_allowance = functional_total - ui_allowance
    elif has_ui:
        ui_allowance, business_allowance = functional_total, 0
    else:
        ui_allowance, business_allowance = 0, functional_total

    return {
        "api_tests": suites["api_tests"][:api_allowance],
        "ui_validations": suites["ui_validations"][:ui_allowance],
        "business_tests": suites["business_tests"][:business_allowance],
        "e2e_tests": suites["e2e_tests"][:targets["e2e"]],
        "edge_cases": suites["edge_cases"][:targets["nfr"]],
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
        ) >= 0.35
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
    ) >= 0.65


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
    focus = params.get("focus") or {name: 25 for name in ("functional", "e2e", "api", "nfr")}

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
    corpus = _evidence_corpus(context, rag_context).lower()
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

    log_progress(update_job_fn, "Fusion: analyzing previous and project test coverage", 28)
    project_tests = _project_existing_tests(store, project_id)
    fusion = call_llm_json_with_repair(
        llm, SYSTEM, build_fusion_pass_prompt(context, project_tests), max_tokens=6000
    )
    context["summaries"]["alreadyCovered"] = str(fusion.get("already_covered_summary") or "")
    log_progress(
        update_job_fn,
        f"Fusion complete: {len(_as_list(fusion.get('inherited_tests')))} inheritance candidate(s)",
        33,
    )

    inherited_reused = inherited_rebuilt = 0
    errors = []
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
    ui_chunks = [[], *_chunks(ui_components, 25)] if ui_components else [[]]
    jobs = []
    # These LLM calls run on ThreadPoolExecutor child threads; the token recorder
    # is thread-local, so bind the parent job's recorder inside each worker or the
    # (often dominant) generation cost is lost from Usage & Cost.
    _parent_rec = usage.current()

    def run_api_worker(values, mode, max_tokens):
        usage.bind(_parent_rec)
        prompt = build_api_agent_prompt(context, rag_context, values, mode)
        return call_llm_json_with_repair(
            llm,
            prompt["messages"][0]["content"],
            prompt["messages"][1]["content"],
            max_tokens=max_tokens,
            timeout_seconds=180,
        )

    def run_ui_worker(chunk):
        usage.bind(_parent_rec)
        prompt = build_ui_agent_prompt(context, chunk)
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
            build_e2e_agent_prompt(context, api_surface[:80], ui_tests[:100], rag_context, len(api_surface)),
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
                    context, api_surface[:80], ui_tests[:100], rag_context
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
    acceptable_business_min = min(10, max(3, round(requirement_count * 0.6)))
    if len(business_tests) < acceptable_business_min:
        try:
            fallback = call_llm_json_with_repair(
                llm, SYSTEM, build_business_test_prompt(context), max_tokens=6000,
                timeout_seconds=240,
            )
            business_tests.extend(_as_list(fallback.get("business_tests")))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Business fallback failed: {exc}")

    suites = {
        "api_tests": _deduplicate(api_tests, "api_tests"),
        "ui_validations": ui_tests,
        "e2e_tests": _deduplicate(e2e_tests, "e2e_tests"),
        "edge_cases": _deduplicate(_as_list(e2e_result.get("edge_cases")), "edge_cases"),
        "business_tests": _deduplicate(business_tests, "business_tests"),
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
                    "ragContext": rag_context,
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
            suites["api_tests"] = _deduplicate(
                _ensure_api_endpoint_coverage(suites["api_tests"], api_surface), "api_tests"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RAG delta repair failed: {exc}")

    suites = _budget_suites(
        suites, total, focus, smoke_mode=bool(params.get("smoke_mode"))
    )
    generated_count = sum(len(values) for values in suites.values())
    if generated_count == 0 and inherited_reused + inherited_rebuilt == 0:
        raise RuntimeError("EmptyGenerationError: no valid test cases survived normalization and evidence guards")

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
    return {
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
    }
