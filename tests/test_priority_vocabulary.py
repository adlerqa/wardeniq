"""Issue #174: a case's priority was stored in whichever vocabulary its write
path used. Generation stored "P1", the case editor "High", sheet import "Mid",
so the testcase CSV export showed "P1" for a generated case and "HIGH" for the
same case after an edit.

Fix: create_case()/update_case() store priority.normalize_priority(): one
vocabulary, High/Medium/Low (the editor's and the exports'). Boot backfills
existing cases with Store.normalize_case_priorities(), and the report reads any
leftover spelling through the same mapping.

Uses mongomock (real update semantics) so the store's actual writes run.
"""
import csv
import io
from pathlib import Path
import sys

import pytest
from bson import ObjectId

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

mongomock = pytest.importorskip("mongomock")

import report  # noqa: E402
import store.base as store_base  # noqa: E402
from priority import PRIORITIES, normalize_priority  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture
def mongo_store(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    return Store("mongodb://localhost/?", "wardeniq_test", 8)


def _create(store, priority):
    return store.create_case("Login works", "functional", priority, "", [], [],
                             [0.1] * 8, None)


def _stored(store, cid):
    return store.cases.find_one({"_id": ObjectId(cid)})["priority"]


def _csv_priorities(store, cids):
    cases = [store.get_case(cid) for cid in cids]
    body = report.build_testcase_csv({"name": "Login"}, cases).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(body)))
    col = next(r for r in rows if "Priority" in r).index("Priority")
    header_at = next(i for i, r in enumerate(rows) if "Priority" in r)
    return [r[col] for r in rows[header_at + 1:] if r]


class TestPriorityVocabulary:
    def test_generated_and_edited_cases_store_the_same_word(self, mongo_store):
        generated = _create(mongo_store, "P1")       # generation path
        edited = _create(mongo_store, "P1")
        mongo_store.update_case(edited, "Login works", "functional", "High", "",
                                [], [], [0.1] * 8)  # case editor path
        imported = _create(mongo_store, "high")      # any other casing

        assert _stored(mongo_store, generated) == "High"
        assert _stored(mongo_store, edited) == "High"
        assert _stored(mongo_store, imported) == "High"
        assert _csv_priorities(mongo_store, [generated, edited]) == ["High", "High"]

    @pytest.mark.parametrize("raw,canon", [
        ("P0", "High"), ("P1", "High"), ("HIGH", "High"), ("Critical", "High"), ("1", "High"),
        ("P2", "Medium"), ("Mid", "Medium"), ("MEDIUM", "Medium"), (" medium ", "Medium"),
        ("P3", "Low"), ("P4", "Low"), ("LOW", "Low"),
        ("", "Medium"), (None, "Medium"), ("whatever", "Medium"),
    ])
    def test_every_known_spelling_maps_into_the_vocabulary(self, raw, canon):
        assert normalize_priority(raw) == canon
        assert normalize_priority(raw) in PRIORITIES

    def test_boot_backfill_rewrites_old_records_once(self, mongo_store):
        # Records written before the fix, straight into the collection.
        old = {raw: str(mongo_store.cases.insert_one({"title": raw, "priority": raw}).inserted_id)
               for raw in ("P1", "HIGH", "Mid", "P3", "Medium")}

        mongo_store.normalize_case_priorities()

        assert {raw: _stored(mongo_store, cid) for raw, cid in old.items()} == {
            "P1": "High", "HIGH": "High", "Mid": "Medium", "P3": "Low", "Medium": "Medium"}
        assert mongo_store.normalize_case_priorities() == 0

    def test_report_reads_a_leftover_old_spelling_as_the_vocabulary(self):
        assert report._priority_label("P1") == "High"
        assert report._priority_label("HIGH") == "High"
        assert report._priority_label("") == "Medium"
