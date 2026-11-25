"""Assigning a PR to a feature (POST /api/prs/{pr_id}/assign) must fetch the PR's changed
files with the PROJECT's GitHub PAT, the same way the manual coverage run does.

The instance-wide GITHUB_TOKEN env var is normally unset (the PAT is stored per project),
so the old route called GitHub without a token, the failure was swallowed, and an EMPTY
coverage result was saved under a job that reported `succeeded`.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.routes import code_coverage as route
from core import deps
from workers import code_coverage_worker as worker
from workers import registry

PAT = "ghp_project_pat"
FILES = [{"filename": "src/search.py", "status": "modified", "additions": 3,
          "deletions": 1, "patch": "@@ -1 +1,3 @@\n-old\n+new\n+lines\n+here"}]


class StubGitHub:
    """Rejects any call that does not carry the project PAT, like a private repo does."""

    def __init__(self, token="", api=None):
        self.token = token

    def _check(self):
        if self.token != PAT:
            raise RuntimeError("404 Not Found (private repository, no valid token)")

    def get_pull(self, owner, name, number):
        self._check()
        return {"number": number, "head": {"sha": "abc"}}

    def get_pull_files(self, owner, name, number):
        self._check()
        return FILES


class SyncThread:
    """Runs the route's background thread inline so the test can look at the result."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def env(monkeypatch):
    store = MagicMock(name="store")
    store.get_settings.return_value = {}
    store.has_running_job.return_value = False
    store.create_job.return_value = "job1"
    store.get_job.return_value = {"status": "running"}
    store.get_feature.return_value = {"id": "f1", "project_id": "p1"}
    store.get_project_github_pat_enc.return_value = "enc"
    store.repos.find_one.return_value = {"_id": "507f1f77bcf86cd799439011", "project_id": "p1", "owner": "acme",
                                         "name": "shop", "full_name": "acme/shop"}
    for mod in (route, registry, deps):
        monkeypatch.setattr(mod, "store", store)
    monkeypatch.setattr(deps.crypto, "decrypt", lambda enc: PAT)
    # No instance-wide token, as in the Docker container.
    monkeypatch.setattr(deps, "GITHUB_TOKEN", "")
    monkeypatch.setattr(worker, "GITHUB_TOKEN", "", raising=False)
    monkeypatch.setattr(deps.github, "GitHub", StubGitHub)
    # Only the route's own `threading` name: the heartbeat thread must stay a real thread.
    monkeypatch.setattr(route, "threading", SimpleNamespace(Thread=SyncThread))
    monkeypatch.setattr(route, "_require_pr_project", lambda request, pr_id: {
        "project_id": "p1", "repo_id": "507f1f77bcf86cd799439011", "number": 7, "title": "Search"})
    monkeypatch.setattr(route, "_require_project", lambda request, pid: None)
    computed = []
    monkeypatch.setattr(route, "_pr_coverage",
                        lambda pr_id, pdoc, files, fid: computed.append((pr_id, files, fid)) or {})
    return store, computed


def _assign():
    return route.assign_pr("pr1", route.AssignPRIn(feature_id="f1"), request=MagicMock())


def test_coverage_is_computed_from_files_fetched_with_the_project_token(env):
    store, computed = env
    assert _assign()["status"] == "computing"
    assert computed == [("pr1", FILES, "f1")]
    assert store.update_job.call_args.kwargs["status"] == "succeeded"


def test_a_fetch_failure_fails_the_job_instead_of_saving_empty_coverage(env, monkeypatch):
    store, computed = env
    store.get_project_github_pat_enc.return_value = None
    monkeypatch.setattr(deps.crypto, "decrypt", lambda enc: "")   # no PAT stored either
    _assign()
    assert computed == []                      # nothing computed from an empty file list
    kw = store.update_job.call_args.kwargs
    assert kw["status"] == "failed"
    assert "could not fetch the changed files of PR #7" in kw["error"]


def test_a_provider_error_is_reported_on_the_job(env, monkeypatch):
    store, computed = env

    class Rejecting(StubGitHub):
        def get_pull(self, owner, name, number):
            raise RuntimeError("401 Bad credentials")

    monkeypatch.setattr(deps.github, "GitHub", Rejecting)
    _assign()
    assert computed == []
    kw = store.update_job.call_args.kwargs
    assert kw["status"] == "failed" and "401 Bad credentials" in kw["error"]
