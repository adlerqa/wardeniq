"""Cross-project dashboard aggregation: active feature/case sets (latest version
per group) and the rollup counts/coverage the dashboard UI reads.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md). `active_feature_ids` /
`active_case_ids` / `counts` are named generically but live here (not
projects.py or steps_test_cases.py) because their only callers are
`dashboard()` and each other — this keeps that call graph in one file.
"""

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


class DashboardMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

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

    def documents_count(self):
        n = 0
        for f in self.features.find({}, {"sources": 1, "source": 1}):
            if f.get("sources"):
                n += len(f["sources"])
            elif f.get("source"):
                n += 1
        return n

    def _covered_and_dev_sets(self):
        """`dev` (the "automated" set) has two independent sources, and a case only
        needs ONE of them to count (issue #99): `by_dev_test` from PR-coverage
        analysis (self.coverage / pr_coverage — a developer-written test noticed
        while reviewing a PR's diff), and a match recorded by the automation
        scan (self.automation_coverage — a connected test repo's automated test
        matched to a generated case, app/workers/repo_scan_worker.py). These are
        genuinely different discovery mechanisms for the same question ("is
        there an automated test for this case"), and a project can have real,
        matched automation coverage with zero PR-coverage runs ever having
        happened — before this fix, that combination silently reported 0%
        automation on the Dashboard while the feature-level Automation Test
        Coverage panel (which already reads self.automation_coverage directly,
        see get_automation_coverage() in store/code_coverage.py) showed the
        real, non-zero count.
        """
        covered, dev = set(), set()
        for c in self.coverage.find({}):
            for x in c.get("covered", []):
                covered.add(x.get("test_case_id"))
                if x.get("by_dev_test"):
                    dev.add(x.get("test_case_id"))
        for doc in self.automation_coverage.find({}, {"items": 1}):
            for item in doc.get("items", []):
                if item.get("status") == "covered" and item.get("generated_id"):
                    dev.add(item["generated_id"])
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
