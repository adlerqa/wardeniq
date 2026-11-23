"""Gap Analysis run surfaces must count only confirmed coverage (#291).

#288 fixed the feature headline, the per-PR rows and the dashboard. The PR "run" surfaces
still counted a "partial" entry (PR touches relevant code, implementation not confirmed) as
covered: the run card's tests_covered / gaps_found, the run detail counts, and the
newly_covered / no_longer_covered comparison. A PR that was only matched loosely read 3/3,
100%. These tests pin the rule "only a confirmed `covered` verdict counts; a missing status
is legacy full coverage" in the helper, in ingest_pr, in diff_runs and in the routes that
serve runs saved before the fix.
"""
import types

import auth
import main
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import coverage as cov
from workers import code_coverage_worker as worker

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)

C1, C2, C3 = (str(ObjectId()) for _ in range(3))


def entry(cid, status="covered", **extra):
    e = {"test_case_id": cid, "status": status, "confidence": 0.35 if status == "partial" else 0.9,
         "rationale": "r", "by_dev_test": False}
    e.update(extra)
    return e


# ------------------------------------------------------------------ the shared rule
class TestIsConfirmed:
    def test_covered_is_confirmed(self):
        assert cov.is_confirmed({"status": "covered"}) is True

    def test_partial_is_not_confirmed(self):
        assert cov.is_confirmed({"status": "partial"}) is False

    def test_an_entry_saved_before_status_existed_is_full_coverage(self):
        assert cov.is_confirmed({"test_case_id": C1}) is True


class TestCoverageCounts:
    def test_all_partial_is_zero_covered(self):
        got = cov.coverage_counts([entry(C1, "partial"), entry(C2, "partial"), entry(C3, "partial")], 3)
        assert got == {"tests_covered": 0, "tests_partial": 3, "gaps_found": 3}

    def test_one_covered_two_partial(self):
        got = cov.coverage_counts([entry(C1), entry(C2, "partial"), entry(C3, "partial")], 3)
        assert got == {"tests_covered": 1, "tests_partial": 2, "gaps_found": 2}

    def test_all_confirmed_has_no_gaps(self):
        assert cov.coverage_counts([entry(C1), entry(C2)], 2) == \
            {"tests_covered": 2, "tests_partial": 0, "gaps_found": 0}

    def test_legacy_entries_without_status_count_as_covered(self):
        got = cov.coverage_counts([{"test_case_id": C1}, {"test_case_id": C2}], 3)
        assert got == {"tests_covered": 2, "tests_partial": 0, "gaps_found": 1}

    def test_a_case_that_is_both_confirmed_and_partial_is_confirmed_only(self):
        got = cov.coverage_counts([entry(C1), entry(C1, "partial")], 1)
        assert got == {"tests_covered": 1, "tests_partial": 0, "gaps_found": 0}

    def test_a_case_listed_twice_counts_once(self):
        assert cov.coverage_counts([entry(C1), entry(C1)], 2)["tests_covered"] == 1

    def test_entries_without_a_case_id_are_ignored(self):
        assert cov.coverage_counts([{"status": "covered"}], 1)["tests_covered"] == 0

    def test_nothing_stored(self):
        assert cov.coverage_counts([], 4) == {"tests_covered": 0, "tests_partial": 0, "gaps_found": 4}

    def test_gaps_never_go_negative(self):
        assert cov.coverage_counts([entry(C1), entry(C2)], 1)["gaps_found"] == 0


# ------------------------------------------------------------------ diff_runs
def prev_run(*entries, rid="r-prev"):
    return {"id": rid, "pr_number": 6, "result": {"covered": list(entries)}}


