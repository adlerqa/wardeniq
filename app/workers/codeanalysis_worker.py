
from datetime import datetime, timedelta, timezone

import coverage as cov
import contracts
import extract as extractmod
import grounding

from core import state
from core.config import MINDMAP_SAMPLES
from core.deps import (
    _fetch_repo_snapshot_files, _implementation_repo_docs, _repo_branch_sha,
    _repo_get_archive, _repo_get_commit, _repo_list_commits, current_llm,
)
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                               # mutated, never rebound)

from workers.heartbeat import heartbeat
from workers.registry import JOB_WORKERS


def _codeanalysis_worker(jid, params):
    """External-reviewer pass: read the ACTUAL repo code, embed it, and map every
    active feature's test cases to covered / partial / uncovered against the code."""
    project_id = params["project_id"]
    repo_ids = params.get("repo_ids") or []
    branches = params.get("branches") or {}          # {repo_id: branch}
    branch_override = (params.get("branch") or "").strip()   # legacy global fallback
    force_reindex = bool(params.get("force_reindex"))
    docs = _implementation_repo_docs(project_id, repo_ids)
    repos = [{**r, "id": str(r["_id"])} for r in docs]
    if not repos:
        raise RuntimeError("no implementation repos selected — test repos are only used for automation coverage")
    mem = []          # in-memory [(repo_full, path, text, embedding)] for cosine retrieval
    total, tests_skipped, errors, per_repo = 0, 0, [], []
    non_impl_skipped = 0    # dropped as unable to implement anything; NOT tests
    # Cross-file dependency evidence (contracts.py): whole-file text for every repo in this
    # job, gathered independently of the incremental-reuse decision below. On the reuse path
    # (below) `mem` is populated from stored function CHUNKS, not whole-file text, so a
    # producer/consumer contract broken entirely outside any indexed chunk boundary would be
    # invisible to `contracts.find_orphaned_contract_reads` if it only saw `mem` — a second,
    # best-effort snapshot fetch (`_fetch_repo_snapshot_files`) closes that gap for reused
    # repos. On the fresh-fetch path (below) the whole-file text is already in hand from
    # `extractmod.source_files_from_tar`, so it is reused directly with no second fetch.
    all_repo_files = []
    # Background heartbeat for the indexing phase below (archive fetch +
    # embedding, across every repo in this job). A LIVE caption via the shared
    # heartbeat() helper (workers/heartbeat.py) — narrower than the generic
    # per-job heartbeat launch_job() already wraps every worker in, because
    # this phase wants the SPECIFIC file/repo being worked on in the caption,
    # not just a re-touched timestamp on whatever stage was last set.
    _heartbeat_message = ["indexing — starting…"]
    with heartbeat(jid, message=lambda: _heartbeat_message[0]):
        for repo in repos:
            provider = (repo.get("git_provider") or "github").lower()
            ref = (branches.get(repo["id"]) or "").strip() or branch_override \
                or repo.get("default_branch", "")
            # Incremental reuse: if the branch head hasn't changed since we last indexed this
            # repo, reuse the stored chunks instead of re-fetching the tarball + re-embedding.
            try:
                head = _repo_branch_sha(repo, ref) if ref else None
            except Exception:  # noqa: BLE001
                head = None
            meta = store.get_code_index(repo["id"])
            # Reuse requires BOTH an unchanged branch head AND an index built by the current
            # exclusion rules. The rules fingerprint is what makes `force_reindex` unnecessary
            # in normal use: change what counts as a spec file and every stale index rebuilds
            # itself, instead of quietly serving chunks filtered by the old rules.
            rules_ok = (meta or {}).get("rules") == cov.INDEX_RULES_FINGERPRINT
            if not force_reindex and rules_ok and head and meta and meta.get("sha") == head and \
                    store.code_chunks.count_documents({"repo_id": repo["id"]}) > 0:
                store.update_job(jid, stage=f"reusing index — {repo['full_name']}@{ref} (unchanged)")
                _heartbeat_message[0] = f"reusing index — {repo['full_name']}@{ref} (unchanged)"
                paths = set()
                for d in store.code_chunks_for_repo(repo["id"]):
                    mem.append((d["repo"], d["path"], d["text"], d["embedding"]))
                    paths.add(d["path"]); total += 1
                per_repo.append({"repo": repo["full_name"], "branch": ref or "default",
                                 "impl_files": len(paths), "reused": True, "git_provider": provider})
                print(f"[wardenIQ][mindmap] {repo['full_name']}@{ref}: reused index "
                      f"({len(paths)} impl files, head {head[:7]})", flush=True)
                # `mem` above only has stored function chunks for a reused repo, not whole-file
                # text — fetch a best-effort whole-repo snapshot separately so contract-break
                # detection sees full file contents even when this repo's index was reused as-is.
                all_repo_files.extend(_fetch_repo_snapshot_files(repo, ref))
                continue
            store.update_job(jid, stage=f"fetching {provider} code — {repo['full_name']}@{ref or 'default'}")
            _heartbeat_message[0] = f"fetching {provider} code — {repo['full_name']}@{ref or 'default'}"
            try:
                data = _repo_get_archive(repo, ref)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{repo['full_name']}@{ref}: {e}")
                per_repo.append({"repo": repo["full_name"], "branch": ref, "error": str(e)[:200]})
                continue
            files, stats = extractmod.source_files_from_tar(data, return_stats=True)
            # Whole-file text is already in hand from this fetch — reuse it directly for
            # contract-break detection instead of issuing a second archive fetch.
            all_repo_files.extend({"path": p, "text": t} for p, t in files)
            store.clear_code_chunks(repo["id"])
            batch = []
            repo_paths, repo_tests, repo_chunks = [], 0, 0
            repo_non_impl = 0
            for path, text in files:
                # Mind Map judges IMPLEMENTATION coverage only. Test/spec files are
                # excluded — whether an automated test exists is tracked separately.
                if cov.is_test_file(path):
                    tests_skipped += 1; repo_tests += 1
                    continue
                # Files that cannot implement anything — type declarations, tool config, seed
                # data, migrations — are dropped on a SEPARATE counter. `tests_skipped` has to
                # keep meaning "developer-authored tests", because automation coverage reports
                # that number and lumping `activity.types.ts` in would inflate it.
                # `text` is passed so the content rule applies: a path rule cannot safely tell
                # `types/activity.types.ts` (declarations only) from a runtime helper that
                # happens to live in types/, but the file body can.
                if cov.is_non_implementation_file(path, text):
                    non_impl_skipped += 1; repo_non_impl += 1
                    continue
                repo_paths.append(path)
                for i, ch in enumerate(grounding.chunk_code_by_function(text, path)):
                    # Heartbeat message only - the background thread above does the
                    # actual (rate-limited) store.update_job() write.
                    _heartbeat_message[0] = f"embedding {repo['full_name']} — {path} ({total} chunk(s) so far)"
                    emb = state.embedder.embed(ch)
                    mem.append((repo["full_name"], path, ch, emb))
                    batch.append({"project_id": project_id, "repo_id": repo["id"],
                                  "repo": repo["full_name"], "path": path, "chunk_index": i,
                                  "text": ch, "embedding": emb})
                    total += 1; repo_chunks += 1
                    if len(batch) >= 100:
                        store.add_code_chunks(batch); batch = []
            if batch:
                store.add_code_chunks(batch)
            if head:
                store.set_code_index(repo["id"], head, repo_chunks, len(repo_paths),
                                     rules=cov.INDEX_RULES_FINGERPRINT)
            per_repo.append({"repo": repo["full_name"], "branch": ref or "default",
                             "git_provider": provider,
                             "files_in_repo": stats["total_files"], "code_matched": len(files),
                             "impl_files": len(repo_paths), "test_files": repo_tests,
                             "non_impl_files": repo_non_impl,
                             "extensions": stats["top_ext"],
                             "impl_sample": repo_paths[:40],
                             "sample": stats["sample"] if not files else []})
            print(f"[wardenIQ][mindmap] {repo['full_name']}@{ref or 'default'}: "
                  f"{len(repo_paths)} impl files, {repo_tests} tests skipped, "
                  f"{repo_non_impl} non-implementation skipped, "
                  f"{stats['total_files']} total. files={repo_paths[:60]}", flush=True)
            store.update_job(jid, stage=f"indexed {repo['full_name']} — {len(repo_paths)} impl files, "
                                         f"{repo_tests} tests skipped, "
                                         f"{repo_non_impl} non-implementation skipped "
                                         f"({stats['total_files']} total)")
    store.merge_job_result(jid, code_chunks=total, tests_skipped=tests_skipped,
                           non_impl_skipped=non_impl_skipped,
                           repos=[r["full_name"] for r in repos], errors=errors,
                           per_repo=per_repo)
    if not mem:
        if tests_skipped:
            note = ("only test/spec files found — connect the implementation repo(s) to "
                    "measure code coverage")
        elif non_impl_skipped:
            # Everything matched was type declarations / config / seed data. Saying "no
            # source files found" here would send someone hunting a extraction bug.
            note = (f"{non_impl_skipped} file(s) matched but none can implement behaviour "
                    "(type declarations, tool config, seed data or migrations)")
        else:
            note = "no recognized source files found — see per-repo diagnostics below"
        store.merge_job_result(jid, features_mapped=0, note=note)
        return
    feats = store.list_features(project_id)
    lm = current_llm()
    repo_names = [r["full_name"] for r in repos]
    mapped = 0
    # Cross-file dependency evidence (contracts.py), computed ONCE over every repo in this
    # job — snapshot-only (no diff, no PR to anchor to), so this is the orphaned-read
    # detector rather than the diff-based break detector: does any `.get(KEY, ...)` read
    # anywhere in the indexed repos reference a key that no code in those same repos ever
    # writes? Best-effort: an empty `all_repo_files` (every fetch failed) degrades to `[]`,
    # which review_code_coverage treats identically to "nothing to report" — never a hard
    # dependency for Mind Map's review to proceed.
    contract_findings = contracts.find_orphaned_contract_reads(all_repo_files) if all_repo_files else []

    def likely_impl_path(path: str) -> bool:
        p = (path or "").lower()
        noisy_parts = (
            "/load-test/", "/loadtest/", "/benchmark/", "/bench/", "/perf/", "/performance/",
            "/storybook/", "/fixtures/", "/fixture/", "/mocks/", "/mock/", "/examples/",
            "/sample/", "/samples/", "/docs/", "/doc/", "/prisma/migrations/", "/migrations/",
            "/seed/", "/seeds/",
        )
        noisy_suffixes = (".snap", ".md", ".txt", ".sql")
        if any(part in p for part in noisy_parts):
            return False
        if p.endswith(noisy_suffixes):
            return False
        return True

    def impl_path_score(path: str, kws: list[str]) -> int:
        """Language-agnostic implementation-file scoring.

        The goal is not to guess a framework, but to prefer likely source files over
        docs, fixtures, migrations, examples, load scripts, and other low-signal paths.
        """
        p = (path or "").lower().strip("/")
        score = 0
        segs = p.split("/") if p else []
        base = segs[-1] if segs else p

        preferred_dirs = {
            "src", "app", "lib", "core", "pkg", "internal", "cmd", "server", "api",
            "services", "service", "handlers", "handler", "controllers", "controller",
            "routes", "router", "models", "domain", "modules", "features", "components",
            "views", "pages",
        }
        de_emphasize_dirs = {
            "docs", "doc", "examples", "example", "samples", "sample", "fixtures", "fixture",
            "mocks", "mock", "bench", "benchmark", "perf", "performance", "scripts",
            "seed", "seeds", "migration", "migrations",
        }
        config_names = {
            "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "cargo.lock",
            "composer.lock", "poetry.lock", "pipfile.lock", "dockerfile", "makefile",
            "tsconfig.json", "vite.config.ts", "vite.config.js", "webpack.config.js",
        }

        for seg in segs:
            if seg in preferred_dirs:
                score += 3
            if seg in de_emphasize_dirs:
                score -= 4
        if base in config_names:
            score -= 5
        if base.startswith("index.") or base.startswith("main.") or base.startswith("server."):
            score += 2
        if base.endswith((".controller.ts", ".service.ts", ".route.ts", ".router.ts",
                          ".view.tsx", ".page.tsx", ".component.tsx")):
            score += 2
        score += sum(2 for k in kws if k and k in p)
        return score

    for f in feats:
        fid = f["id"]
        cids = store.feature_test_case_ids(fid)
        if not cids:
            continue
        cases = store.cases_brief(cids)
        store.update_job(jid, stage=f"reviewing — {f['name']}")
        full = store.get_feature(fid) or {}
        # Hybrid retrieval: BM25 (lexical — exact endpoint/identifier hits) fused with cosine
        # (semantic) via RRF over the in-memory code index. The query includes the requirement,
        # every test-case title, AND the endpoints the cases reference, so API cases retrieve the
        # right routes. Chunks are whole function/route bodies (tree-sitter), so the reviewer sees
        # complete implementations rather than arbitrary windows.
        case_titles = [c.get("title", "") for c in cases]
        eps = [ep["path"] for c in cases for ep in grounding.case_endpoints(c) if ep.get("path")]
        query_text = " ".join([full.get("text") or f["name"]] + case_titles + eps)[:3500]
        q = state.embedder.embed(query_text[:3000], task="query")
        pool = [(r, p, t, e) for (r, p, t, e) in mem if likely_impl_path(p)] or list(mem)
        texts = [f"{p} {t}" for (r, p, t, e) in pool]      # path + code = lexical document
        vecs = [e for (r, p, t, e) in pool]
        # Rank the ENTIRE pool. A top_k here decided what was never even considered, which
        # is a cap wearing a ranking's clothes.
        order = grounding.hybrid_rank_indices(query_text, texts, q, vecs, top_k=len(pool))
        # NO CAPS. Every retrieved chunk is handed to the reviewer, which sweeps them in
        # as many context-sized windows as it takes (coverage.window_excerpts). Rank order
        # is kept so the most relevant code is read first and cases resolve early, but
        # nothing is discarded: previously only ~20 chunks were shown and the remainder was
        # dropped, so "we never looked at it" was reported as "uncovered".
        chosen = [pool[i] for i in order]
        excerpts = [{"repo": r, "path": p, "text": t} for (r, p, t, _e) in chosen]
        reviewed_files = sorted({f"{r}:{p}" for (r, p, _t, _e) in chosen})
        # MINDMAP_SAMPLES>1 judges each batch repeatedly and keeps 'covered' only when the
        # samples agree (costs N x tokens; cuts hallucination variance). Default 1 = off.
        # progress= keeps the job heartbeat alive. The exhaustive sweep is 10x+ longer than
        # the single pass it replaced and easily outlives STALE_JOB_TTL_SECONDS, so without
        # this the stale-job sweeper marks a perfectly healthy run "worker heartbeat lost".
        res = cov.review_code_coverage(lm, f["name"], full.get("text", ""), cases, excerpts,
                                       samples=MINDMAP_SAMPLES,
                                       progress=lambda m: store.update_job(jid, stage=m),
                                       contract_findings=contract_findings)
        res["reviewed_files"] = reviewed_files
        store.save_code_coverage(fid, project_id, res, repo_names)
        g = res.get("grounding") or {}
        print(f"[wardenIQ][mindmap] feature '{f['name']}': reviewed {len(reviewed_files)} "
              f"implementation files (hybrid retrieval); files={reviewed_files}", flush=True)
        # Grounding is the accuracy signal - log it so a bad run is visible in the logs
        # rather than only discoverable by clicking through the UI.
        print(f"[wardenIQ][mindmap] feature '{f['name']}': grounding - "
              f"{g.get('needs_review_count', 0)} case(s) need review, "
              f"{g.get('citations_rejected_total', 0)} fabricated citation(s) rejected, "
              f"{g.get('downgraded_count', 0)} verdict(s) downgraded, "
              f"samples={g.get('samples', 1)}", flush=True)
        mapped += 1
        store.merge_job_result(jid, features_mapped=mapped)
    store.merge_job_result(jid, features_mapped=mapped)
    # Coverage trend history (issue #45): a completed Mind Map run is one of
    # the events worth a point-in-time snapshot.
    try:
        store.save_coverage_snapshot(project_id, "mindmap", job_id=jid)
    except Exception as snap_e:  # noqa: BLE001
        print(f"[coverage-snapshot] skipped: {snap_e}", flush=True)


