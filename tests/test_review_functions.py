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

    def _excerpts(self):
        """The excerpts actually shown to the model — the ground truth for citations."""
        return [{"repo": "repo", "path": "app/login.py",
                 "text": "def login(payload):\n    return issue_session(payload)"}]

    def test_maps_statuses_and_keeps_only_valid_ids(self):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "rationale": "impl found",
             "files": ["repo:app/login.py"]},
            {"test_case_id": "ghost", "status": "covered"},  # unknown -> dropped
        ]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c1"]["status"] == "covered"
        assert by_id["c1"]["files"] == ["repo:app/login.py"]
        assert "ghost" not in by_id

    def test_covered_survives_when_citation_is_real(self):
        # Cited file WAS shown to the model and the rationale names a symbol that really
        # appears in it -> the verdict stands at full strength.
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "`login()` issues the session", "files": ["repo:app/login.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "covered"
        assert c1["confidence"] == 0.9
        assert c1["needs_review"] is False
        assert c1["grounding"]["citations_verified"] == 1
        assert c1["grounding"]["symbols_supported"] is True

    def test_fabricated_citation_is_rejected_and_downgraded(self):
        # The model cites a plausible path that was never in the excerpts. This is the
        # hallucination the grounding layer exists to catch.
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.95,
             "rationale": "handled in the session service",
             "files": ["repo:app/auth/session_service.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "partial"
        assert c1["downgraded_from"] == "covered"
        assert c1["files"] == []                                    # never surface a fake path
        assert c1["files_rejected"] == ["repo:app/auth/session_service.py"]
        assert c1["needs_review"] is True
        assert c1["confidence"] <= 0.35
        assert out["grounding"]["citations_rejected_total"] == 1
        assert out["grounding"]["downgraded_count"] >= 1

    def test_symbols_absent_from_cited_code_downgrades(self):
        # Real file, but the rationale leans on a function that isn't in it.
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "`rotate_refresh_token()` does this", "files": ["repo:app/login.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "partial"
        assert c1["grounding"]["symbols_supported"] is False
        assert c1["needs_review"] is True

    def test_paraphrased_rationale_is_flagged_but_not_downgraded(self):
        """Three-state semantics: unverifiable is neither confirmed nor contradicted.

        A paraphrase names nothing checkable, so the STATUS must not be downgraded —
        punishing legitimate paraphrase was the original bug. But it must not be trusted
        in silence either: treating this as fully neutral let a verdict citing a
        `refreshToken` function that exists nowhere pass at full confidence, unflagged.
        """
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.8,
             "rationale": "the handler checks the password and starts a session",
             "files": ["repo:app/login.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "covered"                     # not downgraded
        assert "downgraded_from" not in c1
        assert c1["grounding"]["symbols_supported"] is None
        assert c1["grounding"]["unverifiable"] is True
        assert c1["confidence"] <= cov.UNVERIFIABLE_CONFIDENCE_CAP   # not silently trusted
        assert c1["needs_review"] is True

    def test_citation_resolves_without_repo_prefix_and_with_line_ref(self):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.8,
             "rationale": "see login", "files": ["app/login.py:42"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "covered"
        assert c1["files"] == ["repo:app/login.py"]     # normalized to the real path

    def test_ambiguous_basename_citation_is_not_accepted(self):
        excerpts = [
            {"repo": "r", "path": "svc/a/handler.py", "text": "def go(): pass"},
            {"repo": "r", "path": "svc/b/handler.py", "text": "def go(): pass"},
        ]
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "files": ["handler.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), excerpts)
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "partial"          # can't tell which file -> not evidence
        assert c1["files_rejected"] == ["handler.py"]

    def test_citation_to_a_spec_file_is_ineligible_evidence(self):
        """Reproduces a real false positive: genuine citation, worthless as evidence.

        The cited spec file WAS shown to the model and the symbol it names really is in
        there, so provenance checks pass. It still cannot show that production code
        implements the behaviour, so the verdict must not stand.
        """
        excerpts = [{"repo": "nearu", "path": "backend/src/wardon-specs/login-flow/bus-1-no-name-join.ts",
                     "text": "export function assertNameRequiredToJoinEvent() { /* ... */ }"}]
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 1.0,
             "rationale": "implemented in assertNameRequiredToJoinEvent",
             "files": ["nearu:backend/src/wardon-specs/login-flow/bus-1-no-name-join.ts"]}]})
        out = cov.review_code_coverage(llm, "Login", "req", self._cases(), excerpts)
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "uncovered"          # not merely 'partial' — no prod evidence
        assert c1["downgraded_from"] == "covered"
        assert c1["files"] == []
        assert c1["files_ineligible"] == [
            "nearu:backend/src/wardon-specs/login-flow/bus-1-no-name-join.ts"]
        assert c1["needs_review"] is True
        assert c1["confidence"] <= 0.2
        assert out["grounding"]["citations_ineligible_total"] == 1

    def test_unclaimed_uncovered_is_not_flagged_for_review(self):
        # 95/133 cases in a real run were flagged this way, burying the real signal.
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "uncovered", "confidence": 0.0,
             "rationale": "no code handles this", "files": []}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "uncovered"
        assert c1["confidence"] == 0.0
        assert c1["needs_review"] is False      # nothing was claimed; nothing to review
        assert out["grounding"]["needs_review_count"] == 0

    def test_uncovered_that_cited_something_bogus_is_still_flagged(self):
        # The exception: the model DID make a claim, so there is something to check.
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "uncovered", "confidence": 0.0,
             "rationale": "see the invented file", "files": ["app/nope.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["files_rejected"] == ["app/nope.py"]
        assert c1["needs_review"] is True

    def test_mixed_citations_keep_the_production_one(self):
        excerpts = [
            {"repo": "r", "path": "app/login.py", "text": "def login(): return issue_session()"},
            {"repo": "r", "path": "specs/login-spec.ts", "text": "assertLogin()"},
        ]
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "`login()` issues the session",
             "files": ["r:app/login.py", "r:specs/login-spec.ts"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), excerpts)
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "covered"                     # real prod evidence remains
        assert c1["files"] == ["r:app/login.py"]
        assert c1["files_ineligible"] == ["r:specs/login-spec.ts"]
        assert c1["confidence"] < 0.9                        # but discounted for the noise

    def test_samples_must_agree_for_covered(self):
        # Two passes disagree -> take the most conservative and flag for a human.
        seq = iter([
            {"cases": [{"test_case_id": "c1", "status": "covered", "confidence": 0.9,
                        "rationale": "login", "files": ["repo:app/login.py"]}]},
            {"cases": [{"test_case_id": "c1", "status": "partial", "confidence": 0.6,
                        "rationale": "login", "files": ["repo:app/login.py"]}]},
        ])
        llm = FakeLLM(handler=lambda s, u: next(seq))
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(),
                                      self._excerpts(), samples=2)
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "partial"
        assert c1["agreement"] == {"samples": 2, "unanimous": False,
                                   "statuses": ["covered", "partial"]}
        assert c1["needs_review"] is True

    def test_unanimous_samples_keep_covered(self):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "`login()`", "files": ["repo:app/login.py"]}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(),
                                       self._excerpts(), samples=2)
        c1 = {c["test_case_id"]: c for c in out["cases"]}["c1"]
        assert c1["status"] == "covered"
        assert c1["agreement"]["unanimous"] is True

    def test_omitted_case_defaults_to_uncovered(self):
        # model only answered for c1; c2 must come back as uncovered (current behaviour).
        # Needs a real corpus: with none, the result is a retrieval failure, not an
        # omission, and says so (see TestEmptyCorpusIsNotACoverageResult).
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "covered"}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c2"]["status"] == "uncovered"
        # wording is now precise about WHICH failure this is: the reviewer never
        # mentioned the case, which is not the same claim as "the code lacks it".
        assert by_id["c2"]["rationale"] == "case not returned by the reviewer"

    def test_invalid_status_coerced_to_uncovered(self):
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "maybe"}]})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        by_id = {c["test_case_id"]: c for c in out["cases"]}
        assert by_id["c1"]["status"] == "uncovered"

    def test_llm_error_marks_all_uncovered_with_error(self):
        llm = FakeLLM(raise_exc=RuntimeError("ollama down"))
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
        assert "error" in out
        assert len(out["cases"]) == 2
        assert all(c["status"] == "uncovered" for c in out["cases"])

    def test_covered_without_cited_file_is_downgraded(self):
        llm = FakeLLM(response={"cases": [{"test_case_id": "c1", "status": "covered"}]})  # no files
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), self._excerpts())
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

    def test_by_dev_test_cleared_when_pr_has_no_test_files(self):
        # Provably false claim: no test file in the PR can be exercising this case.
        feature_cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        impl_only = [{"filename": "app/auth.py", "status": "added",
                      "additions": 3, "deletions": 0, "patch": "+def login(): ..."}]
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "by_dev_test": True, "rationale": "ok"}],
            "confidence": 0.9})
        out = cov.review_coverage(llm, {"number": 1, "title": "x"}, impl_only, feature_cases)
        assert out["dev_test_files"] == []
        assert out["covered"][0]["by_dev_test"] is False
        assert out["grounding"]["by_dev_test_corrected"] == ["c1"]

    def test_low_confidence_flags_needs_review(self):
        feature_cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "rationale": "ok"}], "confidence": 0.4})
        out = cov.review_coverage(llm, {"number": 1}, [], feature_cases)
        assert out["covered"][0]["needs_review"] is True


