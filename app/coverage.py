
import hashlib
import json
import os
import re

from core.logging_setup import get_logger

log = get_logger("coverage")

_LANG = {
    "python":     "Python",
    "javascript": "JavaScript (Node)",
    "typescript": "TypeScript",
    "java":       "Java",
    "go":         "Go",
}

_CODE_SYS = (
    "You are a senior software engineer. You write production-quality IMPLEMENTATION code that "
    "fulfils a feature requirement so that all of its acceptance test cases would pass. "
    "Respond with a single JSON object only."
)


def generate_feature_code(llm, language: str, feature_name: str,
                          requirement_text: str, cases) -> dict:
    """Generate implementation (feature) code that satisfies the requirement + test cases.

    Returns {"files":[{"path","content"}], "notes": "..."} or {"error": ...}.
    """
    lang = _LANG.get(language, "Python")
    accept = [{"title": c["title"], "type": c["type"],
               "criteria": [f"{s['action']} -> {s['expected']}" for s in c.get("steps", [])]}
              for c in cases]
    prompt = (
        f"Implement the feature \"{feature_name}\" in {lang}. Write the ACTUAL application/"
        f"implementation code (not tests) so the requirement is met and every acceptance test "
        f"case below would pass.\n\n"
        f"REQUIREMENT (truncated):\n\"\"\"\n{(requirement_text or '')[:5000]}\n\"\"\"\n\n"
        f"ACCEPTANCE TEST CASES the code must satisfy:\n{json.dumps(accept)[:5000]}\n\n"
        "Produce 1-4 idiomatic source files (handlers/services/models as appropriate). Keep them "
        "cohesive and self-consistent; add brief comments referencing which behavior each part covers.\n"
        "Return JSON: {\"files\":[{\"path\":\"<repo-relative path>\",\"content\":\"<full source>\"}],"
        "\"notes\":\"one line on what was built / assumptions\"}."
    )
    try:
        data = llm.chat_json(_CODE_SYS, prompt)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    files = []
    for f in (data.get("files") or [])[:5]:
        if isinstance(f, dict) and f.get("path") and f.get("content"):
            files.append({"path": str(f["path"]).lstrip("/")[:200], "content": str(f["content"])})
    if not files:
        return {"error": "model returned no files"}
    return {"files": files, "notes": str(data.get("notes", ""))[:300]}

# Heuristic: which files look like developer-authored tests/specs rather than the
# production code that actually implements a requirement. This gates BOTH what gets
# indexed for Mind Map (main.py) and which citations may serve as evidence
# (`_ground_verdict`), so a miss here directly produces false 'covered' verdicts.
#
# The directory branch accepts an optional hyphen/underscore-prefixed qualifier so
# `wardon-specs/`, `api_specs/` and `acceptance-tests/` are caught, and matches `specs`
# as well as `spec` — an earlier version matched only the bare singular `spec/`, which
# let whole spec trees through as if they were implementation.
TEST_FILE_RE = re.compile(
    r"(^|/)([\w.]*[-_])?(tests?|specs?|__tests__|__specs__|e2e|cypress)/|"
    r"(test_|_test|[-_]spec|\.test\.|\.spec\.|\.e2e\.)|"
    r"(Test|Tests|IT|Spec)\.(java|kt|cs|go|rb)$",
    re.IGNORECASE,
)


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path or ""))


# ---------------------------------------------------------------------------
# Files that cannot IMPLEMENT a requirement.
#
# This is deliberately a SEPARATE predicate from is_test_file() rather than a widening of
# it. is_test_file()'s current meaning is load-bearing elsewhere: PR coverage uses it to
# find developer-authored tests and automation coverage counts them, so relabelling type
# declarations and seed data as "tests" would silently corrupt the automation percentage.
# Two different questions, two predicates:
#     is_test_file(p)                -> "is this a test?"        (semantics unchanged)
#     is_non_implementation_file(p)  -> "could this implement anything at all?"
#
# The argument is correctness before cost. A `.d.ts` declaration compiles to nothing and a
# generated migration asserts no behaviour, so neither can ever be evidence that a
# requirement is implemented — yet either can be cited, and was. Budget is a side benefit:
# measured on a real 100-file review corpus, 13 files could not implement anything,
# `prisma/seed.ts` alone at 42,704 bytes, for roughly 6-7% of the code budget. That is a
# real saving but not the point; do not let it justify widening these rules.
#
# Conservative by construction: anything ambiguous stays IN. Dropping a file is invisible
# and unrecoverable (it can no longer be cited, so a real implementation reads as
# uncovered); keeping one merely costs excerpt budget. Every rule below must be a
# construct that CANNOT carry behaviour, not merely one that usually doesn't.
#
# The tool-config branch is an allowlist of NAMED build tools, not a `*.config.ts` glob.
# The glob was written first and measured second, and measurement killed it: it dropped
# `src/config/firebase.config.ts`, which throws when credentials are missing and exports
# the `messaging` client, and `src/config/queue.config.ts`, which holds the job retry count
# and backoff policy — both things a test case would legitimately be judged against. A
# file named after a build tool cannot carry application behaviour; a file merely named
# `*.config.ts` very much can. Add tools here as needed; never widen it back to a glob.
_TOOL_CONFIG = (
    "vite|vitest|jest|webpack|rollup|babel|tailwind|postcss|next|nuxt|svelte|astro|"
    "eslint|prettier|karma|cypress|playwright|tsup|esbuild|metro|nodemon|commitlint|"
    "lint-staged|drizzle|prisma|knexfile|gatsby|remix|craco|jasmine|stylelint|jsdoc"
)
NON_IMPL_PATH_RE = re.compile(
    r"\.d\.ts$|"                                          # ambient type declarations
    r"\.pyi$|"                                            # python type stubs
    r"(^|/)(" + _TOOL_CONFIG + r")\.config\.[cm]?[jt]sx?$|"   # build-tool config only
    r"(^|/)(seed|seeds)\.(ts|js|mjs|cjs|py|rb)$|"         # DB seed scripts
    r"(^|/)(seeds|fixtures|migrations|__mocks__)/|"        # seed/fixture/migration trees
    r"\.sql$|"                                            # raw migrations & dumps
    r"\.(snap|lock)$",                                    # snapshots, lockfiles
    re.IGNORECASE,
)

# Content rule, used only when the file's text is available.
#
# It exists because the path rule cannot safely catch `src/types/activity.types.ts`: a
# blanket `types/` exclusion is exactly the kind of guess that drops real code, since
# plenty of projects keep runtime helpers there. Asking the file itself is both safer and
# stricter — a file consisting only of `interface`/`type` declarations compiles to zero
# JavaScript, so whatever it says, it implements nothing.
#
# Order matters: a VALUE construct anywhere wins and the file is kept. `export const
# MAX_DURATION_MINUTES = 480` and `export const env = {...}` are runtime values a
# rationale may legitimately cite, so `constants/` and `config/` survive this rule — which
# is why there is no path rule for those directories either.
_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/|^[ \t]*#[^\n]*",
                         re.DOTALL | re.MULTILINE)
_VALUE_CONSTRUCT_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b|"
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\b|"
    r"^\s*(?:export\s+)?(?:const|let|var)\s+|"
    r"^\s*(?:export\s+)?enum\s+|"
    r"^\s*(?:async\s+)?def\s+|"
    r"=>|\breturn\b|\bawait\b|\bthrow\b|\bnew\s+[A-Z]",
    re.MULTILINE,
)
_TYPE_ONLY_DECL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type)\s+\w+",
    re.MULTILINE,
)


def _is_declaration_only(text: str) -> bool:
    """True only when the file's text is provably type declarations and nothing else.

    Three-way by construction, collapsed to a conservative bool: a value construct means
    'keeps behaviour' (False); type declarations with no value construct means 'compiles to
    nothing' (True); anything else — an empty file, a bare re-export barrel, a language
    this rule does not model — is unknown and therefore kept (False).
    """
    body = _COMMENT_RE.sub("", text or "")
    if _VALUE_CONSTRUCT_RE.search(body):
        return False
    return bool(_TYPE_ONLY_DECL_RE.search(body))


def is_non_implementation_file(path: str, text: str | None = None) -> bool:
    """Could this file implement a requirement? Answers the negative: True = it cannot.

    Superset of is_test_file(). Pass `text` when it is on hand to enable the content rule;
    with path alone the answer is still sound, just less complete.
    """
    p = path or ""
    if is_test_file(p) or NON_IMPL_PATH_RE.search(p):
        return True
    return _is_declaration_only(text) if text else False


_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_key(text: str):
    """Pull the first ticket/epic-style key like ABC-123 from text."""
    m = _KEY_RE.search(text or "")
    return m.group(1) if m else None


def extract_keys(*texts) -> list:
    """All unique ABC-123 keys across the given texts, first-seen order preserved."""
    seen, out = set(), []
    for t in texts:
        for m in _KEY_RE.findall(t or ""):
            k = m.upper()
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def pr_text(pr: dict, files: list) -> str:
    paths = "\n".join(f"- {f['filename']} ({f['status']})" for f in files[:40])
    return (f"PR #{pr.get('number')}: {pr.get('title','')}\n"
            f"branch: {pr.get('head_ref','')}\n\n"
            f"{(pr.get('body') or '')[:1500]}\n\nChanged files:\n{paths}")


