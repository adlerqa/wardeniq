"""Warn before a long generation when a local model runs on CPU (#249).

Reviewers on CPU-only machines reported 18 to 60 minute runs with no warning beforehand.
`LLM.accelerator()` asks Ollama where the loaded model runs, `usage.cpu_generation_warning()`
turns that into text, and the pre-run estimate route returns both so the Generate page can
show it.

The answer is always a measurement, never a guess from the URL: the "bundled" Ollama URL can
point at the CPU-only container or at a native Ollama on the host (often a GPU), and a guess
there showed a false CPU warning on a Mac that runs Ollama natively. When nothing is loaded
yet (a first run) the small embedding model is loaded to make Ollama report where it runs.

These tests pin: the three measured outcomes, the first-run probe, that a GPU server is never
reported as CPU, that anything unreachable or unreadable claims nothing (so there is never a
false warning), that hosted providers are untouched, and that the route never breaks because
the probe failed.
"""
import types

import auth
import main
import pytest
from fastapi.testclient import TestClient

import llm as llm_mod
import usage
from core import state as core_state
from llm import LLM

GB = 1024 ** 3
URL = "http://ollama:11434"


class Resp:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code = ({} if payload is None else payload), status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def entry(name, size, vram):
    return {"name": name, "size": size, "size_vram": vram}


def ollama(url=URL, **kw):
    return LLM(provider="ollama", model="qwen2.5:3b", ollama_url=url, **kw)


@pytest.fixture
def server(monkeypatch):
    """A fake Ollama behind httpx inside llm.py.

    `loaded` is what /api/ps lists now. Embedding with the probe model loads it: `after_embed`
    becomes the new `loaded` list (None = loading changes nothing). `payload` replaces every
    /api/ps answer, `first_payload` only the first one. `ps_error` fails every /api/ps call;
    `ps_error_on_call=N` fails only the Nth. `gets` and `posts` record every request as
    (url, kwargs).
    """
    s = types.SimpleNamespace(loaded=[], payload=None, first_payload=None, after_embed=None,
                              ps_error=None, ps_error_on_call=None, embed_error=None,
                              gets=[], posts=[])

    def fake_get(url, **kw):
        s.gets.append((url, kw))
        assert url.endswith("/api/ps"), url
        if s.ps_error:
            raise s.ps_error
        if s.ps_error_on_call == len(s.gets):
            raise ConnectionError("went away")
        if s.first_payload is not None and len(s.gets) == 1:
            return Resp(s.first_payload)            # only the first read; later reads are normal
        return Resp(s.payload if s.payload is not None else {"models": list(s.loaded)})

    def fake_post(url, **kw):
        s.posts.append((url, kw))
        assert url.endswith("/api/embed"), url
        if s.embed_error:
            raise s.embed_error
        if s.after_embed is not None:
            s.loaded = list(s.after_embed)
        return Resp({"embeddings": [[0.1]]})

    monkeypatch.setattr(llm_mod.httpx, "get", fake_get)
    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    return s


