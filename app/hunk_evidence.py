"""Numbered diff hunks as the evidence for a PR-coverage verdict (#249 follow-up).

Why this exists. PR coverage asks a model "does this pull request implement this test
case?". Three things made the answer unreliable, and none of them is about one model:

  * The model was shown only the FIRST 6,000 characters of the diff. A 1,200-line PR was
    judged on about 12% of its code (the config and package files that sort first), and the
    route file that actually decides the answer was never in front of the model.
  * "covered" was the model's word. Its citation was checked only as "a file that exists in
    the diff", and the symbols it mentioned were looked up anywhere in that whole file.
  * A test written for `GET /api/v2/search` was matched to a pull request that implements
    `GET /api/v1/search`, because the matching looked at function names.

What every model CAN do is read a short numbered excerpt and point at a number. So the
PROGRAM splits the diff into numbered hunks ([H1] [H2] ...), picks the hunks that look
related to the cases being judged (so a big PR is not judged on its first few files), and a
verdict must cite the numbers of the hunks that show the behaviour. The program then checks
the verdict against the hunks it cites, by plain text comparison, with no model call:

  * a verdict that cites no real hunk cannot be "covered";
  * if the cited hunks share almost nothing with the test case, the claim is dropped;
  * if the test case names an endpoint, the pull request must define that endpoint, and one
    that only differs by API version (v1 vs v2) is a different endpoint.

Everything here is a pure function of the diff and the test cases, so the same numbering is
used to build the prompt and to check the answer.
"""
import math
import re

MAX_HUNK_CHARS = 1400          # a longer hunk is cut at a line into several numbered hunks
MAX_HUNKS = 400
PROMPT_HUNK_BUDGET = 9000      # characters of hunk text shown for one batch of cases
HUNKS_PER_CASE = 3             # best-matching hunks offered per case
MAX_CITED_HUNKS = 3
MIN_SUPPORT_COVERED = 0.4      # share of the case's distinctive words found in the cited hunks
MIN_SUPPORT_PARTIAL = 0.2

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")
_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_WORD = re.compile(r"[a-z0-9]+")
_HUNK_ID = re.compile(r"[Hh]?\s*(\d+)")
_VERSION_SEGMENT = re.compile(r"^v\d+$", re.IGNORECASE)

# Words that say nothing about WHICH behaviour a test case or a code hunk is about.
_GENERIC = frozenset("""
the and for with that this when then given should must will can not are was has have from
into only also each both over after before still able same does done been being they them
their there these those any all its but you your would could may might than less more
user users request requests response responses status return returns returned valid invalid
test tests case cases api endpoint call called calls field value values data error errors
page button check verify ensure result results success successful request body header
headers true false null none undefined const let var function async await import export
default type string number boolean object array new get set
""".split())


_SUFFIXES = ("ations", "ation", "ings", "ing", "ions", "ion", "ed", "es", "s")


def _stem(word: str) -> str:
    """A crude stem, applied the same way to test-case text and to code, so that English
    and identifiers meet: suggestions/suggest, filtering/filter, caching/cache, queries/query.
    It only has to be consistent, not correct English."""
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[:-len(suffix)]
            break
    if word.endswith("e") and len(word) > 4:
        word = word[:-1]
    return word


def code_words(text: str) -> set:
    """Lowercase words of a text or of code: camelCase, snake_case and paths are split,
    stemmed, filler dropped. 'searchProducts' gives {'search', 'product'}. Tokens with
    digits ('100ms', 'v2') are left out: they say nothing about which behaviour it is."""
    words = set()
    for word in _WORD.findall(_CAMEL.sub(r"\1 \2", str(text or "")).lower()):
        if len(word) < 3 or word in _GENERIC or any(ch.isdigit() for ch in word):
            continue
        words.add(_stem(word))
    return words


# ------------------------------------------------------------------ numbered hunks
def split_hunks(files, max_chars: int = MAX_HUNK_CHARS, max_hunks: int = MAX_HUNKS) -> list[dict]:
    """The production diff as numbered hunks, in file order.

    Each hunk: {"id": "H3", "file": path, "start": first new-file line, "end": last,
    "text": the hunk as shown (diff markers kept), "code": its added and unchanged lines
    (what the code is AFTER the change; removed lines implement nothing)}.
    A hunk longer than `max_chars` is cut at a line so that no single number covers a
    whole file."""
    from coverage import is_non_implementation_file   # lazy: coverage imports this module
    hunks = []

    def flush(path, start, end, body):
        if not body or len(hunks) >= max_hunks:
            return
        code = "\n".join(line[1:] if line[:1] in "+ " else line for line in body if not line.startswith("-"))
        hunks.append({"id": f"H{len(hunks) + 1}", "file": path, "start": start, "end": max(start, end),
                      "text": "\n".join(body), "code": code})

    for f in files or []:
        path, patch = f.get("filename"), f.get("patch") or ""
        if not path or not patch.strip():
            continue
        # Seed data, config, type declarations and tests implement nothing; a verdict that
        # cites them is discarded anyway (coverage._ground_verdict), so do not offer them.
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+"))
        if is_non_implementation_file(path, added):
            continue
        line_no, start, body, size = 0, 0, [], 0
        for raw in patch.splitlines():
            header = _HUNK_HEADER.match(raw)
            if header:
                flush(path, start, line_no - 1, body)
                line_no, start, body, size = int(header.group(1)), int(header.group(1)), [raw], len(raw)
                continue
            if not body:               # text before the first @@ (a file header): not code
                continue
            if size + len(raw) > max_chars and len(body) > 1:
                flush(path, start, line_no - 1, body)
                start, body, size = line_no, [], 0
            body.append(raw)
            size += len(raw) + 1
            if not raw.startswith("-"):
                line_no += 1
        flush(path, start, line_no - 1, body)
    return hunks


