"""Characterization tests for the LLM-review helpers (current behaviour).

These pin down how `review_code_coverage`, `review_coverage`, `analyze_impact` and
`diff_versions` shape and validate LLM output today — including the important edge cases
the Phase 1+ rework must preserve or deliberately change:
  * omitted cases default to `uncovered` (D9 in plan.md)
  * unknown test_case_ids from the model are dropped
  * an LLM exception degrades gracefully instead of crashing the worker
"""
import coverage as cov
from conftest import FakeLLM


# --------------------------------------------------------------------------- review_code_coverage (Mind Map)
class TestReviewCodeCoverage:
    def _cases(self):
        return [
            {"id": "c1", "title": "Login", "type": "functional", "steps": []},
            {"id": "c2", "title": "Logout", "type": "functional", "steps": []},
        ]

    def test_maps_statuses_and_keeps_only_valid_ids(self):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "rationale": "impl found",
             "files": ["repo:app/login.py"]},
            {"test_case_id": "ghost", "status": "covered"},  # unknown -> dropped
        ]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c1"]["status"] == "covered"
        assert by_id["c1"]["files"] == ["repo:app/login.py"]
        assert "ghost" not in by_id

    def test_omitted_case_defaults_to_uncovered(self):
        # model only answered for c1; c2 must come back as uncovered (current behaviour)
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "covered"}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c2"]["status"] == "uncovered"
        assert by_id["c2"]["rationale"] == "not addressed by reviewed code"

    def test_invalid_status_coerced_to_uncovered(self):
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "maybe"}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c1"]["status"] == "uncovered"

    def test_llm_error_marks_all_uncovered_with_error(self):
        llm = FakeLLM(raise_exc=RuntimeError("ollama down"))
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        assert "error" in out
        assert len(out["cases"]) == 2
        assert all(c["status"] == "uncovered" for c in out["cases"])

    def test_covered_without_cited_file_is_downgraded(self):
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "covered"}]})  # no files
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c1"]["status"] == "partial"   # covered with nothing to cite → partial


# --------------------------------------------------------------------------- review_coverage (PR coverage)
class TestReviewCoverage:
    def test_detects_dev_test_files_and_filters_ids(self, sample_pr_files):
        feature_cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "by_dev_test": True, "rationale": "ok"},
            {"test_case_id": "nope", "status": "covered"},
        ], "confidence": 0.8})
        pr = {"number": 1, "title": "Add login"}
        out = cov.review_coverage(llm, pr, sample_pr_files, feature_cases)
        assert "tests/test_login.py" in out["dev_test_files"]
        ids = [c["test_case_id"] for c in out["covered"]]
        assert ids == ["c1"]            # unknown id dropped
        assert out["confidence"] == 0.8

    def test_llm_error_is_graceful(self, sample_pr_files):
        llm = FakeLLM(raise_exc=RuntimeError("boom"))
        out = cov.review_coverage(llm, {"number": 1, "title": "x"}, sample_pr_files, [])
        assert out["covered"] == []
        assert out["confidence"] == 0.0
        assert "error" in out


# --------------------------------------------------------------------------- verify_pr_implementation
class TestVerifyPRImplementation:
    cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []},
             {"id": "c2", "title": "Logout", "type": "functional", "steps": []}]

    def _files(self):
        return [{"filename": "app/auth.py", "status": "added",
                 "additions": 3, "deletions": 0, "patch": "+def login(): ..."}]

    def test_maps_and_filters_unknown_ids(self):
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9, "rationale": "impl"},
            {"test_case_id": "ghost", "status": "covered"}]})
        out = cov.verify_pr_implementation(llm, {"number": 1, "title": "x"}, self._files(), self.cases)
        assert [c["test_case_id"] for c in out["covered"]] == ["c1"]
        assert out["covered"][0]["confidence"] == 0.9

    def test_invalid_status_coerced_to_partial(self):
        # unknown status is now the conservative 'partial', never auto-'covered'
        llm = FakeLLM(response={"covered": [{"test_case_id": "c1", "status": "weird"}]})
        out = cov.verify_pr_implementation(llm, {"number": 1}, self._files(), self.cases)
        assert out["covered"][0]["status"] == "partial"

    def test_llm_error_is_graceful(self):
        llm = FakeLLM(raise_exc=RuntimeError("down"))
        out = cov.verify_pr_implementation(llm, {"number": 1}, self._files(), self.cases)
        assert out["covered"] == [] and "error" in out


# --------------------------------------------------------------------------- analyze_impact
class TestAnalyzeImpact:
    def test_keeps_only_valid_cases(self):
        cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        llm = FakeLLM(response={"impacted": [
            {"test_case_id": "c1", "reason": "auth changed", "risk": "high"},
            {"test_case_id": "x", "reason": "noise", "risk": "low"},
        ]})
        out = cov.analyze_impact(llm, "diff...", cases)
        assert len(out["impacted"]) == 1
        assert out["impacted"][0]["test_case_id"] == "c1"
        assert out["impacted"][0]["risk"] == "high"


# --------------------------------------------------------------------------- diff_versions
class TestDiffVersions:
    def test_unclassified_case_defaults_to_keep(self):
        prev = [{"id": "c1", "title": "A", "type": "functional", "steps": []},
                {"id": "c2", "title": "B", "type": "functional", "steps": []}]
        # model only mentions c1 in retire; c2 should default to keep (safe)
        llm = FakeLLM(response={"keep": [], "retire": [{"id": "c1", "reason": "obsolete"}]})
        out = cov.diff_versions(llm, "old", "new", prev)
        assert "c2" in out["keep"]
        assert [r["id"] for r in out["retire"]] == ["c1"]

    def test_llm_error_keeps_everything(self):
        prev = [{"id": "c1", "title": "A", "type": "functional", "steps": []}]
        llm = FakeLLM(raise_exc=RuntimeError("down"))
        out = cov.diff_versions(llm, "old", "new", prev)
        assert out["keep"] == ["c1"]
        assert out["retire"] == []