class TestDiffRuns:
    def test_first_run_with_only_partial_matches_has_nothing_newly_covered(self):
        d = cov.diff_runs(None, [entry(C1, "partial"), entry(C2, "partial")])
        assert d["newly_covered"] == [] and d["no_longer_covered"] == []

    def test_first_run_lists_only_confirmed_cases(self):
        d = cov.diff_runs(None, [entry(C1), entry(C2, "partial")])
        assert d["newly_covered"] == [C1]

    def test_partial_only_prior_run_is_not_reported_as_lost(self):
        d = cov.diff_runs(prev_run(entry(C1, "partial"), entry(C2, "partial")), [])
        assert d["no_longer_covered"] == [] and d["newly_covered"] == []

    def test_a_partial_match_that_becomes_confirmed_is_newly_covered(self):
        d = cov.diff_runs(prev_run(entry(C1, "partial")), [entry(C1)])
        assert d["newly_covered"] == [C1]

    def test_a_confirmed_case_that_drops_to_partial_is_no_longer_covered(self):
        d = cov.diff_runs(prev_run(entry(C1)), [entry(C1, "partial")])
        assert d["no_longer_covered"] == [C1] and d["newly_covered"] == []

    def test_a_confirmed_case_that_disappears_is_no_longer_covered(self):
        assert cov.diff_runs(prev_run(entry(C1)), [])["no_longer_covered"] == [C1]

    def test_unchanged_confirmed_coverage_is_no_change(self):
        d = cov.diff_runs(prev_run(entry(C1)), [entry(C1)])
        assert d["newly_covered"] == [] and d["no_longer_covered"] == []

    def test_legacy_entries_without_status_take_part_as_covered(self):
        d = cov.diff_runs(prev_run({"test_case_id": C1}), [entry(C1), entry(C2)])
        assert d["newly_covered"] == [C2]

    def test_prior_run_metadata_is_still_reported(self):
        d = cov.diff_runs({**prev_run(entry(C1)), "feature_version": 2}, [entry(C1)])
        assert d["prev_run_id"] == "r-prev" and d["prev_pr_number"] == 6 and d["prev_feature_version"] == 2


# ------------------------------------------------------------------ ingest_pr end to end
class IngestStore:
    """The store surface ingest_pr touches. The PR is mapped by its [TAG] to one feature."""

    def __init__(self, case_ids, prev=None):
        self.case_ids, self.prev = list(case_ids), prev
        self.run_updates = []
        self.prs = types.SimpleNamespace(find_one=lambda *a, **k: None)

    def feature_by_epic(self, project_id, key):
        return None

    def features_with_match_key(self, project_id):
        return [("f1", "RESETS")]

    def semantic_feature_scores(self, *a, **k):
        return []

    def upsert_pr(self, doc):
        return "0123456789abcdef01234567"

    def set_pr_mapping(self, *a):
        pass

    def set_pr_suggestion(self, *a):
        pass

    def get_feature(self, fid):
        return {"id": fid, "version": 1}

    def create_code_coverage_run(self, doc):
        return "run-1"

    def update_code_coverage_run(self, run_id, **kw):
        self.run_updates.append(kw)

    def feature_test_case_ids(self, fid):
        return list(self.case_ids)

    def cases_brief(self, ids):
        return [{"id": i, "title": f"case {i}"} for i in ids]

    def previous_done_run_for_feature(self, fid, exclude_id=None):
        return self.prev

    def save_coverage_snapshot(self, *a, **k):
        return None


REPO = {"id": "r1", "project_id": "p1", "owner": "acme", "name": "app", "full_name": "acme/app"}
GH_PR = {"number": 7, "title": "[RESETS] reset password", "body": "", "html_url": "https://example.test/pr/7",
         "head": {"sha": "abc", "ref": "feat/x"}, "user": {"login": "dev"}, "state": "open",
         "_files": [{"filename": "app/auth/reset.py", "status": "modified", "additions": 3, "deletions": 1}]}


@pytest.fixture
def ingest(monkeypatch):
    def run(store, covered):
        monkeypatch.setattr(worker, "store", store)
        monkeypatch.setattr(worker, "state", types.SimpleNamespace(embedder=types.SimpleNamespace(
            embed=lambda *a, **k: [0.0])))
        monkeypatch.setattr(worker, "jira_client", lambda: None)
        # Stub only the verdict step; the counting, diff_runs and unmapped-change code run for real.
        monkeypatch.setattr(worker, "_pr_coverage",
                            lambda *a, **k: {"covered": covered, "dev_test_files": [],
                                             "confidence": 0.35, "notice": ""})
        worker.ingest_pr(REPO, dict(GH_PR))
        done = [u for u in store.run_updates if u.get("status") == "done" and "tests_total" in u]
        assert done, store.run_updates
        return done[-1]
    return run


