"""LLM_TIMEOUT_SECONDS: one setting controls every LLM call timeout (#138, part of #130).

Unset, each call site keeps its built-in default (180/240/300 s in test generation,
300 s Ollama / 120 s hosted in LLM._raw_chat; botocore's own 60 s for Bedrock). Set, it
replaces all of them. An explicit timeout passed straight to _raw_chat still wins: the
eval runner's --call-timeout relies on that.
"""
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import llm as llm_module  # noqa: E402
import testgen.service as svc  # noqa: E402
from llm import LLM, _timeout_from_env, resolve_timeout  # noqa: E402
from tests.test_generation_pipeline import FakeEmbedder, FakeStore, SpyLLM  # noqa: E402


@pytest.fixture
def unset(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_TIMEOUT_SECONDS", None)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_TIMEOUT_SECONDS", 900.0)
    return 900.0


def _post_timeouts(llm, **kwargs):
    """Run one _raw_chat with httpx.post mocked; return the timeout of every POST."""
    response = MagicMock(status_code=200, text="")
    response.json.return_value = {
        "message": {"content": '{"ok": true}'},
        "content": [{"text": '{"ok": true}'}],
        "choices": [{"message": {"content": '{"ok": true}'}}],
    }
    with patch("httpx.post", return_value=response) as post:
        llm._raw_chat("system", "user", 8192, 0.1, 100, **kwargs)
    return [c.kwargs["timeout"] for c in post.call_args_list]


PROVIDERS = [
    (LLM(provider="ollama", model="qwen2.5:3b"), 300.0),
    (LLM(provider="anthropic", model="claude", api_key="k"), 120.0),
    (LLM(provider="openai", model="gpt-4o", api_key="k"), 120.0),
]


class TestParsing:
    @pytest.mark.parametrize("raw", [None, "", "   ", "abc", "0", "-5"])
    def test_blank_invalid_or_non_positive_means_unset(self, raw):
        assert _timeout_from_env(raw) is None

    @pytest.mark.parametrize("raw,expected", [("900", 900.0), (" 45.5 ", 45.5)])
    def test_positive_numbers_are_used(self, raw, expected):
        assert _timeout_from_env(raw) == expected

    @pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "1e400"])
    def test_non_finite_values_are_ignored_with_warning(self, raw):
        with patch.object(llm_module.log, "warning") as warning:
            assert _timeout_from_env(raw) is None

        warning.assert_called_once()
        assert "finite and greater than 0" in warning.call_args.args[0]

    @pytest.mark.parametrize("raw,expected", [("1800", "1800.0"), ("", "None")])
    def test_the_module_reads_the_environment_variable(self, raw, expected):
        # A fresh interpreter: reloading llm in-process would replace the LLM class that
        # other tests subclass.
        env = {**os.environ, "LLM_TIMEOUT_SECONDS": raw}
        out = subprocess.run(
            [sys.executable, "-c", "import llm; print(llm.LLM_TIMEOUT_SECONDS)"],
            cwd=APP_DIR, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert out == expected


class TestResolveTimeout:
    def test_unset_keeps_the_call_sites_default(self, unset):
        assert resolve_timeout(180) == 180

    def test_configured_value_replaces_the_default(self, configured):
        assert resolve_timeout(180) == configured


class TestRawChat:
    @pytest.mark.parametrize("client,default", PROVIDERS)
    def test_unset_keeps_the_built_in_fallbacks(self, unset, client, default):
        assert _post_timeouts(client) == [default]

    @pytest.mark.parametrize("client,default", PROVIDERS)
    def test_the_setting_is_honoured_by_every_provider(self, configured, client, default):
        assert _post_timeouts(client) == [configured]

    @pytest.mark.parametrize("client,default", PROVIDERS)
    def test_an_explicit_timeout_still_wins(self, configured, client, default):
        assert _post_timeouts(client, timeout_seconds=42) == [42]

    def test_the_temperature_retry_uses_the_same_timeout(self, configured):
        rejected = MagicMock(status_code=400, text="temperature not supported")
        ok = MagicMock(status_code=200, text="")
        ok.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
        client = LLM(provider="openai", model="temp-test-model", api_key="k")
        with patch("httpx.post", side_effect=[rejected, ok]) as post:
            client._raw_chat("system", "user", 8192, 0.1, 100)
        assert [c.kwargs["timeout"] for c in post.call_args_list] == [configured, configured]


def _bedrock_client_kwargs(**kwargs):
    """Run one Bedrock _raw_chat with boto3 mocked; return the bedrock-runtime client kwargs."""
    session = MagicMock()
    session.client.return_value.converse.return_value = {
        "output": {"message": {"content": [{"text": '{"ok": true}'}]}}, "usage": {}}
    client = LLM(provider="bedrock", model="anthropic.claude", region="us-east-1")
    with patch("boto3.session.Session", return_value=session):
        client._raw_chat("system", "user", 8192, 0.1, 100, **kwargs)
    return session.client.call_args.kwargs


class TestPing:
    def test_ping_uses_the_configured_global_timeout(self, monkeypatch):
        # Settings Save/Test call LLM.ping(); it intentionally inherits the
        # configured timeout, which is documented for unreachable endpoints.
        monkeypatch.setattr(llm_module, "LLM_TIMEOUT_SECONDS", 1800.0)
        client = LLM(provider="openai", model="gpt-4o", api_key="k")
        response = MagicMock(status_code=200, text="")
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}],
        }

        with patch("httpx.post", return_value=response) as post:
            result = client.ping()

        assert result["ok"] is True
        assert post.call_args.kwargs["timeout"] == 1800.0

    def test_ollama_ping_uses_the_configured_global_timeout(self, monkeypatch):
        monkeypatch.setattr(llm_module, "LLM_TIMEOUT_SECONDS", 1800.0)
        client = LLM(provider="ollama", model="qwen2.5:3b")
        response = MagicMock(status_code=200, text="")
        response.json.return_value = {
            "message": {"content": '{"ok": true}'},
        }
        tags = MagicMock(status_code=200)
        tags.json.return_value = {"models": [{"name": "qwen2.5:3b"}]}

        with patch("httpx.post", return_value=response) as post, patch(
            "httpx.get", return_value=tags
        ):
            result = client.ping()

        assert result["ok"] is True
        assert result["provider"] == "ollama"
        assert post.call_args.kwargs["timeout"] == 1800.0


