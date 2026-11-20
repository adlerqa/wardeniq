"""PR #280 review: list_steps against a REAL MongoDB with string step ids.

The API writes `str(inserted_id)` into cases.step_ids while the steps
collection's own _id is an ObjectId. The previous implementation
$lookup'ed localField "_id" (ObjectId) against foreignField "step_ids"
(strings), which a real MongoDB never matches, so every count came back 0
and the library was ordered by step id alone. Mongomock matches across the
two types, which is why the unit tests could not see it. This suite replicates
the API's create paths exactly and asserts against count_documents().

Requires MONGO_TEST_URI; skipped without a reachable server (see pytest.ini).
"""

import os
import uuid

import pytest
from bson import ObjectId
from pymongo import MongoClient
from store import Store

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")


@pytest.fixture(scope="module", autouse=True)
def _require_mongo():
    """Skip this module's tests when no MongoDB is reachable.

    This runs when the module's tests are about to run, not at import time, so a run that
    deselects the dbintegration marker neither waits out the 1.5 s server selection timeout
    nor opens a MongoClient, and the client used for the check is always closed.
    """
    client = None
    try:
        client = MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
    except Exception:  # noqa: BLE001
        pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
                    "db-integration tests)")
    finally:
        if client is not None:
            client.close()


@pytest.fixture()
def store():
    db_name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
    s = Store(MONGO_TEST_URI, db_name, dim=8)
    # tests/conftest.py replaces Store.get_settings at the class level for the
    # whole pytest session; restore the real behaviour for this instance.
    s.get_settings = lambda: s.db["settings"].find_one({"_id": "app"}) or {}
    try:
        s.ensure_indexes()
    except Exception:  # noqa: BLE001
        pass
    try:
        yield s
    finally:
        s.client.drop_database(db_name)
        s.client.close()


def _add_step(store, action, usage_count):
    sid = store.steps.insert_one(
        {"action": action, "expected": "N/A", "embedding": [0.1] * 8,
         "usage_count": usage_count}).inserted_id
    # the API stores str(inserted_id) in cases.step_ids
    return str(sid)


def test_used_in_cases_counts_distinct_cases_as_strings(store):
    a = _add_step(store, "A", 9)
    b = _add_step(store, "B", 1)
    store.cases.insert_one({"title": "Case 1", "step_ids": [a]})
    store.cases.insert_one({"title": "Case 2", "step_ids": [b, b]})
    store.cases.insert_one({"title": "Case 3", "step_ids": [b]})

    listed = store.list_steps()
    by_id = {s["id"]: s for s in listed}

    assert by_id[a]["used_in_cases"] == 1
    assert by_id[b]["used_in_cases"] == 2  # the [b, b] case counts once
    assert listed[0]["id"] == b            # the higher real count sorts first


def test_order_and_paging_follow_the_distinct_case_count(store):
    a = _add_step(store, "A", 7)  # used by 2 cases
    b = _add_step(store, "B", 2)  # used by 1 case, even though stored 7 <
    c = _add_step(store, "C", 0)  # used by no case, goes last in id order
    store.cases.insert_one({"title": "Case 1", "step_ids": [a]})
    store.cases.insert_one({"title": "Case 2", "step_ids": [a, b]})

    first = store.list_steps(limit=1)
    assert [s["id"] for s in first] == [a]

    rest = store.list_steps(limit=2, skip=1)
    assert [s["id"] for s in rest] == [b, c]

    # equal counts keep a stable order
    m = _add_step(store, "M", 0)
    n = _add_step(store, "N", 0)
    twice = store.list_steps()
    first_order = [s["id"] for s in twice]
    second_order = [s["id"] for s in store.list_steps()]
    assert first_order == second_order
    assert first_order.index(m) < first_order.index(n)


def test_objectid_typed_case_reference_does_not_break_the_count(store):
    # the API writes str(inserted_id), but a case that (wrongly) carries the
    # step id as an ObjectId must not crash the listing and must count, since
    # str(ObjectId) normalises to the same hex string on the grouping side
    a = _add_step(store, "A", 3)
    store.cases.insert_one({"title": "Case OBJ", "step_ids": [ObjectId(a)]})
    listed = store.list_steps()
    by_id = {s["id"]: s for s in listed}
    assert by_id[a]["used_in_cases"] == 1
