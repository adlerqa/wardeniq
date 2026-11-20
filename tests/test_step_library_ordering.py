"""Ticket #270: "Step library: list_steps orders and pages by the stored
usage_count, which is inflated and never decremented".

`Store.list_steps()` (app/store/steps_test_cases.py) sorted and paged by the
stored `usage_count`, but showed a different number next to it: the count of
distinct cases using the step (`used_in_cases`). The stored counter is
incremented on every reuse of a step and never decremented - not when a case
stops using the step and not when the case is deleted - so the library was
ordered by a number that can be far from the one it displays, and a page of
N could leave out a step with a higher real count.

The order is now the count the list shows, with a stable tie-break, and the
paging follows that order.

Uses mongomock (a real MongoDB-aggregation-semantics-compatible in-memory
server) rather than mocking the aggregation by hand, so the pipeline itself
is genuinely exercised end to end - not just asserted to "look right".
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


def add_step(store, action, usage_count):
    """A step with a stored usage_count, as the store keeps it."""
    return str(store.steps.insert_one(
        {"action": action, "expected": "N/A", "embedding": [0.1] * 8,
         "usage_count": usage_count}).inserted_id)


class TestStepLibraryOrdering:
    def test_the_order_follows_the_count_the_list_shows(self, mongo_store):
        # A was reused a lot in the past (stored 5) but only one case uses it
        # now; B is used by three cases but was reused less (stored 2).
        a = add_step(mongo_store, "A", 5)
        b = add_step(mongo_store, "B", 2)
        mongo_store.cases.insert_one({"title": "Case 1", "step_ids": [a]})
        mongo_store.cases.insert_one({"title": "Case 2", "step_ids": [b]})
        mongo_store.cases.insert_one({"title": "Case 3", "step_ids": [b]})
        mongo_store.cases.insert_one({"title": "Case 4", "step_ids": [b]})

        listed = mongo_store.list_steps()

        assert [s["id"] for s in listed] == [b, a]
        assert [s["used_in_cases"] for s in listed] == [3, 1]

    def test_paging_follows_that_order(self, mongo_store):
        a = add_step(mongo_store, "A", 5)
        b = add_step(mongo_store, "B", 2)
        c = add_step(mongo_store, "C", 7)
        mongo_store.cases.insert_one({"title": "Case 1", "step_ids": [a]})
        mongo_store.cases.insert_one({"title": "Case 2", "step_ids": [b]})
        mongo_store.cases.insert_one({"title": "Case 3", "step_ids": [b]})
        mongo_store.cases.insert_one({"title": "Case 4", "step_ids": [c]})

        # C is used by one case, A by one case, B by two: B comes first, then
        # A and C in a stable order.
        first_page = mongo_store.list_steps(limit=1)
        assert len(first_page) == 1
        assert first_page[0]["id"] == b

        second_page = mongo_store.list_steps(limit=1, skip=1)
        assert len(second_page) == 1
        assert second_page[0]["id"] in (a, c)

        # The step with the highest stored counter is NOT first, even though
        # it is used by only one case.
        assert mongo_store.list_steps(limit=1)[0]["id"] != c

    def test_steps_with_the_same_count_keep_a_stable_order(self, mongo_store):
        a = add_step(mongo_store, "A", 1)
        b = add_step(mongo_store, "B", 1)
        mongo_store.cases.insert_one({"title": "Case 1", "step_ids": [a]})
        mongo_store.cases.insert_one({"title": "Case 2", "step_ids": [b]})

        first = mongo_store.list_steps()
        second = mongo_store.list_steps()

        assert [s["id"] for s in first] == [s["id"] for s in second]
        assert {s["id"] for s in first} == {a, b}

    def test_a_case_using_a_step_twice_counts_once(self, mongo_store):
        a = add_step(mongo_store, "A", 1)
        mongo_store.cases.insert_one({"title": "Case 1", "step_ids": [a, a]})

        listed = mongo_store.list_steps()

        assert listed[0]["used_in_cases"] == 1
