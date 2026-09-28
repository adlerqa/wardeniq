"""Code coverage: feature-level coverage report, PR-to-feature "Gap Analysis"
code-coverage runs (list/detail/reassign/manual-trigger/exclude), automation
coverage (test-repo-scan-derived), test-repo rescan/reset-stuck-scan, Mind Map
code analysis + project mindmap view, change-impact analysis + commit-analysis,
and manual PR-to-feature mapping (analyze-pr / unmapped-prs / assign-pr).

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 16/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

``exclude_pr``, ``unmapped_prs``, and ``assign_pr`` were deliberately left in
main.py when api/routes/repos_prs.py was extracted (router 8/20) because they
depend on ``_pr_coverage``/``_fetch_pr_and_files``/``ingest_pr``/``run_tracked`` —
private helpers belonging to this domain. They land here now, alongside those
helpers' other consumers.

This was almost entirely one contiguous block in main.py (only
``feature_coverage`` sat slightly apart, separated by the not-yet-extracted
system.py routes). No new shared-helper deviation was needed: everything this
router depends on (store, launch_job/run_tracked, the code_coverage_worker
helpers, and the RBAC helpers) was already centralized in earlier phases.
"""
import re
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import automation as auto_cov

from core.deps import _ext_error, _implementation_repo_docs, _is_app_repo, _oid, gh_client
from core.logging_setup import get_logger
from core.security import (
    _require_code_coverage_run_project, _require_commit_analysis_project, _require_project,
)
from core.state import store
from workers.registry import launch_job, run_tracked
from workers.code_coverage_worker import _fetch_pr_and_files, _pr_coverage, ingest_pr

# Phase 3 (REFACTOR_PLAN.md): the "codeanalysis" (Mind Map) job now lives in
# app/workers/codeanalysis_worker.py. Importing it is required even though
# nothing here binds a name from it: the import itself is what runs
# `JOB_WORKERS["codeanalysis"] = _codeanalysis_worker` as a side effect.
from workers import codeanalysis_worker  # noqa: F401

log = get_logger("code_coverage")

router = APIRouter()


@router.get("/api/features/{fid}/coverage")
def feature_coverage(fid: str):
    rep = store.feature_coverage_report(fid)
    f = store.get_feature(fid)
    snap = store.get_automation_coverage(fid, version=(f or {}).get("version", 1)) or {}
    total = rep.get("total_test_cases", 0) or 0
    covered = rep.get("covered", 0) or 0
    code_pct = rep.get("coverage_pct", 0)
    # Holistic view: a case is covered once ANY linked PR implements it (union).
    # QA-readiness is a per-feature strategy (PM/Lead defined, stored on the
    # feature): "ready for manual testing" once CODE coverage meets the threshold.
    _thr = (f or {}).get("ready_threshold")
    threshold = int(_thr) if _thr is not None else 80
    rep["summary"] = {
        "total_cases": total,
        "code_pct": code_pct,
        "covered_cases": covered,
        "automation_pct": snap.get("coverage_pct", 0),
        "automated_cases": snap.get("covered_count", 0),
        "ready_threshold": threshold,
        "ready": bool(total and code_pct >= threshold),
    }
    return rep


def _decorate_coverage_run(r: dict) -> dict:
    """Add needs_rerun + commit_url, hydrate covered case titles + comparison."""
    if not r:
        return r
    fid = r.get("feature_id")
    if fid:
        feature = store.get_feature(fid)
        if feature:
            run_done = r.get("completed_at") or r.get("created_at") or 0
            r["needs_rerun"] = bool(feature.get("updated_at") and
                                    feature["updated_at"] > run_done)
            r["feature_name"] = feature.get("name", "")
    r["commit_url"] = auto_cov.build_commit_url(
        r.get("git_provider", "github"),
        r.get("repo_full_name", ""),
        r.get("head_sha", "")) if r.get("head_sha") else ""
    return r


