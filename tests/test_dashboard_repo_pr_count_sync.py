"""Dashboard vs repository-list PR counts (issue #177).

The dashboard showed 30 PRs while the repository list showed 24 during a
sync. In steady state the two views already read the same `prs` collection
(dashboard rollup counts by `project_id`, the repo list sums per-`repo_id`
counts), so a mid-sync gap is a fetch-timing gap: the two views are fetched
independently while PRs stream in, and nothing on either view says a sync is
running or what scope its number covers.

The fix has two parts, both covered here:

1. The filtered repo route (`repos_for_project`, used by
   `/api/projects/{pid}/repos?repo_type=app|test`) must attach `pr_count`
   exactly like the unfiltered `list_repos` does — before this fix it
   returned repos with no count at all, so the two list shapes disagreed
   about what a repo row carries.
2. `/api/dashboard` must report the poller's sync state, so the dashboard
   can label its counts as in-progress while a sync is running instead of
   presenting a mid-flight snapshot as a final number.

Reproduced with an in-memory fake store (same pattern as
tests/test_dashboard_automation_coverage.py's _FakeCollection) rather than
a real MongoDB.
"""
from bson import ObjectId

from store import Store


class _FakeCollection:
    """In-memory stand-in supporting exactly the query shapes repos_prs.py
    and dashboard.py issue: find({...}) with plain equality / $in / $or /
    $exists, find_one, count_documents, sort."""

    def __init__(self, docs=None):
        self.docs = docs or []

    def _matches(self, doc, query):
        for k, v in (query or {}).items():
            if k == "$or":
                if not any(self._matches(doc, branch) for branch in v):
                    return False
                continue
            if isinstance(v, dict):
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
                elif "$exists" in v:
                    if (k in doc) != v["$exists"]:
                        return False
                else:
                    if doc.get(k) != v:
                        return False
            elif doc.get(k) != v:
                return False
        return True

    def find(self, query=None, projection=None):
        # Copy: real Mongo returns fresh dicts per query, and list_repos /
        # repos_for_project mutate them (pop _id, set id/pr_count).
        return _FakeCursor([dict(d) for d in self.docs
                            if self._matches(d, query)])

    def find_one(self, query=None, projection=None, **kw):
        matches = [dict(d) for d in self.docs if self._matches(d, query)]
        return matches[0] if matches else None

    def count_documents(self, query=None):
        return len([d for d in self.docs if self._matches(d, query)])


class _FakeCursor(list):
    def sort(self, *args, **kwargs):
        return self


def _store(*, projects=None, repos=None, prs=None):
    s = Store.__new__(Store)
    s.projects = _FakeCollection(projects or [])
    s.repos = _FakeCollection(repos or [])
    s.prs = _FakeCollection(prs or [])
    s.features = _FakeCollection([])
    s.cases = _FakeCollection([])
    s.assoc = _FakeCollection([])
    s.steps = _FakeCollection([])
    s.coverage = _FakeCollection([])
    s.db = {"automation_coverage": _FakeCollection([])}
    return s


def _scenario():
    """One project, two repos, 5 PRs: 3 on repo A, 2 on repo B."""
    pid = str(ObjectId())
    repo_a, repo_b = str(ObjectId()), str(ObjectId())
    repos = [
        {"_id": ObjectId(repo_a), "project_id": pid, "full_name": "org/a",
         "repo_type": "app"},
        {"_id": ObjectId(repo_b), "project_id": pid, "full_name": "org/b",
         "repo_type": "app"},
    ]
    prs = [
        {"repo_id": repo_a, "project_id": pid, "number": n}
        for n in (1, 2, 3)
    ] + [
        {"repo_id": repo_b, "project_id": pid, "number": n}
        for n in (4, 5)
    ]
    projects = [{"_id": ObjectId(pid), "name": "p"}]
    return pid, repo_a, repo_b, _store(projects=projects, repos=repos, prs=prs)


class TestFilteredRepoListCounts:
    def test_repos_for_project_attaches_pr_count(self):
        pid, repo_a, repo_b, s = _scenario()
        by_id = {r["id"]: r for r in s.repos_for_project(pid, repo_type="app")}
        assert by_id[repo_a]["pr_count"] == 3
        assert by_id[repo_b]["pr_count"] == 2

    def test_filtered_and_unfiltered_lists_agree(self):
        pid, repo_a, repo_b, s = _scenario()
        unfiltered = {r["id"]: r["pr_count"] for r in s.list_repos(pid)}
        filtered = {r["id"]: r["pr_count"]
                    for r in s.repos_for_project(pid, repo_type="app")}
        assert filtered == unfiltered == {repo_a: 3, repo_b: 2}


class TestDashboardSteadyStateInvariant:
    def test_rollup_prs_equals_repo_list_sum(self):
        """Characterization: in steady state the dashboard rollup row and the
        summed repo list must agree — they read the same collection."""
        pid, _a, _b, s = _scenario()
        dash = s.dashboard()
        rollup = {p["id"]: p["prs"] for p in dash["projects"]}
        repo_sum = sum(r["pr_count"] for r in s.list_repos(pid))
        assert rollup[pid] == repo_sum == 5
        assert dash["counts"]["pull_requests"] == 5


class TestDashboardSyncLabel:
    def test_dashboard_route_reports_sync_state(self, monkeypatch):
        import api.routes.system as system

        payload = {"counts": {"pull_requests": 5}, "projects": []}
        monkeypatch.setattr(system, "_current_user", lambda req: {"id": "u1"})
        monkeypatch.setattr(system, "_allowed_project_ids", lambda user: None)

        class _FakeStore:
            def dashboard(self, project_ids=None):
                return dict(payload)

        monkeypatch.setattr(system, "store", _FakeStore())
        monkeypatch.setattr(system, "SYNC",
                            {"running": True, "last": None, "ingested": 7,
                             "mapped": 5, "errors": []})
        out = system.dashboard(request=None)
        assert out["sync"] == {"running": True, "ingested": 7}
        assert out["counts"]["pull_requests"] == 5
