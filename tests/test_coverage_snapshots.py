"""Coverage snapshot persistence (issue #45).

Uses a lightweight fake `db["coverage_snapshots"]` collection (in-memory,
supporting exactly the find_one/find/sort/skip/limit/insert_one/delete_many
shapes the mixin actually issues) plus a stubbed `dashboard()`, rather than a
real MongoDB -- same pattern as tests/test_store_degradation.py's `_FakeCases`.
This tests the mixin's own logic (event validation, dedup window, retention
pruning, optional-field handling) directly; standard pymongo query semantics
(sort/skip/limit/$gte/$in) are not re-verified here.
"""
import time

import pytest

from store import Store


class _FakeCollection:
    """In-memory stand-in for exactly the pymongo calls CoverageSnapshotsMixin
    makes: find_one(query, sort=...), find(query, projection=None) with a
    chainable .sort()/.skip()/.limit(), insert_one(doc), delete_many(query)."""

    def __init__(self):
        self.docs = []
        self._next_id = 1

    def _matching(self, query):
        query = query or {}
        out = []
        for d in self.docs:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict) and "$gte" in v:
                    ok = ok and d.get(k, 0) >= v["$gte"]
                elif isinstance(v, dict) and "$in" in v:
                    ok = ok and d.get(k) in v["$in"]
                else:
                    ok = ok and d.get(k) == v
            if ok:
                out.append(d)
        return out

    def find_one(self, query, sort=None):
        matches = self._matching(query)
        if sort:
            key, direction = sort[0]
            matches = sorted(matches, key=lambda d: d[key], reverse=(direction == -1))
        return dict(matches[0]) if matches else None

    def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = self._next_id
        self._next_id += 1
        self.docs.append(doc)
        from types import SimpleNamespace
        return SimpleNamespace(inserted_id=doc["_id"])

    def find(self, query=None, projection=None):
        return _FakeCursor(self._matching(query))

    def delete_many(self, query):
        ids = set(query.get("_id", {}).get("$in", []))
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["_id"] not in ids]
        return len(self.docs) - before  # informational only, not asserted on


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: d[key], reverse=(direction == -1))
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


def _store(rollup_by_project=None):
    """A bare Store (no real Mongo connection) with a fake coverage_snapshots
    collection and a stubbed dashboard() returning a controllable rollup."""
    s = Store.__new__(Store)
    s.db = {"coverage_snapshots": _FakeCollection()}
    rollup_by_project = rollup_by_project or {}
    s.dashboard = lambda: {"projects": [
        {"id": pid, **vals} for pid, vals in rollup_by_project.items()
    ]}
    return s


_ROLLUP = {"code_pct": 62.5, "automation_pct": 40.0, "test_cases": 8}