def _hydrate_case_titles(ids: list) -> dict:
    """Bulk-resolve {case_id: {title,type,display_id}} for a list of ids."""
    from bson import ObjectId as _OID
    valid = [_OID(i) for i in ids if i and _OID.is_valid(i)]
    out = {}
    if not valid:
        return out
    for case in store.cases.find({"_id": {"$in": valid}},
                                 {"title": 1, "type": 1, "display_id": 1,
                                  "priority": 1, "step_ids": 1}):
        out[str(case["_id"])] = {"title": case.get("title", ""),
                                  "type": case.get("type", ""),
                                  "display_id": case.get("display_id", ""),
                                  "priority": case.get("priority", "P2"),
                                  "steps": store.resolve_steps(case.get("step_ids", []))}
    return out


# --- Gap Analysis: PR Code Coverage ------------------------------------------
@router.get("/api/features/{fid}/code-coverage/runs")
def list_feature_code_coverage_runs(fid: str, limit: int = 50):
    runs = store.list_code_coverage_runs(feature_id=fid, limit=limit)
    feature = store.get_feature(fid)
    feat_updated = (feature or {}).get("updated_at", 0)
    excluded_keys = store.excluded_pr_run_keys(fid)
    for r in runs:
        run_done = r.get("completed_at") or r.get("created_at") or 0
        r["needs_rerun"] = bool(feat_updated and feat_updated > run_done)
        r["excluded"] = (r.get("repo_id"), str(r.get("pr_number"))) in excluded_keys
    return {"runs": runs}


@router.get("/api/code-coverage/runs/{rid}")
def get_code_coverage_run_detail(rid: str, request: Request):
    r = _require_code_coverage_run_project(request, rid)
    result = r.get("result") or {}
    covered = result.get("covered") or []

    # Hydrate covered cases titles
    if covered:
        all_ids = [c.get("test_case_id") for c in covered if c.get("test_case_id")]
        titles = _hydrate_case_titles(all_ids)
        result["covered"] = [{**c, **titles.get(c.get("test_case_id"), {})}
                              for c in covered]

    # Hydrate comparison id → title pairs so the UI can render with context.
    comparison = result.get("comparison") or {}
    if comparison:
        diff_ids = list(comparison.get("newly_covered") or []) + \
                   list(comparison.get("no_longer_covered") or [])
        diff_titles = _hydrate_case_titles(diff_ids)
        comparison["newly_covered_detail"] = [
            {"id": i, **diff_titles.get(i, {})}
            for i in (comparison.get("newly_covered") or [])]
        comparison["no_longer_covered_detail"] = [
            {"id": i, **diff_titles.get(i, {})}
            for i in (comparison.get("no_longer_covered") or [])]
        result["comparison"] = comparison

    # Include the full case list for the feature so the UI can render BOTH
    # covered (Done) and missing (Missing) per type — matching Node's view.
    feature_cases = []
    fid = r.get("feature_id")
    if fid:
        try:
            case_ids = store.feature_test_case_ids(fid)
            from bson import ObjectId as _OID
            valid = [_OID(i) for i in case_ids if i and _OID.is_valid(i)]
            for c in store.cases.find({"_id": {"$in": valid}},
                                       {"title": 1, "type": 1, "display_id": 1,
                                        "priority": 1, "step_ids": 1}):
                feature_cases.append({
                    "id": str(c["_id"]),
                    "title": c.get("title", ""),
                    "type": c.get("type", "other"),
                    "display_id": c.get("display_id", ""),
                    "priority": c.get("priority", "P2"),
                    "steps": store.resolve_steps(c.get("step_ids", [])),
                })
        except Exception:  # noqa: BLE001
            pass
    r["feature_cases"] = feature_cases

    r["result"] = result
    return _decorate_coverage_run(r)


class ReassignIn(BaseModel):
    feature_id: str