class TestBedrock:
    def test_unset_keeps_the_sdk_defaults(self, unset):
        assert "config" not in _bedrock_client_kwargs()

    def test_unset_still_ignores_the_per_call_timeouts(self, unset):
        assert "config" not in _bedrock_client_kwargs(timeout_seconds=180)

    def test_the_setting_sets_connect_and_read_timeouts(self, configured):
        config = _bedrock_client_kwargs()["config"]
        assert (config.connect_timeout, config.read_timeout) == (configured, configured)

    def test_an_explicit_timeout_still_wins_once_configured(self, configured):
        config = _bedrock_client_kwargs(timeout_seconds=42)["config"]
        assert (config.connect_timeout, config.read_timeout) == (42, 42)


class _RecordingLLM:
    def __init__(self):
        self.timeouts = []

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
        return '{"ok": true}'


class TestCallLlmJsonWithRepair:
    def test_default_is_300_when_unset(self, unset):
        fake = _RecordingLLM()
        svc.call_llm_json_with_repair(fake, "system", "user")
        assert fake.timeouts == [300]

    def test_default_follows_the_setting(self, configured):
        fake = _RecordingLLM()
        svc.call_llm_json_with_repair(fake, "system", "user")
        assert fake.timeouts == [configured]


class TimeoutSpyLLM(SpyLLM):
    def __init__(self):
        super().__init__()
        self.timeouts = []

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
        return super()._raw_chat(system, user, num_ctx, temperature, max_tokens, timeout_seconds)


def _run_pipeline():
    spy = TimeoutSpyLLM()
    svc.generate_fresh_testcases_pipeline(
        FakeStore(),
        spy,
        FakeEmbedder(),
        {
            "feature_id": "feature-1",
            "total": 4,
            "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
        },
    )
    assert spy.timeouts, "the pipeline made no LLM calls"
    return spy.timeouts


class TestGenerationPipeline:
    def test_every_generation_call_uses_the_setting(self, monkeypatch):
        monkeypatch.setattr(llm_module, "LLM_TIMEOUT_SECONDS", 1234.0)
        assert set(_run_pipeline()) == {1234.0}

    def test_unset_keeps_the_built_in_per_call_values(self, unset):
        assert set(_run_pipeline()) <= {180, 240, 300}