class TestIngestPr:
    def test_three_partial_matches_do_not_read_three_of_three(self, ingest):
        store = IngestStore([C1, C2, C3])
        u = ingest(store, [entry(C1, "partial"), entry(C2, "partial"), entry(C3, "partial")])
        assert (u["tests_total"], u["tests_covered"], u["tests_partial"], u["gaps_found"]) == (3, 0, 3, 3)
        assert u["result"]["comparison"]["newly_covered"] == []

    def test_one_covered_and_two_partial_reads_one_of_three(self, ingest):
        u = ingest(IngestStore([C1, C2, C3]), [entry(C1), entry(C2, "partial"), entry(C3, "partial")])
        assert (u["tests_covered"], u["tests_partial"], u["gaps_found"]) == (1, 2, 2)
        assert u["result"]["comparison"]["newly_covered"] == [C1]

    def test_all_confirmed_reads_three_of_three(self, ingest):
        u = ingest(IngestStore([C1, C2, C3]), [entry(C1), entry(C2), entry(C3)])
        assert (u["tests_covered"], u["tests_partial"], u["gaps_found"]) == (3, 0, 0)

    def test_losing_only_partial_matches_is_not_reported_as_lost_coverage(self, ingest):
        prev = prev_run(entry(C1, "partial"), entry(C2, "partial"), entry(C3, "partial"))
        u = ingest(IngestStore([C1, C2, C3], prev=prev), [])
        assert u["result"]["comparison"]["no_longer_covered"] == []

    def test_partial_entries_are_still_stored_so_the_screen_can_show_them(self, ingest):
        u = ingest(IngestStore([C1]), [entry(C1, "partial")])
        assert [(c["test_case_id"], c["status"]) for c in u["result"]["covered"]] == [(C1, "partial")]


# ------------------------------------------------------------------ the routes
SESSION = auth.SESSION_COOKIE
ADMIN = {"id": "admin1", "email": "a@example.com", "role": "admin", "active": True,
         "session_version": 0, "all_projects": True}


class _Cases:
    def find(self, *a, **k):
        return []


def _stored_run(rid="r-new", covered=None, comparison=None, status="done", **extra):
    covered = [entry(C1, "partial"), entry(C2, "partial"), entry(C3, "partial")] if covered is None else covered
    run = {"id": rid, "feature_id": "f1", "status": status, "pr_number": 7, "repo_id": "r1",
           "tests_total": 3, "tests_covered": 3, "gaps_found": 0,      # what the old code stored
           "result": {"covered": covered,
                      "comparison": comparison if comparison is not None else
                      {"prev_run_id": None, "newly_covered": [C1, C2, C3], "no_longer_covered": []}}}
    run.update(extra)
    return run


@pytest.fixture
def routes(monkeypatch):
    runs = {}
    monkeypatch.setattr(main.store, "get_user", lambda uid: ADMIN)
    monkeypatch.setattr(main.store, "get_code_coverage_run", lambda rid: runs.get(rid) and dict(runs[rid]))
    monkeypatch.setattr(main.store, "list_code_coverage_runs",
                        lambda feature_id=None, project_id=None, limit=50: [dict(r) for r in runs.values()])
    monkeypatch.setattr(main.store, "get_feature", lambda fid: {"id": fid, "name": "F", "updated_at": 0})
    monkeypatch.setattr(main.store, "excluded_pr_run_keys", lambda fid: set())
    monkeypatch.setattr(main.store, "feature_test_case_ids", lambda fid: [])
    monkeypatch.setattr(main.store, "resolve_steps", lambda ids: [])
    monkeypatch.setattr(main.store, "cases", _Cases())
    return runs


def _get(path):
    return client.get(path, cookies={SESSION: auth.sign_session("admin1", 0)})


