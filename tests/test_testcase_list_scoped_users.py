"""GET /api/test-cases without ?project_id= leaked every project's cases to
project-scoped users (issue #304).

The route tried to filter the store result with ``res.get("cases")``, but the
store returns ``{"total": ..., "items": ...}`` and its rows carry no ``features``
key, so that filter never ran. A user scoped to project A saw project B's cases
and a global ``total``. The fix pushes the allowed project ids into the store
query so that count/skip/limit apply to the already-scoped set.

Uses mongomock so the real Store.list_test_cases() query runs.
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


def _add_case(st, feature_id, title):
    cid = st.create_case(title, "functional", "P2", "", [], [], [0.1] * 8, feature_id)
    st.associate(feature_id, cid, "created")
    return cid


@pytest.fixture
def two_projects(mongo_store):
    mine = mongo_store.create_project("Mine")
    other = mongo_store.create_project("Other")
    f_mine = mongo_store.create_feature(
        "Login", mine, ["a.md"], "text", "summary", [0.1] * 8)
    f_other = mongo_store.create_feature(
        "Checkout", other, ["b.md"], "text", "summary", [0.2] * 8)
    return mongo_store, mine, other, f_mine, f_other


@pytest.fixture
def scoped_route(two_projects, monkeypatch):
    from api.routes import steps_test_cases as routes

    st, mine, other, _, _ = two_projects
    monkeypatch.setattr(routes, "store", st)
    monkeypatch.setattr(routes, "_current_user", lambda request: {"role": "editor"})
    monkeypatch.setattr(routes, "_allowed_project_ids", lambda user: {mine})
    return routes


def test_scoped_user_sees_only_their_projects_cases(two_projects, scoped_route):
    st, mine, other, f_mine, f_other = two_projects
    mine_case = _add_case(st, f_mine, "Mine case")
    _add_case(st, f_other, "Other case")

    res = scoped_route.list_test_cases(request=None)

    assert [c["id"] for c in res["items"]] == [mine_case]
    assert res["total"] == 1


def test_limit_and_skip_apply_to_the_scoped_set(two_projects, scoped_route):
    st, mine, other, f_mine, f_other = two_projects
    mine_cases = [_add_case(st, f_mine, f"Mine {i}") for i in range(3)]
    for i in range(2):
        _add_case(st, f_other, f"Other {i}")

    page1 = scoped_route.list_test_cases(request=None, limit=2)
    assert [c["id"] for c in page1["items"]] == mine_cases[:2]
    assert page1["total"] == 3

    page2 = scoped_route.list_test_cases(request=None, limit=2, skip=1)
    assert [c["id"] for c in page2["items"]] == mine_cases[1:]
    assert page2["total"] == 3


def test_all_projects_user_still_sees_everything(two_projects, monkeypatch):
    from api.routes import steps_test_cases as routes

    st, mine, other, f_mine, f_other = two_projects
    mine_case = _add_case(st, f_mine, "Mine case")
    other_case = _add_case(st, f_other, "Other case")
    monkeypatch.setattr(routes, "store", st)
    monkeypatch.setattr(routes, "_current_user", lambda request: {"role": "admin"})
    monkeypatch.setattr(routes, "_allowed_project_ids", lambda user: None)

    res = routes.list_test_cases(request=None)

    assert {c["id"] for c in res["items"]} == {mine_case, other_case}
    assert res["total"] == 2