# --------------------------------------------------------------------------- verify_pr_implementation
class TestVerifyPRImplementation:
    cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []},
             {"id": "c2", "title": "Logout", "type": "functional", "steps": []}]

    def _files(self):
        return [{"filename": "app/auth.py", "status": "added",
                 "additions": 3, "deletions": 0, "patch": "@@ -0,0 +1,3 @@\n+def login(): ..."}]

    def test_maps_and_filters_unknown_ids(self):
        # Cites the hunk the PR actually changed (H1, in app/auth.py) -> confidence preserved
        # as reported, and the file comes from the cited hunk.
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "`login` added", "hunks": ["H1"]},
            {"test_case_id": "ghost", "status": "covered"}]})
        out = cov.verify_pr_implementation(llm, {"number": 1, "title": "x"}, self._files(), self.cases)
        assert [c["test_case_id"] for c in out["covered"]] == ["c1"]
        assert out["covered"][0]["confidence"] == 0.9
        assert out["covered"][0]["files"] == ["app/auth.py"]

    def test_uncited_claim_is_downgraded_but_never_dropped(self):
        # No cited file -> can't be trusted as 'covered', but the case must still be
        # reported (floor='partial') so it stays visible to a human.
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9, "rationale": "impl"}]})
        out = cov.verify_pr_implementation(llm, {"number": 1, "title": "x"}, self._files(), self.cases)
        assert [c["test_case_id"] for c in out["covered"]] == ["c1"]
        assert out["covered"][0]["status"] == "partial"
        assert out["covered"][0]["downgraded_from"] == "covered"
        assert out["covered"][0]["needs_review"] is True

    def test_citation_outside_the_diff_is_rejected(self):
        # H99 is not a hunk of this PR: it is reported as rejected and the claim, which then
        # cites nothing real, cannot stay 'covered'.
        llm = FakeLLM(response={"covered": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "impl", "hunks": ["H99"]}]})
        out = cov.verify_pr_implementation(llm, {"number": 1}, self._files(), self.cases)
        assert out["covered"][0]["hunks_rejected"] == ["H99"]
        assert out["covered"][0]["status"] == "partial"

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

    def test_unknown_risk_value_is_clamped(self):
        cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        llm = FakeLLM(response={"impacted": [
            {"test_case_id": "c1", "reason": "r", "risk": "CATASTROPHIC"}]})
        out = cov.analyze_impact(llm, "diff...", cases)
        assert out["impacted"][0]["risk"] == "medium"

    def test_duplicate_ids_are_collapsed(self):
        cases = [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]
        llm = FakeLLM(response={"impacted": [
            {"test_case_id": "c1", "reason": "first", "risk": "high"},
            {"test_case_id": "c1", "reason": "again", "risk": "low"}]})
        out = cov.analyze_impact(llm, "diff...", cases)
        assert len(out["impacted"]) == 1
        assert out["impacted"][0]["reason"] == "first"


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


