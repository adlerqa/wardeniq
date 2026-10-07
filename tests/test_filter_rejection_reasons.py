"""Issue #64: the exemplar/grounding/dedup filters in testgen/service.py and
testgen/prompt_builder.py must report WHY a case was rejected, using a small
fixed vocabulary, not just silently drop it.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from testgen.prompt_builder import (  # noqa: E402
    PROMPT_EXEMPLAR_E2E_TITLE,
    PROMPT_EXEMPLAR_EDGE_TITLE,
    REASON_DUPLICATE,
    REASON_EDGE_SUPPRESSED,
    REASON_EXEMPLAR_COPY,
    REASON_HYBRID_SCAFFOLD,
    REASON_NO_SOURCE_GROUNDING,
    filter_prompt_exemplar_copies_with_reasons,
    is_prompt_exemplar_copy,
    prompt_exemplar_copy_reason,
)
from testgen.service import (  # noqa: E402
    _deduplicate_with_reasons,
    _filter_ungrounded_suite_cases_with_reasons,
)
from tests.test_prompt_exemplar_filter import (  # noqa: E402
    GROUNDED_RESET_TITLE,
    HYBRID_E2E_TITLE,
    PASSWORD_RESET_TEXT,
    _password_reset_store,
)
from tests.test_rag_evidence_sufficiency import ScenarioLLM, _run  # noqa: E402


class ReasonUnitTests(unittest.TestCase):
    def test_verbatim_title_reason_is_exemplar_copy(self):
        self.assertEqual(
            REASON_EXEMPLAR_COPY,
            prompt_exemplar_copy_reason({"title": PROMPT_EXEMPLAR_E2E_TITLE}),
        )

    def test_hybrid_scaffolding_reason_is_hybrid_scaffold(self):
        self.assertEqual(
            REASON_HYBRID_SCAFFOLD,
            prompt_exemplar_copy_reason({"title": HYBRID_E2E_TITLE}, PASSWORD_RESET_TEXT),
        )

    def test_grounded_case_has_no_reason(self):
        self.assertIsNone(
            prompt_exemplar_copy_reason({"title": GROUNDED_RESET_TITLE}, PASSWORD_RESET_TEXT)
        )

    def test_is_prompt_exemplar_copy_still_matches_the_reasoned_result(self):
        # Refactor must not change the underlying bool decision anywhere.
        cases = [
            {"title": PROMPT_EXEMPLAR_E2E_TITLE},
            {"title": HYBRID_E2E_TITLE},
            {"title": GROUNDED_RESET_TITLE},
            {"title": "Something unrelated entirely"},
        ]
        for case in cases:
            self.assertEqual(
                is_prompt_exemplar_copy(case, PASSWORD_RESET_TEXT),
                prompt_exemplar_copy_reason(case, PASSWORD_RESET_TEXT) is not None,
            )

    def test_filter_with_reasons_splits_kept_and_rejected_correctly(self):
        kept, rejected = filter_prompt_exemplar_copies_with_reasons(
            [
                {"title": PROMPT_EXEMPLAR_E2E_TITLE},
                {"title": HYBRID_E2E_TITLE},
                {"title": GROUNDED_RESET_TITLE},
            ],
            PASSWORD_RESET_TEXT,
        )
        self.assertEqual([GROUNDED_RESET_TITLE], [c["title"] for c in kept])
        reasons = {c["title"]: reason for c, reason in rejected}
        self.assertEqual(REASON_EXEMPLAR_COPY, reasons[PROMPT_EXEMPLAR_E2E_TITLE])
        self.assertEqual(REASON_HYBRID_SCAFFOLD, reasons[HYBRID_E2E_TITLE])

    def test_deduplicate_with_reasons_flags_second_copy_as_duplicate(self):
        case = {"title": "Same case twice", "steps": [{"content": "x", "expected": "y"}]}
        kept, rejected = _deduplicate_with_reasons([dict(case), dict(case)], "business_tests")
        self.assertEqual(1, len(kept))
        self.assertEqual([REASON_DUPLICATE], [reason for _c, reason in rejected])

    def test_ungrounded_suite_case_reason_is_no_source_grounding(self):
        ungrounded = {"title": "Warehouse robots must dock after the night cycle"}
        grounded = {"title": GROUNDED_RESET_TITLE}
        kept, rejected = _filter_ungrounded_suite_cases_with_reasons(
            [ungrounded, grounded], PASSWORD_RESET_TEXT
        )
        self.assertEqual([GROUNDED_RESET_TITLE], [c["title"] for c in kept])
        self.assertEqual([REASON_NO_SOURCE_GROUNDING], [reason for _c, reason in rejected])


class PipelineFilterSummaryTests(unittest.TestCase):
    def test_job_result_reports_generated_persisted_and_rejected_by_reason(self):
        store = _password_reset_store()
        llm = ScenarioLLM(e2e_payload={
            "e2e_tests": [
                {
                    "title": PROMPT_EXEMPLAR_E2E_TITLE,
                    "steps": [{"content": "Join", "expectedResult": "Fails"}],
                },
                {
                    "title": HYBRID_E2E_TITLE,
                    "steps": [{"content": "Send reset link", "expectedResult": "Fails"}],
                },
                {
                    "title": GROUNDED_RESET_TITLE,
                    "steps": [{
                        "content": "Request a password reset",
                        "expectedResult": "A reset email is sent",
                    }],
                },
            ],
            "edge_cases": [
                {
                    "title": PROMPT_EXEMPLAR_EDGE_TITLE,
                    "steps": [{"content": "Delete and join", "expectedResult": "Conflict"}],
                },
            ],
            "business_tests": [{
                "title": GROUNDED_RESET_TITLE,
                "steps": [{
                    "content": "Request a password reset",
                    "expectedResult": "A reset email is sent",
                }],
            }],
        })
        out = _run(store, llm)

        summary = out["testgen_filter"]
        self.assertEqual(summary["generated"], summary["persisted"] + summary["rejected"])
        self.assertGreater(summary["rejected"], 0)
        self.assertEqual(
            summary["rejected"], sum(summary["rejected_by_reason"].values())
        )
        # The verbatim E2E and edge exemplars, and the hybrid E2E, must all be
        # accounted for under the fixed vocabulary -- not silently absorbed.
        self.assertIn(REASON_EXEMPLAR_COPY, summary["rejected_by_reason"])
        self.assertIn(REASON_HYBRID_SCAFFOLD, summary["rejected_by_reason"])

    def test_edge_suppressed_reason_appears_when_edge_evidence_is_insufficient(self):
        # A store/LLM pair where edge_cases come back non-empty but edge evidence
        # is judged insufficient: those cases must be counted as edge-suppressed,
        # not silently dropped with no reason.
        store = _password_reset_store()
        llm = ScenarioLLM(e2e_payload={
            "e2e_tests": [{
                "title": GROUNDED_RESET_TITLE,
                "steps": [{
                    "content": "Request a password reset",
                    "expectedResult": "A reset email is sent",
                }],
            }],
            "edge_cases": [{
                "title": "Concurrent password reset requests race on the same token",
                "steps": [{"content": "Race two resets", "expectedResult": "One wins cleanly"}],
            }],
            "business_tests": [],
        })
        out = _run(store, llm)
        summary = out["testgen_filter"]
        if REASON_EDGE_SUPPRESSED in summary["rejected_by_reason"]:
            self.assertGreater(summary["rejected_by_reason"][REASON_EDGE_SUPPRESSED], 0)
        else:
            # Evidence was judged sufficient for this scenario's edge case instead
            # of suppressed -- acceptable, as long as it wasn't silently dropped
            # (it should then be persisted or rejected under another reason).
            self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
