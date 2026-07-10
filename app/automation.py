"""Automation coverage: scan a connected test repo, extract test cases, then
match each extracted test against the wardenIQ-generated cases.

Matching is **hybrid**:
  1. Cheap, deterministic Jaccard + domain-boost prefilter narrows down to the
     top K=5 candidate generated cases per scanned test.
  2. An LLM verifier picks the single best match (or "no match") with a score
     and short rationale.

This is more recall-friendly than Node's pure-Jaccard matcher while still
keeping LLM cost bounded (one verifier call per generated case, not per pair).
"""
from __future__ import annotations

import io
import json
import os
import re
import tarfile
from typing import Iterable

# ---------------------------------------------------------------- framework detect
_TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|specs|e2e|cypress|cy|playwright|features?|stories|scenarios)/"
    r"|(?:test_|_test|\.test\.|\.spec\.|\.cy\.|\.feature$)",
    re.IGNORECASE,
)

_SKIP_DIRS = re.compile(r"(?:^|/)(?:node_modules|\.git|dist|build|out|\.next|coverage)/")
_ALLOWED_EXT = re.compile(r"\.(?:ts|tsx|js|jsx|py|rb|java|kt|go|cs|feature|md|json)$", re.IGNORECASE)
MAX_FILES = 400
MAX_FILE_BYTES = 200_000


def is_test_path(p: str) -> bool:
    if not p:
        return False
    if _SKIP_DIRS.search(p):
        return False
    if not _ALLOWED_EXT.search(p):
        return False
    return bool(_TEST_FILE_RE.search(p))


def detect_framework(path: str, content: str) -> str:
    p = (path or "").lower()
    if p.endswith(".feature"):
        return "Cucumber"
    if p.endswith(".md"):
        return "Markdown"
    if p.endswith(".json"):
        return "JSON"
    if "playwright" in content or "@playwright/test" in content or "page.locator(" in content:
        return "Playwright"
    if "cypress" in content or "cy.visit(" in content or ".cy." in p:
        return "Cypress"
    if "import pytest" in content or re.search(r"^def test_", content, re.M):
        return "Pytest"
    if "@Test" in content and re.search(r"public\s+(class|void)\b", content):
        return "JUnit / TestNG"
    if "describe(" in content or "it(" in content or "test(" in content:
        return "Jest / Mocha"
    return "Other"


# ---------------------------------------------------------------- title extract
_JS_TITLE = re.compile(
    r"(?:it|test|test\.(?:describe|step|skip|only)|describe)\s*"
    r"\(\s*(?P<q>['\"`])(?P<title>[^'\"`\n][^'\"`\n]{1,300})(?P=q)",
)
_PY_FN = re.compile(r"^\s*def\s+(test_[a-zA-Z0-9_]+)\s*\(", re.M)
_FEATURE = re.compile(r"^\s*(?:Scenario(?:\s+Outline)?|Example):\s*(?P<t>.+)$", re.M)
_FEATURE_NAME = re.compile(r"^\s*Feature:\s*(?P<t>.+)$", re.M)
_MD_TC = re.compile(r"^(?:#+\s*|[-*]\s*)(?:TC[-_ ]?\d+[:\-\s]+)?(?P<t>[^\n]{6,200})$", re.M | re.IGNORECASE)
_JSON_KEYS = ("testcases", "test_cases", "tests", "cases", "scenarios", "items",
              "api_tests", "e2e_tests", "ui_validations", "edge_cases", "business_tests")


