"""PR → feature mapping, LLM coverage review, version diff, and test-code generation."""
import json
import re

import httpx

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

# Heuristic: which changed files look like developer-authored tests.
TEST_FILE_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|e2e|cypress)/|"
    r"(test_|_test|\.test\.|\.spec\.)|"
    r"(Test|Tests|IT|Spec)\.(java|kt|cs|go|rb)$",
    re.IGNORECASE,
)


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path or ""))


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
    """Map a PR to a feature via the Epic it belongs to. Returns
    (feature_id|None, confidence, method).

    A PR carries an Epic key or a ticket key in its TITLE or BODY. Features are
    bound 1:1 to Epics (feature.key == epic key). Resolution, per key found:
      1. If the key is itself an Epic bound to a feature -> map (method 'epic').
      2. Else treat it as a ticket, resolve its parent Epic via Jira, and map to
         the feature bound to that Epic (method 'ticket->epic').
    No semantic/embedding fallback: if nothing resolves, the PR is left unmapped
    (a miss is preferred over a wrong guess)."""
    keys = extract_keys(pr.get("title", ""), pr.get("body", ""))
    if not keys:
        return None, 0.0, "unmapped"
    # 1) any key that is directly an Epic bound to a feature
    for key in keys:
        fid = store.feature_by_epic(project_id, key)
        if fid:
            return fid, 1.0, f"epic:{key}"
    # 2) treat each key as a ticket, resolve its parent Epic via Jira
    if jira is not None and getattr(jira, "ok", lambda: False)():
        for key in keys:
            epic = jira.parent_epic(key)
            if epic and epic != key:
                fid = store.feature_by_epic(project_id, epic)
                if fid:
                    return fid, 1.0, f"ticket:{key}->epic:{epic}"
    return None, 0.0, "unmapped"


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


def _code_excerpt_block(code_excerpts, max_total=16000, max_per=900) -> str:
    parts, used = [], 0
    for c in code_excerpts[:20]:
        block = f"// FILE {c.get('repo','')}:{c.get('path','')}\n{(c.get('text','') or '')[:max_per]}"
        add = ("\n\n" if parts else "") + block
        if used + len(add) > max_total:
            break
        parts.append(block)
        used += len(add)
    return "\n\n".join(parts)


def review_code_coverage(llm, feature_name, requirement, cases, code_excerpts, batch_size=10) -> dict:
    """LLM external-reviewer pass: map actual code to a feature's test cases.

    Cases are judged in small BATCHES (so a large feature isn't crammed into one call, which
    caused the model to under-cover). Prompt is strict: 'covered' requires the specific behaviour
    to be visibly implemented in the excerpts AND a cited file — otherwise it's downgraded, so the
    model can't hallucinate coverage it can't point to.
    """
    code = _code_excerpt_block(code_excerpts)
    valid = {c["id"]: c for c in cases}
    seen, out, errored = set(), [], False
    for i in range(0, len(cases), batch_size):
        batch = cases[i:i + batch_size]
        briefs = [{"id": c["id"], "title": c["title"], "type": c["type"],
                   "steps": c.get("steps", [])[:6]} for c in batch]
        prompt = (
            f"FEATURE: {feature_name}\n\nREQUIREMENT (truncated):\n{(requirement or '')[:2000]}\n\n"
            f"RELEVANT PRODUCTION CODE (excerpts; test/spec files excluded):\n{code}\n\n"
            f"TEST CASES TO JUDGE ({len(briefs)}):\n{json.dumps(briefs)[:5000]}\n\n"
            "For EACH case, decide from the PRODUCTION code ABOVE only:\n"
            "- 'covered' = the code clearly implements the SPECIFIC behaviour and you can name the exact file/function.\n"
            "- 'partial' = the relevant area exists but the specific behaviour is only partly handled.\n"
            "- 'uncovered' = the behaviour is absent, OR its implementing code is not in the excerpts above.\n"
            "Do NOT assume code you cannot see; do NOT mark covered because a test could exist. "
            "For 'covered' or 'partial' you MUST cite the implementing file(s).\n"
            "Return JSON: {\"cases\":[{\"test_case_id\":\"<id>\",\"status\":\"covered|partial|uncovered\","
            "\"rationale\":\"short, reference the code\",\"files\":[\"repo:path\"]}]}."
        )
        try:
            data = llm.chat_json(_CODEREV_SYS, prompt, temperature=0.1)
        except Exception:  # noqa: BLE001
            errored = True
            continue
        for x in data.get("cases", []):
            if not (isinstance(x, dict) and x.get("test_case_id") in valid):
                continue
            cid = x["test_case_id"]
            if cid in seen:
                continue
            seen.add(cid)
            st = x.get("status") if x.get("status") in ("covered", "partial", "uncovered") else "uncovered"
            files = [str(f)[:160] for f in (x.get("files") or [])][:6]
            if st == "covered" and not files:   # covered with nothing to point at → not trustworthy
                st = "partial"
            out.append({"test_case_id": cid, "display_id": valid[cid].get("display_id"),
                        "title": valid[cid]["title"], "type": valid[cid]["type"], "status": st,
                        "rationale": str(x.get("rationale", ""))[:300], "files": files})
    for cid, c in valid.items():           # anything the model didn't return → uncovered
        if cid not in seen:
            out.append({"test_case_id": cid, "display_id": c.get("display_id"),
                        "title": c["title"], "type": c["type"],
                        "status": "uncovered", "rationale": "not addressed by reviewed code", "files": []})
    res = {"cases": out}
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


