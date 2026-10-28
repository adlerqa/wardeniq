"""Issue #175: the case editor's "This exact step is shared by N testcases" note
counted step references, not test cases.

Repro: one test case uses the same step at two positions -> the editor says
"shared by 2 testcases" although only one case uses it, and removing the
duplicate leaves the count at 2.

Root cause: the editor reads `usage_count` from `get_case()`'s resolved steps,
which was the step document's stored counter. `get_or_create_step()` bumps it
with $inc on every reuse (so a step reused twice in one case counts twice) and
nothing ever decrements it (so removing a use never lowers it).

Fix: `get_case()` asks `resolve_steps(..., live_usage=True)`, which recounts
distinct cases from cases.step_ids with the same aggregation `list_steps()`
already uses for the step library.

Uses mongomock (real aggregate semantics) so the actual query runs.
"""
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

mongomock = pytest.importorskip("mongomock")

import store.base as store_base  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture
def mongo_store(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    return Store("mongodb://localhost/?", "wardeniq_test", 8)


def _step_id_for(steps, action):
    return next(s["id"] for s in steps if s["action"] == action)


def _make_case(store, title, step_ids):
    return store.create_case(title, "functional", "High", "", step_ids, [],
                             [0.1] * 8, None)


def _shared_by(store, cid, sid):
    steps = store.get_case(cid)["steps"]
    return next(s["usage_count"] for s in steps if s["id"] == sid)


class TestStepSharedByCount:
    def test_one_case_using_a_step_twice_counts_once(self, mongo_store):
        emb = [0.3] * 8
        # The real generation path: the second use of the same step text reuses
        # the step (and $inc's its stored counter to 2).
        first = mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)
        second = mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)
        assert second["origin"] == "reused"
        sid = first["step_id"]
        other = mongo_store.get_or_create_step("Open page", "Page shown", [0.9] + [0.0] * 7, 0.9)
        cid = _make_case(mongo_store, "Save twice", [sid, other["step_id"], sid])

        assert _shared_by(mongo_store, cid, sid) == 1

    def test_count_matches_distinct_cases_and_drops_after_an_edit(self, mongo_store):
        emb = [0.3] * 8
        sid = mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)["step_id"]
        mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)
        mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)
        a = _make_case(mongo_store, "A", [sid, sid])
        b = _make_case(mongo_store, "B", [sid])
        assert _shared_by(mongo_store, a, sid) == 2

        # Case B stops using the step: A is now the only case left.
        mongo_store.update_case(b, "B", "functional", "High", "", [], [], [0.1] * 8)
        assert _shared_by(mongo_store, a, sid) == 1

    def test_step_order_and_duplicates_are_kept(self, mongo_store):
        emb = [0.3] * 8
        sid = mongo_store.get_or_create_step("Click Save", "Saved", emb, 0.9)["step_id"]
        oid = mongo_store.get_or_create_step("Open page", "Page shown", [0.9] + [0.0] * 7, 0.9)["step_id"]
        cid = _make_case(mongo_store, "Order", [oid, sid, sid])
        assert [s["id"] for s in mongo_store.get_case(cid)["steps"]] == [oid, sid, sid]