class TestRunListRoute:
    def test_a_run_saved_with_the_old_inflated_count_is_corrected(self, routes):
        routes["r-new"] = _stored_run()
        run = _get("/api/features/f1/code-coverage/runs").json()["runs"][0]
        assert (run["tests_covered"], run["tests_partial"], run["gaps_found"]) == (0, 3, 3)

    def test_a_confirmed_run_is_unchanged(self, routes):
        routes["r-new"] = _stored_run(covered=[entry(C1), entry(C2), entry(C3)], gaps_found=0)
        run = _get("/api/features/f1/code-coverage/runs").json()["runs"][0]
        assert (run["tests_covered"], run["tests_partial"], run["gaps_found"]) == (3, 0, 0)

    def test_a_run_with_no_covered_list_keeps_what_was_stored(self, routes):
        routes["r-x"] = {"id": "r-x", "feature_id": "f1", "status": "done", "tests_total": 0,
                         "tests_covered": 0, "result": {"no_cases": True}}
        run = _get("/api/features/f1/code-coverage/runs").json()["runs"][0]
        assert run["tests_covered"] == 0 and "tests_partial" not in run

    def test_a_run_that_is_still_running_is_left_alone(self, routes):
        routes["r-x"] = _stored_run(rid="r-x", status="running", tests_covered=0)
        run = _get("/api/features/f1/code-coverage/runs").json()["runs"][0]
        assert run["tests_covered"] == 0 and "tests_partial" not in run


class TestRunDetailRoute:
    def test_counts_are_corrected_and_the_partial_status_is_kept_for_the_screen(self, routes):
        routes["r-new"] = _stored_run()
        r = _get("/api/code-coverage/runs/r-new").json()
        assert (r["tests_covered"], r["tests_partial"], r["gaps_found"]) == (0, 3, 3)
        assert {c["status"] for c in r["result"]["covered"]} == {"partial"}

    def test_an_old_first_run_comparison_no_longer_lists_partial_matches(self, routes):
        routes["r-new"] = _stored_run()          # stored comparison has all three as newly covered
        cmp = _get("/api/code-coverage/runs/r-new").json()["result"]["comparison"]
        assert cmp["newly_covered"] == [] and cmp["newly_covered_detail"] == []

    def test_the_comparison_is_recomputed_against_the_earlier_run_when_it_still_exists(self, routes):
        routes["r-prev"] = _stored_run(rid="r-prev", covered=[entry(C1, "partial"), entry(C2, "partial")])
        routes["r-new"] = _stored_run(
            covered=[], comparison={"prev_run_id": "r-prev", "newly_covered": [],
                                    "no_longer_covered": [C1, C2]})
        cmp = _get("/api/code-coverage/runs/r-new").json()["result"]["comparison"]
        assert cmp["no_longer_covered"] == [] and cmp["prev_run_id"] == "r-prev"

    def test_a_real_loss_of_confirmed_coverage_still_shows_as_lost(self, routes):
        routes["r-prev"] = _stored_run(rid="r-prev", covered=[entry(C1), entry(C2, "partial")])
        routes["r-new"] = _stored_run(
            covered=[], comparison={"prev_run_id": "r-prev", "newly_covered": [],
                                    "no_longer_covered": [C1, C2]})
        cmp = _get("/api/code-coverage/runs/r-new").json()["result"]["comparison"]
        assert cmp["no_longer_covered"] == [C1]

    def test_a_confirmed_gain_is_kept_when_the_earlier_run_is_gone(self, routes):
        routes["r-new"] = _stored_run(
            covered=[entry(C1), entry(C2, "partial")],
            comparison={"prev_run_id": "deleted", "newly_covered": [C1, C2], "no_longer_covered": [C3]})
        cmp = _get("/api/code-coverage/runs/r-new").json()["result"]["comparison"]
        assert cmp["newly_covered"] == [C1]
        assert cmp["no_longer_covered"] == [C3]      # cannot be re-checked without the earlier run

    def test_a_run_with_no_comparison_is_served_unchanged(self, routes):
        routes["r-x"] = {"id": "r-x", "feature_id": "f1", "status": "done", "tests_total": 0,
                         "tests_covered": 0, "result": {"unmatched": True}}
        r = _get("/api/code-coverage/runs/r-x").json()
        assert r["result"] == {"unmatched": True}