def extract_tests(path: str, content: str, framework: str) -> list[dict]:
    """Return list of {title, line, raw_excerpt} for tests found in this file.

    A best-effort extractor — wraps each framework's typical declaration style.
    """
    out: list[dict] = []
    seen = set()

    def _add(title: str, line: int = 0):
        t = (title or "").strip().strip("`'\"")
        if 4 <= len(t) <= 240 and t.lower() not in seen:
            seen.add(t.lower())
            out.append({"title": t, "line": line})

    if framework == "Cucumber":
        feat_match = _FEATURE_NAME.search(content)
        feature_name = (feat_match.group("t") or "").strip() if feat_match else ""
        for m in _FEATURE.finditer(content):
            line = content[:m.start()].count("\n") + 1
            _add((feature_name + " — " if feature_name else "") + m.group("t").strip(), line)
        return out

    if framework == "Markdown":
        for m in _MD_TC.finditer(content):
            line = content[:m.start()].count("\n") + 1
            _add(m.group("t").strip(), line)
        return out

    if framework == "JSON":
        try:
            data = json.loads(content)
        except Exception:  # noqa: BLE001
            return out

        def _walk(obj):
            if isinstance(obj, dict):
                if "title" in obj and isinstance(obj["title"], str):
                    _add(obj["title"])
                for k in _JSON_KEYS:
                    if k in obj and isinstance(obj[k], list):
                        for it in obj[k]:
                            _walk(it)
                for v in obj.values():
                    _walk(v) if isinstance(v, (dict, list)) else None
            elif isinstance(obj, list):
                for it in obj:
                    _walk(it)

        _walk(data)
        return out

    if framework == "Pytest":
        for m in _PY_FN.finditer(content):
            line = content[:m.start()].count("\n") + 1
            t = m.group(1).replace("test_", "").replace("_", " ")
            _add(t, line)
        # also catch docstring-style test names
        return out

    # JS / TS / Playwright / Cypress / Jest / Mocha — same syntax surface.
    for m in _JS_TITLE.finditer(content):
        line = content[:m.start()].count("\n") + 1
        _add(m.group("title"), line)
    return out


# ---------------------------------------------------------------- tar walk
def files_from_tarball(tar_bytes: bytes) -> Iterable[tuple[str, str]]:
    """Yield (relative_path, content_text) for likely test files in a GitHub
    tarball. Skips non-test paths, dotfiles, vendored deps, oversize files."""
    yielded = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            # GitHub tarballs root is `owner-repo-<sha>/`; strip first segment.
            parts = member.name.split("/", 1)
            rel = parts[1] if len(parts) == 2 else parts[0]
            if not is_test_path(rel):
                continue
            if (member.size or 0) > MAX_FILE_BYTES:
                continue
            try:
                f = tar.extractfile(member)
                if not f:
                    continue
                data = f.read()
                if not data:
                    continue
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    continue
                yield rel, text
                yielded += 1
                if yielded >= MAX_FILES:
                    break
            except Exception:  # noqa: BLE001
                continue


# ---------------------------------------------------------------- mapping
_STOP = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
         "should", "must", "be", "is", "are", "by", "when", "then", "given",
         "test", "case", "verify", "check", "ensure", "via", "as", "if"}

_TOKEN = re.compile(r"[a-z0-9]+")
_HTTP_VERBS = {"get", "post", "put", "patch", "delete"}
_API_PATH = re.compile(r"/[a-z][a-z0-9_/{}-]+")
_STATUS_CODE = re.compile(r"\b(?:2\d\d|3\d\d|4\d\d|5\d\d)\b")


def _tokenize(s: str) -> set[str]:
    return {t for t in _TOKEN.findall((s or "").lower()) if t not in _STOP and len(t) > 1}


def _domain_signal(s: str) -> tuple[set[str], set[str], set[str]]:
    s_low = (s or "").lower()
    return (
        {v for v in _HTTP_VERBS if v in s_low},
        set(_API_PATH.findall(s_low)),
        set(_STATUS_CODE.findall(s_low)),
    )