def map_pr_to_feature(store, jira, pr, project_id):
    """Map a PR to a feature. Returns (feature_id|None, confidence, method).

    Resolution order:
      1. Jira Epic/ticket keys in the PR TITLE or BODY (feature.key == epic key):
         a direct Epic -> map ('epic'); else resolve a ticket's parent Epic via
         Jira -> map ('ticket->epic').
      2. Manual PR match tag (Jira-independent): a feature's `match_key` present as
         a whole word (case-insensitive) in the PR title/body -> map ('tag').
         e.g. match_key "FINES" matches "FINES", "[FINES]" or "FINES:" but NOT
         "REFINES"/"FINESSE" (guards against accidental substring matches).
    Keyword tiers ONLY: if nothing resolves, the PR is left unmapped (a miss is preferred
    over a wrong guess). This is the coverage-grade mapping and it deliberately never
    consults embeddings; the semantic fallback lives in resolve_pr_mapping() below, which
    calls this first and only goes further when it finds nothing."""
    keys = extract_keys(pr.get("title", ""), pr.get("body", ""))
    for key in keys:
        fid = store.feature_by_epic(project_id, key)
        if fid:
            return fid, 1.0, f"epic:{key}"
    if keys and jira is not None and getattr(jira, "ok", lambda: False)():
        for key in keys:
            epic = jira.parent_epic(key)
            if epic and epic != key:
                fid = store.feature_by_epic(project_id, epic)
                if fid:
                    return fid, 1.0, f"ticket:{key}->epic:{epic}"
    haystack = f"{pr.get('title', '')} {pr.get('body', '')}"
    try:
        for fid, mk in store.features_with_match_key(project_id):
            tag = str(mk or "").strip()
            if not tag:
                continue
            # Match the tag as a whole token (case-insensitive): surrounding
            # brackets/colons/spaces all count as boundaries, so "FINES",
            # "[FINES]" and "FINES:" match, but "REFINES"/"FINESSE" do not.
            if re.search(
                rf"(?<![A-Za-z0-9]){re.escape(tag)}(?![A-Za-z0-9])",
                haystack,
                re.IGNORECASE,
            ):
                return fid, 1.0, f"tag:{tag.upper()}"
    except Exception:  # noqa: BLE001 -- mapping must never crash PR ingest
        pass
    return None, 0.0, "unmapped"


# --------------------------------------------------------------------------- semantic PR mapping
#
# Issue #54: most PRs carry neither an epic key nor a match tag, so the keyword tiers above
# leave them unmapped and nothing downstream (coverage, and later PR review) can use a
# requirement for them. The fallback below ranks the project's features by embedding
# similarity to the PR and reports the best one WITH its score and margin.
#
# It is a SUGGESTION, never a fact, and it never moves coverage numbers on its own: unless
# PR_SEMANTIC_COUNTS_TOWARD_COVERAGE is switched on, the PR stays unmapped for coverage
# accounting and the suggestion is stored beside it. Keyword tiers always win.


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# Master switch for computing a semantic suggestion at all (default on).
PR_SEMANTIC_MAPPING = _env_flag("PR_SEMANTIC_MAPPING", True)
# Minimum similarity for the best feature, on mongot's (1 + cosine) / 2 scale. The default was
# chosen from a small calibration with nomic-embed-text (clear PRs scored 0.86-0.94, vague or
# off-topic ones at most 0.83); other embedding models score on different ranges, so retune it
# if the embedding model changes.
PR_SEMANTIC_FLOOR = _env_float("PR_SEMANTIC_FLOOR", 0.85)
# Minimum lead of the best feature over the runner-up. A PR that fits two features about
# equally well is ambiguous and stays unmapped.
PR_SEMANTIC_MARGIN = _env_float("PR_SEMANTIC_MARGIN", 0.05)
# Off by default: a semantic match is shown as a suggestion but does NOT feed coverage.
PR_SEMANTIC_COUNTS_TOWARD_COVERAGE = _env_flag("PR_SEMANTIC_COUNTS_TOWARD_COVERAGE", False)


def pr_mapping_text(pr: dict) -> str:
    """The text a PR is embedded as for mapping: title, body and the changed file paths."""
    paths = [str(p) for p in (pr.get("changed_files") or [])][:40]
    parts = [str(pr.get("title") or "").strip(), str(pr.get("body") or "").strip()[:1500]]
    if paths:
        parts.append("Changed files:\n" + "\n".join(f"- {p}" for p in paths))
    return "\n\n".join(p for p in parts if p)


def semantic_pr_match(store, embedder, pr: dict, project_id, floor=None, margin=None):
    """Best feature for a PR by embedding similarity, or None.

    Returns {"method": "semantic", "feature_id", "confidence", "margin", "runner_up"}.
    `confidence` is the retrieval similarity of the best feature, an honest relevance score
    and not a calibrated probability. None when there is no PR text, no features, the best
    score is under the floor, or the lead over the runner-up is under the margin. Never
    raises: a broken embedder or index must not break PR ingest.
    """
    floor = PR_SEMANTIC_FLOOR if floor is None else floor
    margin = PR_SEMANTIC_MARGIN if margin is None else margin
    text = pr_mapping_text(pr)
    if embedder is None or not project_id or not text:
        return None
    try:
        ranked = store.semantic_feature_scores(
            embedder.embed(text[:3000], task="query"), project_id, limit=5) or []
    except Exception as exc:  # noqa: BLE001 -- mapping must never crash PR ingest
        log.warning("[pr-map] semantic lookup failed for %s#%s: %s",
                    pr.get("repo_full_name"), pr.get("number"), exc)
        return None
    if not ranked:
        return None
    best = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    lead = round(best["score"] - runner["score"], 4) if runner else None
    log.info("[pr-map] %s#%s semantic best=%s score=%.3f runner_up=%s margin=%s (floor=%.2f, min_margin=%.2f)",
             pr.get("repo_full_name"), pr.get("number"), best.get("feature_id"), best["score"],
             runner.get("feature_id") if runner else None, lead, floor, margin)
    if best["score"] < floor or (lead is not None and lead < margin):
        return None
    return {"method": "semantic", "feature_id": best["feature_id"],
            "confidence": round(best["score"], 4), "margin": lead,
            "runner_up": ({"feature_id": runner["feature_id"], "confidence": round(runner["score"], 4)}
                          if runner else None)}


def resolve_pr_mapping(store, jira, pr: dict, project_id, embedder=None,
                       counts_toward_coverage=None, floor=None, margin=None) -> dict:
    """Map a PR to a feature: keyword tiers first, then a semantic suggestion.

    Returns {"feature_id", "confidence", "method", "suggestion"}.
      * A keyword tier (epic / ticket->epic / tag) that resolves wins outright and is exactly
        what map_pr_to_feature() returns; the embedder is not touched.
      * Otherwise a semantic match is returned as `suggestion`. By default the PR stays
        unmapped for coverage (feature_id None, method "unmapped"); only with
        counts_toward_coverage (PR_SEMANTIC_COUNTS_TOWARD_COVERAGE) does it become the
        mapping, with method "semantic" and the similarity as its confidence.
    """
    fid, confidence, method = map_pr_to_feature(store, jira, pr, project_id)
    where = f"{pr.get('repo_full_name')}#{pr.get('number')}"
    if fid:
        log.info("[pr-map] %s method=%s confidence=%.2f feature=%s", where, method, confidence, fid)
        return {"feature_id": fid, "confidence": confidence, "method": method, "suggestion": None}
    suggestion = semantic_pr_match(store, embedder, pr, project_id, floor, margin) \
        if PR_SEMANTIC_MAPPING else None
    counts = PR_SEMANTIC_COUNTS_TOWARD_COVERAGE if counts_toward_coverage is None else counts_toward_coverage
    if suggestion and counts:
        log.info("[pr-map] %s method=semantic confidence=%.3f feature=%s (counts toward coverage)",
                 where, suggestion["confidence"], suggestion["feature_id"])
        return {"feature_id": suggestion["feature_id"], "confidence": suggestion["confidence"],
                "method": "semantic", "suggestion": suggestion}
    log.info("[pr-map] %s method=unmapped%s", where,
             f" (semantic suggestion {suggestion['feature_id']} at {suggestion['confidence']:.3f}, "
             "not counted toward coverage)" if suggestion else "")
    return {"feature_id": None, "confidence": 0.0, "method": "unmapped", "suggestion": suggestion}


# --------------------------------------------------------------------------- citation grounding
#
# An LLM verdict that cites a file is only worth something if that file is one we
# ACTUALLY showed it. Without this check a plausible-but-invented path ("app/auth/
# session.py") sails through as evidence and a hallucinated 'covered' looks identical
# to a real one. Everything below is deterministic — no model calls — and runs over
# the same excerpt list that was sent in the prompt.

# Verdicts at or below this confidence are flagged `needs_review` instead of trusted.
# Tunable without a code change; see also docs in README (Configuration).
REVIEW_CONFIDENCE_THRESHOLD = float(os.getenv("COVERAGE_REVIEW_THRESHOLD", "0.7"))
# Ceiling on a 'covered' verdict whose rationale asserts nothing checkable. Such a claim
# cannot be contradicted, which is precisely why it must not be trusted in silence —
# see the third branch in `_ground_verdict`.
UNVERIFIABLE_CONFIDENCE_CAP = float(os.getenv("COVERAGE_UNVERIFIABLE_CAP", "0.6"))

# Status ranking, used to pick the most conservative verdict across samples.
_STATUS_RANK = {"uncovered": 0, "partial": 1, "covered": 2}
_RANK_STATUS = {v: k for k, v in _STATUS_RANK.items()}

