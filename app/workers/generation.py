
import re
import time

import coverage as cov

from core import state
from core.config import ENV_FILE_PATH
from core.deps import (
    _gather_external, _generate_feature_summary, _oid, _write_env_var,
    current_embedder, current_llm, gh_client,
)
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                               # mutated, never rebound)
from extract import chunk as chunk_doc
from testgen.service import generate_fresh_testcases_pipeline

from workers.registry import JOB_WORKERS, launch_job
from workers.repo_scan_worker import _apply_import_overlays, _rescan_pool_for_feature


def _gen_worker(jid, params):
    try:
        def update_fn(stage, progress=None):
            store.update_job_progress(jid, stage, progress)

        res = generate_fresh_testcases_pipeline(
            store=store,
            llm=current_llm(),
            embedder=state.embedder,
            params=params,
            update_job_fn=update_fn
        )
        store.merge_job_result(jid, **res)

        # Auto-trigger automation coverage for any connected test repos so the
        # Gap Analysis pane is fresh as soon as the user opens it. Scoped to
        # this single feature to keep LLM cost bounded.
        try:
            fid = params.get("feature_id")
            feature = store.get_feature(fid) if fid else None
            if feature and feature.get("project_id"):
                # Coverage trend history (issue #45): a completed generation run
                # is one of the events worth a point-in-time snapshot.
                try:
                    store.save_coverage_snapshot(feature["project_id"], "generation",
                                                 job_id=jid)
                except Exception as snap_e:  # noqa: BLE001
                    print(f"[coverage-snapshot] skipped: {snap_e}", flush=True)
                test_repos = store.repos_for_project(
                    feature["project_id"], repo_type="test")
                for tr in test_repos:
                    if tr.get("scan_status") == "running":
                        continue
                    launch_job("test_repo_scan", {
                        "repo_id": tr["id"], "feature_id": fid},
                        label=f"Auto-scan · {tr.get('full_name')}",
                        project_id=feature["project_id"], feature_id=fid)
        except Exception as auto_e:  # noqa: BLE001
            print(f"[auto-scan] skipped: {auto_e}", flush=True)
        # GAP4: a freshly (re)generated feature may now match rows sitting in the
        # imported pool — rescan and promote the evidence-backed ones.
        try:
            fid2 = params.get("feature_id")
            feat2 = store.get_feature(fid2) if fid2 else None
            if feat2:
                _rescan_pool_for_feature(feat2)     # GAP4
                _apply_import_overlays(feat2)         # GAP3
        except Exception as re_e:  # noqa: BLE001
            print(f"[import-recheck] skipped: {re_e}", flush=True)
    except Exception as e:
        store.update_job(jid, status="failed", stage="error", error=str(e))
        raise e


JOB_WORKERS["generate"] = _gen_worker


def _ingest_worker(jid, params):
    """Background ingestion for external sources; augments the feature's corpus with
    progress updates, then chains generation on the same job."""
    fid = params["feature_id"]
    pid = params["project_id"]
    name = params.get("name") or ""
    parts = list(params.get("base_parts") or [])
    sources = list(params.get("base_sources") or [])

    figma_data, warnings = _gather_external(
        parts, sources,
        figma_urls=params.get("figma_urls") or [], pdf_figma=params.get("pdf_figma") or [],
        confluence_urls=params.get("confluence_urls") or [],
        confluence_children=params.get("confluence_children", True),
        crawl_seeds=params.get("crawl_seeds") or [], jid=jid)
    if figma_data:
        store.set_feature_figma(fid, figma_data)

    # ---- Rebuild corpus, update the feature, re-index for RAG ----
    store.update_job_progress(jid, "Indexing evidence", 40)
    raw = "\n\n".join(parts)
    if not raw.strip():
        store.update_job(jid, status="failed", stage="error",
                         error="No readable content from the provided sources. " + "; ".join(warnings[:3]))
        return
    summary = _generate_feature_summary(name, raw)
    emb = state.embedder.embed(raw[:2000])
    store.update_feature_doc(fid, sources, raw, summary, emb)
    chunks = []
    for i, ch in enumerate(chunk_doc(raw, max_chars=1200, overlap=150)):
        chunks.append({"source": sources[0] if sources else "combined",
                       "chunk_index": i, "text": ch, "embedding": state.embedder.embed(ch)})
    store.add_feature_chunks(fid, pid, chunks)
    if warnings:
        store.update_job_progress(jid, "Some sources skipped — " + "; ".join(warnings[:3]), 45)

    # ---- Generate on the SAME job (reuses the generate worker + auto test-repo scan) ----
    _gen_worker(jid, {"feature_id": fid, "text": raw,
                      "focus": params.get("focus"), "total": params.get("total")})


JOB_WORKERS["ingest"] = _ingest_worker