# ------------------------------------------------------------------ models already loaded
class TestMeasuredFromLoadedModels:
    def test_a_model_held_entirely_in_ram_is_cpu(self, server):
        server.loaded = [entry("qwen2.5:3b", 3 * GB, 0)]
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "cpu"}

    def test_a_model_held_entirely_in_vram_is_gpu(self, server):
        server.loaded = [entry("qwen2.5:3b", 3 * GB, 3 * GB)]
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "gpu"}

    def test_vram_a_hair_short_of_the_size_still_counts_as_gpu(self, server):
        server.loaded = [entry("qwen2.5:3b", 1000, 990)]
        assert ollama().accelerator()["accelerator"] == "gpu"

    def test_a_model_split_between_gpu_and_cpu_is_mixed(self, server):
        server.loaded = [entry("qwen2.5:7b", 6 * GB, 2 * GB)]
        assert ollama().accelerator()["accelerator"] == "mixed"

    def test_every_loaded_model_counts_not_only_the_generation_model(self, server):
        server.loaded = [entry("nomic-embed-text", GB // 4, 0)]
        assert ollama().accelerator()["accelerator"] == "cpu"

    def test_models_are_summed_before_deciding(self, server):
        server.loaded = [entry("qwen2.5:3b", 3 * GB, 3 * GB), entry("nomic-embed-text", GB // 4, 0)]
        assert ollama().accelerator()["accelerator"] == "mixed"

    def test_nothing_is_loaded_for_the_probe_when_a_model_is_already_there(self, server):
        server.loaded = [entry("qwen2.5:3b", 3 * GB, 0)]
        ollama().accelerator("nomic-embed-text")
        assert server.posts == []

    def test_the_url_is_never_used_to_decide(self, server):
        # Any URL, including the bundled-container one, says nothing about the hardware.
        server.loaded = [entry("qwen2.5:3b", 3 * GB, 3 * GB)]
        for url in (URL, "http://host.docker.internal:11434", "http://10.0.0.5:11434"):
            assert ollama(url).accelerator()["accelerator"] == "gpu"


# ------------------------------------------------------------------ first run: nothing loaded
class TestFirstRunProbe:
    def test_nothing_loaded_loads_the_probe_model_then_measures_cpu(self, server):
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "cpu"}
        (url, kw), = server.posts
        assert url == URL + "/api/embed"
        assert kw["json"] == {"model": "nomic-embed-text", "input": "x"}

    def test_nothing_loaded_then_measures_gpu(self, server):
        server.after_embed = [entry("nomic-embed-text", GB // 4, GB // 4)]
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "gpu"}

    def test_a_gpu_server_with_nothing_loaded_is_never_called_cpu(self, server):
        # The regression this design exists for: a Mac that runs Ollama natively has its
        # "bundled" URL pointing at the host. Nothing loaded must not mean CPU.
        server.after_embed = [entry("nomic-embed-text", GB // 4, GB // 4)]
        got = ollama("http://host.docker.internal:11434").accelerator("nomic-embed-text")
        assert got == {"accelerator": "gpu"}

    def test_the_probe_is_asked_exactly_once(self, server):
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        ollama().accelerator("nomic-embed-text")
        assert len(server.posts) == 1 and len(server.gets) == 2     # ps, load, ps

    def test_nothing_loaded_and_no_probe_model_claims_nothing(self, server):
        assert ollama().accelerator() == {"accelerator": "unknown"}
        assert server.posts == []

    def test_a_probe_that_loads_nothing_claims_nothing(self, server):
        server.after_embed = []         # the server unloaded it straight away
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}

    @pytest.mark.parametrize("error", [ConnectionError("refused"), TimeoutError("slow"),
                                       RuntimeError("HTTP 404 model not found")])
    def test_a_probe_that_fails_claims_nothing(self, server, error):
        server.embed_error = error
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}

    def test_ps_unreadable_after_the_probe_claims_nothing(self, server):
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        server.ps_error_on_call = 2         # the read after the probe fails
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}

    def test_the_probe_request_is_bounded_and_authenticated(self, server):
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        LLM(provider="ollama", model="m", api_key="tok", ollama_url=URL).accelerator("nomic-embed-text")
        _, kw = server.posts[0]
        assert kw["timeout"] <= 20 and kw["headers"] == {"Authorization": "Bearer tok"}


# ------------------------------------------------------------------ never claim what we do not know
class TestUnknown:
    def test_an_unreachable_ollama_claims_nothing_and_makes_no_probe(self, server):
        server.ps_error = ConnectionError("refused")
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}
        assert server.posts == []

    def test_an_http_error_from_ps_claims_nothing(self, server):
        server.ps_error = RuntimeError("HTTP 500")
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}
        assert server.posts == []

    @pytest.mark.parametrize("payload", [[], "oops", 3, {"models": ["junk"]}, {"models": [1, None]}])
    def test_an_answer_we_cannot_read_claims_nothing_and_makes_no_probe(self, server, payload):
        server.payload = payload
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "unknown"}
        assert server.posts == []        # unreadable entries are not "nothing loaded"

    @pytest.mark.parametrize("payload", [{"models": None}, {"models": []}, {}])
    def test_an_empty_or_missing_model_list_means_nothing_is_loaded(self, server, payload):
        server.first_payload = payload
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        assert ollama().accelerator("nomic-embed-text") == {"accelerator": "cpu"}
        assert len(server.posts) == 1

    def test_a_zero_size_claims_nothing(self, server):
        server.loaded = [entry("qwen2.5:3b", 0, 0)]
        assert ollama().accelerator()["accelerator"] == "unknown"

    def test_a_non_numeric_size_claims_nothing_and_does_not_raise(self, server):
        server.loaded = [{"name": "m", "size": "big", "size_vram": 0}]
        assert ollama().accelerator()["accelerator"] == "unknown"

    def test_ps_is_asked_with_a_short_timeout_and_the_bearer_token(self, server):
        server.loaded = [entry("m", GB, 0)]
        LLM(provider="ollama", model="m", api_key="tok", ollama_url="http://10.0.0.5:11434").accelerator()
        url, kw = server.gets[0]
        assert url == "http://10.0.0.5:11434/api/ps" and kw["timeout"] <= 3
        assert kw["headers"] == {"Authorization": "Bearer tok"}