# Baseline confidence per status when the model doesn't report one of its own.
_BASE_CONFIDENCE = {"covered": 0.85, "partial": 0.60, "uncovered": 0.55}

# A "candidate symbol" is a token that looks like code rather than prose: quoted or
# backticked, snake_case, camelCase/PascalCase, called like `foo(`, or dotted `a.b`.
# Plain English words deliberately do NOT match, so a paraphrased rationale is never
# penalised for having nothing to check.
_QUOTED_RE = re.compile(r"[`'\"]([A-Za-z_][\w./-]{2,80})[`'\"]")
_CALL_RE = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")
_SNAKE_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")
_CAMEL_RE = re.compile(r"\b([a-z]+[A-Z]\w*|[A-Z][a-z]+[A-Z]\w*)\b")
# A dotted token is only a symbol (`obj.method`) if it is NOT the stem of a filename —
# without the lookahead, "auth.controller.ts" yields the pseudo-symbol "auth.controller".
_DOTTED_RE = re.compile(
    r"\b([A-Za-z_]\w*\.[A-Za-z_]\w{2,})\b"
    r"(?!\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|java|rb|cs|kt|kts|php|rs|swift|scala)\b)",
    re.IGNORECASE)
# Prompt scaffolding and file references, stripped before symbol extraction so a cited
# path is never mistaken for a claim about an identifier (see `strip_citations`).
_FILE_SCAFFOLD_RE = re.compile(r"/{2,}\s*FILE\b|\bFILE\b(?=\s*[`'\"]?\s*:?)")
_EXTISH_RE = re.compile(
    r"[\w.-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|java|rb|cs|kt|kts|php|rs|swift|scala|c|h|cpp)\b",
    re.IGNORECASE)
_PATHISH_RE = re.compile(r"[\w.@~-]*/[\w.@/~-]+")
# Trailing line/anchor references a model may append to a path: ":42", "#L42".
_LINEREF_RE = re.compile(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)\s*$")


def _clean_path(raw) -> str:
    """Normalize a model-supplied path: strip quotes/backticks, line refs, slashes."""
    s = str(raw or "").strip()
    s = s.strip("`'\" \t")
    s = _LINEREF_RE.sub("", s).strip()
    return s.strip().lstrip("./").lstrip("/")


def citation_index(code_excerpts) -> dict:
    """Index the excerpts actually shown to the model, for verifying its citations.

    `canon` maps the canonical "repo:path" to that file's concatenated excerpt text
    (a file can contribute more than one chunk). `by_path` / `by_base` are lookup
    aids for citations that drop the repo prefix or give only a basename.
    """
    canon: dict = {}
    by_path: dict = {}
    by_base: dict = {}
    for c in code_excerpts or []:
        repo = str((c or {}).get("repo") or "").strip()
        path = _clean_path((c or {}).get("path"))
        if not path:
            continue
        key = f"{repo}:{path}" if repo else path
        text = str((c or {}).get("text") or "")
        canon[key] = (canon[key] + "\n" + text) if key in canon else text
        by_path.setdefault(path.lower(), [])
        if key not in by_path[path.lower()]:
            by_path[path.lower()].append(key)
        base = path.rsplit("/", 1)[-1].lower()
        by_base.setdefault(base, [])
        if key not in by_base[base]:
            by_base[base].append(key)
    return {"canon": canon, "by_path": by_path, "by_base": by_base}


def resolve_citation(raw, idx: dict):
    """Resolve one cited path to a real excerpt. Returns (canonical_key, strength).

    Strength is 'exact' | 'path' | 'suffix' | 'basename' for a hit, or None when the
    citation matches nothing we showed the model — i.e. it was invented.
    """
    s = _clean_path(raw)
    if not s or not idx.get("canon"):
        return None, None
    low = s.lower()
    for key in idx["canon"]:
        if key.lower() == low:
            return key, "exact"
    # Drop a leading "repo:" segment and retry as a plain path.
    bare = low.split(":", 1)[1].strip("/ ") if ":" in low else low
    hits = idx["by_path"].get(bare)
    if hits:
        return hits[0], "path"
    # The model may shorten or lengthen a path; accept a suffix match in either
    # direction, but ONLY when it is unambiguous. Picking the first of several matches
    # would launder a wrong citation into evidence, which is the whole failure mode
    # this function exists to prevent.
    if len(bare) >= 6:
        matches = []
        for path, keys in idx["by_path"].items():
            if path.endswith("/" + bare) or bare.endswith("/" + path):
                matches.extend(keys)
        matches = list(dict.fromkeys(matches))
        if len(matches) == 1:
            return matches[0], "suffix"
        if matches:
            return None, None       # ambiguous -> not usable as evidence
    # Basename only — accept when exactly one shown file has that name, since a bare
    # "login.py" is otherwise ambiguous and would launder a wrong citation.
    keys = idx["by_base"].get(bare.rsplit("/", 1)[-1])
    if keys and len(keys) == 1:
        return keys[0], "basename"
    return None, None


def strip_citations(text: str, raw_files=None) -> str:
    """Remove file references from a rationale, leaving only substantive claims.

    A path is a CITATION, not a claim about an identifier, and conflating the two broke
    the symbol check in both directions on real data. Reviewers routinely echo the
    prompt's own `// FILE repo:path` header into their rationale; the old code turned that
    path into a pseudo-identifier ("auth.controller"), compared it against the file's
    contents, inevitably failed, and downgraded correct verdicts. Worse, the same
    pseudo-identifier could be the token that PASSED the check, whitewashing a rationale
    whose only real claim was a function that does not exist.
    """
    t = str(text or "")
    for f in (raw_files or []):
        t = t.replace(str(f), " ")
    t = _FILE_SCAFFOLD_RE.sub(" ", t)
    t = _EXTISH_RE.sub(" ", t)
    t = _PATHISH_RE.sub(" ", t)
    return t


def candidate_symbols(text: str) -> set:
    """Code-like identifiers named in a rationale. Empty set => nothing to verify.

    Path- and filename-shaped tokens are deliberately NOT symbols — see `strip_citations`.
    """
    t = str(text or "")
    out = set()
    for rx in (_QUOTED_RE, _CALL_RE, _SNAKE_RE, _CAMEL_RE, _DOTTED_RE):
        for m in rx.findall(t):
            tok = str(m).strip("`'\" ")
            # A path or filename is a citation, already verified separately. Drop it
            # rather than mining a fake identifier out of its last segment.
            if "/" in tok or _EXTISH_RE.search(tok):
                continue
            tok = tok.strip(".")
            if len(tok) >= 3:
                out.add(tok)
    return out


def _symbols_supported(symbols: set, texts: list):
    """True/False if any named symbol appears in the cited code; None if none named.

    None is the neutral case: a rationale can legitimately paraphrase ("the handler
    validates the token") without naming anything checkable, and must not be punished
    for that. Only a rationale that DOES name identifiers, none of which exist in the
    code it cites, is treated as unsupported.
    """
    if not symbols:
        return None
    if not texts:
        return None
    blob = "\n".join(texts)
    low = blob.lower()
    for sym in symbols:
        if sym in blob or sym.lower() in low:
            return True
    return False