@router.post("/api/code-coverage/runs/{rid}/reassign")
def reassign_code_coverage_run(rid: str, body: ReassignIn):
    """Manually override the auto-resolved feature for a PR run, and re-run
    coverage against the chosen feature's current version (sticky binding)."""
    run = store.get_code_coverage_run(rid)
    if not run:
        raise HTTPException(404, "run not found")
    feature = store.get_feature(body.feature_id)
    if not feature:
        raise HTTPException(404, "feature not found")
    store.update_code_coverage_run(rid, feature_id=body.feature_id,
                                   feature_version=feature.get("version", 1),
                                   confidence="manual")
    if not run.get("repo_id") or not run.get("pr_number"):
        raise HTTPException(400, "run is missing repo_id / pr_number — cannot re-run")
    jid = launch_job("code_coverage", {
        "repo_id": run["repo_id"], "pr_number": int(run["pr_number"]),
        "feature_id": body.feature_id},
        label=f"Coverage · reassign to {feature.get('name')}",
        project_id=run.get("project_id"), feature_id=body.feature_id)
    return {"ok": True, "job_id": jid}


class ExcludePrIn(BaseModel):
    excluded: bool = True


@router.post("/api/prs/{pr_id}/exclude")
def exclude_pr(pr_id: str, body: ExcludePrIn):
    """Exclude (or re-include) a PR from a feature's Gap Analysis coverage.

    Excluded PRs stay visible in the Gap Analysis list (flagged) but no longer
    contribute to the feature's aggregate code coverage — lets a QA lead drop
    an outdated/junk PR and have coverage recompute immediately."""
    res = store.set_pr_excluded(pr_id, body.excluded)
    if res is None:
        raise HTTPException(404, "PR not found")
    return res


_GH_PR_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", re.IGNORECASE)
_GL_MR_RE = re.compile(r"gitlab\.com/(.+?)/-/merge_requests/(\d+)", re.IGNORECASE)


def parse_pr_url(url: str) -> dict | None:
    """Returns {repo_full_name, number, provider} or None if not a PR/MR URL."""
    if not url:
        return None
    url = url.strip()
    m = _GH_PR_RE.search(url)
    if m:
        return {"provider": "github", "repo_full_name": m.group(1),
                "number": int(m.group(2))}
    m = _GL_MR_RE.search(url)
    if m:
        return {"provider": "gitlab", "repo_full_name": m.group(1),
                "number": int(m.group(2))}
    return None


class ManualCovIn(BaseModel):
    feature_id: str
    # Accept either an explicit repo_id+pr_number OR a PR/MR URL.
    repo_id: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None


@router.post("/api/code-coverage/runs/manual")
def manual_code_coverage(body: ManualCovIn):
    """Manually run PR code coverage. Accepts either:
       - {feature_id, repo_id, pr_number}, OR
       - {feature_id, pr_url}  with a github.com/.../pull/N or
                                gitlab.com/.../-/merge_requests/N URL.
    The URL form looks up the connected repo on this project by full_name."""
    feature = store.get_feature(body.feature_id)
    if not feature:
        raise HTTPException(404, "feature not found")
    pid = feature.get("project_id")

    repo_id = body.repo_id
    pr_number = body.pr_number

    if body.pr_url:
        parsed = parse_pr_url(body.pr_url)
        if not parsed:
            raise HTTPException(400, "URL must be a GitHub PR or GitLab MR link")
        pr_number = parsed["number"]
        # Find a connected repo on this project that matches the URL.
        candidates = [r for r in store.list_repos(pid)
                      if r.get("full_name") == parsed["repo_full_name"]
                      and r.get("git_provider") == parsed["provider"]]
        if not candidates:
            raise HTTPException(
                400,
                f"repository '{parsed['repo_full_name']}' "
                f"is not connected to this project — connect it first")
        repo_id = candidates[0]["id"]

    if not repo_id or not pr_number:
        raise HTTPException(400, "provide pr_url or (repo_id + pr_number)")

    repo = store.get_repo(repo_id)
    if not repo:
        raise HTTPException(404, "repo not found")
    jid = launch_job("code_coverage", {
        "repo_id": repo_id, "pr_number": pr_number,
        "feature_id": body.feature_id},
        label=f"Coverage · {repo.get('full_name')} #{pr_number}",
        project_id=repo.get("project_id"), feature_id=body.feature_id)
    return {"job_id": jid, "repo_full_name": repo.get("full_name"),
            "pr_number": pr_number}


