"""Each retrieved passage is printed once in the combined E2E prompt (#249 follow-up).

A tester on a CPU-only machine found that the combined E2E call sent 5,117 prompt tokens and wrote
4,250 in an 8,192-token window, so Ollama dropped part of the earlier text mid-reply. Measured on
a real run, that prompt was 5,862 tokens, and its three retrieved-evidence blocks (one each for the
E2E, edge-case and business suites, each from its own retrieval over the same few chunks) shared 10
of their 13 distinct lines. The same passages were in the prompt three times.

What is pinned here:
  * without `shown` the evidence text is exactly what it always was, for every other prompt
  * with it, a passage or summary an earlier block printed is replaced by a pointer to it, and
    everything else (order, numbering, scores, distinct passages) is kept
  * the combined prompt prints each passage once, keeps all three blocks and their labels, and is
    clearly shorter
"""
import os
import sys
import unittest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

from testgen.prompt_builder import build_e2e_agent_prompt, build_rag_evidence_block  # noqa: E402


def chunk(text, score=0.5, source="prd"):
    return {"text": text, "score": score, "sourceType": source}


ALPHA = "A reset link expires after 30 minutes and can be used once."
BETA = "Requests are rate limited to 5 per hour per email address."
GAMMA = "The reset form requires a new password of at least 12 characters."
DELTA = "The reset email never says whether an account exists."


def ctx(*chunks, summary="Password reset"):
    return {"summary": summary, "retrieved_chunks": list(chunks)}


class TestDefaultIsUnchanged(unittest.TestCase):
    def test_no_shown_dict_means_the_old_text(self):
        c = ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.4))
        self.assertEqual(build_rag_evidence_block(c, 4), build_rag_evidence_block(c, 4, None, ""))

    def test_the_same_context_twice_without_shown_prints_everything_twice(self):
        c = ctx(chunk(ALPHA))
        self.assertEqual(build_rag_evidence_block(c, 4), build_rag_evidence_block(c, 4))
        self.assertIn(ALPHA, build_rag_evidence_block(c, 4))

    def test_missing_contexts_are_unchanged(self):
        self.assertEqual("RAG EVIDENCE: none.", build_rag_evidence_block(None, 4, {}, "X"))
        self.assertIn("none retrieved", build_rag_evidence_block(ctx(), 4, {}, "X"))


class TestPointers(unittest.TestCase):
    def test_a_repeated_passage_becomes_a_pointer_to_the_first_block(self):
        shown = {}
        first = build_rag_evidence_block(ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.8)), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk(BETA, 0.9), chunk(GAMMA, 0.5)), 4, shown, "EDGE")
        self.assertIn(ALPHA, first)
        self.assertEqual(1, second.count("the same passage as E2E [2]"))
        self.assertNotIn(BETA, second)
        self.assertIn(GAMMA, second)

    def test_order_numbering_and_scores_are_kept(self):
        shown = {}
        build_rag_evidence_block(ctx(chunk(ALPHA, 0.9)), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk(DELTA, 0.2), chunk(ALPHA, 0.7)), 4, shown, "EDGE")
        self.assertLess(second.index("[1] SOURCE=prd | SCORE=0.7000"), second.index("[2] SOURCE=prd | SCORE=0.2000"))
        self.assertIn("(the same passage as E2E [1])", second)

    def test_a_pointer_may_point_into_the_second_block(self):
        shown = {}
        build_rag_evidence_block(ctx(chunk(ALPHA)), 4, shown, "E2E")
        build_rag_evidence_block(ctx(chunk(BETA)), 4, shown, "EDGE")
        third = build_rag_evidence_block(ctx(chunk(BETA)), 4, shown, "BUSINESS")
        self.assertIn("(the same passage as EDGE [1])", third)

    def test_the_summary_is_printed_once(self):
        shown = {}
        first = build_rag_evidence_block(ctx(chunk(ALPHA), summary="Password reset flow"), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk(BETA), summary="Password reset flow"), 4, shown, "EDGE")
        self.assertIn("Password reset flow", first)
        self.assertNotIn("Password reset flow", second)
        self.assertIn("same as in the E2E block above", second)

    def test_a_different_summary_is_still_printed(self):
        shown = {}
        build_rag_evidence_block(ctx(chunk(ALPHA), summary="one"), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk(BETA), summary="another"), 4, shown, "EDGE")
        self.assertIn("another", second)

    def test_whitespace_differences_do_not_hide_a_repeat(self):
        shown = {}
        build_rag_evidence_block(ctx(chunk("A  reset link\nexpires soon")), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk("A reset link expires soon")), 4, shown, "EDGE")
        self.assertIn("the same passage as E2E [1]", second)

    def test_a_pointer_still_respects_top_k(self):
        shown = {}
        build_rag_evidence_block(ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.8)), 4, shown, "E2E")
        second = build_rag_evidence_block(ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.8)), 1, shown, "EDGE")
        self.assertEqual(1, second.count("the same passage"))


class TestTheCombinedPrompt(unittest.TestCase):
    def prompt(self):
        shared = ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.8), chunk(GAMMA, 0.7), chunk(DELTA, 0.6), summary="Password reset " * 40)
        context = {"featureName": "Password reset", "summaries": {}, "flags": {},
                   "businessContext": {"prd": {"requirements": ["r1", "r2"]}}}
        return build_e2e_agent_prompt(context, [], [], shared, 0, 4, shared, 4, shared, 4)

    def test_each_passage_is_printed_once(self):
        prompt = self.prompt()
        for passage in (ALPHA, BETA, GAMMA, DELTA):
            self.assertEqual(1, prompt.count(passage), passage)

    def test_all_three_blocks_and_their_labels_are_still_there(self):
        prompt = self.prompt()
        for label in ("E2E/JOURNEY RETRIEVED EVIDENCE", "API/STATE-MUTATION RETRIEVED EVIDENCE",
                      "BUSINESS RULE RETRIEVED EVIDENCE"):
            self.assertIn(label, prompt)
        self.assertEqual(3, prompt.count("RAG SUMMARY:"))
        self.assertEqual(3, prompt.count("TOP RETRIEVED CHUNKS (highest relevance first):"))

    def test_the_later_blocks_point_back_to_the_first(self):
        prompt = self.prompt()
        self.assertGreaterEqual(prompt.count("the same passage as E2E/JOURNEY"), 4)

    def test_the_prompt_is_clearly_shorter_than_with_three_full_copies(self):
        shared = ctx(chunk(ALPHA, 0.9), chunk(BETA, 0.8), chunk(GAMMA, 0.7), chunk(DELTA, 0.6), summary="Password reset " * 40)
        legacy = 3 * len(build_rag_evidence_block(shared, 4))
        now = len(self.prompt()) - len(build_e2e_agent_prompt(
            {"featureName": "Password reset", "summaries": {}, "flags": {},
             "businessContext": {"prd": {"requirements": ["r1", "r2"]}}}, [], [],
            {}, 0, 4, {}, 4, {}, 4))
        self.assertLess(now, legacy * 0.6)


if __name__ == "__main__":
    unittest.main()