def _ground_verdict(status: str, rationale: str, raw_files, idx: dict,
                    model_confidence=None, floor: str = "uncovered") -> dict:
    """Verify one verdict's citations and score how much to trust it.

    Returns the corrected status plus the evidence trail: which citations resolved to
    real files, which were invented, whether the rationale's identifiers actually
    appear in the cited code, a 0-1 confidence, and a needs_review flag.

    `floor` is the lowest status a downgrade may reach. Mind Map allows 'uncovered'
    (an unsupported claim there really does mean "we can't show this is covered"), but
    the PR verifier floors at 'partial' so a weakly-evidenced claim is still reported
    to a human rather than vanishing from the result.
    """
    verified, rejected, ineligible, strengths = [], [], [], []
    for f in (raw_files or []):
        key, strength = resolve_citation(f, idx)
        if not key:
            rejected.append(str(f)[:160])
            continue
        # ELIGIBILITY, separate from provenance. A citation can be perfectly genuine —
        # the file really was shown, the named symbol really is in it — and still be
        # worthless as evidence, because a test/spec file asserting a behaviour does not
        # show that production code implements it. Verifying only provenance certified
        # exactly this false positive in a real run, so the check lives here too rather
        # than relying on the indexer having filtered the corpus.
        #
        # The same reasoning covers type declarations, tool config, seed data and
        # migrations, so this uses the wider predicate: an `interface CreateEventRequest`
        # in a .types.ts file names the shape of a request beautifully and proves nothing
        # about whether any code handles one. The text is passed so the content rule
        # applies — the indexer's path-only pass cannot catch `activity.types.ts`, and
        # this is the layer that has the file body to hand.
        path = key.split(":", 1)[1] if ":" in key else key
        if is_non_implementation_file(path, idx.get("canon", {}).get(key)):
            if key not in ineligible:
                ineligible.append(key)
            continue
        if key not in verified:
            verified.append(key)
        strengths.append(strength)

    texts = [idx["canon"][k] for k in verified if k in idx.get("canon", {})]
    # Check only what the rationale genuinely CLAIMS about the code — its file references
    # are citations, already verified above, and must not be re-checked as identifiers.
    symbols = candidate_symbols(strip_citations(rationale, raw_files))
    sym_ok = _symbols_supported(symbols, texts)

    original = status if status in _STATUS_RANK else "uncovered"
    final = original
    unverifiable = False
    try:
        conf = float(model_confidence) if model_confidence is not None else _BASE_CONFIDENCE[original]
    except (TypeError, ValueError):
        conf = _BASE_CONFIDENCE[original]
    notes = []

    floor_rank = _STATUS_RANK.get(floor, 0)

    # No usable file behind a positive claim → the claim is unsupported.
    if original in ("covered", "partial") and not verified:
        if ineligible:
            # The model's ENTIRE evidence base was test/spec code. Per the reviewer's own
            # brief ("if the only relevant code you see is test code, the case is
            # uncovered") this is not a partial result — there is no production evidence
            # at all, so drop straight to the floor.
            final = _RANK_STATUS[floor_rank]
            conf = min(conf, 0.2)
            notes.append("cited only files that cannot implement behaviour (test/spec "
                         "code, type declarations, config or generated data)")
        else:
            # Downgrade one rung rather than discarding it, and say why.
            final = _RANK_STATUS[max(floor_rank, _STATUS_RANK[original] - 1)]
            conf = min(conf, 0.35)
            notes.append("no cited file matched the reviewed code"
                         if raw_files else "no file cited")
    # Cited a real file, but the identifiers the rationale leans on aren't in it.
    elif sym_ok is False:
        if original == "covered":
            final = _RANK_STATUS[max(floor_rank, _STATUS_RANK["partial"])]
        conf -= 0.25
        notes.append("rationale references identifiers absent from the cited code")
    # Cited a real file but named NOTHING checkable — no function, route or identifier,
    # e.g. "the refresh token logic is implemented in <file>". There is no claim here to
    # confirm or contradict. Treating that as neutral (which it was) let a verdict citing
    # a `refreshToken` function that exists nowhere in the repository pass at full
    # confidence, unflagged. So: never downgrade for it — punishing legitimate paraphrase
    # was the original bug — but never grant silent trust either. Cap and flag.
    elif sym_ok is None and original in ("covered", "partial") and verified:
        unverifiable = True
        notes.append("rationale names no identifier that can be checked against the "
                     "cited code — claim is unverifiable, not confirmed")
        if original == "covered":
            conf = min(conf, UNVERIFIABLE_CONFIDENCE_CAP)

    if rejected:
        conf -= 0.15
        notes.append(f"{len(rejected)} cited path(s) not among the reviewed files")
    if ineligible and verified:
        conf -= 0.10
        notes.append(f"{len(ineligible)} cited path(s) ignored as non-implementation code")
    if verified and all(s == "basename" for s in strengths):
        conf -= 0.10
        notes.append("citation matched only by filename")

    conf = max(0.0, min(1.0, round(conf, 3)))

    # `needs_review` must mean "a human can act on this". A plain 'uncovered' verdict
    # that cited nothing is self-consistent — the model looked and found no evidence,
    # which IS the answer, so there is nothing to review. Flagging those buried the
    # signal: in a real 133-case run 95 cases were flagged, all of them uncovered with a
    # model-reported confidence of 0.0, while the handful of genuinely wrong 'covered'
    # verdicts came through unflagged. Reserve the flag for claims with something to check.
    nothing_claimed = (final == "uncovered" and not verified and not rejected
                       and not ineligible)
    # `unverifiable` is listed explicitly rather than relied on via the confidence cap, so
    # lowering COVERAGE_REVIEW_THRESHOLD can never quietly un-flag an unsupportable claim.
    needs_review = False if nothing_claimed else bool(
        conf < REVIEW_CONFIDENCE_THRESHOLD or rejected or ineligible or unverifiable
        or final != original)

    out = {
        "status": final,
        "confidence": conf,
        "needs_review": needs_review,
        "files": verified,
        "files_rejected": rejected,
        "files_ineligible": ineligible,
        "grounding": {
            "citations_verified": len(verified),
            "citations_rejected": len(rejected),
            "citations_ineligible": len(ineligible),
            "symbols_checked": len(symbols),
            "symbols_supported": sym_ok,
            # True when the rationale made a positive claim with nothing checkable in it.
            "unverifiable": unverifiable,
            "notes": notes,
        },
    }
    if final != original:
        out["downgraded_from"] = original
    return out


def window_excerpts(code_excerpts, budget: int, per_chunk: int, max_chunks: int) -> list:
    """Partition EVERY excerpt into context-sized windows. Nothing is discarded.

    Relevance order is preserved, so the most promising code is examined first — but
    unlike the old `[:20]` slice, the tail of the corpus is examined too, in a later
    window, rather than being silently dropped and then reported as absent.
    """
    windows: list = []
    cur: list = []
    used = 0
    for c in code_excerpts or []:
        text = str((c or {}).get("text") or "")
        cost = (min(len(text), per_chunk) + len(str((c or {}).get("repo") or ""))
                + len(str((c or {}).get("path") or "")) + 14)
        if cur and (used + cost > budget or len(cur) >= max_chunks):
            windows.append(cur)
            cur, used = [], 0
        cur.append(c)
        used += cost
    if cur:
        windows.append(cur)
    return windows or [[]]


def _merge_windows(per_window: list) -> dict:
    """Fuse one case's verdicts from DIFFERENT windows: the best evidence anywhere wins.

    This is deliberately the OPPOSITE of `_reconcile_samples`. Repeated samples look at
    the SAME code, so disagreement means unreliability and the LOWEST status is correct.
    Different windows look at DIFFERENT code, so "not found here" says nothing about
    elsewhere — only the HIGHEST status carries information, and a case is 'uncovered'
    only once every window has failed to find it. Getting this backwards would make an
    exhaustive sweep score worse than a single sample.
    """
    verdicts = [v for v in per_window if v]
    if not verdicts:
        return {}
    best = max(verdicts, key=lambda v: (_STATUS_RANK.get(v.get("status", "uncovered"), 0),
                                        float(v.get("confidence") or 0.0)))
    out = dict(best)
    # Evidence is cumulative across windows; noise is reported from the winning window
    # only, so a path that simply wasn't in THIS window isn't recorded as a fabrication.
    out["files"] = list(dict.fromkeys([f for v in verdicts for f in (v.get("files") or [])]))
    if len(verdicts) > 1:
        out["windows"] = {"searched": len(verdicts),
                          "statuses": [v.get("status") for v in verdicts]}
    return out


def _reconcile_samples(verdicts: list) -> dict:
    """Fuse repeated judgements of the same case into one conservative verdict.

    'covered' only survives if every sample said so — any disagreement takes the
    lowest status and flags the case for a human. This is a cheap way to cut
    hallucination variance without executing anything.
    """
    verdicts = [v for v in verdicts if v]
    if not verdicts:
        return {}
    if len(verdicts) == 1:
        v = dict(verdicts[0])
        v["agreement"] = {"samples": 1, "unanimous": True,
                          "statuses": [v.get("status")]}
        return v
    statuses = [v.get("status", "uncovered") for v in verdicts]
    ranks = [_STATUS_RANK.get(s, 0) for s in statuses]
    unanimous = len(set(statuses)) == 1
    winner = min(verdicts, key=lambda v: _STATUS_RANK.get(v.get("status", "uncovered"), 0))
    out = dict(winner)
    out["status"] = _RANK_STATUS[min(ranks)]
    out["confidence"] = max(0.0, min(1.0, round(
        sum(float(v.get("confidence") or 0.0) for v in verdicts) / len(verdicts)
        - (0.0 if unanimous else 0.15), 3)))
    out["files"] = list(dict.fromkeys([f for v in verdicts for f in (v.get("files") or [])]))
    out["files_rejected"] = list(dict.fromkeys(
        [f for v in verdicts for f in (v.get("files_rejected") or [])]))
    out["files_ineligible"] = list(dict.fromkeys(
        [f for v in verdicts for f in (v.get("files_ineligible") or [])]))
    # Same rule as the single-sample path: an unclaimed 'uncovered' has nothing to review.
    nothing_claimed = (out["status"] == "uncovered" and not out["files"]
                       and not out["files_rejected"] and not out["files_ineligible"])
    out["needs_review"] = False if nothing_claimed else bool(
        not unanimous or out["confidence"] < REVIEW_CONFIDENCE_THRESHOLD
        or any(v.get("needs_review") for v in verdicts))
    out["agreement"] = {"samples": len(verdicts), "unanimous": unanimous, "statuses": statuses}
    if not unanimous:
        notes = list((out.get("grounding") or {}).get("notes") or [])
        notes.append(f"samples disagreed ({', '.join(statuses)}); took the most conservative")
        out.setdefault("grounding", {})["notes"] = notes
    return out


_CODEREV_SYS = (
    "You are an external code reviewer auditing IMPLEMENTATION coverage. Given a feature's "
    "requirement, its test cases, and excerpts of the ACTUAL production/implementation code (from "
    "one or more repositories), judge for each test case whether the production code actually "
    "implements the behaviour the test case describes. Reason about what the code DOES, like a "
    "reviewer reading a PR.\n"
    "CRITICAL: you are NOT checking whether an automated test exists. The presence of a test file, "
    "spec, or assertion does NOT make a case 'covered' — only the production code that fulfils the "
    "requirement does. If the only relevant code you see is test code, the case is 'uncovered'. "
    "Automated-test coverage is measured separately. Respond with a single JSON object only."
)


