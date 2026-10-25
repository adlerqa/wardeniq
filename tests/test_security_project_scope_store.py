"""Store-level scoping for the dashboard and tag list (mongomock-backed)."""
import pytest

mongomock = pytest.importorskip("mongomock")

import store.base as store_base  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture
def s(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    st = Store("mongodb://localhost/?", "wardeniq_scope_test", 8)
    pa = str(st.projects.insert_one({"name": "A"}).inserted_id)
    pb = str(st.projects.insert_one({"name": "B"}).inserted_id)
    for pid, tag in ((pa, "alpha"), (pb, "secret-b")):
        fid = str(st.features.insert_one({"project_id": pid, "name": "F", "version": 1}).inserted_id)
        sid = str(st.steps.insert_one({"action": "a", "expected": "e"}).inserted_id)
        cid = str(st.cases.insert_one({"title": "t", "type": "api", "tags": [tag],
                                       "step_ids": [sid]}).inserted_id)
        st.associate(fid, cid, "manual", None)
        st.repos.insert_one({"project_id": pid})
    return st, pa, pb


def test_dashboard_scoped_to_projects(s):
    st, pa, pb = s
    full = st.dashboard()
    assert full["counts"]["projects"] == 2 and full["counts"]["test_cases"] == 2
    scoped = st.dashboard(project_ids={pa})
    assert [p["id"] for p in scoped["projects"]] == [pa]
    c = scoped["counts"]
    assert (c["projects"], c["features"], c["test_cases"], c["test_steps"], c["repos"]) == (1, 1, 1, 1, 1)
    assert st.dashboard(project_ids=set())["counts"]["test_cases"] == 0


def test_tags_scoped_to_projects(s):
    st, pa, pb = s
    assert st.all_tags() == ["alpha", "secret-b"]
    assert st.all_tags(project_ids={pa}) == ["alpha"]
    assert st.all_tags(project_ids=set()) == []