class TestSaveCoverageSnapshot:
    def test_persists_a_snapshot_for_a_recognized_event(self):
        s = _store({"p1": _ROLLUP})
        sid = s.save_coverage_snapshot("p1", "generation")
        assert sid is not None
        docs = s.db["coverage_snapshots"].docs
        assert len(docs) == 1
        assert docs[0]["project_id"] == "p1"
        assert docs[0]["event"] == "generation"
        assert docs[0]["coverage_pct"] == 62.5
        assert docs[0]["automation_pct"] == 40.0
        assert docs[0]["case_count"] == 8

    @pytest.mark.parametrize("event", ["generation", "code_analysis", "mindmap",
                                       "cycle_completion"])
    def test_every_documented_event_type_is_accepted(self, event):
        s = _store({"p1": _ROLLUP})
        assert s.save_coverage_snapshot("p1", event) is not None
        assert s.db["coverage_snapshots"].docs[0]["event"] == event

    def test_unrecognized_event_is_rejected(self):
        s = _store({"p1": _ROLLUP})
        assert s.save_coverage_snapshot("p1", "not_a_real_event") is None
        assert s.db["coverage_snapshots"].docs == []

    def test_missing_project_id_is_a_noop(self):
        s = _store({"p1": _ROLLUP})
        assert s.save_coverage_snapshot(None, "generation") is None
        assert s.save_coverage_snapshot("", "generation") is None
        assert s.db["coverage_snapshots"].docs == []

    def test_project_with_no_rollup_entry_is_a_noop(self):
        # e.g. the project was deleted mid-job -- must not raise.
        s = _store({})  # dashboard() returns no projects at all
        assert s.save_coverage_snapshot("does-not-exist", "generation") is None
        assert s.db["coverage_snapshots"].docs == []

    def test_commit_sha_is_optional(self):
        s = _store({"p1": _ROLLUP})
        s.save_coverage_snapshot("p1", "code_analysis")  # no commit_sha given
        assert s.db["coverage_snapshots"].docs[0]["commit_sha"] is None

    def test_commit_sha_is_recorded_when_given(self):
        s = _store({"p1": _ROLLUP})
        s.save_coverage_snapshot("p1", "code_analysis", commit_sha="abc123")
        assert s.db["coverage_snapshots"].docs[0]["commit_sha"] == "abc123"

    def test_job_id_is_recorded_when_given(self):
        s = _store({"p1": _ROLLUP})
        s.save_coverage_snapshot("p1", "generation", job_id="job-42")
        assert s.db["coverage_snapshots"].docs[0]["job_id"] == "job-42"


class TestDuplicateRetryBehavior:
    def test_same_event_retried_within_the_window_does_not_duplicate(self):
        s = _store({"p1": _ROLLUP})
        first = s.save_coverage_snapshot("p1", "generation")
        second = s.save_coverage_snapshot("p1", "generation")  # immediate retry
        assert first == second
        assert len(s.db["coverage_snapshots"].docs) == 1

    def test_different_events_for_the_same_project_both_persist(self):
        s = _store({"p1": _ROLLUP})
        s.save_coverage_snapshot("p1", "generation")
        s.save_coverage_snapshot("p1", "mindmap")
        assert len(s.db["coverage_snapshots"].docs) == 2

    def test_same_event_outside_the_window_creates_a_new_snapshot(self):
        import store.coverage_snapshots as cs_mod
        s = _store({"p1": _ROLLUP})
        first = s.save_coverage_snapshot("p1", "generation")
        # Backdate the existing snapshot past the dedup window.
        s.db["coverage_snapshots"].docs[0]["at"] -= (
            cs_mod.SNAPSHOT_DEDUP_WINDOW_SECONDS + 5)
        second = s.save_coverage_snapshot("p1", "generation")
        assert first != second
        assert len(s.db["coverage_snapshots"].docs) == 2

    def test_same_event_for_different_projects_both_persist(self):
        s = _store({"p1": _ROLLUP, "p2": _ROLLUP})
        s.save_coverage_snapshot("p1", "generation")
        s.save_coverage_snapshot("p2", "generation")
        assert len(s.db["coverage_snapshots"].docs) == 2