def _reembed_worker(jid, params):
    """Switch the embedding model: rebuild all vector indexes at the new dimension
    and re-embed every stored vector. Search/dedup/Mind-Map are degraded until this
    finishes (the vectors and indexes are being replaced)."""
    # CRITICAL (REFACTOR_PLAN.md 2.6): rebind via the qualified `state.embedder`
    # attribute, never `global embedder` — this is the app's one live-reassignment
    # of the embedder singleton, and every other consumer reads `state.embedder`
    # (not a name-imported local), so they must all observe this exact rebind.
    state.embedder = current_embedder()    # now points at the newly-saved model
    dim = int(params.get("dim") or state.embedder.dim)
    store.update_job_progress(jid, "Dropping old vector indexes", 3)
    store.drop_vector_indexes()
    counts = store.reembed_all(lambda t: state.embedder.embed(t),
                               progress=lambda s, p: store.update_job_progress(jid, s, p))
    store.update_job_progress(jid, "Building vector indexes at new dimension", 96)
    store.create_vector_indexes(dim)
    store.merge_job_result(jid, reembedded=counts, dim=dim,
                           provider=state.embedder.provider, model=state.embedder.model)
    store.update_job_progress(jid, "done", 100)


JOB_WORKERS["reembed"] = _reembed_worker


def _migrate_worker(jid, params):
    """Copy the whole database to a target MongoDB, then point MONGO_URI at it (.env).
    The app keeps running on the CURRENT database until the user restarts, so a failed
    or partial copy never strands them — the source stays authoritative."""
    target = params["target_uri"]
    overwrite = bool(params.get("overwrite"))
    store.update_job_progress(jid, "Starting migration", 2)
    counts = store.migrate_to(
        target, overwrite=overwrite,
        progress=lambda s, p: store.update_job_progress(jid, s, p))
    store.update_job_progress(jid, "Pointing wardenIQ at the new database (.env)", 97)
    ok, err = _write_env_var(ENV_FILE_PATH, "MONGO_URI", target)
    if not ok:
        raise RuntimeError(f"data was copied, but writing the config file failed: {err}")
    store.merge_job_result(jid, copied=counts, total_docs=sum(counts.values()),
                           restart_required=True, apply_cmd="docker compose up -d")
    store.update_job_progress(jid, "done", 100)


JOB_WORKERS["migrate"] = _migrate_worker


def _develop_worker(jid, params):
    feature = store.get_feature(params["feature_id"])
    cases = store.get_feature_cases(params["feature_id"])
    if not feature or not cases:
        raise RuntimeError("feature has no test cases")
    repo = store.repos.find_one({"_id": _oid(params["repo_id"])})
    if not repo:
        raise RuntimeError("repo not found")
    owner, name = repo["owner"], repo["name"]
    base_branch, language = params["base_branch"], params["language"]
    fname = feature.get("name", "feature")
    store.update_job(jid, stage="generating implementation code")
    gen = cov.generate_feature_code(current_llm(), language, fname, feature.get("text", ""), cases)
    if gen.get("error") or not gen.get("files"):
        raise RuntimeError(gen.get("error", "no code generated"))
    files = gen["files"]
    store.merge_job_result(jid, files=[f["path"] for f in files], notes=gen.get("notes", ""))
    slug = re.sub(r"[^a-z0-9]+", "-", fname.lower()).strip("-")[:40] or "feature"
    branch = f"wardeniq/{slug}-v{feature.get('version', 1)}"
    store.update_job(jid, stage=f"creating branch {branch}")
    base_sha = gh_client().branch_sha(owner, name, base_branch)
    try:
        gh_client().create_branch(owner, name, branch, base_sha)
    except Exception:  # branch exists → unique suffix
        branch = f"{branch}-{int(time.time())}"
        gh_client().create_branch(owner, name, branch, base_sha)
    for i, f in enumerate(files):
        store.update_job(jid, stage=f"committing {i+1}/{len(files)}: {f['path']}")
        gh_client().put_file(owner, name, f["path"], f["content"],
                             f"wardenIQ: implement {fname} ({f['path']})", branch)
    store.update_job(jid, stage="opening pull request")
    body = (f"Implementation generated by **wardenIQ** for feature **{fname}** "
            f"(v{feature.get('version', 1)}).\n\n{gen.get('notes','')}\n\n"
            f"Built to satisfy {len(cases)} acceptance test cases:\n"
            + "\n".join(f"- {c['title']}" for c in cases[:40]))
    pr = gh_client().create_pull(owner, name, f"wardenIQ: implement {fname}",
                                 branch, base_branch, body)
    store.merge_job_result(jid, pr_number=pr.get("number"), pr_url=pr.get("html_url"),
                           branch=branch, repo_id=str(repo["_id"]), cases=len(cases),
                           file_count=len(files))


JOB_WORKERS["develop"] = _develop_worker