# --- Gap Analysis: Automation Coverage ---------------------------------------
@router.get("/api/features/{fid}/automation-coverage")
def get_feature_automation_coverage(fid: str):
    feature = store.get_feature(fid)
    if not feature:
        raise HTTPException(404, "feature not found")
    snapshot = store.get_automation_coverage(fid, version=feature.get("version", 1))
    if not snapshot:
        # Surface the current state even when no scan has run yet, so the UI
        # can render "no test repo connected / rescan to begin" guidance.
        test_repos = store.repos_for_project(feature["project_id"], repo_type="test")
        return {
            "feature_id": fid,
            "total_generated": len(store.feature_test_case_ids(fid)),
            "covered_count": 0,
            "missing_count": len(store.feature_test_case_ids(fid)),
            "coverage_pct": 0.0,
            "items": [],
            "scan_status": "never",
            "test_repos": [{
                "id": r["id"], "full_name": r["full_name"],
                "scan_status": r.get("scan_status", "never"),
                "scan_files_found": r.get("scan_files_found", 0),
                "scan_cases_count": r.get("scan_cases_count", 0),
                "scan_error": r.get("scan_error", ""),
                "last_scan_at": r.get("last_scan_at"),
            } for r in test_repos],
        }
    snapshot["id"] = str(snapshot.pop("_id"))
    test_repos = store.repos_for_project(feature["project_id"], repo_type="test")
    snapshot["test_repos"] = [{
        "id": r["id"], "full_name": r["full_name"],
        "scan_status": r.get("scan_status", "never"),
        "scan_files_found": r.get("scan_files_found", 0),
        "scan_cases_count": r.get("scan_cases_count", 0),
        "scan_error": r.get("scan_error", ""),
        "last_scan_at": r.get("last_scan_at"),
    } for r in test_repos]
    return snapshot


@router.post("/api/projects/{pid}/repos/{rid}/rescan")
def rescan_test_repo(pid: str, rid: str, feature_id: str | None = None):
    repo = store.get_repo(rid)
    if not repo or repo.get("project_id") != pid:
        raise HTTPException(404, "repo not found in this project")
    if repo.get("repo_type") != "test":
        raise HTTPException(400, "rescan only applies to test repos")
    # If a scan is already running we surface that instead of stacking jobs.
    if repo.get("scan_status") == "running":
        return {"already_running": True, "repo_id": rid}
    params = {"repo_id": rid}
    if feature_id:
        params["feature_id"] = feature_id
    jid = launch_job("test_repo_scan", params,
                     label=f"Rescan · {repo.get('full_name')}",
                     project_id=pid, feature_id=feature_id)
    return {"job_id": jid, "status": "running"}


@router.post("/api/projects/{pid}/repos/{rid}/scan/reset")
def reset_stuck_scan(pid: str, rid: str):
    """Force-clear a stuck `running` scan_status so the user can retry."""
    repo = store.get_repo(rid)
    if not repo or repo.get("project_id") != pid:
        raise HTTPException(404, "repo not found in this project")
    if repo.get("scan_status") != "running":
        return {"ok": True, "was_running": False}
    store.set_repo_scan_status(rid, "failed",
                               scan_error="manually reset — previous scan was stuck")
    return {"ok": True, "was_running": True}