JOB_WORKERS["codeanalysis"] = _codeanalysis_worker


def _project_case_briefs(pid, limit=80):
    res = store.list_test_cases(project_id=pid, limit=limit)
    return store.cases_brief([i["id"] for i in res["items"]])


def _commit_change_summary(commits, max_chars=8000):
    """Structured per-commit summary for the LLM tier — keeps commit boundaries intact
    (the old build's flat-merge lost these, so matches couldn't be tied to a commit)."""
    parts = []
    for c in commits:
        head = f"COMMIT {c.get('short', '')} [{c.get('repo', '')}] {c.get('message', '')}"
        body = [f"  {f['filename']} ({f.get('status', '')}, "
                f"+{f.get('additions', 0)}/-{f.get('deletions', 0)})\n{(f.get('patch') or '')[:800]}"
                for f in (c.get("files") or [])[:8]]
        parts.append(head + "\n" + "\n".join(body))
    return "\n\n".join(parts)[:max_chars]


def _analyze_worker(jid, params):
    """Grounded impact / commit analysis.

    For each commit we extract endpoints + symbols (with file:line evidence) and match them
    to test cases by tier (endpoint-exact > endpoint-path > guarded-symbol). Cases not matched
    by grounded signals get a bounded LLM pass over a *per-commit* summary. Every impacted case
    carries a verdict, confidence/tier and the exact commit/file/line proof.
    """
    days = params["days"]
    repo_ids = params.get("repo_ids") or []
    branches = params.get("branches") or {}          # {repo_id: branch}
    project_id = params["project_id"]
    feature_id = params.get("feature_id")
    docs = _implementation_repo_docs(project_id, repo_ids)
    repos = [{**r, "id": str(r["_id"])} for r in docs]
    if not repos:
        store.merge_job_result(
            jid,
            impacted=[],
            results=[],
            grounded=0,
            ai=0,
            note="no implementation repos selected — test repos are only used for automation coverage",
        )
        return
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    commits, per_repo, errors, changed = [], [], [], set()
    for repo in repos:
        provider = (repo.get("git_provider") or "github").lower()
        ref = (branches.get(repo["id"]) or "").strip() or repo.get("default_branch", "")
        store.update_job(jid, stage=f"fetching {provider} commits — {repo['full_name']}@{ref or 'default'}")
        try:
            raw = _repo_list_commits(repo, since, ref=ref)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{repo['full_name']}@{ref}: {e}"); raw = []
        per_repo.append({"repo": repo["full_name"], "branch": ref or "default", "commits": len(raw), "git_provider": provider})
        for c in raw[:40]:
            sha = c.get("sha") or ""
            try:
                files = _repo_get_commit(repo, sha)
            except Exception:  # noqa: BLE001
                files = []
            for f in files:
                changed.add(f"{repo['full_name']}:{f['filename']}")
            commits.append({
                "repo": repo["full_name"], "sha": sha, "short": sha[:7],
                "url": c.get("html_url"),
                "message": ((c.get("commit", {}).get("message") or "").splitlines() or [""])[0][:90],
                "files": files})
    store.merge_job_result(jid, commit_count=sum(p["commits"] for p in per_repo),
                           per_repo=per_repo,
                           commits=[{"repo": c["repo"], "sha": c["short"], "url": c["url"],
                                     "message": c["message"]} for c in commits][:60],
                           changed_files=sorted(changed), errors=errors)
    if not commits:
        store.merge_job_result(jid, impacted=[], results=[], grounded=0, ai=0,
                               note="no changes in window")
        return

    cases = (store.cases_brief(store.feature_test_case_ids(feature_id)) if feature_id
             else _project_case_briefs(project_id))
    by_id = {c["id"]: c for c in cases}

    # 1) grounded tiers (no LLM) — exact, evidence-backed
    store.update_job(jid, stage="grounded matching (endpoints + symbols)")
    # Cross-file dependency evidence (contracts.py): a whole-repo snapshot per analyzed repo,
    # so a producer/consumer contract break can be found even when the consumer lives outside
    # any of this window's commits. Best-effort — see _fetch_repo_snapshot_files.
    repo_files = []
    for repo in repos:
        ref = (branches.get(repo["id"]) or "").strip() or repo.get("default_branch", "")
        repo_files.extend(_fetch_repo_snapshot_files(repo, ref))
    gm = grounding.match_commit_changes(commits, cases, repo_files=repo_files)
    results = []
    for cid, m in gm["matches"].items():
        c = by_id[cid]
        results.append({"case_id": cid, "display_id": c.get("display_id"),
                        "title": c["title"], "type": c["type"], "steps": c.get("steps"),
                        "status": m["status"], "tier": m["tier"], "confidence": m["confidence"],
                        "signal": m["signal"], "signal_type": m["signal_type"],
                        "risk": m["risk"], "reason": m["reason"], "evidence": m["evidence"]})

    # 2) LLM tier on the remainder only (semantic impacts) -> review_needed
    remaining = [c for c in cases if c["id"] not in gm["matched_ids"]]
    ai_count = 0
    if remaining:
        store.update_job(jid, stage=f"LLM impact analysis ({len(remaining)} remaining cases)")
        res = cov.analyze_impact(current_llm(), _commit_change_summary(commits), remaining)
        for x in res.get("impacted", []):
            cid = x.get("test_case_id")
            if cid in by_id and cid not in gm["matched_ids"]:
                c = by_id[cid]
                results.append({"case_id": cid, "display_id": c.get("display_id"),
                                "title": c["title"], "type": c["type"], "steps": c.get("steps"),
                                "status": "review_needed", "tier": 5, "confidence": None,
                                "signal": None, "signal_type": "ai",
                                "risk": x.get("risk", "medium"),
                                "reason": x.get("reason", ""), "evidence": []})
                ai_count += 1

    results.sort(key=lambda r: (r.get("tier") or 9))
    compact = [{"repo": c["repo"], "sha": c["short"], "url": c["url"], "message": c["message"]}
               for c in commits]
    run_id = store.save_commit_analysis(
        project_id, feature_id,
        {"days": days, "repo_ids": repo_ids, "branches": branches}, compact, results)
    # `impacted` kept for the existing cycle-builder/UI; now enriched with evidence
    store.merge_job_result(jid, run_id=run_id, impacted=results, results=results,
                           grounded=len(gm["matches"]), ai=ai_count)


JOB_WORKERS["analyze"] = _analyze_worker