# --------------------------------------------------------------------------- excerpt budget
#
# The old fixed caps (max_per=900, max_total=16000) were the single biggest accuracy
# limiter in Mind Map, for two compounding reasons.
#
# 1. 900 characters gutted the whole point of tree-sitter chunking. Chunks are WHOLE
#    function bodies, but a 3,305-char `sendOtp` controller was cut to 27% — the model
#    saw the signature and the first few lines, never the validation or the response
#    paths. It then reported the behaviour "not present in the provided code excerpts",
#    which was true of what it was shown and wrong about the code. Verified false
#    negatives on real endpoints that demonstrably exist.
# 2. 16000 chars of code put the Ollama prompt ~2,000 tokens OVER its 8k context once
#    the 4,000-token output reservation is counted, so the prompt was being silently
#    truncated on top of that. Raising the per-chunk cap without fixing the total would
#    have made accuracy worse, not better.
#
# So the budget is now derived from the context the model actually has, truncation is
# explicitly MARKED (the reviewer is told what it didn't see, rather than silently
# shown less), and the output reservation is sized to what the reply really needs.

# Per-chunk allowance. 4000 admits a typical complete controller/route body whole.
EXCERPT_PER_CHARS = int(os.getenv("MINDMAP_EXCERPT_PER_CHARS", "4000"))
# Chunks per WINDOW (not per review). Nothing is discarded any more: the corpus is swept
# in as many windows as it takes. This used to be a bare `code_excerpts[:20]`, which threw
# the rest of the codebase away — so a verdict about a 20-chunk sample was reported as a
# verdict about the repository.
EXCERPT_MAX_CHUNKS = int(os.getenv("MINDMAP_EXCERPT_MAX_CHUNKS", "40"))
# Safety valve only. 0 = unlimited (the default): sweep every window until the whole
# corpus has been read, however long that takes. Set a number to bound cost.
MAX_WINDOWS = int(os.getenv("MINDMAP_MAX_WINDOWS", "0"))

# Fingerprint of the rules that decide what is indexed as production code. It is stored
# alongside a repo's code index so that CHANGING those rules invalidates the index
# automatically — without it, a cached index keeps serving chunks filtered by whatever
# rules were in force when it was built, and the operator has to know to force a rebuild.
#
# MUST be stable across PROCESSES, not just within one. This used builtin `hash()`, which
# CPython salts per interpreter (PEP 456) unless PYTHONHASHSEED is pinned — it isn't
# anywhere in this repo. The fingerprint therefore changed on every restart, so the stored
# value never matched, `rules_ok` was always False, and every Mind Map run re-fetched the
# tarball and re-embedded every chunk. That silently destroyed the incremental-reuse
# optimisation this check was bolted onto. sha256 of the pattern is content-addressed and
# identical in every process. Verify with a SUBPROCESS test: an in-process comparison
# passes trivially even when this is broken.
#
# It must cover EVERY rule that decides what gets indexed, not just the test filter. When
# the non-implementation rules were added, hashing only TEST_FILE_RE would have meant
# changing them left every cached index valid — still serving chunks filtered by the old
# rules, with no way for an operator to know. That is the same bug class as the salted
# `hash()` above, reached from the opposite direction, so the input is assembled from the
# patterns themselves: add a rule and the fingerprint moves without anyone remembering to
# bump a version number.
_INDEX_RULE_PATTERNS = (
    TEST_FILE_RE.pattern,
    NON_IMPL_PATH_RE.pattern,
    _VALUE_CONSTRUCT_RE.pattern,
    _TYPE_ONLY_DECL_RE.pattern,
    _COMMENT_RE.pattern,
)
INDEX_RULES_FINGERPRINT = "indexrules:" + hashlib.sha256(
    "\n".join(_INDEX_RULE_PATTERNS).encode("utf-8")).hexdigest()[:16]
# Output tokens reserved for the reply. ~10 verdicts of JSON needs well under 1k; the
# old 4000 crowded out the code it was supposed to be judging.
REVIEW_MAX_TOKENS = int(os.getenv("MINDMAP_REVIEW_MAX_TOKENS", "2000"))
# Everything in the prompt that ISN'T code (system + requirement + cases + instructions).
_NON_CODE_PROMPT_CHARS = 9000
_CHARS_PER_TOKEN = 4


def excerpt_total_chars(llm=None) -> int:
    """How many characters of code the prompt can afford for this provider.

    Ollama is clamped to a hard context in llm.py, so the whole prompt plus the reserved
    reply must fit inside it — the budget is derived from that same number so raising
    OLLAMA_MAX_NUM_CTX widens the code window automatically. Hosted providers have
    100k+ contexts and are limited only by cost/latency.
    """
    explicit = os.getenv("MINDMAP_EXCERPT_TOTAL_CHARS")
    if explicit:
        return max(2000, int(explicit))
    provider = str(getattr(llm, "provider", "") or "ollama").lower()
    if provider == "ollama":
        ctx_tokens = int(os.getenv("OLLAMA_MAX_NUM_CTX", "8192"))
        budget = ctx_tokens * _CHARS_PER_TOKEN - _NON_CODE_PROMPT_CHARS \
            - REVIEW_MAX_TOKENS * _CHARS_PER_TOKEN
        return max(4000, budget)
    return int(os.getenv("MINDMAP_EXCERPT_TOTAL_CHARS_HOSTED", "60000"))


def _trunc_marker(hidden: int) -> str:
    return f"\n// ...TRUNCATED — {hidden} more characters of this file were NOT shown"


def _code_excerpt_block(code_excerpts, max_total=None, max_per=None) -> str:
    max_per = EXCERPT_PER_CHARS if max_per is None else max_per
    max_total = excerpt_total_chars() if max_total is None else max_total
    parts: list = []
    used = 0
    for c in code_excerpts[:EXCERPT_MAX_CHUNKS]:
        text = str((c or {}).get("text", "") or "")
        header = f"// FILE {c.get('repo','')}:{c.get('path','')}"
        sep = 2 if parts else 0
        # Room left for this chunk's body once the header and separator are paid for.
        room = max_total - used - len(header) - sep - 1
        if room < 200:            # too little space left to say anything useful
            break
        body_room = min(max_per, room)
        if len(text) > body_room:
            # MARK the cut. Silent truncation is what taught the reviewer to report a
            # half-shown function as absent; an explicit marker lets it say "unknown"
            # instead, and the prompt tells it to prefer 'partial' over 'uncovered'.
            # The marker is part of the block, so reserve its own length out of the
            # budget — otherwise every truncated chunk overruns max_total by ~70 chars.
            reserve = len(_trunc_marker(len(text)))     # upper bound on the digit count
            keep = body_room - reserve
            if keep < 120:      # a sliver of code plus a marker teaches the model nothing
                break
            hidden = len(text) - keep
            body = text[:keep].rstrip() + _trunc_marker(hidden)
        else:
            body = text
        block = f"{header}\n{body}" if body else header
        used += len(block) + sep
        parts.append(block)
    return "\n\n".join(parts)


def _codereview_prompt(feature_name, requirement, code, briefs, evidence_block="") -> str:
    return (
        f"FEATURE: {feature_name}\n\nREQUIREMENT (truncated):\n{(requirement or '')[:2000]}\n\n"
        f"RELEVANT PRODUCTION CODE (excerpts; test/spec files excluded):\n{code}"
        f"{evidence_block}\n\n"
        f"TEST CASES TO JUDGE ({len(briefs)}):\n{json.dumps(briefs)[:5000]}\n\n"
        "For EACH case, decide from the PRODUCTION code ABOVE only:\n"
        "- 'covered' = the code clearly implements the SPECIFIC behaviour and you can name the exact file/function.\n"
        "- 'partial' = the relevant area exists but the specific behaviour is only partly handled.\n"
        "- 'uncovered' = the behaviour is absent, OR its implementing code is not in the excerpts above.\n"
        "IMPORTANT — TRUNCATION: an excerpt ending in a '// ...TRUNCATED' marker means the REST of "
        "that file was not shown to you. Treat the unseen part as UNKNOWN, never as proof of absence: "
        "if the visible part of a truncated file is clearly the right place for this behaviour, answer "
        "'partial' (citing that file) rather than 'uncovered', and say in the rationale that the "
        "relevant region was truncated.\n"
        "Do NOT assume code you cannot see; do NOT mark covered because a test could exist. "
        "For 'covered' or 'partial' you MUST cite the implementing file(s), copied EXACTLY as the "
        "`// FILE repo:path` header above shows them — a path that is not in the excerpts will be "
        "rejected and the verdict downgraded. In `rationale`, name the actual function/route/"
        "identifier you relied on so it can be checked against the code.\n"
        "Also give `confidence` (0.0-1.0): how sure you are given ONLY the code above.\n"
        "Return JSON: {\"cases\":[{\"test_case_id\":\"<id>\",\"status\":\"covered|partial|uncovered\","
        "\"rationale\":\"short, reference the code\",\"files\":[\"repo:path\"],\"confidence\":0.0-1.0}]}."
    )


# How many test cases are judged per LLM call. Every case in a batch competes for the
# model's attention against the same block of source, so a small local model juggling 10
# verdicts at once loses track: in a real run the reviewer denied that `verifyOtp` existed
# for one case and cited it correctly for another, from an IDENTICAL code block, in
# different batches. Lowering this trades more calls for markedly better attention per
# case and is the cheapest accuracy lever for a small model.
REVIEW_BATCH_SIZE = int(os.getenv("MINDMAP_BATCH_SIZE", "10"))


def _beat(progress, message: str):
    """Report liveness. Never let a progress callback break a review."""
    if not progress:
        return
    try:
        progress(message)
    except Exception:  # noqa: BLE001
        pass