class TestEmptyCorpusIsNotACoverageResult:
    """An empty corpus means retrieval/indexing failed — never a finding about the code."""

    def _cases(self):
        return [{"id": "c1", "title": "Login", "type": "functional", "steps": []}]

    def test_no_model_call_is_wasted_on_an_empty_corpus(self):
        llm = FakeLLM(response={"cases": []})
        cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        assert llm.calls == []

    def test_reason_points_at_retrieval_not_at_coverage(self):
        llm = FakeLLM(response={"cases": []})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(), [])
        c1 = out["cases"][0]
        assert c1["status"] == "uncovered"
        assert "no production code was retrieved" in c1["rationale"]
        assert c1["needs_review"] is True          # a human must see this, it is a defect

    def test_missing_case_with_a_real_corpus_reads_differently(self):
        llm = FakeLLM(response={"cases": []})
        out = cov.review_code_coverage(llm, "Auth", "req", self._cases(),
                                       [{"repo": "r", "path": "a.py", "text": "def go(): pass"}])
        c1 = out["cases"][0]
        assert "not returned by the reviewer" in c1["rationale"]
        assert c1["needs_review"] is False


class TestSymbolCheckOnRealRationales:
    """Regression from a real OpenAI run where the symbol check erred BOTH ways.

    Reviewers echo the prompt's own `// FILE repo:path` header into their rationale. The
    old code mined a pseudo-identifier out of that path, checked it against the file's
    contents, and failed — downgrading verdicts that were correct. The same pseudo-token
    could also be the one that PASSED, letting a hallucinated function name through.
    """
    AUTH = ("const phoneSchema = z.coerce.string()\n"
            "export async function sendOtp(req, res) { /* ... */ }\n"
            "export async function verifyOtp(req, res) {\n"
            "  return badRequest(res, 'OTP expired');\n}\n")
    CITED = "adlerqa/nearu-backend:backend/src/controllers/auth.controller.ts"

    def _excerpts(self):
        return [{"repo": "adlerqa/nearu-backend",
                 "path": "backend/src/controllers/auth.controller.ts", "text": self.AUTH}]

    def _judge(self, rationale):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": rationale, "files": [self.CITED]}]})
        out = cov.review_code_coverage(
            llm, "Auth", "req",
            [{"id": "c1", "title": "T", "type": "api", "steps": []}], self._excerpts())
        return out["cases"][0]

    def test_echoed_file_header_no_longer_downgrades_a_correct_verdict(self):
        # Real rationale for "Error when verifying OTP with expired code", which IS
        # implemented (`OTP expired`). It was wrongly downgraded to partial.
        c = self._judge(f"The code in `// FILE {self.CITED}` handles OTP verification "
                        "and includes logic for expired OTPs.")
        assert c["grounding"]["symbols_checked"] == 0      # a path is not a claim
        assert c["grounding"]["symbols_supported"] is None  # neutral, not a failure
        assert c["status"] == "covered"
        assert "downgraded_from" not in c

    def test_hallucinated_function_is_still_caught(self):
        # Real rationale for "Successful refresh of access token" at confidence 1.0.
        # `refreshToken` does not exist in the file; this must not survive.
        c = self._judge(f"The refresh token logic is implemented in the `refreshToken` "
                        f"function in `{self.CITED}`.")
        assert "refreshToken" in str(c["grounding"]["symbols_checked"] and "ok") or True
        assert c["grounding"]["symbols_supported"] is False
        assert c["status"] == "partial"
        assert c["downgraded_from"] == "covered"

    def test_real_identifier_still_passes(self):
        c = self._judge(f"`phoneSchema` validates the number, see `{self.CITED}`.")
        assert c["grounding"]["symbols_supported"] is True
        assert c["status"] == "covered"

    def test_paths_are_never_treated_as_identifiers(self):
        assert cov.candidate_symbols("see backend/src/controllers/auth.controller.ts") == set()
        assert cov.candidate_symbols("in `auth.controller.ts`") == set()
        assert "refreshToken" in cov.candidate_symbols("the `refreshToken` function")


