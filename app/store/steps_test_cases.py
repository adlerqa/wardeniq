"""Test steps and test cases: CRUD, display-id allocation, similarity search
(mongot + numpy fallback), and case/feature association.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md). `cosine_atlas` and
`VECTOR_INDEX` are shared cross-domain constants defined in store/base.py.
"""

import re
import time

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from store.base import VECTOR_INDEX, cosine_atlas


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


class StepsTestCasesMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def _all_step_vectors(self):
        return [(str(s["_id"]), s["embedding"]) for s in
                self.steps.find({}, {"embedding": 1})]

    def get_or_create_step(self, action, expected, embedding, auto_reuse: float):
        best_id, best_score = None, 0.0
        for sid, emb in self._all_step_vectors():
            sc = cosine_atlas(embedding, emb)
            if sc > best_score:
                best_id, best_score = sid, sc
        if best_id and best_score >= auto_reuse:
            self.steps.update_one({"_id": ObjectId(best_id)}, {"$inc": {"usage_count": 1}})
            return {"step_id": best_id, "origin": "reused", "score": round(best_score, 4)}
        sid = str(self.steps.insert_one({
            "action": action, "expected": expected, "embedding": embedding,
            "usage_count": 1, "created_at": time.time(), "updated_at": time.time()}).inserted_id)
        return {"step_id": sid, "origin": "new", "score": round(best_score, 4)}

    def update_step(self, sid, action, expected, embedding):
        self.steps.update_one({"_id": ObjectId(sid)}, {"$set": {
            "action": action, "expected": expected, "embedding": embedding,
            "updated_at": time.time()}})
        affected = self.cases.count_documents({"step_ids": sid})
        return {"updated": sid, "affected_cases": affected}

    def list_steps(self, limit=200, skip=0):
        # Fetch the page first, then compute usage counts in ONE aggregation
        # against cases.step_ids (indexed). Previously this was N count_documents
        # calls, one per step, which was the main cause of the step-library
        # loader appearing to hang on non-trivial datasets.
        steps = list(
            self.steps.find({}, {"embedding": 0})
            .sort("usage_count", -1)
            .skip(skip)
            .limit(limit)
        )
        ids = [str(s["_id"]) for s in steps]
        counts = {}
        if ids:
            pipeline = [
                {"$match": {"step_ids": {"$in": ids}}},
                {"$unwind": "$step_ids"},
                {"$match": {"step_ids": {"$in": ids}}},
                # Group on (case, count once) via $addToSet on the case's own _id,
                # not a raw $sum -- a single test case can legitimately reference
                # the same shared step more than once in its own step_ids array
                # (e.g. reusing "click the X button" at step 2 and step 5 of the
                # same script). $sum after $unwind counts every occurrence, so
                # that one case alone would inflate a step's count by 1 for each
                # repeat -- reproduced: a step used by 3 distinct cases, one of
                # which references it twice, reported "4 cases" in this listing
                # while the step's own "Used in Cases" detail (a plain find(),
                # which naturally returns each matching case once) correctly
                # listed 3. $addToSet dedupes back down to distinct cases.
                {"$group": {"_id": "$step_ids", "cases": {"$addToSet": "$_id"}}},
            ]
            for row in self.cases.aggregate(pipeline):
                counts[row["_id"]] = len(row["cases"])
        out = []
        for s in steps:
            s["id"] = str(s.pop("_id"))
            s["used_in_cases"] = counts.get(s["id"], 0)
            out.append(s)
        return out

    def resolve_steps(self, step_ids):
        by_id = {}
        for s in self.steps.find({"_id": {"$in": [ObjectId(i) for i in step_ids]}}):
            by_id[str(s["_id"])] = {"id": str(s["_id"]), "action": s.get("action"),
                                    "expected": s.get("expected"),
                                    "usage_count": s.get("usage_count", 1)}
        return [by_id[i] for i in step_ids if i in by_id]

    @staticmethod
    def _display_code(value, fallback):
        """Create a short readable code: words -> initials, one word -> first 3."""
        words = re.findall(r"[A-Za-z0-9]+", str(value or ""))
        if not words:
            return fallback
        if len(words) == 1:
            code = words[0][:3]
        else:
            code = "".join(word[0] for word in words[:4])
        return code.upper()

    def _assigned_prefix(self, group_id, base):
        """Return a stable, globally-unique display prefix for a feature group.
        First choice is `base` (PROJECT-FEATURE); if another group already owns it,
        the shortest numeric suffix that is free is used (NEA-LOG, NEA-LOG2, …).
        The mapping is persisted so a group always keeps the same prefix."""
        key = f"caseprefix:{group_id}"
        existing = self.counters.find_one({"_id": key})
        if existing and existing.get("prefix"):
            return existing["prefix"]
        candidate, n = base, 1
        while self.counters.find_one(
            {"kind": "caseprefix", "prefix": candidate, "_id": {"$ne": key}}
        ):
            n += 1
            candidate = f"{base}{n}"
        self.counters.update_one(
            {"_id": key},
            {"$set": {"kind": "caseprefix", "group_id": group_id,
                      "prefix": candidate, "updated_at": time.time()}},
            upsert=True,
        )
        return candidate

    def _case_display_context(self, feature_id, project_id=None):
        """Return (project_id, prefix, group_id). Numbering is per feature *group*
        so every feature's cases run 1..N; the prefix is unique per group."""
        feature = None
        if feature_id and ObjectId.is_valid(feature_id):
            feature = self.features.find_one(
                {"_id": ObjectId(feature_id)},
                {"name": 1, "project_id": 1, "group_id": 1},
            )
        resolved_project_id = project_id or (feature or {}).get("project_id")
        group_id = (feature or {}).get("group_id") or (
            feature_id if (feature and ObjectId.is_valid(feature_id)) else None
        )
        project = None
        if resolved_project_id and ObjectId.is_valid(resolved_project_id):
            project = self.projects.find_one(
                {"_id": ObjectId(resolved_project_id)}, {"name": 1}
            )
        project_code = self._display_code((project or {}).get("name"), "PRJ")
        feature_code = self._display_code((feature or {}).get("name"), "FEA")
        base = f"{project_code}-{feature_code}"
        prefix = self._assigned_prefix(group_id, base) if group_id else base
        return resolved_project_id, prefix, group_id

    def _next_case_display_id(self, feature_id, project_id=None):
        resolved_project_id, prefix, group_id = self._case_display_context(
            feature_id, project_id
        )
        # One sequence per feature group → each feature numbers its cases 1..N,
        # continuing across versions (carried cases keep their existing ids).
        counter_key = f"testcase:group:{group_id}" if group_id else f"testcase:{prefix}"
        counter = self.counters.find_one_and_update(
            {"_id": counter_key},
            {
                "$inc": {"value": 1},
                "$set": {
                    "kind": "testcase",
                    "project_id": resolved_project_id,
                    "group_id": group_id,
                    "prefix": prefix,
                    "updated_at": time.time(),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return f"{prefix}-{counter['value']}"

    def _backfill_case_display_ids(self):
        """Assign readable IDs once to legacy cases without changing Mongo IDs."""
        missing = list(self.cases.find(
            {
                "$or": [
                    {"display_id": {"$exists": False}},
                    {"display_id": None},
                    {"display_id": ""},
                ]
            },
            {"source_feature_id": 1, "project_id": 1, "created_at": 1},
        ).sort([("created_at", 1), ("_id", 1)]))
        for case in missing:
            cid = str(case["_id"])
            feature_id = case.get("source_feature_id")
            if not feature_id:
                association = self.assoc.find_one(
                    {"test_case_id": cid}, sort=[("created_at", 1)]
                )
                feature_id = (association or {}).get("feature_id")
            display_id = self._next_case_display_id(
                feature_id, case.get("project_id")
            )
            self.cases.update_one(
                {"_id": case["_id"], "$or": [
                    {"display_id": {"$exists": False}},
                    {"display_id": None},
                    {"display_id": ""},
                ]},
                {"$set": {"display_id": display_id}},
            )

    def _renumber_display_ids(self):
        """One-time migration: renumber every case per feature-group so ids read
        {prefix}-1..N (each feature starts at 1). Guarded by a flag so it runs once.
        The previous id is preserved in `display_id_legacy` — nothing is lost, and
        test cycles read the id live so they pick up the new numbers automatically."""
        flag_id = "migration:renumber_per_feature_v1"
        if (self.counters.find_one({"_id": flag_id}) or {}).get("done"):
            return

        feat_group = {}

        def group_of(fid):
            if not fid:
                return None
            if fid in feat_group:
                return feat_group[fid]
            g = None
            if ObjectId.is_valid(fid):
                f = self.features.find_one({"_id": ObjectId(fid)}, {"group_id": 1})
                if f:
                    g = f.get("group_id") or str(f["_id"])
            feat_group[fid] = g
            return g

        groups = {}
        for c in self.cases.find({}, {"source_feature_id": 1, "display_id": 1, "created_at": 1}):
            cid = str(c["_id"])
            fid = c.get("source_feature_id")
            if not fid:
                a = self.assoc.find_one({"test_case_id": cid}, sort=[("created_at", 1)])
                fid = (a or {}).get("feature_id")
            g = group_of(fid)
            if g:                       # leave cases we can't tie to a feature untouched
                groups.setdefault(g, []).append(c)

        if groups:
            def seq(did):
                m = re.search(r"(\d+)$", did or "")
                return int(m.group(1)) if m else 0

            # Phase 1 — park every affected case on a unique temp id (dodges the
            # unique index) while stashing the original id in display_id_legacy.
            for c in (c for lst in groups.values() for c in lst):
                self.cases.update_one({"_id": c["_id"]}, [{"$set": {
                    "display_id_legacy": {"$ifNull": ["$display_id_legacy", "$display_id"]},
                    "display_id": {"$concat": ["__mig_", {"$toString": "$_id"}]},
                }}])

            # Phase 2 — assign contiguous ids per group (original order preserved).
            for g, lst in groups.items():
                lst.sort(key=lambda c: (seq(c.get("display_id")), c.get("created_at") or 0, str(c["_id"])))
                prefix = self._group_prefix(g)
                for c in lst:
                    self.cases.update_one({"_id": c["_id"]},
                                          {"$set": {"display_id": self._alloc_display_id(g, prefix)}})

        self.counters.update_one({"_id": flag_id},
                                 {"$set": {"done": True, "at": time.time()}}, upsert=True)
        # Always self-heal: if any case is stuck on a temp id (e.g. a previous run
        # crashed mid-migration or two workers raced), give it a real id now.
        self._repair_temp_display_ids()

    def _group_prefix(self, group_id):
        """Resolve a group's display prefix (assigning + persisting one if needed)."""
        rep = (self.features.find_one({"_id": ObjectId(group_id)}, {"name": 1, "project_id": 1})
               if ObjectId.is_valid(group_id) else None) \
            or self.features.find_one({"group_id": group_id}, {"name": 1, "project_id": 1})
        pid = (rep or {}).get("project_id")
        project = (self.projects.find_one({"_id": ObjectId(pid)}, {"name": 1})
                   if pid and ObjectId.is_valid(pid) else None)
        base = (f"{self._display_code((project or {}).get('name'), 'PRJ')}"
                f"-{self._display_code((rep or {}).get('name'), 'FEA')}")
        return self._assigned_prefix(group_id, base)

    def _alloc_display_id(self, group_id, prefix):
        """Allocate the next free {prefix}-N for a group, skipping any id already
        taken and retrying on a unique-index clash (safe under concurrent workers)."""
        key = f"testcase:group:{group_id}"
        for _ in range(1000000):
            counter = self.counters.find_one_and_update(
                {"_id": key},
                {"$inc": {"value": 1},
                 "$set": {"kind": "testcase", "group_id": group_id,
                          "prefix": prefix, "updated_at": time.time()}},
                upsert=True, return_document=ReturnDocument.AFTER)
            candidate = f"{prefix}-{counter['value']}"
            if self.cases.find_one({"display_id": candidate}, {"_id": 1}):
                continue
            return candidate
        return f"{prefix}-{ObjectId()}"   # unreachable in practice

    def _repair_temp_display_ids(self):
        """Reassign any case still parked on a temporary `__mig_…` id to a real,
        per-feature display id. Idempotent and cheap when there is nothing to fix,
        so it can run on every startup."""
        stuck = list(self.cases.find(
            {"display_id": {"$regex": "^__mig_"}},
            {"source_feature_id": 1, "display_id_legacy": 1}))
        for c in stuck:
            cid = str(c["_id"])
            fid = c.get("source_feature_id")
            if not fid:
                a = self.assoc.find_one({"test_case_id": cid}, sort=[("created_at", 1)])
                fid = (a or {}).get("feature_id")
            _pid, prefix, group_id = self._case_display_context(fid)
            if not group_id:
                # Can't tie it to a feature — restore its original id if that's free.
                legacy = c.get("display_id_legacy")
                if legacy and not self.cases.find_one(
                        {"display_id": legacy, "_id": {"$ne": c["_id"]}}, {"_id": 1}):
                    self._safe_update_display_id(c["_id"], legacy)
                continue
            self._safe_update_display_id(c["_id"], self._alloc_display_id(group_id, prefix))

    def _safe_update_display_id(self, case_oid, display_id):
        try:
            self.cases.update_one({"_id": case_oid}, {"$set": {"display_id": display_id}})
        except DuplicateKeyError:
            pass   # another worker got there first; a later pass will settle it

    def _case_belongs_to_project(self, case_doc, project_id):
        if not project_id:
            return True
        if case_doc.get("project_id"):
            return case_doc.get("project_id") == project_id
        source_fid = case_doc.get("source_feature_id")
        if source_fid and ObjectId.is_valid(source_fid):
            source = self.features.find_one({"_id": ObjectId(source_fid)}, {"project_id": 1})
            if source and source.get("project_id") == project_id:
                return True
        for assoc in self.assoc.find({"test_case_id": str(case_doc["_id"])}, {"feature_id": 1}):
            fid = assoc.get("feature_id")
            if not fid or not ObjectId.is_valid(fid):
                continue
            feature = self.features.find_one({"_id": ObjectId(fid)}, {"project_id": 1})
            if feature and feature.get("project_id") == project_id:
                return True
        return False

    def _all_case_vectors(self, project_id=None):
        out = []
        for c in self.cases.find({}, {"embedding": 1, "title": 1, "type": 1,
                                      "project_id": 1, "source_feature_id": 1,
                                      "metadata": 1, "identity_hash": 1,
                                      "test_slug": 1}):
            if self._case_belongs_to_project(c, project_id):
                out.append((
                    str(c["_id"]), c["embedding"], c.get("title"), c.get("type"),
                    c.get("metadata") or {}, c.get("identity_hash"), c.get("test_slug"),
                ))
        return out

    def find_similar_cases(self, embedding, suggest: float, exclude_id=None, top=5,
                           project_id=None):
        """Nearest existing test cases by embedding (for dedup/reuse).

        mongot `$vectorSearch` (ANN) is tried first so this scales as the case store
        grows to tens of thousands+; the exact numpy scan is a true fallback used when
        mongot is unavailable (dev without a search cluster, index still building, or
        a query error). Both score in the same (1+cos)/2 space, so `suggest` behaves
        identically on either path.
        """
        try:
            got = self._find_similar_cases_mongot(embedding, suggest, exclude_id, top, project_id)
            if got is not None:
                return got
        except Exception:  # noqa: BLE001 — any mongot/index problem → exact numpy fallback
            pass
        # mongot unavailable — fall back to exact numpy, but only if the store is small
        # enough to scan in memory. On a large store we fail SAFE (dedup degrades to
        # "no reuse" for this call) rather than risk OOM / multi-second latency.
        # NOTE: the [] below is AMBIGUOUS to a caller - it means "we didn't look", not
        # "nothing similar exists". Check `store.search_degraded('dedup')` to tell them
        # apart before reporting a run as clean.
        if not self._numpy_fallback_ok("dedup"):
            return []
        return self._find_similar_cases_numpy(embedding, suggest, exclude_id, top, project_id)

    def _find_similar_cases_mongot(self, embedding, suggest, exclude_id, top, project_id):
        # The cases vector index only declares a `type` filter, so project scoping is
        # done in Python over a generous ANN candidate pool. Near-duplicates score very
        # high, so they reliably surface within the pool even before filtering.
        pool = max(200, top * 40)
        pipeline = [
            {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding",
                               "queryVector": embedding, "numCandidates": pool, "limit": pool}},
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {"$project": {"title": 1, "type": 1, "project_id": 1, "source_feature_id": 1,
                          "metadata": 1, "identity_hash": 1, "test_slug": 1, "score": 1}},
        ]
        out = []
        for c in self.cases.aggregate(pipeline):
            cid = str(c["_id"])
            if cid == exclude_id or not self._case_belongs_to_project(c, project_id):
                continue
            sc = round(float(c.get("score", 0.0)), 4)
            if sc < suggest:
                continue
            out.append({"case_id": cid, "title": c.get("title"), "type": c.get("type"),
                        "score": sc, "metadata": c.get("metadata") or {},
                        "identity_hash": c.get("identity_hash"), "test_slug": c.get("test_slug")})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:top]

    def _find_similar_cases_numpy(self, embedding, suggest, exclude_id, top, project_id):
        scored = []
        for cid, emb, title, ctype, metadata, identity_hash, test_slug in self._all_case_vectors(
            project_id=project_id
        ):
            if cid == exclude_id:
                continue
            sc = cosine_atlas(embedding, emb)
            if sc >= suggest:
                scored.append({
                    "case_id": cid,
                    "title": title,
                    "type": ctype,
                    "score": round(sc, 4),
                    "metadata": metadata,
                    "identity_hash": identity_hash,
                    "test_slug": test_slug,
                })
        return sorted(scored, key=lambda x: x["score"], reverse=True)[:top]

    def create_case(self, title, ctype, priority, preconditions, step_ids, tags,
                    embedding, feature_id, similar_to=None, project_id=None,
                    identity_hash=None, test_slug=None, metadata=None):
        resolved_project_id, _, _ = self._case_display_context(feature_id, project_id)
        display_id = self._next_case_display_id(feature_id, resolved_project_id)
        cid = str(self.cases.insert_one({
            "title": title, "type": ctype, "priority": priority,
            "preconditions": preconditions, "step_ids": step_ids, "tags": tags,
            "embedding": embedding, "source_feature_id": feature_id,
            "project_id": resolved_project_id, "identity_hash": identity_hash,
            "test_slug": test_slug, "metadata": metadata or {},
            "display_id": display_id,
            "execution_status": "untested",
            "similar_to": similar_to or [], "created_at": time.time()}).inserted_id)
        return cid

    def find_case_by_identity(self, project_id, identity_hash=None, test_slug=None):
        if identity_hash:
            for c in self.cases.find({"identity_hash": identity_hash}):
                if self._case_belongs_to_project(c, project_id):
                    c["id"] = str(c.pop("_id"))
                    return c
        if test_slug:
            legacy_query = {
                "test_slug": test_slug,
                "$or": [
                    {"identity_hash": None},
                    {"identity_hash": {"$exists": False}},
                    {"identity_hash": ""},
                ],
            }
            for c in self.cases.find(legacy_query):
                if self._case_belongs_to_project(c, project_id):
                    c["id"] = str(c.pop("_id"))
                    return c
        return None

    def resolve_case_reference(self, reference_key=None, title=None, project_id=None):
        """Resolve fusion references that may be Mongo ids or Node-style composite keys."""
        candidate_ids = []
        raw = str(reference_key or "").strip()
        if raw:
            candidate_ids.append(raw)
            candidate_ids.extend(part for part in raw.split("::") if part)
        for candidate in reversed(candidate_ids):
            if not ObjectId.is_valid(candidate):
                continue
            c = self.cases.find_one({"_id": ObjectId(candidate)})
            if c and (not project_id or not c.get("project_id") or c.get("project_id") == project_id):
                c["id"] = str(c.pop("_id"))
                return c
        if title:
            for c in self.cases.find({"title": title}):
                if not self._case_belongs_to_project(c, project_id):
                    continue
                c["id"] = str(c.pop("_id"))
                return c
        return None

    def associate(self, feature_id, case_id, origin, score=None):
        try:
            self.assoc.insert_one({"feature_id": feature_id, "test_case_id": case_id,
                                   "origin": origin, "score": score, "created_at": time.time()})
        except Exception:  # duplicate association — ignore
            pass

    def feature_count_for_case(self, case_id):
        return self.assoc.count_documents({"test_case_id": case_id})

    def case_exists(self, case_id):
        return bool(case_id and ObjectId.is_valid(case_id)
                    and self.cases.find_one({"_id": ObjectId(case_id)}, {"_id": 1}))

    def get_feature_cases(self, fid):
        case_ids = [a["test_case_id"] for a in self.assoc.find({"feature_id": fid})]
        origin = {a["test_case_id"]: a for a in self.assoc.find({"feature_id": fid})}
        # "integration" = a case that ALSO belongs to a different feature GROUP
        # (linked/reused from another functionality) -- not merely carried across
        # this feature's own versions. Compare feature groups, not feature ids.
        _cur = self.features.find_one({"_id": ObjectId(fid)}, {"group_id": 1})
        _cur_group = (_cur or {}).get("group_id") or fid
        cross_feature = set()
        if case_ids:
            _case_feats, _feat_ids = {}, set()
            for a in self.assoc.find({"test_case_id": {"$in": case_ids}},
                                     {"test_case_id": 1, "feature_id": 1}):
                _case_feats.setdefault(a["test_case_id"], set()).add(a["feature_id"])
                _feat_ids.add(a["feature_id"])
            _grp = {}
            _valid = [ObjectId(x) for x in _feat_ids if ObjectId.is_valid(x)]
            for f in self.features.find({"_id": {"$in": _valid}}, {"group_id": 1}):
                _grp[str(f["_id"])] = f.get("group_id") or str(f["_id"])
            for _cid, _fset in _case_feats.items():
                if any((_grp.get(x) or x) != _cur_group for x in _fset):
                    cross_feature.add(_cid)
        out = []
        for c in self.cases.find({"_id": {"$in": [ObjectId(i) for i in case_ids]}}):
            cid = str(c["_id"])
            out.append({
                "id": cid, "display_id": c.get("display_id"),
                "title": c.get("title"), "type": c.get("type"),
                "priority": c.get("priority"), "preconditions": c.get("preconditions"),
                "tags": c.get("tags", []), "steps": self.resolve_steps(c.get("step_ids", [])),
                "similar_to": c.get("similar_to", []),
                "identity_hash": c.get("identity_hash"), "test_slug": c.get("test_slug"),
                "metadata": c.get("metadata", {}),
                "execution_status": c.get("execution_status", "untested"),
                "shared_with_features": self.feature_count_for_case(cid),
                # GAP3: "this generated case is also backed by an imported QA row".
                "import_backed": bool(c.get("import_backed")),
                "import_overlay": (c.get("metadata") or {}).get("import_overlay"),
                # True when the case itself came from an uploaded sheet.
                "imported": bool(c.get("project_imported_row_id")
                                  or (c.get("metadata") or {}).get("project_imported_row_id")),
                "association": {"origin": origin[cid].get("origin"),
                                "score": origin[cid].get("score")},
                "inherited": cid in cross_feature,
                # "integration" when the case is shared with another feature group.
                "category": ("integration" if cid in cross_feature else c.get("type")),
            })
        order = {"functional": 0, "e2e": 1, "api": 2, "ui": 3, "nfr": 4}

        def _seq(display_id):
            m = re.search(r"(\d+)$", display_id or "")
            return int(m.group(1)) if m else 10 ** 9

        # category first, then ascending by the numeric part of the display id (EC-LOG-1, 2, 3…)
        return sorted(out, key=lambda x: (order.get(x["type"], 9), _seq(x.get("display_id"))))

    def set_case_import_overlay(self, case_id, overlay):
        """GAP3: stamp (or clear) an import-backed overlay on a generated test case."""
        if not ObjectId.is_valid(case_id):
            return
        if overlay:
            self.cases.update_one({"_id": ObjectId(case_id)},
                                  {"$set": {"import_backed": True,
                                            "metadata.import_overlay": overlay}})
        else:
            self.cases.update_one({"_id": ObjectId(case_id)},
                                  {"$set": {"import_backed": False},
                                   "$unset": {"metadata.import_overlay": ""}})

    def search_cases(self, query_embedding, limit=8, ctype=None):
        """Semantic test-case search. mongot `$vectorSearch` first (scales); exact
        numpy scan as a true fallback when mongot is unavailable."""
        stage = {"index": VECTOR_INDEX, "path": "embedding",
                 "queryVector": query_embedding, "numCandidates": limit * 12, "limit": limit}
        if ctype:
            stage["filter"] = {"type": {"$eq": ctype}}
        pipeline = [{"$vectorSearch": stage},
                    {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                    {"$project": {"embedding": 0}}]
        try:
            out = []
            for c in self.cases.aggregate(pipeline):
                cid = str(c["_id"])
                out.append({"id": cid, "title": c.get("title"),
                            "type": c.get("type"), "priority": c.get("priority"),
                            "tags": c.get("tags", []), "score": round(c.get("score", 0), 4),
                            "steps": self.resolve_steps(c.get("step_ids", [])),
                            "shared_with_features": self.feature_count_for_case(cid)})
            return out, pipeline
        except Exception:  # noqa: BLE001 — mongot down / index not ready → numpy fallback
            if not self._numpy_fallback_ok("case search"):
                return [], None
            return self._search_cases_numpy(query_embedding, limit, ctype), None

    def _search_cases_numpy(self, query_embedding, limit, ctype=None):
        q = {"type": ctype} if ctype else {}
        scored = []
        for c in self.cases.find(q, {"title": 1, "type": 1, "priority": 1, "tags": 1,
                                     "step_ids": 1, "embedding": 1}):
            emb = c.get("embedding")
            if not emb:
                continue
            scored.append((cosine_atlas(query_embedding, emb), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sc, c in scored[:limit]:
            cid = str(c["_id"])
            out.append({"id": cid, "title": c.get("title"), "type": c.get("type"),
                        "priority": c.get("priority"), "tags": c.get("tags", []),
                        "score": round(float(sc), 4),
                        "steps": self.resolve_steps(c.get("step_ids", [])),
                        "shared_with_features": self.feature_count_for_case(cid)})
        return out

    def cases_brief(self, case_ids):
        """Compact {id,title,type,steps-summary} for feeding the coverage LLM."""
        out = []
        for c in self.cases.find({"_id": {"$in": [ObjectId(i) for i in case_ids]}},
                                 {"embedding": 0}):
            steps = self.resolve_steps(c.get("step_ids", []))
            out.append({"id": str(c["_id"]), "title": c.get("title"), "type": c.get("type"),
                        "priority": c.get("priority"), "display_id": c.get("display_id"),
                        "steps": [f"{s['action']} -> {s['expected']}" for s in steps]})
        return out

    def get_case(self, cid):
        c = self.cases.find_one({"_id": ObjectId(cid)})
        if not c:
            return None
        associations = list(self.assoc.find({"test_case_id": cid}, {"_id": 0}))
        feats = [a["feature_id"] for a in associations]
        fnames = []
        for fid in feats:
            f = self.features.find_one(
                {"_id": ObjectId(fid)},
                {"name": 1, "version": 1, "project_id": 1},
            )
            if f:
                association = next(
                    (a for a in associations if a.get("feature_id") == fid), {}
                )
                fnames.append({
                    "id": fid,
                    "name": f.get("name"),
                    "version": f.get("version", 1),
                    "project_id": f.get("project_id"),
                    "origin": association.get("origin"),
                    "score": association.get("score"),
                })
        return {"id": cid, "display_id": c.get("display_id"),
                "title": c.get("title"), "type": c.get("type"),
                "priority": c.get("priority"), "preconditions": c.get("preconditions"),
                "tags": c.get("tags", []), "steps": self.resolve_steps(c.get("step_ids", [])),
                "features": fnames, "shared_with_features": len(feats),
                "metadata": c.get("metadata", {}),
                "execution_status": c.get("execution_status", "untested"),
                "execution_note": c.get("execution_note", ""),
                "executed_at": c.get("executed_at"),
                "source_feature_id": c.get("source_feature_id"),
                # True when this case originated from an uploaded sheet (direct import
                # OR reused across features) — drives the "Imported from sheet" label.
                "imported": bool(c.get("project_imported_row_id")
                                  or (c.get("metadata") or {}).get("project_imported_row_id")),
                "import_backed": bool(c.get("import_backed")),
                "import_overlay": (c.get("metadata") or {}).get("import_overlay"),
                "created_at": c.get("created_at"), "updated_at": c.get("updated_at")}

    def list_test_cases(self, project_id=None, feature_id=None, ctype=None,
                        tag=None, q=None, status="active", execution_status=None,
                        lineage=None, step_id=None,
                        limit=50, skip=0):
        active_fids, _ = self.active_feature_ids()
        active = self.active_case_ids(active_fids)
        # scope
        if feature_id:
            scope = set(self.feature_test_case_ids(feature_id))
        elif project_id:
            scope = set()
            for fid in [str(f["_id"]) for f in self.features.find({"project_id": project_id}, {"_id": 1})]:
                scope.update(self.feature_test_case_ids(fid))
        else:
            scope = None
        # status → restrict the id set (active = on a latest version; deprecated = retired only)
        idset = None
        if status == "active":
            idset = (scope & active) if scope is not None else active
        elif status == "deprecated":
            base = scope if scope is not None else {str(c["_id"]) for c in self.cases.find({}, {"_id": 1})}
            idset = base - active
        else:  # all
            idset = scope
        query = {}
        if step_id:
            query["step_ids"] = step_id
        and_clauses = []
        if idset is not None:
            query["_id"] = {"$in": [ObjectId(i) for i in idset]}
        if ctype:
            query["type"] = ctype
        if tag:
            query["tags"] = tag
        if q:
            pattern = {"$regex": re.escape(q), "$options": "i"}
            and_clauses.append({"$or": [
                {"title": pattern},
                {"display_id": pattern},
            ]})
        if execution_status == "untested":
            and_clauses.append({"$or": [
                {"execution_status": "untested"},
                {"execution_status": {"$exists": False}},
                {"execution_status": None},
            ]})
        elif execution_status:
            query["execution_status"] = execution_status
        inherited_origins = {"reused", "carried", "carried_repaired", "inherited", "adapted"}
        association_rows = {}
        if feature_id:
            association_rows = {
                row["test_case_id"]: row
                for row in self.assoc.find({"feature_id": feature_id}, {"_id": 0})
            }
        elif lineage:
            for row in self.assoc.find({}, {"_id": 0}).sort("created_at", 1):
                cid = row["test_case_id"]
                existing = association_rows.get(cid)
                if not existing or (
                    row.get("origin") in inherited_origins
                    and existing.get("origin") not in inherited_origins
                ):
                    association_rows[cid] = row
        if lineage:
            matching_ids = {
                cid for cid, association in association_rows.items()
                if (
                    lineage == "inherited"
                    and association.get("origin") in inherited_origins
                ) or (
                    lineage == "created"
                    and association.get("origin") not in inherited_origins
                )
            }
            lineage_oids = [ObjectId(cid) for cid in matching_ids if ObjectId.is_valid(cid)]
            if "_id" in query:
                allowed = set(query["_id"].get("$in", []))
                query["_id"]["$in"] = [oid for oid in lineage_oids if oid in allowed]
            else:
                query["_id"] = {"$in": lineage_oids}
        if and_clauses:
            query["$and"] = and_clauses
        total = self.cases.count_documents(query)
        rows = []
        for c in self.cases.find(query, {"embedding": 0}).sort("_id", 1).skip(skip).limit(limit):
            cid = str(c["_id"])
            association = association_rows.get(cid)
            if not association:
                associations = list(self.assoc.find(
                    {"test_case_id": cid}, {"_id": 0}
                ).sort("created_at", 1))
                association = next(
                    (a for a in associations if a.get("origin") in inherited_origins),
                    associations[0] if associations else {},
                )
            source_feature_name = None
            source_fid = c.get("source_feature_id")
            if source_fid and ObjectId.is_valid(source_fid):
                source = self.features.find_one(
                    {"_id": ObjectId(source_fid)}, {"name": 1}
                )
                source_feature_name = (source or {}).get("name")
            rows.append({"id": cid, "display_id": c.get("display_id"),
                         "title": c.get("title"), "type": c.get("type"),
                         "priority": c.get("priority"), "tags": c.get("tags", []),
                         "step_count": len(c.get("step_ids", [])),
                         "shared_with_features": self.feature_count_for_case(cid),
                         "execution_status": c.get("execution_status", "untested"),
                         "association_origin": (association or {}).get("origin"),
                         "inherited": (association or {}).get("origin") in inherited_origins,
                         "source_feature_name": source_feature_name,
                         # True for ANY case sourced from an uploaded sheet (promoted
                         # directly OR reused across features) — so the UI can say
                         # "Imported from sheet" rather than "Inherited from <feature>".
                         "imported": bool(c.get("project_imported_row_id")
                                  or (c.get("metadata") or {}).get("project_imported_row_id")),
                         "deprecated": cid not in active})
        return {"total": total, "items": rows}

    def update_case(self, cid, title, ctype, priority, preconditions, tags, step_ids, embedding):
        self.cases.update_one({"_id": ObjectId(cid)}, {"$set": {
            "title": title, "type": ctype, "priority": priority,
            "preconditions": preconditions, "tags": tags, "step_ids": step_ids,
            "embedding": embedding, "updated_at": time.time()}})

    def update_case_execution(self, cid, status, note=""):
        result = self.cases.update_one({"_id": ObjectId(cid)}, {"$set": {
            "execution_status": status,
            "execution_note": note,
            "executed_at": time.time(),
            "updated_at": time.time(),
        }})
        return result.matched_count > 0

    def all_tags(self):
        return sorted({t for c in self.cases.find({}, {"tags": 1}) for t in c.get("tags", [])})

    def delete_case(self, cid, force=False):
        linked_features = self.feature_count_for_case(cid)
        if linked_features > 1 and not force:
            return {
                "deleted": False,
                "requires_force": True,
                "linked_features": linked_features,
                "reason": (
                    f"test case is linked to {linked_features} features; "
                    "confirm global deletion"
                ),
            }
        self.cases.delete_one({"_id": ObjectId(cid)})
        self.assoc.delete_many({"test_case_id": cid})
        self.cleanup_orphaned_steps()
        return {
            "deleted": True,
            "deleted_case": cid,
            "removed_feature_links": linked_features,
        }

    def unlink_case_from_feature(self, fid, cid):
        result = self.assoc.delete_one({"feature_id": fid, "test_case_id": cid})
        if not result.deleted_count:
            return {"removed": False, "reason": "test case is not linked to this feature"}
        remaining = self.feature_count_for_case(cid)
        deleted_orphan = False
        if remaining == 0:
            self.cases.delete_one({"_id": ObjectId(cid)})
            deleted_orphan = True
            self.cleanup_orphaned_steps()
        return {
            "removed": True,
            "feature_id": fid,
            "test_case_id": cid,
            "remaining_feature_links": remaining,
            "deleted_orphan": deleted_orphan,
        }

    def create_step(self, action, expected, embedding):
        return str(self.steps.insert_one({
            "action": action, "expected": expected, "embedding": embedding,
            "usage_count": 0, "created_at": time.time(), "updated_at": time.time()}).inserted_id)

    def delete_step(self, sid):
        used = self.cases.count_documents({"step_ids": sid})
        if used:
            return {"deleted": False, "reason": f"step is used in {used} case(s)"}
        self.steps.delete_one({"_id": ObjectId(sid)})
        return {"deleted": True}

    def cleanup_orphaned_steps(self):
        """Delete all test steps that are not referenced by any test case."""
        referenced_sids = set()
        for c in self.cases.find({}, {"step_ids": 1}):
            for sid in c.get("step_ids", []):
                if sid:
                    try:
                        referenced_sids.add(ObjectId(sid) if isinstance(sid, str) else sid)
                    except Exception:  # noqa: BLE001
                        pass
        self.steps.delete_many({"_id": {"$nin": list(referenced_sids)}})
