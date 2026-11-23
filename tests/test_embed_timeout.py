"""Embedding calls have a configurable timeout and fail with a readable error (#249 follow-up).

Reported by a tester on a CPU-only machine: "the first embedding call takes about 4 minutes
on this box, but the app times out after 2 minutes, so POST /api/features returns 500 before
any job starts". The cause was in our code:

  * every embedding call had a fixed `timeout=120.0` that no setting changed. The docs and the
    CPU notice say to raise LLM_TIMEOUT_SECONDS on a slow machine, and that setting did not
    reach embeddings, so the advice could not work;
  * a timeout was not caught anywhere, so creating a feature answered a bare HTTP 500.

What is pinned here:
  * EMBED_TIMEOUT_SECONDS, else LLM_TIMEOUT_SECONDS, else the old 120 s (Ollama, OpenAI-style
    providers and Voyage; Bedrock keeps botocore's own timeout)
  * an invalid value is ignored with a warning that names the right variable
  * a timeout becomes EmbeddingTimeout, whose message names the setting, and the API answers
    it with HTTP 504 and that message; other failures are not turned into it
  * a real HTTP server that answers slowly: cut off at the limit, answered when the limit is
    raised
"""
import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from unittest.mock import patch

import httpx
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import embeddings  # noqa: E402
from core.exceptions import embedding_timeout_handler  # noqa: E402
from embeddings import DEFAULT_EMBED_TIMEOUT, Embedder, EmbeddingTimeout, embed_timeout  # noqa: E402
import llm as llm_module  # noqa: E402
from llm import _timeout_from_env  # noqa: E402


@pytest.fixture(autouse=True)
def no_timeout_settings(monkeypatch):
    monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", None)
    monkeypatch.setattr(embeddings, "LLM_TIMEOUT_SECONDS", None)


# ------------------------------------------------------------------ which timeout
class TestWhichTimeout:
    def test_the_old_default_when_nothing_is_set(self):
        assert embed_timeout() == DEFAULT_EMBED_TIMEOUT == 120.0

    def test_llm_timeout_covers_embeddings_so_the_documented_advice_works(self, monkeypatch):
        monkeypatch.setattr(embeddings, "LLM_TIMEOUT_SECONDS", 1800.0)
        assert embed_timeout() == 1800.0

    def test_the_embedding_setting_wins_over_the_llm_one(self, monkeypatch):
        monkeypatch.setattr(embeddings, "LLM_TIMEOUT_SECONDS", 1800.0)
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 600.0)
        assert embed_timeout() == 600.0

    def test_the_embedding_setting_alone(self, monkeypatch):
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 45.5)
        assert embed_timeout() == 45.5


class TestParsing:
    @pytest.mark.parametrize("raw,expected", [("600", 600.0), (" 90.5 ", 90.5), ("", None), (None, None)])
    def test_valid_and_blank_values(self, raw, expected):
        assert _timeout_from_env(raw, "EMBED_TIMEOUT_SECONDS") == expected

    @staticmethod
    def warning_text(call):
        with patch.object(llm_module.log, "warning") as warning:
            assert call() is None
        (args, _), = warning.call_args_list
        return args[0] % args[1:]

    @pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", "inf", "1e400"])
    def test_invalid_values_are_ignored_and_the_warning_names_the_variable(self, raw):
        text = self.warning_text(lambda: _timeout_from_env(raw, "EMBED_TIMEOUT_SECONDS"))
        assert "EMBED_TIMEOUT_SECONDS" in text and "LLM_TIMEOUT_SECONDS" not in text

    def test_the_llm_setting_still_names_itself(self):
        assert "LLM_TIMEOUT_SECONDS" in self.warning_text(lambda: _timeout_from_env("abc"))


# ------------------------------------------------------------------ every provider uses it
class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


PROVIDERS = [
    ("ollama", {"embedding": [0.1, 0.2]}),
    ("openai", {"data": [{"embedding": [0.1, 0.2]}], "usage": {}}),
    ("gemini", {"data": [{"embedding": [0.1, 0.2]}], "usage": {}}),
    ("voyage", {"data": [{"embedding": [0.1, 0.2]}], "usage": {}}),
]


