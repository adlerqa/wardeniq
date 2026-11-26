"""An Ollama call that needs more tokens than its context window is reported (#249 follow-up).

Found by a tester reading Ollama's own log on a CPU-only machine: the combined E2E call sent
5,117 prompt tokens and wrote 4,250 in an 8,192-token window, and Ollama logged `truncated = 1`.
Ollama does not fail such a call: it keeps writing and throws away part of the earlier text, which
is the instructions and evidence at the start of the prompt. The reply still parsed, but it may
have ignored the rules, and wardenIQ said nothing (its only warning is for hitting the output
limit). Ollama returns `prompt_eval_count` and `eval_count` on every call, so the app can tell.

What is pinned here:
  * a call whose prompt plus reply is larger than the window is recorded on the LLM object and
    logged, with the task it belonged to and the numbers; a call that fits, or exactly fills the
    window, or has no counts, is not
  * the window used is the one actually sent (it respects OLLAMA_MAX_NUM_CTX)
  * the generation pipeline reports only the overflows of its own run, in the job log and in the
    job result
"""
import os
import sys
import unittest
from unittest.mock import patch

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import llm as llm_module  # noqa: E402
from llm import LLM  # noqa: E402
from testgen.service import generate_fresh_testcases_pipeline  # noqa: E402
from tests.test_rag_evidence_sufficiency import ScenarioLLM, _delivery_store  # noqa: E402
from tests.test_generation_pipeline import FakeEmbedder  # noqa: E402

E2E_USER = "TASK: Generate E2E flows, edge cases, and business rule tests\n\nlots of evidence"


class FakeResponse:
    status_code = 200

    def __init__(self, prompt, reply):
        self._data = {"message": {"content": "{}"}, "prompt_eval_count": prompt, "eval_count": reply,
                      "done_reason": "stop"}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def call(prompt, reply, num_ctx=8192, user=E2E_USER, **env):
    """One Ollama call that reports these token counts; returns (the LLM, the warning calls)."""
    model = LLM(provider="ollama", model="qwen2.5:3b")
    with patch.object(llm_module.httpx, "post", lambda *a, **k: FakeResponse(prompt, reply)), \
            patch.object(llm_module.log, "warning") as warning:
        model._raw_chat("system", user, num_ctx, 0.1, 10000)
    return model, warning.call_args_list


class TestRecordedOnTheLlm(unittest.TestCase):
    def test_the_real_runs_numbers_are_recorded_with_the_task(self):
        model, warnings = call(5117, 4250)
        self.assertEqual([{
            "model": "qwen2.5:3b", "task": "Generate E2E flows, edge cases, and business rule tests",
            "prompt_tokens": 5117, "reply_tokens": 4250, "context": 8192,
        }], model.context_overflows)
        self.assertEqual(1, len(warnings))

    def test_the_warning_says_what_happened_and_what_to_do(self):
        _, warnings = call(5117, 4250)
        args = warnings[0][0]
        text = args[0] % args[1:]
        self.assertIn("9367 tokens", text)
        self.assertIn("5117 prompt + 4250 reply", text)
        self.assertIn("8192-token context", text)
        self.assertIn("OLLAMA_MAX_NUM_CTX", text)

    def test_a_call_that_fits_is_not_recorded(self):
        model, warnings = call(5000, 2000)
        self.assertEqual([], model.context_overflows)
        self.assertEqual([], warnings)

    def test_a_call_that_exactly_fills_the_window_is_not_recorded(self):
        model, _ = call(5000, 3192)
        self.assertEqual([], model.context_overflows)

    def test_one_token_over_is(self):
        model, _ = call(5000, 3193)
        self.assertEqual(1, len(model.context_overflows))

    def test_missing_counts_are_not_an_overflow(self):
        model = LLM(provider="ollama", model="m")
        with patch.object(llm_module.httpx, "post", lambda *a, **k: FakeResponse(None, None)):
            model._raw_chat("s", "u", 8192, 0.1, 100)
        self.assertEqual([], model.context_overflows)

    def test_a_call_without_a_task_line_is_still_recorded(self):
        model, _ = call(9000, 500, user="just a prompt")
        self.assertEqual("", model.context_overflows[0]["task"])

    def test_the_window_is_the_one_actually_sent(self):
        # the caller asks for 8192 but OLLAMA_MAX_NUM_CTX caps the window at 4096
        with patch.object(llm_module, "OLLAMA_MAX_NUM_CTX", 4096):
            model, _ = call(3000, 1500, num_ctx=8192)
        self.assertEqual(4096, model.context_overflows[0]["context"])

    def test_each_llm_object_has_its_own_list(self):
        a, b = LLM(provider="ollama"), LLM(provider="ollama")
        a.context_overflows.append({"x": 1})
        self.assertEqual([], b.context_overflows)


class OverflowingLLM(ScenarioLLM):
    """A scenario model that, like LLM, notes the calls that outgrew the window."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context_overflows = []

    def chat_json(self, system, user, **kwargs):
        if "Generate E2E flows, edge cases, and business rule tests" in user:
            self.context_overflows.append({"model": "m", "task": "Generate E2E flows, edge cases, and business rule tests",
                                           "prompt_tokens": 5117, "reply_tokens": 4250, "context": 8192})
        return super().chat_json(system, user, **kwargs)


class TestReportedByThePipeline(unittest.TestCase):
    def run_pipeline(self, llm):
        stages = []
        result = generate_fresh_testcases_pipeline(
            _delivery_store(), llm, FakeEmbedder(),
            {"feature_id": "feature-1", "total": 40,
             "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20}},
            update_job_fn=lambda stage=None, progress=None: stages.append(stage))
        return result, stages

    def test_an_overflow_during_the_run_is_in_the_result_and_the_job_log(self):
        result, stages = self.run_pipeline(OverflowingLLM())
        self.assertEqual(1, len(result["context_overflows"]))
        self.assertEqual(9367, result["context_overflows"][0]["prompt_tokens"] + result["context_overflows"][0]["reply_tokens"])
        message = next(s for s in stages if s.startswith("Context window exceeded"))
        self.assertIn("9367 tokens", message)
        self.assertIn("8192-token window", message)
        self.assertIn("OLLAMA_MAX_NUM_CTX", message)

    def test_only_this_runs_overflows_are_reported(self):
        llm = OverflowingLLM()
        llm.context_overflows.append({"model": "m", "task": "an earlier job's call", "prompt_tokens": 1,
                                      "reply_tokens": 9000, "context": 8192})
        result, stages = self.run_pipeline(llm)
        self.assertEqual(["Generate E2E flows, edge cases, and business rule tests"],
                         [item["task"] for item in result["context_overflows"]])
        self.assertFalse(any("earlier job" in s for s in stages))

    def test_a_clean_run_reports_none(self):
        result, stages = self.run_pipeline(ScenarioLLM())      # no context_overflows attribute at all
        self.assertEqual([], result["context_overflows"])
        self.assertFalse(any(s.startswith("Context window exceeded") for s in stages))


if __name__ == "__main__":
    unittest.main()
