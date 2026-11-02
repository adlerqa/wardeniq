"""GET /api/features without ?project_id= hid every feature from project-scoped users.

The route keeps only rows whose `project_id` is in the user's allowed projects,
but `Store.list_features()` built its rows without a `project_id` key, so the
filter always produced an empty list for anyone not allowed all projects.

Uses mongomock so `list_features()`'s real query runs.
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


def test_list_features_rows_carry_project_id(mongo_store):
    p1 = mongo_store.create_project("Mine")
    p2 = mongo_store.create_project("Other")
    f1 = mongo_store.create_feature("Login", p1, ["a.md"], "text", "summary", [0.1] * 8)
    f2 = mongo_store.create_feature("Checkout", p2, ["b.md"], "text", "summary", [0.2] * 8)
    rows = {f["id"]: f for f in mongo_store.list_features(None)}
    assert rows[f1]["project_id"] == p1
    assert rows[f2]["project_id"] == p2


def test_unfiltered_list_keeps_only_the_scoped_users_projects(mongo_store, monkeypatch):
    from api.routes import features as routes

    p1 = mongo_store.create_project("Mine")
    p2 = mongo_store.create_project("Other")
    f1 = mongo_store.create_feature("Login", p1, ["a.md"], "text", "summary", [0.1] * 8)
    mongo_store.create_feature("Checkout", p2, ["b.md"], "text", "summary", [0.2] * 8)
    monkeypatch.setattr(routes, "store", mongo_store)
    monkeypatch.setattr(routes, "_current_user", lambda request: {"role": "viewer"})
    monkeypatch.setattr(routes, "_allowed_project_ids", lambda user: {p1})
    assert [f["id"] for f in routes.list_features(request=None)["features"]] == [f1]