class TestHostedProviders:
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "bedrock", "groq", "gemini"])
    def test_a_hosted_provider_has_no_answer_and_makes_no_request(self, server, provider):
        m = LLM(provider=provider, model="m", api_key="k")
        assert m.accelerator("nomic-embed-text") == {"accelerator": None}
        assert server.gets == [] and server.posts == []


# ------------------------------------------------------------------ the warning text
class TestCpuGenerationWarning:
    def test_cpu_gets_a_warning_that_names_the_cost_and_the_way_out(self):
        w = usage.cpu_generation_warning("cpu")
        assert "CPU" in w and "20 minutes" in w and "over an hour" in w
        assert "hosted provider" in w and "GPU" in w
        assert "LLM_TIMEOUT_SECONDS" in w

    def test_it_says_the_bundled_container_never_uses_a_gpu_on_any_os(self):
        # The bundled compose file gives the Ollama container no GPU on any operating system
        # (a Windows machine with an AMD GPU sat idle, #306), so the hint is not Mac-only.
        w = usage.cpu_generation_warning("cpu")
        assert "bundled Ollama container" in w and "does not use a GPU" in w
        assert "on any operating system" in w
        assert "On a Mac" not in w and "Docker cannot" not in w

    def test_it_says_how_to_get_a_gpu_and_point_the_app_at_it(self):
        w = usage.cpu_generation_warning("cpu")
        assert "natively on a machine with a GPU" in w and "OLLAMA_URL" in w

    def test_it_stays_conditional_because_the_url_does_not_say_which_ollama_it_is(self):
        # The app cannot tell the bundled container from a native CPU-only Ollama, so the
        # container claim must be an "if", not a statement about the user's setup.
        assert "If this is the bundled Ollama container" in usage.cpu_generation_warning("cpu")

    def test_mixed_gets_a_different_warning(self):
        w = usage.cpu_generation_warning("mixed")
        assert "partly fits" in w and w != usage.cpu_generation_warning("cpu")

    @pytest.mark.parametrize("value", ["gpu", "unknown", None, "", "tpu"])
    def test_everything_else_gets_no_warning(self, value):
        assert usage.cpu_generation_warning(value) is None

    def test_the_text_makes_no_minute_claim_derived_from_the_token_estimate(self):
        # The estimate (~4k output tokens for 16 cases) understates a real run, so a figure
        # computed from it would promise a much shorter run than people see.
        w = usage.cpu_generation_warning("cpu")
        assert "tokens" not in w and "second" not in w


# ------------------------------------------------------------------ the route
SESSION = auth.SESSION_COOKIE
USER = {"id": "u1", "email": "u@example.com", "role": "editor", "active": True,
        "session_version": 0, "all_projects": True}
client = TestClient(main.app)
main.store.add_audit = lambda *a, **kw: True


@pytest.fixture
def route(monkeypatch):
    """The estimate route with a signed-in user, ollama settings and a fakeable probe."""
    monkeypatch.setattr(main.store, "get_user", lambda uid: USER)
    monkeypatch.setattr(main.store, "get_settings",
                        lambda: {"llm_provider": "ollama", "llm_model": "qwen2.5:3b"})
    monkeypatch.setattr(core_state, "embedder",
                        types.SimpleNamespace(provider="ollama", model="nomic-embed-text"))
    state = types.SimpleNamespace(llm=None, probes=[])
    monkeypatch.setattr("api.routes.jobs_usage.current_llm", lambda: state.llm)

    def post(body=None):
        return client.post("/api/usage/estimate", json=body or {"text_length": 4000},
                           cookies={SESSION: auth.sign_session("u1", 0)})

    def local(accel):
        def accelerator(probe_model=""):
            state.probes.append(probe_model)
            return {"accelerator": accel}
        return types.SimpleNamespace(provider="ollama", accelerator=accelerator)

    state.post, state.local = post, local
    return state