class TestRetentionPolicy:
    def test_pruning_keeps_only_the_most_recent_n(self):
        import store.coverage_snapshots as cs_mod
        s = _store({"p1": _ROLLUP})
        cap = 5
        original = cs_mod.SNAPSHOT_RETENTION_PER_PROJECT
        cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = cap
        try:
            now = time.time()
            # Insert more than the cap directly (bypassing dedup) with distinct
            # timestamps, then prune.
            for i in range(cap + 3):
                s.db["coverage_snapshots"].insert_one({
                    "project_id": "p1", "event": "generation", "at": now + i,
                    "commit_sha": None, "job_id": None,
                    "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
                })
            s._prune_coverage_snapshots("p1")
            remaining = s.db["coverage_snapshots"].docs
            assert len(remaining) == cap
            # The newest `cap` snapshots survive (highest `at` values).
            assert sorted(d["at"] for d in remaining) == sorted(
                now + i for i in range(3, cap + 3))
        finally:
            cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = original

    def test_pruning_does_not_touch_other_projects(self):
        import store.coverage_snapshots as cs_mod
        s = _store({"p1": _ROLLUP, "p2": _ROLLUP})
        original = cs_mod.SNAPSHOT_RETENTION_PER_PROJECT
        cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = 2
        try:
            now = time.time()
            for i in range(5):
                s.db["coverage_snapshots"].insert_one({
                    "project_id": "p1", "event": "generation", "at": now + i,
                    "commit_sha": None, "job_id": None,
                    "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
                })
            s.db["coverage_snapshots"].insert_one({
                "project_id": "p2", "event": "generation", "at": now,
                "commit_sha": None, "job_id": None,
                "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
            })
            s._prune_coverage_snapshots("p1")
            remaining = s.db["coverage_snapshots"].docs
            assert sum(1 for d in remaining if d["project_id"] == "p1") == 2
            assert sum(1 for d in remaining if d["project_id"] == "p2") == 1
        finally:
            cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = original

    def test_saving_a_snapshot_triggers_pruning(self):
        import store.coverage_snapshots as cs_mod
        s = _store({"p1": _ROLLUP})
        original = cs_mod.SNAPSHOT_RETENTION_PER_PROJECT
        cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = 2
        try:
            now = time.time()
            for i, event in enumerate(["generation", "mindmap", "code_analysis"]):
                s.db["coverage_snapshots"].insert_one({
                    "project_id": "p1", "event": event, "at": now - 1000 + i,
                    "commit_sha": None, "job_id": None,
                    "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
                })
            # A fresh, non-duplicate save should trigger the prune down to 2.
            s.save_coverage_snapshot("p1", "cycle_completion")
            assert len(s.db["coverage_snapshots"].docs) == 2
        finally:
            cs_mod.SNAPSHOT_RETENTION_PER_PROJECT = original


class TestListCoverageSnapshots:
    def test_returns_oldest_first(self):
        s = _store({"p1": _ROLLUP})
        now = time.time()
        for i, event in enumerate(["generation", "mindmap", "code_analysis"]):
            s.db["coverage_snapshots"].insert_one({
                "project_id": "p1", "event": event, "at": now + i,
                "commit_sha": None, "job_id": None,
                "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
            })
        docs = s.list_coverage_snapshots("p1")
        assert [d["event"] for d in docs] == ["generation", "mindmap", "code_analysis"]

    def test_ids_are_strings_not_raw_object_ids(self):
        s = _store({"p1": _ROLLUP})
        s.save_coverage_snapshot("p1", "generation")
        docs = s.list_coverage_snapshots("p1")
        assert isinstance(docs[0]["id"], str)
        assert "_id" not in docs[0]

    def test_only_returns_the_requested_project(self):
        s = _store({"p1": _ROLLUP, "p2": _ROLLUP})
        s.save_coverage_snapshot("p1", "generation")
        s.save_coverage_snapshot("p2", "mindmap")
        docs = s.list_coverage_snapshots("p1")
        assert len(docs) == 1
        assert docs[0]["project_id"] == "p1"

    def test_respects_limit(self):
        s = _store({"p1": _ROLLUP})
        now = time.time()
        for i, event in enumerate(["generation", "mindmap", "code_analysis", "cycle_completion"]):
            s.db["coverage_snapshots"].insert_one({
                "project_id": "p1", "event": event, "at": now + i,
                "commit_sha": None, "job_id": None,
                "coverage_pct": 0, "automation_pct": 0, "case_count": 0,
            })
        docs = s.list_coverage_snapshots("p1", limit=2)
        assert len(docs) == 2
        # limit keeps the most recent, still returned oldest-first.
        assert [d["event"] for d in docs] == ["code_analysis", "cycle_completion"]
