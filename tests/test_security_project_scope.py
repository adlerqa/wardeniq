"""Project scoping: a user limited to some projects must be refused (403/404) on every
route that addresses another project's data -- by path id or by a body reference.

The route list is enumerated from the live app, so a new route that takes a
project-scoped id is covered automatically; routes that are intentionally not
project-scoped are listed in NOT_PROJECT_SCOPED with the reason.

Every Store method/collection on the app's singleton is replaced with a MagicMock
for the duration of each test (nothing touches MongoDB), and every by-id lookup
resolves to a resource that belongs to OTHER -- a project the user can't access.
"""
from unittest.mock import MagicMock

import auth
import main
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from core import state

client = TestClient(main.app, raise_server_exceptions=False)

OTHER = "507f1f77bcf86cd799439011"     # a project (and every other id) the user can't see
MINE = "507f1f77bcf86cd799439022"

# (method, path) -> why it is not subject to project scoping.
NOT_PROJECT_SCOPED = {
    ("POST", "/api/projects"): "creates a new project",
    ("GET", "/api/steps"): "shared step library (global by design)",
    ("PATCH", "/api/steps/{sid}"): "shared step library (global by design)",
    ("POST", "/api/steps"): "shared step library (global by design)",
    ("DELETE", "/api/steps/{sid}"): "admin-only; shared step library",
    ("POST", "/api/usage/estimate"): "pure cost estimate, no stored data",
    ("GET", "/api/status"): "instance health",
    ("GET", "/api/sync/status"): "instance poller status",
    ("GET", "/api/github/ratelimit"): "instance token rate limit",
    ("GET", "/api/github/my-repos"): "instance token repo list",
    ("GET", "/api/git/accessible-repos"): "uses a caller-supplied PAT only",
    ("GET", "/api/atlassian/accessible-jira-projects"): "instance Jira config",
    ("GET", "/api/atlassian/accessible-confluence-spaces"): "instance Confluence config",
    ("GET", "/api/ollama/models"): "instance model list",
}
# Collection/aggregate routes: they filter to the user's projects instead of
# refusing (asserted by the dedicated tests further down).
FILTERED = {
    ("GET", "/api/projects"), ("GET", "/api/features"), ("GET", "/api/jobs"),
    ("GET", "/api/test-cases"), ("GET", "/api/documents"), ("GET", "/api/dashboard"),
    ("GET", "/api/tags"), ("GET", "/api/usage"), ("POST", "/api/retrieve"),
}
SELF_SERVICE_PREFIXES = ("/api/auth/", "/api/invite/", "/api/webhook/",
                         "/api/integrations/")


def _scoped_user():
    return {"id": "u1", "email": "u1@example.com", "role": "editor", "active": True,
            "session_version": 0, "all_projects": False, "project_ids": [MINE]}


@pytest.fixture
def fake_store(monkeypatch):
    s = main.store
    for name in dir(type(s)):
        if name.startswith("__"):
            continue
        if callable(getattr(type(s), name, None)):
            monkeypatch.setattr(s, name, MagicMock(name=name), raising=False)
    for name, val in list(vars(s).items()):
        if type(val).__module__.startswith("pymongo"):
            monkeypatch.setattr(s, name, MagicMock(name=name))
    user = _scoped_user()
    other = {"id": OTHER, "project_id": OTHER, "feature_id": OTHER, "repo_id": OTHER,
             "repo_type": "test", "s3_key": "k", "case_ids": [OTHER], "number": 1,
             "pr_number": 1, "owner": "o", "name": "n", "full_name": "o/n",
             "features": [{"project_id": OTHER}], "type": "x", "status": "running"}
    s.get_user = MagicMock(return_value=user)
    for getter in ("get_feature", "get_repo", "get_cycle", "get_job", "get_validator_run",
                   "get_test_plan_run", "get_code_coverage_run", "get_commit_analysis",
                   "get_cycle_template", "get_stored_document", "get_feature_import",
                   "get_project", "get_case"):
        setattr(s, getter, MagicMock(return_value=dict(other)))
    s.prs.find_one = MagicMock(return_value=dict(other, _id=OTHER))
    s.repos.find_one = MagicMock(return_value=dict(other, _id=OTHER))
    s.add_audit = MagicMock()
    monkeypatch.setattr(state, "embedder", MagicMock())
    return s


def _cookie():
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}


def _value_for(field_name, annotation):
    ann = str(annotation)
    if "list" in ann:
        return [] if "dict" in ann else [OTHER]
    if "bool" in ann:
        return False
    if "int" in ann and "str" not in ann:
        return 1
    if "dict" in ann:
        return {}
    return OTHER


