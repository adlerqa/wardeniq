"""Tests for per-process token accounting + cost (app/usage.py)."""
import usage


class TestRecorder:
    def teardown_method(self):
        usage.stop()   # ensure no recorder leaks between tests

    def test_records_per_model_and_aggregates(self):
        usage.start()
        usage.record("gpt-4o", 1000, 500, kind="llm")
        usage.record("gpt-4o", 200, 100, kind="llm")
        usage.record("nomic-embed-text", 4000, 0, kind="embedding", estimated=True)
        rec = usage.stop()
        s = usage.summarize(rec, prices={})
        assert s["by_model"]["gpt-4o"]["calls"] == 2
        assert s["by_model"]["gpt-4o"]["total_tokens"] == 1800
        assert s["by_model"]["nomic-embed-text"]["estimated"] is True
        assert s["total_tokens"] == 5800

    def test_record_without_recorder_is_noop(self):
        usage.stop()                      # no recorder bound
        usage.record("gpt-4o", 10, 10)    # must not raise
        assert usage.summarize({}, {})["total_tokens"] == 0


class TestPricing:
    def test_known_model_cost(self):
        rec = {"gpt-4o": {"calls": 1, "prompt_tokens": 1_000_000,
                          "completion_tokens": 1_000_000, "kind": "llm"}}
        s = usage.summarize(rec)                      # 1M in * 2.50 + 1M out * 10.00
        assert abs(s["cost_usd"] - 12.50) < 1e-9

    def test_substring_match_resolves_versioned_model(self):
        # concrete "gpt-4o-2024-08-06" should resolve to the "gpt-4o" price entry
        rec = {"gpt-4o-2024-08-06": {"prompt_tokens": 1_000_000, "completion_tokens": 0,
                                     "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec)
        assert abs(s["by_model"]["gpt-4o-2024-08-06"]["cost_usd"] - 2.50) < 1e-9

    def test_settings_override_wins_and_prices_local_model(self):
        rec = {"qwen2.5:7b": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000,
                              "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={"qwen2.5:7b": {"in": 1.0, "out": 2.0}})
        assert abs(s["cost_usd"] - 3.0) < 1e-9

    def test_unpriced_model_reports_none_cost(self):
        rec = {"totally-unknown-model": {"prompt_tokens": 500, "completion_tokens": 500,
                                         "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={})
        assert s["by_model"]["totally-unknown-model"]["cost_usd"] is None
        assert s["cost_usd"] is None

    def test_family_fallback_prices_versioned_gemini(self):
        # "gemini-3.1-flash-lite" hits no exact/substring price but matches the family rule
        # (("gemini","flash","lite") -> $0.10 / 1M input, current published rate).
        rec = {"gemini-3.1-flash-lite": {"prompt_tokens": 1_000_000, "completion_tokens": 0,
                                         "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={})
        assert abs(s["by_model"]["gemini-3.1-flash-lite"]["cost_usd"] - 0.10) < 1e-9

    def test_ollama_tag_is_free(self):
        rec = {"qwen2.5:7b": {"prompt_tokens": 999_999, "completion_tokens": 999_999,
                              "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={})
        assert s["by_model"]["qwen2.5:7b"]["cost_usd"] == 0.0