def review_code_coverage(llm, feature_name, requirement, cases, code_excerpts, batch_size=None,
                         samples=1, progress=None, contract_findings=None) -> dict:
    """LLM external-reviewer pass: map actual code to a feature's test cases.

    Cases are judged in small BATCHES (so a large feature isn't crammed into one call, which
    caused the model to under-cover). Prompt is strict: 'covered' requires the specific behaviour
    to be visibly implemented in the excerpts AND a cited file.

    Every verdict is then GROUNDED (`_ground_verdict`): each cited path must resolve to a file
    actually present in `code_excerpts`, and identifiers named in the rationale must appear in
    that file's text. An unsupported claim is downgraded rather than trusted, and carries a
    confidence plus `needs_review` so a low-quality verdict is visible instead of silent.

    `samples` > 1 judges each batch repeatedly and keeps only unanimous 'covered' verdicts
    (see `_reconcile_samples`) — costs N× tokens, cuts hallucination variance.

    EXHAUSTIVE BY DEFAULT: the corpus is swept in as many context-sized windows as it
    takes, so every retrieved chunk is actually read. Previously only the first 20 chunks
    were shown and the rest discarded, which turned "we didn't look at it" into
    "uncovered". A case is judged uncovered only after EVERY window failed to find it;
    cases proven covered drop out early so the sweep stays affordable.

    `contract_findings` (optional, backward-compatible — omitting it reproduces prior
    behaviour exactly): pre-computed output of `contracts.find_orphaned_contract_reads(files)`
    over the WHOLE repo's current file text (the caller, `_codeanalysis_worker`, already holds
    this in memory and computes it once per run — it is not recomputed here, since this
    function only ever sees CHUNKED excerpts, not whole-file text).

    Unlike `verify_pr_implementation`'s `repo_files` (which finds a PR's diff and searches for
    a consumer elsewhere), Mind Map has no diff at all — it reviews one current snapshot — so
    the evidence here is the snapshot-only signal instead (see contracts.py's
    `find_orphaned_contract_reads`): a `.get(KEY, ...)` read whose KEY is written nowhere in
    the repo. The benchmark evidence for this exact bug (AUTH-007) showed the LLM had BOTH the
    producer and consumer files in front of it and still failed to connect them — a prompting
    problem, not a missing-evidence one — so this cannot rely on giving the model more text to
    read alone; the deterministic cap below is what actually holds the line regardless of what
    the model concludes.
    """
    budget = excerpt_total_chars(llm)
    batch_size = REVIEW_BATCH_SIZE if batch_size is None else max(1, int(batch_size))
    valid = {c["id"]: c for c in cases}
    errored = False
    passes = max(1, int(samples or 1))

    case_break_matches = {}
    evidence_block = ""
    if contract_findings:
        import grounding
        case_break_matches = grounding.match_contract_breaks_to_cases(contract_findings, cases)
        lines = []
        for fnd in contract_findings[:10]:
            hint = (f" (most similarly-named key written anywhere in the repo: "
                    f"`{fnd['suggested_replacement_key']}`)" if fnd.get("suggested_replacement_key")
                    else "")
            for con in (fnd.get("consumers") or [])[:5]:
                lines.append(
                    f"- {con['file']}:{con['line']} (function {con.get('function') or '?'}) reads "
                    f"`{fnd['old_key']}` via `.get(...)`, but NOTHING in the current codebase "
                    f"writes that key anywhere{hint}: `{con['snippet']}`")
        if lines:
            evidence_block = (
                "\n\nSTATIC-ANALYSIS EVIDENCE (ground truth — repo-wide scan, not a guess):\n"
                + "\n".join(lines) +
                "\n\nEach line above means the fallback/None path is taken UNCONDITIONALLY, every "
                "single time this code runs, because no producer anywhere in the repository ever "
                "supplies that key. If a test case depends on this behaving correctly under the "
                "real (non-fallback) value, it is NOT correctly implemented — use 'uncovered' or "
                "'partial', never 'covered', for that case.\n")

    # Citations are verified against the WHOLE corpus, not just the current window. A file
    # the model saw in an earlier window is still real evidence, so a global index avoids
    # rejecting a legitimate citation merely because this window didn't contain it. The
    # eligibility and symbol checks are unaffected — they read that file's actual text.
    idx = citation_index(code_excerpts)

    windows = window_excerpts(code_excerpts, budget, EXCERPT_PER_CHARS, EXCERPT_MAX_CHUNKS)
    if MAX_WINDOWS > 0:
        windows = windows[:MAX_WINDOWS]

    # cid -> [merged-per-window verdict]
    collected: dict = {}
    # Cases already proven covered with real evidence need no further windows — 'covered'
    # is the ceiling, so more reading cannot improve them. This is what keeps an
    # exhaustive sweep affordable: cases drop out as they resolve.
    resolved: set = set()

    for w_index, window in enumerate(windows, 1):
        pending = [c for c in cases if c["id"] not in resolved]
        if not pending:
            break
        code = _code_excerpt_block(window, max_total=budget)
        if not code:
            continue
        # HEARTBEAT. An exhaustive sweep is 10x+ longer than the single pass this replaced
        # — easily past the stale-job TTL — so a live worker MUST keep saying so or the
        # sweeper marks the job "worker heartbeat lost" while it is happily working.
        # Doubles as real progress in the UI instead of one frozen "reviewing <feature>".
        _beat(progress, f"reviewing {feature_name} — window {w_index}/{len(windows)}, "
                        f"{len(pending)} case(s) outstanding")
        batches = (len(pending) + batch_size - 1) // batch_size
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i + batch_size]
            if batches > 1:
                # A single window can itself outlast the TTL on a slow provider.
                _beat(progress,
                      f"reviewing {feature_name} — window {w_index}/{len(windows)}, "
                      f"batch {i // batch_size + 1}/{batches}")
            briefs = [{"id": c["id"], "title": c["title"], "type": c["type"],
                       "steps": c.get("steps", [])[:6]} for c in batch]
            prompt = _codereview_prompt(feature_name, requirement, code, briefs, evidence_block)
            per_case_samples: dict = {}
            for attempt in range(passes):
                # First pass stays near-deterministic; extra samples get a little heat so
                # agreement means something instead of re-reading one cached answer.
                temp = 0.1 if attempt == 0 else 0.35
                try:
                    # Reserve only what the reply needs; the rest is for code.
                    data = llm.chat_json(_CODEREV_SYS, prompt, temperature=temp,
                                         max_tokens=REVIEW_MAX_TOKENS)
                except Exception:  # noqa: BLE001
                    errored = True
                    continue
                seen_in_pass = set()
                for x in (data or {}).get("cases", []):
                    if not (isinstance(x, dict) and x.get("test_case_id") in valid):
                        continue
                    cid = x["test_case_id"]
                    if cid in seen_in_pass:      # duplicate rows within one reply
                        continue
                    seen_in_pass.add(cid)
                    raw_status = str(x.get("status") or "")
                    st = raw_status if raw_status in _STATUS_RANK else "uncovered"
                    raw_files = [f for f in (x.get("files") or [])][:6]
                    v = _ground_verdict(st, x.get("rationale", ""), raw_files, idx,
                                        model_confidence=x.get("confidence"))
                    v["rationale"] = str(x.get("rationale", ""))[:300]
                    per_case_samples.setdefault(cid, []).append(v)
            # Within a window, samples are repeated looks at the same code → conservative.
            for cid, samples_for_case in per_case_samples.items():
                merged = _reconcile_samples(samples_for_case)
                collected.setdefault(cid, []).append(merged)
                if merged.get("status") == "covered" and merged.get("files"):
                    resolved.add(cid)

    out = []
    for cid, c in valid.items():
        got = collected.get(cid)
        if not got:
            # Not returned by the model at all → uncovered, and honest about WHY. These are
            # different failures and must not read the same: an empty corpus means nobody
            # ever looked, which is a retrieval/indexing problem, not a coverage result.
            reason = ("no production code was retrieved for this feature, so nothing could "
                      "be matched — check the repo/branch selection and the code index"
                      if not code_excerpts else "case not returned by the reviewer")
            out.append({"test_case_id": cid, "display_id": c.get("display_id"),
                        "title": c["title"], "type": c["type"], "status": "uncovered",
                        "rationale": reason, "files": [],
                        "files_rejected": [], "files_ineligible": [], "confidence": 0.5,
                        "needs_review": not code_excerpts,
                        "grounding": {"citations_verified": 0, "citations_rejected": 0,
                                      "citations_ineligible": 0,
                                      "symbols_checked": 0, "symbols_supported": None,
                                      "unverifiable": False, "notes": [reason]}})
            continue
        # Across windows, the best evidence found anywhere wins.
        v = _merge_windows(got)
        v.update({"test_case_id": cid, "display_id": c.get("display_id"),
                  "title": c["title"], "type": c["type"]})
        # Deterministic cap: an orphaned-contract-read finding relevant to this case means a
        # real read-site, cited with file:line, unconditionally falls through to a
        # fallback/None value because nothing in the repo writes that key — that cannot be
        # 'covered' no matter what the LLM concluded (see the AUTH-007 Mind Map miss this is
        # designed to catch, where the LLM had this exact evidence in front of it and still
        # said 'covered'). Enforced independently of the model's own reasoning.
        if v.get("status") == "covered" and cid in case_break_matches:
            m0 = case_break_matches[cid][0]
            f0, con0 = m0["break"], m0["consumer"]
            v["downgraded_from"] = v.get("downgraded_from", v["status"])
            v["status"] = "partial"
            v["needs_review"] = True
            v["contract_break_cap"] = (
                f"capped from 'covered': {con0['file']}:{con0['line']} reads `{f0['old_key']}` "
                f"via `.get(...)`, but nothing in the current codebase writes that key — the "
                f"fallback/None path is taken unconditionally")
        out.append(v)

    res = {"cases": out, "grounding": {
        "reviewed_file_count": len(idx.get("canon") or {}),
        "windows_swept": len(windows),
        "chunks_reviewed": sum(len(w) for w in windows),
        "resolved_early": len(resolved),
        "samples": passes,
        "confidence_threshold": REVIEW_CONFIDENCE_THRESHOLD,
        "needs_review_count": sum(1 for c in out if c.get("needs_review")),
        "citations_rejected_total": sum(len(c.get("files_rejected") or []) for c in out),
        "citations_ineligible_total": sum(len(c.get("files_ineligible") or []) for c in out),
        "unverifiable_count": sum(1 for c in out
                                  if (c.get("grounding") or {}).get("unverifiable")),
        "downgraded_count": sum(1 for c in out if c.get("downgraded_from")),
    }}
    if contract_findings:
        res["contract_findings_considered"] = len(contract_findings)
    if errored:
        res["error"] = "one or more review batches failed"
    return res


