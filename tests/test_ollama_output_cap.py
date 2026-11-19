"""An output limit the caller chose is enforced on a local Ollama model (#249).

Ollama only stops a reply at `num_predict`, and the app never sent it, so a small model that fell
into a repetition loop wrote thousands of tokens (about 20,000 in 30 minutes in one observed
run), bounded only by the call's timeout, which people are told to raise on CPU. The pipeline
already asks for a limit on every call (3,000 to 10,000 tokens); this makes Ollama honour it, the
way the benchmark runner's "pipeline" mode already does.

What is pinned here:
  * only a limit the caller CHOSE is sent: chat_json and call_llm_json_with_repair now default to
    None ("no limit chosen"), so callers that never chose one (the code generator, the Mind Map
    reviewers' defaults) stay unbounded on Ollama exactly as before
  * Anthropic and Bedrock, which require a limit, still get the old default of 4000 for those callers
  * OpenAI-compatible providers are untouched (newer OpenAI models reject `max_tokens`)
  * a reply cut off at the limit is reported, and the repair call gets headroom above the limit
    so that a truncated reply can actually be repaired
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import llm as llm_module  # noqa: E402
import testgen.service as svc  # noqa: E402
from llm import DEFAULT_MAX_TOKENS, LLM  # noqa: E402


def ollama_reply(content='{"ok": true}', done_reason="stop"):
    r = MagicMock(status_code=200, text="")
    r.json.return_value = {"message": {"content": content}, "done_reason": done_reason,
                           "prompt_eval_count": 10, "eval_count": 5}
    return r


def sent(post):
    """The JSON bodies of every httpx.post made, in order."""
    return [c.kwargs["json"] for c in post.call_args_list]


def chat_ollama(max_tokens, **kw):
    with patch("httpx.post", return_value=ollama_reply(**kw)) as post:
        LLM(provider="ollama", model="qwen2.5:3b")._raw_chat("s", "u", 8192, 0.1, max_tokens)
    return sent(post)[0]


# ------------------------------------------------------------------ Ollama honours an explicit limit
class TestOllamaRequest:
    def test_an_explicit_limit_is_sent_as_num_predict(self):
        body = chat_ollama(3000)
        assert body["options"]["num_predict"] == 3000

    def test_the_other_options_are_unchanged(self):
        opts = chat_ollama(3000)["options"]
        assert opts["temperature"] == 0.1 and opts["num_ctx"] == 8192
        assert set(opts) == {"temperature", "num_ctx", "num_predict"}

    def test_no_limit_chosen_sends_no_num_predict_at_all(self):
        opts = chat_ollama(None)["options"]
        assert "num_predict" not in opts and set(opts) == {"temperature", "num_ctx"}

    @pytest.mark.parametrize("value", [0, -1, -4000])
    def test_zero_or_negative_is_not_a_limit(self, value):
        assert "num_predict" not in chat_ollama(value)["options"]

    def test_the_context_cap_is_unchanged(self):
        with patch("httpx.post", return_value=ollama_reply()) as post:
            LLM(provider="ollama", model="m")._raw_chat("s", "u", 99999, 0.1, 500)
        assert sent(post)[0]["options"]["num_ctx"] == llm_module.OLLAMA_MAX_NUM_CTX

    def test_a_float_limit_is_sent_as_a_whole_number(self):
        assert chat_ollama(6500.0)["options"]["num_predict"] == 6500

    def test_json_format_and_non_streaming_are_unchanged(self):
        body = chat_ollama(3000)
        assert body["format"] == "json" and body["stream"] is False


class TestCutOffReply:
    def test_a_reply_cut_at_the_limit_is_logged_with_the_limit(self):
        with patch.object(llm_module.log, "warning") as warn:
            chat_ollama(3000, done_reason="length")
        (fmt, *args), _ = warn.call_args
        assert "cut off" in fmt and 3000 in args and "qwen2.5:3b" in args

    def test_a_reply_that_finished_is_not_logged(self):
        with patch.object(llm_module.log, "warning") as warn:
            chat_ollama(3000, done_reason="stop")
        warn.assert_not_called()

    def test_without_a_limit_there_is_nothing_to_report(self):
        with patch.object(llm_module.log, "warning") as warn:
            chat_ollama(None, done_reason="length")      # e.g. the window filled; not our limit
        warn.assert_not_called()

    def test_the_reply_text_is_still_returned(self):
        with patch("httpx.post", return_value=ollama_reply('{"a": 1', done_reason="length")):
            out = LLM(provider="ollama", model="m")._raw_chat("s", "u", 8192, 0.1, 100)
        assert out == '{"a": 1'


# ------------------------------------------------------------------ chat_json's default
class TestChatJsonDefault:
    def test_the_default_is_no_limit(self):
        with patch("httpx.post", return_value=ollama_reply()) as post:
            LLM(provider="ollama", model="m").chat_json("s", "u")
        assert "num_predict" not in sent(post)[0]["options"]

    def test_an_explicit_limit_passed_to_chat_json_reaches_ollama(self):
        with patch("httpx.post", return_value=ollama_reply()) as post:
            LLM(provider="ollama", model="m").chat_json("s", "u", max_tokens=2000)
        assert sent(post)[0]["options"]["num_predict"] == 2000

    def test_the_health_check_ping_is_limited_to_its_own_50_tokens(self):
        with patch("httpx.post", return_value=ollama_reply()) as post, \
                patch("httpx.get", side_effect=RuntimeError("no tags in this test")):
            LLM(provider="ollama", model="m").ping()
        assert sent(post)[0]["options"]["num_predict"] == 50


# ------------------------------------------------------------------ other providers do not change
class TestOtherProvidersUnchanged:
    def anthropic_body(self, max_tokens):
        r = MagicMock(status_code=200, text="")
        r.json.return_value = {"content": [{"text": "{}"}], "usage": {}}
        with patch("httpx.post", return_value=r) as post:
            LLM(provider="anthropic", model="claude", api_key="k")._raw_chat("s", "u", 8192, 0.1, max_tokens)
        return sent(post)[0]

    def test_anthropic_gets_its_old_default_when_none_was_chosen(self):
        assert self.anthropic_body(None)["max_tokens"] == DEFAULT_MAX_TOKENS == 4000

    def test_anthropic_gets_an_explicit_limit_as_before(self):
        assert self.anthropic_body(6500)["max_tokens"] == 6500

    def test_bedrock_gets_the_default_and_an_explicit_limit_as_before(self):
        for chosen, expected in ((None, 4000), (6500, 6500)):
            client = MagicMock()
            client.converse.return_value = {"output": {"message": {"content": [{"text": "{}"}]}}, "usage": {}}
            m = LLM(provider="bedrock", model="m", region="us-east-1")
            with patch.object(m, "_bedrock_client", return_value=client):
                m._raw_chat("s", "u", 8192, 0.1, chosen)
            assert client.converse.call_args.kwargs["inferenceConfig"]["maxTokens"] == expected

    @pytest.mark.parametrize("provider", ["openai", "groq", "mistral", "gemini"])
    def test_openai_compatible_providers_get_no_output_limit_key(self, provider):
        r = MagicMock(status_code=200, text="")
        r.json.return_value = {"choices": [{"message": {"content": "{}"}}], "usage": {}}
        with patch("httpx.post", return_value=r) as post:
            LLM(provider=provider, model="m", api_key="k")._raw_chat("s", "u", 8192, 0.1, 6500)
        body = sent(post)[0]
        assert "max_tokens" not in body and "max_completion_tokens" not in body


# ------------------------------------------------------------------ the pipeline helper
class Recorder:
    """A model double: returns scripted replies and records the limit of every call."""

    provider = "ollama"
    model = "m"

    def __init__(self, replies):
        self.replies, self.limits = list(replies), []

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens, timeout_seconds=None):
        self.limits.append(max_tokens)
        return self.replies.pop(0)


class TestRepairLimit:
    @pytest.mark.parametrize("cap,expected", [(1000, 1506), (3000, 4006), (6500, 8381), (10000, 12756)])
    def test_the_repair_gets_a_quarter_more_plus_a_little(self, cap, expected):
        assert svc._repair_limit(cap) == expected

    @pytest.mark.parametrize("cap", [None, 0])
    def test_no_limit_chosen_means_none_for_the_repair_too(self, cap):
        assert svc._repair_limit(cap) is None

    @pytest.mark.parametrize("cap", [500, 3000, 6500])
    def test_the_repair_always_has_room_for_a_reply_cut_at_the_cap(self, cap):
        assert svc._repair_limit(cap) > cap


class TestCallWithRepair:
    # `_json_object` runs a local json_repair pass first, so a reply cut off at the limit is
    # usually salvaged for free: what was completed before the cut survives and no second model
    # call is made. The model-based repair below is the fallback for a reply that is unreadable.
    UNREADABLE = "I am sorry, I cannot produce that."

    def test_the_default_chooses_no_limit(self):
        m = Recorder(['{"a": 1}'])
        assert svc.call_llm_json_with_repair(m, "s", "u") == {"a": 1}
        assert m.limits == [None]

    def test_an_explicit_limit_is_passed_through(self):
        m = Recorder(['{"a": 1}'])
        svc.call_llm_json_with_repair(m, "s", "u", max_tokens=3000)
        assert m.limits == [3000]

    def test_a_reply_cut_off_at_the_limit_is_salvaged_locally_without_a_second_call(self):
        m = Recorder(['{"items": [1, 2, 3'])
        out = svc.call_llm_json_with_repair(m, "s", "u", max_tokens=3000)
        assert out == {"items": [1, 2, 3]} and m.limits == [3000]

    def test_a_cut_off_list_keeps_the_complete_entries_before_the_cut(self):
        cut = '{"test_cases": [{"title": "a"}, {"title": "b"}, {"title": "c", "steps": ['
        out = svc.call_llm_json_with_repair(Recorder([cut]), "s", "u", max_tokens=3000)
        titles = [t["title"] for t in out["test_cases"]]
        assert titles[:2] == ["a", "b"]

    def test_an_unreadable_reply_is_repaired_by_the_model_with_headroom_not_the_same_limit(self):
        m = Recorder([self.UNREADABLE, '{"items": [1]}'])
        out = svc.call_llm_json_with_repair(m, "s", "u", max_tokens=3000)
        assert out == {"items": [1]}
        assert m.limits == [3000, 4006]

    def test_a_reply_that_never_becomes_valid_fails_after_both_attempts(self):
        m = Recorder([self.UNREADABLE] * 4)
        with patch.object(svc.time, "sleep"), pytest.raises(RuntimeError, match="failed after 2 attempts"):
            svc.call_llm_json_with_repair(m, "s", "u", max_tokens=3000)
        assert m.limits == [3000, 4006, 3000, 4006]

    def test_a_callers_own_default_still_means_no_repair_limit(self):
        m = Recorder([self.UNREADABLE, '{"x": [1]}'])
        svc.call_llm_json_with_repair(m, "s", "u")
        assert m.limits == [None, None]

    def test_end_to_end_through_the_real_client(self):
        # The first reply is unreadable; the repair call asks Ollama for more room.
        replies = [ollama_reply(self.UNREADABLE, done_reason="length"), ollama_reply('{"items": [1, 2]}')]
        with patch("httpx.post", side_effect=replies) as post:
            out = svc.call_llm_json_with_repair(LLM(provider="ollama", model="m"), "s", "u", max_tokens=3000)
        assert out == {"items": [1, 2]}
        assert [b["options"]["num_predict"] for b in sent(post)] == [3000, 4006]

    def test_end_to_end_a_cut_off_reply_costs_one_request_not_two(self):
        with patch("httpx.post", return_value=ollama_reply('{"items": [1, 2', done_reason="length")) as post:
            out = svc.call_llm_json_with_repair(LLM(provider="ollama", model="m"), "s", "u", max_tokens=3000)
        assert out == {"items": [1, 2]} and len(sent(post)) == 1


# ------------------------------------------------------------------ the limits the pipeline asks for
class TestPipelineLimitsAreExplicit:
    def test_the_designed_limits_are_literal_values_in_the_pipeline(self):
        src = open(os.path.join(APP_DIR, "testgen", "service.py")).read()
        for designed in ("max_tokens=4000", "max_tokens=3000", "max_tokens=6000", "max_tokens=10000"):
            assert designed in src, designed

    def test_no_provider_default_leaks_into_a_call_that_chose_none(self):
        # chat_json is the one place a default lived; it must not impose 4000 any more.
        import inspect
        assert inspect.signature(LLM.chat_json).parameters["max_tokens"].default is None
        assert inspect.signature(svc.call_llm_json_with_repair).parameters["max_tokens"].default is None
