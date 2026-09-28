
import os
import re
import time

from core import state
from core.config import (
    GITHUB_API, GITLAB_BASE_URL, IMPORT_SEMANTIC_MATCH, IMPORT_SEMANTIC_THRESHOLD, STEP_AUTO,
)
from core.deps import current_llm, project_github_token, project_gitlab_token
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                               # mutated, never rebound)
import automation as auto_cov
import github
import sheet_import as sheet_mod

from workers.registry import JOB_WORKERS


def _test_repo_scan_worker(jid, params):
    """Scan a connected test repo, extract test titles, run hybrid matching
    against generated cases.

    Params:
      repo_id (required)       — which test repo to scan
      feature_id (optional)    — when set, only match for this feature (used by
                                 the auto-trigger after generate)
      project_features (bool)  — when set False, skip the matching loop entirely
    """
    repo_id = params["repo_id"]
    scoped_fid = params.get("feature_id")
    store.update_job_progress(jid, "Loading repo…", 5)
    repo = store.get_repo(repo_id)
    if not repo:
        store.update_job(jid, status="failed", stage="error", error="repo not found")
        return
    pid = repo["project_id"]
    provider = repo.get("git_provider", "github")
    if repo.get("repo_type") != "test":
        store.update_job(jid, status="failed", stage="error",
                         error="rescan only applies to test repos")
        return
    store.set_repo_scan_status(repo_id, "running", scan_error="")

    try:
        token = (project_gitlab_token(pid) if provider == "gitlab"
                 else project_github_token(pid))
        if not token:
            raise RuntimeError(f"no {provider} PAT configured for this project")
        store.update_job_progress(jid, "Downloading tarball…", 15)

        # Fetch tarball + remember the HEAD SHA we just scanned.
        default_branch = repo.get("default_branch") or "main"
        if provider == "github":
            client = github.GitHub(token, GITHUB_API)
            tar_bytes = client.get_archive(repo["owner"], repo["name"])
            # capture commit sha at head
            try:
                head = client.list_commits(repo["owner"], repo["name"],
                                           since_iso="1970-01-01T00:00:00Z",
                                           per_page=1, ref=default_branch)
                commit_sha = (head[0].get("sha") if head else "") or ""
            except Exception:  # noqa: BLE001
                commit_sha = ""
        else:
            # GitLab tarball endpoint
            import httpx as _httpx
            import urllib.parse as _up
            store.update_job_progress(jid, "Downloading GitLab archive…", 18)
            gitlab_api = f"{GITLAB_BASE_URL}/api/v4"
            url = (f"{gitlab_api}/projects/"
                   f"{_up.quote(repo['full_name'], safe='')}"
                   f"/repository/archive.tar.gz")
            r = _httpx.get(url, headers={"PRIVATE-TOKEN": token},
                           params={"sha": default_branch}, timeout=120.0,
                           follow_redirects=True)
            if r.status_code == 404:
                # Try the repo's default branch from /projects endpoint.
                try:
                    proj = _httpx.get(
                        f"{gitlab_api}/projects/"
                        f"{_up.quote(repo['full_name'], safe='')}",
                        headers={"PRIVATE-TOKEN": token}, timeout=30.0).json()
                    db = proj.get("default_branch") or "main"
                    if db != default_branch:
                        default_branch = db
                        r = _httpx.get(url, headers={"PRIVATE-TOKEN": token},
                                       params={"sha": default_branch},
                                       timeout=120.0, follow_redirects=True)
                except Exception:  # noqa: BLE001
                    pass
            r.raise_for_status()
            tar_bytes = r.content
            # Capture HEAD SHA for the chosen branch so commit links work.
            try:
                commits = _httpx.get(
                    f"{gitlab_api}/projects/"
                    f"{_up.quote(repo['full_name'], safe='')}/repository/commits",
                    headers={"PRIVATE-TOKEN": token},
                    params={"ref_name": default_branch, "per_page": 1},
                    timeout=30.0).json()
                commit_sha = (commits[0].get("id") if commits else "") or ""
            except Exception:  # noqa: BLE001
                commit_sha = ""
    except Exception as e:  # noqa: BLE001
        store.set_repo_scan_status(repo_id, "failed", scan_error=str(e)[:300])
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return

    # Anything past this point may take minutes and may call out to an LLM;
    # if it raises, we MUST flip scan_status off `running` so the user isn't
    # stuck. The whole block is wrapped in try/finally for that reason.
    scan_outcome = {"status": "failed", "error": "scan never completed"}
    files_seen = 0
    scanned = []
    matched_total = 0
    try:
        store.update_job_progress(jid, "Parsing test files…", 35)
        for rel, text in auto_cov.files_from_tarball(tar_bytes):
            files_seen += 1
            fw = auto_cov.detect_framework(rel, text)
            for t in auto_cov.extract_tests(rel, text, fw):
                scanned.append({
                    "id": f"trc:{repo_id}:{len(scanned)+1}",
                    "title": t["title"],
                    "file_path": rel,
                    "line": t.get("line") or 0,
                    "framework": fw,
                    "repo_id": repo_id,
                    "repo_full_name": repo["full_name"],
                    "git_provider": provider,
                    "default_branch": default_branch,
                    "commit_sha": commit_sha,
                })
        store.replace_test_repo_cases(pid, repo_id, scanned)
        print(f"[scan] {repo['full_name']}: {files_seen} files seen, "
              f"{len(scanned)} tests extracted", flush=True)

        store.update_job_progress(jid, "Matching to generated cases…", 60)
        all_features = store.list_features(project_id=pid)
        features = [f for f in all_features
                    if (not scoped_fid or f["id"] == scoped_fid)]
        llm = current_llm()
        all_scanned = store.list_test_repo_cases(project_id=pid)
        clean_scanned = [{**c, "id": c.get("id") or c.get("_id") or ""}
                         for c in all_scanned]
        for f_idx, f in enumerate(features):
            fid = f["id"]
            case_ids = store.feature_test_case_ids(fid)
            gen = store.cases_brief(case_ids)
            if not gen:
                continue

            def _prog(done, total, _fname=f.get("name", ""),
                      _fi=f_idx, _ftot=len(features)):
                base = 60 + (35 * _fi // max(1, _ftot))
                inc = (35 // max(1, _ftot)) * done // max(1, total)
                store.update_job_progress(
                    jid, f"Matching {_fname or 'feature'} · {done}/{total}",
                    min(95, base + inc))

            # Default to Jaccard-only matching to match Node's behavior +
            # eliminate any LLM-stall risk. Set AUTOMATION_USE_LLM=true on the
            # container to enable the slower, semantically-richer LLM verifier.
            use_llm = os.getenv("AUTOMATION_USE_LLM", "false").lower() == "true"
            try:
                matches = auto_cov.hybrid_match_generated_to_scanned(
                    llm, gen, clean_scanned, use_llm=use_llm,
                    progress_fn=_prog)
            except Exception as match_err:  # noqa: BLE001
                # Match failure on one feature must NOT kill the whole scan.
                print(f"[scan] match error on feature {f.get('name')}: "
                      f"{match_err}", flush=True)
                matches = [{"generated_id": g["id"], "match": None}
                           for g in gen]

            idx = {c["id"]: c for c in clean_scanned}
            covered_count = 0
            items = []
            for g, m in zip(gen, matches):
                mt = m.get("match")
                if mt:
                    covered_count += 1
                    sc = idx.get(mt["id"]) or {}
                    file_url = auto_cov.build_blob_url(
                        sc.get("git_provider", "github"),
                        sc.get("repo_full_name", ""),
                        sc.get("default_branch", "main"),
                        sc.get("file_path", ""),
                        sc.get("line") or None)
                    items.append({
                        "generated_id": g["id"],
                        "generated_title": g["title"],
                        "generated_type": g.get("type", ""),
                        "priority": g.get("priority"),
                        "display_id": g.get("display_id"),
                        "status": "covered",
                        "match": {**mt, "file_url": file_url,
                                  "repo_full_name": sc.get("repo_full_name", ""),
                                  "commit_sha": sc.get("commit_sha", ""),
                                  "line": sc.get("line") or 0}})
                else:
                    items.append({
                        "generated_id": g["id"],
                        "generated_title": g["title"],
                        "generated_type": g.get("type", ""),
                        "priority": g.get("priority"),
                        "display_id": g.get("display_id"),
                        "status": "missing",
                        "match": None})
            matched_total += covered_count
            store.save_automation_coverage(fid, pid, f.get("version", 1), {
                "total_generated": len(gen),
                "covered_count": covered_count,
                "missing_count": len(gen) - covered_count,
                "coverage_pct": (round(100 * covered_count / len(gen), 1)
                                  if gen else 0.0),
                "items": items,
                "scanned_repo_id": repo_id,
                "scanned_repo_full_name": repo["full_name"],
            })
        scan_outcome = {"status": "done", "error": ""}
    except Exception as scan_err:  # noqa: BLE001
        import traceback as _tb
        print(f"[scan] FATAL: {scan_err}\n{_tb.format_exc()}", flush=True)
        scan_outcome = {"status": "failed",
                        "error": f"{type(scan_err).__name__}: {scan_err}"[:300]}
    finally:
        # GUARANTEED status update — repo can never remain stuck "running".
        store.set_repo_scan_status(
            repo_id, scan_outcome["status"],
            scan_files_found=files_seen,
            scan_cases_count=len(scanned),
            scan_error=scan_outcome["error"],
            default_branch=default_branch,
            last_scan_at=time.time())
        store.merge_job_result(jid, files_seen=files_seen,
                               cases_extracted=len(scanned),
                               features_matched=matched_total,
                               scan_outcome=scan_outcome["status"])
        if scan_outcome["status"] == "failed":
            store.update_job(jid, status="failed", stage="error",
                             error=scan_outcome["error"])


JOB_WORKERS["test_repo_scan"] = _test_repo_scan_worker


# --------------------------------------------------------------- Import Sheet
def _create_imported_testcase(feature_id: str, row_dict: dict,
                                origin: str = "imported",
                                inherited_from: dict | None = None,
                                project_id: str | None = None,
                                project_imported_row_id: str | None = None,
                                identity_hash: str | None = None,
                                score: float | None = None) -> str:
    """Materialize a parsed sheet row into a wardenIQ test case + association.
    Returns the new case_id."""
    feature = store.get_feature(feature_id) or {}
    project_id = project_id or feature.get("project_id")
    identity_hash = identity_hash or row_dict.get("identity_hash")
    if not identity_hash:
        identity_hash = sheet_mod.identity_hash(row_dict)
    if project_id and identity_hash:
        existing = store.find_case_by_identity(project_id, identity_hash=identity_hash)
        if existing:
            store.associate(feature_id, existing["id"], origin, score)
            return existing["id"]

    title = row_dict.get("title") or "Imported test case"
    type_raw = (row_dict.get("category") or "").lower()
    case_type = "functional"
    for k, v in (("api", "api"), ("e2e", "e2e"), ("end-to-end", "e2e"),
                  ("ui", "ui"), ("edge", "nfr"), ("nfr", "nfr"),
                  ("functional", "functional"), ("business", "functional")):
        if k in type_raw:
            case_type = v
            break
    pri_norm = {"High": "P1", "Mid": "P2", "Low": "P3"}.get(
        row_dict.get("priority", "Mid"), "P2")
    pre = row_dict.get("preconditions") or ""
    raw_steps = row_dict.get("steps") or []
    expected = row_dict.get("expected_result") or ""
    step_pairs = []
    for i, raw_step in enumerate(raw_steps):
        if isinstance(raw_step, dict):
            action = raw_step.get("content") or raw_step.get("step") or ""
            exp = raw_step.get("expectedResult") or raw_step.get("expected_result") or ""
        else:
            action = str(raw_step or "")
            exp = ""
        if not exp and i == len(raw_steps) - 1 and expected:
            exp = expected
        if action:
            step_pairs.append({"action": action, "expected": exp})
    if not step_pairs:
        step_pairs = [{"action": title,
                        "expected": expected or "Behaviour observed as described"}]
    step_ids = []
    for s in step_pairs:
        emb = state.embedder.embed(f"{s['action']}. Expected: {s['expected']}")
        step_ids.append(store.get_or_create_step(s["action"], s["expected"],
                                                  emb, STEP_AUTO)["step_id"])
    cemb = state.embedder.embed(title + " " + " ".join(s["action"] for s in step_pairs))
    metadata = {
        "source_type": "manual_import",
        "identity_hash": identity_hash,
        "project_imported_row_id": project_imported_row_id,
        "inherited_from_feature_id": (inherited_from or {}).get("feature_id"),
    }
    cid = store.create_case(title, case_type, pri_norm, pre, step_ids,
                             row_dict.get("tags") or [], cemb, feature_id,
                             project_id=project_id,
                             identity_hash=identity_hash,
                             metadata=metadata)
    store.associate(feature_id, cid, origin, score)
    return cid


def _case_exists(case_id: str | None) -> bool:
    return store.case_exists(case_id)


def _promote_imported_row_to_feature(row_id: str, feature: dict, payload: dict,
                                      origin: str, score: float = 0.0,
                                      inherited_from: dict | None = None) -> str:
    """Link a canonical imported row to a feature, reusing a prior testcase."""
    feature_id = str(feature.get("id") or feature.get("_id"))
    project_id = feature.get("project_id")
    version = feature.get("version", 1)
    same_feature = store.get_row_promotion(row_id, feature_id)
    if same_feature and _case_exists(same_feature.get("promoted_testcase_id")):
        cid = same_feature["promoted_testcase_id"]
        store.associate(feature_id, cid, origin, score)
    else:
        prior = store.get_row_promotion(row_id)
        if prior and _case_exists(prior.get("promoted_testcase_id")):
            cid = prior["promoted_testcase_id"]
            store.associate(feature_id, cid, origin, score)
        else:
            cid = _create_imported_testcase(
                feature_id, payload, origin=origin,
                inherited_from=inherited_from, project_id=project_id,
                project_imported_row_id=row_id,
                identity_hash=payload.get("identity_hash") or sheet_mod.identity_hash(payload),
                score=score)
    store.link_row_to_feature(row_id, feature_id)
    store.record_row_promotion(row_id, project_id, feature_id, version, cid, score)
    return cid


def _parsed_row_from_payload(payload: dict) -> sheet_mod.ParsedRow:
    return sheet_mod.ParsedRow(
        sheet=payload.get("sheet", ""),
        row_number=payload.get("row_number", 0),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        intent=payload.get("intent", ""),
        category=payload.get("category"),
        suite=payload.get("suite", ""),
        priority=payload.get("priority", "Mid"),
        endpoint=payload.get("endpoint", ""),
        method=payload.get("method", ""),
        steps=payload.get("steps") or [],
        expected_result=payload.get("expected_result", ""),
        module=payload.get("module", ""),
        tags=payload.get("tags") or [],
        preconditions=payload.get("preconditions", ""),
        test_id=payload.get("test_id", ""),
        status=payload.get("status", ""),
    )


def _sheet_steps_preview(steps, limit: int = 4) -> list[str]:
    out = []
    for step in steps or []:
        if isinstance(step, dict):
            text = step.get("content") or step.get("step") or step.get("action") or ""
        else:
            text = str(step or "")
        text = " ".join(text.split())
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _feature_doc_for_import_context(feature: dict) -> dict:
    """Enrich feature scoring context from the stored unified context surface."""
    if not feature:
        return {}
    merged = dict(feature)
    feature_id = str(feature.get("id") or feature.get("_id") or "")
    version = feature.get("version", 1)
    try:
        unified = store.build_unified_context(feature_id, version) if feature_id else {}
    except Exception as exc:  # noqa: BLE001
        print(f"[import] unified context unavailable; using feature doc: {exc}", flush=True)
        unified = {}

    text_parts = [
        feature.get("text") or "",
        feature.get("summary") or "",
        unified.get("summaries", {}).get("prd") or "",
    ]
    for group in (unified.get("requirements") or {}).values():
        if isinstance(group, list):
            text_parts.extend(str(item) for item in group)
    business = unified.get("businessContext") or unified.get("business_context") or {}
    for key in ("userStories", "acceptanceCriteria", "assumptions", "risks", "requirements"):
        values = business.get(key) or []
        if isinstance(values, list):
            text_parts.extend(str(item) for item in values)
    technical = unified.get("technicalContext") or {}
    for section in ("prd", "hld", "lld"):
        block = technical.get(section) or {}
        text_parts.extend(str(item) for item in block.get("technicalLines") or [])
        text_parts.extend(str(item) for item in block.get("endpoints") or [])
    for chunk in (unified.get("rag") or {}).get("retrieved_chunks") or []:
        if isinstance(chunk, dict):
            text_parts.append(str(chunk.get("text") or ""))

    seen_text = set()
    merged_text = []
    for part in text_parts:
        compact = " ".join(str(part or "").split()).strip()
        if not compact:
            continue
        key = compact.lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        merged_text.append(compact)
    if merged_text:
        merged["text"] = "\n".join(merged_text)
    merged["description"] = (
        feature.get("description")
        or feature.get("summary")
        or unified.get("featureDescription")
        or ""
    )

    raw_api = []
    existing_api = feature.get("raw_api_spec") or unified.get("rawApiSpec") or []
    if isinstance(existing_api, list):
        raw_api.extend(ep for ep in existing_api if isinstance(ep, dict))
    endpoint_strings = []
    for section in ("prd", "hld", "lld"):
        block = technical.get(section) or {}
        endpoint_strings.extend(str(item) for item in block.get("endpoints") or [])
    for value in endpoint_strings:
        m = re.match(r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", value, re.I)
        if m:
            raw_api.append({"method": m.group(1).upper(), "path": m.group(2)})
        elif value.strip().startswith("/"):
            raw_api.append({"method": "", "path": value.strip()})
    if raw_api:
        deduped_api = []
        seen_api = set()
        for ep in raw_api:
            key = (str(ep.get("method") or "").upper(), str(ep.get("path") or "").lower())
            if not key[1] or key in seen_api:
                continue
            seen_api.add(key)
            deduped_api.append(ep)
        merged["raw_api_spec"] = deduped_api
    return merged


def _reuse_existing_import_rows(jid, feature_import_id: str, project_id: str,
                                feature_id: str, duplicate_of: str) -> None:
    """No-parse exact duplicate path: reuse canonical rows from old upload."""
    feature = store.get_feature(feature_id) or {}
    fi = store.get_feature_import(feature_import_id) or {}
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    import_batch_id = fi.get("import_batch_id") or feature_import_id
    rows = store.list_imported_rows_for_feature_import(duplicate_of)
    matched = 0
    stored = 0
    promoted_case_ids = []
    items = []
    store.update_job_progress(jid, "Reusing already uploaded sheet…", 35)
    for idx, r in enumerate(rows):
        payload = sheet_mod.normalize_imported_payload_shape(
            dict(r.get("normalized_payload") or {}))
        if not payload.get("title"):
            continue
        ihash = r.get("identity_hash") or payload.get("identity_hash") or sheet_mod.identity_hash(payload)
        payload["identity_hash"] = ihash
        row_obj = _parsed_row_from_payload(payload)
        result = sheet_mod.score_row(row_obj, ctx)
        store.add_imported_row_source(
            r["id"], feature_import_id, import_batch_id, feature_id,
            fi.get("original_filename", "") or payload.get("original_filename", ""),
            payload.get("sheet", "Sheet1"), payload.get("row_number", idx + 1))
        store.touch_imported_row_seen(
            r["id"],
            relevance_score=max(result.score, r.get("latest_relevance_score", 0) or 0),
            relevance_feature_id=feature_id)
        item = {
            "row_index": idx,
            "identity_hash": ihash,
            "project_imported_row_id": r["id"],
            "title": payload.get("title", ""),
            "category": payload.get("category"),
            "priority": payload.get("priority", "Mid"),
            "sheet": payload.get("sheet", ""),
            "row_number": payload.get("row_number", idx + 1),
            "endpoint": payload.get("endpoint", ""),
            "method": payload.get("method", ""),
            "steps_count": len(payload.get("steps") or []),
            "steps_preview": _sheet_steps_preview(payload.get("steps") or []),
            "expected_result": (payload.get("expected_result") or "")[:160],
            "score": result.score,
            "action": result.action,
            "breakdown": result.breakdown,
            "already_uploaded": True,
        }
        if result.action == "matched":
            cid = _promote_imported_row_to_feature(
                r["id"], feature, payload, origin="inherited",
                score=result.score,
                inherited_from={"feature_id": r.get("latest_relevance_feature_id")})
            item["promoted_testcase_id"] = cid
            promoted_case_ids.append(cid)
            matched += 1
        else:
            stored += 1
        items.append(item)
    store.update_feature_import(feature_import_id, row_count=len(items),
                                  accepted_count=matched, flagged_count=stored,
                                  rejected_count=0)
    store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                      f"Already uploaded · {matched} matched · {stored} stored",
                                      completed=True,
                                      result_json={"items": items,
                                                   "alreadyUploaded": True,
                                                   "duplicate_of": duplicate_of,
                                                   "import_batch_id": import_batch_id})
    store.merge_job_result(jid, row_count=len(items), matched=matched,
                            stored=stored, promoted_case_ids=promoted_case_ids,
                            alreadyUploaded=True, duplicate_of=duplicate_of,
                            import_batch_id=import_batch_id)


def _import_evidence_ok(row, ctx) -> bool:
    """GAP5 evidence gate: a matched row is only promoted when the feature's actual
    API surface backs it. A row WITH an endpoint must hit an endpoint in the feature's
    spec (and, for api_tests, its method must be in the spec too). Rows without an
    endpoint, or features with no API spec to check against, are not gated (so UI/
    business tests and spec-less features still promote on score alone)."""
    ep = (getattr(row, "endpoint", "") or "").strip()
    if not ep or not getattr(ctx, "endpoints", None):
        return True
    if sheet_mod._endpoint_match(ep, ctx.endpoints) <= 0:
        return False
    cat = (getattr(row, "category", "") or "").lower()
    method = (getattr(row, "method", "") or "").upper().strip()
    if cat in ("api_tests", "api") and method and ctx.methods and method not in ctx.methods:
        return False
    return True


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _feature_embedding(feature):
    text = ((feature.get("name") or "") + " " +
            (feature.get("description") or feature.get("summary") or ""))[:2000]
    try:
        return state.embedder.embed(text, task="query") if text.strip() else None
    except Exception:  # noqa: BLE001
        return None


def _pool_row_embedding(row):
    """GAP8: embedding for a pool row, cached on the row so we embed it once."""
    emb = row.get("embedding")
    if emb:
        return emb
    p = row.get("normalized_payload") or {}
    steps_txt = " ".join((s.get("content") if isinstance(s, dict) else str(s))
                         for s in (p.get("steps") or []))
    text = f"{p.get('title', '')} {p.get('description', '')} {steps_txt}".strip()[:2000]
    if not text:
        return None
    try:
        emb = state.embedder.embed(text)
        store.set_imported_row_embedding(row["id"], emb)
        return emb
    except Exception:  # noqa: BLE001
        return None


def _rescan_pool_for_feature(feature) -> tuple[int, list[str]]:
    """Re-score this project's unlinked imported-pool rows against `feature` and
    promote newly-matching, evidence-backed rows into it. Returns (rescored,
    promoted_case_ids). Shared by: the on-demand refresh endpoint, the post-generation
    recheck (GAP4), and the scheduled project-wide re-analysis (GAP2)."""
    if not feature:
        return 0, []
    fid = str(feature.get("id") or feature.get("_id"))
    pid = feature.get("project_id")
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    pool = store.list_project_imported_rows(pid, feature_id=fid, unlinked_only=True)
    # GAP8 (opt-in): embed the feature once for the semantic-match path.
    feat_emb = _feature_embedding(feature) if IMPORT_SEMANTIC_MATCH else None
    promoted, rescored = [], 0
    for r in pool:
        payload = sheet_mod.normalize_imported_payload_shape(
            r.get("normalized_payload") or {})
        if not payload.get("title"):
            continue
        row_obj = _parsed_row_from_payload(payload)
        res = sheet_mod.score_row(row_obj, ctx)
        rescored += 1
        store.update_imported_row_relevance(
            r["id"], relevance_score=res.score, relevance_feature_id=fid,
            needs_project_analysis=False)
        # Promote if the algorithmic scorer matched (GAP5-gated) OR, when semantic
        # matching is enabled, if the embedding similarity clears the threshold.
        promote_it = (res.action == "matched")
        if not promote_it and IMPORT_SEMANTIC_MATCH and feat_emb:
            remb = _pool_row_embedding(r)
            if remb and _cosine(feat_emb, remb) >= IMPORT_SEMANTIC_THRESHOLD:
                promote_it = True
        if promote_it and _import_evidence_ok(row_obj, ctx):
            payload = dict(payload)
            payload["identity_hash"] = r.get("identity_hash") or payload.get("identity_hash")
            cid = _promote_imported_row_to_feature(
                r["id"], feature, payload, origin="inherited", score=res.score,
                inherited_from={"feature_id": r.get("latest_relevance_feature_id")})
            promoted.append(cid)
    if promoted:
        try:
            store.mark_feature_test_plans_stale(fid)
        except Exception:  # noqa: BLE001
            pass
    return rescored, promoted


def _apply_import_overlays(feature) -> int:
    """GAP3: flag GENERATED test cases that are also backed by an imported QA-library
    row (strong token overlap on title+steps), so the UI can badge "matches imported
    QA library". Pure annotation — never changes the case content. Returns count."""
    if not feature:
        return 0
    fid = str(feature.get("id") or feature.get("_id"))
    pid = feature.get("project_id")
    try:
        cases = store.get_feature_cases(fid)
        pool = store.list_project_imported_rows(pid)
    except Exception:  # noqa: BLE001
        return 0
    if not cases or not pool:
        return 0
    pool_tok = []
    for r in pool:
        p = r.get("normalized_payload") or {}
        steps_txt = " ".join((s.get("content") if isinstance(s, dict) else str(s))
                             for s in (p.get("steps") or []))
        toks = sheet_mod.tokenize(f"{p.get('title', '')} {steps_txt}")
        if toks:
            pool_tok.append((r, p, toks))
    if not pool_tok:
        return 0
    stamped = 0
    for case in cases:
        # Overlay is for genuinely GENERATED cases, not ones already sourced from imports.
        if (case.get("association") or {}).get("origin") in ("imported", "inherited", "reviewed"):
            continue
        steps_txt = " ".join(f"{s.get('action', '')} {s.get('expected', '')}"
                             for s in (case.get("steps") or []) if isinstance(s, dict))
        ctok = sheet_mod.tokenize(f"{case.get('title', '')} {steps_txt}")
        if not ctok:
            continue
        best, best_p, best_score = None, None, 0.0
        for r, p, toks in pool_tok:
            j = sheet_mod._jaccard(ctok, toks)
            if j > best_score:
                best, best_p, best_score = r, p, j
        if best and best_score >= 0.5:
            store.set_case_import_overlay(case["id"], {
                "confidence": round(best_score, 3),
                "matched_pool_row_id": best["id"],
                "matched_title": (best_p.get("title") or "")[:160],
                "basis": "title+steps overlap",
            })
            stamped += 1
    return stamped
