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

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")
ROOT = Path(__file__).resolve().parents[1]


def _server_reachable() -> bool:
    try:
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if not _server_reachable():
    pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
                "db-integration tests)", allow_module_level=True)

from store import Store  # noqa: E402


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


def test_the_real_pipeline_output_becomes_a_result_and_the_database_is_dropped(stub_model):
    cfg = runner.EvalConfig(model="stub-model", mongo_uri=MONGO_TEST_URI)
    corpus = (ROOT / "examples" / "sample-prd.md").read_text(encoding="utf-8")
    original_gap_check = runner.svc._requirement_gaps

    run = runner.run_repeat(
        cfg, 1, corpus,
        store_factory=lambda name: Store(MONGO_TEST_URI, name, 8),
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
    assert run["llm_calls"]["count"] > 0 and run["llm_calls"]["failed"] == 0
    assert run["ingest"]["chunks"] >= 1
    assert run["requirement_coverage"]["total"] == 11
    # The gap-check wrapper was removed again, and the throwaway database is gone.
    assert runner.svc._requirement_gaps is original_gap_check
    assert run["database"].startswith(runner.DB_PREFIX)
    assert run["database"] not in MongoClient(MONGO_TEST_URI).list_database_names()


def test_two_repeats_never_share_data(stub_model):
    cfg = runner.EvalConfig(model="stub-model", mongo_uri=MONGO_TEST_URI)
    corpus = (ROOT / "examples" / "sample-prd.md").read_text(encoding="utf-8")
    seen = []

    def factory(name):
        store = Store(MONGO_TEST_URI, name, 8)
        seen.append((name, store))
        return store

    runs = [runner.run_repeat(cfg, n, corpus, store_factory=factory,
                              llm_factory=lambda: runner.RecordingLLM(
                                  provider="ollama", model="stub-model",
                                  ollama_url="http://127.0.0.1:1"),
                              embedder=StubEmbedder()) for n in (1, 2)]

    assert all(r["ok"] for r in runs), [r["error"] for r in runs]
    assert seen[0][0] != seen[1][0]
    assert not {n for n, _ in seen} & set(MongoClient(MONGO_TEST_URI).list_database_names())
