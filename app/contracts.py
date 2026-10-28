
from __future__ import annotations

import re

from coverage import is_test_file  # single source of truth for test-file detection

try:
    from unidiff import PatchSet
except Exception:  # noqa: BLE001 — keep this module importable even if unidiff isn't installed
    PatchSet = None


# --------------------------------------------------------------------------- diff parsing
def _hunks(patch: str, path: str):
    """Yield unidiff Hunk objects for a (possibly header-less) GitHub-style patch body."""
    if not patch or PatchSet is None:
        return []
    wrapped = patch if patch.lstrip().startswith("---") else f"--- a/{path}\n+++ b/{path}\n{patch}"
    try:
        ps = PatchSet(wrapped)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for f in ps:
        out.extend(list(f))
    return out


# --------------------------------------------------------------------------- function naming
# Applied to a hunk's `section_header` (git's own "nearest enclosing function/class" heuristic,
# populated for most languages by git's default diff driver) — general by construction, not
# tied to any one language. Falls back to scanning context lines when a driver doesn't populate
# section_header (e.g. some minimal git configs).
_DEF_RX = [
    re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\("),                     # Python
    re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\("),                # JS/TS (named function)
    re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("),   # Go (incl. methods)
    re.compile(r"\b(?:public|private|protected|static)[\w\s<>\[\]]*?\s([A-Za-z_]\w*)\s*\("),  # Java/C#
    re.compile(r"^([A-Za-z_]\w*)\s*[:=]\s*(?:async\s*)?\([^)]*\)\s*=>"),  # JS arrow assigned to a name
]


def _function_name(section_header: str) -> str | None:
    header = (section_header or "").strip()
    if not header:
        return None
    for rx in _DEF_RX:
        m = rx.search(header)
        if m:
            return m.group(1)
    return None


# --------------------------------------------------------------------------- key write/read extraction
GENERIC_KEYS = {
    "self", "cls", "data", "value", "result", "response", "request", "params", "options",
    "kwargs", "args", "config", "context", "item", "items", "key", "value",
}

# Each write pattern is tagged with a KIND BUCKET ("dict" or "attr"). A rename is only ever
# paired with, and only ever searched against, reads of the SAME bucket — `stored.role` (an
# unrelated object's plain attribute) must never be treated as a consumer of a DICT key named
# "role" that some other object writes, even though both literally contain the word "role".
# This distinction was added after a real false positive surfaced in testing (see
# WARDENIQ_CROSS_FILE_BEFORE_AFTER.md, "False-positive checks"): a Payment/login case matched
# purely because `stored.role` (a plain attribute, unrelated model) shares the literal name
# "role" with the JWT-claim DICT key `issue_token_pair` renames.
_WRITE_RX = [
    ("dict", "dict_subscript", re.compile(r"[\w\.]+\[\s*['\"]([A-Za-z_][\w-]*)['\"]\s*\]\s*=(?!=)")),
    ("dict", "dict_literal_key", re.compile(r"^\s*['\"]([A-Za-z_][\w-]*)['\"]\s*:\s*\S")),
    ("attr", "attr_write", re.compile(r"\bself\.([A-Za-z_]\w*)\s*=(?!=)")),
    # Captures the argument list of dict(...) (one level of nested parens, or up to end of line
    # for a call spanning lines); every keyword in it is then pulled out by _KWARG_RX.
    ("dict", "kwarg_write", re.compile(r"\bdict\(((?:[^()]|\([^()]*\))*)")),
]
_KWARG_RX = re.compile(r"(?:^|,)\s*([A-Za-z_]\w*)\s*=(?!=)")
_NESTED_PARENS_RX = re.compile(r"\([^()]*\)")


def extract_key_writes_from_lines(lines: list[str]) -> dict[str, set[str]]:
    """Keys/fields WRITTEN across a set of lines (added-only or removed-only diff lines, or a
    whole file). Conservative by construction: only literal string keys are considered — a
    dynamically computed key (`payload[var_name] = ...`) is skipped rather than guessed at,
    since a wrong guess here would fabricate evidence.

    Returns {key: {kind_bucket, ...}} — a key can appear via more than one bucket (rare, but
    keeps this a strict superset of the old flat-set behaviour rather than an approximation).
    """
    out: dict[str, set[str]] = {}
    for line in lines:
        for kind, label, rx in _WRITE_RX:
            for m in rx.finditer(line):
                if label == "kwarg_write":
                    keys = _KWARG_RX.findall(_NESTED_PARENS_RX.sub("", m.group(1)))
                else:
                    keys = [m.group(1)]
                for key in keys:
                    if key and key.lower() not in GENERIC_KEYS:
                        out.setdefault(key, set()).add(kind)
    return out


_READ_RX_TEMPLATES = [
    ("dict", r"\.get\(\s*['\"]{key}['\"]"),
    ("dict", r"\[\s*['\"]{key}['\"]\s*\](?!\s*=(?!=))"),
    ("dict", r"getattr\([^,]+,\s*['\"]{key}['\"]"),
    ("attr", r"\.{key}\b(?!\s*=(?!=))(?!\s*\()"),
]


def extract_key_reads_for(key: str, text: str, kinds: set[str] | None = None) -> list[dict]:
    """Locations in `text` (a WHOLE file's current content) that read the literal key/field
    `key`, with a best-effort 1-based line number and a short snippet for the citation.

    `kinds`: restrict to these read-kind buckets ("dict" and/or "attr"). Omit to search both —
    callers that know the PRODUCER's write kind should always pass it, so a dict-key rename is
    never matched against an unrelated plain-attribute read of the same literal name (see the
    module-level note above `_WRITE_RX`).

    Targeted by construction — this only ever searches for one already-identified key, so it
    does not suffer the false-positive blast radius a blanket "find every attribute access"
    pass would have.
    """
    if not key:
        return []
    out = []
    patterns = [(kind, re.compile(t.format(key=re.escape(key))))
                for kind, t in _READ_RX_TEMPLATES if kinds is None or kind in kinds]
    for i, line in enumerate((text or "").splitlines(), start=1):
        if any(rx.search(line) for _kind, rx in patterns):
            out.append({"line": i, "snippet": line.strip()[:160]})
    return out


# --------------------------------------------------------------------------- per-diff producer changes
class ProducerChange:
    __slots__ = ("file", "function", "old_key", "new_key", "change_type", "kinds")

    def __init__(self, file, function, old_key, new_key, change_type, kinds):
        self.file = file
        self.function = function
        self.old_key = old_key
        self.new_key = new_key
        self.change_type = change_type   # "rename" | "removal" | "addition"
        self.kinds = kinds                # {"dict"} and/or {"attr"} — the WRITE kind(s) seen

    def as_dict(self):
        return {"file": self.file, "function": self.function, "old_key": self.old_key,
                "new_key": self.new_key, "change_type": self.change_type, "kinds": sorted(self.kinds)}


def diff_producer_changes(patch: str, path: str) -> tuple[list, set]:
    """What did this ONE file's diff change about the contracts it produces?

    Returns (changes, touched_functions):
      * changes: list[ProducerChange] for key renames/removals/additions found in a hunk whose
        enclosing function could be identified.
      * touched_functions: every function name whose body was touched at all in this diff,
        whether or not a key-level change was detected — the coarser "shared utility / function
        contract changed" signal (function return-shape changes, signature changes, or any
        other body edit a caller elsewhere might be sensitive to).
    """
    if is_test_file(path):
        return [], set()
    changes: list[ProducerChange] = []
    touched: set[str] = set()
    for hunk in _hunks(patch, path):
        func = _function_name(getattr(hunk, "section_header", None)) or "<module-level>"
        touched.add(func)
        removed_lines = [ln.value for ln in hunk if ln.is_removed]
        added_lines = [ln.value for ln in hunk if ln.is_added]
        removed_map = extract_key_writes_from_lines(removed_lines)
        added_map = extract_key_writes_from_lines(added_lines)
        only_removed = sorted(set(removed_map) - set(added_map))
        only_added = sorted(set(added_map) - set(removed_map))
        # Pair off removed/added keys positionally within the same hunk+function as renames —
        # best-effort but exact enough to be explainable: each pairing cites the real hunk.
        paired = min(len(only_removed), len(only_added))
        for i in range(paired):
            old_key, new_key = only_removed[i], only_added[i]
            changes.append(ProducerChange(path, func, old_key, new_key, "rename",
                                          removed_map[old_key] | added_map[new_key]))
        for old_key in only_removed[paired:]:
            changes.append(ProducerChange(path, func, old_key, None, "removal", removed_map[old_key]))
        for new_key in only_added[paired:]:
            changes.append(ProducerChange(path, func, None, new_key, "addition", added_map[new_key]))
    return changes, touched


# --------------------------------------------------------------------------- repo-wide consumer search
_DEF_LINE_RX = re.compile(r"^(\s*)(?:def|function|func)\s+([A-Za-z_]\w*)\s*\(")


def _enclosing_function_in_text(text: str, at_line: int) -> str | None:
    """Nearest enclosing `def`/`function`/`func` above `at_line` (1-based) in a WHOLE file's
    text, using indentation to stay inside the same block — good enough for the common case
    (Python/JS/Go-style bodies) without needing a full parser for what is, again, evidence for
    an LLM/human to weigh, not a certainty claim."""
    lines = (text or "").splitlines()
    if at_line < 1 or at_line > len(lines):
        return None
    target_indent = len(lines[at_line - 1]) - len(lines[at_line - 1].lstrip())
    for i in range(at_line - 1, -1, -1):
        m = _DEF_LINE_RX.match(lines[i])
        if m and len(m.group(1)) < target_indent + 1:
            return m.group(2)
    return None


def find_key_consumers(old_key: str, repo_files: list[dict], diff_paths: set[str],
                       kinds: set[str] | None = None) -> list[dict]:
    """Where else in the CURRENT repo snapshot is `old_key` still read, outside the diff?

    `kinds`: the PRODUCER's write kind(s) (see `_WRITE_RX`) — restricts the read search to the
    same kind so a dict-key rename is never matched against an unrelated plain attribute of the
    same literal name (and vice versa). Always pass this in real use; it defaults to None
    (search both kinds) only so the function stays independently callable/testable.
    """
    if not old_key:
        return []
    out = []
    for rf in repo_files:
        path = rf.get("path") or rf.get("filename") or ""
        if not path or path in diff_paths or is_test_file(path):
            continue
        text = rf.get("text") or ""
        for hit in extract_key_reads_for(old_key, text, kinds=kinds):
            out.append({"file": path, "line": hit["line"], "snippet": hit["snippet"],
                        "function": _enclosing_function_in_text(text, hit["line"])})
    return out


def find_function_consumers(func_name: str, repo_files: list[dict], diff_paths: set[str]) -> list[dict]:
    """Where else in the CURRENT repo snapshot is `func_name` CALLED, outside the diff? Coarser
    companion signal for function/interface and shared-utility contract changes that aren't
    expressible as a single dict-key rename (e.g. a return tuple's arity changed, internal
    logic changed with no key involved at all)."""
    if not func_name or func_name == "<module-level>":
        return []
    rx = re.compile(r"\b" + re.escape(func_name) + r"\s*\(")
    out = []
    for rf in repo_files:
        path = rf.get("path") or rf.get("filename") or ""
        if not path or path in diff_paths or is_test_file(path):
            continue
        text = rf.get("text") or ""
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line) and "def " not in line and "function " not in line:
                out.append({"file": path, "line": i, "snippet": line.strip()[:160],
                            "function": _enclosing_function_in_text(text, i)})
    return out


# --------------------------------------------------------------------------- top-level entry point
_MAX_CONSUMERS_PER_BREAK = 8


def build_contract_breaks(pr_files: list[dict], repo_files: list[dict]) -> dict:
    """The full pipeline: PR diff -> changed contracts -> repo-wide consumers -> evidence.

    `pr_files`: [{"filename", "patch"}, ...] — exactly the shape already used elsewhere in this
        codebase for a PR's/commit's changed files.
    `repo_files`: [{"path", "text"}, ...] — the CURRENT full text of the repo's other files
        (the diff's own files are excluded automatically even if included here).

    Returns {"contract_breaks": [...], "function_changes": [...]}. Both are evidence lists, not
    verdicts — callers decide how to weigh them (see grounding.match_commit_changes and
    coverage.verify_pr_implementation for how this pilot's fix wires them in).
    """
    diff_paths = {f.get("filename") for f in pr_files if f.get("filename")}
    all_changes: list[ProducerChange] = []
    all_touched: set[str] = set()
    for f in pr_files:
        path = f.get("filename") or ""
        if not path:
            continue
        changes, touched = diff_producer_changes(f.get("patch") or "", path)
        all_changes.extend(changes)
        all_touched |= touched

    breaks = []
    functions_with_key_changes = set()
    for change in all_changes:
        if change.change_type not in ("rename", "removal"):
            continue   # pure additions rarely break an existing consumer
        functions_with_key_changes.add(change.function)
        consumers = find_key_consumers(change.old_key, repo_files, diff_paths, kinds=change.kinds)
        if not consumers:
            continue
        verb = f"-> `{change.new_key}`" if change.new_key else "(removed, no replacement key found)"
        breaks.append({
            "producer_file": change.file,
            "producer_function": change.function,
            "old_key": change.old_key,
            "new_key": change.new_key,
            "change_type": change.change_type,
            "consumers": consumers[:_MAX_CONSUMERS_PER_BREAK],
            "consumer_count": len(consumers),
            "reason": (
                f"`{change.function}` in {change.file} changes the `{change.old_key}` key/field "
                f"{verb}, but {len(consumers)} location(s) elsewhere in the repository still read "
                f"`{change.old_key}` and were not part of this change."
            ),
        })

    function_changes = []
    for func in sorted(all_touched - functions_with_key_changes):
        producer_files = sorted({c.file for c in all_changes if c.function == func} |
                                {f.get("filename") for f in pr_files if f.get("filename")
                                 and _function_touches(f, func)})
        for pf in producer_files:
            consumers = find_function_consumers(func, repo_files, diff_paths)
            if consumers:
                function_changes.append({
                    "producer_file": pf,
                    "producer_function": func,
                    "consumers": consumers[:_MAX_CONSUMERS_PER_BREAK],
                    "consumer_count": len(consumers),
                    "reason": (
                        f"`{func}` in {pf} was modified by this change, and is called from "
                        f"{len(consumers)} location(s) elsewhere in the repository that were not "
                        f"part of this diff."
                    ),
                })
                break   # one producer citation per function is enough evidence
    return {"contract_breaks": breaks, "function_changes": function_changes}


def _function_touches(pr_file: dict, func_name: str) -> bool:
    """True if `func_name`'s section_header appears anywhere in this file's hunks — used only to
    attribute a `function_changes` entry back to the right producer file."""
    for hunk in _hunks(pr_file.get("patch") or "", pr_file.get("filename") or ""):
        if _function_name(getattr(hunk, "section_header", None)) == func_name:
            return True
    return False


# ------------------------------------------------------------- snapshot-only (no-diff) checks
# `build_contract_breaks` above needs a DIFF: it finds what a PR's producer changed and whether
# a consumer elsewhere still expects the old shape. Mind Map's whole-codebase review
# (coverage.review_code_coverage, driven by main.py's _codeanalysis_worker) has no diff at
# all — it only ever sees the CURRENT snapshot of the repo, with no "before" to compare
# against. The benchmark evidence (see WARDENIQ_CROSS_FILE_BEFORE_AFTER.md) shows Mind Map's
# failure on this exact bug was different in kind from the diff-based tools': both the
# producer file (tokens.py) and the consumer file (middleware.py) WERE already in the evidence
# the LLM reviewed, yet it still failed to connect a key that stopped being written to a
# read-site that still expects it. `find_orphaned_contract_reads` below is a second,
# independent, snapshot-only signal that does not need a diff: a `.get(KEY, ...)` read whose
# KEY is written by NOTHING anywhere in the current codebase is inherently suspicious — its
# fallback/None path is taken unconditionally, every time — regardless of whether that
# happened via a rename, a removal, or a typo.
import difflib  # noqa: E402  (kept local to this section; stdlib only)

_EXTERNAL_RECEIVER_RX = re.compile(
    r"(?:os\.environ|environ|getenv|headers|cookies|query_params|"
    r"request\.args|request\.form|request\.GET|request\.POST|\.meta)\s*$",
    re.IGNORECASE)

_DICT_GET_RX = re.compile(r"([A-Za-z_][\w\.]*)\.get\(\s*['\"]([A-Za-z_][\w-]*)['\"]")


def find_orphaned_contract_reads(repo_files: list[dict]) -> list[dict]:
    """Snapshot-only companion to `build_contract_breaks`, for callers with no diff to work from.

    Finds `.get(KEY, ...)` / `.get(KEY)` read sites whose KEY is never WRITTEN anywhere in the
    current repo snapshot. Deliberately narrow, to bound false positives:
      * only `.get(...)` reads — a bracket-subscript read (`claims["role"]`) raises loudly on a
        missing key, so it fails fast and is not the silent-regression class this targets;
      * excludes receivers that are obviously EXTERNAL to this codebase's own producers
        (environment variables, HTTP headers/cookies/query-args/getenv) — those keys are
        supplied by the environment or the caller, not by any function in this repo, so "no
        local writer" is the expected, unremarkable case for them, not a defect;
      * excludes GENERIC_KEYS (the same structural-noise list `build_contract_breaks` uses) and
        anything shorter than 3 characters.

    Returns a list shaped exactly like a `build_contract_breaks` "contract_break" entry
    (`old_key`/`new_key`/`change_type`/`consumers`/`reason`) — `change_type` is
    `"orphaned_read"`, `producer_file`/`producer_function` are `None` since, by construction,
    no producer was found — so every existing caller
    (`grounding.match_contract_breaks_to_cases`, coverage.py's evidence-block builder) can
    consume it with zero special-casing. `new_key` is left `None` — a same-repo fuzzy name
    match is offered only as a `suggested_replacement_key` (never asserted as a confirmed
    rename, since a snapshot alone cannot confirm one — only a diff can).
    """
    written: dict[str, set] = {}
    for rf in repo_files:
        path = rf.get("path") or rf.get("filename") or ""
        if not path or is_test_file(path):
            continue
        text = rf.get("text") or ""
        for key, kinds in extract_key_writes_from_lines(text.splitlines()).items():
            if "dict" in kinds:
                written.setdefault(key, set()).add(path)

    findings: dict[str, list] = {}
    for rf in repo_files:
        path = rf.get("path") or rf.get("filename") or ""
        if not path or is_test_file(path):
            continue
        text = rf.get("text") or ""
        for i, line in enumerate(text.splitlines(), start=1):
            for m in _DICT_GET_RX.finditer(line):
                receiver, key = m.group(1), m.group(2)
                if key.lower() in GENERIC_KEYS or len(key) < 3:
                    continue
                if _EXTERNAL_RECEIVER_RX.search(receiver):
                    continue
                if key in written:
                    continue
                findings.setdefault(key, []).append({
                    "file": path, "line": i, "snippet": line.strip()[:160],
                    "function": _enclosing_function_in_text(text, i),
                })

    all_written_keys = sorted(written)
    out = []
    for key, consumers in findings.items():
        close = difflib.get_close_matches(key, all_written_keys, n=1, cutoff=0.6)
        suggestion = close[0] if close else None
        if suggestion:
            where = ", ".join(sorted(written.get(suggestion, []))[:2])
            hint = (f"; the most similarly-named key currently written anywhere in the repo "
                    f"is `{suggestion}` (in {where}) — possible rename target")
        else:
            hint = " and no similarly-named key is written anywhere in the repo either"
        out.append({
            "producer_file": None, "producer_function": None,
            "old_key": key, "new_key": None, "suggested_replacement_key": suggestion,
            "change_type": "orphaned_read",
            "consumers": consumers[:_MAX_CONSUMERS_PER_BREAK],
            "consumer_count": len(consumers),
            "reason": (
                f"`{key}` is read via `.get(...)` at {len(consumers)} location(s) in the "
                f"repository, but no code anywhere in the current snapshot ever WRITES that "
                f"key — its fallback/None path is taken unconditionally, every time{hint}. "
                f"This can indicate a producer was renamed or removed without updating this "
                f"consumer."
            ),
        })
    return out
