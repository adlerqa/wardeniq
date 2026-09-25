"""Mongo client/db setup, shared collection attributes, index management, the
search-degradation gate, and whole-database migration.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md, Option A: mixin composition).
BaseStore.__init__ is THE single place all 20 plain-attribute collections are
cached (store/__init__.py's Store class puts BaseStore last in its MRO so this
__init__ wins) — every domain mixin reads these via `self.<attr>`, never its own
copy. `_degraded` / search_degraded() / _numpy_fallback_ok() stay together here
because they are cross-cutting by nature (every domain's numpy-fallback search
path reports through this one gate).
"""

import math
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bson import ObjectId
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel


VECTOR_INDEX = "vector_index"
TEXT_INDEX = "text_index"


def _with_durable_write_concern(uri: str) -> str:
    """Opt into a majority write concern (and retryWrites) unless the URI already
    picks its own.

    pymongo's un-annotated default is w=1 -- acknowledged by the primary alone. If
    that primary steps down (routine election, container restart, a laptop
    suspending mid-session) before the write replicates, the write is rolled back
    when it rejoins as secondary. Nothing surfaces this to the user: the original
    PUT already returned 200. A Jira/LLM/SMTP settings save is exactly the write
    this bites hardest -- it happens once, isn't re-read for a while, and when it's
    gone the symptom looks like "the browser session forgot it" rather than "the
    database rolled back an ack'd write".

    Only fills in what's missing so an operator's own explicit w=/retryWrites=
    choice (e.g. a single-node dev Mongo, where majority reduces to 1 anyway) is
    never overridden. Best-effort: any parse failure returns the URI unchanged
    rather than block startup over connection-string cosmetics.
    """
    try:
        parts = urlsplit(uri)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if not any(k.lower() == "w" for k in query):
            query["w"] = "majority"
        if not any(k.lower() == "retrywrites" for k in query):
            query["retryWrites"] = "true"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:  # noqa: BLE001
        return uri


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


class BaseStore:
    def __init__(self, uri: str, db_name: str, dim: int):
        self.client = MongoClient(_with_durable_write_concern(uri))
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
        self.api_tokens = self.db["api_tokens"]
        self.api_token_failures = self.db["api_token_failures"]
        self.validator_runs = self.db["validator_runs"]
        self.validator_questions = self.db["validator_questions"]
        self.validator_answers = self.db["validator_answers"]
        self.test_plan_runs = self.db["test_plan_runs"]
        self.counters = self.db["counters"]
        # Records when a search path silently degraded (mongot down AND the store is too
        # large for the exact numpy fallback). Without this, a skipped dedup lookup is
        # indistinguishable from "no duplicates found" - so a generation run would create
        # near-duplicates with nothing but a log line to show for it. Callers check
        # `search_degraded()` and surface it; see testgen.service.
        self._degraded: dict = {}
        self.documents = self.db["stored_documents"]

    def ping(self):
        self.client.admin.command("ping"); return True

    def ensure_indexes(self):
        for name in ["projects", "features", "feature_chunks", "code_chunks", "code_coverage",
                     "test_steps", "test_cases", "associations", "repos", "pull_requests",
                     "pr_coverage", "users", "api_tokens", "api_token_failures",
                     "validator_runs", "validator_questions",
                     "validator_answers", "test_plan_runs", "test_cycles", "counters",
                     "feature_imports", "project_imported_rows",
                     "project_imported_row_sources", "project_imported_row_feature_map",
                     "project_imported_row_promotions",
                     "project_imported_row_corrections", "import_analysis_status",
                     "stored_documents"]:
            if name not in self.db.list_collection_names():
                self.db.create_collection(name)
        self.documents.create_index([("project_id", 1), ("created_at", -1)])
        self.documents.create_index([("feature_id", 1)])
        self.users.create_index([("email", 1)], unique=True)
        self.api_tokens.create_index([("token_hash", 1)], unique=True)
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
        # One correction row per (import batch, imported row) — latest decision wins.
        self.project_imported_row_corrections.create_index([
            ("import_batch_id", 1), ("project_imported_row_id", 1)
        ])
        self.project_imported_row_corrections.create_index([("import_batch_id", 1)])
        self._backfill_case_display_ids()
        self.cases.create_index([("display_id", 1)], unique=True, sparse=True)
        self._renumber_display_ids()   # one-time: per-feature numbering (1..N)
        self._repair_temp_display_ids()   # self-heal any ids stuck on a temp value
        self._backfill_settings_configured()
        self._converge_repo_kinds()
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
            # Make it inspectable, not just printed: a log line in a container nobody is
            # tailing is not an alert. Callers turn this into a job warning / health flag.
            rec = self._degraded.setdefault(what, {"count": 0, "first_at": time.time()})
            rec["count"] += 1
            rec["last_at"] = time.time()
            rec["docs"] = n
            rec["cap"] = NUMPY_FALLBACK_MAX_DOCS
            rec["reason"] = ("mongot unavailable and the case store exceeds the in-memory "
                            "fallback cap, so exact search was skipped")
            return False
        return True

    def search_degraded(self, what: str | None = None):
        """Has a search path silently degraded? Returns the record(s), or None/{} if clean.

        `what` is the subsystem name passed to `_numpy_fallback_ok` ('dedup',
        'case search', ...). Truthy result means results were INCOMPLETE, not empty.
        """
        if what is not None:
            return self._degraded.get(what)
        return dict(self._degraded)

    def clear_search_degraded(self, what: str | None = None):
        """Reset degradation state (call once mongot is confirmed healthy again)."""
        if what is None:
            self._degraded.clear()
        else:
            self._degraded.pop(what, None)

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
