
from core.deps import current_llm
from core.logging_setup import get_logger
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                               # mutated, never rebound)
import sheet_import as sheet_mod

from workers.registry import JOB_WORKERS
from workers.repo_scan_worker import (
    _feature_doc_for_import_context,
    _import_evidence_ok,
    _promote_imported_row_to_feature,
    _reuse_existing_import_rows,
    _sheet_steps_preview,
)

log = get_logger("import")


def _test_import_worker(jid, params):
    """Parse the uploaded sheet, score rows against the feature, store
    canonical rows in the project pool, promote matches into the feature."""
    feature_import_id = params["feature_import_id"]
    project_id = params["project_id"]
    feature_id = params["feature_id"]
    fi = store.get_feature_import(feature_import_id)
    if not fi:
        store.update_job(jid, status="failed", stage="error",
                         error="feature_import not found")
        return
    duplicate_of = fi.get("duplicate_of_import_id")
    if duplicate_of:
        store.set_import_analysis_status(feature_import_id, "PROCESSING",
                                           "Reusing already uploaded sheet…")
        _reuse_existing_import_rows(jid, feature_import_id, project_id,
                                    feature_id, duplicate_of)
        return
    store.set_import_analysis_status(feature_import_id, "PROCESSING",
                                       "Parsing sheet…")
    store.update_job_progress(jid, "Parsing sheet…", 10)

    file_bytes = fi.get("file_bytes")
    if isinstance(file_bytes, str):
        import base64 as _b64
        file_bytes = _b64.b64decode(file_bytes)

    # ---- Pass 1: parse the sheet (header detect, merge propagation, group) ----
    try:
        rows = sheet_mod.parse_sheet(file_bytes,
                                       fi.get("original_filename", ""))
        content_signature = sheet_mod.content_signature(rows)
        store.update_feature_import(
            feature_import_id,
            content_signature_sha256=content_signature)
        duplicate_import = store.find_feature_import_by_signature(
            project_id, sig=content_signature, exclude_id=feature_import_id)
        if duplicate_import:
            store.update_feature_import(
                feature_import_id,
                duplicate_of_import_id=duplicate_import["id"])
            _reuse_existing_import_rows(jid, feature_import_id, project_id,
                                        feature_id, duplicate_import["id"])
            return
    except Exception as e:  # noqa: BLE001
        store.set_import_analysis_status(feature_import_id, "FAILED",
                                           f"parse error: {e}", completed=True)
        store.update_job(jid, status="failed", stage="error", error=str(e)[:200])
        return

    feature = store.get_feature(feature_id) or {}
    feat_name = feature.get("name", "")
    feat_desc = (feature.get("description") or feature.get("summary") or "")[:600]

    # ---- Pass 2: QA-relevance gate (short LLM + hard-coded fallback) -------
    # Mirrors Node's `isQARelatedSpreadsheet`. The LLM gets the RAW cell
    # preview (same shape Node uses) so the prompt judges actual upload
    # content rather than already-cleaned rows. On LLM failure we fall back
    # to the deterministic keyword heuristic.
    if rows:
        store.update_job_progress(jid, "Classifying sheet (LLM)…", 25)
        raw_tables = sheet_mod.raw_tables(file_bytes,
                                           fi.get("original_filename", ""))
        preview = sheet_mod.build_tables_preview(raw_tables)
        try:
            is_qa, reason = sheet_mod.classify_sheet_is_qa(
                current_llm(), preview, feat_name, feat_desc)
        except Exception as e:  # noqa: BLE001
            is_qa, reason = None, f"classifier failed: {e}"
        if is_qa is None:
            # LLM unreachable → fall back to deterministic heuristic.
            is_qa = sheet_mod.looks_like_qa_sheet_heuristic(raw_tables)
            reason = (reason or "") + " · heuristic fallback"
        if not is_qa:
            store.set_import_analysis_status(
                feature_import_id, "COMPLETED",
                f"Not a QA sheet — {reason}",
                completed=True, result_json={"items": [], "rejected_reason": reason})
            store.update_feature_import(feature_import_id, row_count=0,
                                          rejected_count=len(rows))
            store.merge_job_result(jid, row_count=0, matched=0, stored=0,
                                     rejected=len(rows), rejected_reason=reason)
            return

    # ---- Pass 3: LLM polish in concurrent batches of 8 ---------------------
    # Drops metadata-only rows (is_testcase=false), normalizes title/category/
    # priority/steps, rewrites Gherkin-style narrative noise. Mirrors Node's
    # `polishImportedRowsWithAI`.
    if rows:
        store.update_job_progress(jid, "Polishing rows (LLM, batched)…", 35)
        def _polish_progress(done, total):
            store.update_job_progress(
                jid, f"Polishing rows · {done}/{total} batches",
                35 + (15 * done // max(1, total)))
        try:
            rows = sheet_mod.polish_all_rows(
                current_llm(), rows, feat_name, feat_desc,
                batch_size=8, max_workers=6, progress_fn=_polish_progress)
        except Exception as e:  # noqa: BLE001
            log.warning("polish failed (using parser output): %s", e)

    if not rows:
        store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                           "No test rows recognized",
                                           completed=True, result_json={"items": []})
        store.update_feature_import(feature_import_id, row_count=0)
        store.merge_job_result(jid, row_count=0, matched=0, stored=0)
        return

    # ---- Pass 4: algorithmic scoring + project-pool storage ----------------
    ctx = sheet_mod.build_feature_context(_feature_doc_for_import_context(feature))
    store.update_job_progress(jid, "Scoring rows…", 55)

    import_batch_id = fi.get("import_batch_id") or feature_import_id
    matched = 0
    stored = 0
    promoted_case_ids = []
    items = []
    for idx, row in enumerate(rows):
        ihash = sheet_mod.identity_hash(row)
        payload = row.to_dict()
        payload["identity_hash"] = ihash
        result = sheet_mod.score_row(row, ctx)
        # GAP5 evidence gate: downgrade a "matched" row to the pool when the feature's
        # API surface doesn't actually back it (keeps unsupported endpoints out).
        action = result.action
        if action == "matched" and not _import_evidence_ok(row, ctx):
            action = "stored_for_later"
        match_status = "matched_feature" if action == "matched" else "unmatched_pool"
        prid = store.upsert_project_imported_row(
            project_id, ihash, payload,
            match_status=match_status, latest_score=result.score,
            latest_feature_id=feature_id,
            needs_project_analysis=(action != "matched"))
        store.add_imported_row_source(
            prid, feature_import_id, import_batch_id, feature_id,
            fi.get("original_filename", ""), row.sheet, row.row_number)
        item = {
            "row_index": idx,
            "identity_hash": ihash,
            "project_imported_row_id": prid,
            "title": row.title,
            "category": row.category,
            "priority": row.priority,
            "sheet": row.sheet,
            "row_number": row.row_number,
            "endpoint": row.endpoint,
            "method": row.method,
            "steps_count": len(row.steps),
            "steps_preview": _sheet_steps_preview(row.steps),
            "expected_result": row.expected_result[:160],
            "score": result.score,
            "action": action,
            "scorer_action": result.action,   # pre-evidence-gate (for review UI)
            "breakdown": result.breakdown,
        }
        if action == "matched":
            # Promote into the feature now.
            cid = _promote_imported_row_to_feature(
                prid, feature, payload, origin="imported", score=result.score)
            promoted_case_ids.append(cid)
            item["promoted_testcase_id"] = cid
            matched += 1
        else:
            stored += 1
        items.append(item)

    # GAP9: promoting imported rows changed this feature's test cases → its stored
    # test-plan runs are now out of date; flag them for regeneration.
    if promoted_case_ids:
        try:
            store.mark_feature_test_plans_stale(feature_id)
        except Exception:  # noqa: BLE001
            pass

    store.update_feature_import(feature_import_id, row_count=len(rows),
                                  accepted_count=matched, flagged_count=stored,
                                  rejected_count=0)
    store.set_import_analysis_status(feature_import_id, "COMPLETED",
                                       f"{matched} matched · {stored} stored",
                                       completed=True,
                                       result_json={"items": items,
                                                      "import_batch_id": import_batch_id})
    store.merge_job_result(jid, row_count=len(rows), matched=matched,
                            stored=stored, promoted_case_ids=promoted_case_ids,
                            import_batch_id=import_batch_id)


JOB_WORKERS["test_import"] = _test_import_worker