_PRIMPL_SYS = (
    "You are an external code reviewer auditing whether a pull request's PRODUCTION code changes "
    "IMPLEMENT the behaviour described by a feature's test cases. Judge what the changed code DOES, "
    "like a reviewer reading the diff. CRITICAL: the presence of a test file or assertion does NOT "
    "make a case covered — only production code that fulfils the behaviour does (automated-test "
    "coverage is measured separately). Respond with a single JSON object only."
)


def verify_pr_implementation(llm, pr, prod_files, cases, batch_size=10, repo_files=None) -> dict:
    """LLM verifier: which test cases does this PR's PRODUCTION code actually IMPLEMENT?

    Judged in batches. Strict: merely touching the same endpoint/file is NOT enough for
    'covered' — the specific behaviour must be implemented in the diff. Returns
    {"covered":[{test_case_id,status:covered|partial,confidence:0-1,rationale}]}.

    `repo_files` (optional, backward-compatible — omitting it reproduces prior behaviour
    exactly) is the rest of the repository's current file text, the same shape Mind Map
    already holds in memory per run. When supplied, `contracts.build_contract_breaks()`
    (see app/contracts.py) statically finds producer/consumer contract changes whose
    consumers live OUTSIDE this PR's own diff — e.g. a renamed dict key/token claim that an
    unchanged file elsewhere still reads under the old name. This is the general,
    non-hardcoded fix for the class of miss where every file this function is handed is
    drawn only from `prod_files` (the PR's own diff), so a downstream consumer in an
    untouched file was structurally invisible to the LLM. Two things are grounded on it:
    (1) an explicit, cited EVIDENCE block is added to the prompt so the LLM reasons from
    real producer/consumer citations instead of diff-only guessing, and (2) a deterministic
    cap below the LLM's own judgement — a case tied to an unresolved break can never be
    reported 'covered' regardless of what the model says, since the downstream consumer
    provably was not updated by this PR.
    """
    diff = "\n".join(f"{f['filename']} ({f['status']}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})\n"
                     f"{f.get('patch', '')}" for f in prod_files[:25])[:6000]
    # Ground citations against the diff itself: the only files this PR can implement
    # anything in are the ones it changed.
    idx = citation_index([{"repo": "", "path": f.get("filename"), "text": f.get("patch") or ""}
                          for f in prod_files[:25]])
    valid = {c["id"] for c in cases}

    # Deterministic cross-file dependency evidence (app/contracts.py). Local imports:
    # contracts.py and grounding.py both import from this module (`is_test_file`), so a
    # module-level import here would be circular depending on load order; deferring to call
    # time is safe since by then every module involved has already finished loading.
    contract_breaks = []
    case_break_matches = {}
    if repo_files:
        import contracts
        import grounding
        try:
            deps = contracts.build_contract_breaks(prod_files, repo_files)
            contract_breaks = deps.get("contract_breaks", [])
        except Exception:  # noqa: BLE001 - the deterministic layer must never break the verifier
            contract_breaks = []
        if contract_breaks:
            case_break_matches = grounding.match_contract_breaks_to_cases(contract_breaks, cases)

    evidence_block = ""
    if contract_breaks:
        lines = []
        for b in contract_breaks[:10]:
            change = (f"`{b['old_key']}` -> `{b['new_key']}`" if b.get("old_key") and b.get("new_key")
                      else f"`{b.get('old_key') or b.get('new_key')}` ({b.get('change_type')})")
            for con in (b.get("consumers") or [])[:5]:
                lines.append(
                    f"- {b['producer_file']}::{b['producer_function']} changed {change}. "
                    f"Consumer {con['file']}:{con['line']} (function {con.get('function') or '?'}) "
                    f"still reads the OLD contract and is OUTSIDE this PR's diff — it was NOT "
                    f"changed by this PR: `{con['snippet']}`")
        if lines:
            evidence_block = (
                "\n\nCROSS-FILE DEPENDENCY EVIDENCE (static analysis, ground truth — these are REAL "
                "files/lines NOT included in the diff above, found by scanning the rest of the "
                "repository for consumers of a contract this PR changed):\n" + "\n".join(lines) +
                "\n\nIf a test case depends on one of these still-unupdated consumers behaving "
                "correctly with the NEW contract, the PR does NOT fully implement it — use "
                "'partial' (or omit), never 'covered', for that case.\n")

    out, seen, errored = [], set(), False
    for i in range(0, len(cases), batch_size):
        batch = cases[i:i + batch_size]
        briefs = [{"id": c["id"], "title": c["title"], "type": c["type"],
                   "steps": c.get("steps", [])[:6]} for c in batch]
        prompt = (
            f"PULL REQUEST #{pr.get('number')}: {pr.get('title', '')}\n\n"
            f"CHANGED PRODUCTION CODE (diff; test/spec files excluded):\n{diff}"
            f"{evidence_block}\n\n"
            f"TEST CASES TO JUDGE ({len(briefs)}):\n{json.dumps(briefs)[:5000]}\n\n"
            "For each case, judge whether THIS diff's PRODUCTION code IMPLEMENTS the SPECIFIC behaviour:\n"
            "- 'covered' = the changed code clearly implements this exact behaviour.\n"
            "- 'partial' = the diff touches the relevant area but does not fully implement this behaviour.\n"
            "Omit a case entirely if the diff does not implement or touch it. IMPORTANT: touching the same "
            "endpoint/route/function is NOT enough for 'covered' — the case's specific behaviour must be "
            "implemented in the diff, otherwise use 'partial' or omit.\n"
            "Cite the changed file(s) you relied on in `files`, exactly as named in the diff above, and "
            "name the actual function/route in `rationale` so both can be verified.\n"
            "Return JSON: {\"covered\":[{\"test_case_id\":\"<id>\",\"status\":\"covered|partial\","
            "\"confidence\":0.0-1.0,\"rationale\":\"short\",\"files\":[\"path\"]}]}."
        )
        try:
            data = llm.chat_json(_PRIMPL_SYS, prompt, temperature=0.1)
        except Exception:  # noqa: BLE001
            errored = True
            continue
        for x in data.get("covered", []):
            if isinstance(x, dict) and x.get("test_case_id") in valid and x["test_case_id"] not in seen:
                cid = x["test_case_id"]
                seen.add(cid)
                raw_status = str(x.get("status") or "")
                st = raw_status if raw_status in ("covered", "partial") else "partial"
                # floor='partial': this result only reports cases the PR touches, so a
                # weakly-evidenced claim is downgraded but never dropped — dropping it
                # would look identical to the model never having mentioned the case.
                v = _ground_verdict(st, x.get("rationale", ""), x.get("files") or [], idx,
                                    model_confidence=x.get("confidence"), floor="partial")
                status = v["status"]
                needs_review = v["needs_review"]
                contract_cap = None
                # Deterministic cap: an unresolved contract break relevant to this case means
                # a real downstream consumer, outside this PR's diff, still reads the OLD
                # contract shape — that cannot be 'covered' regardless of the LLM's verdict.
                # This does not depend on the LLM having used the evidence block at all; it
                # is enforced independently of what the model said.
                if status == "covered" and cid in case_break_matches:
                    m0 = case_break_matches[cid][0]
                    b0, con0 = m0["break"], m0["consumer"]
                    change = (f"`{b0['old_key']}`->`{b0['new_key']}`"
                              if b0.get("old_key") and b0.get("new_key")
                              else f"`{b0.get('old_key') or b0.get('new_key')}`")
                    status = "partial"
                    needs_review = True
                    contract_cap = (
                        f"capped from 'covered': {b0['producer_file']}::{b0['producer_function']} "
                        f"changed {change}, but {con0['file']}:{con0['line']} still reads the old "
                        f"contract and was not part of this PR's diff")
                out.append({"test_case_id": cid, "status": status,
                            "confidence": v["confidence"], "needs_review": needs_review,
                            "rationale": str(x.get("rationale", ""))[:300],
                            "files": v["files"], "files_rejected": v["files_rejected"],
                            "files_ineligible": v["files_ineligible"],
                            "grounding": v["grounding"],
                            **({"downgraded_from": v["downgraded_from"]}
                               if v.get("downgraded_from") else {}),
                            **({"contract_break_cap": contract_cap} if contract_cap else {})})
    res = {"covered": out,
           "grounding": {"needs_review_count": sum(1 for c in out if c.get("needs_review")),
                         "confidence_threshold": REVIEW_CONFIDENCE_THRESHOLD}}
    if contract_breaks:
        res["contract_breaks_considered"] = len(contract_breaks)
    if errored:
        res["error"] = "one or more verify batches failed"
    return res


