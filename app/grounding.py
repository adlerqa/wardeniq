"""Grounded code-understanding primitives shared by Code Coverage and Commit Analysis.

This module turns raw diffs and source files into *evidence* — endpoints, symbols, and
token sets with exact file:line locations — and provides the matching/calibration helpers
that let the LLM act as a verifier on grounded signals instead of a blind guesser.

Design rules (see plan.md):
  * No LLM calls and no DB access here — pure, deterministic, unit-testable logic.
  * No hardcoded domain vocabulary (the old build's #1 accuracy flaw). Domain coherence is
    derived per-case from the test case's own title + steps.
  * Multi-language, offline, error-tolerant parsing via vendored tree-sitter grammars, with a
    regex fallback so unsupported languages still produce signals.

Libraries leveraged (the "why Python" of the stack):
  * unidiff  -> unified-diff parsing with exact new-file line numbers (real evidence).
  * tree-sitter (bundled grammars) -> accurate symbol/structure extraction; tolerates fragments.
  * numpy    -> fast vectorized cosine over the in-memory code index.
"""
import os
import re

import numpy as np
from unidiff import PatchSet

from coverage import is_test_file  # single source of truth for test-file detection
from extract import CODE_EXT       # recognised source-code extensions

# --------------------------------------------------------------------------- calibration
MATCH_THRESHOLD = 0.70
REVIEW_THRESHOLD = 0.50


def calibrate(confidence) -> str:
    """Map a 0..1 confidence to a verdict: matched | review_needed | dropped."""
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return "dropped"
    if c >= MATCH_THRESHOLD:
        return "matched"
    if c >= REVIEW_THRESHOLD:
        return "review_needed"
    return "dropped"


# --------------------------------------------------------------------------- tokenization
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "when", "then", "should",
    "will", "must", "user", "users", "test", "case", "cases", "verify", "verifies", "given",
    "valid", "invalid", "page", "data", "value", "values", "system", "api", "returns", "return",
    "request", "response", "status", "code", "able", "are", "via",
}