class CodeAnalyzeIn(BaseModel):
    project_id: str
    repo_ids: list[str] = []          # empty → all repos in the project
    branches: dict[str, str] = {}     # {repo_id: branch}; missing → repo's default
    branch: str = ""                  # legacy global override (applied if no per-repo branch)
    # Re-fetch and re-index even when the branch head is unchanged. Needed after the
    # test/spec exclusion rules change: cached chunks were filtered by the OLD rules, so
    # spec files already in the index keep being retrieved (and keep eating the excerpt
    # budget) until something forces a rebuild.
    force_reindex: bool = False


@router.post("/api/code-analysis")
def code_analysis(body: CodeAnalyzeIn, request: Request):
    _require_project(request, body.project_id)
    repos = _implementation_repo_docs(body.project_id, body.repo_ids)
    if not repos:
        raise HTTPException(404, "no implementation repos to analyze")
    jid = launch_job("codeanalysis", {"project_id": body.project_id, "repo_ids": body.repo_ids,
                                      "branches": body.branches, "branch": body.branch.strip(),
                                      "force_reindex": body.force_reindex},
                     label=f"Mind Map — {len(repos)} repo(s)",
                     project_id=body.project_id)
    return {"job_id": jid}


@router.get("/api/features/{fid}/code-coverage")
def feature_code_coverage(fid: str):
    return store.get_code_coverage(fid) or {"feature_id": fid, "result": {"cases": []},
                                            "repos": [], "analyzed": False}


@router.get("/api/projects/{pid}/mindmap")
def project_mindmap(pid: str):
    out = []
    for f in store.list_features(pid):
        cc = store.get_code_coverage(f["id"])
        cases = (cc or {}).get("result", {}).get("cases", [])
        counts = {"covered": 0, "partial": 0, "uncovered": 0}
        for c in cases:
            counts[c.get("status", "uncovered")] = counts.get(c.get("status", "uncovered"), 0) + 1
        out.append({"feature": f["name"], "feature_id": f["id"], "version": f.get("version", 1),
                    "case_count": f.get("case_count", len(cases)), "counts": counts,
                    "cases": cases, "repos": (cc or {}).get("repos", []),
                    "reviewed_files": (cc or {}).get("result", {}).get("reviewed_files", []),
                    "analyzed": bool(cc), "updated_at": (cc or {}).get("updated_at")})
    return {"project_id": pid, "features": out}


class AnalyzeIn(BaseModel):
    project_id: str
    repo_ids: list[str] = []          # empty → all repos in the project
    branches: dict[str, str] = {}     # {repo_id: branch}; missing → repo's default
    days: int = Field(14, ge=1, le=180)  # matches the UI's declared Lookback bounds
    feature_id: str | None = None     # optional: scope impact to one feature's cases


@router.post("/api/analyze")
def analyze(body: AnalyzeIn, request: Request):
    _require_project(request, body.project_id)
    repos = _implementation_repo_docs(body.project_id, body.repo_ids)
    if not repos:
        raise HTTPException(404, "no implementation repos to analyze")
    jid = launch_job("analyze", {"project_id": body.project_id, "repo_ids": body.repo_ids,
                                 "branches": body.branches, "days": body.days,
                                 "feature_id": body.feature_id},
                     label=f"Change impact analysis — {len(repos)} repo(s), {body.days}d",
                     project_id=body.project_id)
    return {"job_id": jid}


@router.get("/api/commit-analysis/{run_id}")
def get_commit_analysis(run_id: str, request: Request):
    return _require_commit_analysis_project(request, run_id)


@router.get("/api/projects/{pid}/commit-analysis/latest")
def latest_commit_analysis(pid: str, feature_id: str | None = None):
    return store.latest_commit_analysis(pid, feature_id) or {"results": [], "commits": []}


class AnalyzePRIn(BaseModel):
    repo_id: str
    number: int


