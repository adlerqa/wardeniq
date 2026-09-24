"""Feature CRUD, versioning, Jira epic/match-key binding, and unified-context
assembly for generation.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md).
"""

import time

from bson import ObjectId

from core.logging_setup import get_logger
from store.base import VECTOR_INDEX


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

log = get_logger("store.features")


class FeaturesMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def create_feature(self, name, project_id, sources, text, summary, embedding, key=None,
                       group_id=None, version=1, version_diff=None, match_key=None):
        if isinstance(sources, str):
            sources = [sources]
        from extract import extract_api_endpoints
        raw_api_spec = extract_api_endpoints(text)
        doc = {"name": name, "project_id": project_id, "key": key,
               "match_key": ((match_key or "").strip().upper() or None),
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

    def search_feature_chunks(self, query_embedding, feature_id, limit=8, category=None):
        """Retrieve the most relevant chunks of ONE feature's own document(s) for a
        query embedding -- the retrieval half of test-generation RAG (the write side
        is add_feature_chunks()). Modeled directly on
        store/code_coverage.py's search_code_chunks(): mongot $vectorSearch first
        (fast, real similarity ranking), in-memory numpy cosine as a true fallback so
        retrieval still works without a live search cluster (e.g. tests / dev / a
        transient mongot outage).

        `feature_id` is applied as a $vectorSearch pre-filter, not a post-hoc filter --
        the fchunks index already declares `feature_id` as a filter field at
        provisioning time (store/base.py's _ensure_vector(self.fchunks,
        extra_filters=["project_id", "feature_id"])), so a chunk belonging to a
        different feature can never enter the candidate pool, let alone the result.
        The numpy fallback below applies the same feature_id scoping via its own
        find() query, so cross-feature leakage is impossible on either path.

        `category` is optional and purely for observability (e.g. "api"/"ui"/"e2e" from
        testgen.service's category-specific generation retrieval) -- it is never used to
        filter or score, only stamped onto the debug log line below so a log reader can
        tell which of a run's several search_feature_chunks() calls this one was.
        """
        t0 = time.time()
        try:
            pool = max(int(limit) * 8, 40)
            stage = {"index": VECTOR_INDEX, "path": "embedding",
                     "queryVector": query_embedding, "numCandidates": pool, "limit": limit,
                     "filter": {"feature_id": {"$eq": feature_id}}}
            pipeline = [{"$vectorSearch": stage},
                        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                        {"$limit": limit}]
            out = [{"chunk_id": str(d.get("_id")), "chunk_index": d.get("chunk_index"),
                    "source": d.get("source"), "text": d.get("text"),
                    "score": round(float(d.get("score", 0)), 4)}
                   for d in self.fchunks.aggregate(pipeline)]
            if out:
                self._log_feature_chunk_retrieval(feature_id, len(out), "atlas", time.time() - t0, category)
                return out
        except Exception:  # noqa: BLE001 -- no mongot / index -> numpy fallback below
            pass
        docs = list(self.fchunks.find(
            {"feature_id": feature_id},
            {"chunk_index": 1, "source": 1, "text": 1, "embedding": 1}))
        if not docs:
            self._log_feature_chunk_retrieval(feature_id, 0, "numpy", time.time() - t0, category)
            return []
        # Embedding-model-switch hardening: the store has no per-row model/dimension
        # metadata (see the embedding-agnosticism investigation), so a query embedding
        # from a different model/dimension than what's currently stored -- e.g. a
        # partially-applied re-embed after a Settings model switch, or a race with a
        # concurrent ingest -- is only detectable here, at compute time. Any of these
        # ARE EXPECTED failure shapes on an unlucky day, not programmer errors, so they
        # degrade this one retrieval to empty rather than raising out of
        # search_feature_chunks() and crashing the whole test-generation pipeline (the
        # $vectorSearch branch above already has this same "degrade, don't crash"
        # posture for its own failures).
        try:
            import numpy as np
            qv = np.asarray(query_embedding, dtype=float)
            M = np.asarray([d["embedding"] for d in docs], dtype=float)
            if qv.ndim != 1 or M.ndim != 2 or M.shape[1] != qv.shape[0]:
                raise ValueError(
                    f"embedding dimension mismatch: query has "
                    f"{qv.shape[0] if qv.ndim == 1 else 'a ragged shape'}, stored chunks have "
                    f"{M.shape[1] if M.ndim == 2 else 'a ragged shape'}"
                )
            qn = np.linalg.norm(qv) or 1.0
            norms = np.linalg.norm(M, axis=1); norms[norms == 0] = 1.0
            scores = (M @ qv) / (norms * qn)
            order = np.argsort(-scores)[: int(limit)]
            out = [{"chunk_id": str(docs[i]["_id"]), "chunk_index": docs[i].get("chunk_index"),
                    "source": docs[i].get("source"), "text": docs[i].get("text"),
                    "score": round(float(scores[i]), 4)} for i in order]
        except Exception as exc:  # noqa: BLE001 -- dimension mismatch / malformed stored
                                   # embedding / any other cosine-math failure -> degrade
                                   # to empty, matching the atlas branch's posture above.
            log.warning("[feature_chunks] numpy fallback failed for feature_id=%s: %s",
                      feature_id, exc)
            self._log_feature_chunk_retrieval(feature_id, 0, "numpy_failed", time.time() - t0, category)
            return []
        self._log_feature_chunk_retrieval(feature_id, len(out), "numpy", time.time() - t0, category)
        return out

    @staticmethod
    def _log_feature_chunk_retrieval(feature_id, count, source, duration_s, category=None):
        """Store-layer half of retrieval observability: confirms which path
        actually answered (atlas vs numpy fallback) and how long it took, without
        the caller having to know that detail. Deliberately omits chunk text.
        testgen.service adds the query-text/chunk-id/score-level log on top of this."""
        cat = f"category={category} " if category else ""
        log.debug("[feature_chunks] %sfeature_id=%s source=%s results=%d duration_ms=%d",
                 cat, feature_id, source, count, round(duration_s * 1000))

    def features_by_key(self, project_id, key):
        return [str(f["_id"]) for f in
                self.features.find({"project_id": project_id, "key": key}, {"_id": 1})]

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

    def set_feature_match_key(self, fid, match_key):
        """Set/clear a feature's manual PR match tag. Applied to every version in
        the group so it survives regeneration. Stored UPPERCASE; blank clears."""
        mk = (match_key or "").strip().upper() or None
        f = self.features.find_one({"_id": ObjectId(fid)}, {"group_id": 1})
        gid = (f or {}).get("group_id", fid)
        self.features.update_many({"group_id": gid}, {"$set": {"match_key": mk}})
        return mk

    def features_with_match_key(self, project_id):
        """Latest-version (feature_id, match_key) for every feature in the project
        that has a manual PR match tag set."""
        best = {}
        for f in self.features.find(
                {"project_id": project_id, "match_key": {"$nin": [None, ""]}},
                {"_id": 1, "group_id": 1, "version": 1, "match_key": 1}):
            gid = f.get("group_id", str(f["_id"]))
            v = f.get("version", 1)
            if gid not in best or v > best[gid][1]:
                best[gid] = (str(f["_id"]), v, f.get("match_key"))
        return [(fid, mk) for (fid, _v, mk) in best.values()]

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

        # Check if the configured LLM provider is local Ollama
        settings = self.get_settings()
        is_ollama = (settings.get("llm_provider", "ollama") == "ollama")

        # Optimization: Apply dynamic limits on raw text slices to avoid CPU-Ollama context windows crashes/hangs
        prd_limit = 15000 if is_ollama else 80000

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
            # NOTE: previously this dict included a "rag" key built from ALL of this
            # feature's chunks (unranked, capped at chunk_limit). Nothing ever read
            # context["rag"] (confirmed via grep across prompt_builder.py/service.py),
            # so it was deleted as dead code. Query-driven, category-specific retrieval
            # now lives in generate_fresh_testcases_pipeline() via search_feature_chunks();
            # the broad/unranked chunk corpus needed for grounding/extraction is still
            # fetched separately there (store.fchunks.find({"feature_id": feature_id})),
            # untouched by this change.
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
