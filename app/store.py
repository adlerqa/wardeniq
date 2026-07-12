"""Normalized QA store on Percona MongoDB + mongot.

Collections
  features         {name, project, source, text, summary, embedding}
  test_steps       {action, expected, embedding, usage_count}        ← atomic, reusable
  test_cases       {title, type, priority, preconditions, step_ids[], tags,
                    embedding, source_feature_id, similar_to[]}        ← references steps
  associations     {feature_id, test_case_id, origin, score}          ← many-to-many

Key properties
  * A test case references steps by id → editing a step propagates everywhere.
  * A test case can be associated to many features (reuse without duplication).
  * Dedup uses cosine similarity (Atlas score space = (1+cos)/2).
"""
import math
import os
import re
import time
from bson import ObjectId
from pymongo import MongoClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.operations import SearchIndexModel

VECTOR_INDEX = "vector_index"
TEXT_INDEX = "text_index"

# Safety cap for the EXACT numpy fallback. numpy loads every vector into app RAM
# and scans linearly, so on a large store (mongot down / index rebuilding) it would
# be slow and could OOM the process. Above this many docs we fail SAFE (degraded,
# loudly logged) instead of attempting a full in-memory scan. Override via env.
NUMPY_FALLBACK_MAX_DOCS = int(os.getenv("NUMPY_FALLBACK_MAX_DOCS", "20000"))