@router.post("/api/analyze-pr")
def analyze_pr(body: AnalyzePRIn):
    """Fetch a specific PR, map it to a feature, review which test cases it covers."""
    repo = store.repos.find_one({"_id": _oid(body.repo_id)})
    if not repo:
        raise HTTPException(404, "repo not found")
    if not _is_app_repo(repo):
        raise HTTPException(400, "PR coverage only applies to implementation repos; test repos are used for automation coverage")
    repo = {**repo, "id": str(repo["_id"])}
    try:
        pr, files, _sha = _fetch_pr_and_files(repo, body.number)
        pr["_files"] = files
    except Exception as e:  # noqa: BLE001
        provider = (repo.get("git_provider") or "github").lower()
        raise _ext_error(provider, e)
    pr_id = ingest_pr(repo, pr)                 # stores PR + mapping + coverage
    pdoc = store.prs.find_one({"_id": _oid(pr_id)})
    fid = pdoc.get("feature_id") if pdoc else None
    feature = store.get_feature(fid) if fid else None
    covdoc = store.coverage.find_one({"pr_id": pr_id}) or {}
    covered = []
    for c in covdoc.get("covered", []):
        case = store.cases.find_one({"_id": _oid(c["test_case_id"])}, {"title": 1, "type": 1})
        if case:
            covered.append({"title": case.get("title"), "type": case.get("type"),
                            "status": c.get("status", "covered"), "tier": c.get("tier"),
                            "confidence": c.get("confidence"), "signal_type": c.get("signal_type"),
                            "signal": c.get("signal"), "evidence": c.get("evidence", []),
                            "rationale": c.get("rationale", ""), "by_dev_test": c.get("by_dev_test")})
    return {"pr": {"number": pdoc.get("number"), "title": pdoc.get("title"), "url": pdoc.get("url"),
                   "repo": repo["full_name"]},
            "feature": {"id": fid, "name": feature.get("name") if feature else None,
                        "mapping": pdoc.get("mapping_method")},
            "notice": covdoc.get("notice", ""),
            "dev_test_files": covdoc.get("dev_test_files", []),
            "covered": covered}


class AssignPRIn(BaseModel):
    feature_id: str


@router.get("/api/projects/{pid}/unmapped-prs")
def unmapped_prs(pid: str):
    return {"prs": store.list_unmapped_prs(pid)}


@router.post("/api/prs/{pr_id}/assign")
def assign_pr(pr_id: str, body: AssignPRIn):
    """Manually map an unmatched PR to a feature, then compute its coverage in the background.

    Mapping is persisted immediately (so the PR leaves the unmapped queue at once); the coverage
    pass — which may call the LLM and take a while — runs in a daemon thread so the UI stays snappy.
    """
    p = store.prs.find_one({"_id": _oid(pr_id)})
    if not p:
        raise HTTPException(404, "PR not found")
    store.set_pr_mapping(pr_id, body.feature_id, 1.0, "manual")
    repo = store.repos.find_one({"_id": _oid(p["repo_id"])}) if p.get("repo_id") else None
    pdoc = {**p, "id": pr_id}

    def _bg():
        files = []
        if repo:
            try:
                provider = (repo.get("git_provider") or "github").lower()
                if provider == "gitlab":
                    _, files, _ = _fetch_pr_and_files({**repo, "id": str(repo["_id"])}, p["number"])
                else:
                    files = gh_client().get_pull_files(repo["owner"], repo["name"], p["number"])
            except Exception:  # noqa: BLE001
                files = []
        try:
            run_tracked(
                "pr_coverage",
                lambda: _pr_coverage(pr_id, pdoc, files, body.feature_id),
                label=f"PR coverage · assign #{p.get('number')}",
                project_id=(repo or {}).get("project_id"),
                feature_id=body.feature_id)
        except Exception as e:  # noqa: BLE001
            log.warning("[assign] coverage failed for PR %s: %s", pr_id, e)

    threading.Thread(target=_bg, daemon=True).start()
    return {"ok": True, "feature_id": body.feature_id, "status": "computing"}