def _tokenize(text: str) -> set:
    """camelCase-aware tokeniser: lowercase identifiers, length >= 3, stop-words removed."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    return {t for t in re.findall(r"[A-Za-z][A-Za-z0-9]*", s.lower())
            if len(t) >= 3 and t not in _STOP}


def _step_text(st) -> str:
    """Steps come either as {action, expected} dicts or 'action -> expected' strings."""
    if isinstance(st, dict):
        return f"{st.get('action', '')} {st.get('expected', '')}"
    return str(st or "")


def domain_tokens(case: dict) -> set:
    """Trusted domain tokens for a test case — from its TITLE + STEPS only.

    These guard against cross-domain false positives (e.g. an OTP case matching a /cart route).
    """
    parts = [case.get("title", "")] + [_step_text(st) for st in (case.get("steps") or [])]
    return _tokenize(" ".join(parts))


def signal_tokens(*texts) -> set:
    """Tokens from a piece of evidence (symbol name, endpoint path, file path)."""
    return _tokenize(" ".join(t for t in texts if t))


def feature_keywords(name: str, requirement: str = "", case_titles=None, limit: int = 24) -> list:
    """Keywords for path/code retrieval — drawn from the feature NAME + requirement + every
    test-case TITLE (not just the name, which is often too generic). Ranked by how often the
    term appears across those sources so the most defining terms come first.
    """
    sources = [name or "", requirement or ""] + list(case_titles or [])
    freq = {}
    for src in sources:
        for tok in _tokenize(src):
            if len(tok) >= 4:                 # 4+ chars keeps path matching low-noise
                freq[tok] = freq.get(tok, 0) + 1
    # name tokens are the strongest signal — boost them
    for tok in _tokenize(name or ""):
        if tok in freq:
            freq[tok] += 3
    return [t for t, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))][:limit]


def tokens_overlap(a: set, b: set) -> bool:
    return bool(a & b)


# --------------------------------------------------------------------------- diff parsing
def parse_added_lines(patch: str, path: str = "f"):
    """Return [(new_file_line_no, text)] for added lines using unidiff.

    GitHub returns per-file patch bodies (no ---/+++ header); we wrap them so unidiff can
    recover the real target line numbers. Falls back to a naive '+' scan if parsing fails.
    """
    if not patch:
        return []
    wrapped = patch if patch.lstrip().startswith("---") else f"--- a/{path}\n+++ b/{path}\n{patch}"
    try:
        ps = PatchSet(wrapped)
    except Exception:  # noqa: BLE001
        return [(None, ln[1:]) for ln in patch.splitlines()
                if ln.startswith("+") and not ln.startswith("+++")]
    out = []
    for f in ps:
        for h in f:
            for ln in h:
                if ln.is_added:
                    out.append((ln.target_line_no, ln.value.rstrip("\n")))
    return out


# --------------------------------------------------------------------------- endpoint extraction
# (method_group, path_group, regex). path_group text must start with "/" to be accepted.
_ENDPOINT_RX = [
    # @app.get("/x") / @router.post('/x')  — FastAPI / Flask / NestJS decorators
    (1, 2, re.compile(r"""@\s*\w+\.(get|post|put|patch|delete|head|options)\s*\(\s*['"]([^'"]+)['"]""", re.I)),
    # app.get("/x") / router.post('/x') / r.GET("/x")  — Express / Koa / Gin / chi
    (1, 2, re.compile(r"""\b\w+\.(get|post|put|patch|delete|head|options|all|use)\s*\(\s*['"]([^'"]+)['"]""", re.I)),
    # @GetMapping("/x") / @RequestMapping(value="/x")  — Spring
    (1, 2, re.compile(r"""@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?['"]([^'"]+)['"]""")),
    # HandleFunc("/x", ...)  — Go net/http  (method unknown -> ANY)
    (None, 1, re.compile(r"""HandleFunc\s*\(\s*['"]([^'"]+)['"]""")),
]


def _norm_method(m) -> str:
    if not m:
        return "ANY"
    m = m.upper()
    return "ANY" if m in ("ALL", "USE", "REQUEST") else m


def extract_endpoints(patch: str, path: str, removed: bool = False) -> list:
    """Extract HTTP endpoints declared in a diff's added (or removed) lines.

    Returns [{method, path, file, line, removed}] with real line numbers from unidiff.
    """
    out, seen = [], set()
    for line_no, text in parse_added_lines(patch, path):
        for mg, pg, rx in _ENDPOINT_RX:
            for m in rx.finditer(text):
                p = m.group(pg)
                if not p or not p.startswith("/"):   # kills obj.get('key') style false hits
                    continue
                method = _norm_method(m.group(mg) if mg else None)
                key = (method, p)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"method": method, "path": p, "file": path,
                            "line": line_no, "removed": removed})
    return out


# --------------------------------------------------------------------------- endpoint alignment
def _norm_path(p: str) -> list:
    p = (p or "").split("?")[0].rstrip("/") or "/"
    segs = [s for s in p.split("/") if s]
    out = []
    for s in segs:
        if (s.startswith(":") or (s.startswith("{") and s.endswith("}"))
                or (s.startswith("<") and s.endswith(">")) or s.isdigit()):
            out.append("*")   # path params and concrete numeric ids -> wildcard
        else:
            out.append(s.lower())
    return out


def endpoints_align(a: dict, b: dict) -> str:
    """Return 'exact' | 'path' | 'none' for two {method, path} endpoints."""
    ma, mb = _norm_method(a.get("method")), _norm_method(b.get("method"))
    if ma != "ANY" and mb != "ANY" and ma != mb:
        return "none"
    pa, pb = _norm_path(a.get("path")), _norm_path(b.get("path"))
    if pa == pb:
        return "exact"
    short, long_ = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    if short and long_[-len(short):] == short and any(s != "*" for s in short):
        return "path"
    return "none"


_EP_IN_TEXT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_\-/{}:.]*)", re.I)
_PATH_IN_TEXT = re.compile(r"(?<![\w'\"])(/[A-Za-z0-9_\-/{}:.]+)")


def case_endpoints(case: dict) -> list:
    """Endpoints referenced by a test case's title/steps (method + path, or bare path -> ANY)."""
    text = case.get("title", "") + " " + " ".join(
        _step_text(s) for s in (case.get("steps") or []))
    eps, used = [], set()
    for m in _EP_IN_TEXT.finditer(text):
        ep = {"method": m.group(1).upper(), "path": m.group(2)}
        eps.append(ep)
        used.add(ep["path"])
    for m in _PATH_IN_TEXT.finditer(text):
        p = m.group(1)
        if p not in used and len(p) > 1:
            eps.append({"method": "ANY", "path": p})
            used.add(p)
    return eps


# --------------------------------------------------------------------------- symbol extraction
GENERIC_SYMBOLS = {
    "index", "main", "init", "constructor", "handler", "handle", "get", "set", "run", "start",
    "stop", "new", "create", "update", "delete", "list", "tostring", "equals", "hashcode",
    "render", "setup", "teardown", "default", "callback", "wrapper", "test", "foo", "bar",
}

# (kind, regex) — regexes run per added diff line so unidiff line numbers stay attached.
_SYMBOL_RX = [
    ("class", re.compile(r"\bclass\s+([A-Za-z_]\w*)")),
    ("function", re.compile(r"\bdef\s+([A-Za-z_]\w*)")),               # python / ruby
    ("function", re.compile(r"\bfunction\s+([A-Za-z_]\w*)")),          # js / ts
    ("function", re.compile(r"\b(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(")),  # js arrow
    ("function", re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")),  # go
]

_EXT_LANG = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
             ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".go": "go",
             ".java": "java", ".rb": "ruby"}
_TS_CACHE = {}
_INTEREST = ("function", "method", "class", "module", "interface")


def _ts_language(ext: str):
    """Load a vendored tree-sitter Language for an extension, or None. Cached."""
    if ext in _TS_CACHE:
        return _TS_CACHE[ext]
    name = _EXT_LANG.get(ext)
    lang = None
    if name:
        try:
            from tree_sitter import Language
            if name == "python":
                import tree_sitter_python as mod; raw = mod.language()
            elif name == "javascript":
                import tree_sitter_javascript as mod; raw = mod.language()
            elif name == "typescript":
                import tree_sitter_typescript as mod
                raw = mod.language_tsx() if ext == ".tsx" else mod.language_typescript()
            elif name == "go":
                import tree_sitter_go as mod; raw = mod.language()
            elif name == "java":
                import tree_sitter_java as mod; raw = mod.language()
            elif name == "ruby":
                import tree_sitter_ruby as mod; raw = mod.language()
            else:
                raw = None
            lang = Language(raw) if raw is not None else None
        except Exception:  # noqa: BLE001  -- missing wheel / ABI mismatch -> regex fallback
            lang = None
    _TS_CACHE[ext] = lang
    return lang


def _kind(node_type: str) -> str:
    for k in ("class", "interface", "module", "method", "function"):
        if k in node_type:
            return k
    return "symbol"


def _regex_symbols(text: str, path: str) -> list:
    out, seen = [], set()
    for i, line in enumerate(text.splitlines(), start=1):
        for kind, rx in _SYMBOL_RX:
            for m in rx.finditer(line):
                name = m.group(1)
                if name and name.lower() not in GENERIC_SYMBOLS and (kind, name, i) not in seen:
                    seen.add((kind, name, i))
                    out.append({"name": name, "kind": kind, "file": path, "line": i})
    return out


def extract_symbols_from_source(text: str, path: str) -> list:
    """Functions/classes/methods from a FULL source file (tree-sitter, regex fallback).

    Used for Mind Map code indexing where whole files are available. Returns
    [{name, kind, file, line}].
    """
    ext = os.path.splitext(path or "")[1].lower()
    lang = _ts_language(ext)
    if lang is not None:
        try:
            from tree_sitter import Parser
            data = (text or "").encode("utf-8", "replace")
            root = Parser(lang).parse(data).root_node
            out, seen = [], set()

            def walk(n):
                if any(k in n.type for k in _INTEREST):
                    nm = n.child_by_field_name("name")
                    if nm is not None:
                        name = data[nm.start_byte:nm.end_byte].decode("utf-8", "replace")
                        line = nm.start_point[0] + 1
                        if name and name.lower() not in GENERIC_SYMBOLS and (name, line) not in seen:
                            seen.add((name, line))
                            out.append({"name": name, "kind": _kind(n.type),
                                        "file": path, "line": line})
                for c in n.children:
                    walk(c)

            walk(root)
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return _regex_symbols(text or "", path)


def extract_symbols(patch: str, path: str) -> list:
    """Symbols added in a DIFF (regex over added lines, with real unidiff line numbers)."""
    out, seen = [], set()
    for line_no, text in parse_added_lines(patch, path):
        for kind, rx in _SYMBOL_RX:
            for m in rx.finditer(text):
                name = m.group(1)
                if name and name.lower() not in GENERIC_SYMBOLS and name not in seen:
                    seen.add(name)
                    out.append({"name": name, "kind": kind, "file": path, "line": line_no})
    return out


# --------------------------------------------------------------------------- file classification
_TEST_INFRA_RE = re.compile(
    r"(jest|vitest|playwright|cypress|karma|mocha|nightwatch|wdio)\.config"
    r"|/__mocks__/|(^|/)conftest\.py$|setup\.(jest|tests?)\.",
    re.I,
)


def classify_diff_files(files) -> tuple:
    """Split changed files into (production, test, test_infra). `files` may be dicts or paths."""
    prod, test, infra = [], [], []
    for f in files:
        name = f.get("filename") if isinstance(f, dict) else f
        if not name:
            continue
        if is_test_file(name):
            test.append(name)
        elif _TEST_INFRA_RE.search(name):
            infra.append(name)
        elif os.path.splitext(name)[1].lower() in CODE_EXT:
            prod.append(name)
        # else: docs / lockfiles / generic config -> ignored
    return prod, test, infra


def is_test_only(files) -> bool:
    """True when a change touches only test / test-infra files (no production source)."""
    prod, test, infra = classify_diff_files(files)
    return not prod and bool(test or infra)


def dev_tested_cases(dev_test_files, cases) -> set:
    """Grounded automation signal (no LLM): which cases a PR's dev-test files plausibly exercise.

    A case is considered dev-tested when its domain tokens overlap the tokens of a changed test
    file's path (e.g. `tests/test_login.py` -> the "Login..." case). Conservative and explainable;
    full test->case mapping is the separate test-repo-scanning feature.
    """
    file_tokens = set()
    for f in dev_test_files:
        name = f.get("filename") if isinstance(f, dict) else f
        file_tokens |= signal_tokens(name or "")
    if not file_tokens:
        return set()
    return {c["id"] for c in cases if tokens_overlap(domain_tokens(c), file_tokens)}


# --------------------------------------------------------------------------- fast vector math
def cosine(a, b) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(va @ vb / (na * nb))


def _bm25_tokens(text: str) -> list:
    """Code-aware tokeniser for lexical (BM25) matching: camelCase/snake split, keep len>=2."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    return [t for t in re.findall(r"[A-Za-z0-9_]+", s.lower()) if len(t) >= 2]


def hybrid_rank_indices(query_text, texts, query_vec, vectors, top_k: int = 16) -> list:
    """Fuse LEXICAL (BM25) and SEMANTIC (cosine) rankings via reciprocal-rank-fusion.

    Retrieval is the accuracy bottleneck for code review: BM25 nails exact identifier/endpoint
    matches (e.g. `/api/login`, `checkout`) that weak local embeddings miss, while cosine catches
    paraphrases. RRF combines both so the truly-relevant code surfaces for the reviewer.
    """
    n = len(texts)
    if n == 0:
        return []
    # semantic ranking
    if query_vec is not None and vectors is not None and len(vectors) == n:
        cos_order = rank_by_cosine(query_vec, vectors, top_k=n)
    else:
        cos_order = list(range(n))
    # lexical ranking
    try:
        from rank_bm25 import BM25Okapi
        corpus = [_bm25_tokens(t) for t in texts]
        bm = BM25Okapi(corpus)
        scores = bm.get_scores(_bm25_tokens(query_text))
        bm_order = sorted(range(n), key=lambda i: scores[i], reverse=True)
    except Exception:  # noqa: BLE001  -- rank_bm25 missing → fall back to cosine only
        bm_order = cos_order
    rrf = {}
    for rank, i in enumerate(cos_order):
        rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + rank)
    for rank, i in enumerate(bm_order):
        rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + rank)
    return sorted(rrf, key=lambda i: rrf[i], reverse=True)[:top_k]


def _split_chars(s: str, max_chars: int) -> list:
    s = s or ""
    if not s.strip():
        return []
    if len(s) <= max_chars:
        return [s]
    return [s[i:i + max_chars] for i in range(0, len(s), max_chars)]


def chunk_code_by_function(text: str, path: str, max_chars: int = 2000) -> list:
    """Split source into COMPLETE function/method bodies (via tree-sitter) plus a module-level
    remainder (imports, route registrations, config). Feeding whole implementations — instead of
    arbitrary 1.5k char windows — lets the reviewer judge a case against the full function that
    implements it. Falls back to char-chunking for unsupported languages or parse failures.
    """
    lines = (text or "").split("\n")
    lang = _ts_language(os.path.splitext(path or "")[1].lower())
    if lang is None or not (text or "").strip():
        return _split_chars(text, max_chars) if text else []
    try:
        from tree_sitter import Parser
        root = Parser(lang).parse((text or "").encode("utf-8", "replace")).root_node
        spans = []

        def walk(n):
            if ("function" in n.type or "method" in n.type) and n.start_point[0] != n.end_point[0]:
                spans.append((n.start_point[0], n.end_point[0]))
                return   # don't recurse into a captured function
            for c in n.children:
                walk(c)

        walk(root)
    except Exception:  # noqa: BLE001
        return _split_chars(text, max_chars)
    if not spans:
        return _split_chars(text, max_chars)
    spans.sort()
    covered = [False] * len(lines)
    chunks = []
    for s, e in spans:
        e = min(e, len(lines) - 1)
        chunks += _split_chars("\n".join(lines[s:e + 1]), max_chars)
        for i in range(s, e + 1):
            covered[i] = True
    module = "\n".join(lines[i] for i in range(len(lines)) if not covered[i]).strip()
    chunks += _split_chars(module, max_chars)   # keep imports / route registrations / config
    return [c for c in chunks if c.strip()]


def rank_by_cosine(query_vec, vectors, top_k: int = 12) -> list:
    """Return indices of the top_k vectors most similar to query_vec (vectorised)."""
    if not len(vectors):
        return []
    q = np.asarray(query_vec, dtype=float)
    qn = np.linalg.norm(q) or 1.0
    M = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(M, axis=1)
    norms[norms == 0] = 1.0
    scores = (M @ q) / (norms * qn)
    k = min(top_k, len(scores))
    idx = np.argpartition(-scores, k - 1)[:k]
    return [int(i) for i in idx[np.argsort(-scores[idx])]]


# --------------------------------------------------------------------------- commit matching
_MAX_EVIDENCE = 5


def _add_evidence(match: dict, ev: dict):
    key = (ev.get("sha"), ev.get("file"), ev.get("line"))
    if key in match["_seen"] or len(match["evidence"]) >= _MAX_EVIDENCE:
        return
    match["_seen"].add(key)
    match["evidence"].append({k: ev.get(k) for k in ("repo", "sha", "url", "file", "line", "signal")})


def match_commit_changes(commits: list, cases: list) -> dict:
    """Grounded, evidence-bearing match of commit changes to test cases (NO LLM).

    Tiers (highest confidence wins): endpoint-exact (1, .95) > endpoint-path (2, .90) >
    symbol-overlap-with-domain-guard (3, .75). Every match cites the exact commit/file/line.

    `commits`: [{repo, sha, message, files:[{filename,status,patch,...}]}]
    `cases`:   [{id, title, type, steps}]
    Returns {"matches": {case_id: {...}}, "matched_ids": set}.
    """
    # 1) pull grounded signals out of every (non-test) changed file, tagged with commit context
    endpoints, symbols = [], []
    for c in commits:
        repo, sha, url = c.get("repo"), c.get("sha"), c.get("url")
        for f in c.get("files", []) or []:
            path, patch = f.get("filename", ""), f.get("patch", "")
            if not path or is_test_file(path):   # test files are never primary evidence
                continue
            for ep in extract_endpoints(patch, path):
                endpoints.append({**ep, "repo": repo, "sha": sha, "url": url})
            for sy in extract_symbols(patch, path):
                symbols.append({**sy, "repo": repo, "sha": sha, "url": url})

    # Document frequency of domain tokens across the whole suite. A token shared by
    # a large fraction of cases (e.g. "auth"/"token"/"session" in a login feature)
    # is feature-wide, not distinctive, so a symbol match resting only on such a
    # token is noise. Only applied once the suite is big enough for frequency to mean
    # something.
    case_toks = {c["id"]: domain_tokens(c) for c in cases}
    df = {}
    for toks in case_toks.values():
        for t in toks:
            df[t] = df.get(t, 0) + 1
    n_cases = max(1, len(cases))
    generic_cutoff = max(2, n_cases // 3)

    def _distinctive(tok):
        # small suites: every token counts; larger suites: drop feature-wide tokens
        return n_cases < 6 or df.get(tok, 0) <= generic_cutoff

    # 2) score each case against the signals
    matches = {}
    for case in cases:
        cid = case["id"]
        ceps = case_endpoints(case)
        ctoks = case_toks[cid]
        best = None

        # endpoint tiers
        for ev in endpoints:
            tier = conf = None
            for cep in ceps:
                align = endpoints_align(cep, ev)
                if align == "exact":
                    tier, conf = 1, 0.95
                    break
                if align == "path" and tier is None:
                    tier, conf = 2, 0.90
            if tier is None:
                continue
            sig = f"{ev['method']} {ev['path']}"
            evd = {"repo": ev["repo"], "sha": ev["sha"], "url": ev.get("url"),
                   "file": ev["file"], "line": ev["line"], "signal": sig}
            if best is None or tier < best["tier"]:
                best = {"tier": tier, "confidence": conf, "signal": sig,
                        "signal_type": "endpoint", "risk": "high",
                        "evidence": [], "_seen": set()}
                _add_evidence(best, evd)
            elif tier == best["tier"] and best["signal_type"] == "endpoint":
                _add_evidence(best, evd)

        # symbol tier — only if no endpoint matched; guarded by the case's own domain
        # tokens AND requiring at least one DISTINCTIVE shared token (a feature-wide
        # word like "auth"/"token"/"session" alone is not enough evidence).
        if best is None:
            for ev in symbols:
                overlap = ctoks & signal_tokens(ev["name"])
                if not overlap or not any(_distinctive(t) for t in overlap):
                    continue
                if best is None:
                    best = {"tier": 3, "confidence": 0.75, "signal": ev["name"],
                            "signal_type": "symbol", "risk": "medium",
                            "evidence": [], "_seen": set()}
                _add_evidence(best, {"repo": ev["repo"], "sha": ev["sha"],
                                     "url": ev.get("url"), "file": ev["file"],
                                     "line": ev["line"], "signal": ev["name"]})

        if best:
            best.pop("_seen", None)
            best["status"] = calibrate(best["confidence"])
            n = len(best["evidence"])
            where = best["evidence"][0] if n else {}
            best["reason"] = (
                f"{best['signal_type']} `{best['signal']}` changed in "
                f"{where.get('file', '?')}:{where.get('line', '?')}"
                + (f" (+{n - 1} more)" if n > 1 else ""))
            matches[cid] = best

    # 3) fan-out cap: a changed symbol that "matches" a large share of the suite is a
    # shared utility, not a precise per-case impact. Drop those symbol matches so they
    # fall through to the LLM semantic tier instead of flooding results as false
    # positives. Endpoints are exempt — they're precise by construction.
    fanout_cap = max(6, n_cases // 6)
    sym_spread = {}
    for m in matches.values():
        if m["signal_type"] == "symbol":
            sym_spread[m["signal"]] = sym_spread.get(m["signal"], 0) + 1
    noisy = {sig for sig, k in sym_spread.items() if k > fanout_cap}
    if noisy:
        matches = {cid: m for cid, m in matches.items()
                   if not (m["signal_type"] == "symbol" and m["signal"] in noisy)}

    return {"matches": matches, "matched_ids": set(matches.keys())}