class TestEveryProviderUsesTheTimeout:
    @pytest.mark.parametrize("provider,payload", PROVIDERS)
    def test_the_default(self, monkeypatch, provider, payload):
        seen = {}
        monkeypatch.setattr(embeddings.httpx, "post", lambda url, **kw: seen.update(kw) or FakeResponse(payload))
        Embedder(provider=provider, model="m", api_key="k").embed("text")
        assert seen["timeout"] == 120.0

    @pytest.mark.parametrize("provider,payload", PROVIDERS)
    def test_a_configured_value(self, monkeypatch, provider, payload):
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 900.0)
        seen = {}
        monkeypatch.setattr(embeddings.httpx, "post", lambda url, **kw: seen.update(kw) or FakeResponse(payload))
        Embedder(provider=provider, model="m", api_key="k").embed("text")
        assert seen["timeout"] == 900.0

    def test_the_request_itself_is_unchanged(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(embeddings.httpx, "post",
                            lambda url, **kw: seen.update({"url": url, **kw}) or FakeResponse({"embedding": [1.0]}))
        Embedder(provider="ollama", model="nomic-embed-text", ollama_url="http://h:11434").embed("hello")
        assert seen["url"] == "http://h:11434/api/embeddings"
        assert seen["json"] == {"model": "nomic-embed-text", "prompt": "search_document: hello"}


# ------------------------------------------------------------------ the error
class TestTheError:
    def raising(self, exc):
        def post(url, **kw):
            raise exc
        return post

    @pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow"), httpx.PoolTimeout("slow")])
    def test_a_timeout_becomes_an_embedding_timeout_that_names_the_setting(self, monkeypatch, exc):
        monkeypatch.setattr(embeddings.httpx, "post", self.raising(exc))
        with pytest.raises(EmbeddingTimeout) as caught:
            Embedder(provider="ollama", model="nomic-embed-text").embed("text")
        message = str(caught.value)
        assert "nomic-embed-text" in message and "120 s" in message
        assert "EMBED_TIMEOUT_SECONDS" in message and "LLM_TIMEOUT_SECONDS" in message
        assert "Configuration → Embeddings" in message
        assert caught.value.__cause__ is exc

    def test_the_message_shows_the_limit_that_applied(self, monkeypatch):
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 7.5)
        monkeypatch.setattr(embeddings.httpx, "post", self.raising(httpx.ReadTimeout("slow")))
        with pytest.raises(EmbeddingTimeout, match=r"within 7\.5 s"):
            Embedder(provider="openai", model="m", api_key="k").embed("text")

    def test_it_is_a_runtime_error_so_existing_handlers_still_catch_it(self):
        assert issubclass(EmbeddingTimeout, RuntimeError)

    def test_a_connection_failure_is_not_turned_into_a_timeout_message(self, monkeypatch):
        monkeypatch.setattr(embeddings.httpx, "post", self.raising(httpx.ConnectError("refused")))
        with pytest.raises(httpx.ConnectError):
            Embedder(provider="ollama", model="m").embed("text")

    def test_the_missing_model_message_is_unchanged(self, monkeypatch):
        class NotFound(FakeResponse):
            status_code = 404

        monkeypatch.setattr(embeddings.httpx, "post", lambda url, **kw: NotFound({}))
        with pytest.raises(RuntimeError, match="isn't downloaded in Ollama yet"):
            Embedder(provider="ollama", model="nomic-embed-text").embed("text")


class TestTheApiAnswer:
    def test_the_handler_answers_504_with_the_message(self):
        response = asyncio.run(embedding_timeout_handler(None, EmbeddingTimeout("raise EMBED_TIMEOUT_SECONDS")))
        assert response.status_code == 504
        assert json.loads(response.body) == {"detail": "raise EMBED_TIMEOUT_SECONDS"}

    def test_the_handler_is_registered_on_the_app(self):
        import main

        assert main.app.exception_handlers[EmbeddingTimeout] is embedding_timeout_handler


# ------------------------------------------------------------------ a real, slow HTTP server
class SlowOllama(BaseHTTPRequestHandler):
    delay = 0.6

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        time.sleep(self.delay)
        body = json.dumps({"embedding": [0.1, 0.2, 0.3], "prompt_eval_count": 4}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def slow_ollama():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


class TestAgainstARealSlowServer:
    def test_cut_off_at_the_limit_with_a_readable_error(self, monkeypatch, slow_ollama):
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 0.2)
        started = time.time()
        with pytest.raises(EmbeddingTimeout, match="EMBED_TIMEOUT_SECONDS"):
            Embedder(provider="ollama", model="nomic-embed-text", ollama_url=slow_ollama).embed("text")
        assert time.time() - started < 0.55          # it did not wait for the 0.6 s answer

    def test_answered_when_the_limit_is_raised(self, monkeypatch, slow_ollama):
        monkeypatch.setattr(embeddings, "EMBED_TIMEOUT_SECONDS", 5.0)
        assert Embedder(provider="ollama", model="m", ollama_url=slow_ollama).embed("text") == [0.1, 0.2, 0.3]

    def test_the_llm_setting_alone_is_enough(self, monkeypatch, slow_ollama):
        # the advice in the docs and in the CPU notice: raise LLM_TIMEOUT_SECONDS
        monkeypatch.setattr(embeddings, "LLM_TIMEOUT_SECONDS", 5.0)
        assert Embedder(provider="ollama", model="m", ollama_url=slow_ollama).embed("text") == [0.1, 0.2, 0.3]
