"""PR/MR code-coverage ingestion + the "code_coverage" manual-run job.

Moved out of main.py (Phase 3 of REFACTOR_PLAN.md). This groups `ingest_pr`
(the shared PR-ingestion pipeline: register the PR, map it to a feature,
fetch changed files, run grounded+LLM coverage) and its helpers together with
the "code_coverage" job worker, since the worker is just a thin manual-trigger
wrapper around `ingest_pr`.

`ingest_pr` / `_fetch_pr_and_files` / `ingest_pr_tracked` / `_pr_coverage` are
also called from code that stays in main.py for now (the GitHub/GitLab
webhook route handlers, and `sync_repo` — the polling loop, a Phase 4
background/poller.py concern) — main.py re-imports them back from this
module (see the `from workers.code_coverage_worker import (...)` block there)
rather than duplicating them, exactly the same cross-import pattern already
used for workers/repo_scan_worker.py's helpers.

`jira_client` was moved to core/deps.py in this same phase (a documented
deviation, alongside `_oid`) specifically so `ingest_pr` could depend on it
without main.py needing to be imported back into this module — that would
create a main.py <-> workers.code_coverage_worker circular import.
"""
import time

import github
import gitlab as gitlab_mod
import coverage as cov
import grounding

from core.config import GITHUB_API
from core.deps import (
    _fetch_repo_snapshot_files, _oid, current_llm, jira_client,
    project_github_token, project_gitlab_token,
)
from core.state import SYNC, store  # noqa: F401  (bare name-imports are safe:
                                     # both are mutated in place, never rebound)

from workers.registry import JOB_WORKERS, run_tracked


def _pr_coverage(pr_id, pr_doc, files, fid):
    """Grounded + implementation-verified PR coverage for one mapped PR.

    Implementation coverage (does the PR's PRODUCTION code build each case?) is computed by the
    grounded tiers first (endpoint/symbol with file:line evidence), then an implementation-focused
    LLM verify on the remainder. Automation (dev-test) signal is tracked separately. Test-only PRs
    are flagged and get no implementation-coverage number.
    """
    cases = store.cases_brief(store.feature_test_case_ids(fid))
    prod, test_files, infra = grounding.classify_diff_files(files)
    dev_test_files = test_files
    if not cases:
        store.save_coverage(pr_id, fid, [], dev_test_files, 0.0)
        return {"covered": [], "dev_test_files": dev_test_files, "confidence": 0.0, "notice": ""}
    if grounding.is_test_only(files):
        store.save_coverage(pr_id, fid, [], dev_test_files, 0.0, notice="test_only_pr")
        return {"covered": [], "dev_test_files": dev_test_files, "confidence": 0.0, "notice": "test_only_pr"}

    prod_set = set(prod)
    prod_files = [f for f in files if f["filename"] in prod_set]
    pseudo = [{"repo": pr_doc.get("repo_full_name"), "sha": str(pr_doc.get("number")),
               "url": pr_doc.get("url"), "message": pr_doc.get("title", ""), "files": prod_files}]
    # Cross-file dependency evidence (contracts.py): fetch the rest of the repo at the PR's
    # head branch so a producer/consumer contract break can be found even when the consumer
    # is a file this PR's own diff never touched. Best-effort — see
    # _fetch_repo_snapshot_files; a fetch failure (no PAT, network error, etc.) silently
    # degrades to the original diff-only behaviour rather than failing this PR's coverage run.
    repo_files = []
    repo_doc = store.get_repo(pr_doc["repo_id"]) if pr_doc.get("repo_id") else None
    if repo_doc:
        repo_files = _fetch_repo_snapshot_files(repo_doc, pr_doc.get("head_ref") or "")
    # Grounding gives SCOPE (which cases the PR touches, with file:line evidence) — NOT a verdict.
    gm = grounding.match_commit_changes(pseudo, cases, repo_files=repo_files)
    # The LLM decides the actual verdict over ALL cases: does the diff IMPLEMENT the behaviour?
    llm_v = {}
    if prod_files:
        res = cov.verify_pr_implementation(current_llm(), pr_doc, prod_files, cases,
                                           repo_files=repo_files)
        llm_v = {x["test_case_id"]: x for x in res.get("covered", [])}
    by_id = {c["id"]: c for c in cases}
    covered = []
    for cid in by_id:
        m = gm["matches"].get(cid)     # grounded scope hit (endpoint/symbol) or None
        v = llm_v.get(cid)             # LLM verdict or None
        if v and v.get("status") == "covered":
            status = "covered"          # only the LLM confirming implementation earns "covered"
        elif m or (v and v.get("status") == "partial"):
            status = "partial"          # in scope (code touched) but implementation not confirmed
        else:
            continue                    # neither touched nor implemented → not covered
        covered.append({
            "test_case_id": cid, "status": status,
            "tier": (m.get("tier") if m else 5),
            "confidence": (v.get("confidence") if v else (m.get("confidence") if m else None)),
            "signal_type": (m.get("signal_type") if m else "ai"),
            "signal": (m.get("signal") if m else None),
            "evidence": (m.get("evidence") if m else []),
            "rationale": (v.get("rationale") if v else
                          "PR changes touch code relevant to this case; specific implementation not confirmed"),
            "by_dev_test": False})
    dev_ids = grounding.dev_tested_cases(dev_test_files, cases)
    for c in covered:
        if c["test_case_id"] in dev_ids:
            c["by_dev_test"] = True
    overall = max([c["confidence"] for c in covered if c.get("confidence") is not None], default=0.0)
    store.save_coverage(pr_id, fid, covered, dev_test_files, overall)
    return {"covered": covered, "dev_test_files": dev_test_files, "confidence": overall, "notice": ""}


