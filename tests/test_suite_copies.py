"""A test written in one suite under another suite's title is dropped (#249 follow-up).

Reported by a tester on a CPU-only machine (qwen2.5:3b, examples/sample-prd.md): the combined
E2E call wrote five business tests that were word-for-word copies of its own E2E titles. The
16 kept cases had 11 distinct titles: four of the copies were kept again as e2e and one as
nfr. `_deduplicate` only compares within one suite and the identity hash includes the suite,
so nothing noticed. The copies also took the business suite's slots, and the five distinct
business tests the fallback wrote afterwards were trimmed away by the budget step, which keeps
the first ones.

What is pinned here:
  * the title comparison ignores case and punctuation
  * a business test or edge case whose title is already an E2E (or API) test's title is dropped,
    and counted under its own reason in the job result
  * that happens BEFORE the business fallback counts what it has, so the fallback asks for the
    tests that are really missing, and the fallback's own copies are dropped too
  * the prompt asks for distinct titles
"""
import os
import sys
import unittest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import testgen.service as svc  # noqa: E402
from testgen.prompt_builder import REASON_SUITE_COPY, build_e2e_agent_prompt  # noqa: E402
from tests.test_rag_evidence_sufficiency import ScenarioLLM, _delivery_store, _run, _titles  # noqa: E402


def case(title, intent="x"):
    return {"title": title, "intent": intent,
            "steps": [{"content": "Do it", "expectedResult": "It works"}]}


FLOW_1 = "Carrier records a shipment, then reads its status back"
FLOW_2 = "A shipment already marked delivered rejects a further status transition"
RULE = "Carrier partners must authenticate with a partner token before any call"


class TestTitleComparison(unittest.TestCase):
    def test_case_and_punctuation_do_not_matter(self):
        self.assertEqual(svc._title_key(case("User resets,  the Password!")), "user resets the password")
        self.assertEqual(svc._title_key({}), "")

    def test_a_copy_is_dropped_and_the_rest_keeps_its_order(self):
        kept, dropped = svc._drop_title_copies(
            [case("B rule"), case("a flow."), case("C rule")], [case("A Flow")])
        self.assertEqual(["B rule", "C rule"], [c["title"] for c in kept])
        self.assertEqual([("a flow.", REASON_SUITE_COPY)], [(c["title"], r) for c, r in dropped])

    def test_empty_titles_never_match_each_other(self):
        kept, dropped = svc._drop_title_copies([case("")], [case("")])
        self.assertEqual(1, len(kept))
        self.assertEqual([], dropped)

    def test_non_dict_entries_are_ignored_not_raised(self):
        kept, dropped = svc._drop_title_copies([case("x"), None, "text"], [None, "text", case("y")])
        self.assertEqual(3, len(kept))
        self.assertEqual([], dropped)

    def test_a_title_repeated_inside_one_list_is_left_to_the_ordinary_deduplication(self):
        kept, dropped = svc._drop_title_copies([case("same"), case("same")], [])
        self.assertEqual(2, len(kept))
        self.assertEqual([], dropped)


class TestThePrompt(unittest.TestCase):
    def test_business_titles_must_differ_from_e2e_and_edge_titles(self):
        context = {"featureName": "Parcel tracking", "summaries": {}, "flags": {},
                   "businessContext": {"prd": {"requirements": ["r"]}}}
        prompt = build_e2e_agent_prompt(context, [], [], {}, 0)
        self.assertIn("must differ from the title of every e2e_tests and edge_cases item", prompt)
        self.assertIn("write fewer business tests", prompt)


class TestThroughThePipeline(unittest.TestCase):
    def payload(self, edge=(), business=()):
        return {"e2e_tests": [case(FLOW_1), case(FLOW_2)], "edge_cases": list(edge), "business_tests": list(business)}

    def run_with(self, payload, fallback=()):
        store = _delivery_store()
        llm = ScenarioLLM(e2e_payload=payload, business_fallback=list(fallback))
        asked = {}
        real = svc._business_fallback_request

        def spy(requirement_count, have, *args, **kwargs):
            asked["have"] = have
            return real(requirement_count, have, *args, **kwargs)

        svc._business_fallback_request = spy
        try:
            result = _run(store, llm)
        finally:
            svc._business_fallback_request = real
        return store, result, asked

    def test_business_copies_of_e2e_titles_are_not_kept(self):
        store, result, _ = self.run_with(self.payload(business=[case(FLOW_1), case(FLOW_2), case(RULE)]))
        keys = [svc._title_key({"title": title}) for title in _titles(store)]
        self.assertEqual(len(keys), len(set(keys)), "a title was kept in two suites")
        self.assertIn(RULE, _titles(store))
        self.assertEqual(2, result["testgen_filter"]["rejected_by_reason"].get(REASON_SUITE_COPY))

    def test_an_edge_case_that_copies_an_e2e_title_is_not_kept(self):
        store, result, _ = self.run_with(self.payload(edge=[case(FLOW_1.upper() + "!")]))
        keys = [svc._title_key({"title": title}) for title in _titles(store)]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(1, result["testgen_filter"]["rejected_by_reason"].get(REASON_SUITE_COPY))

    def test_the_fallback_counts_only_the_business_tests_that_are_really_there(self):
        _, _, asked = self.run_with(self.payload(business=[case(FLOW_1), case(FLOW_2), case(RULE)]))
        self.assertEqual(1, asked["have"], "the two copies must not count as business tests")

    def test_the_copies_of_a_run_with_nothing_else_leave_the_fallback_to_fill_the_suite(self):
        store, result, asked = self.run_with(
            self.payload(business=[case(FLOW_1), case(FLOW_2)]),
            fallback=[case("Refunds are refused after a shipment is delivered")])
        self.assertEqual(0, asked["have"])
        self.assertIn("Refunds are refused after a shipment is delivered", _titles(store))

    def test_a_fallback_test_that_copies_an_e2e_title_is_dropped_too(self):
        store, result, _ = self.run_with(
            self.payload(), fallback=[case(FLOW_2), case("Refunds are refused after delivery")])
        keys = [svc._title_key({"title": title}) for title in _titles(store)]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("Refunds are refused after delivery", _titles(store))
        self.assertGreaterEqual(result["testgen_filter"]["rejected_by_reason"].get(REASON_SUITE_COPY, 0), 1)

    def test_distinct_titles_are_untouched(self):
        store, result, _ = self.run_with(self.payload(business=[case(RULE)]))
        self.assertIn(RULE, _titles(store))
        self.assertNotIn(REASON_SUITE_COPY, result["testgen_filter"]["rejected_by_reason"])


if __name__ == "__main__":
    unittest.main()
