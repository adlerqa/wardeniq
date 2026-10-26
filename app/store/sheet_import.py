"""Imported test-sheet pipeline: feature imports, the project-wide imported-row
pool, source/relevance tracking, promotion to features, and review corrections.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md). This is the largest single
domain (34 members) — it owns all 7 `@property`-exposed imported-row
collections plus every `*_imported_*` / `*_pool*` method.
"""

import time

from bson import ObjectId


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: gives this mixin visibility into the collection attributes and
    # cross-mixin helpers that store/__init__.py's Store actually composes in at
    # runtime (BaseStore.__init__ sets self.projects/self.cases/etc; other mixins
    # add their own methods). At runtime this mixin still inherits only `object`
    # (see the `else` branch) — Store's own MRO (store/__init__.py) is what really
    # provides these at runtime, unchanged from before this TYPE_CHECKING addition.
    from store.base import BaseStore as _Base
else:
    _Base = object


class SheetImportMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    @property
    def feature_imports(self):
        return self.db["feature_imports"]

    @property
    def project_imported_rows(self):
        return self.db["project_imported_rows"]

    @property
    def project_imported_row_sources(self):
        return self.db["project_imported_row_sources"]

    @property
    def project_imported_row_feature_map(self):
        return self.db["project_imported_row_feature_map"]

    @property
    def project_imported_row_promotions(self):
        return self.db["project_imported_row_promotions"]

    @property
    def project_imported_row_corrections(self):
        return self.db["project_imported_row_corrections"]

    @property
    def import_analysis_status(self):
        return self.db["import_analysis_status"]

    def record_import_correction(self, project_id, batch_id, feature_id, row_id,
                                  identity_hash, action, note="", actor=None):
        """Persist a reviewer's override of the scorer's decision for one imported
        row within one import batch. Latest write wins (upsert on batch + row)."""
        now = time.time()
        key = {"import_batch_id": batch_id,
               "project_imported_row_id": row_id or None}
        self.project_imported_row_corrections.update_one(
            key,
            {"$set": {**key, "project_id": project_id, "feature_id": feature_id,
                      "identity_hash": identity_hash or None,
                      "action": action, "note": (note or "")[:2000],
                      "actor": actor, "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True)

    def import_corrections_for_batch(self, batch_id):
        """Return the latest corrections for a batch, keyed by BOTH the imported
        row id and its identity hash so callers can look up either way."""
        out = {}
        for c in self.project_imported_row_corrections.find(
                {"import_batch_id": batch_id}):
            c["id"] = str(c.pop("_id"))
            if c.get("project_imported_row_id"):
                out[c["project_imported_row_id"]] = c
            if c.get("identity_hash"):
                out[c["identity_hash"]] = c
        return out

    def list_projects_with_pending_import_rows(self):
        """Project ids that still have imported-pool rows awaiting project-wide
        re-analysis (needs_project_analysis=True). Consumed by the scheduler (GAP2)."""
        return self.project_imported_rows.distinct(
            "project_id", {"needs_project_analysis": True})

    def set_imported_row_embedding(self, project_imported_row_id, embedding):
        """GAP8: cache a pool row's embedding on the row so semantic matching doesn't
        re-embed it every pass. No-op if the id is invalid."""
        if not ObjectId.is_valid(project_imported_row_id):
            return
        self.project_imported_rows.update_one(
            {"_id": ObjectId(project_imported_row_id)},
            {"$set": {"embedding": embedding}})

    def create_feature_import(self, doc):
        doc = {**doc, "created_at": time.time(), "updated_at": time.time()}
        return str(self.feature_imports.insert_one(doc).inserted_id)

    def update_feature_import(self, iid, **fields):
        fields["updated_at"] = time.time()
        self.feature_imports.update_one({"_id": ObjectId(iid)}, {"$set": fields})

    def get_feature_import(self, iid):
        if not ObjectId.is_valid(iid):
            return None
        r = self.feature_imports.find_one({"_id": ObjectId(iid)})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def find_feature_import_by_file_sha(self, project_id, file_sha, feature_id=None):
        if not file_sha:
            return None
        q = {"project_id": project_id, "file_sha256": file_sha}
        if feature_id:
            q["feature_id"] = feature_id
        r = self.feature_imports.find_one(q, sort=[("created_at", -1)])
        if r:
            r["id"] = str(r.pop("_id"))
        return r

    def find_feature_import_by_signature(self, project_id, feature_id=None, sig=None,
                                         exclude_id=None):
        if not sig:
            return None
        q = {"project_id": project_id, "content_signature_sha256": sig}
        if feature_id:
            q["feature_id"] = feature_id
        if exclude_id and ObjectId.is_valid(exclude_id):
            q["_id"] = {"$ne": ObjectId(exclude_id)}
        r = self.feature_imports.find_one(q, sort=[("created_at", -1)])
        if r:
            r["id"] = str(r.pop("_id"))
        return r

    def upsert_project_imported_row(self, project_id, identity_hash, payload,
                                     match_status="unmatched_pool",
                                     latest_score=0.0, latest_feature_id=None,
                                     needs_project_analysis=True):
        """Insert if new, increment times_seen if seen before."""
        existing = self.project_imported_rows.find_one(
            {"project_id": project_id, "identity_hash": identity_hash})
        now = time.time()
        if existing:
            existing_status = existing.get("current_match_status", "unmatched_pool")
            next_status = ("matched_feature"
                           if match_status == "matched_feature"
                           or existing_status == "matched_feature"
                           else match_status)
            next_needs_analysis = (
                existing.get("needs_project_analysis", False)
                or needs_project_analysis)
            if match_status == "matched_feature":
                next_needs_analysis = False
            self.project_imported_rows.update_one(
                {"_id": existing["_id"]},
                {"$set": {"last_seen_at": now, "updated_at": now,
                          "current_match_status": next_status,
                          "latest_relevance_score": max(
                              latest_score, existing.get("latest_relevance_score", 0)),
                          "latest_relevance_feature_id": (latest_feature_id
                              if latest_score > existing.get("latest_relevance_score", 0)
                              else existing.get("latest_relevance_feature_id")),
                          "needs_project_analysis": next_needs_analysis,
                          "normalized_payload": payload},
                 "$inc": {"times_seen": 1}})
            return str(existing["_id"])
        doc = {
            "project_id": project_id, "identity_hash": identity_hash,
            "normalized_payload": payload,
            "ownership": "user_imported",
            "current_match_status": match_status,
            "needs_project_analysis": needs_project_analysis,
            "latest_relevance_score": latest_score,
            "latest_relevance_feature_id": latest_feature_id,
            "promotion_count": 0, "times_seen": 1,
            "first_seen_at": now, "last_seen_at": now,
            "created_at": now, "updated_at": now,
        }
        return str(self.project_imported_rows.insert_one(doc).inserted_id)

    def add_imported_row_source(self, project_imported_row_id, feature_import_id,
                                  import_batch_id, feature_id, original_filename,
                                  sheet_name, row_number):
        try:
            self.project_imported_row_sources.insert_one({
                "project_imported_row_id": project_imported_row_id,
                "feature_import_id": feature_import_id,
                "import_batch_id": import_batch_id,
                "feature_id": feature_id,
                "original_filename": original_filename,
                "sheet_name": sheet_name, "row_number": row_number,
                "observed_at": time.time(), "created_at": time.time(),
            })
        except Exception:  # noqa: BLE001
            pass  # duplicate source row — ignore

    def list_imported_rows_for_feature_import(self, feature_import_id):
        """Return canonical project rows that came from one uploaded workbook."""
        out = []
        seen = set()
        for src in self.project_imported_row_sources.find(
                {"feature_import_id": feature_import_id}).sort("observed_at", 1):
            rid = src.get("project_imported_row_id")
            if not rid or rid in seen or not ObjectId.is_valid(rid):
                continue
            row = self.project_imported_rows.find_one({"_id": ObjectId(rid)})
            if not row:
                continue
            row["id"] = str(row.pop("_id"))
            row["source_ref"] = {
                "feature_import_id": src.get("feature_import_id"),
                "import_batch_id": src.get("import_batch_id"),
                "feature_id": src.get("feature_id"),
                "original_filename": src.get("original_filename"),
                "sheet_name": src.get("sheet_name"),
                "row_number": src.get("row_number"),
            }
            out.append(row)
            seen.add(rid)
        return out

    def update_imported_row_relevance(self, project_imported_row_id,
                                      relevance_score=None,
                                      relevance_feature_id=None,
                                      needs_project_analysis=None,
                                      match_status=None):
        if not ObjectId.is_valid(project_imported_row_id):
            return False
        fields = {"updated_at": time.time()}
        if relevance_score is not None:
            fields["latest_relevance_score"] = relevance_score
        if relevance_feature_id is not None:
            fields["latest_relevance_feature_id"] = relevance_feature_id
        if needs_project_analysis is not None:
            fields["needs_project_analysis"] = bool(needs_project_analysis)
        if match_status:
            fields["current_match_status"] = match_status
        self.project_imported_rows.update_one(
            {"_id": ObjectId(project_imported_row_id)}, {"$set": fields})
        return True

    def touch_imported_row_seen(self, project_imported_row_id,
                                relevance_score=None,
                                relevance_feature_id=None):
        if not ObjectId.is_valid(project_imported_row_id):
            return False
        fields = {"updated_at": time.time(), "last_seen_at": time.time()}
        if relevance_score is not None:
            fields["latest_relevance_score"] = relevance_score
        if relevance_feature_id is not None:
            fields["latest_relevance_feature_id"] = relevance_feature_id
        self.project_imported_rows.update_one(
            {"_id": ObjectId(project_imported_row_id)},
            {"$set": fields, "$inc": {"times_seen": 1}})
        return True

    def link_row_to_feature(self, project_imported_row_id, feature_id):
        existing = self.project_imported_row_feature_map.find_one({
            "project_imported_row_id": project_imported_row_id,
            "feature_id": feature_id})
        if existing:
            return False
        self.project_imported_row_feature_map.insert_one({
            "project_imported_row_id": project_imported_row_id,
            "feature_id": feature_id,
            "first_import_at": time.time()})
        return True

    def unlink_row_from_feature(self, project_imported_row_id, feature_id):
        self.project_imported_row_feature_map.delete_one({
            "project_imported_row_id": project_imported_row_id,
            "feature_id": feature_id})

    def unlink_imported_row_from_feature(self, project_imported_row_id, feature_id):
        """Detach one imported-memory row from one feature and remove promoted cases.

        The canonical project memory row remains available for future reuse.
        """
        removed_cases = 0
        deleted_orphans = 0
        promotions = list(self.project_imported_row_promotions.find({
            "project_imported_row_id": project_imported_row_id,
            "feature_id": feature_id,
        }))
        for prom in promotions:
            cid = prom.get("promoted_testcase_id")
            if not cid:
                continue
            result = self.unlink_case_from_feature(feature_id, cid)
            if result.get("removed"):
                removed_cases += 1
            if result.get("deleted_orphan"):
                deleted_orphans += 1
        self.project_imported_row_promotions.delete_many({
            "project_imported_row_id": project_imported_row_id,
            "feature_id": feature_id,
        })
        self.unlink_row_from_feature(project_imported_row_id, feature_id)
        return {"removed_testcases": removed_cases, "deleted_orphans": deleted_orphans}

    def delete_project_imported_row(self, project_imported_row_id):
        """Hard-delete a canonical row + its lineage. Use when 'delete from system'."""
        self.project_imported_row_feature_map.delete_many(
            {"project_imported_row_id": project_imported_row_id})
        self.project_imported_row_sources.delete_many(
            {"project_imported_row_id": project_imported_row_id})
        if ObjectId.is_valid(project_imported_row_id):
            self.project_imported_rows.delete_one(
                {"_id": ObjectId(project_imported_row_id)})

    def delete_imported_row_from_project(self, project_id, project_imported_row_id):
        """Delete one canonical imported row and all testcases promoted from it.

        Feature-import records are deleted only when no remaining source rows
        still point at the same uploaded workbook.
        """
        if not ObjectId.is_valid(project_imported_row_id):
            return {"removed": False, "reason": "invalid row id"}
        row = self.project_imported_rows.find_one({
            "_id": ObjectId(project_imported_row_id), "project_id": project_id})
        if not row:
            return {"removed": False, "reason": "row not found"}

        sources = list(self.project_imported_row_sources.find(
            {"project_imported_row_id": project_imported_row_id}))
        feature_import_ids = {
            s.get("feature_import_id") for s in sources if s.get("feature_import_id")
        }
        promotions = list(self.project_imported_row_promotions.find(
            {"project_imported_row_id": project_imported_row_id}))
        deleted_case_ids = set()
        removed_case_links = 0
        affected_feature_ids = set()
        for prom in promotions:
            cid = prom.get("promoted_testcase_id")
            linked_fid = prom.get("feature_id")
            if not cid or not linked_fid:
                continue
            result = self.unlink_case_from_feature(linked_fid, cid)
            if result.get("removed"):
                removed_case_links += 1
                affected_feature_ids.add(linked_fid)
            if result.get("deleted_orphan"):
                deleted_case_ids.add(cid)

        self.project_imported_row_promotions.delete_many(
            {"project_imported_row_id": project_imported_row_id})
        self.project_imported_row_feature_map.delete_many(
            {"project_imported_row_id": project_imported_row_id})
        self.project_imported_row_sources.delete_many(
            {"project_imported_row_id": project_imported_row_id})
        self.project_imported_rows.delete_one({"_id": ObjectId(project_imported_row_id)})

        deleted_import_ids = []
        for fid in feature_import_ids:
            remaining = self.project_imported_row_sources.count_documents(
                {"feature_import_id": fid})
            if remaining == 0:
                self.feature_imports.delete_one({"_id": ObjectId(fid)}
                                                if ObjectId.is_valid(fid)
                                                else {"_id": fid})
                self.import_analysis_status.delete_many({"feature_import_id": fid})
                deleted_import_ids.append(fid)
        return {
            "removed": True,
            "deleted_testcase_ids": sorted(deleted_case_ids),
            "removed_testcase_links": removed_case_links,
            "affected_feature_ids": sorted(affected_feature_ids),
            "deleted_feature_import_ids": deleted_import_ids,
        }

    def record_row_promotion(self, project_imported_row_id, project_id, feature_id,
                              version_number, testcase_id, match_score):
        self.project_imported_row_promotions.update_one(
            {"project_imported_row_id": project_imported_row_id,
             "feature_id": feature_id,
             "feature_version_number": version_number},
            {"$set": {
                "project_imported_row_id": project_imported_row_id,
                "project_id": project_id, "feature_id": feature_id,
                "feature_version_number": version_number,
                "promoted_testcase_id": testcase_id,
                "match_score": match_score,
                "promoted_at": time.time(), "updated_at": time.time()},
             "$setOnInsert": {"created_at": time.time()}},
            upsert=True)
        if ObjectId.is_valid(project_imported_row_id):
            self.project_imported_rows.update_one(
                {"_id": ObjectId(project_imported_row_id)},
                {"$inc": {"promotion_count": 1},
                 "$set": {"current_match_status": "matched_feature",
                          "needs_project_analysis": False}})

    def get_row_promotion(self, project_imported_row_id, feature_id=None):
        q = {"project_imported_row_id": project_imported_row_id}
        if feature_id:
            q["feature_id"] = feature_id
        r = self.project_imported_row_promotions.find_one(q, sort=[("promoted_at", -1)])
        if r:
            r["id"] = str(r.pop("_id"))
        return r

    def list_project_imported_rows(self, project_id, feature_id=None,
                                     unlinked_only=False, limit=200):
        """Project-pool listing. When feature_id passed, filter via the feature
        map; when unlinked_only=True, exclude rows already mapped to the feature."""
        out = []
        q = {"project_id": project_id}
        for r in self.project_imported_rows.find(q).sort("last_seen_at", -1).limit(limit):
            r["id"] = str(r.pop("_id"))
            mapped = self.project_imported_row_feature_map.count_documents({
                "project_imported_row_id": r["id"],
                "feature_id": feature_id or {"$exists": True}})
            r["mapped_to_feature"] = bool(mapped) if feature_id else None
            if feature_id and unlinked_only and r["mapped_to_feature"]:
                continue
            source = self.project_imported_row_sources.find_one(
                {"project_imported_row_id": r["id"]}, sort=[("observed_at", -1)])
            if source:
                r["latest_source"] = {
                    "feature_import_id": source.get("feature_import_id"),
                    "import_batch_id": source.get("import_batch_id"),
                    "feature_id": source.get("feature_id"),
                    "original_filename": source.get("original_filename"),
                    "sheet_name": source.get("sheet_name"),
                    "row_number": source.get("row_number"),
                }
            out.append(r)
        return out

    def list_project_imported_row_ids_for_source(self, project_id, feature_import_id=None,
                                                 original_filename=None, sheet_name=None):
        q = {}
        if feature_import_id:
            q["feature_import_id"] = feature_import_id
        if original_filename:
            q["original_filename"] = original_filename
        if sheet_name:
            q["sheet_name"] = sheet_name
        row_ids = []
        seen = set()
        for src in self.project_imported_row_sources.find(q):
            rid = src.get("project_imported_row_id")
            if not rid or rid in seen or not ObjectId.is_valid(rid):
                continue
            row = self.project_imported_rows.find_one(
                {"_id": ObjectId(rid), "project_id": project_id}, {"_id": 1})
            if not row:
                continue
            seen.add(rid)
            row_ids.append(rid)
        return row_ids

    def get_project_imported_row(self, rid):
        if not ObjectId.is_valid(rid):
            return None
        r = self.project_imported_rows.find_one({"_id": ObjectId(rid)})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def get_project_imported_row_by_hash(self, project_id, identity_hash):
        r = self.project_imported_rows.find_one({
            "project_id": project_id, "identity_hash": identity_hash})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def save_import_review_correction(self, project_id, feature_id, import_batch_id,
                                       version, payload, note, admin_id):
        self.project_imported_row_corrections.insert_one({
            "project_id": project_id, "feature_id": feature_id,
            "import_batch_id": import_batch_id,
            "feature_version_number": version,
            "correction_note": note or "",
            "correction_payload": payload,
            "row_count": len((payload or {}).get("rows") or []),
            "created_by": admin_id,
            "created_at": time.time(), "updated_at": time.time(),
        })

    def set_import_analysis_status(self, feature_import_id, status, details="",
                                     completed=False, result_json=None,
                                     pending_global=False):
        self.import_analysis_status.update_one(
            {"feature_import_id": feature_import_id},
            {"$set": {
                "feature_import_id": feature_import_id,
                "status": status, "details": details or status,
                "completed": completed,
                "pending_global_analysis": pending_global,
                "result_json": result_json,
                "updated_at": time.time(),
                "completed_at": (time.time() if completed else None)},
             "$setOnInsert": {"created_at": time.time(),
                              "started_at": time.time()}},
            upsert=True)

    def get_import_analysis_status(self, feature_import_id):
        return self.import_analysis_status.find_one(
            {"feature_import_id": feature_import_id})
