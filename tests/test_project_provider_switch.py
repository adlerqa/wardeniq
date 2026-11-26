"""Changing a project's default provider preserves its PATs and linked repositories."""
import pytest

mongomock = pytest.importorskip("mongomock")

from api.routes import projects  # noqa: E402
import store.base as store_base  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture
def mongo_store(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    store = Store("mongodb://localhost/?", "wardeniq_test", 8)
    monkeypatch.setattr(projects, "store", store)
    return store


@pytest.mark.parametrize("initial_provider,new_provider", [
    ("github", "gitlab"),
    ("gitlab", "github"),
])
def test_provider_switch_preserves_pats_and_linked_repo(
        mongo_store, initial_provider, new_provider):
    pid = mongo_store.create_project("Demo", default_git_provider=initial_provider)
    github_pat = "fake-github-ciphertext"
    gitlab_pat = "fake-gitlab-ciphertext"
    mongo_store.set_project_github_pat_enc(pid, github_pat)
    mongo_store.set_project_gitlab_pat_enc(pid, gitlab_pat)
    rid = mongo_store.add_repo(
        pid, "acme", "demo", f"https://{initial_provider}.com/acme/demo", "BE",
        git_provider=initial_provider)
    repo_before = mongo_store.get_repo(rid)

    projects.patch_project(pid, projects.ProjectPatchIn(default_git_provider=new_provider))

    assert mongo_store.get_project(pid)["default_git_provider"] == new_provider
    assert mongo_store.get_project_github_pat_enc(pid) == github_pat
    assert mongo_store.get_project_gitlab_pat_enc(pid) == gitlab_pat
    assert mongo_store.get_repo(rid) == repo_before
