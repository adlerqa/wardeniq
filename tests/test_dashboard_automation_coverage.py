"""Dashboard automation coverage (issue #99): the Dashboard's aggregate
automation % must also count cases automated via a test-repo scan match
(app/workers/repo_scan_worker.py, stored in the automation_coverage
collection), not only PR-coverage's `by_dev_test` flag.

The bug: a project with real, matched automation coverage at the feature
level (the "Automation Test Coverage" panel, which reads
store.get_automation_coverage() directly) but zero PR-coverage runs showed
0% automation on the Dashboard, because _covered_and_dev_sets() only ever
looked at self.coverage (pr_coverage). Reproduced here with an in-memory
fake store (same pattern as tests/test_store_degradation.py's _FakeCases and
tests/test_coverage_snapshots.py's _FakeCollection) rather than a real
MongoDB.
"""
from bson import ObjectId

from store import Store


class _FakeCollection:
    """In-memory stand-in supporting exactly the query shapes dashboard.py
    issues: find({...}) with plain equality / $in, find_one, count_documents."""

    def __init__(self, docs=None):
        self.docs = docs or []

    def _matches(self, doc, query):
        for k, v in (query or {}).items():
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def find(self, query=None, projection=None):
        return [d for d in self.docs if self._matches(d, query)]

    def find_one(self, query=None, projection=None, **kw):
        matches = self.find(query)
        return matches[0] if matches else None

    def count_documents(self, query=None):
        return len(self.find(query))


def _store(*, coverage_docs=None, automation_docs=None, features=None,
          cases=None, assoc=None, projects=None):
    """A bare Store (no real Mongo connection) with fake collections for
    every one of dashboard()'s dependencies.

    `automation_coverage` (and `test_repo_cases`) are read-only @property
    definitions in CodeCoverageMixin that read `self.db[...]` -- they can't be
    set directly on the instance, so `self.db` is faked as a plain dict instead.
    """
    s = Store.__new__(Store)
    s.db = {"automation_coverage": _FakeCollection(automation_docs or [])}
    s.coverage = _FakeCollection(coverage_docs or [])
    s.features = _FakeCollection(features or [])
    s.cases = _FakeCollection(cases or [])
    s.assoc = _FakeCollection(assoc or [])
    s.projects = _FakeCollection(projects or [])
    s.prs = _FakeCollection([])
    s.repos = _FakeCollection([])
    s.steps = _FakeCollection([])
    return s


class TestCoveredAndDevSets:
    """_covered_and_dev_sets() in isolation -- the actual fixed method."""

    def test_by_dev_test_from_pr_coverage_still_counts(self):
        s = _store(coverage_docs=[
            {"covered": [{"test_case_id": "c1", "by_dev_test": True},
                        {"test_case_id": "c2", "by_dev_test": False}]},
        ])
        covered, dev = s._covered_and_dev_sets()
        assert covered == {"c1", "c2"}
        assert dev == {"c1"}

    def test_automation_scan_match_counts_even_with_no_pr_coverage(self):
        # The exact bug scenario: automation_coverage has real matches, but
        # self.coverage (pr_coverage) is completely empty.
        s = _store(automation_docs=[
            {"feature_id": "f1", "items": [
                {"generated_id": "c1", "status": "covered"},
                {"generated_id": "c2", "status": "missing"},
            ]},
        ])
        covered, dev = s._covered_and_dev_sets()
        assert covered == set()
        assert dev == {"c1"}

    def test_both_sources_combine_without_duplication(self):
        s = _store(
            coverage_docs=[{"covered": [{"test_case_id": "c1", "by_dev_test": True}]}],
            automation_docs=[{"feature_id": "f1", "items": [
                {"generated_id": "c1", "status": "covered"},   # same case, both sources
                {"generated_id": "c2", "status": "covered"},   # only the scan found this one
            ]}],
        )
        covered, dev = s._covered_and_dev_sets()
        assert dev == {"c1", "c2"}

    def test_missing_status_items_are_not_counted_as_automated(self):
        s = _store(automation_docs=[
            {"feature_id": "f1", "items": [{"generated_id": "c1", "status": "missing"}]},
        ])
        _, dev = s._covered_and_dev_sets()
        assert dev == set()

    def test_item_without_generated_id_is_skipped_not_crashed(self):
        s = _store(automation_docs=[
            {"feature_id": "f1", "items": [{"status": "covered"}]},  # malformed/legacy row
        ])
        _, dev = s._covered_and_dev_sets()   # must not raise
        assert dev == set()

    def test_empty_items_list_is_fine(self):
        s = _store(automation_docs=[{"feature_id": "f1", "items": []}])
        _, dev = s._covered_and_dev_sets()
        assert dev == set()

    def test_no_automation_coverage_docs_at_all(self):
        s = _store()
        covered, dev = s._covered_and_dev_sets()
        assert covered == set() and dev == set()