def cosine_atlas(a, b) -> float:
    """Cosine similarity mapped to Atlas score space [0,1] (1 = identical)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return (1 + dot / (na * nb)) / 2


class Store:
    def __init__(self, uri: str, db_name: str, dim: int):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.dim = dim
        self.projects = self.db["projects"]
        self.features = self.db["features"]
        self.steps = self.db["test_steps"]
        self.cases = self.db["test_cases"]
        self.assoc = self.db["associations"]
        self.fchunks = self.db["feature_chunks"]
        self.code_chunks = self.db["code_chunks"]
        self.code_index = self.db["code_index"]   # per-repo index freshness (head sha)
        self.code_cov = self.db["code_coverage"]
        self.repos = self.db["repos"]
        self.prs = self.db["pull_requests"]
        self.coverage = self.db["pr_coverage"]
        self.commit_analysis = self.db["commit_analysis"]
        self.users = self.db["users"]
        self.validator_runs = self.db["validator_runs"]
        self.validator_questions = self.db["validator_questions"]
        self.validator_answers = self.db["validator_answers"]
        self.test_plan_runs = self.db["test_plan_runs"]
        self.counters = self.db["counters"]

    def ping(self):
        self.client.admin.command("ping"); return True

    # ---- indexes -------------------------------------------------------------
    def ensure_indexes(self):
        for name in ["projects", "features", "feature_chunks", "code_chunks", "code_coverage",
                     "test_steps", "test_cases", "associations", "repos", "pull_requests",
                     "pr_coverage", "users", "validator_runs", "validator_questions",
                     "validator_answers", "test_plan_runs", "test_cycles", "counters",
                     "feature_imports", "project_imported_rows",
                     "project_imported_row_sources", "project_imported_row_feature_map",
                     "project_imported_row_promotions",
                     "project_imported_row_corrections", "import_analysis_status"]:
            if name not in self.db.list_collection_names():
                self.db.create_collection(name)
        self.users.create_index([("email", 1)], unique=True)
        self.assoc.create_index([("feature_id", 1), ("test_case_id", 1)], unique=True)
        self.repos.create_index([("project_id", 1), ("full_name", 1)], unique=True)
        self.prs.create_index([("repo_id", 1), ("number", 1)], unique=True)
        self.coverage.create_index([("pr_id", 1)], unique=True)
        self.validator_questions.create_index([("validator_run_id", 1), ("order_index", 1)])
        self.validator_answers.create_index([("validator_run_id", 1), ("question_id", 1)], unique=True)
        self.test_plan_runs.create_index([("feature_id", 1), ("run_number", 1)], unique=True)
        self.db["test_cycles"].create_index(
            [("project_id", 1), ("name_key", 1)],
            unique=True,
            partialFilterExpression={"name_key": {"$type": "string"}},
        )
        self.cases.create_index([("project_id", 1), ("identity_hash", 1)])
        self.cases.create_index([("project_id", 1), ("test_slug", 1)])
        # Backs the step-library usage count (previously an unindexed collscan
        # per step, which turned /api/steps into an O(N) hot path).
        self.cases.create_index([("step_ids", 1)])
        # Cheap lookup for the stale-job sweeper (running + updated_at range).
        self.db["jobs"].create_index([("status", 1), ("updated_at", 1)])
        self.feature_imports.create_index([("project_id", 1), ("feature_id", 1), ("file_sha256", 1)])
        self.feature_imports.create_index([("project_id", 1), ("file_sha256", 1)])
        self.feature_imports.create_index([("project_id", 1), ("content_signature_sha256", 1)])
        self.project_imported_rows.create_index([("project_id", 1), ("identity_hash", 1)], unique=True)
        self.project_imported_rows.create_index([("project_id", 1), ("current_match_status", 1), ("last_seen_at", -1)])
        self.project_imported_row_sources.create_index([
            ("project_imported_row_id", 1), ("import_batch_id", 1),
            ("original_filename", 1), ("sheet_name", 1), ("row_number", 1)
        ], unique=True)
        self.project_imported_row_sources.create_index([("feature_import_id", 1)])
        self.project_imported_row_feature_map.create_index([
            ("project_imported_row_id", 1), ("feature_id", 1)
        ], unique=True)
        self.project_imported_row_promotions.create_index([
            ("project_imported_row_id", 1), ("feature_id", 1),
            ("feature_version_number", 1)
        ], unique=True)
        self._backfill_case_display_ids()
        self.cases.create_index([("display_id", 1)], unique=True, sparse=True)
        self._renumber_display_ids()   # one-time: per-feature numbering (1..N)
        self._repair_temp_display_ids()   # self-heal any ids stuck on a temp value
        self._backfill_settings_configured()
        self._ensure_vector(self.features, extra_filters=["project_id"])
        self._ensure_vector(self.fchunks, extra_filters=["project_id", "feature_id"])
        self._ensure_vector(self.code_chunks, extra_filters=["project_id", "repo_id"])
        self._ensure_vector(self.steps)
        self._ensure_vector(self.cases, extra_filters=["type"])
        self._ensure_text(self.cases)

    def _existing(self, coll):
        try:
            return {i.get("name") for i in coll.list_search_indexes()}
        except Exception:  # noqa: BLE001
            return set()

    def _ensure_vector(self, coll, extra_filters=None):
        if VECTOR_INDEX in self._existing(coll):
            return
        fields = [{"type": "vector", "path": "embedding",
                   "numDimensions": self.dim, "similarity": "cosine"}]
        for f in (extra_filters or []):
            fields.append({"type": "filter", "path": f})
        coll.create_search_index(SearchIndexModel(
            definition={"fields": fields}, name=VECTOR_INDEX, type="vectorSearch"))

    def _ensure_text(self, coll):
        if TEXT_INDEX in self._existing(coll):
            return
        coll.create_search_index(SearchIndexModel(
            definition={"mappings": {"dynamic": False, "fields": {
                "title": {"type": "string"},
                "type": [{"type": "token"}, {"type": "stringFacet"}],
                "tags": [{"type": "token"}, {"type": "stringFacet"}],
            }}}, name=TEXT_INDEX, type="search"))

    def _vector_specs(self):
        """(collection, filter_fields) for every vector-indexed collection."""
        return [
            (self.features, ["project_id"]),
            (self.fchunks, ["project_id", "feature_id"]),
            (self.code_chunks, ["project_id", "repo_id"]),
            (self.steps, None),
            (self.cases, ["type"]),
        ]

    def drop_vector_indexes(self):
        """Drop every vectorSearch index (before switching embedding dimension)."""
        for coll, _ in self._vector_specs():
            try:
                if VECTOR_INDEX in self._existing(coll):
                    coll.drop_search_index(VECTOR_INDEX)
            except Exception:  # noqa: BLE001
                pass

    def create_vector_indexes(self, dim):
        """(Re)create every vectorSearch index at `dim`. Resilient to mongot's
        asynchronous drop/create: retries while an old index is still going away."""
        import time as _t
        self.dim = int(dim)
        for coll, filters in self._vector_specs():
            fields = [{"type": "vector", "path": "embedding",
                       "numDimensions": self.dim, "similarity": "cosine"}]
            for f in (filters or []):
                fields.append({"type": "filter", "path": f})
            for _ in range(24):
                try:
                    if VECTOR_INDEX in self._existing(coll):
                        _t.sleep(5)   # old index still dropping — wait it out
                        continue
                    coll.create_search_index(SearchIndexModel(
                        definition={"fields": fields}, name=VECTOR_INDEX, type="vectorSearch"))
                    break
                except Exception:  # noqa: BLE001
                    _t.sleep(5)

    def reembed_all(self, embed, progress=None):
        """Re-embed every stored vector with `embed(text)->vector`, reproducing the
        original source text per collection. code_chunks are transient (rebuilt on
        the next Mind-Map run) so they're cleared rather than re-embedded. Call
        drop_vector_indexes() before this and create_vector_indexes(dim) after."""
        def prog(s, p):
            if progress:
                progress(s, p)

        counts = {}
        prog("Clearing code index (rebuilt on next analysis)", 5)
        try:
            self.code_chunks.delete_many({})
        except Exception:  # noqa: BLE001
            pass

        prog("Re-embedding features", 12)
        n = 0
        for f in self.features.find({}, {"text": 1}):
            txt = (f.get("text") or "")[:2000]
            if not txt:
                continue
            self.features.update_one({"_id": f["_id"]}, {"$set": {"embedding": embed(txt)}})
            n += 1
        counts["features"] = n

        prog("Re-embedding document chunks", 35)
        n = 0
        for c in self.fchunks.find({}, {"text": 1}):
            txt = c.get("text") or ""
            if not txt:
                continue
            self.fchunks.update_one({"_id": c["_id"]}, {"$set": {"embedding": embed(txt)}})
            n += 1
        counts["feature_chunks"] = n

        prog("Re-embedding test steps", 58)
        n = 0
        for s in self.steps.find({}, {"action": 1, "expected": 1}):
            text = f"{s.get('action', '')}. Expected: {s.get('expected', '')}"
            self.steps.update_one({"_id": s["_id"]}, {"$set": {"embedding": embed(text)}})
            n += 1
        counts["test_steps"] = n

        prog("Re-embedding test cases", 78)
        n = 0
        for c in self.cases.find({}, {"title": 1, "step_ids": 1}):
            steps = []
            for sid in (c.get("step_ids") or []):
                try:
                    st = self.steps.find_one({"_id": ObjectId(sid)}, {"action": 1, "expected": 1})
                except Exception:  # noqa: BLE001
                    st = None
                if st:
                    steps.append(f"{st.get('action', '')} {st.get('expected', '')}")
            text = (c.get("title") or "Untitled test case") + " " + " ".join(steps)
            self.cases.update_one({"_id": c["_id"]}, {"$set": {"embedding": embed(text)}})
            n += 1
        counts["test_cases"] = n
        prog("Finalizing", 94)
        return counts

    def index_status(self):
        out = {}
        for nm, coll in [("features", self.features), ("test_steps", self.steps),
                         ("test_cases", self.cases)]:
            try:
                out[nm] = {i.get("name"): i.get("queryable", False)
                           for i in coll.list_search_indexes()}
            except Exception:  # noqa: BLE001
                out[nm] = {}
        return out

    def db_info(self):
        """Read-only snapshot of the connected database for the Configuration UI.

        No credentials are ever returned — only hostnames, topology, version, and
        whether Vector Search is available. Deployment (which DB) stays in .env; this
        is purely observability. Every field is best-effort; failures degrade to None.
        """
        info = {"hosts": [], "server_version": None, "replica_set": None,
                "members": [], "search_available": False, "indexes": {}}
        # Hosts as configured on the client (already credential-free — pymongo parses
        # user:pass out of the URI into auth options, not into .nodes/.address).
        try:
            info["hosts"] = sorted({f"{h}:{p}" for (h, p) in self.client.nodes}) \
                or ([f"{self.client.address[0]}:{self.client.address[1]}"]
                    if self.client.address else [])
        except Exception:  # noqa: BLE001
            pass
        try:
            info["server_version"] = self.client.server_info().get("version")
        except Exception:  # noqa: BLE001
            pass
        # Replica-set topology (name + per-member health/state).
        try:
            st = self.client.admin.command("replSetGetStatus")
            info["replica_set"] = st.get("set")
            for m in st.get("members", []):
                info["members"].append({
                    "name": m.get("name"),
                    "state": m.get("stateStr"),          # PRIMARY / SECONDARY / ...
                    "health": int(m.get("health", 0)) == 1,
                    "self": bool(m.get("self", False)),
                })
        except Exception:  # noqa: BLE001
            pass  # standalone / Atlas serverless / no permission → leave empty
        # Vector Search availability: if we can list search indexes AND at least one
        # is queryable, search is genuinely working. (Atlas or self-managed + mongot.)
        idx = self.index_status()
        info["indexes"] = idx
        try:
            info["search_available"] = any(
                any(queryable for queryable in coll.values())
                for coll in idx.values()
            )
        except Exception:  # noqa: BLE001
            pass
        return info

    # ---- counts --------------------------------------------------------------
    def active_feature_ids(self, project_id=None):
        """Latest version per feature group → (set of active feature ids, set of group ids)."""
        q = {"project_id": project_id} if project_id else {}
        latest = {}
        for f in self.features.find(q, {"group_id": 1, "version": 1}):
            g = f.get("group_id", str(f["_id"]))
            v = f.get("version", 1)
            if g not in latest or v > latest[g][1]:
                latest[g] = (str(f["_id"]), v)
        return {x[0] for x in latest.values()}, set(latest.keys())

    def active_case_ids(self, active_fids):
        ids = set()
        for fid in active_fids:
            ids.update(self.feature_test_case_ids(fid))
        return ids

    def counts(self):
        active_fids, groups = self.active_feature_ids()
        return {"features": len(groups),
                "feature_versions": self.features.count_documents({}),
                "test_cases": len(self.active_case_ids(active_fids)),
                "total_cases_all_versions": self.cases.count_documents({}),
                "test_steps": self.steps.count_documents({}),
                "associations": self.assoc.count_documents({})}

    # ---- code analysis / mind map -------------------------------------------
    def clear_code_chunks(self, repo_id):
        self.code_chunks.delete_many({"repo_id": repo_id})

    def add_code_chunks(self, docs):
        if docs:
            self.code_chunks.insert_many(docs)

    def save_code_coverage(self, feature_id, project_id, result, repos):
        self.code_cov.update_one({"feature_id": feature_id}, {"$set": {
            "feature_id": feature_id, "project_id": project_id, "result": result,
            "repos": repos, "updated_at": time.time()}}, upsert=True)

    def get_code_coverage(self, feature_id):
        c = self.code_cov.find_one({"feature_id": feature_id})
        if c:
            c.pop("_id", None)
        return c

    def code_chunk_count(self, project_id):
        return self.code_chunks.count_documents({"project_id": project_id})

    def code_chunks_for_repo(self, repo_id):
        """Load a repo's indexed chunks (for reuse without re-fetching the tarball)."""
        return list(self.code_chunks.find(
            {"repo_id": repo_id}, {"repo": 1, "path": 1, "text": 1, "embedding": 1, "_id": 0}))

    def get_code_index(self, repo_id):
        return self.code_index.find_one({"repo_id": repo_id})

    def set_code_index(self, repo_id, sha, count, impl_files):
        self.code_index.update_one({"repo_id": repo_id}, {"$set": {
            "repo_id": repo_id, "sha": sha, "count": count, "impl_files": impl_files,
            "updated_at": time.time()}}, upsert=True)

    def search_code_chunks(self, query_embedding, project_id=None, repo_ids=None, limit=16):
        """Retrieve the most relevant production-code chunks for a query embedding.

        Uses the mongot vectorSearch index when available; falls back to an in-memory numpy
        cosine scan so retrieval still works without a live search cluster (e.g. tests / dev).
        """
        try:
            stage = {"index": VECTOR_INDEX, "path": "embedding",
                     "queryVector": query_embedding, "numCandidates": 300, "limit": limit}
            filt = {}
            if project_id:
                filt["project_id"] = {"$eq": project_id}
            if repo_ids:
                filt["repo_id"] = {"$in": list(repo_ids)}
            if filt:
                stage["filter"] = filt
            pipeline = [{"$vectorSearch": stage},
                        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                        {"$limit": limit}]
            out = [{"repo": d.get("repo"), "path": d.get("path"), "text": d.get("text"),
                    "score": round(d.get("score", 0), 4)} for d in self.code_chunks.aggregate(pipeline)]
            if out:
                return out
        except Exception:  # noqa: BLE001  -- no mongot / index -> numpy fallback below
            pass
        q = {}
        if project_id:
            q["project_id"] = project_id
        if repo_ids:
            q["repo_id"] = {"$in": list(repo_ids)}
        docs = list(self.code_chunks.find(q, {"repo": 1, "path": 1, "text": 1, "embedding": 1, "_id": 0}))
        if not docs:
            return []
        import numpy as np
        qv = np.asarray(query_embedding, dtype=float)
        qn = np.linalg.norm(qv) or 1.0
        M = np.asarray([d["embedding"] for d in docs], dtype=float)
        norms = np.linalg.norm(M, axis=1); norms[norms == 0] = 1.0
        scores = (M @ qv) / (norms * qn)
        order = np.argsort(-scores)[:limit]
        return [{"repo": docs[i].get("repo"), "path": docs[i].get("path"),
                 "text": docs[i].get("text"), "score": round(float(scores[i]), 4)} for i in order]

    # ---- commit analysis (grounded impact) ----------------------------------
    def save_commit_analysis(self, project_id, feature_id, params, commits, results):
        """Persist one grounded commit-analysis run; returns its id."""
        return str(self.commit_analysis.insert_one({
            "project_id": project_id, "feature_id": feature_id, "params": params,
            "commits": commits, "results": results, "created_at": time.time()}).inserted_id)

    def get_commit_analysis(self, run_id):
        d = self.commit_analysis.find_one({"_id": ObjectId(run_id)})
        if d:
            d["id"] = str(d.pop("_id"))
        return d

    def latest_commit_analysis(self, project_id, feature_id=None):
        q = {"project_id": project_id}
        if feature_id:
            q["feature_id"] = feature_id
        d = self.commit_analysis.find_one(q, sort=[("_id", -1)])
        if d:
            d["id"] = str(d.pop("_id"))
        return d

    # ---- jobs (unified background work) --------------------------------------
    def create_job(self, jtype, params, label="", project_id=None, feature_id=None):
        return str(self.db["jobs"].insert_one({
            "type": jtype, "label": label, "status": "running", "stage": "starting",
            "progress": 0, "logs": [{"stage": "starting", "progress": 0, "at": time.time()}],
            "params": params, "result": {}, "error": None,
            "project_id": project_id, "feature_id": feature_id,
            "created_at": time.time(), "updated_at": time.time()}).inserted_id)

    def update_job(self, jid, **fields):
        fields["updated_at"] = time.time()
        self.db["jobs"].update_one({"_id": ObjectId(jid)}, {"$set": fields})
        stage = fields.get("stage")
        status = fields.get("status")
        progress = fields.get("progress")
        error = fields.get("error")
        parts = [f"[Job {jid}]"]
        if status:
            parts.append(f"status={status}")
        if stage:
            parts.append(f"stage='{stage}'")
        if progress is not None:
            parts.append(f"progress={progress}%")
        if error:
            parts.append(f"error='{error}'")
        if len(parts) > 1:
            print(" ".join(parts), flush=True)

    def update_job_progress(self, jid, stage, progress=None):
        now = time.time()
        fields = {"stage": stage, "updated_at": now}
        if progress is not None:
            fields["progress"] = max(0, min(100, int(progress)))
        self.db["jobs"].update_one(
            {"_id": ObjectId(jid)},
            {
                "$set": fields,
                "$push": {
                    "logs": {
                        "$each": [{"stage": stage, "progress": fields.get("progress"), "at": now}],
                        "$slice": -80,
                    }
                },
            },
        )
        prog_str = f" ({fields['progress']}%). Log saved." if progress is not None else ""
        print(f"[Job {jid}] {stage}{prog_str}", flush=True)

    def merge_job_result(self, jid, **fields):
        upd = {f"result.{k}": v for k, v in fields.items()}
        upd["updated_at"] = time.time()
        self.db["jobs"].update_one({"_id": ObjectId(jid)}, {"$set": upd})

    def set_job_usage(self, jid, usage):
        """Attach a per-process token/cost summary (from usage.summarize) to a job."""
        self.db["jobs"].update_one(
            {"_id": ObjectId(jid)},
            {"$set": {"usage": usage or {}, "updated_at": time.time()}})

    def usage_summary(self, project_id=None, prices=None, recent=40, scan=1000):
        """Aggregate token usage + cost across recent jobs: totals, per-model,
        per-project, and a list of recent processes (for the usage dashboard).

        Cost is recomputed live from stored token counts using the current price
        table, so editing prices in Settings updates historical costs too."""
        import usage as usage_mod
        price_map = {**usage_mod.DEFAULT_PRICES, **(prices or {})}

        def cost_of(model, pin, pout):
            p = usage_mod.price_for(model, price_map)
            if p is None:
                return None
            return (pin / 1e6) * float(p.get("in", 0)) + (pout / 1e6) * float(p.get("out", 0))

        q = {"usage.total_tokens": {"$gt": 0}}
        if project_id:
            q["project_id"] = project_id
        by_model, by_project = {}, {}
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        any_cost = False
        recents = []
        pname = {}
        fname = {}
        for j in self.db["jobs"].find(q, {"params": 0}).sort("_id", -1).limit(scan):
            u = j.get("usage") or {}
            job_cost, job_has_cost = 0.0, False
            for model, d in (u.get("by_model") or {}).items():
                pin = int(d.get("prompt_tokens", 0) or 0)
                pout = int(d.get("completion_tokens", 0) or 0)
                c = cost_of(model, pin, pout)
                agg = by_model.setdefault(model, {
                    "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "cost_usd": 0.0, "kind": d.get("kind", "llm"),
                    "has_cost": False})
                agg["calls"] += int(d.get("calls", 0) or 0)
                agg["prompt_tokens"] += pin
                agg["completion_tokens"] += pout
                agg["total_tokens"] += pin + pout
                if c is not None:
                    agg["cost_usd"] += c
                    agg["has_cost"] = True
                    job_cost += c
                    job_has_cost = True
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                totals[k] += int(u.get(k, 0) or 0)
            if job_has_cost:
                totals["cost_usd"] += job_cost
                any_cost = True
            pid = j.get("project_id") or ""
            if pid and pid not in pname and ObjectId.is_valid(pid):
                p = self.projects.find_one({"_id": ObjectId(pid)}, {"name": 1})
                pname[pid] = (p or {}).get("name") or pid
            pj = by_project.setdefault(pid or "—", {
                "project_id": pid, "name": pname.get(pid, "Unassigned" if not pid else pid),
                "total_tokens": 0, "cost_usd": 0.0, "has_cost": False})
            pj["total_tokens"] += int(u.get("total_tokens", 0) or 0)
            if job_has_cost:
                pj["cost_usd"] += job_cost
                pj["has_cost"] = True
            if len(recents) < recent:
                fid = j.get("feature_id") or ""
                if fid and fid not in fname and ObjectId.is_valid(fid):
                    f = self.features.find_one({"_id": ObjectId(fid)}, {"name": 1})
                    fname[fid] = (f or {}).get("name") or ""
                recents.append({
                    "id": str(j["_id"]), "type": j.get("type"),
                    "label": j.get("label") or j.get("type"),
                    "status": j.get("status"), "created_at": j.get("created_at"),
                    "project_id": pid, "project_name": pname.get(pid, ""),
                    "feature_id": fid, "feature_name": fname.get(fid, ""),
                    "total_tokens": u.get("total_tokens", 0),
                    "prompt_tokens": u.get("prompt_tokens", 0),
                    "completion_tokens": u.get("completion_tokens", 0),
                    "cost_usd": round(job_cost, 6) if job_has_cost else None,
                    "by_model": u.get("by_model") or {},
                })
        totals["cost_usd"] = round(totals["cost_usd"], 4) if any_cost else None
        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 6) if m.pop("has_cost") else None
        proj_list = sorted(by_project.values(), key=lambda x: x["total_tokens"], reverse=True)
        for p in proj_list:
            p["cost_usd"] = round(p["cost_usd"], 4) if p.pop("has_cost") else None
        return {"totals": totals, "by_model": by_model,
                "by_project": proj_list, "recent": recents}

    def get_job(self, jid):
        j = self.db["jobs"].find_one({"_id": ObjectId(jid)})
        if j:
            j["id"] = str(j.pop("_id"))
        return j

    def list_jobs(self, limit=60, status=None, jtype=None):
        q = {}
        if status:
            q["status"] = status
        if jtype:
            q["type"] = jtype
        out = []
        for j in self.db["jobs"].find(q, {"params": 0}).sort("_id", -1).limit(limit):
            j["id"] = str(j.pop("_id"))
            out.append(j)
        return out

    def fail_orphaned_jobs(self):
        """Background threads do not survive an application process restart."""
        now = time.time()
        orphaned = list(self.db["jobs"].find({"status": "running"}, {"_id": 1, "stage": 1}))
        for job in orphaned:
            stage = job.get("stage") or "unknown"
            message = (
                "Generation worker stopped because the application restarted while "
                f"the job was at: {stage}. Retry the job to continue."
            )
            self.db["jobs"].update_one(
                {"_id": job["_id"], "status": "running"},
                {
                    "$set": {
                        "status": "failed",
                        "stage": "interrupted by application restart",
                        "error": message,
                        "updated_at": now,
                    },
                    "$push": {
                        "logs": {
                            "$each": [{
                                "stage": "interrupted by application restart",
                                "progress": None,
                                "at": now,
                            }],
                            "$slice": -80,
                        }
                    },
                },
            )
        if orphaned:
            print(f"[Jobs] Marked {len(orphaned)} orphaned running job(s) as failed.", flush=True)
        return len(orphaned)

    def sweep_stale_jobs(self, ttl_seconds=600):
        """Fail any 'running' job whose heartbeat (`updated_at`) is older than
        ttl_seconds. Workers call update_job_progress() regularly, so a stale
        updated_at means the worker thread is dead or hung. Runs on a timer,
        not just at startup, so live-process hangs also recover and the UI
        stops spinning forever.
        """
        now = time.time()
        cutoff = now - ttl_seconds
        stale = list(self.db["jobs"].find(
            {"status": "running", "updated_at": {"$lt": cutoff}},
            {"_id": 1, "stage": 1, "updated_at": 1}))
        for job in stale:
            stage = job.get("stage") or "unknown"
            idle = int(now - float(job.get("updated_at") or now))
            message = (
                f"Worker heartbeat lost — no progress for {idle}s while at: "
                f"{stage}. Marked failed by the stale-job sweeper. Retry to continue."
            )
            self.db["jobs"].update_one(
                {"_id": job["_id"], "status": "running"},
                {
                    "$set": {
                        "status": "failed",
                        "stage": "stalled",
                        "error": message,
                        "updated_at": now,
                    },
                    "$push": {
                        "logs": {
                            "$each": [{
                                "stage": "stalled — worker heartbeat lost",
                                "progress": None,
                                "at": now,
                            }],
                            "$slice": -80,
                        }
                    },
                },
            )
        if stale:
            print(f"[Jobs] Swept {len(stale)} stalled running job(s).", flush=True)
        return len(stale)

    # ---- projects ------------------------------------------------------------
    def create_project(self, name, key=None, description="", jira_project_key=None,
                       jira_project_name=None, confluence_space_key=None,
                       confluence_space_name=None, default_git_provider="github"):
        doc = {"name": name, "key": key, "description": (description or ""),
               "jira_project_key": jira_project_key, "jira_project_name": jira_project_name,
               "confluence_space_key": confluence_space_key,
               "confluence_space_name": confluence_space_name,
               "default_git_provider": (default_git_provider or "github").lower(),
               "created_at": time.time()}
        return str(self.projects.insert_one(doc).inserted_id)

    def get_or_default_project(self):
        p = self.projects.find_one({})
        if p:
            return str(p["_id"])
        return self.create_project("Default Project")

    def get_project(self, pid):
        if not ObjectId.is_valid(pid):
            return None
        p = self.projects.find_one({"_id": ObjectId(pid)})
        if not p:
            return None
        p["id"] = str(p.pop("_id"))
        return p

    def list_projects(self):
        out = []
        for p in self.projects.find({}).sort("_id", -1):
            pid = str(p.pop("_id")); p["id"] = pid
            # Strip secret/encrypted blobs before returning.
            for k in ("github_pat_enc", "gitlab_pat_enc"):
                p.pop(k, None)
            p["github_pat_set"] = bool(self.projects.find_one(
                {"_id": ObjectId(pid)}, {"github_pat_enc": 1}).get("github_pat_enc"))
            p["gitlab_pat_set"] = bool(self.projects.find_one(
                {"_id": ObjectId(pid)}, {"gitlab_pat_enc": 1}).get("gitlab_pat_enc"))
            p["repo_count"] = self.repos.count_documents({"project_id": pid})
            p["feature_count"] = self.features.count_documents({"project_id": pid})
            out.append(p)
        return out

    def update_project(self, pid, fields):
        """Apply a $set update to a project doc; safe-ignores empty input."""
        if not ObjectId.is_valid(pid) or not fields:
            return None
        clean = {k: v for k, v in fields.items() if v is not None}
        if not clean:
            return self.get_project(pid)
        self.projects.update_one({"_id": ObjectId(pid)}, {"$set": clean})
        return self.get_project(pid)

    def get_project_github_pat_enc(self, pid):
        if not ObjectId.is_valid(pid):
            return ""
        p = self.projects.find_one({"_id": ObjectId(pid)}, {"github_pat_enc": 1})
        return (p or {}).get("github_pat_enc", "") or ""

    def get_project_gitlab_pat_enc(self, pid):
        if not ObjectId.is_valid(pid):
            return ""
        p = self.projects.find_one({"_id": ObjectId(pid)}, {"gitlab_pat_enc": 1})
        return (p or {}).get("gitlab_pat_enc", "") or ""

    def set_project_github_pat_enc(self, pid, enc):
        self.projects.update_one({"_id": ObjectId(pid)},
                                 {"$set": {"github_pat_enc": enc or ""}})

    def set_project_gitlab_pat_enc(self, pid, enc):
        self.projects.update_one({"_id": ObjectId(pid)},
                                 {"$set": {"gitlab_pat_enc": enc or ""}})

    # ---- features ------------------------------------------------------------
    def create_feature(self, name, project_id, sources, text, summary, embedding, key=None,
                       group_id=None, version=1, version_diff=None):
        if isinstance(sources, str):
            sources = [sources]
        from extract import extract_api_endpoints
        raw_api_spec = extract_api_endpoints(text)
        doc = {"name": name, "project_id": project_id, "key": key,
               "sources": sources, "source": ", ".join(sources),
               "text": text, "summary": summary, "embedding": embedding,
               "raw_api_spec": raw_api_spec,
               "group_id": group_id, "version": version, "version_diff": version_diff or {},
               "created_at": time.time()}
        fid = str(self.features.insert_one(doc).inserted_id)
        if not group_id:   # first version: the group is itself
            self.features.update_one({"_id": ObjectId(fid)}, {"$set": {"group_id": fid}})
        return fid

    def set_feature_figma(self, feature_id, figma):
        """Attach extracted Figma design data (summaries.figma shape) to a feature."""
        self.features.update_one({"_id": ObjectId(feature_id)}, {"$set": {"figma": figma or {}}})

    def get_versions(self, group_id):
        out = []
        for f in self.features.find({"group_id": group_id}, {"embedding": 0, "text": 0}).sort("version", 1):
            out.append({"id": str(f["_id"]), "version": f.get("version", 1),
                        "source": f.get("source", ""), "created_at": f.get("created_at"),
                        "case_count": self.assoc.count_documents({"feature_id": str(f["_id"])})})
        return out

    def reset_feature_content(self, fid):
        """For 'replace' mode: drop this version's case associations (retiring orphans) + chunks."""
        case_ids = self.feature_test_case_ids(fid)
        self.assoc.delete_many({"feature_id": fid})
        removed = 0
        for cid in case_ids:
            if self.assoc.count_documents({"test_case_id": cid}) == 0:
                self.cases.delete_one({"_id": ObjectId(cid)}); removed += 1
        self.fchunks.delete_many({"feature_id": fid})
        self.cleanup_orphaned_steps()
        return removed

    def update_feature_doc(self, fid, sources, text, summary, embedding):
        if isinstance(sources, str):
            sources = [sources]
        from extract import extract_api_endpoints
        raw_api_spec = extract_api_endpoints(text)
        self.features.update_one({"_id": ObjectId(fid)}, {"$set": {
            "sources": sources, "source": ", ".join(sources), "text": text,
            "summary": summary, "embedding": embedding, "raw_api_spec": raw_api_spec,
            "updated_at": time.time()}})

    def set_version_diff(self, fid, diff):
        self.features.update_one({"_id": ObjectId(fid)}, {"$set": {"version_diff": diff}})

    def add_feature_chunks(self, feature_id, project_id, chunks):
        """chunks: list of {source, chunk_index, text, embedding}."""
        docs = [{"feature_id": feature_id, "project_id": project_id, **c} for c in chunks]
        if docs:
            self.fchunks.insert_many(docs)

    def search_features(self, embedding, project_id=None, limit=3):
        """Match a query against ALL feature doc chunks; best chunk score per feature."""
        stage = {"index": VECTOR_INDEX, "path": "embedding",
                 "queryVector": embedding, "numCandidates": 200, "limit": 50}
        if project_id:
            stage["filter"] = {"project_id": {"$eq": project_id}}
        pipeline = [{"$vectorSearch": stage},
                    {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                    {"$group": {"_id": "$feature_id", "score": {"$max": "$score"}}},
                    {"$sort": {"score": -1}}, {"$limit": limit}]
        out = []
        for row in self.fchunks.aggregate(pipeline):
            f = self.features.find_one({"_id": ObjectId(row["_id"])}, {"name": 1, "key": 1})
            if f:
                out.append({"id": row["_id"], "name": f.get("name"), "key": f.get("key"),
                            "score": round(row["score"], 4)})
        return out

    def features_by_key(self, project_id, key):
        return [str(f["_id"]) for f in
                self.features.find({"project_id": project_id, "key": key}, {"_id": 1})]

    # ---- epic <-> feature binding (1:1) --------------------------------------
    def feature_by_epic(self, project_id, epic_key):
        """Return the LATEST-version feature id bound to `epic_key` in the
        project, or None. (Epic key is stored on the feature's `key` field.)"""
        if not (project_id and epic_key):
            return None
        best = None
        for f in self.features.find({"project_id": project_id, "key": epic_key},
                                    {"_id": 1, "version": 1}):
            v = f.get("version", 1)
            if best is None or v > best[1]:
                best = (str(f["_id"]), v)
        return best[0] if best else None

    def epic_bound_group(self, project_id, epic_key, exclude_group_id=None):
        """Return the group_id of a feature already bound to `epic_key`, or None.
        Ignores `exclude_group_id` so re-versioning the same feature is allowed."""
        if not (project_id and epic_key):
            return None
        for f in self.features.find({"project_id": project_id, "key": epic_key},
                                    {"group_id": 1, "_id": 1}):
            gid = f.get("group_id") or str(f["_id"])
            if exclude_group_id and gid == exclude_group_id:
                continue
            return gid
        return None

    def bound_epic_keys(self, project_id, exclude_group_id=None):
        """Set of epic keys already associated with a feature in the project."""
        keys = set()
        for f in self.features.find(
                {"project_id": project_id, "key": {"$nin": [None, ""]}},
                {"key": 1, "group_id": 1, "_id": 1}):
            gid = f.get("group_id") or str(f["_id"])
            if exclude_group_id and gid == exclude_group_id:
                continue
            keys.add(f["key"])
        return keys

    def jira_project_in_use(self, jira_project_key, exclude_pid=None):
        """Return the id of an app project already using `jira_project_key`
        (other than `exclude_pid`), or None. Enforces 1 Jira project : 1 app project."""
        if not jira_project_key:
            return None
        for p in self.projects.find({"jira_project_key": jira_project_key}, {"_id": 1}):
            pid = str(p["_id"])
            if exclude_pid and pid == exclude_pid:
                continue
            return pid
        return None

    def get_feature(self, fid):
        f = self.features.find_one({"_id": ObjectId(fid)})
        if f:
            f["id"] = str(f.pop("_id")); f.pop("embedding", None)
            f["versions"] = self.get_versions(f.get("group_id", f["id"]))
        return f

    def build_unified_context(self, feature_id, version_number):
        import json
        import re

        def score_relevance(text: str = "", feature_name: str = "") -> int:
            if not feature_name:
                return 0
            keywords = [k for k in feature_name.lower().split() if k]
            lower = text.lower()
            return sum(1 for k in keywords if k in lower)

        def unique_compact(items: list, max_items: int = 50) -> list[str]:
            out = []
            seen = set()
            for item in items:
                value = " ".join(str(item or "").split()).strip()
                if not value:
                    continue
                key = value.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(value)
                if len(out) >= max_items:
                    break
            return out

        def extract_requirement_lines(text: str = "", max_items: int = 20, feature_name: str = "") -> list[str]:
            if not text or len(text) < 20:
                return []
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            requirement_words = [
                'must', 'should', 'shall', 'required', 'validate', 'reject',
                'deny', 'allow', 'expire', 'lock', 'redirect', 'return',
                'create', 'update', 'verify', 'prevent', 'restrict', 'support',
                'only', 'cannot', 'not accept',
            ]
            picked = []
            seen = set()
            for line in lines:
                lower = line.lower()
                is_requirement = (
                    len(line) >= 15 and
                    any(word in lower for word in requirement_words)
                )
                if not is_requirement:
                    continue
                normalized = " ".join(line.split()).strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                picked.append(normalized)
            
            if feature_name:
                picked.sort(key=lambda x: score_relevance(x, feature_name), reverse=True)
            return picked[:max_items]

        def extract_api_endpoints(text: str = "", max_items: int = 40, feature_name: str = "") -> list[str]:
            if not text or len(text) < 10:
                return []
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            found = []
            
            method_path_regex = re.compile(
                r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9\-._~:/?#[\]@!$&\'()*+,;=%{}]+)\b', re.IGNORECASE
            )
            path_only_regex = re.compile(
                r'(\/(?:api|v1|v2|auth|user|users|login|signup|register|otp|session|feature|features|project|projects|document|documents)[A-Za-z0-9\-._~:/?#[\]@!$&\'()*+,;=%{}]*)', re.IGNORECASE
            )
            
            for line in lines:
                for match in method_path_regex.finditer(line):
                    found.append(f"{match.group(1).upper()} {match.group(2)}")
                for match in path_only_regex.finditer(line):
                    found.append(match.group(1))
                    
            if feature_name:
                found.sort(key=lambda x: score_relevance(x, feature_name), reverse=True)
                
            return unique_compact(found, max_items)

        def extract_technical_lines(text: str = "", max_items: int = 30, feature_name: str = "") -> list[str]:
            if not text or len(text) < 20:
                return []
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            keywords = [
                'api', 'endpoint', 'request', 'response', 'status code', 'http',
                'jwt', 'token', 'otp', 'session', 'role', 'permission',
                'authorization', 'authentication', 'validation', 'error',
                'retry', 'timeout', 'limit', 'rate limit', 'webhook', 'callback',
                'integration', 'payload', 'database', 'table', 'queue',
            ]
            picked = []
            for line in lines:
                lower = line.lower()
                if len(line) >= 20 and any(word in lower for word in keywords):
                    picked.append(line)
                    
            if feature_name:
                picked.sort(key=lambda x: score_relevance(x, feature_name), reverse=True)
                
            return unique_compact(picked, max_items)

        def extract_business_context(text: str = "") -> dict:
            if not text or len(text) < 20:
                return {}
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            req_lines = extract_requirement_lines(text, 25)
            
            user_stories = [l for l in lines if l.lower().startswith('as a')]
            
            acceptance_criteria = []
            for l in lines:
                lower = l.lower()
                if (
                    'should' in lower or
                    'acceptance criteria' in lower or
                    'must' in lower or
                    'shall' in lower or
                    'required' in lower
                ):
                    acceptance_criteria.append(l)
                    
            assumptions = [l for l in lines if 'assumption' in l.lower()]
            risks = [l for l in lines if 'risk' in l.lower()]
            
            return {
                "userStories": user_stories,
                "acceptanceCriteria": acceptance_criteria,
                "assumptions": assumptions,
                "risks": risks,
                "requirements": req_lines
            }

        feature = self.features.find_one({"_id": ObjectId(feature_id)})
        if not feature:
            raise ValueError(f"Feature with id {feature_id} not found")
            
        raw_text = feature.get("text") or ""
        raw_api_spec = feature.get("raw_api_spec") or ""
        
        # Load all chunks for this feature
        fchunks = list(self.fchunks.find({"feature_id": feature_id}))
        retrieved_chunks = [{"sourceType": c.get("source", "document"), "text": c.get("text", "")} for c in fchunks]
        
        # Check if the configured LLM provider is local Ollama
        settings = self.get_settings()
        is_ollama = (settings.get("llm_provider", "ollama") == "ollama")
        
        # Optimization: Apply dynamic limits on raw text slices to avoid CPU-Ollama context windows crashes/hangs
        prd_limit = 15000 if is_ollama else 80000
        chunk_limit = 3 if is_ollama else 12
        
        feature_name = feature.get("name") or "Unnamed Feature"
        prd_text = raw_text[:prd_limit]
        
        requirements = {
            "prd": extract_requirement_lines(prd_text, 30, feature_name),
            "hld": [],
            "lld": []
        }
        
        business_context = extract_business_context(prd_text)
        
        technical_context = {
            "prd": {
                "endpoints": extract_api_endpoints(prd_text, 25, feature_name),
                "technicalLines": extract_technical_lines(prd_text, 25, feature_name),
                "embeddedLinks": []
            },
            "hld": {"endpoints": [], "technicalLines": [], "embeddedLinks": []},
            "lld": {"endpoints": [], "technicalLines": [], "embeddedLinks": []},
            "apiSpec": raw_api_spec
        }
        
        # Construct unified context modeled after Node structure
        return {
            "featureName": feature_name,
            "featureDescription": feature.get("summary") or "",
            "projectId": feature.get("project_id"),
            "featureId": feature_id,
            "versionNumber": version_number,
            "versionTransitionSummary": json.dumps(feature.get("version_diff") or {}),
            "summaries": {
                "prd": prd_text,
                "hld": "",
                "lld": "",
                "figma": (feature.get("figma") or {})
            },
            "technicalContext": technical_context,
            "businessContext": business_context,
            "business_context": business_context,
            "requirements": requirements,
            "flags": {
                "hasBusiness": True,
                "hasTechnical": bool(raw_api_spec),
                "hasFunctional": True,
                "hasBusinessOnly": not bool(raw_api_spec),
                "figmaOk": bool((feature.get("figma") or {}).get("sampleScreens")),
                "hasUI": bool((feature.get("figma") or {}).get("sampleScreens")),
                "hasScreens": bool((feature.get("figma") or {}).get("sampleScreens")),
                "hasFlows": bool((feature.get("figma") or {}).get("flows")),
                "hasApiEvidence": bool(raw_api_spec) or len(technical_context["prd"]["endpoints"]) > 0,
                "hasTechnicalEvidence": bool(raw_api_spec) or len(technical_context["prd"]["technicalLines"]) > 0
            },
            "metadata": {
                "versionNumber": version_number,
                "featureName": feature.get("name"),
                "featureId": feature_id
            },
            "rag": {
                "retrieved_chunks": retrieved_chunks[:chunk_limit]
            },
            "rawApiSpec": raw_api_spec
        }

    def list_features(self, project_id=None):
        q = {"project_id": project_id} if project_id else {}
        latest = {}   # group_id -> latest feature doc
        for f in self.features.find(q, {"embedding": 0, "text": 0}):
            g = f.get("group_id", str(f["_id"]))
            if g not in latest or f.get("version", 1) > latest[g].get("version", 1):
                latest[g] = f
        out = []
        for g, f in latest.items():
            fid = str(f["_id"])
            out.append({"id": fid, "name": f.get("name"), "source": f.get("source"),
                        "key": f.get("key"), "version": f.get("version", 1),
                        "group_id": g, "versions": self.features.count_documents({"group_id": g}),
                        "case_count": self.assoc.count_documents({"feature_id": fid}),
                        "created_at": f.get("created_at")})
        return sorted(out, key=lambda x: x.get("created_at", 0), reverse=True)

    def feature_test_case_ids(self, fid):
        return [a["test_case_id"] for a in self.assoc.find({"feature_id": fid})]

    # ---- steps (dedup + reuse) ----------------------------------------------
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
                {"$group": {"_id": "$step_ids", "n": {"$sum": 1}}},
            ]
            for row in self.cases.aggregate(pipeline):
                counts[row["_id"]] = row["n"]
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

    # ---- cases (dedup + reuse) ----------------------------------------------
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
        if not self._numpy_fallback_ok("dedup"):
            return []
        return self._find_similar_cases_numpy(embedding, suggest, exclude_id, top, project_id)

    def _numpy_fallback_ok(self, what: str) -> bool:
        try:
            n = self.cases.estimated_document_count()
        except Exception:  # noqa: BLE001
            n = 0
        if n > NUMPY_FALLBACK_MAX_DOCS:
            print(f"[store] mongot unavailable and case store is large ({n} > "
                  f"{NUMPY_FALLBACK_MAX_DOCS}); skipping exact numpy fallback for {what} "
                  f"(degraded) to avoid OOM. Restore mongot to resume full search.",
                  flush=True)
            return False
        return True

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
                "association": {"origin": origin[cid].get("origin"),
                                "score": origin[cid].get("score")},
            })
        order = {"functional": 0, "e2e": 1, "api": 2, "ui": 3, "nfr": 4}

        def _seq(display_id):
            m = re.search(r"(\d+)$", display_id or "")
            return int(m.group(1)) if m else 10 ** 9

        # category first, then ascending by the numeric part of the display id (EC-LOG-1, 2, 3…)
        return sorted(out, key=lambda x: (order.get(x["type"], 9), _seq(x.get("display_id"))))

    # ---- RAG retrieval via mongot -------------------------------------------
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

    # ---- test-case management -----------------------------------------------
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

    # ---- dashboard -----------------------------------------------------------
    def documents_count(self):
        n = 0
        for f in self.features.find({}, {"sources": 1, "source": 1}):
            if f.get("sources"):
                n += len(f["sources"])
            elif f.get("source"):
                n += 1
        return n

    def _covered_and_dev_sets(self):
        covered, dev = set(), set()
        for c in self.coverage.find({}):
            for x in c.get("covered", []):
                covered.add(x.get("test_case_id"))
                if x.get("by_dev_test"):
                    dev.add(x.get("test_case_id"))
        return covered, dev

    def dashboard(self):
        covered, dev = self._covered_and_dev_sets()
        active_fids, groups = self.active_feature_ids()
        active = self.active_case_ids(active_fids)
        total_cases = len(active)
        by_type = {t: 0 for t in ["functional", "e2e", "api", "ui", "nfr"]}
        if active:
            for c in self.cases.find({"_id": {"$in": [ObjectId(i) for i in active]}}, {"type": 1}):
                if c.get("type") in by_type:
                    by_type[c["type"]] += 1
        cov_active, aut_active = len(covered & active), len(dev & active)
        docs = 0
        for f in self.features.find({"_id": {"$in": [ObjectId(i) for i in active_fids]}},
                                    {"sources": 1, "source": 1}):
            docs += len(f.get("sources") or ([f["source"]] if f.get("source") else []))
        # per-project rollup (active only)
        projects = []
        for p in self.projects.find({}):
            pid = str(p["_id"])
            afids, pgroups = self.active_feature_ids(pid)
            pcases = self.active_case_ids(afids)
            tc = len(pcases)
            projects.append({
                "id": pid, "name": p.get("name"), "features": len(pgroups), "test_cases": tc,
                "code_pct": round(100 * len(pcases & covered) / tc, 1) if tc else 0,
                "automation_pct": round(100 * len(pcases & dev) / tc, 1) if tc else 0,
                "prs": self.prs.count_documents({"project_id": pid}),
                "repos": self.repos.count_documents({"project_id": pid})})
        return {
            "counts": {
                "projects": self.projects.count_documents({}),
                "features": len(groups),
                "feature_versions": self.features.count_documents({}),
                "test_cases": total_cases,
                "test_steps": self.steps.count_documents({}),
                "documents": docs,
                "repos": self.repos.count_documents({}),
                "pull_requests": self.prs.count_documents({}),
            },
            "coverage": {
                "code_pct": round(100 * cov_active / total_cases, 1) if total_cases else 0,
                "automation_pct": round(100 * aut_active / total_cases, 1) if total_cases else 0,
                "covered_cases": cov_active, "automated_cases": aut_active,
            },
            "by_type": by_type,
            "projects": projects,
        }

    # ---- test cycles ---------------------------------------------------------
    @staticmethod
    def _cycle_counts(items):
        counts = {key: 0 for key in ["pending", "passed", "failed", "skipped", "blocked"]}
        for item in items:
            status = str(item.get("execution_status") or item.get("status") or "pending").lower()
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _cycle_activity(self, action, performed_by=None, item_id=None,
                        old_value=None, new_value=None):
        return {
            "id": str(ObjectId()), "action": action, "performed_by": performed_by,
            "item_id": item_id, "old_value": old_value, "new_value": new_value,
            "created_at": time.time(),
        }

    def _cycle_item_from_case(self, case_id, order):
        case = self.cases.find_one({"_id": ObjectId(case_id)}, {"embedding": 0})
        if not case:
            return None
        feature_id = case.get("source_feature_id")
        feature = (
            self.features.find_one({"_id": ObjectId(feature_id)}, {"name": 1, "version": 1})
            if feature_id and ObjectId.is_valid(feature_id) else None
        )
        return {
            "id": str(ObjectId()), "case_id": case_id, "testcase_id": case_id,
            "title": case.get("title"), "category": case.get("type") or "",
            "priority": case.get("priority") or "P2",
            "steps": [
                f"{step.get('action', '')} → {step.get('expected', '')}".strip(" →")
                for step in self.resolve_steps(case.get("step_ids", []))
            ],
            "feature_id": feature_id, "feature_name": (feature or {}).get("name", ""),
            "feature_version_number": (feature or {}).get("version"),
            "execution_status": "pending", "actual_result": "", "defect_link": "",
            "notes": "", "executed_by": None, "executed_at": None,
            "display_order": order, "created_at": time.time(), "updated_at": time.time(),
        }

    def create_cycle(self, project_id, name, case_ids, source=None, **meta):
        duplicate = self.db["test_cycles"].find_one({
            "project_id": project_id,
            "name_key": name.strip().lower(),
        })
        if duplicate:
            raise ValueError("A test cycle with this name already exists in this project")
        items = []
        for index, case_id in enumerate(dict.fromkeys(case_ids), 1):
            item = self._cycle_item_from_case(case_id, index)
            if item:
                items.append(item)
        now = time.time()
        cid = self.db["test_cycles"].insert_one({
            "project_id": project_id, "name": name.strip(),
            "name_key": name.strip().lower(), "description": meta.get("description", ""),
            "environment": meta.get("environment", ""), "build_version": meta.get("build_version", ""),
            "assigned_to": meta.get("assigned_to"), "scheduled_start_at": meta.get("scheduled_start_at"),
            "scheduled_end_at": meta.get("scheduled_end_at"), "actual_start_at": None,
            "actual_end_at": None, "status": "draft", "items": items,
            "source": source or {}, "activity": [self._cycle_activity("cycle_created", meta.get("created_by"))],
            "created_by": meta.get("created_by"), "created_at": now, "updated_at": now,
        }).inserted_id
        return str(cid)

    def list_cycles(self, project_id, status=None):
        query = {"project_id": project_id}
        if status:
            query["status"] = status
        out = []
        for c in self.db["test_cycles"].find(query).sort("_id", -1):
            items = c.get("items", [])
            counts = self._cycle_counts(items)
            out.append({"id": str(c["_id"]), "name": c.get("name"), "total": len(items),
                        "counts": counts, "status": c.get("status", "draft"),
                        "description": c.get("description", ""), "environment": c.get("environment", ""),
                        "build_version": c.get("build_version", ""), "source": c.get("source", {}),
                        "created_at": c.get("created_at"), "updated_at": c.get("updated_at")})
        return out

    def get_cycle(self, cycle_id):
        c = self.db["test_cycles"].find_one({"_id": ObjectId(cycle_id)})
        if not c:
            return None
        changed = False
        status_alias = {"pass": "passed", "fail": "failed"}
        for index, item in enumerate(c.get("items", []), 1):
            if not item.get("id"):
                item["id"] = str(ObjectId())
                changed = True
            raw_status = str(item.get("execution_status") or item.get("status") or "pending").lower()
            normalized_status = status_alias.get(raw_status, raw_status)
            if item.get("execution_status") != normalized_status:
                item["execution_status"] = normalized_status
                item["status"] = normalized_status
                changed = True
            # Refresh title/category/priority/steps from the LIVE case each read so edits to a
            # test case (or its shared steps) propagate into cycles that reference it.
            if item.get("case_id") and ObjectId.is_valid(item["case_id"]):
                case = self.cases.find_one({"_id": ObjectId(item["case_id"])}, {"embedding": 0})
                if case:
                    live = {
                        "title": case.get("title"), "category": case.get("type") or "",
                        "display_id": case.get("display_id") or "",
                        "priority": case.get("priority") or "P2",
                        "steps": [
                            f"{step.get('action', '')} → {step.get('expected', '')}".strip(" →")
                            for step in self.resolve_steps(case.get("step_ids", []))
                        ],
                    }
                    for key, value in live.items():
                        if item.get(key) != value:
                            item[key] = value
                            changed = True
            item.setdefault("display_order", index)
            item.setdefault("actual_result", "")
            item.setdefault("defect_link", "")
            item.setdefault("notes", "")
        if changed:
            self.db["test_cycles"].update_one(
                {"_id": c["_id"]},
                {"$set": {"items": c.get("items", []), "updated_at": time.time()}},
            )
        c["id"] = str(c.pop("_id"))
        c["counts"] = self._cycle_counts(c.get("items", []))
        c["total"] = len(c.get("items", []))
        return c

    def update_cycle(self, cycle_id, fields, performed_by=None):
        allowed = {
            "name", "description", "status", "environment", "build_version",
            "assigned_to", "scheduled_start_at", "scheduled_end_at",
        }
        update = {key: value for key, value in fields.items() if key in allowed}
        if "name" in update:
            update["name_key"] = str(update["name"]).strip().lower()
        update["updated_at"] = time.time()
        activity = self._cycle_activity("cycle_updated", performed_by)
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {"$set": update, "$push": {"activity": activity}},
        )
        return self.get_cycle(cycle_id)

    def set_cycle_item_status(self, cycle_id, item_or_case_id, status, actual_result="",
                              defect_link="", notes="", executed_by=None):
        status = str(status).lower()
        if status not in {"pending", "passed", "failed", "skipped", "blocked"}:
            raise ValueError("Invalid cycle execution status")
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        items = c.get("items", [])
        target = next(
            (item for item in items if item.get("id") == item_or_case_id or item.get("case_id") == item_or_case_id),
            None,
        )
        if not target:
            raise ValueError("Cycle item not found")
        old = target.get("execution_status", "pending")
        target.update({
            "execution_status": status, "status": status,
            "actual_result": actual_result, "defect_link": defect_link, "notes": notes,
            "executed_by": executed_by,
            "executed_at": time.time() if status != "pending" else None,
            "updated_at": time.time(),
        })
        counts = self._cycle_counts(items)
        terminal = counts["passed"] + counts["failed"] + counts["skipped"] + counts["blocked"]
        cycle_status = c.get("status", "draft")
        cycle_updates = {}
        if terminal == len(items) and items:
            cycle_status = "completed"
            cycle_updates["actual_end_at"] = time.time()
        elif cycle_status == "draft" and status != "pending":
            cycle_status = "active"
            cycle_updates["actual_start_at"] = time.time()
        cycle_updates.update({"items": items, "status": cycle_status, "updated_at": time.time()})
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": cycle_updates,
                "$push": {"activity": self._cycle_activity(
                    "status_changed", executed_by, target["id"], old, status
                )},
            },
        )
        return target

    def batch_cycle_item_status(self, cycle_id, item_ids, status, executed_by=None):
        for item_id in item_ids:
            self.set_cycle_item_status(cycle_id, item_id, status, executed_by=executed_by)
        return self.get_cycle(cycle_id)

    def add_cycle_items(self, cycle_id, case_ids, performed_by=None):
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        existing = {item.get("case_id") for item in c.get("items", [])}
        items = c.get("items", [])
        added = 0
        for case_id in case_ids:
            if case_id in existing:
                continue
            item = self._cycle_item_from_case(case_id, len(items) + 1)
            if item:
                items.append(item)
                existing.add(case_id)
                added += 1
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": {"items": items, "updated_at": time.time()},
                "$push": {"activity": self._cycle_activity(
                    "items_added", performed_by, new_value=str(added)
                )},
            },
        )
        return added

    def remove_cycle_item(self, cycle_id, item_id, performed_by=None):
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        items = [item for item in c.get("items", []) if item.get("id") != item_id]
        for index, item in enumerate(items, 1):
            item["display_order"] = index
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": {"items": items, "updated_at": time.time()},
                "$push": {"activity": self._cycle_activity("item_removed", performed_by, item_id)},
            },
        )

    def cycle_report(self, cycle_id):
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        counts, total = c["counts"], c["total"]
        completed = total - counts.get("pending", 0)
        category, priority = {}, {}
        for item in c.get("items", []):
            category[item.get("category", "")] = category.get(item.get("category", ""), 0) + 1
            priority[item.get("priority", "")] = priority.get(item.get("priority", ""), 0) + 1
        return {
            "cycle": c,
            "summary": {
                **counts, "total": total,
                "pass_rate": round(100 * counts.get("passed", 0) / completed, 1) if completed else 0,
                "completion_rate": round(100 * completed / total, 1) if total else 0,
            },
            "category_breakdown": category, "priority_breakdown": priority,
            "recent_activity": list(reversed(c.get("activity", [])[-50:])),
        }

    def cycle_csv(self, cycle_id):
        import csv
        import io
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([f"Cycle: {c.get('name')}", f"Status: {c.get('status')}"])
        writer.writerow([])
        writer.writerow([
            "#", "Test Case ID", "Title", "Category", "Priority", "Status",
            "Feature", "Version", "Steps", "Actual Result", "Defect Link", "Notes",
        ])
        prio_map = {"p1": "High", "p2": "Medium", "p3": "Low", "1": "High", "2": "Medium",
                    "3": "Low", "critical": "High", "mid": "Medium", "high": "High",
                    "medium": "Medium", "low": "Low"}
        for item in c.get("items", []):
            prio = prio_map.get(str(item.get("priority") or "").strip().lower(), item.get("priority"))
            writer.writerow([
                item.get("display_order"),
                item.get("display_id") or item.get("case_id"),   # readable ID, not the Mongo _id
                item.get("title"),
                item.get("category"), prio, item.get("execution_status"),
                item.get("feature_name"), item.get("feature_version_number"),
                "\n".join(item.get("steps", [])), item.get("actual_result"),
                item.get("defect_link"), item.get("notes"),
            ])
        return out.getvalue()

    def delete_cycle(self, cycle_id):
        self.db["test_cycles"].delete_one({"_id": ObjectId(cycle_id)})
        return {"deleted": cycle_id}

    # ---- cycle templates (reusable case sets) --------------------------------
    def save_cycle_as_template(self, cycle_id, name):
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        case_ids = [it.get("case_id") for it in c.get("items", []) if it.get("case_id")]
        return str(self.db["cycle_templates"].insert_one({
            "project_id": c.get("project_id"), "name": name, "case_ids": case_ids,
            "description": c.get("description", ""), "environment": c.get("environment", ""),
            "build_version": c.get("build_version", ""), "case_count": len(case_ids),
            "created_at": time.time()}).inserted_id)

    def list_cycle_templates(self, project_id):
        out = []
        for t in self.db["cycle_templates"].find({"project_id": project_id}).sort("_id", -1):
            out.append({"id": str(t["_id"]), "name": t.get("name"),
                        "case_count": t.get("case_count", len(t.get("case_ids", []))),
                        "description": t.get("description", ""), "created_at": t.get("created_at")})
        return out

    def create_cycle_from_template(self, template_id, name, created_by=None):
        t = self.db["cycle_templates"].find_one({"_id": ObjectId(template_id)})
        if not t:
            return None
        return self.create_cycle(
            t.get("project_id"), name, t.get("case_ids", []), {"from_template": template_id},
            description=t.get("description", ""), environment=t.get("environment", ""),
            build_version=t.get("build_version", ""), created_by=created_by)

    def delete_cycle_template(self, template_id):
        self.db["cycle_templates"].delete_one({"_id": ObjectId(template_id)})
        return {"deleted": template_id}

    # ---- Import Sheet: storage helpers ---------------------------------------
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

    # ---- settings ------------------------------------------------------------
    def _backfill_settings_configured(self):
        # First-run gate (`configured`) was added after launch. Existing installs
        # that already saved LLM settings should not be sent back to Configuration,
        # so mark them configured when meaningful LLM signals are present.
        try:
            s = self.db["settings"].find_one({"_id": "app"})
            if s and "configured" not in s and (
                s.get("llm_api_key_enc") or s.get("llm_model")
                or s.get("llm_provider") or s.get("ollama_url")
            ):
                self.db["settings"].update_one(
                    {"_id": "app"}, {"$set": {"configured": True}})
        except Exception:  # noqa: BLE001
            pass

    def get_settings(self):
        return self.db["settings"].find_one({"_id": "app"}) or {}

    def save_settings(self, doc):
        self.db["settings"].update_one({"_id": "app"}, {"$set": doc}, upsert=True)

    # ---- database migration --------------------------------------------------
    def target_has_data(self, target_uri: str) -> bool:
        """True if the target database already holds any app data (so we don't clobber
        someone's existing DB without consent)."""
        from pymongo import MongoClient
        c = MongoClient(target_uri, serverSelectionTimeoutMS=8000)
        try:
            tgt = c[self.db.name]
            for nm in tgt.list_collection_names():
                if nm.startswith("system."):
                    continue
                if tgt[nm].estimated_document_count() > 0:
                    return True
            return False
        finally:
            c.close()

    def migrate_to(self, target_uri: str, progress=None, overwrite: bool = False) -> dict:
        """Copy EVERY collection from this database to the database at target_uri,
        preserving _ids and embedded vectors. Indexes are NOT copied — the app
        recreates them (regular + vector/search) on next startup against the target.
        Returns {collection: docs_copied}. Documents are streamed in batches so large,
        embedding-heavy datasets don't blow up memory."""
        from pymongo import MongoClient
        BATCH = 300
        c = MongoClient(target_uri, serverSelectionTimeoutMS=8000)
        try:
            tgt = c[self.db.name]
            names = [n for n in self.db.list_collection_names() if not n.startswith("system.")]
            if not overwrite:
                for nm in names:
                    if tgt[nm].estimated_document_count() > 0:
                        raise RuntimeError(
                            f"the target database already contains data (collection '{nm}'). "
                            "Re-run with overwrite to replace it.")
            counts, total = {}, max(len(names), 1)
            for i, nm in enumerate(names):
                src = self.db[nm]
                approx = src.estimated_document_count()
                if progress:
                    progress(f"Copying {nm} ({approx} docs)…", int(5 + (i / total) * 90))
                if overwrite:
                    tgt[nm].delete_many({})
                batch, copied = [], 0
                for doc in src.find({}):
                    batch.append(doc)
                    if len(batch) >= BATCH:
                        tgt[nm].insert_many(batch, ordered=False)
                        copied += len(batch); batch = []
                if batch:
                    tgt[nm].insert_many(batch, ordered=False)
                    copied += len(batch)
                counts[nm] = copied
            return counts
        finally:
            c.close()

    # ---- users / auth --------------------------------------------------------
    @staticmethod
    def _user_out(u):
        if not u:
            return None
        return {"id": str(u["_id"]), "email": u.get("email"), "name": u.get("name"),
                "role": u.get("role", "viewer"), "active": u.get("active", True),
                "created_at": u.get("created_at"), "last_login": u.get("last_login"),
                # Invite lifecycle (additive; pre-existing docs default to "active"
                # since a user without invite metadata was created before this field
                # and has effectively already joined).
                "invite_status": u.get("invite_status", "active"),
                "invited_by": u.get("invited_by"), "invited_at": u.get("invited_at"),
                "invite_resolved_at": u.get("invite_resolved_at"),
                "session_version": u.get("session_version", 0),
                # Project access (additive; pre-existing docs have no field → default
                # to all_projects=True so existing users are grandfathered in).
                "all_projects": u.get("all_projects", True),
                "project_ids": u.get("project_ids", []),
                "otp_hash": u.get("otp_hash"), "otp_expires": u.get("otp_expires", 0),
                "otp_attempts": u.get("otp_attempts", 0)}

    def get_user(self, uid):
        try:
            return self._user_out(self.users.find_one({"_id": ObjectId(uid)}))
        except Exception:  # noqa: BLE001
            return None

    def get_user_by_email(self, email):
        return self._user_out(self.users.find_one({"email": (email or "").strip().lower()}))

    def list_users(self):
        return [self._user_out(u) for u in self.users.find().sort("created_at", 1)]

    def count_users(self):
        return self.users.count_documents({})

    def count_active_admins(self):
        return self.users.count_documents({"role": "admin", "active": True})

    def create_user(self, email, name, role="viewer", active=True,
                    invite_status="active", invited_by=None,
                    all_projects=True, project_ids=None):
        """Create a user.

        invite_status:
          * "active"  — self-service / bootstrap sign-in (no pending invite).
          * "pending" — created via admin invite; becomes "active" on first login.
        invited_by is the admin's user id, kept for the audit trail.

        Project access:
          * all_projects=True  → access to every project (default; also how existing
            users and admins behave).
          * all_projects=False → access limited to project_ids (a list of project ids).
        """
        doc = {"email": email.strip().lower(), "name": name, "role": role,
               "active": active, "created_at": time.time(), "last_login": None,
               "invite_status": invite_status, "invited_by": invited_by,
               "invited_at": time.time() if invite_status == "pending" else None,
               "all_projects": bool(all_projects),
               "project_ids": [] if all_projects else list(project_ids or [])}
        res = self.users.insert_one(doc)
        return self.get_user(str(res.inserted_id))

    def set_user_projects(self, uid, all_projects, project_ids=None):
        """Update a user's project access. all_projects=True clears the explicit list."""
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {
            "all_projects": bool(all_projects),
            "project_ids": [] if all_projects else list(project_ids or [])}})
        return self.get_user(uid)

    def accept_invite(self, uid):
        """Explicit accept of a pending invite (from the invited user). Idempotent:
        only a pending invite transitions to accepted."""
        self.users.update_one(
            {"_id": ObjectId(uid), "invite_status": "pending"},
            {"$set": {"invite_status": "accepted", "invite_resolved_at": time.time()}})
        return self.get_user(uid)

    def decline_invite(self, uid):
        """Explicit decline of a pending invite. Marks it declined and deactivates
        the account so the person can't act, but keeps the record for the admin."""
        self.users.update_one(
            {"_id": ObjectId(uid), "invite_status": "pending"},
            {"$set": {"invite_status": "declined", "active": False,
                      "invite_resolved_at": time.time()}})
        return self.get_user(uid)

    def invite_inviter_info(self, uid):
        """Return {email, name} of whoever sent this user's invite, or None."""
        u = self.users.find_one({"_id": ObjectId(uid)}, {"invited_by": 1})
        inviter_id = (u or {}).get("invited_by")
        if not inviter_id:
            return None
        inv = self.get_user(inviter_id)
        return {"email": inv["email"], "name": inv.get("name")} if inv else None

    def bump_session_version(self, uid):
        """Increment a user's session_version, invalidating all their existing
        sessions. Called on role change / disable / forced logout so authorization
        changes take effect immediately (the user must re-authenticate)."""
        self.users.update_one({"_id": ObjectId(uid)}, {"$inc": {"session_version": 1}})
        return self.get_user(uid)

    def update_user(self, uid, fields):
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": fields})
        return self.get_user(uid)

    def delete_user(self, uid):
        self.users.delete_one({"_id": ObjectId(uid)})
        return {"deleted": uid}

    def set_otp(self, uid, otp_hash, expires):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"otp_hash": otp_hash, "otp_expires": expires,
                                        "otp_attempts": 0}})

    def otp_recent_issue_count(self, uid, window_seconds):
        """Record an OTP issuance now and return how many were issued within the last
        `window_seconds` (including this one). Used to rate-limit code requests.
        Keeps only timestamps inside the window."""
        now = time.time()
        cutoff = now - window_seconds
        u = self.users.find_one({"_id": ObjectId(uid)}, {"otp_issues": 1}) or {}
        issues = [t for t in (u.get("otp_issues") or []) if t >= cutoff]
        issues.append(now)
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {"otp_issues": issues[-20:]}})
        return len(issues)

    def inc_otp_attempts(self, uid):
        self.users.update_one({"_id": ObjectId(uid)}, {"$inc": {"otp_attempts": 1}})

    def clear_otp(self, uid):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$unset": {"otp_hash": "", "otp_expires": "", "otp_attempts": ""}})

    # ---- invite tokens (separate from OTP so login codes never overwrite invites) --
    def set_invite_token(self, uid, token_hash, expires):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$set": {"invite_token_hash": token_hash,
                                        "invite_token_expires": expires}})

    def get_user_by_invite_token(self, token):
        """Return the (still-valid, unexpired) user whose invite token matches, else
        None. Compares the hash against every user carrying a live token."""
        import auth as _auth  # local import: store.py stays framework-light
        h = _auth.hash_token(token)
        now = time.time()
        u = self.users.find_one({"invite_token_hash": h,
                                 "invite_token_expires": {"$gt": now}})
        return self._user_out(u)

    def clear_invite_token(self, uid):
        self.users.update_one({"_id": ObjectId(uid)},
                              {"$unset": {"invite_token_hash": "", "invite_token_expires": ""}})

    def touch_login(self, uid):
        self.users.update_one({"_id": ObjectId(uid)}, {"$set": {"last_login": time.time()}})

    # ---- audit log -----------------------------------------------------------
    @property
    def audit(self):
        return self.db["audit_logs"]

    def add_audit(self, action, actor=None, target=None, old=None, new=None,
                  ip=None, user_agent=None, detail=None):
        """Append an immutable audit entry. Best-effort: never let logging failures
        break the underlying action (callers wrap in try/except)."""
        doc = {"action": action, "ts": time.time(),
               "actor_id": (actor or {}).get("id") if isinstance(actor, dict) else actor,
               "actor_email": (actor or {}).get("email") if isinstance(actor, dict) else None,
               "target": target, "old": old, "new": new,
               "ip": ip, "user_agent": user_agent, "detail": detail}
        self.audit.insert_one(doc)
        return True

    def list_audit(self, limit=100, action=None, actor_email=None):
        q = {}
        if action:
            q["action"] = action
        if actor_email:
            q["actor_email"] = actor_email
        out = []
        for d in self.audit.find(q).sort("ts", -1).limit(int(limit)):
            d["id"] = str(d.pop("_id"))
            out.append(d)
        return out

    # ---- legacy migration ----------------------------------------------------
    def migrate_legacy_features(self, default_pid=None):
        """Adopt features created before project_id existed into a default project,
        and backfill version/group_id for pre-versioning features."""
        legacy_count = self.features.count_documents({"$or": [{"project_id": {"$exists": False}}, {"project_id": None}]})
        if legacy_count > 0:
            pid = default_pid or self.get_or_default_project()
            self.features.update_many(
                {"$or": [{"project_id": {"$exists": False}}, {"project_id": None}]},
                {"$set": {"project_id": pid}})
        self.features.update_many({"version": {"$exists": False}}, {"$set": {"version": 1}})
        for f in self.features.find({"$or": [{"group_id": {"$exists": False}}, {"group_id": None}]},
                                    {"_id": 1}):
            self.features.update_one({"_id": f["_id"]}, {"$set": {"group_id": str(f["_id"])}})
        return True

    # ---- project CRUD --------------------------------------------------------
    def rename_project(self, pid, name):
        self.projects.update_one({"_id": ObjectId(pid)}, {"$set": {"name": name}})

    def delete_project(self, pid):
        if not ObjectId.is_valid(pid) or not self.projects.find_one({"_id": ObjectId(pid)}):
            return None
        fids = [str(f["_id"]) for f in self.features.find({"project_id": pid}, {"_id": 1})]
        project_case_ids = {
            row["test_case_id"] for row in self.assoc.find(
                {"feature_id": {"$in": fids}}, {"test_case_id": 1}
            )
        }
        externally_shared = {
            cid for cid in project_case_ids
            if self.assoc.count_documents({
                "test_case_id": cid,
                "feature_id": {"$nin": fids},
            }) > 0
        }
        removed_orphan_cases = 0
        for fid in fids:
            result = self.delete_feature(fid)
            removed_orphan_cases += result.get("removed_orphan_cases", 0)
        rids = [str(r["_id"]) for r in self.repos.find({"project_id": pid}, {"_id": 1})]
        for rid in rids:
            self.delete_repo(rid)
        self.code_chunks.delete_many({"project_id": pid})
        self.code_cov.delete_many({"project_id": pid})
        self.db["test_cycles"].delete_many({"project_id": pid})
        self.db["jobs"].delete_many({"project_id": pid})
        self.projects.delete_one({"_id": ObjectId(pid)})
        self.cleanup_orphaned_steps()
        return {
            "deleted_project": pid,
            "features": len(fids),
            "repos": len(rids),
            "removed_orphan_cases": removed_orphan_cases,
            "preserved_shared_cases": len(externally_shared),
        }

    # ---- feature CRUD --------------------------------------------------------
    def rename_feature(self, fid, name=None, key=None):
        upd = {}
        if name is not None:
            upd["name"] = name
        if key is not None:
            upd["key"] = key or None
        if upd:
            self.features.update_one({"_id": ObjectId(fid)}, {"$set": upd})

    def delete_feature(self, fid):
        if not ObjectId.is_valid(fid) or not self.features.find_one({"_id": ObjectId(fid)}):
            return None
        # remove associations; delete cases that were authored by this feature and
        # are not associated to any other feature (keep shared/reused cases).
        case_ids = self.feature_test_case_ids(fid)
        self.assoc.delete_many({"feature_id": fid})
        removed_cases = 0
        preserved_shared_cases = 0
        for cid in case_ids:
            if self.assoc.count_documents({"test_case_id": cid}) == 0:
                self.cases.delete_one({"_id": ObjectId(cid)})
                removed_cases += 1
            else:
                preserved_shared_cases += 1
                replacement = self.assoc.find_one(
                    {"test_case_id": cid}, sort=[("created_at", 1)]
                )
                replacement_fid = (replacement or {}).get("feature_id")
                if replacement_fid and ObjectId.is_valid(replacement_fid):
                    replacement_feature = self.features.find_one(
                        {"_id": ObjectId(replacement_fid)}, {"project_id": 1}
                    )
                    self.cases.update_one(
                        {"_id": ObjectId(cid), "source_feature_id": fid},
                        {"$set": {
                            "source_feature_id": replacement_fid,
                            "project_id": (replacement_feature or {}).get("project_id"),
                            "updated_at": time.time(),
                        }},
                    )
        self.fchunks.delete_many({"feature_id": fid})
        self.prs.update_many({"feature_id": fid}, {"$set": {"feature_id": None}})
        run_ids = [
            str(run["_id"]) for run in self.validator_runs.find(
                {"feature_id": fid}, {"_id": 1}
            )
        ]
        if run_ids:
            self.validator_questions.delete_many({"validator_run_id": {"$in": run_ids}})
            self.validator_answers.delete_many({"validator_run_id": {"$in": run_ids}})
        self.validator_runs.delete_many({"feature_id": fid})
        self.test_plan_runs.delete_many({"feature_id": fid})
        self.db["jobs"].delete_many({"feature_id": fid})
        self.features.delete_one({"_id": ObjectId(fid)})
        self.cleanup_orphaned_steps()
        return {
            "deleted_feature": fid,
            "removed_associations": len(case_ids),
            "removed_orphan_cases": removed_cases,
            "preserved_shared_cases": preserved_shared_cases,
        }

    # ---- test-case CRUD ------------------------------------------------------
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

    # ---- step CRUD -----------------------------------------------------------
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

    # ---- repos ---------------------------------------------------------------
    def delete_repo(self, rid):
        self.prs.delete_many({"repo_id": rid})
        self.repos.delete_one({"_id": ObjectId(rid)})
        return {"deleted_repo": rid}

    def add_repo(self, project_id, owner, name, url, kind, default_branch="main",
                 repo_type="app", git_provider="github", label="", webhook_id=None,
                 webhook_secret_enc=""):
        full = f"{owner}/{name}"
        doc = {"project_id": project_id, "owner": owner, "name": name, "full_name": full,
               "url": url, "kind": kind, "label": label or full,
               "repo_type": repo_type, "git_provider": git_provider,
               "default_branch": default_branch, "watch": True,
               "webhook_id": webhook_id, "webhook_secret_enc": webhook_secret_enc,
               "last_synced": 0, "created_at": time.time()}
        existing = self.repos.find_one({"project_id": project_id, "full_name": full,
                                        "git_provider": git_provider})
        if existing:
            self.repos.update_one({"_id": existing["_id"]},
                                  {"$set": {k: v for k, v in doc.items() if v is not None
                                            and k not in ("created_at",)}})
            return str(existing["_id"])
        return str(self.repos.insert_one(doc).inserted_id)

    def get_repo(self, rid):
        if not ObjectId.is_valid(rid):
            return None
        r = self.repos.find_one({"_id": ObjectId(rid)})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def list_repos(self, project_id):
        out = []
        for r in self.repos.find({"project_id": project_id}).sort("_id", 1):
            r["id"] = str(r.pop("_id"))
            r["pr_count"] = self.prs.count_documents({"repo_id": r["id"]})
            # Don't return raw encrypted secret in API payloads.
            r["webhook_configured"] = bool(r.pop("webhook_secret_enc", "") or
                                           r.get("webhook_id"))
            out.append(r)
        return out

    def repos_watching(self):
        return [{**r, "id": str(r["_id"])} for r in self.repos.find({"watch": True})]

    def repo_by_fullname(self, full_name, git_provider=None):
        q = {"full_name": full_name}
        if git_provider:
            q["git_provider"] = git_provider
        r = self.repos.find_one(q)
        return ({**r, "id": str(r["_id"])} if r else None)

    def repos_by_fullname_app(self, full_name, git_provider="github"):
        """All `app` repos across projects sharing this full_name (for fan-out webhooks)."""
        q = {"full_name": full_name, "git_provider": git_provider, "repo_type": "app"}
        out = []
        for r in self.repos.find(q):
            r["id"] = str(r.pop("_id"))
            out.append(r)
        return out

    def set_repo_synced(self, repo_id, ts):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"last_synced": ts}})

    def set_repo_watch(self, repo_id, watch):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"watch": bool(watch)}})

    def set_repo_webhook(self, repo_id, webhook_id, webhook_secret_enc):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {
            "webhook_id": webhook_id, "webhook_secret_enc": webhook_secret_enc}})

    def set_repo_label(self, repo_id, label):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"label": label}})

    # ---- pull requests -------------------------------------------------------
    def upsert_pr(self, doc):
        """doc keyed by (repo_id, number). Returns pr_id."""
        key = {"repo_id": doc["repo_id"], "number": doc["number"]}
        self.prs.update_one(key, {"$set": doc, "$setOnInsert": {"created_at_local": time.time()}},
                            upsert=True)
        return str(self.prs.find_one(key)["_id"])

    def set_pr_mapping(self, pr_id, feature_id, confidence, method):
        self.prs.update_one({"_id": ObjectId(pr_id)}, {"$set": {
            "feature_id": feature_id, "mapping_confidence": confidence, "mapping_method": method}})

    def list_prs(self, project_id=None, feature_id=None):
        q = {}
        if project_id:
            q["project_id"] = project_id
        if feature_id:
            q["feature_id"] = feature_id
        out = []
        for p in self.prs.find(q).sort("number", -1):
            p["id"] = str(p.pop("_id")); out.append(p)
        return out

    # ---- coverage ------------------------------------------------------------
    def save_coverage(self, pr_id, feature_id, covered, dev_test_files, confidence, notice=""):
        self.coverage.update_one({"pr_id": pr_id}, {"$set": {
            "pr_id": pr_id, "feature_id": feature_id, "covered": covered,
            "dev_test_files": dev_test_files, "confidence": confidence,
            "notice": notice, "updated_at": time.time()}}, upsert=True)

    def list_unmapped_prs(self, project_id):
        """PRs in a project that didn't auto-map to a feature (need manual assignment)."""
        q = {"project_id": project_id,
             "$or": [{"feature_id": None}, {"feature_id": {"$exists": False}}]}
        out = []
        for p in self.prs.find(q).sort("number", -1):
            out.append({"id": str(p["_id"]), "number": p.get("number"), "title": p.get("title"),
                        "repo": p.get("repo_full_name"), "url": p.get("url"),
                        "state": p.get("state"), "author": p.get("author"),
                        "mapping_confidence": p.get("mapping_confidence", 0)})
        return out

    # ---- Gap Analysis: PR Code Coverage runs ---------------------------------
    @property
    def code_coverage_runs(self):
        return self.db["code_coverage_runs"]

    def create_code_coverage_run(self, doc):
        repo_id = doc.get("repo_id")
        pr_number = doc.get("pr_number")
        if repo_id and pr_number is not None:
            try:
                p_num_int = int(pr_number)
                p_num_str = str(pr_number)
                self.code_coverage_runs.delete_many({
                    "repo_id": repo_id,
                    "pr_number": {"$in": [p_num_int, p_num_str]}
                })
            except Exception:
                self.code_coverage_runs.delete_many({
                    "repo_id": repo_id,
                    "pr_number": pr_number
                })
        doc = {**doc, "created_at": time.time(), "status": doc.get("status", "pending")}
        return str(self.code_coverage_runs.insert_one(doc).inserted_id)

    def update_code_coverage_run(self, rid, **fields):
        fields["updated_at"] = time.time()
        self.code_coverage_runs.update_one({"_id": ObjectId(rid)}, {"$set": fields})

    def get_code_coverage_run(self, rid):
        if not ObjectId.is_valid(rid):
            return None
        r = self.code_coverage_runs.find_one({"_id": ObjectId(rid)})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def previous_done_run_for_feature(self, feature_id, exclude_id=None):
        """Find the most-recent `done` run for this feature, excluding the
        given run id. Used to compute newly_covered / no_longer_covered."""
        q = {"feature_id": feature_id, "status": "done"}
        if exclude_id and ObjectId.is_valid(exclude_id):
            q["_id"] = {"$ne": ObjectId(exclude_id)}
        r = self.code_coverage_runs.find_one(q, sort=[("_id", -1)])
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def list_code_coverage_runs(self, feature_id=None, project_id=None, limit=50):
        q = {}
        if feature_id:
            q["feature_id"] = feature_id
        if project_id:
            q["project_id"] = project_id
        out = []
        for r in self.code_coverage_runs.find(q).sort("_id", -1).limit(limit):
            r["id"] = str(r.pop("_id"))
            out.append(r)
        return out

    # ---- Gap Analysis: Automation Coverage -----------------------------------
    @property
    def automation_coverage(self):
        return self.db["automation_coverage"]

    @property
    def test_repo_cases(self):
        return self.db["test_repo_cases"]

    def save_automation_coverage(self, feature_id, project_id, version, doc):
        self.automation_coverage.update_one(
            {"feature_id": feature_id, "version": version},
            {"$set": {**doc, "feature_id": feature_id, "project_id": project_id,
                      "version": version, "updated_at": time.time()}},
            upsert=True)

    def get_automation_coverage(self, feature_id, version=None):
        q = {"feature_id": feature_id}
        if version is not None:
            q["version"] = version
        return self.automation_coverage.find_one(q, sort=[("version", -1)])

    def replace_test_repo_cases(self, project_id, repo_id, cases):
        """Atomic-style replace: drop old rows for this repo, insert new batch."""
        self.test_repo_cases.delete_many({"repo_id": repo_id})
        if cases:
            self.test_repo_cases.insert_many([{**c, "project_id": project_id,
                                               "repo_id": repo_id} for c in cases])

    def list_test_repo_cases(self, project_id=None, repo_id=None):
        q = {}
        if project_id:
            q["project_id"] = project_id
        if repo_id:
            q["repo_id"] = repo_id
        out = []
        for c in self.test_repo_cases.find(q):
            c["id"] = str(c.pop("_id"))
            out.append(c)
        return out

    def set_repo_scan_status(self, rid, status, **fields):
        upd = {"scan_status": status, **fields, "scan_status_updated_at": time.time()}
        self.repos.update_one({"_id": ObjectId(rid)}, {"$set": upd})

    def repos_for_project(self, project_id, repo_type=None, git_provider=None):
        q = {"project_id": project_id}
        if repo_type == "app":
            # "App" (analysis) repos = anything NOT explicitly a test repo, so unclassified /
            # legacy repos are still selectable in impact analysis + Mind Map.
            q["$or"] = [{"repo_type": "app"}, {"repo_type": {"$in": [None, ""]}},
                        {"repo_type": {"$exists": False}}]
        elif repo_type == "test":
            q["repo_type"] = "test"
        if git_provider:
            q["git_provider"] = git_provider
        out = []
        for r in self.repos.find(q).sort("_id", 1):
            r["id"] = str(r.pop("_id"))
            # Never leak the encrypted webhook secret to callers — surface only a
            # "configured" boolean (matches list_repos()). No internal caller reads
            # the raw blob from here.
            r["webhook_configured"] = bool(r.pop("webhook_secret_enc", "") or
                                           r.get("webhook_id"))
            out.append(r)
        return out

    def feature_coverage_report(self, fid):
        """Aggregate coverage for a feature across all mapped PRs."""
        all_cases = self.feature_test_case_ids(fid)
        covered_ids, dev_tested_ids, pr_rows = set(), set(), []
        prs = self.list_prs(feature_id=fid)
        repos_seen = {}
        evidence = []   # per covered (case, PR) with link + rationale
        for pr in prs:
            cov = self.coverage.find_one({"pr_id": pr["id"]})
            cset = []
            if cov:
                for c in cov.get("covered", []):
                    tcid = c.get("test_case_id")
                    covered_ids.add(tcid); cset.append(tcid)
                    if c.get("by_dev_test"):
                        dev_tested_ids.add(tcid)
                    case = self.cases.find_one({"_id": ObjectId(tcid)}, {"title": 1}) if tcid else None
                    evidence.append({
                        "case_id": tcid, "case_title": case.get("title") if case else "(removed)",
                        "pr_number": pr.get("number"), "pr_url": pr.get("url"),
                        "repo": pr.get("repo_full_name"),
                        "status": c.get("status", "covered"), "confidence": c.get("confidence"),
                        "signal_type": c.get("signal_type"), "code_evidence": c.get("evidence", []),
                        "rationale": c.get("rationale", ""), "by_dev_test": c.get("by_dev_test", False)})
            repos_seen[pr.get("repo_id")] = repos_seen.get(pr.get("repo_id"), 0) + 1
            pr_rows.append({"number": pr.get("number"), "title": pr.get("title"),
                            "repo": pr.get("repo_full_name"), "state": pr.get("state"),
                            "url": pr.get("url"), "covered_count": len(cset),
                            "notice": (cov or {}).get("notice", ""),
                            "dev_tests": len((cov or {}).get("dev_test_files", []))})
        total = len(all_cases)
        return {
            "feature_id": fid, "total_test_cases": total,
            "covered": len(covered_ids & set(all_cases)),
            "uncovered": total - len(covered_ids & set(all_cases)),
            "dev_tested": len(dev_tested_ids & set(all_cases)),
            "pr_count": len(prs), "repos_touched": len(repos_seen),
            "prs": pr_rows, "evidence": evidence,
            "coverage_pct": round(100 * len(covered_ids & set(all_cases)) / total, 1) if total else 0,
            "dev_test_pct": round(100 * len(dev_tested_ids & set(all_cases)) / total, 1) if total else 0,
        }

    # ---- MCQ Validator --------------------------------------------------------
    def create_validator_run(self, feature_id, is_retake=False, version_number=None):
        now = time.time()
        # Find highest run_number for this feature_id
        highest = self.validator_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        run_number = (highest.get("run_number", 0) + 1) if highest else 1
        
        doc = {
            "feature_id": feature_id,
            "version_number": version_number,
            "run_number": run_number,
            "status": "generating", "stage": "Preparing validator context",
            "progress": 5, "error": None,
            "is_retake": is_retake,
            "clarity_score": None,
            "weak_areas": [],
            "results": None,
            "created_at": now,
            "updated_at": now
        }
        res = self.validator_runs.insert_one(doc)
        return str(res.inserted_id)

    def update_validator_run_status(self, run_id, status, error=None, stage=None, progress=None):
        fields = {"status": status, "error": error, "updated_at": time.time()}
        if stage is not None:
            fields["stage"] = stage
        if progress is not None:
            fields["progress"] = max(0, min(100, int(progress)))
        self.validator_runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": fields}
        )

    def update_validator_run_results(self, run_id, clarity_score, weak_areas, results):
        self.validator_runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": {
                "clarity_score": clarity_score,
                "weak_areas": weak_areas,
                "results": results,
                "status": "completed",
                "stage": "Completed",
                "progress": 100,
                "updated_at": time.time()
            }}
        )

    def get_validator_run(self, run_id):
        run = self.validator_runs.find_one({"_id": ObjectId(run_id)})
        if run:
            run["id"] = str(run.pop("_id"))
        return run

    def list_validator_runs(self, feature_id):
        out = []
        for r in self.validator_runs.find({"feature_id": feature_id}).sort("run_number", -1):
            r["id"] = str(r.pop("_id"))
            out.append(r)
        return out

    def insert_validator_questions(self, run_id, questions):
        # questions: list of NormalizedQuestion dicts
        docs = []
        for i, q in enumerate(questions):
            docs.append({
                "validator_run_id": run_id,
                "order_index": i,
                "category": q.get("category"),
                "question": q.get("question"),
                "options": q.get("options"),
                "correct_answer_index": q.get("correct_answer_index"),
                "source_refs": q.get("source_refs"),
                "created_at": time.time()
            })
        if docs:
            self.validator_questions.insert_many(docs)

    def get_validator_questions(self, run_id):
        out = []
        for q in self.validator_questions.find({"validator_run_id": run_id}).sort("order_index", 1):
            q["id"] = str(q.pop("_id"))
            out.append(q)
        return out

    def save_validator_answers(self, run_id, answers):
        # answers: list of PreparedAnswer dicts/inputs
        for a in answers:
            key = {"validator_run_id": run_id, "question_id": a["question_id"]}
            self.validator_answers.update_one(
                key,
                {"$set": {
                    "selected_index": a["selected_index"],
                    "confidence": a["confidence"],
                    "comment": a.get("comment"),
                    "answered_by": a.get("answered_by"),
                    "updated_at": time.time()
                }, "$setOnInsert": {"created_at": time.time()}},
                upsert=True
            )

    def get_validator_answers(self, run_id):
        out = []
        for a in self.validator_answers.find({"validator_run_id": run_id}):
            a["id"] = str(a.pop("_id"))
            out.append(a)
        return out

    # ---- Test Plan runs -------------------------------------------------------
    def create_test_plan_run(self, feature_id, version_number, created_by=None):
        now = time.time()
        # Find highest run_number for this feature_id
        highest = self.test_plan_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        run_number = (highest.get("run_number", 0) + 1) if highest else 1
        
        doc = {
            "feature_id": feature_id,
            "version_number": version_number,
            "run_number": run_number,
            "status": "PROCESSING",
            "source": "ai_generated",
            "content": None,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now
        }
        res = self.test_plan_runs.insert_one(doc)
        return str(res.inserted_id), run_number

    def update_test_plan_run(self, run_id, status, content=None, error=None):
        fields = {"status": status, "updated_at": time.time()}
        if content is not None:
            fields["content"] = content
        if error is not None:
            fields["error"] = error
        self.test_plan_runs.update_one({"_id": ObjectId(run_id)}, {"$set": fields})

    def get_test_plan_run(self, run_id):
        p = self.test_plan_runs.find_one({"_id": ObjectId(run_id)})
        if p:
            p["id"] = str(p.pop("_id"))
        return p

    def get_latest_test_plan_run(self, feature_id):
        p = self.test_plan_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        if p:
            p["id"] = str(p.pop("_id"))
        return p
