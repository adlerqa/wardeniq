"""Code analysis / Mind Map chunks, PR code-coverage runs, and automation
(test-repo) coverage tracking.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md). `feature_coverage_report`
and `set_feature_ready_threshold` are named `*_feature*` but placed here rather
than in features.py — both are fundamentally coverage-reporting operations that
read the coverage/PR collections owned by this module, per docs/internal/REFACTOR_PLAN.md
section 13's note that a few cross-domain joins should go where they most belong
rather than force an artificial boundary.
"""

import time

from bson import ObjectId

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


class CodeCoverageMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

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

    def set_code_index(self, repo_id, sha, count, impl_files, rules: str = ""):
        """Record a repo's index state. `rules` fingerprints the test/spec exclusion rules
        that produced these chunks, so changing those rules invalidates the index by
        itself — an index built under older rules must never be silently reused."""
        self.code_index.update_one({"repo_id": repo_id}, {"$set": {
            "repo_id": repo_id, "sha": sha, "count": count, "impl_files": impl_files,
            "rules": rules, "updated_at": time.time()}}, upsert=True)

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

    def set_feature_ready_threshold(self, fid, pct):
        """Per-feature QA-readiness threshold (percent CODE coverage) at which the
        feature is "ready for manual testing". Applied to all versions in the group
        so it survives regeneration. Clamped 0-100."""
        try:
            p = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            p = 80
        f = self.features.find_one({"_id": ObjectId(fid)}, {"group_id": 1})
        gid = (f or {}).get("group_id") or fid
        self.features.update_many({"group_id": gid}, {"$set": {"ready_threshold": p}})
        return p

    def feature_coverage_report(self, fid):
        """Aggregate coverage for a feature across all mapped PRs."""
        all_cases = self.feature_test_case_ids(fid)
        covered_ids, dev_tested_ids, pr_rows = set(), set(), []
        # Excluded PRs are ignored in coverage (still visible in Gap Analysis,
        # flagged) — a QA lead can drop outdated/junk PRs from the calculation.
        prs = [p for p in self.list_prs(feature_id=fid) if not p.get("excluded")]
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