class TestDashboardAutomationPct:
    """dashboard()'s aggregate automation_pct end to end -- reproduces the
    exact bug report: a feature with 21/36 automated cases at the panel
    level must not show 0% on the Dashboard."""

    def test_reproduces_and_fixes_the_reported_bug(self):
        fid = str(ObjectId())
        c_automated = str(ObjectId())
        c_not_automated = str(ObjectId())

        s = _store()
        # Real ObjectId so dashboard()'s `str(p["_id"])` round-trips predictably.
        project_oid = ObjectId()
        pid = str(project_oid)
        s.projects = _FakeCollection([{"_id": project_oid, "name": "NearU"}])
        s.features = _FakeCollection([
            {"_id": ObjectId(fid), "group_id": "g1", "version": 1,
             "project_id": pid, "sources": []},
        ])
        s.assoc = _FakeCollection([
            {"feature_id": fid, "test_case_id": c_automated},
            {"feature_id": fid, "test_case_id": c_not_automated},
        ])
        s.cases = _FakeCollection([
            {"_id": ObjectId(c_automated), "type": "functional"},
            {"_id": ObjectId(c_not_automated), "type": "functional"},
        ])
        # The bug's exact shape: automation_coverage HAS real matches...
        s.db["automation_coverage"] = _FakeCollection([
            {"feature_id": fid, "version": 1, "items": [
                {"generated_id": c_automated, "status": "covered"},
                {"generated_id": c_not_automated, "status": "missing"},
            ]},
        ])
        # ...but pr_coverage (self.coverage) is completely empty.
        s.coverage = _FakeCollection([])

        result = s.dashboard()

        assert result["coverage"]["automated_cases"] == 1
        assert result["coverage"]["automation_pct"] == 50.0
        assert result["projects"][0]["automation_pct"] == 50.0

    def test_zero_automation_when_nothing_matched_anywhere(self):
        # Sanity check: the fix must not manufacture automation out of nothing.
        fid = str(ObjectId())
        c1 = str(ObjectId())
        project_oid = ObjectId()
        pid = str(project_oid)

        s = _store()
        s.projects = _FakeCollection([{"_id": project_oid, "name": "Empty"}])
        s.features = _FakeCollection([
            {"_id": ObjectId(fid), "group_id": "g1", "version": 1,
             "project_id": pid, "sources": []},
        ])
        s.assoc = _FakeCollection([{"feature_id": fid, "test_case_id": c1}])
        s.cases = _FakeCollection([{"_id": ObjectId(c1), "type": "functional"}])
        s.db["automation_coverage"] = _FakeCollection([
            {"feature_id": fid, "version": 1,
             "items": [{"generated_id": c1, "status": "missing"}]},
        ])
        s.coverage = _FakeCollection([])

        result = s.dashboard()
        assert result["coverage"]["automated_cases"] == 0
        assert result["coverage"]["automation_pct"] == 0