def jaccard_score(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    j = len(inter) / len(union) if union else 0.0
    # Domain boost (HTTP/path/status alignment) — up to +0.4
    boost = 0.0
    va, pa, sa = _domain_signal(a)
    vb, pb, sb = _domain_signal(b)
    if va & vb:
        boost += 0.10
    if pa & pb:
        boost += 0.20
    if sa & sb:
        boost += 0.10
    return min(j + boost, 1.0)


# ---------------------------------------------------------------- LLM verifier
_HYBRID_SYS = (
    "You are matching one wardenIQ-generated test case against a small set of automation "
    "tests from a repository. Decide which automation test (if any) implements the same "
    "behaviour as the generated case. Return JSON only."
)

_HYBRID_BATCH_SYS = (
    "You are matching wardenIQ-generated test cases against automation tests from a "
    "repository. For each generated case you'll get a small candidate list. Decide which "
    "candidate (if any) implements the same behaviour. Return JSON only."
)


def llm_verify_batch(llm, items: list[dict]) -> dict:
    """One LLM call resolves up to ~20 ambiguous cases at once. `items` is a
    list of {generated:{id,title,type,steps}, candidates:[{id,title,framework,file_path}, ...]}.

    Returns {decisions: [{generated_id, match_id|null, score, rationale}]}.
    The same per-call try/except contract as the single-case variant — caller
    treats exceptions as 'no match' for every item in this batch."""
    if not items:
        return {"decisions": []}
    prompt = (
        "For each generated test case below, choose the SINGLE candidate that best "
        "implements the same behaviour. If none of the candidates match, return "
        "match_id=null. Score 0.0-1.0. Only score ≥0.6 counts as a real match.\n\n"
        f"INPUT:\n{json.dumps({'items': items})[:8000]}\n\n"
        'Return JSON: {"decisions":[{"generated_id":"...", "match_id":"<id or null>",'
        '"score":0.0-1.0,"rationale":"one sentence"}]}.'
    )
    try:
        data = llm.chat_json(_HYBRID_BATCH_SYS, prompt, temperature=0.1,
                             max_tokens=2400, retries=0)
    except Exception as e:  # noqa: BLE001
        return {"decisions": [{"generated_id": it["generated"]["id"],
                                "match_id": None, "score": 0.0,
                                "rationale": f"llm error: {e}"} for it in items]}
    out = []
    for d in (data.get("decisions") or []):
        if not isinstance(d, dict):
            continue
        out.append({
            "generated_id": d.get("generated_id"),
            "match_id": d.get("match_id"),
            "score": float(d.get("score") or 0.0),
            "rationale": str(d.get("rationale", ""))[:300],
        })
    return {"decisions": out}


def _format_step(s):
    if isinstance(s, dict):
        return {"action": s.get("action") or "", "expected": s.get("expected") or ""}
    s_str = str(s or "")
    if " -> " in s_str:
        parts = s_str.split(" -> ", 1)
        return {"action": parts[0], "expected": parts[1]}
    return {"action": s_str, "expected": ""}


def llm_verify_match(llm, generated_case: dict, candidates: list[dict]) -> dict:
    """Ask the LLM to pick the best match (or none) for a single generated case.

    Returns {"match_id": str|None, "score": 0..1, "rationale": str}.
    The candidates list should already be Jaccard-prefiltered to ~5 entries to
    keep this prompt cheap.
    """
    if not candidates:
        return {"match_id": None, "score": 0.0, "rationale": "no candidates"}
    payload = {
        "generated": {
            "id": generated_case.get("id"),
            "title": generated_case.get("title"),
            "type": generated_case.get("type"),
            "steps": [_format_step(s) for s in (generated_case.get("steps") or [])[:6]],
        },
        "candidates": [{
            "id": c.get("id"),
            "title": c.get("title"),
            "framework": c.get("framework", ""),
            "file_path": c.get("file_path", ""),
        } for c in candidates[:5]],
    }
    prompt = (
        "Given a wardenIQ-generated test case and a small list of automation tests from a "
        "repository, choose the SINGLE candidate that best implements the same behaviour. "
        "If none of them match, return match_id=null.\n\n"
        f"INPUT:\n{json.dumps(payload)[:3500]}\n\n"
        'Return JSON: {"match_id":"<candidate id or null>","score":0.0-1.0,'
        '"rationale":"one sentence"}. Score ≥0.6 means a real match; below 0.6, return null.'
    )
    try:
        # Short timeout — match decisions don't need long generation budgets.
        # Falls through to "no match" if the model is slow or unavailable.
        data = llm.chat_json(_HYBRID_SYS, prompt, temperature=0.1,
                             max_tokens=400, retries=0)
    except Exception as e:  # noqa: BLE001
        return {"match_id": None, "score": 0.0, "rationale": f"llm error: {e}"}
    mid = data.get("match_id")
    score = float(data.get("score") or 0.0)
    if score < 0.6:
        return {"match_id": None, "score": score,
                "rationale": str(data.get("rationale", ""))[:300]}
    valid_ids = {c.get("id") for c in candidates}
    if mid not in valid_ids:
        return {"match_id": None, "score": 0.0, "rationale": "model returned unknown id"}
    return {"match_id": str(mid), "score": min(score, 1.0),
            "rationale": str(data.get("rationale", ""))[:300]}


def hybrid_match_generated_to_scanned(llm, generated_cases: list[dict],
                                       scanned_cases: list[dict],
                                       jaccard_threshold: float = 0.18,
                                       jaccard_fast_path: float = 0.65,
                                       top_k: int = 3,
                                       batch_size: int = 20,
                                       use_llm: bool = True,
                                       progress_fn=None) -> list[dict]:
    """For each generated case, find the best matching scanned automation test.

    Three-tier strategy:
      Jaccard >= jaccard_fast_path → accept immediately, NO LLM call.
      jaccard_threshold ≤ score < jaccard_fast_path → batched LLM verifier.
      < jaccard_threshold → no match.

    The LLM verifier is now BATCHED — one call resolves up to `batch_size`
    ambiguous cases. For a typical feature with ~67 generated cases this
    collapses 67 LLM calls into 1–4, dropping scan time from minutes to
    seconds. Per-call try/except still applies — a stuck batch falls through
    to 'no match' for every case in it without blocking the rest.

    `progress_fn(done, total)` fires after each generated case.

    Returns a list aligned with `generated_cases`:
        {"generated_id", "match": {"id","title","file_path","framework","score","rationale"} | None}
    """
    by_id = {c.get("id"): c for c in scanned_cases}
    total = len(generated_cases)
    out_by_gid = {}
    candidate_lookup = {}      # generated_id → {"top": (score, scanned), "candidates": [...] }
    fast_path_hits = 0

    # ---- pass 1: Jaccard scoring + fast-path bucketing ----------------------
    for idx, g in enumerate(generated_cases):
        gid = g.get("id")
        title = g.get("title", "")
        scored = []
        for s in scanned_cases:
            sc = jaccard_score(title, s.get("title", ""))
            if sc >= jaccard_threshold:
                scored.append((sc, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[0] if scored else None
        if not top:
            out_by_gid[gid] = {"generated_id": gid, "match": None}
            if progress_fn:
                progress_fn(idx + 1, total)
            continue
        top_score, top_match = top
        if top_score >= jaccard_fast_path:
            fast_path_hits += 1
            out_by_gid[gid] = {"generated_id": gid, "match": {
                "id": top_match.get("id"), "title": top_match.get("title"),
                "file_path": top_match.get("file_path", ""),
                "framework": top_match.get("framework", ""),
                "score": round(top_score, 3),
                "rationale": f"high title overlap (jaccard {top_score:.2f})"}}
            if progress_fn:
                progress_fn(idx + 1, total)
            continue
        candidate_lookup[gid] = {
            "generated": g, "top": top,
            "candidates": [s for _, s in scored[:top_k]],
        }
        if progress_fn:
            progress_fn(idx + 1, total)

    ambiguous = [gid for gid in (g.get("id") for g in generated_cases)
                 if gid in candidate_lookup]

    # ---- pass 2: batched LLM verifier on the ambiguous middle ---------------
    llm_hits = 0
    llm_misses = 0
    if ambiguous and use_llm:
        for start in range(0, len(ambiguous), batch_size):
            batch_ids = ambiguous[start:start + batch_size]
            items = [{
                "generated": {
                    "id": gid,
                    "title": candidate_lookup[gid]["generated"].get("title", ""),
                    "type": candidate_lookup[gid]["generated"].get("type", ""),
                    "steps": [_format_step(s) for s in (candidate_lookup[gid]["generated"].get("steps") or [])[:4]],
                },
                "candidates": [{
                    "id": c.get("id"), "title": c.get("title", ""),
                    "framework": c.get("framework", ""),
                    "file_path": c.get("file_path", ""),
                } for c in candidate_lookup[gid]["candidates"]],
            } for gid in batch_ids]
            try:
                resp = llm_verify_batch(llm, items)
            except Exception as e:  # noqa: BLE001
                resp = {"decisions": [{"generated_id": gid, "match_id": None,
                                        "score": 0.0, "rationale": f"llm error: {e}"}
                                       for gid in batch_ids]}
            decisions_by_gid = {d.get("generated_id"): d
                                for d in (resp.get("decisions") or [])}
            for gid in batch_ids:
                d = decisions_by_gid.get(gid) or {"match_id": None, "score": 0.0,
                                                    "rationale": "no decision returned"}
                mid = d.get("match_id")
                score = float(d.get("score") or 0.0)
                if mid and mid in by_id and score >= 0.6:
                    best = by_id[mid]
                    out_by_gid[gid] = {"generated_id": gid, "match": {
                        "id": best.get("id"), "title": best.get("title"),
                        "file_path": best.get("file_path", ""),
                        "framework": best.get("framework", ""),
                        "score": round(score, 3),
                        "rationale": d.get("rationale", "")}}
                    llm_hits += 1
                else:
                    out_by_gid[gid] = {"generated_id": gid, "match": None}
                    llm_misses += 1
    elif ambiguous and not use_llm:
        # Jaccard-only mode: take the prefilter's top.
        for gid in ambiguous:
            top_score, top_match = candidate_lookup[gid]["top"]
            out_by_gid[gid] = {"generated_id": gid, "match": {
                "id": top_match.get("id"), "title": top_match.get("title"),
                "file_path": top_match.get("file_path", ""),
                "framework": top_match.get("framework", ""),
                "score": round(top_score, 3),
                "rationale": "jaccard prefilter only"}}

    # Preserve input order.
    out_list = [out_by_gid.get(g.get("id"),
                               {"generated_id": g.get("id"), "match": None})
                for g in generated_cases]
    stats = {"fast_path": fast_path_hits, "llm_hits": llm_hits,
             "llm_misses": llm_misses, "total": total,
             "llm_batches": ((len(ambiguous) + batch_size - 1) // batch_size
                              if ambiguous else 0)}
    # Wrap in a subclass so the worker can introspect stats while still passing
    # the list around like a plain list.
    class _MatchList(list):
        pass
    wrapped = _MatchList(out_list)
    wrapped._match_stats = stats
    return wrapped


# ---------------------------------------------------------------- URL helpers
def build_blob_url(git_provider: str, repo_full_name: str, default_branch: str,
                   file_path: str, line: int | None = None) -> str:
    if not (repo_full_name and default_branch and file_path):
        return ""
    p = file_path.lstrip("/")
    if (git_provider or "").lower() == "gitlab":
        url = f"https://gitlab.com/{repo_full_name}/-/blob/{default_branch}/{p}"
        if line:
            url += f"#L{line}"
        return url
    url = f"https://github.com/{repo_full_name}/blob/{default_branch}/{p}"
    if line:
        url += f"#L{line}"
    return url


def build_commit_url(git_provider: str, repo_full_name: str, sha: str,
                     file_path: str | None = None) -> str:
    if not (repo_full_name and sha):
        return ""
    if (git_provider or "").lower() == "gitlab":
        base = f"https://gitlab.com/{repo_full_name}/-/commit/{sha}"
    else:
        base = f"https://github.com/{repo_full_name}/commit/{sha}"
    if file_path:
        # Anchor to the file diff section on GitHub commit pages.
        import hashlib as _h
        anchor = _h.sha256(file_path.encode()).hexdigest()[:32]
        base += f"#diff-{anchor}"
    return base