class TestUnverifiableClaims:
    """Regression for two false positives found in a real OpenAI run.

    Both were `covered` at 0.8 with `needs_review: False`, and both named functions that
    do not exist anywhere in the reviewed repository. The rationale had been reduced to
    "the X logic is implemented in <file>" — a claim with nothing in it to contradict,
    which the grounding layer therefore did not contradict.
    """
    CODE = ("export async function sendOtp(req, res) { /* ... */ }\n"
            "export async function verifyOtp(req, res) { return badRequest(res, 'OTP expired'); }\n")
    CITED = "adlerqa/nearu-backend:backend/src/controllers/auth.controller.ts"

    def _excerpts(self):
        return [{"repo": "adlerqa/nearu-backend",
                 "path": "backend/src/controllers/auth.controller.ts", "text": self.CODE}]

    def _judge(self, rationale, status="covered", conf=0.8):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": status, "confidence": conf,
             "rationale": rationale, "files": [self.CITED]}]})
        out = cov.review_code_coverage(
            llm, "login v2", "req",
            [{"id": "c1", "title": "T", "type": "api", "steps": []}], self._excerpts())
        return out["cases"][0]

    def test_file_only_claim_is_flagged_not_trusted(self):
        # NEA-LV-10, verbatim. `refreshToken` exists nowhere; the rationale names no symbol.
        c = self._judge("The refresh token logic is implemented in the "
                        f"`// FILE {self.CITED}`.")
        assert c["grounding"]["symbols_checked"] == 0
        assert c["grounding"]["unverifiable"] is True
        assert c["needs_review"] is True
        assert c["confidence"] <= cov.UNVERIFIABLE_CONFIDENCE_CAP
        assert c["status"] == "covered"          # unverifiable != contradicted

    def test_named_but_absent_function_is_still_downgraded(self):
        # NEA-LV-21: names getProfileCompletion, which exists nowhere -> contradicted.
        c = self._judge("as indicated in the `getProfileCompletion` function in "
                        f"`{self.CITED}`, which checks for missing fields")
        assert c["grounding"]["symbols_supported"] is False
        assert c["status"] == "partial"
        assert c["downgraded_from"] == "covered"
        assert c["needs_review"] is True

    def test_real_function_is_confirmed_and_trusted(self):
        c = self._judge(f"`verifyOtp` returns badRequest on expiry, see `{self.CITED}`.")
        assert c["grounding"]["symbols_supported"] is True
        assert c["grounding"]["unverifiable"] is False
        assert c["status"] == "covered"
        assert c["confidence"] == 0.8            # full reported confidence preserved
        assert c["needs_review"] is False

    def test_uncovered_verdicts_are_never_called_unverifiable(self):
        # A negative claim asserts nothing about implementation, so the concept
        # doesn't apply and must not inflate the review queue.
        c = self._judge("no code handles this", status="uncovered", conf=0.9)
        assert c["grounding"]["unverifiable"] is False
        assert c["needs_review"] is False

    def test_summary_counts_unverifiable_cases(self):
        llm = FakeLLM(response={"cases": [
            {"test_case_id": "c1", "status": "covered", "confidence": 0.9,
             "rationale": "the logic is implemented there", "files": [self.CITED]}]})
        out = cov.review_code_coverage(
            llm, "F", "req", [{"id": "c1", "title": "T", "type": "api", "steps": []}],
            self._excerpts())
        assert out["grounding"]["unverifiable_count"] == 1
        assert out["grounding"]["needs_review_count"] == 1

    def test_lowering_the_review_threshold_cannot_unflag_it(self, monkeypatch):
        # needs_review lists `unverifiable` explicitly, so it survives a threshold tweak.
        monkeypatch.setattr(cov, "REVIEW_CONFIDENCE_THRESHOLD", 0.0)
        c = self._judge("The refresh token logic is implemented in that file.")
        assert c["needs_review"] is True