_IMPACT_SYS = (
    "You are a senior QA engineer assessing release risk. Given a summary of recent code "
    "changes across a repository and a list of existing test cases, decide which test cases are "
    "IMPACTED and should be re-run. Respond with a single JSON object only."
)


def analyze_impact(llm, change_summary: str, cases) -> dict:
    """LLM-only: pick impacted test cases from recent code changes."""
    cases_brief = [{"id": c["id"], "title": c["title"], "type": c["type"],
                    "steps": c["steps"][:5]} for c in cases]
    prompt = (
        f"RECENT CODE CHANGES (files + diffs, truncated):\n{change_summary[:7000]}\n\n"
        f"EXISTING TEST CASES (id, title, type, steps):\n{json.dumps(cases_brief)[:7000]}\n\n"
        "Return JSON: {\"impacted\":[{\"test_case_id\":\"<id>\",\"reason\":\"why this change affects it\","
        "\"risk\":\"high|medium|low\"}]}. Include only test cases genuinely affected by these changes."
    )
    try:
        data = llm.chat_json(_IMPACT_SYS, prompt, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        return {"impacted": [], "error": str(e)}
    valid = {c["id"] for c in cases}
    out, seen = [], set()
    for x in data.get("impacted", []):
        if isinstance(x, dict) and x.get("test_case_id") in valid and x["test_case_id"] not in seen:
            seen.add(x["test_case_id"])
            # Clamp to the documented enum — an unrecognised value would otherwise reach
            # the UI and sort/filter unpredictably.
            risk = str(x.get("risk", "medium")).strip().lower()
            out.append({"test_case_id": x["test_case_id"], "reason": str(x.get("reason", ""))[:300],
                        "risk": risk if risk in ("high", "medium", "low") else "medium"})
    return {"impacted": out}


_DIFF_SYS = (
    "You are a senior QA engineer maintaining a test suite across requirement versions. "
    "Given the OLD and NEW requirement documents and the existing test cases (written for OLD), "
    "decide which existing cases are still valid under NEW (keep) and which are obsolete (retire). "
    "Respond with a single JSON object only."
)


def diff_versions(llm, old_text: str, new_text: str, prev_cases) -> dict:
    """Classify previous-version test cases as keep vs retire under the new docs."""
    brief = [{"id": c["id"], "title": c["title"], "type": c["type"], "steps": c["steps"][:5]}
             for c in prev_cases]
    prompt = (
        f"OLD REQUIREMENT (truncated):\n{old_text[:5000]}\n\n"
        f"NEW REQUIREMENT (truncated):\n{new_text[:5000]}\n\n"
        f"EXISTING TEST CASES (written for OLD):\n{json.dumps(brief)[:6000]}\n\n"
        "Return JSON: {\"keep\":[\"<id>\",...],\"retire\":[{\"id\":\"<id>\",\"reason\":\"why obsolete\"}]}. "
        "Every existing case id must appear in exactly one of keep or retire."
    )
    try:
        data = llm.chat_json(_DIFF_SYS, prompt, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        return {"keep": [c["id"] for c in prev_cases], "retire": [], "error": str(e)}
    valid = {c["id"] for c in prev_cases}
    keep = [i for i in data.get("keep", []) if i in valid]
    retire = [{"id": x["id"], "reason": str(x.get("reason", ""))[:300]}
              for x in data.get("retire", []) if isinstance(x, dict) and x.get("id") in valid]
    retired_ids = {x["id"] for x in retire}
    # any case not explicitly classified -> default keep (safe)
    for cid in valid:
        if cid not in keep and cid not in retired_ids:
            keep.append(cid)
    return {"keep": keep, "retire": retire}


_COVERAGE_SYS = (
    "You are a senior QA engineer doing code review. Given a pull request's changed files/diff "
    "and a list of existing test cases for a feature, decide which test cases this PR's changes "
    "exercise or relate to. Respond with a single JSON object only."
)


def review_coverage(llm, pr, files, feature_cases) -> dict:
    """Ask the LLM which test cases the PR covers; flag dev-authored tests."""
    dev_test_files = [f["filename"] for f in files if is_test_file(f["filename"])]
    diff = "\n".join(f"{f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']})\n{f['patch']}"
                     for f in files[:25])[:6000]
    cases_brief = [{"id": c["id"], "title": c["title"], "type": c["type"],
                    "steps": c["steps"][:6]} for c in feature_cases]
    prompt = (
        f"PULL REQUEST #{pr.get('number')}: {pr.get('title','')}\n\n"
        f"CHANGED FILES + DIFF (truncated):\n{diff}\n\n"
        f"DEVELOPER TEST FILES detected in this PR: {dev_test_files or 'none'}\n\n"
        f"EXISTING TEST CASES (id, title, steps):\n{json.dumps(cases_brief)[:6000]}\n\n"
        "Return JSON: {\"covered\":[{\"test_case_id\":\"<id>\",\"status\":\"covered|partial\","
        "\"by_dev_test\":true|false,\"rationale\":\"short\"}],\"confidence\":0.0-1.0}. "
        "Only include test cases genuinely related to these changes. by_dev_test=true if a developer "
        "test file in this PR appears to exercise that case."
    )
    try:
        data = llm.chat_json(_COVERAGE_SYS, prompt, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        return {"covered": [], "dev_test_files": dev_test_files, "confidence": 0.0,
                "error": str(e)}
    valid_ids = {c["id"] for c in feature_cases}
    try:
        top_conf = float(data.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        top_conf = 0.0
    covered, corrections = [], []
    for c in data.get("covered", []):
        if isinstance(c, dict) and c.get("test_case_id") in valid_ids:
            status = c.get("status") if c.get("status") in ("covered", "partial") else "covered"
            by_dev = bool(c.get("by_dev_test"))
            # Provably false claim: the model can't be exercised by a developer test
            # this PR doesn't contain. Cheap deterministic correction, no model needed.
            if by_dev and not dev_test_files:
                by_dev = False
                corrections.append(c["test_case_id"])
            covered.append({"test_case_id": c["test_case_id"],
                            "status": status,
                            "by_dev_test": by_dev,
                            "needs_review": bool(top_conf and top_conf < REVIEW_CONFIDENCE_THRESHOLD),
                            "rationale": str(c.get("rationale", ""))[:300]})
    out = {"covered": covered, "dev_test_files": dev_test_files, "confidence": top_conf}
    if corrections:
        out["grounding"] = {"by_dev_test_corrected": corrections,
                            "note": "by_dev_test cleared: this PR contains no developer test files"}
    return out


def compute_unmapped_changes(files: list, covered: list) -> list:
    """Files changed in this PR that no covered/partial test case appears to
    address. Heuristic: a file is 'mapped' if its path (or basename) appears in
    any covered case's rationale text. Mirrors Node's pr_unmapped_changes panel
    (file_path + reason) without a second LLM hop."""
    if not files:
        return []
    rationales = " ".join((c.get("rationale") or "") for c in (covered or []))
    rationales_low = rationales.lower()
    out = []
    for f in files:
        path = f.get("filename") or ""
        if not path:
            continue
        # Skip test files — those are reported separately as dev_test_files.
        if is_test_file(path):
            continue
        base = path.rsplit("/", 1)[-1].lower()
        if path.lower() in rationales_low or base in rationales_low:
            continue
        # Pull the first symbol from the patch (def/function/class) as a hint.
        patch = f.get("patch") or ""
        sym = ""
        for line in patch.splitlines()[:40]:
            line = line.lstrip("+ ")
            for prefix in ("def ", "function ", "class ", "func ", "fn ",
                           "public ", "private ", "async function ", "const ", "let "):
                if line.startswith(prefix):
                    sym = line[len(prefix):].split("(")[0].split(":")[0].split("=")[0].strip()
                    break
            if sym:
                break
        out.append({
            "file_path": path,
            "status": f.get("status", ""),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "symbol": sym[:80],
            "reason": "no test case appears to exercise this change",
        })
    return out[:30]


def diff_runs(prev_run: dict | None, this_covered: list) -> dict:
    """Compute newly_covered / no_longer_covered relative to a prior run.

    `prev_run` is a code_coverage_runs document (or None if there is no prior).
    `this_covered` is the list of covered/partial items just produced by
    review_coverage (each having `test_case_id` + status).
    """
    this_ids = {c.get("test_case_id") for c in this_covered if c.get("test_case_id")
                and c.get("status") in ("covered", "partial")}
    if not prev_run:
        return {"prev_run_id": None, "newly_covered": sorted(this_ids),
                "no_longer_covered": []}
    prev_result = prev_run.get("result") or {}
    prev_ids = {c.get("test_case_id") for c in (prev_result.get("covered") or [])
                if c.get("test_case_id")
                and c.get("status") in ("covered", "partial")}
    return {
        "prev_run_id": prev_run.get("id"),
        "prev_pr_number": prev_run.get("pr_number"),
        "prev_feature_version": prev_run.get("feature_version"),
        "newly_covered": sorted(this_ids - prev_ids),
        "no_longer_covered": sorted(prev_ids - this_ids),
    }