def _gitlab_mr_to_pr_shape(mr: dict, changes: dict) -> tuple[dict, list]:
    """Translate a GitLab MR + changes payload into the GitHub-PR-ish dict and
    file list that the rest of ingest_pr already understands."""
    iid = mr.get("iid") or 0
    pseudo_pr = {
        "number": iid,
        "title": mr.get("title") or "",
        "body": mr.get("description") or "",
        "user": {"login": (mr.get("author") or {}).get("username") or ""},
        "head": {"ref": mr.get("source_branch") or "",
                 "sha": mr.get("sha") or mr.get("last_commit_sha") or ""},
        "state": "merged" if mr.get("merged_at") else (mr.get("state") or "opened"),
        "html_url": mr.get("web_url") or "",
        "updated_at": mr.get("updated_at") or "",
        "merged_at": mr.get("merged_at"),
    }
    files = []
    for ch in (changes.get("changes") or [])[:50]:
        path = ch.get("new_path") or ch.get("old_path") or ""
        if not path:
            continue
        status = ("added" if ch.get("new_file") else
                  "removed" if ch.get("deleted_file") else
                  "renamed" if ch.get("renamed_file") else
                  "modified")
        diff = (ch.get("diff") or "")[:1500]
        adds = sum(1 for ln in diff.splitlines()
                   if ln.startswith("+") and not ln.startswith("+++"))
        dels = sum(1 for ln in diff.splitlines()
                   if ln.startswith("-") and not ln.startswith("---"))
        files.append({"filename": path, "status": status,
                      "additions": adds, "deletions": dels, "patch": diff})
    return pseudo_pr, files


def _fetch_pr_and_files(repo: dict, pr_number: int) -> tuple[dict, list, str]:
    """Provider-aware fetch. Returns (pr_dict, files, head_sha)."""
    provider = (repo.get("git_provider") or "github").lower()
    pid = repo.get("project_id")
    if provider == "gitlab":
        token = project_gitlab_token(pid)
        if not token:
            raise RuntimeError("no GitLab PAT configured for this project")
        client = gitlab_mod.GitLab(token)
        mr = client.get_mr(repo["full_name"], pr_number)
        changes = client.get_mr_changes(repo["full_name"], pr_number)
        pr, files = _gitlab_mr_to_pr_shape(mr, changes)
        return pr, files, (pr.get("head") or {}).get("sha", "")
    # GitHub default
    token = project_github_token(pid)
    if not token:
        raise RuntimeError("no GitHub PAT configured for this project")
    client = github.GitHub(token, GITHUB_API)
    pr = client.get_pull(repo["owner"], repo["name"], pr_number)
    files = client.get_pull_files(repo["owner"], repo["name"], pr_number)
    return pr, files, (pr.get("head") or {}).get("sha", "")


