"""Poller sync_repo regression tests (issue #178).

Covers the three reported defects with a mocked GitHub client and a fake
store — no MongoDB, no network:

1. A PR whose ingest fails (``ingest_pr_tracked`` returns ``None`` because
   ``run_tracked`` swallowed the exception and marked the job failed) must
   NOT advance ``last_synced`` past itself, or it is never retried.
2. ``sync_repo`` must paginate past the first ``per_page=30`` page, or busy
   repos silently lose PRs.
3. ``SYNC["errors"]`` must be capped — it is returned whole by
   ``/api/sync/status`` and otherwise grows without limit.
"""

import types
from datetime import datetime, timezone

import pytest

import background.poller as poller
from core.state import SYNC


def _ts(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()


def _pr(number, updated_at):
    return {"number": number, "updated_at": updated_at,
            "title": f"PR {number}"}


class _FakeRepos:
    def __init__(self, repo):
        self._repo = repo
        self.synced = []  # (repo_id, ts) in call order

    def find(self, query):
        return [self._repo]

    def set_repo_synced(self, repo_id, ts):
        self.synced.append((repo_id, ts))


class _FakeStore:
    def __init__(self, repo):
        self.repos = _FakeRepos(repo)

    def set_repo_synced(self, repo_id, ts):
        self.repos.set_repo_synced(repo_id, ts)


class _FakeGitHub:
    """Paginated stand-in for ``github.GitHub``.

    ``list_pulls`` without ``page`` behaves like the real single-page call
    (page 1 only); with ``page`` it returns that page's slice, so a caller
    that never paginates can only ever see the first page.
    """

    def __init__(self, pulls, fail_list=False):
        self._pulls = pulls
        self._fail_list = fail_list

    def __call__(self, token, api):
        return self

    def list_pulls(self, owner, name, state="all", per_page=30, page=1):
        if self._fail_list:
            raise RuntimeError("boom")
        start = (page - 1) * per_page
        return self._pulls[start:start + per_page]


@pytest.fixture
def sync_env(monkeypatch):
    """Patch poller's collaborators; return a handle for arranging cases."""
    repo = {"_id": "repo1", "owner": "acme", "name": "widget",
            "full_name": "acme/widget", "project_id": "proj1",
            "git_provider": "github", "last_synced": _ts("2026-10-20T00:00:00Z")}
    store = _FakeStore(repo)
    monkeypatch.setattr(poller, "store", store)
    monkeypatch.setattr(poller, "project_github_token", lambda pid: "tok")
    monkeypatch.setattr(poller, "_oid", lambda s: s)
    calls = []
    monkeypatch.setattr(poller, "ingest_pr_tracked",
                        lambda r, pr: calls.append(pr["number"]) or "prid")
    saved_errors = list(SYNC["errors"])
    SYNC["errors"] = []
    yield {"repo": repo, "store": store, "calls": calls}
    SYNC["errors"] = saved_errors


def _install_github(monkeypatch, pulls, fail_list=False):
    fake = _FakeGitHub(pulls, fail_list=fail_list)
    monkeypatch.setattr(poller, "github",
                        types.SimpleNamespace(GitHub=lambda t, a: fake))


def test_failed_ingest_does_not_advance_cursor(sync_env, monkeypatch):
    """A swallowed ingest failure must not move last_synced past the PR."""
    fail_pr = _pr(7, "2026-10-22T00:00:00Z")
    ok_pr = _pr(8, "2026-10-21T00:00:00Z")
    _install_github(monkeypatch, [fail_pr, ok_pr])

    def ingest(repo, pr):
        sync_env["calls"].append(pr["number"])
        return None if pr["number"] == 7 else "prid"

    monkeypatch.setattr(poller, "ingest_pr_tracked", ingest)
    poller.sync_repo("repo1")
    assert sync_env["calls"] == [7, 8]
    assert sync_env["store"].repos.synced == [
        ("repo1", _ts("2026-10-21T00:00:00Z"))]


def test_successful_sync_advances_to_newest(sync_env, monkeypatch):
    """Control: all-success sync still advances to the newest PR."""
    prs = [_pr(1, "2026-10-21T00:00:00Z"), _pr(2, "2026-10-23T00:00:00Z")]
    _install_github(monkeypatch, prs)
    poller.sync_repo("repo1")
    assert sync_env["store"].repos.synced == [
        ("repo1", _ts("2026-10-23T00:00:00Z"))]


def test_pagination_fetches_beyond_first_page(sync_env, monkeypatch):
    """35 updated PRs must all be ingested, not just the first 30."""
    prs = [_pr(n, "2026-10-21T00:00:00Z") for n in range(1, 36)]
    _install_github(monkeypatch, prs)
    poller.sync_repo("repo1")
    assert len(sync_env["calls"]) == 35
    assert sync_env["calls"] == list(range(1, 36))


def test_sync_errors_capped(sync_env, monkeypatch):
    """A list failure on top of a full error log must not grow it past cap."""
    SYNC["errors"] = [f"old-{i}" for i in range(150)]
    _install_github(monkeypatch, [], fail_list=True)
    poller.sync_repo("repo1")
    assert len(SYNC["errors"]) <= 100
    assert SYNC["errors"][-1].endswith("list: boom")
