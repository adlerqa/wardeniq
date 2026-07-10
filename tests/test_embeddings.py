"""Tests for the pluggable Embedder request shaping + dimension probe (no network)."""
import embeddings
from embeddings import Embedder


class FakeResp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


def patch_post(monkeypatch, payload):
    calls = {}
    def fake_post(url, **kw):
        calls["url"] = url
        calls["json"] = kw.get("json")
        calls["headers"] = kw.get("headers") or {}
        return FakeResp(payload)
    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    return calls


class TestOllama:
    def test_uses_task_prefix_and_returns_vector(self, monkeypatch):
        calls = patch_post(monkeypatch, {"embedding": [0.1, 0.2, 0.3]})
        e = Embedder(provider="ollama", model="nomic-embed-text", ollama_url="http://x:11434")
        v = e.embed("hello", task="query")
        assert v == [0.1, 0.2, 0.3]
        assert calls["url"].endswith("/api/embeddings")
        assert calls["json"]["prompt"].startswith("search_query: ")
        assert calls["json"]["model"] == "nomic-embed-text"


class TestOpenAI:
    def test_posts_v1_embeddings_with_dimensions_and_bearer(self, monkeypatch):
        calls = patch_post(monkeypatch, {"data": [{"embedding": [1, 2, 3, 4]}],
                                         "usage": {"prompt_tokens": 5}})
        e = Embedder(provider="openai", model="text-embedding-3-small", dim=1536, api_key="sk-x")
        v = e.embed("doc text")
        assert v == [1, 2, 3, 4]
        assert calls["url"] == "https://api.openai.com/v1/embeddings"
        assert calls["json"]["input"] == "doc text"
        assert calls["json"]["dimensions"] == 1536          # output-dim requested
        assert calls["headers"]["Authorization"] == "Bearer sk-x"


class TestGemini:
    def test_uses_openai_compat_embeddings_path(self, monkeypatch):
        calls = patch_post(monkeypatch, {"data": [{"embedding": [0.5] * 8}], "usage": {}})
        e = Embedder(provider="gemini", model="gemini-embedding-001", dim=768, api_key="g-key")
        v = e.embed("x")
        assert len(v) == 8
        # gemini base already includes /v1beta/openai → path is /embeddings
        assert calls["url"].endswith("/v1beta/openai/embeddings")


class TestVoyage:
    def test_input_type_and_list_input(self, monkeypatch):
        calls = patch_post(monkeypatch, {"data": [{"embedding": [9, 8, 7]}],
                                         "usage": {"total_tokens": 3}})
        e = Embedder(provider="voyage", model="voyage-3", api_key="v-key")
        v = e.embed("q", task="query")
        assert v == [9, 8, 7]
        assert calls["url"] == "https://api.voyageai.com/v1/embeddings"
        assert calls["json"]["input"] == ["q"]
        assert calls["json"]["input_type"] == "query"


class TestNativeDimension:
    def test_no_dimensions_forced_when_dim_unset(self, monkeypatch):
        # switch-time probe builds the client WITHOUT a dim → must NOT send `dimensions`,
        # so the model returns its NATIVE size (e.g. gemini-embedding-001 → 3072), not a
        # silently-downgraded default.
        calls = patch_post(monkeypatch, {"data": [{"embedding": [0.0] * 3072}], "usage": {}})
        e = Embedder(provider="gemini", model="gemini-embedding-001", api_key="k")  # no dim
        assert e.dim is None
        assert e.probe_dim() == 3072                     # native dimension measured
        assert "dimensions" not in (calls["json"] or {})  # nothing forced

    def test_dimensions_forced_when_dim_set(self, monkeypatch):
        calls = patch_post(monkeypatch, {"data": [{"embedding": [0.0] * 768}], "usage": {}})
        e = Embedder(provider="gemini", model="gemini-embedding-001", dim=768, api_key="k")
        e.embed("x")
        assert calls["json"]["dimensions"] == 768         # explicit request honored


class TestProbe:
    def test_probe_dim_measures_actual_length(self, monkeypatch):
        patch_post(monkeypatch, {"data": [{"embedding": [0.0] * 1024}], "usage": {}})
        e = Embedder(provider="voyage", model="voyage-3", api_key="k")
        assert e.probe_dim() == 1024

    def test_ok_requires_key_for_hosted(self):
        assert Embedder(provider="ollama").ok() is True
        assert Embedder(provider="openai", model="m").ok() is False
        assert Embedder(provider="openai", model="m", api_key="k").ok() is True