class TestEstimateRoute:
    def test_a_cpu_model_gets_the_warning_and_the_old_fields_are_unchanged(self, route):
        route.llm = route.local("cpu")
        body = route.post().json()
        assert body["accelerator"] == "cpu"
        assert body["warning"] == usage.cpu_generation_warning("cpu")
        assert body["low"] is None and body["high"] is None and "local" in body["note"].lower()
        assert body["completion_tokens_mid"] > 0

    def test_the_embedding_model_is_the_probe(self, route):
        route.llm = route.local("cpu")
        route.post()
        assert route.probes == ["nomic-embed-text"]

    def test_no_probe_when_the_embeddings_are_not_from_ollama(self, route, monkeypatch):
        monkeypatch.setattr(core_state, "embedder",
                            types.SimpleNamespace(provider="openai", model="text-embedding-3-small"))
        route.llm = route.local("cpu")
        route.post()
        assert route.probes == [""]

    def test_no_probe_when_there_is_no_embedder_yet(self, route, monkeypatch):
        monkeypatch.setattr(core_state, "embedder", None)
        route.llm = route.local("cpu")
        assert route.post().status_code == 200 and route.probes == [""]

    def test_a_gpu_model_gets_no_warning(self, route):
        route.llm = route.local("gpu")
        body = route.post().json()
        assert body["accelerator"] == "gpu" and "warning" not in body

    def test_an_unknown_answer_gets_no_warning(self, route):
        route.llm = route.local("unknown")
        body = route.post().json()
        assert body["accelerator"] == "unknown" and "warning" not in body

    def test_a_mixed_model_gets_the_mixed_warning(self, route):
        route.llm = route.local("mixed")
        assert route.post().json()["warning"] == usage.cpu_generation_warning("mixed")

    def test_the_warning_does_not_need_a_document(self, route):
        route.llm = route.local("cpu")
        body = route.post({"text_length": 0}).json()
        assert body["warning"] and body["completion_tokens_mid"] >= 0

    def test_a_hosted_provider_is_left_exactly_as_before_and_is_never_probed(self, route, monkeypatch):
        monkeypatch.setattr(main.store, "get_settings",
                            lambda: {"llm_provider": "openai", "llm_model": "gpt-4o"})
        route.llm = types.SimpleNamespace(provider="openai",
                                          accelerator=lambda **k: pytest.fail("probed"))
        body = route.post({"text_length": 4000, "total": 16}).json()
        assert "accelerator" not in body and "warning" not in body
        assert body["low"] is not None and body["currency"] == "USD"

    def test_a_probe_that_raises_never_breaks_the_estimate(self, route):
        def boom(probe_model=""):
            raise RuntimeError("probe exploded")

        route.llm = types.SimpleNamespace(provider="ollama", accelerator=boom)
        r = route.post()
        assert r.status_code == 200
        body = r.json()
        assert "warning" not in body and "accelerator" not in body and "note" in body

    def test_building_the_client_failing_never_breaks_the_estimate(self, route, monkeypatch):
        def boom():
            raise RuntimeError("settings unreadable")

        monkeypatch.setattr("api.routes.jobs_usage.current_llm", boom)
        r = route.post()
        assert r.status_code == 200 and "warning" not in r.json()

    def test_it_still_requires_a_signed_in_user(self, route):
        route.llm = route.local("cpu")
        assert client.post("/api/usage/estimate", json={"text_length": 1}).status_code == 401

    def test_end_to_end_cpu_first_run_through_the_real_client(self, route, server):
        # Nothing loaded yet; loading the embedding model shows the server is on CPU.
        route.llm = LLM(provider="ollama", model="qwen2.5:3b", ollama_url=URL)
        server.after_embed = [entry("nomic-embed-text", GB // 4, 0)]
        body = route.post().json()
        assert body["accelerator"] == "cpu"
        assert body["warning"] == usage.cpu_generation_warning("cpu")
        assert server.posts[0][1]["json"]["model"] == "nomic-embed-text"

    def test_end_to_end_gpu_first_run_gets_no_warning(self, route, server):
        # The user's own setup: a native Ollama on the Mac's GPU, nothing loaded yet.
        route.llm = LLM(provider="ollama", model="qwen2.5:3b",
                        ollama_url="http://host.docker.internal:11434")
        server.after_embed = [entry("nomic-embed-text", GB // 4, GB // 4)]
        body = route.post().json()
        assert body["accelerator"] == "gpu" and "warning" not in body
