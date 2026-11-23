"""The business-tests fallback asks for the tests that will be kept, not one per requirement (#249).

Measured on a GPU qwen2.5:3b with examples/sample-prd.md (about 20 extracted requirements), twice:
the fallback was told "exactly 20 tests, one per rule" and wrote 4,784 and 3,946 tokens, 40% and
34% of the whole run's output and about a third of its time. In the second run 19 of its 20 tests
had the same title. The duplicate filter dropped the repeats and `_budget_suites` then trimmed the
business suite to its focus share (8 or 9), so almost all of that output was thrown away.

What is pinned here:
  * the prompt builder only changes when a caller passes `max_tests` below the rule count; with no
    limit (or a limit at or above the rule count) the text is the old one, word for word
  * `_business_fallback_request` asks for max(acceptable suite size, what `_budget_suites` keeps)
    minus the business tests already produced, never more than the rules, never less than 1,
    and follows the user's focus weights (a heavy functional focus is not capped at 10)
  * the pipeline passes that number to the fallback prompt
"""
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import testgen.service as svc  # noqa: E402
from testgen.prompt_builder import build_business_test_prompt  # noqa: E402

EVEN = {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20}
# pool counts of the other categories in the measured run: 10 API, 9 UI, 4 E2E, 2 edge
OTHERS = {"api": 10, "ui": 9, "e2e": 4, "nfr": 2}


def ctx(rules):
    return {"featureName": "Reset", "businessContext": {"requirements": rules}, "summaries": {"prd": ""}}


def prompt(n_rules, **kw):
    return build_business_test_prompt(ctx([f"Rule {i} must hold" for i in range(n_rules)]), {}, top_k=4, **kw)


# ------------------------------------------------------------------ the prompt builder
class TestPromptBuilder:
    def test_a_smaller_request_asks_for_that_many_different_rules(self):
        p = prompt(20, max_tests=9)
        assert "contains 20 distinct rules" in p
        assert "Generate exactly 9 tests" in p
        assert "DIFFERENT rule" in p and "9 most important" in p
        assert "Output at most 9 tests" in p
        assert "one per rule" not in p

    def test_no_limit_is_the_old_text_exactly(self):
        p = prompt(20)
        assert "Generate exactly 20 tests — one per rule." in p
        assert "Output at most 20 tests" in p
        assert "DIFFERENT" not in p

    @pytest.mark.parametrize("limit", [20, 21, 500])
    def test_a_limit_at_or_above_the_rule_count_changes_nothing(self, limit):
        assert prompt(20, max_tests=limit) == prompt(20)

    def test_a_limit_below_one_still_asks_for_one(self):
        p = prompt(5, max_tests=0)
        assert "Generate exactly 1 tests" in p and "Output at most 1 tests" in p

    def test_no_rules_extracted_keeps_the_fixed_ceiling_unless_limited(self):
        base = build_business_test_prompt(ctx([]), {}, top_k=4)
        assert "Generate exactly one test per rule" in base and "Output at most 10 tests" in base
        limited = build_business_test_prompt(ctx([]), {}, top_k=4, max_tests=7)
        assert "at most 7 tests" in limited and "Output at most 7 tests" in limited
        # a limit above the fixed ceiling cannot raise it
        assert "Output at most 10 tests" in build_business_test_prompt(ctx([]), {}, top_k=4, max_tests=50)


# ------------------------------------------------------------------ how many to ask for
def request(**kw):
    args = dict(requirement_count=20, have=0, acceptable_min=10, others=OTHERS, focus=EVEN, total=16)
    args.update(kw)
    return svc._business_fallback_request(**args)


