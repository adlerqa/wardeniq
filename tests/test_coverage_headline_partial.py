"""Headline code coverage must not count "partial" PR hits (issue #249 feedback).

The reported bug: linking ONE unrelated PR to a feature made every test case
"covered" at 0.35 confidence, and the dashboard then read 100%. The worker
(app/workers/code_coverage_worker.py `_pr_coverage`) stores a grounded scope
hit that the LLM did not confirm as status "partial", but the rollups
(`feature_coverage_report` and the dashboard) added every entry to the covered
set regardless of status.

Uses in-memory fakes (same pattern as tests/test_dashboard_automation_coverage.py),
no MongoDB.
"""
from bson import ObjectId

from store import Store

# feature_coverage_report looks each case up by ObjectId, so these must be valid ids.
C1, C2, C3, C4, OTHER = (str(ObjectId()) for _ in range(5))


class _FakeCollection:
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
        m = self.find(query)
        return m[0] if m else None

    def count_documents(self, query=None):
        return len(self.find(query))


def _entry(cid, status=None, confidence=None, by_dev_test=False):
    e = {"test_case_id": cid, "by_dev_test": by_dev_test, "confidence": confidence}
    if status is not None:
        e["status"] = status
    return e


def _report_store(case_ids, pr_covers):
    """Store whose feature `f1` has `case_ids` and one PR per element of `pr_covers`
    (each a list of coverage entries)."""
    s = Store.__new__(Store)
    s.feature_test_case_ids = lambda fid: list(case_ids)
    s.list_prs = lambda feature_id=None: [
        {"id": f"pr{i}", "number": i, "title": f"PR {i}", "repo_id": "r1"}
        for i in range(len(pr_covers))]
    s.coverage = _FakeCollection([{"pr_id": f"pr{i}", "covered": c}
                                  for i, c in enumerate(pr_covers)])
    s.cases = _FakeCollection([])
    # feature_coverage_report looks cases up by ObjectId; the fake returns None -> "(removed)".
    return s


class TestFeatureCoverageReport:
    def test_reported_scenario_partial_hits_do_not_reach_100_percent(self):
        # One unrelated PR, all three cases hit by grounding only at 0.35.
        s = _report_store([C1, C2, C3], [
            [_entry(C1, "partial", 0.35), _entry(C2, "partial", 0.35),
             _entry(C3, "partial", 0.35)],
        ])
        rep = s.feature_coverage_report("f1")
        assert rep["covered"] == 0
        assert rep["coverage_pct"] == 0
        assert rep["partial"] == 3
        assert rep["partial_pct"] == 100.0
        assert rep["uncovered"] == 3          # partial is not covered

    def test_confirmed_cases_still_count(self):
        s = _report_store([C1, C2, C3, C4], [
            [_entry(C1, "covered", 0.9), _entry(C2, "partial", 0.35)],
        ])
        rep = s.feature_coverage_report("f1")
        assert rep["covered"] == 1
        assert rep["coverage_pct"] == 25.0
        assert rep["partial"] == 1

    def test_case_covered_by_one_pr_and_partial_in_another_counts_once_as_covered(self):
        s = _report_store([C1, C2], [
            [_entry(C1, "partial", 0.35)],
            [_entry(C1, "covered", 0.8)],
        ])
        rep = s.feature_coverage_report("f1")
        assert rep["covered"] == 1
        assert rep["partial"] == 0            # not double-counted
        assert rep["coverage_pct"] == 50.0

    def test_entries_stored_before_status_existed_count_as_covered(self):
        s = _report_store([C1, C2], [[_entry(C1), _entry(C2)]])
        rep = s.feature_coverage_report("f1")
        assert rep["covered"] == 2
        assert rep["coverage_pct"] == 100.0

    def test_partial_for_a_case_not_in_the_feature_is_ignored(self):
        s = _report_store([C1], [[_entry(OTHER, "partial", 0.35)]])
        rep = s.feature_coverage_report("f1")
        assert rep["partial"] == 0

    def test_no_cases_does_not_divide_by_zero(self):
        s = _report_store([], [[_entry(C1, "partial")]])
        rep = s.feature_coverage_report("f1")
        assert rep["coverage_pct"] == 0 and rep["partial_pct"] == 0

    def test_dev_tested_is_independent_of_status(self):
        # by_dev_test is a separate signal (a developer test file in the PR).
        s = _report_store([C1], [[_entry(C1, "partial", 0.35, by_dev_test=True)]])
        rep = s.feature_coverage_report("f1")
        assert rep["dev_tested"] == 1
        assert rep["covered"] == 0


class TestDashboardRollup:
    def _store(self, coverage_docs):
        s = Store.__new__(Store)
        s.db = {"automation_coverage": _FakeCollection([])}
        s.coverage = _FakeCollection(coverage_docs)
        return s

    def test_partial_is_not_in_the_covered_set(self):
        s = self._store([{"covered": [_entry("c1", "covered"), _entry("c2", "partial")]}])
        covered, dev = s._covered_and_dev_sets()
        assert covered == {"c1"}

    def test_coverage_sets_split_covered_partial_and_dev(self):
        s = self._store([{"covered": [
            _entry("c1", "covered", by_dev_test=True),
            _entry("c2", "partial"),
            _entry("c3", "covered"), _entry("c3", "partial"),   # covered wins
        ]}])
        covered, partial, dev = s._coverage_sets()
        assert covered == {"c1", "c3"}
        assert partial == {"c2"}
        assert dev == {"c1"}

    def test_legacy_entries_without_status_are_covered(self):
        s = self._store([{"covered": [_entry("c1")]}])
        covered, partial, _ = s._coverage_sets()
        assert covered == {"c1"} and partial == set()