def verify_pr_implementation(llm, pr, prod_files, cases, batch_size=10) -> dict:
    """LLM verifier: which test cases does this PR's PRODUCTION code actually IMPLEMENT?

    Judged in batches. Strict: merely touching the same endpoint/file is NOT enough for
    'covered' — the specific behaviour must be implemented in the diff. Returns
    {"covered":[{test_case_id,status:covered|partial,confidence:0-1,rationale}]}.
    """
    diff = "\n".join(f"{f['filename']} ({f['status']}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})\n"
                     f"{f.get('patch', '')}" for f in prod_files[:25])[:6000]
    valid = {c["id"] for c in cases}
    out, seen, errored = [], set(), False
    for i in range(0, len(cases), batch_size):
        batch = cases[i:i + batch_size]
        briefs = [{"id": c["id"], "title": c["title"], "type": c["type"],
                   "steps": c.get("steps", [])[:6]} for c in batch]
        prompt = (
            f"PULL REQUEST #{pr.get('number')}: {pr.get('title', '')}\n\n"
            f"CHANGED PRODUCTION CODE (diff; test/spec files excluded):\n{diff}\n\n"
            f"TEST CASES TO JUDGE ({len(briefs)}):\n{json.dumps(briefs)[:5000]}\n\n"
            "For each case, judge whether THIS diff's PRODUCTION code IMPLEMENTS the SPECIFIC behaviour:\n"
            "- 'covered' = the changed code clearly implements this exact behaviour.\n"
            "- 'partial' = the diff touches the relevant area but does not fully implement this behaviour.\n"
            "Omit a case entirely if the diff does not implement or touch it. IMPORTANT: touching the same "
            "endpoint/route/function is NOT enough for 'covered' — the case's specific behaviour must be "
            "implemented in the diff, otherwise use 'partial' or omit.\n"
            "Return JSON: {\"covered\":[{\"test_case_id\":\"<id>\",\"status\":\"covered|partial\","
            "\"confidence\":0.0-1.0,\"rationale\":\"short\"}]}."
        )
        try:
            data = llm.chat_json(_PRIMPL_SYS, prompt, temperature=0.1)
        except Exception:  # noqa: BLE001
            errored = True
            continue
        for x in data.get("covered", []):
            if isinstance(x, dict) and x.get("test_case_id") in valid and x["test_case_id"] not in seen:
                seen.add(x["test_case_id"])
                st = x.get("status") if x.get("status") in ("covered", "partial") else "partial"
                out.append({"test_case_id": x["test_case_id"], "status": st,
                            "confidence": float(x.get("confidence", 0.0) or 0.0),
                            "rationale": str(x.get("rationale", ""))[:300]})
    res = {"covered": out}
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
    out = []
    for x in data.get("impacted", []):
        if isinstance(x, dict) and x.get("test_case_id") in valid:
            out.append({"test_case_id": x["test_case_id"], "reason": str(x.get("reason", ""))[:300],
                        "risk": x.get("risk", "medium")})
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
    covered = []
    for c in data.get("covered", []):
        if isinstance(c, dict) and c.get("test_case_id") in valid_ids:
            covered.append({"test_case_id": c["test_case_id"],
                            "status": c.get("status", "covered"),
                            "by_dev_test": bool(c.get("by_dev_test")),
                            "rationale": str(c.get("rationale", ""))[:300]})
    return {"covered": covered, "dev_test_files": dev_test_files,
            "confidence": float(data.get("confidence", 0.0) or 0.0)}


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