class TestRequestSize:
    def test_the_measured_run_asks_for_nine_not_twenty(self):
        # E2E call wrote 1 business test; the suite is acceptable at 10; the budget keeps
        # ceil(0.2 * 25 / 0.8) = 7. So 10 - 1 = 9 more, instead of one per rule (20).
        assert request(have=1) == 9

    def test_nothing_already_written(self):
        assert request(have=0) == 10

    def test_what_is_already_written_is_subtracted(self):
        assert request(have=6) == 4

    def test_never_less_than_one(self):
        assert request(have=30) == 1

    def test_never_more_than_the_rules(self):
        assert request(requirement_count=4, have=0) == 4

    def test_a_heavy_functional_focus_is_not_capped_at_ten(self):
        focus = {"functional": 60, "e2e": 10, "api": 10, "nfr": 10, "ui": 10}
        # budget keeps ceil(0.6 * 25 / 0.4) = 38, more than the 20 rules, so every rule
        assert request(focus=focus) == 20
        assert request(focus=focus, requirement_count=0) == 38

    def test_functional_only_focus_keeps_every_rule(self):
        focus = {"functional": 100, "e2e": 0, "api": 0, "nfr": 0, "ui": 0}
        assert request(focus=focus, have=1) == 19

    def test_categories_with_zero_weight_do_not_count_towards_the_pool(self):
        focus = {"functional": 20, "e2e": 20, "api": 0, "nfr": 20, "ui": 20}
        with_api = request(focus=EVEN, acceptable_min=3, requirement_count=40)
        without_api = request(focus=focus, acceptable_min=3, requirement_count=40)
        # all four others counted: ceil(0.2 * 25 / 0.8) = 7; without API (weight 0, so it is
        # dropped from the pool): the share is 20/80 and the rest is 15 -> ceil(0.25 * 15 / 0.75) = 5
        assert with_api == 7
        assert without_api == 5

    def test_smoke_mode_uses_the_requested_total(self):
        assert request(smoke_mode=True, total=100, acceptable_min=3, requirement_count=40) == 20
        assert request(smoke_mode=True, total=16, acceptable_min=3) == 3

    def test_missing_weights_default_to_an_even_split(self):
        assert request(focus=None, have=1) == 9


# ------------------------------------------------------------------ wired into the pipeline
class TestPipelinePassesTheRequest:
    def _run(self, monkeypatch, focus=EVEN, smoke=True):
        from test_generation_pipeline import FakeEmbedder, FakeStore, SpyLLM

        asked, prompt_args = {}, {}
        real_prompt = svc.build_business_test_prompt

        def spy_request(*args, **kwargs):
            asked["args"], asked["kwargs"] = args, kwargs
            return 5

        def spy_prompt(context, rag_context=None, top_k=6, max_tests=None):
            prompt_args["max_tests"] = max_tests
            return real_prompt(context, rag_context, top_k=top_k, max_tests=max_tests)

        monkeypatch.setattr(svc, "_business_fallback_request", spy_request)
        monkeypatch.setattr(svc, "build_business_test_prompt", spy_prompt)
        llm = SpyLLM()
        svc.generate_fresh_testcases_pipeline(
            FakeStore(), llm, FakeEmbedder(),
            {"feature_id": "feature-1", "total": 16, "focus": focus, "smoke_mode": smoke},
        )
        return asked, prompt_args, llm

    def test_the_fallback_prompt_gets_the_helpers_answer(self, monkeypatch):
        asked, prompt_args, llm = self._run(monkeypatch)
        assert asked, "the business fallback did not run"
        assert prompt_args["max_tests"] == 5
        assert llm.calls_matching("Generate one business rule test per requirement rule")

    def test_the_helper_is_given_what_the_pipeline_knows(self, monkeypatch):
        asked, _, _ = self._run(monkeypatch)
        requirement_count, have, acceptable_min, others, focus, total = asked["args"]
        assert have == 0  # the fixture's E2E call writes no business tests
        assert acceptable_min == min(10, max(3, round(requirement_count * 0.6)))
        assert set(others) == {"api", "ui", "e2e", "nfr"}
        assert others["api"] == 3 and others["ui"] == 0  # what DAG layer 1 produced in the fixture
        assert focus == EVEN and total == 16
        assert asked["kwargs"] == {"smoke_mode": True}

    def test_the_fallback_is_unchanged_when_no_business_focus(self, monkeypatch):
        focus = {"functional": 0, "e2e": 50, "api": 50, "nfr": 0, "ui": 0}
        asked, _, llm = self._run(monkeypatch, focus=focus)
        assert not asked
        assert not llm.calls_matching("Generate one business rule test")
