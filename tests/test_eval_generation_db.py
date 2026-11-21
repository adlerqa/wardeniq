"""The generation evaluation runner against the REAL generation pipeline and a REAL MongoDB,
with a stubbed model (issue #43).

The unit tests in tests/test_eval_generation.py use a fake pipeline. This file closes that gap:
nothing in the pipeline is mocked, only the network call to the model, so a change to the
pipeline's output shape that would break the runner is caught without needing Ollama.

Requires MONGO_TEST_URI like the other dbintegration tests; skipped when no MongoDB is
reachable. Each run uses its own wardeniq_eval_* database, which the runner drops.
"""
import importlib.util
import os
from pathlib import Path

import pytest
from pymongo import MongoClient
from store import Store

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _require_mongo():
    """Skip this module's tests when no MongoDB is reachable.

    This runs when the module's tests are about to run, not at import time, so a run that
    deselects the dbintegration marker neither waits out the 1.5 s server selection timeout
    nor opens a MongoClient, and the client used for the check is always closed.
    """
    client = None
    try:
        client = MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
    except Exception:  # noqa: BLE001
        pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
                    "db-integration tests)")
    finally:
        if client is not None:
            client.close()


def _database_names():
    client = MongoClient(MONGO_TEST_URI)
    try:
        return set(client.list_database_names())
    finally:
        client.close()


@pytest.fixture()
def store_factory():
    """A Store per throwaway database, with every client closed when the test ends."""
    stores = []

    def make(name):
        store = Store(MONGO_TEST_URI, name, 8)
        stores.append(store)
        return store

    try:
        yield make
    finally:
        for store in stores:
            store.client.close()


def _load_runner():
    spec = importlib.util.spec_from_file_location("eval_generation_runner_db",
                                                  ROOT / "scripts" / "eval_generation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class StubEmbedder:
    def embed(self, text, task="document"):
        n = len(text)
        return [float(n % 7 + 1), float(n % 5 + 1), 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]


@pytest.fixture
def stub_model(monkeypatch):
    """Every model call returns the same minimal non-empty JSON object (the pipeline rejects
    an empty one); nothing touches the network, and the model produces no test cases."""
    monkeypatch.setattr(runner, "LIVE_STATE_MODULES", ())
    monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat",
                        lambda self, *a, **k: '{"stub": true}')


def test_the_real_pipeline_output_becomes_a_result_and_the_database_is_dropped(stub_model,
                                                                              store_factory):
    cfg = runner.EvalConfig(model="stub-model", mongo_uri=MONGO_TEST_URI)
    corpus = (ROOT / "examples" / "sample-prd.md").read_text(encoding="utf-8")
    original_gap_check = runner.svc._requirement_gaps

    run = runner.run_repeat(
        cfg, 1, corpus,
        store_factory=store_factory,
        llm_factory=lambda: runner.RecordingLLM(provider="ollama", model="stub-model",
                                                ollama_url="http://127.0.0.1:1"),
        embedder=StubEmbedder())

    assert run["ok"] is True, run["error"]
    # The pipeline's own accounting block, normalised by the runner.
    assert run["filter"]["available"] is True
    assert run["filter"]["generated"] >= 0
    assert set(run["filter"]["reasons"]) >= {"exemplar-copy", "no-source-grounding", "duplicate"}
    # Real pipeline progress was captured as stages, and real model calls were timed.
    assert run["stages"] and run["stages"][-1]["stage"]
    assert run["llm_calls"]["attempted"] > 0 and run["llm_calls"]["failed"] == 0
    # Every real call got an answer, so the repeat is complete and each call was classified.
    assert run["complete"] is True, run["completeness"]
    assert run["calls"] and {c["outcome"] for c in run["calls"]} == {"ok"}
    assert run["runtime"]["call_timeout_mode"] == "pipeline-defaults"
    # The real pipeline passes its own max_tokens to the client on every call, and the default
    # "pipeline" mode turns exactly that into the output cap (3,000 to 10,000 tokens today).
    assert run["runtime"]["output_cap_mode"] == "pipeline"
    for call in run["calls"]:
        assert isinstance(call["max_tokens_requested"], int) and call["max_tokens_requested"] > 0
        assert call["output_cap_tokens"] == call["max_tokens_requested"]
    assert run["runtime"]["length_limited_calls"] == 0
    assert run["ingest"]["chunks"] >= 1
    assert run["requirement_coverage"]["total"] == 11
    # The gap-check wrapper was removed again, and the throwaway database is gone.
    assert runner.svc._requirement_gaps is original_gap_check
    assert run["database"].startswith(runner.DB_PREFIX)
    assert run["database"] not in _database_names()


def test_two_repeats_never_share_data(stub_model, store_factory):
    cfg = runner.EvalConfig(model="stub-model", mongo_uri=MONGO_TEST_URI)
    corpus = (ROOT / "examples" / "sample-prd.md").read_text(encoding="utf-8")
    seen = []

    def factory(name):
        store = store_factory(name)
        seen.append((name, store))
        return store

    runs = [runner.run_repeat(cfg, n, corpus, store_factory=factory,
                              llm_factory=lambda: runner.RecordingLLM(
                                  provider="ollama", model="stub-model",
                                  ollama_url="http://127.0.0.1:1"),
                              embedder=StubEmbedder()) for n in (1, 2)]

    assert all(r["ok"] for r in runs), [r["error"] for r in runs]
    assert seen[0][0] != seen[1][0]
    assert not {n for n, _ in seen} & _database_names()