def _case_text(case: dict) -> str:
    steps = case.get("steps") or []
    parts = [str(case.get("title") or "")]
    for step in steps:
        parts.append(f"{step.get('action', '')} {step.get('expected', '')}" if isinstance(step, dict) else str(step))
    return " ".join(parts)


def case_words(case: dict) -> set:
    return code_words(_case_text(case))


def distinctive_words(case: dict, document_frequency: dict, n_cases: int) -> set:
    """The words of a test case that tell it apart from the other cases of the feature.
    A word in more than half of a large suite ('search' in a search feature) does not."""
    words = case_words(case)
    if n_cases < 4:
        return words
    limit = max(1, n_cases // 2)
    return {word for word in words if document_frequency.get(word, 0) <= limit}


def document_frequency(cases: list) -> dict:
    df: dict = {}
    for case in cases:
        for word in case_words(case):
            df[word] = df.get(word, 0) + 1
    return df


ROUTE_BOOST = 25.0


def _aligned_paths(case: dict, endpoints: list) -> set:
    """Paths of the PR's routes that are the endpoint(s) a test case names."""
    import grounding
    case_eps = grounding.case_endpoints(case)
    return {e["path"] for e in endpoints or []
            if any(grounding.endpoints_align(c, e) in ("exact", "path") for c in case_eps)}


def select_hunks(hunks: list, cases: list, budget: int = PROMPT_HUNK_BUDGET,
                 per_case: int = HUNKS_PER_CASE, endpoints: list | None = None) -> list:
    """The hunks to show for one batch of cases: for each case its best-matching hunks, best
    first, taking turns between the cases until the character budget is used. A word that is
    rare among the hunks counts for more than one that is in most of them. A big PR is
    therefore judged on the code that matches the cases, not on whichever files sort first."""
    if not hunks or not cases:
        return []
    hunk_words = [code_words(h["file"] + " " + h["code"]) for h in hunks]
    df: dict = {}
    for words in hunk_words:
        for word in words:
            df[word] = df.get(word, 0) + 1
    weight = {word: math.log(1 + len(hunks) / count) for word, count in df.items()}
    ranked = []
    for case in cases:
        words = case_words(case)
        paths = _aligned_paths(case, endpoints)
        # The hunk that defines the route a case names is the best evidence there is.
        scores = [(sum(weight[w] for w in words & hw)
                   + (ROUTE_BOOST if any(p in hunks[i]["code"] for p in paths) else 0.0), i)
                  for i, hw in enumerate(hunk_words)]
        ranked.append([i for score, i in sorted(scores, key=lambda t: (-t[0], t[1])) if score > 0][:per_case])
    chosen, used = [], 0
    for turn in range(per_case):
        for order in ranked:
            if turn >= len(order) or order[turn] in chosen:
                continue
            size = len(hunks[order[turn]]["text"]) + 60
            if used + size > budget and chosen:
                continue
            chosen.append(order[turn])
            used += size
    return [hunks[i] for i in sorted(chosen)]


def render_hunks(hunks: list) -> str:
    if not hunks:
        return "CHANGED CODE: no changed code looks related to these test cases."
    blocks = [f"[{h['id']}] {h['file']} (new lines {h['start']}-{h['end']})\n{h['text']}" for h in hunks]
    return "CHANGED CODE, as numbered hunks (cite these numbers):\n" + "\n\n".join(blocks)


# ------------------------------------------------------------------ endpoints
def diff_endpoints(files) -> list:
    """HTTP routes this pull request defines (method + path), read from its added lines."""
    import grounding
    out = []
    for f in files or []:
        if f.get("filename") and f.get("patch"):
            out.extend(grounding.extract_endpoints(f["patch"], f["filename"]))
    # `app.use("/api", router)` mounts a router; it is a prefix, not an endpoint.
    return [e for e in out if not (e.get("method") == "ANY" and len([s for s in e["path"].split("/") if s]) <= 1)]


def _unversioned(path: str) -> list:
    return [s.lower() for s in (path or "").split("?")[0].split("/") if s and not _VERSION_SEGMENT.match(s)]


def endpoint_status(case: dict, endpoints: list) -> str:
    """How the pull request's routes relate to the endpoint(s) a test case names:

      'aligned'   the PR defines it;
      'conflict'  the PR defines the same endpoint under another API version (case: /v2/search,
                  PR: /v1/search): a different endpoint, so the case is not implemented here;
      'absent'    the PR defines routes, none of them this one;
      'unknown'   the case names no endpoint, or the diff has no routes we can read."""
    import grounding
    case_eps = grounding.case_endpoints(case)
    if not case_eps or not endpoints:
        return "unknown"
    if any(grounding.endpoints_align(c, e) in ("exact", "path") for c in case_eps for e in endpoints):
        return "aligned"
    for c in case_eps:
        for e in endpoints:
            if c.get("method") not in (None, "ANY", e.get("method")) and e.get("method") != "ANY":
                continue
            a, b = _unversioned(c.get("path")), _unversioned(e.get("path"))
            short, long_ = (a, b) if len(a) <= len(b) else (b, a)
            versions_differ = [s for s in (c.get("path") or "").lower().split("/") if _VERSION_SEGMENT.match(s)] != \
                              [s for s in (e.get("path") or "").lower().split("/") if _VERSION_SEGMENT.match(s)]
            if short and long_[-len(short):] == short and versions_differ:
                return "conflict"
    return "absent"


def cites_route(case: dict, endpoints: list, cited: list) -> bool:
    """True when a cited hunk contains the route the test case names, as the PR defines it
    (the case says `GET /api/v2/search`, the cited hunk has `"/v2/search"`). Naming the
    case's own route is the strongest evidence a hunk can offer for an endpoint case, and
    it does not depend on the case's wording matching the code's."""
    return any(path in hunk["code"] for path in _aligned_paths(case, endpoints) for hunk in cited)


# ------------------------------------------------------------------ citations
def cited_hunks(item: dict, by_id: dict) -> tuple[list, list]:
    """(the cited hunks that exist, cited ids that do not). The model may write ["H3"], "H3,H7",
    3 or "h3"; at most MAX_CITED_HUNKS distinct citations count."""
    raw = item.get("hunks")
    parts = raw if isinstance(raw, (list, tuple)) else [raw]
    ids = []
    for part in parts:
        ids.extend(f"H{n}" for n in _HUNK_ID.findall(str(part or "")))
    ids = list(dict.fromkeys(ids))[:MAX_CITED_HUNKS]
    return [by_id[i] for i in ids if i in by_id], [i for i in ids if i not in by_id]


_RANK = {None: 0, "partial": 1, "covered": 2}


def verify_verdict(case: dict, status: str, cited: list, endpoint: str, df: dict, n_cases: int,
                   route_hit: bool = False) -> dict:
    """Hold one model verdict to the hunks it cites.

    `status` is what the model said ('covered' or 'partial'); `cited` the real hunks it
    cited; `endpoint` the endpoint_status(); `df`/`n_cases` describe the whole suite (see
    distinctive_words); `route_hit` whether a cited hunk contains the case's own route.
    Returns {"status": 'covered' | 'partial' | None (claim dropped), "notes": [...],
    "support": share of the case's words found in the cited code, or None}.
    The result is never stronger than the model's own status."""
    final, notes, support = status, [], None
    if endpoint == "conflict":
        return {"status": None, "support": None,
                "notes": ["the test case names an endpoint that this PR defines under another API version"]}
    if not cited:
        # Nothing to check the claim against: never 'covered'. A 'partial' stays visible
        # (flagged for review) rather than vanishing, as before.
        notes.append("no changed hunk cited")
        final = "partial"
    else:
        words = case_words(case)
        distinctive = distinctive_words(case, df, n_cases)
        cited_words = set()
        for hunk in cited:
            cited_words |= code_words(hunk["file"] + " " + hunk["code"])
        if words and not route_hit:
            support = len(words & cited_words) / len(words)
            # Two gates. Too little in common overall, or none of the words that set this
            # case apart from the others: the hunks are about something else.
            if support < MIN_SUPPORT_PARTIAL or (distinctive and not distinctive & cited_words):
                return {"status": None, "support": round(support, 2),
                        "notes": ["the cited hunks share almost nothing with the test case"]}
            if support < MIN_SUPPORT_COVERED and final == "covered":
                final = "partial"
                notes.append("the cited hunks cover too little of what the test case describes")
    if endpoint == "absent" and final == "covered":
        final = "partial"
        notes.append("the test case names an endpoint that this PR does not define")
    if _RANK[final] > _RANK[status]:
        final = status
    return {"status": final, "notes": notes, "support": None if support is None else round(support, 2)}