def ingest_pr(repo: dict, pr: dict, feature_id_override: str | None = None):
    """Fetch a PR's files, store it, auto-map to a feature (unless overridden),
    review coverage, and persist a `code_coverage_runs` row.

    When `feature_id_override` is provided (manual run from a specific feature
    page), we PIN the run to that feature and skip the LLM/heuristic mapping —
    so the run shows up on the feature the user was on, every time."""
    owner, name = repo["owner"], repo["name"]
    number = pr["number"]
    provider = (repo.get("git_provider") or "github").lower()
    head_sha = ""
    head = pr.get("head") or {}
    if isinstance(head, dict):
        head_sha = head.get("sha", "") or ""
    head_ref = (pr.get("head") or {}).get("ref", "") if isinstance(pr.get("head"), dict) else pr.get("head_ref", "")

    # ---- Phase 1: register the PR + a RUNNING coverage row UP FRONT -----------
    # Done before fetching files / running the LLM (the slow parts) so the UI
    # shows "gap analysis running" the moment the webhook lands. Mapping only
    # needs the PR title/body, which the webhook payload already carries.
    base_doc = {
        "project_id": repo["project_id"], "repo_id": repo["id"],
        "repo_full_name": repo["full_name"], "number": number,
        "title": pr.get("title"), "author": (pr.get("user") or {}).get("login"),
        "head_ref": head_ref, "state": "merged" if pr.get("merged_at") else pr.get("state"),
        "url": pr.get("html_url"), "body": pr.get("body"),
        "updated_at": pr.get("updated_at"), "merged_at": pr.get("merged_at"),
    }
    pr_id = store.upsert_pr(base_doc)
    SYNC["ingested"] += 1

    # Manual runs from a specific feature page pin to that feature; otherwise
    # preserve an existing manual assignment before falling back to auto-map.
    if feature_id_override:
        fid, score, method = feature_id_override, 1.0, "manual"
    else:
        prev = store.prs.find_one({"_id": _oid(pr_id)},
                                  {"mapping_method": 1, "feature_id": 1, "mapping_confidence": 1})
        if prev and prev.get("mapping_method") == "manual" and prev.get("feature_id"):
            fid, score, method = prev["feature_id"], prev.get("mapping_confidence", 1.0), "manual"
        else:
            fid, score, method = cov.map_pr_to_feature(
                store, jira_client(), base_doc, repo["project_id"])
    store.set_pr_mapping(pr_id, fid, score, method)

    feature = store.get_feature(fid) if fid else None
    version = (feature or {}).get("version", 1) if feature else None
    run_id = store.create_code_coverage_run({
        "project_id": repo["project_id"],
        "feature_id": fid,
        "feature_version": version,
        "pr_id": pr_id,
        "repo_id": repo["id"],
        "repo_full_name": repo["full_name"],
        "git_provider": repo.get("git_provider", "github"),
        "pr_number": number,
        "pr_title": pr.get("title", ""),
        "pr_branch": head_ref,
        "pr_url": pr.get("html_url"),
        "head_sha": head_sha,
        "source": "webhook",
        "confidence": method,
        "mapping_score": score,
        "status": "running",
    })

    # ---- Phase 2: fetch changed files (slow / network) ------------------------
    files = pr.get("_files")  # caller may pre-fetch (provider dispatch)
    if files is None:
        try:
            if provider == "gitlab":
                fetched_pr, files, fetched_head_sha = _fetch_pr_and_files(repo, number)
                head_sha = fetched_head_sha or head_sha
                if fetched_pr:
                    pr = {**fetched_pr, **pr}
            else:
                token = project_github_token(repo.get("project_id"))
                files = github.GitHub(token, GITHUB_API).get_pull_files(owner, name, number)
        except Exception as e:  # noqa: BLE001
            files = []
            SYNC["errors"].append(f"{repo['full_name']}#{number} files: {e}")
    if files is None:
        files = []

    # Enrich the PR row now that files (and, for GitLab, richer PR data) exist.
    head_ref = (pr.get("head") or {}).get("ref", "") if isinstance(pr.get("head"), dict) else pr.get("head_ref", head_ref)
    doc = {
        **base_doc,
        "title": pr.get("title"), "head_ref": head_ref,
        "state": "merged" if pr.get("merged_at") else pr.get("state"),
        "url": pr.get("html_url"), "body": pr.get("body"),
        "changed_files": [f["filename"] for f in files],
        "additions": sum(f["additions"] for f in files),
        "deletions": sum(f["deletions"] for f in files),
        "updated_at": pr.get("updated_at"), "merged_at": pr.get("merged_at"),
    }
    store.upsert_pr(doc)

    # Providers whose webhook payload lacked title/body (e.g. GitLab) may have
    # missed the provisional mapping; re-map now that the PR is enriched and move
    # the (already-visible) running row onto the resolved feature.
    if not feature_id_override and method != "manual" and not fid:
        fid, score, method = cov.map_pr_to_feature(store, jira_client(), doc, repo["project_id"])
        if fid:
            store.set_pr_mapping(pr_id, fid, score, method)
            feature = store.get_feature(fid)
            version = (feature or {}).get("version", 1) if feature else None
            store.update_code_coverage_run(run_id, feature_id=fid, feature_version=version,
                                           confidence=method, mapping_score=score,
                                           head_sha=head_sha)
        else:
            store.update_code_coverage_run(run_id, head_sha=head_sha)
    elif head_sha:
        store.update_code_coverage_run(run_id, head_sha=head_sha)

    if fid:
        SYNC["mapped"] += 1
        cases = store.cases_brief(store.feature_test_case_ids(fid))
        if cases:
            try:
                result = _pr_coverage(pr_id, doc, files, fid)
                tests_covered = len([c for c in result.get("covered", [])
                                     if c.get("status") in ("covered", "partial")])

                # Cross-version comparison vs the previous done run on this feature.
                prev = store.previous_done_run_for_feature(fid, exclude_id=run_id)
                comparison = cov.diff_runs(prev, result.get("covered", []))

                # Code changes that didn't map to any covered/partial test case.
                unmapped = cov.compute_unmapped_changes(files, result.get("covered", []))

                store.update_code_coverage_run(run_id,
                    status="done",
                    completed_at=time.time(),
                    tests_total=len(cases),
                    tests_covered=tests_covered,
                    gaps_found=max(0, len(cases) - tests_covered),
                    result={"covered": result.get("covered", []),
                            "dev_test_files": result.get("dev_test_files", []),
                            "confidence": result.get("confidence", 0.0),
                            "notice": result.get("notice", ""),
                            "changed_files": [f["filename"] for f in files][:50],
                            "comparison": comparison,
                            "unmapped_changes": unmapped})
            except Exception as e:  # noqa: BLE001
                store.update_code_coverage_run(run_id, status="failed",
                                               error=str(e)[:300],
                                               completed_at=time.time())
        else:
            store.update_code_coverage_run(run_id, status="done",
                                           completed_at=time.time(),
                                           tests_total=0, tests_covered=0,
                                           result={"no_cases": True})
    else:
        store.update_code_coverage_run(run_id, status="done",
                                       completed_at=time.time(),
                                       tests_total=0, tests_covered=0,
                                       result={"unmatched": True,
                                               "mapping_score": score})
    # Coverage trend history (issue #45): a completed PR ingestion ("code
    # analysis") is one of the events worth a point-in-time snapshot.
    try:
        store.save_coverage_snapshot(repo["project_id"], "code_analysis",
                                     commit_sha=head_sha or None)
    except Exception as snap_e:  # noqa: BLE001
        print(f"[coverage-snapshot] skipped: {snap_e}", flush=True)
    return pr_id