def _request_kwargs(route: APIRoute):
    if not route.body_field:
        return {}
    model = route.body_field.type_
    if model is dict:
        return {"json": {"case_ids": [OTHER], "item_ids": [OTHER], "status": "passed",
                         "testCaseIds": [OTHER], "feature_id": OTHER, "project_id": OTHER}}
    if isinstance(model, type) and issubclass(model, BaseModel):
        fields = model.model_fields
        if model.__name__.startswith("Body_"):      # multipart form
            data, files = {}, {}
            for n, f in fields.items():
                if "UploadFile" in str(f.annotation):
                    files[n] = ("a.csv", b"title\nx\n", "text/csv")
                else:
                    v = _value_for(n, f.annotation)
                    data[n] = str(v).lower() if isinstance(v, bool) else (
                        OTHER if isinstance(v, (list, dict)) else str(v))
            return {"data": data, "files": files or {"file": ("a.csv", b"x", "text/csv")}}
        return {"json": {n: _value_for(n, f.annotation) for n, f in fields.items()}}
    return {"json": {}}


def _scoped_routes():
    out = []
    for r in main.app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith("/api/"):
            continue
        if r.path.startswith(SELF_SERVICE_PREFIXES):
            continue
        for m in sorted(r.methods):
            key = (m, r.path)
            if key in NOT_PROJECT_SCOPED or key in FILTERED:
                continue
            out.append(pytest.param(m, r, id=f"{m} {r.path}"))
    return out


@pytest.mark.parametrize("method,route", _scoped_routes())
def test_scoped_user_refused_for_other_project(fake_store, method, route):
    path = route.path
    for p in route.param_convertors:
        path = path.replace("{" + p + "}", "csv" if p == "fmt" else OTHER)
    r = client.request(method, path, cookies=_cookie(), **_request_kwargs(route))
    assert r.status_code in (403, 404), (method, route.path, r.status_code, r.text[:300])


# ------------------------------------------------------------ filtered collections
def test_usage_rejects_other_project_and_scopes_global_view(fake_store):
    r = client.get(f"/api/usage?project_id={OTHER}", cookies=_cookie())
    assert r.status_code == 403
    fake_store.usage_summary.return_value = {}
    r = client.get("/api/usage", cookies=_cookie())
    assert r.status_code == 200
    assert fake_store.usage_summary.call_args.kwargs["project_ids"] == {MINE}


def test_dashboard_and_tags_are_scoped(fake_store):
    fake_store.dashboard.return_value = {}
    fake_store.all_tags.return_value = []
    assert client.get("/api/dashboard", cookies=_cookie()).status_code == 200
    assert fake_store.dashboard.call_args.kwargs["project_ids"] == {MINE}
    assert client.get("/api/tags", cookies=_cookie()).status_code == 200
    assert fake_store.all_tags.call_args.kwargs["project_ids"] == {MINE}


def test_retrieve_hides_other_projects_cases(fake_store):
    fake_store.search_cases.return_value = ([{"id": "c-other"}, {"id": "c-mine"}], [])
    fake_store.get_case = MagicMock(side_effect=lambda cid: {
        "id": cid, "features": [{"project_id": MINE if cid == "c-mine" else OTHER}]})
    r = client.post("/api/retrieve", cookies=_cookie(), json={"text": "login"})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["results"]] == ["c-mine"]


def test_documents_list_hides_other_projects(fake_store):
    fake_store.list_stored_documents.return_value = [
        {"id": "d1", "project_id": OTHER}, {"id": "d2", "project_id": MINE},
        {"id": "d3", "project_id": ""}]
    r = client.get("/api/documents", cookies=_cookie())
    assert r.status_code == 200
    assert [d["id"] for d in r.json()["documents"]] == ["d2"]
    assert client.get(f"/api/documents?project_id={OTHER}", cookies=_cookie()).status_code == 403


def test_reassign_validates_before_writing(fake_store):
    # Even an all-projects user: a run without repo/PR must not be modified.
    user = dict(_scoped_user(), all_projects=True)
    fake_store.get_user = MagicMock(return_value=user)
    fake_store.get_code_coverage_run = MagicMock(return_value={"feature_id": OTHER})
    r = client.post(f"/api/code-coverage/runs/{OTHER}/reassign", cookies=_cookie(),
                    json={"feature_id": OTHER})
    assert r.status_code == 400
    fake_store.update_code_coverage_run.assert_not_called()
