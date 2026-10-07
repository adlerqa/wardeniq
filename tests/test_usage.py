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
        # A not-yet-listed versioned gemini flash-lite id hits no exact/substring price
        # but matches the family rule (("gemini","flash","lite") -> $0.10 / 1M input).
        # Deliberately NOT "gemini-3.1-flash-lite" — that id is now an exact DEFAULT_PRICES
        # entry (it's a real, currently-offered dropdown model), so it would resolve via
        # the exact-match branch instead of exercising the fallback this test targets.
        rec = {"gemini-4.0-flash-lite": {"prompt_tokens": 1_000_000, "completion_tokens": 0,
                                         "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={})
        assert abs(s["by_model"]["gemini-4.0-flash-lite"]["cost_usd"] - 0.10) < 1e-9

    def test_ollama_tag_is_free(self):
        rec = {"qwen2.5:7b": {"prompt_tokens": 999_999, "completion_tokens": 999_999,
                              "calls": 1, "kind": "llm"}}
        s = usage.summarize(rec, prices={})
        assert s["by_model"]["qwen2.5:7b"]["cost_usd"] == 0.0


class TestEstimateGenerationTokens:
    """Pure token-count math (issue #22) -- no pricing involved."""

    def test_scales_with_total(self):
        small = usage.estimate_generation_tokens(text_length=4000, total=4)
        large = usage.estimate_generation_tokens(text_length=4000, total=40)
        assert large["prompt_tokens_mid"] > small["prompt_tokens_mid"]
        assert large["completion_tokens_mid"] > small["completion_tokens_mid"]

    def test_scales_with_document_length(self):
        short_doc = usage.estimate_generation_tokens(text_length=400, total=16)
        long_doc = usage.estimate_generation_tokens(text_length=40_000, total=16)
        assert long_doc["prompt_tokens_mid"] > short_doc["prompt_tokens_mid"]
        # Only the (discovery) input side depends on document length.
        assert long_doc["completion_tokens_mid"] == short_doc["completion_tokens_mid"]

    def test_document_length_input_is_capped_per_pass(self):
        # Well past the per-pass cap: further growth must stop moving the estimate.
        huge = usage.estimate_generation_tokens(text_length=10_000_000, total=16)
        bigger = usage.estimate_generation_tokens(text_length=100_000_000, total=16)
        assert huge["prompt_tokens_mid"] == bigger["prompt_tokens_mid"]

    def test_zero_and_negative_inputs_do_not_crash(self):
        z = usage.estimate_generation_tokens(text_length=0, total=0)
        assert z["prompt_tokens_mid"] >= 0
        assert z["completion_tokens_mid"] >= 0
        neg = usage.estimate_generation_tokens(text_length=-5, total=-5)
        assert neg["prompt_tokens_mid"] >= 0
        assert neg["completion_tokens_mid"] >= 0

    def test_none_inputs_do_not_crash(self):
        r = usage.estimate_generation_tokens(text_length=None, total=None)
        assert r["prompt_tokens_mid"] >= 0
        assert r["completion_tokens_mid"] >= 0


class TestEstimateGenerationCost:
    def test_ollama_provider_has_no_dollar_figure(self):
        r = usage.estimate_generation_cost(4000, 16, provider="ollama", model="qwen2.5:7b")
        assert r["low"] is None
        assert r["high"] is None
        assert "local" in r["note"].lower()

    def test_default_provider_is_treated_as_ollama(self):
        r = usage.estimate_generation_cost(4000, 16, provider="", model="")
        assert r["low"] is None
        assert r["high"] is None

    def test_unknown_hosted_model_reports_no_dollar_figure(self):
        r = usage.estimate_generation_cost(4000, 16, provider="openai",
                                           model="totally-unknown-model-xyz", prices={})
        assert r["low"] is None
        assert r["high"] is None
        assert "no pricing known" in r["note"].lower()

    def test_known_hosted_model_returns_a_range(self):
        r = usage.estimate_generation_cost(4000, 16, provider="openai", model="gpt-4o")
        assert r["low"] is not None and r["high"] is not None
        assert r["low"] <= r["high"]
        assert r["low"] > 0
        assert r["currency"] == "USD"

    def test_settings_price_override_is_honoured(self):
        cheap = usage.estimate_generation_cost(
            4000, 16, provider="openai", model="my-custom-model",
            prices={"my-custom-model": {"in": 0.01, "out": 0.01}})
        pricey = usage.estimate_generation_cost(
            4000, 16, provider="openai", model="my-custom-model",
            prices={"my-custom-model": {"in": 100.0, "out": 100.0}})
        assert cheap["low"] < pricey["low"]

    def test_larger_total_increases_the_estimate(self):
        small = usage.estimate_generation_cost(4000, 4, provider="openai", model="gpt-4o")
        large = usage.estimate_generation_cost(4000, 40, provider="openai", model="gpt-4o")
        assert large["low"] > small["low"]

    def test_range_is_a_band_around_the_midpoint(self):
        r = usage.estimate_generation_cost(4000, 16, provider="openai", model="gpt-4o")
        mid = (r["prompt_tokens_mid"] / 1e6) * 2.50 + (r["completion_tokens_mid"] / 1e6) * 10.00
        assert r["low"] < mid < r["high"]