def ingest_pr_tracked(repo, pr, feature_id_override=None):
    """``ingest_pr`` wrapped so its webhook/poller/sync-driven LLM + embedding
    cost is captured as a job in Usage & Cost. Use ONLY from non-job threads
    (the manual code_coverage worker already records via launch_job)."""
    num = (pr or {}).get("number")
    label = f"PR coverage · {repo.get('full_name', '')}#{num}"
    return run_tracked("pr_coverage",
                       lambda: ingest_pr(repo, pr, feature_id_override),
                       label=label, project_id=repo.get("project_id"))


def _code_coverage_worker(jid, params):
    """Manual PR/MR coverage run, provider-aware. Dispatches GitHub vs GitLab
    by repo.git_provider so a GitLab MR doesn't hit the GitHub API."""
    repo_id = params["repo_id"]
    pr_number = int(params["pr_number"])
    store.update_job_progress(jid, "Fetching PR…", 10)
    repo = store.get_repo(repo_id)
    if not repo:
        store.update_job(jid, status="failed", stage="error", error="repo not found")
        return
    try:
        pr, files, _sha = _fetch_pr_and_files(repo, pr_number)
    except Exception as e:  # noqa: BLE001
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return
    pr["_files"] = files     # avoid re-fetching in ingest_pr
    store.update_job_progress(jid, "Running LLM coverage…", 40)
    # PIN to the user's chosen feature on manual runs.
    pr_id = ingest_pr(repo, pr, feature_id_override=params.get("feature_id"))
    store.update_job_progress(jid, "Persisting…", 90)
    store.merge_job_result(jid, pr_id=pr_id, repo_full_name=repo["full_name"])


JOB_WORKERS["code_coverage"] = _code_coverage_worker
