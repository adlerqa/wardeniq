"""Pure metric helpers for the generation-quality evaluation (issue #43).

No I/O, no model, no network: everything here takes plain data and returns plain data, so
it is unit-tested without a model. The runner (scripts/eval_generation.py) feeds it what
the real generation pipeline returned.

What is a DIRECT pipeline signal and what is a HEURISTIC:

  direct      testgen_filter counts (generated / persisted / rejected / rejected_by_reason),
              the pipeline's own requirement-gap list, progress-stage timings, LLM call
              timings and token usage. These are recorded exactly as the pipeline reports
              them; this module only normalises and divides. The grounding-survivor counts
              are also the pipeline's own numbers, but it only reports them as progress
              text, so they are parsed out of that text (None if the wording changes).
  heuristic   requirement_coverage() below. It is a keyword check against a small
              hand-labelled fixture, not a judgement that a case is correct.

Rates use the number of candidates the model produced BEFORE filtering ("generated") as the
denominator, so they describe the model, not the post-filter suite. When the denominator is
zero or unknown the rate is None, never 0.0: "nothing was generated" must not read as
"nothing was wrong".
"""
import hashlib
import math
import re

from testgen.prompt_builder import (
    REASON_DUPLICATE,
    REASON_EDGE_SUPPRESSED,
    REASON_EXEMPLAR_COPY,
    REASON_HYBRID_SCAFFOLD,
    REASON_NO_SOURCE_GROUNDING,
)

KNOWN_REASONS = (
    REASON_EXEMPLAR_COPY,
    REASON_HYBRID_SCAFFOLD,
    REASON_NO_SOURCE_GROUNDING,
    REASON_DUPLICATE,
    REASON_EDGE_SUPPRESSED,
)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _as_count(value):
    """A non-negative whole number, or None."""
    if _is_number(value) and value >= 0 and float(value).is_integer():
        return int(value)
    return None


def rate(count, denominator):
    """count / denominator to 4 places, or None if either is missing/invalid or the
    denominator is not positive."""
    if not _is_number(count) or not _is_number(denominator) or denominator <= 0:
        return None
    return round(count / denominator, 4)


def corpus_hash(data: bytes) -> str:
    """Full sha256 of the corpus bytes (identifies exactly what was evaluated)."""
    return hashlib.sha256(data).hexdigest()


def summarize_filter(testgen_filter) -> dict:
    """Normalise the pipeline's out["testgen_filter"] into counts and rates.

    Returns {"available": False, "reason": ...} when the block is missing or malformed, so
    a pipeline change cannot silently turn into zeros.
    """
    if not isinstance(testgen_filter, dict):
        return {"available": False, "reason": "testgen_filter is missing or not a mapping"}
    generated = _as_count(testgen_filter.get("generated"))
    persisted = _as_count(testgen_filter.get("persisted"))
    rejected = _as_count(testgen_filter.get("rejected"))
    if generated is None or persisted is None or rejected is None:
        return {"available": False,
                "reason": "generated/persisted/rejected must be non-negative whole numbers"}

    raw_reasons = testgen_filter.get("rejected_by_reason")
    raw_reasons = raw_reasons if isinstance(raw_reasons, dict) else {}
    counts, ignored = {}, []
    for reason, value in raw_reasons.items():
        n = _as_count(value)
        if n is None:
            ignored.append(str(reason))
        else:
            counts[str(reason)] = n

    reasons = {r: {"count": counts.get(r, 0), "rate": rate(counts.get(r, 0), generated)}
               for r in KNOWN_REASONS}
    other = {r: n for r, n in counts.items() if r not in KNOWN_REASONS}
    return {
        "available": True,
        "generated": generated,
        "persisted": persisted,
        "rejected": rejected,
        "persisted_rate": rate(persisted, generated),
        "rejected_rate": rate(rejected, generated),
        "reasons": reasons,
        "other_reasons": other,
        "ignored_reason_entries": sorted(ignored),
        "reasons_sum_matches_rejected": sum(counts.values()) == rejected,
    }


def stage_durations(marks, end_time) -> list:
    """Turn progress marks [(timestamp, stage, progress), ...] into per-stage durations.

    A stage lasts from its mark to the next mark; the last one lasts until `end_time`.
    Malformed marks are skipped. Stages overlap nothing: they are the pipeline's own
    sequential progress messages.
    """
    clean = []
    for mark in marks or []:
        if isinstance(mark, (tuple, list)) and len(mark) == 3 and _is_number(mark[0]):
            clean.append((float(mark[0]), str(mark[1]), mark[2]))
    out = []
    for i, (started, stage, progress) in enumerate(clean):
        stop = clean[i + 1][0] if i + 1 < len(clean) else end_time
        seconds = max(0.0, float(stop) - started) if _is_number(stop) else 0.0
        out.append({"stage": stage, "progress": progress, "seconds": round(seconds, 3)})
    return out


_SURVIVORS_RE = re.compile(
    r"(\d+)\s+entit(?:y|ies),\s*(\d+)\s+APIs?,\s*(\d+)\s+UI components?\s+survived\s+sanitization",
    re.IGNORECASE)


def parse_grounding_survivors(stages):
    """How many grounded entities / APIs / UI components survived the pipeline's grounding
    pass, read from the pipeline's own progress message ("Pass 1 complete: 0 entities, 2
    APIs, 2 UI components survived sanitization"). The pipeline reports this only as text,
    so this is None, not zeros, if the message is absent or its wording changes."""
    for stage in stages or []:
        text = stage.get("stage") if isinstance(stage, dict) else None
        match = _SURVIVORS_RE.search(text) if isinstance(text, str) else None
        if match:
            entities, apis, ui = (int(g) for g in match.groups())
            return {"entities": entities, "apis": apis, "ui_components": ui}
    return None


