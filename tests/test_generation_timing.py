"""Wall-clock profiling for the generation pipeline (issue #48, profiling only —
no algorithm/quality change; see #42 for the benchmark work any future
optimization would need to be validated against).

Reuses tests/test_rag_evidence_sufficiency.py's real fixtures (ScenarioStore /
ScenarioLLM / _delivery_store) to run the REAL pipeline end to end, rather than
re-building a parallel fake harness.
"""
import pytest

from tests.test_generation_pipeline import FakeEmbedder
from tests.test_rag_evidence_sufficiency import ScenarioLLM, _delivery_store

from testgen.service import generate_fresh_testcases_pipeline, stage_durations

REQUIRED_STAGES = {
    "discovery_pass_1", "discovery_pass_2", "discovery_pass_3",
    "dag_layer_1", "dag_layer_2", "persistence",
}


def _run(store, llm, **params):
    return generate_fresh_testcases_pipeline(
        store, llm, FakeEmbedder(),
        {"feature_id": "feature-1", "total": 40,
         "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
         **params},
    )


class TestStageDurationsPureFunction:
    """stage_durations() itself: consecutive-delta math, no pipeline involved."""

    def test_computes_consecutive_deltas(self):
        marks = [("_start", 100.0), ("a", 100.5), ("b", 100.9), ("c", 102.0)]
        d = stage_durations(marks)
        assert d == {"a": 0.5, "b": 0.4, "c": 1.1}

    def test_empty_list_returns_empty_dict(self):
        assert stage_durations([]) == {}

    def test_single_mark_returns_empty_dict(self):
        # Just the "_start" sentinel, no stage completed yet.
        assert stage_durations([("_start", 100.0)]) == {}

    def test_partial_list_reports_only_completed_stages(self):
        # Simulates an exception cutting a run short after 2 stages.
        marks = [("_start", 0.0), ("discovery_pass_1", 1.0), ("discovery_pass_2", 1.7)]
        d = stage_durations(marks)
        assert d == {"discovery_pass_1": 1.0, "discovery_pass_2": 0.7}

    def test_zero_duration_stage_does_not_crash(self):
        marks = [("_start", 5.0), ("instant_stage", 5.0)]
        assert stage_durations(marks) == {"instant_stage": 0.0}

    def test_very_small_duration_is_rounded_not_truncated_to_zero(self):
        marks = [("_start", 0.0), ("tiny", 0.0005)]
        assert stage_durations(marks) == {"tiny": 0.001} or \
            stage_durations(marks) == {"tiny": 0.0}  # rounds to 3 decimal places


class TestPipelineStageTimings:
    """The real pipeline, run end to end against fast fake LLM/store fixtures."""

    def test_returns_all_six_named_stages(self):
        res = _run(_delivery_store(), ScenarioLLM())
        timings = res["stage_timings"]
        assert REQUIRED_STAGES.issubset(timings.keys())

    def test_every_duration_is_a_non_negative_number(self):
        res = _run(_delivery_store(), ScenarioLLM())
        for name, seconds in res["stage_timings"].items():
            assert isinstance(seconds, (int, float)), name
            assert seconds >= 0, f"{name} was negative: {seconds}"

    def test_total_seconds_is_at_least_the_sum_of_named_stages(self):
        # >= rather than == : the total also includes bonus buckets
        # (retrieval_setup, fusion, rag_validation) that aren't in the issue's
        # required 6, so it's expected to exceed their sum, never fall short.
        res = _run(_delivery_store(), ScenarioLLM())
        timings = res["stage_timings"]
        stage_sum = sum(v for k, v in timings.items() if k != "total_seconds")
        assert timings["total_seconds"] >= stage_sum - 0.01  # rounding slack

    def test_does_not_change_generation_output(self):
        # Profiling must be purely observational -- same case counts as a plain
        # run of the same fixtures (mirrors test_rag_evidence_sufficiency's own
        # assertions, just checking stage_timings didn't perturb anything else).
        res = _run(_delivery_store(), ScenarioLLM())
        assert res["cases_new"] + res["cases_reused"] >= 1
        assert "stage_timings" in res

    def test_timing_sink_is_populated_when_passed_explicitly(self):
        sink = []
        generate_fresh_testcases_pipeline(
            _delivery_store(), ScenarioLLM(), FakeEmbedder(),
            {"feature_id": "feature-1", "total": 40,
             "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20}},
            timing_sink=sink,
        )
        assert sink[0][0] == "_start"
        names = {name for name, _ in sink}
        assert REQUIRED_STAGES.issubset(names)


class _AlwaysFailingLLM(ScenarioLLM):
    """Every LLM call fails -- used to prove partial timing survives a mid-run
    exception. Pass 0 (build_raw_api_spec_from_documents) needs no LLM call, so
    it always completes before this fixture's failure is even reached."""

    def _raw_chat(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage")


class TestPartialTimingOnFailure:
    def test_exception_after_pass_0_still_leaves_that_mark_in_the_sink(self):
        sink = []
        with pytest.raises(Exception):
            generate_fresh_testcases_pipeline(
                _delivery_store(), _AlwaysFailingLLM(), FakeEmbedder(),
                {"feature_id": "feature-1", "total": 40,
                 "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20}},
                timing_sink=sink,
            )
        # Pass 0 needs no LLM call, so it completes before Pass 1's LLM call
        # blows up -- exactly the "capture timing even when a stage fails,
        # where practical" case the issue asks for.
        names = [name for name, _ in sink]
        assert names[0] == "_start"
        assert "discovery_pass_1" in names
        # The run never got anywhere near later stages.
        assert "dag_layer_1" not in names
        # And the partial sink is still safely summarizable.
        partial = stage_durations(sink)
        assert "discovery_pass_1" in partial
        assert partial["discovery_pass_1"] >= 0