def llm_call_summary(calls) -> dict:
    """Roll up recorded LLM calls: [{"seconds", "prompt_chars", "response_chars", "ok"}].

    `total_seconds` is the SUM of call durations; the pipeline runs some calls in parallel,
    so it can exceed the wall-clock time of the run.
    """
    seconds, prompt_chars, response_chars, failed, count = [], 0, 0, 0, 0
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        count += 1
        if _is_number(call.get("seconds")):
            seconds.append(float(call["seconds"]))
        prompt_chars += int(call["prompt_chars"]) if _is_number(call.get("prompt_chars")) else 0
        response_chars += int(call["response_chars"]) if _is_number(call.get("response_chars")) else 0
        if call.get("ok") is False:
            failed += 1
    return {
        "count": count,
        "failed": failed,
        "total_seconds": round(sum(seconds), 3),
        "max_seconds": round(max(seconds), 3) if seconds else None,
        "mean_seconds": round(sum(seconds) / len(seconds), 3) if seconds else None,
        "prompt_chars": prompt_chars,
        "response_chars": response_chars,
    }


def flatten_strings(value) -> list:
    """Every string nested anywhere inside `value` (dicts, lists, tuples)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in flatten_strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in flatten_strings(v)]
    return []


def case_text(case) -> str:
    """Lower-cased user-visible text of one persisted case: title, preconditions, steps."""
    if not isinstance(case, dict):
        return ""
    parts = []
    for key in ("title", "preconditions", "steps"):
        parts.extend(flatten_strings(case.get(key)))
    return " ".join(" ".join(parts).lower().split())


def requirement_coverage(requirements, case_texts) -> dict:
    """HEURISTIC: which fixture requirements does at least one case mention?

    A requirement is "covered" when some case text contains, for EVERY group in its
    `must_mention`, at least one of that group's alternative phrases. This only says a
    case talks about the requirement's key terms; it does not say the case is right.
    Invalid requirement entries are skipped and counted.
    """
    texts = [t.lower() for t in (case_texts or []) if isinstance(t, str)]
    per, invalid = [], 0
    for req in requirements or []:
        groups = req.get("must_mention") if isinstance(req, dict) else None
        if (not isinstance(req, dict) or not req.get("id") or not isinstance(groups, list)
                or not groups
                or not all(isinstance(g, (list, tuple)) and g and all(isinstance(a, str) and a
                                                                       for a in g)
                           for g in groups)):
            invalid += 1
            continue
        matching = [i for i, text in enumerate(texts)
                    if all(any(alt.lower() in text for alt in group) for group in groups)]
        per.append({"id": req["id"], "covered": bool(matching), "case_count": len(matching)})
    total = len(per)
    covered = sum(1 for p in per if p["covered"])
    return {
        "method": "keyword-heuristic",
        "total": total,
        "covered": covered,
        "rate": rate(covered, total),
        "uncovered_ids": [p["id"] for p in per if not p["covered"]],
        "invalid_requirements": invalid,
        "per_requirement": per,
    }


def flatten_run(run) -> dict:
    """The numeric metrics of one successful run, as a flat {name: number-or-None} map."""
    flat = {}
    flt = (run or {}).get("filter") or {}
    if flt.get("available"):
        for key in ("generated", "persisted", "rejected", "persisted_rate", "rejected_rate"):
            flat[key] = flt.get(key)
        for reason, short in ((REASON_EXEMPLAR_COPY, "exemplar_copy"),
                              (REASON_HYBRID_SCAFFOLD, "hybrid_scaffold"),
                              (REASON_NO_SOURCE_GROUNDING, "no_source_grounding"),
                              (REASON_DUPLICATE, "duplicate")):
            entry = (flt.get("reasons") or {}).get(reason) or {}
            flat[f"{short}_count"] = entry.get("count")
            flat[f"{short}_rate"] = entry.get("rate")
    survivors = (run or {}).get("grounding_survivors")
    if isinstance(survivors, dict):
        for key in ("entities", "apis", "ui_components"):
            flat[f"grounding_{key}"] = survivors.get(key)
    flat["requirement_coverage_rate"] = ((run or {}).get("requirement_coverage") or {}).get("rate")
    gaps = (run or {}).get("requirement_gaps") or {}
    flat["pipeline_gap_count"] = gaps.get("count") if isinstance(gaps, dict) else None
    timings = (run or {}).get("timings") or {}
    flat["ingest_seconds"] = timings.get("ingest_seconds")
    flat["pipeline_seconds"] = timings.get("pipeline_seconds")
    usage_block = (run or {}).get("usage") or {}
    flat["prompt_tokens"] = usage_block.get("prompt_tokens")
    flat["completion_tokens"] = usage_block.get("completion_tokens")
    return flat


def aggregate_repeats(runs) -> dict:
    """Mean / min / max of each metric across the SUCCESSFUL repeats.

    n is how many repeats contributed a number for that metric. With few repeats these are
    descriptive only; they are not confidence intervals.
    """
    runs = [r for r in (runs or []) if isinstance(r, dict)]
    ok = [r for r in runs if r.get("ok")]
    flats = [flatten_run(r) for r in ok]
    names = sorted({k for f in flats for k in f})
    metrics = {}
    for name in names:
        values = [f[name] for f in flats if _is_number(f.get(name))]
        metrics[name] = {
            "n": len(values),
            "mean": round(sum(values) / len(values), 4) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return {"repeats_total": len(runs), "repeats_ok": len(ok), "metrics": metrics}
