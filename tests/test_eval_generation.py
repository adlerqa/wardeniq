"""Tests for the generation-quality evaluation (issue #43, first slice).

Covers the pure metric helpers, the fixed corpus/labels, and the runner
(scripts/eval_generation.py) with fakes, so nothing here needs a model, Ollama or MongoDB.
The real pipeline against a real MongoDB is exercised in tests/test_eval_generation_db.py.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import httpx
import pytest

import usage
from tests.eval import generation_fixture as fixture
from tests.eval import generation_metrics as m

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    spec = importlib.util.spec_from_file_location("eval_generation_runner",
                                                  ROOT / "scripts" / "eval_generation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


@pytest.fixture(autouse=True)
def _other_test_modules_may_have_imported_the_app(monkeypatch):
    """Other test modules import `main`, so in a full run those modules are in sys.modules.
    The isolation guard is exercised explicitly below, and import-cleanliness is checked in
    a fresh subprocess."""
    monkeypatch.setattr(runner, "LIVE_STATE_MODULES", ())


# =========================================================================== metrics
class TestRate:
    def test_basic_and_rounding(self):
        assert m.rate(1, 4) == 0.25
        assert m.rate(1, 3) == 0.3333
        assert m.rate(0, 5) == 0.0

    @pytest.mark.parametrize("count,den", [(1, 0), (1, -2), (None, 4), (1, None), ("1", 4),
                                           (1, "4"), (True, 4), (1, float("nan")),
                                           (1, float("inf"))])
    def test_zero_or_invalid_gives_none_never_zero(self, count, den):
        assert m.rate(count, den) is None


class TestSummarizeFilter:
    GOOD = {"generated": 10, "persisted": 6, "rejected": 4,
            "rejected_by_reason": {"exemplar-copy": 2, "duplicate": 1, "no-source-grounding": 1}}

    def test_counts_and_rates_use_generated_as_denominator(self):
        s = m.summarize_filter(self.GOOD)
        assert s["available"] is True
        assert (s["generated"], s["persisted"], s["rejected"]) == (10, 6, 4)
        assert s["persisted_rate"] == 0.6 and s["rejected_rate"] == 0.4
        assert s["reasons"]["exemplar-copy"] == {"count": 2, "rate": 0.2}
        assert s["reasons"]["duplicate"] == {"count": 1, "rate": 0.1}
        assert s["reasons"]["no-source-grounding"] == {"count": 1, "rate": 0.1}
        assert s["reasons_sum_matches_rejected"] is True

    def test_known_reasons_absent_from_input_are_reported_as_zero(self):
        s = m.summarize_filter(self.GOOD)
        assert s["reasons"]["hybrid-scaffold"] == {"count": 0, "rate": 0.0}
        assert set(s["reasons"]) == set(m.KNOWN_REASONS)

    def test_unknown_reasons_are_kept_separately(self):
        s = m.summarize_filter({**self.GOOD, "rejected_by_reason": {"brand-new-reason": 4}})
        assert s["other_reasons"] == {"brand-new-reason": 4}
        assert s["reasons_sum_matches_rejected"] is True

    def test_zero_generated_gives_no_rates(self):
        s = m.summarize_filter({"generated": 0, "persisted": 0, "rejected": 0,
                                "rejected_by_reason": {}})
        assert s["available"] is True
        assert s["persisted_rate"] is None and s["rejected_rate"] is None
        assert s["reasons"]["exemplar-copy"] == {"count": 0, "rate": None}

    @pytest.mark.parametrize("bad", [None, [], "x", 3, {}, {"generated": 1},
                                     {"generated": -1, "persisted": 0, "rejected": 0},
                                     {"generated": 1.5, "persisted": 0, "rejected": 0},
                                     {"generated": "1", "persisted": 0, "rejected": 0}])
    def test_missing_or_invalid_block_is_unavailable_not_zeros(self, bad):
        s = m.summarize_filter(bad)
        assert s["available"] is False and s["reason"]

    def test_invalid_reason_entries_are_ignored_and_listed(self):
        s = m.summarize_filter({**self.GOOD, "rejected_by_reason":
                                {"exemplar-copy": "two", "duplicate": -1, "no-source-grounding": 1}})
        assert s["reasons"]["exemplar-copy"]["count"] == 0
        assert s["ignored_reason_entries"] == ["duplicate", "exemplar-copy"]
        assert s["reasons_sum_matches_rejected"] is False

    def test_non_mapping_reasons_treated_as_empty(self):
        s = m.summarize_filter({**self.GOOD, "rejected_by_reason": None})
        assert s["available"] and s["reasons_sum_matches_rejected"] is False


class TestStageDurations:
    def test_each_stage_lasts_until_the_next_mark_and_the_last_until_end(self):
        marks = [(10.0, "Pass 0", 5), (12.5, "Pass 1", 20), (20.0, "Persist", 82)]
        out = m.stage_durations(marks, 25.0)
        assert [(s["stage"], s["seconds"]) for s in out] == [
            ("Pass 0", 2.5), ("Pass 1", 7.5), ("Persist", 5.0)]
        assert out[0]["progress"] == 5

    def test_empty_and_malformed(self):
        assert m.stage_durations([], 5.0) == []
        assert m.stage_durations(None, 5.0) == []
        out = m.stage_durations([("x", "bad", 1), (1.0,), None, (2.0, "ok", None)], 3.0)
        assert out == [{"stage": "ok", "progress": None, "seconds": 1.0}]

    def test_end_before_last_mark_clamps_to_zero(self):
        assert m.stage_durations([(10.0, "a", 1)], 5.0)[0]["seconds"] == 0.0


class TestGroundingSurvivors:
    def test_parses_the_pipelines_own_progress_message(self):
        stages = [{"stage": "Pass 0 complete: 2 verbatim API endpoint(s) found", "seconds": 1},
                  {"stage": "Pass 1 complete: 0 entities, 2 APIs, 3 UI components survived sanitization",
                   "seconds": 53}]
        assert m.parse_grounding_survivors(stages) == {"entities": 0, "apis": 2, "ui_components": 3}

    @pytest.mark.parametrize("stages", [None, [], [{"stage": "Pass 1 started"}], ["x"],
                                        [{"stage": None}], [{"stage": "5 widgets survived"}]])
    def test_absent_or_reworded_message_gives_none_not_zeros(self, stages):
        assert m.parse_grounding_survivors(stages) is None

    def test_singular_forms_are_accepted(self):
        stage = {"stage": "Pass 1 complete: 1 entity, 1 API, 1 UI component survived sanitization"}
        assert m.parse_grounding_survivors([stage]) == {"entities": 1, "apis": 1, "ui_components": 1}


class TestLlmCallSummary:
    def test_rollup_counts_outcomes_and_decode_speed(self):
        calls = [
            {"outcome": "ok", "seconds": 2.0, "prompt_chars": 100, "response_chars": 10,
             "completion_tokens": 100, "decode_seconds": 5.0, "queue_wait_seconds_estimate": 1.0},
            {"outcome": "timeout", "seconds": 4.0, "prompt_chars": 50, "response_chars": 0},
            {"outcome": "parse_error", "seconds": 1.0, "completion_tokens": 20,
             "decode_seconds": 1.0},
        ]
        s = m.llm_call_summary(calls)
        assert (s["attempted"], s["successful"], s["failed"]) == (3, 1, 2)
        assert (s["timeouts"], s["http_errors"], s["parse_errors"], s["other_errors"]) == (1, 0, 1, 0)
        assert s["by_outcome"] == {"ok": 1, "length_limited": 0, "timeout": 1, "http_error": 0,
                                   "parse_error": 1, "other": 0}
        assert s["answered"] == 2 and s["length_limited"] == 0
        assert s["total_seconds"] == 7.0 and s["max_seconds"] == 4.0
        assert s["prompt_chars"] == 150 and s["response_chars"] == 10
        assert s["completion_tokens"] == 120 and s["decode_seconds"] == 6.0
        assert s["tokens_per_second"] == 20.0
        assert s["queue_wait_seconds_estimate"] == 1.0

    def test_empty_has_no_mean_and_no_speed(self):
        s = m.llm_call_summary([])
        assert s["attempted"] == 0 and s["mean_seconds"] is None and s["max_seconds"] is None
        assert s["tokens_per_second"] is None and s["completion_tokens"] is None

    def test_junk_entries_are_ignored(self):
        s = m.llm_call_summary([None, "x", {"seconds": "slow"}, {"seconds": 1.0, "ok": True}])
        assert s["attempted"] == 2 and s["total_seconds"] == 1.0

    def test_entries_without_an_outcome_fall_back_to_the_ok_flag(self):
        s = m.llm_call_summary([{"ok": True}, {"ok": False}, {}])
        assert s["successful"] == 1 and s["other_errors"] == 2

    def test_decode_speed_ignores_calls_without_both_numbers(self):
        s = m.llm_call_summary([{"outcome": "ok", "completion_tokens": 50},
                                {"outcome": "ok", "decode_seconds": 5.0},
                                {"outcome": "ok", "completion_tokens": 10, "decode_seconds": 0}])
        assert s["tokens_per_second"] is None


class TestCompleteness:
    @staticmethod
    def _calls(*outcomes):
        return [{"outcome": o, "seconds": 1.0} for o in outcomes]

    def test_all_calls_answered_is_complete(self):
        c = m.assess_completeness(self._calls("ok", "ok"))
        assert c["complete"] is True and c["reasons"] == []
        assert (c["attempted_calls"], c["successful_calls"], c["failed_calls"]) == (2, 2, 0)

    @pytest.mark.parametrize("outcome,key", [("timeout", "timeout_count"),
                                             ("http_error", "http_error_count"),
                                             ("other", "other_error_count")])
    def test_any_infrastructure_failure_makes_it_incomplete(self, outcome, key):
        c = m.assess_completeness(self._calls("ok", outcome))
        assert c["complete"] is False and c[key] == 1 and c["failed_calls"] == 1
        assert len(c["reasons"]) == 1

    def test_a_parse_error_alone_does_not_make_it_incomplete(self):
        # Malformed JSON is the model's own output; excluding such repeats would flatter it.
        c = m.assess_completeness(self._calls("ok", "parse_error"))
        assert c["complete"] is True and c["parse_error_count"] == 1 and c["failed_calls"] == 1

    def test_no_calls_at_all_is_incomplete(self):
        c = m.assess_completeness([])
        assert c["complete"] is False and "no model calls" in c["reasons"][0]

    def test_reasons_name_each_kind_of_failure(self):
        c = m.assess_completeness(self._calls("timeout", "timeout", "http_error"))
        text = " ".join(c["reasons"])
        assert "2 model call(s) timed out" in text and "1 model call(s) failed with an HTTP error" in text


class TestCaseText:
    def test_collects_title_preconditions_and_nested_steps_lowercased(self):
        case = {"title": "Reset Link EXPIRES", "preconditions": ["User exists"],
                "steps": [{"action": "Wait 31 Minutes", "expected": {"msg": "Link Invalid"}}],
                "id": "ignored-id", "metadata": {"intent": "ignored"}}
        text = m.case_text(case)
        assert "reset link expires" in text and "user exists" in text
        assert "wait 31 minutes" in text and "link invalid" in text
        assert "ignored" not in text

    def test_non_dict_is_empty(self):
        assert m.case_text(None) == "" and m.case_text("x") == ""


class TestRequirementCoverage:
    REQS = [{"id": "A", "must_mention": [["alpha"], ["beta", "bravo"]]},
            {"id": "B", "must_mention": [["gamma"]]}]

    def test_every_group_needs_one_alternative_in_the_same_case(self):
        out = m.requirement_coverage(self.REQS, ["alpha and bravo", "gamma"])
        assert out["covered"] == 2 and out["rate"] == 1.0 and out["uncovered_ids"] == []
        assert out["method"] == "keyword-heuristic"

    def test_groups_split_across_different_cases_do_not_count(self):
        out = m.requirement_coverage(self.REQS, ["alpha only", "bravo only"])
        assert out["uncovered_ids"] == ["A", "B"] and out["covered"] == 0

    def test_matching_is_case_insensitive_and_counts_cases(self):
        out = m.requirement_coverage(self.REQS, ["ALPHA Beta", "alpha bravo", "x"])
        per = {p["id"]: p for p in out["per_requirement"]}
        assert per["A"] == {"id": "A", "covered": True, "case_count": 2}

    def test_no_cases_and_no_requirements(self):
        assert m.requirement_coverage(self.REQS, [])["covered"] == 0
        none = m.requirement_coverage([], ["x"])
        assert none["total"] == 0 and none["rate"] is None

    @pytest.mark.parametrize("bad", [None, {"id": "", "must_mention": [["a"]]},
                                     {"id": "X"}, {"id": "X", "must_mention": []},
                                     {"id": "X", "must_mention": ["a"]},
                                     {"id": "X", "must_mention": [[]]},
                                     {"id": "X", "must_mention": [[""]]}])
    def test_invalid_requirements_are_skipped_and_counted(self, bad):
        out = m.requirement_coverage([bad, self.REQS[1]], ["gamma"])
        assert out["invalid_requirements"] == 1 and out["total"] == 1 and out["covered"] == 1

    def test_non_string_case_texts_are_ignored(self):
        assert m.requirement_coverage(self.REQS, [None, 5, "gamma"])["covered"] == 1


class TestAggregateRepeats:
    @staticmethod
    def _run(generated, exemplar, seconds, ok=True, complete=True, repeat=1):
        return {"repeat": repeat, "ok": ok, "complete": complete,
                "completeness": {"complete": complete,
                                 "reasons": [] if complete else ["3 model call(s) timed out"]},
                "filter": m.summarize_filter({"generated": generated, "persisted": generated - exemplar,
                                              "rejected": exemplar,
                                              "rejected_by_reason": {"exemplar-copy": exemplar}}),
                "timings": {"pipeline_seconds": seconds, "ingest_seconds": 1.0},
                "requirement_coverage": {"rate": 0.5}, "requirement_gaps": {"count": 2},
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                "llm_calls": {"attempted": 10, "parse_errors": 1, "tokens_per_second": 12.0,
                              "queue_wait_seconds_estimate": 30.0},
                "pipeline": {"errors": []}}

    def test_mean_min_max_across_complete_repeats(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0), self._run(10, 4, 140.0, repeat=2)])
        assert agg["repeats_total"] == 2 and agg["repeats_complete"] == 2
        assert agg["valid_baseline"] is True and agg["all_repeats_complete"] is True
        ex = agg["metrics"]["exemplar_copy_rate"]
        assert (ex["n"], ex["mean"], ex["min"], ex["max"]) == (2, 0.3, 0.2, 0.4)
        assert agg["metrics"]["pipeline_seconds"]["mean"] == 120.0
        assert agg["metrics"]["decode_tokens_per_second"]["mean"] == 12.0
        assert agg["statement"].startswith("VALID BASELINE: all 2 repeats completed")
        assert agg["provisional_metrics"] == {} and agg["repeats_missing"] == 0

    def test_incomplete_repeats_never_enter_any_statistics(self):
        good = self._run(10, 2, 100.0, repeat=1)
        bad = self._run(10, 5, 900.0, complete=False, repeat=2)
        agg = m.aggregate_repeats([good, bad])
        assert agg["repeats_complete"] == 1 and agg["repeats_incomplete"] == 1
        prov = agg["provisional_metrics"]
        assert prov["exemplar_copy_rate"]["n"] == 1
        assert prov["exemplar_copy_rate"]["mean"] == 0.2           # not 0.35
        assert prov["pipeline_seconds"]["max"] == 100.0             # the 900 s repeat is excluded

    def test_one_incomplete_repeat_means_no_valid_baseline_whatever_the_others_did(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0, repeat=1),
                                   self._run(10, 5, 900.0, complete=False, repeat=2),
                                   self._run(10, 2, 110.0, repeat=3)], planned=3)
        assert agg["repeats_complete"] == 2
        assert agg["valid_baseline"] is False and agg["all_repeats_complete"] is False
        assert agg["metrics"] == {}                                  # nothing official
        assert agg["provisional_metrics"]["generated"]["n"] == 2     # reference only
        assert agg["statement"].startswith("NOT A VALID BASELINE: 2 of 3 requested repeats")
        assert "1 incomplete or failed" in agg["statement"]

    def test_repeats_that_never_ran_count_against_the_baseline(self):
        # e.g. the run was interrupted after 2 of 3 repeats, both complete.
        agg = m.aggregate_repeats([self._run(10, 2, 100.0, repeat=1),
                                   self._run(10, 2, 100.0, repeat=2)], planned=3)
        assert agg["valid_baseline"] is False and agg["repeats_missing"] == 1
        assert agg["metrics"] == {} and agg["provisional_metrics"]["generated"]["n"] == 2
        assert "1 not run" in agg["statement"]

    def test_the_planned_count_defaults_to_the_runs_given(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0)])
        assert agg["repeats_planned"] == 1 and agg["valid_baseline"] is True

    @pytest.mark.parametrize("planned", [None, 0, -1, "3", 1.5])
    def test_an_invalid_planned_count_falls_back_to_the_runs_given(self, planned):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0)], planned=planned)
        assert agg["repeats_planned"] == 1

    def test_valid_baseline_is_never_true_for_a_partial_set_of_complete_repeats(self):
        for done in (1, 2):
            runs = [self._run(10, 2, 100.0, repeat=i + 1) for i in range(done)]
            assert m.aggregate_repeats(runs, planned=3)["valid_baseline"] is False
        runs = [self._run(10, 2, 100.0, repeat=i + 1) for i in range(3)]
        assert m.aggregate_repeats(runs, planned=3)["valid_baseline"] is True

    def test_length_limited_notes_are_listed_per_repeat(self):
        run = self._run(10, 2, 100.0, repeat=2)
        run["completeness"]["notes"] = ["1 model call(s) stopped at the output token cap"]
        agg = m.aggregate_repeats([run])
        assert agg["notes"] == ["repeat 2: 1 model call(s) stopped at the output token cap"]

    def test_incomplete_repeats_stay_visible_as_diagnostics(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0), self._run(10, 5, 900.0, complete=False, repeat=2)])
        diag = agg["incomplete_diagnostics"]
        assert [d["repeat"] for d in diag] == [2]
        assert diag[0]["ran"] is True and diag[0]["reasons"] == ["3 model call(s) timed out"]
        assert diag[0]["metrics"]["exemplar_copy_rate"] == 0.5

    def test_no_complete_repeat_means_no_valid_baseline(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0, complete=False),
                                   self._run(10, 3, 100.0, complete=False, repeat=2)])
        assert agg["valid_baseline"] is False and agg["repeats_complete"] == 0
        assert agg["metrics"] == {} and agg["provisional_metrics"] == {}
        assert agg["statement"].startswith("NO VALID BASELINE")
        assert "nothing about model quality" in agg["statement"]

    def test_a_repeat_that_crashed_is_incomplete_and_explained(self):
        crashed = {"repeat": 2, "ok": False, "complete": False, "error": "RuntimeError: boom"}
        agg = m.aggregate_repeats([self._run(10, 2, 100.0), crashed])
        assert agg["repeats_ok"] == 1 and agg["repeats_incomplete"] == 1
        assert agg["incomplete_diagnostics"][0]["reasons"] == ["RuntimeError: boom"]
        assert agg["incomplete_diagnostics"][0]["ran"] is False

    def test_a_repeat_with_no_completeness_verdict_is_not_trusted(self):
        legacy = {"ok": True, "filter": m.summarize_filter({"generated": 1, "persisted": 1,
                                                            "rejected": 0, "rejected_by_reason": {}})}
        agg = m.aggregate_repeats([legacy])
        assert agg["valid_baseline"] is False and agg["metrics"] == {}

    def test_none_values_do_not_count_toward_n(self):
        zero = self._run(0, 0, 50.0)       # zero generated -> rates are None
        agg = m.aggregate_repeats([zero, self._run(10, 2, 100.0, repeat=2)])
        assert agg["metrics"]["exemplar_copy_rate"]["n"] == 1
        assert agg["metrics"]["exemplar_copy_count"]["n"] == 2

    def test_grounding_survivors_are_aggregated_when_present(self):
        a, b = self._run(10, 2, 100.0), self._run(10, 2, 100.0, repeat=2)
        a["grounding_survivors"] = {"entities": 0, "apis": 2, "ui_components": 1}
        b["grounding_survivors"] = {"entities": 2, "apis": 2, "ui_components": 3}
        agg = m.aggregate_repeats([a, b])["metrics"]
        assert agg["grounding_entities"]["mean"] == 1.0 and agg["grounding_ui_components"]["max"] == 3
        assert "grounding_apis" in agg
        assert "grounding_entities" not in m.aggregate_repeats([self._run(10, 2, 1.0)])["metrics"]

    def test_nothing_to_aggregate(self):
        agg = m.aggregate_repeats([])
        assert agg["repeats_total"] == 0 and agg["valid_baseline"] is False
        assert agg["statement"] == "No repeats were run." and agg["metrics"] == {}
        assert m.aggregate_repeats([None, "x"])["repeats_total"] == 0

    def test_unavailable_filter_contributes_no_filter_metrics(self):
        agg = m.aggregate_repeats([{"ok": True, "complete": True, "filter": {"available": False},
                                    "timings": {"pipeline_seconds": 5.0}}])
        assert "generated" not in agg["metrics"] and agg["metrics"]["pipeline_seconds"]["n"] == 1


def test_corpus_hash_is_sha256():
    assert m.corpus_hash(b"abc") == hashlib.sha256(b"abc").hexdigest()


# =========================================================================== fixture
class TestFixture:
    PRD = " ".join((ROOT / fixture.CORPUS_PATH).read_text(encoding="utf-8").split())

    def test_ids_are_unique(self):
        ids = [r["id"] for r in fixture.REQUIREMENTS]
        assert len(ids) == len(set(ids))

    def test_every_excerpt_is_verbatim_in_the_corpus(self):
        for req in fixture.REQUIREMENTS:
            assert " ".join(req["excerpt"].split()) in self.PRD, req["id"]

    def test_every_requirement_id_in_the_prd_is_labelled(self):
        in_prd = set(re.findall(r"\*\*((?:N?FR)-\d+)\*\*", (ROOT / fixture.CORPUS_PATH).read_text()))
        assert in_prd == {r["id"] for r in fixture.REQUIREMENTS}

    def test_labels_are_well_formed(self):
        for req in fixture.REQUIREMENTS:
            assert req["must_mention"], req["id"]
            for group in req["must_mention"]:
                assert group and all(isinstance(a, str) and a == a.lower() and a for a in group), req["id"]

    def test_unrelated_text_covers_nothing(self):
        out = m.requirement_coverage(fixture.REQUIREMENTS, ["the quick brown fox"])
        assert out["covered"] == 0

    def test_a_case_that_names_the_key_terms_covers_the_requirement(self):
        out = m.requirement_coverage(fixture.REQUIREMENTS, [
            "forgot password link on the sign-in screen",
            "audit log records the reset request",
        ])
        assert {p["id"] for p in out["per_requirement"] if p["covered"]} >= {"FR-1", "NFR-4"}

    def test_fixture_hash_changes_when_a_label_changes(self, monkeypatch):
        before = fixture.fixture_hash()
        monkeypatch.setattr(fixture, "REQUIREMENTS",
                            [dict(fixture.REQUIREMENTS[0], must_mention=[["different"]])])
        assert fixture.fixture_hash() != before


# =========================================================================== runner helpers
class FakeClient:
    def __init__(self):
        self.dropped = []

    def drop_database(self, name):
        self.dropped.append(name)


class FakeStore:
    instances = []

    def __init__(self, uri, db_name, dim=8):
        self.uri, self.dim = uri, dim
        self.db = types.SimpleNamespace(name=db_name)
        self.client = FakeClient()
        self.cases = [{"type": "api", "title": "Forgot password link opens the form",
                       "preconditions": [], "steps": [{"action": "click forgot password"}]}]
        self.created = []
        FakeStore.instances.append(self)

    def create_project(self, name):
        return "p1"

    def create_feature(self, name, project_id, sources, text, summary, embedding):
        self.created.append({"name": name, "summary": summary, "sources": sources})
        return "f1"

    def add_feature_chunks(self, fid, pid, chunks):
        self.chunks = chunks

    def get_feature_cases(self, fid):
        return self.cases

    def search_degraded(self):
        return {}


class FakeEmbedder:
    def __init__(self, *args, **kwargs):
        pass

    def embed(self, text, task="document"):
        return [0.0] * 8


class SpyLLM:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        SpyLLM.instances.append(self)

    def chat_json(self, system, user, **kw):
        self.calls.append({"label": "other", "outcome": "ok", "seconds": 0.5,
                           "prompt_chars": 10, "response_chars": 5})
        return {"summary": "Users who forgot their password can request a reset link by email."}


def real_shaped_output(generated=10, exemplar=2):
    """The same keys generate_fresh_testcases_pipeline() returns."""
    return {"cases_new": generated - exemplar, "cases_reused": 0, "steps_new": 30,
            "steps_reused": 0, "by_type": {"api": {"new": 2, "reused": 0}},
            "inherited_reused": 0, "inherited_rebuilt": 0, "discovered_api_count": 2,
            "rag_gap_count": 1, "errors": [],
            "testgen_filter": {"generated": generated, "persisted": generated - exemplar,
                               "rejected": exemplar,
                               "rejected_by_reason": {"exemplar-copy": exemplar}}}


def fake_pipeline(**kwargs):
    update = kwargs["update_job_fn"]
    update(stage="Pass 0: extracting", progress=5)
    update(stage="Pass 1 complete: 0 entities, 2 APIs, 2 UI components survived sanitization",
           progress=17)
    update(stage="Persisting", progress=82)
    usage.record("fake-model", 120, 30)
    # Call the pipeline's own gap check the way the real pipeline does.
    runner.svc._requirement_gaps(
        "The system must email the user a confirmation after every successful password reset.",
        {"api_tests": []})
    return real_shaped_output()


def _cfg(**kw):
    base = dict(model="qwen2.5:3b", mongo_uri="mongodb://127.0.0.1:1/?directConnection=true")
    base.update(kw)
    return runner.EvalConfig(**base)


def _run(cfg=None, repeat=1, pipeline_fn=fake_pipeline, store_factory=None, llm=None):
    cfg = cfg or _cfg()
    llm = llm or SpyLLM()
    return runner.run_repeat(
        cfg, repeat, "corpus text " * 50,
        store_factory=store_factory or (lambda name: FakeStore(cfg.mongo_uri, name)),
        llm_factory=lambda: llm, embedder=FakeEmbedder(), pipeline_fn=pipeline_fn)


# =========================================================================== runner
class TestRunnerResult:
    def test_pipeline_output_is_converted_into_the_result_structure(self):
        run = _run()
        assert run["ok"] is True and run["error"] is None
        flt = run["filter"]
        assert flt["generated"] == 10 and flt["reasons"]["exemplar-copy"] == {"count": 2, "rate": 0.2}
        assert run["pipeline"]["cases_new"] == 8 and run["pipeline"]["rag_gap_count"] == 1
        assert [s["stage"] for s in run["stages"]][0] == "Pass 0: extracting"
        assert run["stages"][-1]["stage"] == "Persisting"
        assert run["grounding_survivors"] == {"entities": 0, "apis": 2, "ui_components": 2}
        assert run["usage"]["prompt_tokens"] == 120 and run["usage"]["completion_tokens"] == 30
        assert run["timings"]["total_seconds"] >= 0
        assert run["persisted_cases"] == [{"type": "api", "title": "Forgot password link opens the form"}]
        assert run["requirement_coverage"]["method"] == "keyword-heuristic"
        assert run["ingest"]["summary_source"] == "model" and run["ingest"]["chunks"] >= 1

    def test_the_pipelines_own_gap_check_result_is_captured_and_restored(self):
        original = runner.svc._requirement_gaps
        run = _run()
        assert run["requirement_gaps"]["count"] == 1
        assert "confirmation" in run["requirement_gaps"]["items"][0]
        assert runner.svc._requirement_gaps is original

    def test_an_unavailable_filter_block_is_reported_not_zeroed(self):
        out = real_shaped_output()
        out.pop("testgen_filter")
        run = _run(pipeline_fn=lambda **kw: out)
        assert run["ok"] and run["filter"]["available"] is False

    def test_summary_fallback_is_recorded(self):
        class NoSummaryLLM(SpyLLM):
            def chat_json(self, *a, **k):
                raise RuntimeError("model unavailable")

        run = _run(llm=NoSummaryLLM())
        assert run["ingest"]["summary_source"] == "fallback"

    def test_seed_is_base_plus_repeat_minus_one(self):
        cfg = _cfg(seed=42)
        assert [_run(cfg, r)["seed"] for r in (1, 2, 3)] == [42, 43, 44]


class TestIsolation:
    def test_each_repeat_gets_its_own_throwaway_database_which_is_dropped(self):
        FakeStore.instances.clear()
        r1, r2 = _run(repeat=1), _run(repeat=2)
        assert r1["database"] != r2["database"]
        for run, store in zip((r1, r2), FakeStore.instances):
            assert run["database"].startswith(runner.DB_PREFIX)
            assert store.db.name == run["database"]
            assert store.client.dropped == [run["database"]]

    def test_database_is_dropped_even_when_the_pipeline_fails(self):
        FakeStore.instances.clear()

        def boom(**kw):
            raise RuntimeError("model fell over")

        run = _run(pipeline_fn=boom)
        assert FakeStore.instances[0].client.dropped == [run["database"]]

    def test_refuses_to_drop_any_other_database(self):
        client = FakeClient()
        store = types.SimpleNamespace(client=client)
        with pytest.raises(runner.EvalError):
            runner.drop_database(store, "wardeniq")
        assert client.dropped == []

    def test_a_store_bound_to_some_other_database_is_rejected(self):
        run = _run(store_factory=lambda name: FakeStore("uri", "wardeniq"))
        assert run["ok"] is False and "isolation check failed" in run["error"]

    def test_refuses_to_run_if_live_app_state_is_loaded(self, monkeypatch):
        monkeypatch.setattr(runner, "LIVE_STATE_MODULES", ("core.state",))
        monkeypatch.setitem(sys.modules, "core.state", types.ModuleType("core.state"))
        with pytest.raises(runner.EvalError, match="live application state"):
            _run()

    def test_main_exits_2_if_live_app_state_is_loaded(self, monkeypatch, capsys):
        TestModelSelection._wire(monkeypatch)
        monkeypatch.setattr(runner, "LIVE_STATE_MODULES", ("core.deps",))
        monkeypatch.setitem(sys.modules, "core.deps", types.ModuleType("core.deps"))
        assert runner.main(["--model", "m", "--mongo-uri", "mongodb://x/"]) == 2
        assert "live application state" in capsys.readouterr().err

    def test_importing_the_runner_does_not_load_live_settings_or_database(self):
        code = (
            "import importlib.util, sys\n"
            f"sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'app')!r}]\n"
            f"spec = importlib.util.spec_from_file_location('r', {str(ROOT / 'scripts' / 'eval_generation.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "print([x for x in ('core.state', 'core.deps', 'main') if x in sys.modules])\n"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert out.stdout.strip().endswith("[]"), out.stdout + out.stderr


class TestMetadataAndSecrets:
    def _payload(self, cfg=None, runs=None, argv=None):
        cfg = cfg or _cfg()
        return runner.build_payload(
            cfg, runs if runs is not None else [_run(cfg)],
            argv=argv or ["--model", cfg.model], corpus_bytes=b"corpus bytes",
            digests={cfg.model: "357c53fb659c", cfg.embed_model: "0a109f422b47"},
            ollama_version="0.12.0", mongo_version="7.0.14")

    def test_metadata_is_generated(self):
        meta = self._payload()["meta"]
        assert meta["model"] == "qwen2.5:3b" and meta["provider"] == "ollama"
        assert meta["model_digest"] == "357c53fb659c"
        assert meta["embed_model_digest"] == "0a109f422b47"
        assert meta["corpus"]["sha256"] == hashlib.sha256(b"corpus bytes").hexdigest()
        assert meta["corpus"]["path"] == fixture.CORPUS_PATH
        assert meta["fixture_sha256"] == fixture.fixture_hash()
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", meta["timestamp_utc"])
        assert meta["git"]["sha"] is None or re.fullmatch(r"[0-9a-f]{40}", meta["git"]["sha"])
        assert meta["run_parameters"]["seed_rule"] == "seed_base + repeat - 1"
        assert meta["hardware"]["platform"] and meta["hardware"]["machine"]
        assert meta["runtime"]["ollama_version"] == "0.12.0"
        assert meta["runtime"]["ollama_host"] == "localhost"
        assert meta["command"].startswith("python scripts/eval_generation.py ")

    def test_aggregate_is_present(self):
        payload = self._payload(runs=[_run(repeat=1), _run(repeat=2)])
        assert payload["aggregate"]["repeats_ok"] == 2

    def test_secrets_are_not_written_to_the_output(self, monkeypatch):
        uri = "mongodb://evaluser:Sup3rS3cretPw@db.internal.example:27017/?authSource=admin"
        monkeypatch.setenv("EVAL_API_KEY", "sk-test-not-a-real-key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-also-fake")
        cfg = _cfg(mongo_uri=uri)

        def exploding_store(name):
            raise RuntimeError(f"cannot connect to {uri}")

        failed = runner.run_repeat(cfg, 1, "x" * 400, store_factory=exploding_store,
                                   llm_factory=SpyLLM, embedder=FakeEmbedder(),
                                   pipeline_fn=fake_pipeline)
        ok = _run(cfg)
        text = json.dumps(self._payload(cfg, [ok, failed],
                                        argv=["--model", "qwen2.5:3b", "--mongo-uri", uri]),
                          default=str)
        for secret in ("Sup3rS3cretPw", "evaluser", "db.internal.example",
                       "sk-test-not-a-real-key", "sk-test-also-fake"):
            assert secret not in text
        assert failed["ok"] is False and "<redacted>" in failed["error"]

    @pytest.mark.parametrize("argv,expected", [
        (["--mongo-uri", "mongodb://u:p@h/"], ["--mongo-uri", "<redacted>"]),
        (["--mongo-uri=mongodb://u:p@h/"], ["--mongo-uri=<redacted>"]),
        (["--model", "m", "--repeats", "3"], ["--model", "m", "--repeats", "3"]),
    ])
    def test_redact_argv(self, argv, expected):
        assert runner.redact_argv(argv) == expected

    def test_redact_text_removes_uri_and_each_credential_part(self):
        cfg = _cfg(mongo_uri="mongodb://alice:hunter2@host:27017/")
        text = runner.redact_text("failed for alice with hunter2 at mongodb://alice:hunter2@host:27017/", cfg)
        assert "alice" not in text and "hunter2" not in text


class TestModelSelection:
    def test_the_requested_model_is_the_one_given_to_the_llm(self, monkeypatch, tmp_path):
        SpyLLM.instances.clear()
        self._wire(monkeypatch)
        out = tmp_path / "r.json"
        rc = runner.main(["--model", "llama3.2:3b", "--mongo-uri", "mongodb://x/",
                          "--out", str(out)])
        assert rc == 0
        assert SpyLLM.instances and SpyLLM.instances[0].kwargs["model"] == "llama3.2:3b"
        assert SpyLLM.instances[0].kwargs["provider"] == "ollama"
        assert json.loads(out.read_text())["meta"]["model"] == "llama3.2:3b"

    @staticmethod
    def _wire(monkeypatch, pipeline=fake_pipeline):
        import store as store_pkg
        monkeypatch.setattr(runner, "preflight_ollama",
                            lambda cfg: ({cfg.model: "abc123abc123", cfg.embed_model: "def456def456"}, "0.12.0"))
        monkeypatch.setattr(runner, "preflight_mongo", lambda cfg: "7.0.14")
        monkeypatch.setattr(store_pkg, "Store", FakeStore)
        monkeypatch.setattr(runner, "RecordingLLM", SpyLLM)
        monkeypatch.setattr(runner, "Embedder", FakeEmbedder)
        monkeypatch.setattr(runner.svc, "generate_fresh_testcases_pipeline", pipeline)

    def test_only_local_ollama_is_accepted_in_this_slice(self):
        with pytest.raises(SystemExit):
            runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/", "--provider", "openai"])

    def test_model_and_mongo_uri_are_required_with_no_default(self, monkeypatch):
        monkeypatch.delenv("EVAL_MONGO_URI", raising=False)
        with pytest.raises(SystemExit):
            runner.parse_args(["--model", "m"])
        with pytest.raises(SystemExit):
            runner.parse_args(["--mongo-uri", "mongodb://x/"])

    def test_mongo_uri_can_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("EVAL_MONGO_URI", "mongodb://env/")
        assert runner.parse_args(["--model", "m"]).mongo_uri == "mongodb://env/"

    def test_repeats_must_be_positive(self):
        with pytest.raises(SystemExit):
            runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "0"])


class TestFailureHandling:
    def test_a_failed_repeat_is_recorded_and_the_next_one_still_runs(self, monkeypatch, tmp_path):
        TestModelSelection._wire(monkeypatch)
        calls = {"n": 0}

        def flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("the model returned garbage")
            return fake_pipeline(**kw)

        monkeypatch.setattr(runner.svc, "generate_fresh_testcases_pipeline", flaky)
        out = tmp_path / "r.json"
        rc = runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "2",
                          "--out", str(out)])
        data = json.loads(out.read_text())
        assert rc == 1
        assert [r["ok"] for r in data["runs"]] == [False, True]
        assert "the model returned garbage" in data["runs"][0]["error"]
        assert data["aggregate"]["repeats_ok"] == 1 and data["aggregate"]["repeats_total"] == 2

    def test_failed_preflight_runs_nothing_and_writes_nothing(self, monkeypatch, tmp_path, capsys):
        TestModelSelection._wire(monkeypatch)

        def missing(cfg):
            raise runner.EvalError("model 'x' is not installed in Ollama. ollama pull x")

        monkeypatch.setattr(runner, "preflight_ollama", missing)
        out = tmp_path / "r.json"
        rc = runner.main(["--model", "x", "--mongo-uri", "mongodb://x/", "--out", str(out)])
        assert rc == 2 and not out.exists()
        assert "ollama pull x" in capsys.readouterr().err

    def test_exceptions_never_escape_run_repeat(self):
        def boom(**kw):
            raise ValueError("bad")

        run = _run(pipeline_fn=boom)
        assert run["ok"] is False and run["error"].startswith("ValueError: bad")


class TestOllamaPreflight:
    class Resp:
        def __init__(self, payload):
            self._p = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._p

    def _get(self, monkeypatch, installed):
        def fake_get(url, timeout=None):
            if url.endswith("/api/tags"):
                return self.Resp({"models": [{"name": n, "digest": d} for n, d in installed.items()]})
            return self.Resp({"version": "0.12.0"})
        monkeypatch.setattr(runner.httpx, "get", fake_get)

    def test_reports_digests_and_never_pulls(self, monkeypatch):
        self._get(monkeypatch, {"qwen2.5:3b": "357c53fb659c" + "0" * 52,
                                "nomic-embed-text:latest": "0a109f422b47" + "0" * 52})
        digests, version = runner.preflight_ollama(_cfg())
        assert digests["qwen2.5:3b"] == "357c53fb659c" and version == "0.12.0"
        assert digests["nomic-embed-text"] == "0a109f422b47"

    def test_a_missing_model_is_a_clean_error_that_names_the_pull_command(self, monkeypatch):
        self._get(monkeypatch, {"nomic-embed-text:latest": "0a109f422b47"})
        with pytest.raises(runner.EvalError, match="ollama pull qwen2.5:3b"):
            runner.preflight_ollama(_cfg())

    def test_unreachable_ollama_is_a_clean_error(self, monkeypatch):
        def refuse(url, timeout=None):
            raise OSError("connection refused")
        monkeypatch.setattr(runner.httpx, "get", refuse)
        with pytest.raises(runner.EvalError, match="cannot reach Ollama"):
            runner.preflight_ollama(_cfg())


# =========================================================================== model client
class TestSeedShim:
    class FakeHttpx:
        def __init__(self):
            self.posts = []

        def post(self, url, *args, **kwargs):
            self.posts.append((url, kwargs))
            return "response"

        marker = "passthrough"

    def test_seed_is_added_to_ollama_chat_requests_only_and_then_removed(self):
        fake = self.FakeHttpx()
        original = runner.llm_module.httpx
        runner.llm_module.httpx = fake
        try:
            with runner.seeded_ollama(7):
                proxy = runner.llm_module.httpx
                assert proxy.post("http://o/api/chat", json={"model": "m", "options": {"temperature": 0.1}}) == "response"
                proxy.post("http://o/api/embeddings", json={"prompt": "x"})
                assert proxy.marker == "passthrough"
            assert runner.llm_module.httpx is fake
        finally:
            runner.llm_module.httpx = original
        chat, embed = fake.posts
        assert chat[1]["json"]["options"] == {"temperature": 0.1, "seed": 7}
        assert embed[1]["json"] == {"prompt": "x"}

    def test_an_explicit_seed_in_the_request_is_not_overridden(self):
        fake = self.FakeHttpx()
        original = runner.llm_module.httpx
        runner.llm_module.httpx = fake
        try:
            with runner.seeded_ollama(7):
                runner.llm_module.httpx.post("http://o/api/chat", json={"options": {"seed": 99}})
        finally:
            runner.llm_module.httpx = original
        assert fake.posts[0][1]["json"]["options"]["seed"] == 99

    def test_the_shim_is_removed_even_if_the_body_raises(self):
        original = runner.llm_module.httpx
        with pytest.raises(RuntimeError):
            with runner.seeded_ollama(1):
                raise RuntimeError("x")
        assert runner.llm_module.httpx is original


class TestRecordingLLM:
    def _llm(self):
        return runner.RecordingLLM(provider="ollama", model="m")

    def test_calls_are_timed_and_labelled_without_changing_the_result(self, monkeypatch):
        monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat",
                            lambda self, system, user, *a, **k: '{"ok": true}')
        llm = self._llm()
        out = llm._raw_chat("sys", "TASK: Generate API tests\nrest", 8192, 0.1, 100)
        assert out == '{"ok": true}'
        call = llm.calls[0]
        assert call["label"] == "Generate API tests" and call["outcome"] == "ok"
        assert call["response_chars"] == 12 and call["seconds"] >= 0

    def test_a_failing_call_is_recorded_and_re_raised(self, monkeypatch):
        def fail(self, *a, **k):
            raise RuntimeError("down")
        monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat", fail)
        llm = self._llm()
        with pytest.raises(RuntimeError):
            llm._raw_chat("s", "no task header", 1, 0.1, 1)
        assert llm.calls[0]["outcome"] == "other" and llm.calls[0]["label"] == "other"


def test_summary_prompt_stays_in_step_with_the_apps_ingest_prompt():
    deps = (ROOT / "app" / "core" / "deps.py").read_text(encoding="utf-8")
    prompt = runner.summary_prompt("NAME", "EVIDENCE")
    rule_lines = [ln for ln in prompt.splitlines()
                  if ln.startswith("- ") or ln.startswith("Create a clean feature summary")]
    assert len(rule_lines) >= 6
    for line in rule_lines:
        # The app's prompt is an f-string, so its literal braces are doubled in the source.
        assert line.replace("{", "{{").replace("}", "}}") in deps, line


# =========================================================================== robustness
def _http_status_error(status):
    request = httpx.Request("POST", "http://ollama.invalid/api/chat")
    return httpx.HTTPStatusError(f"HTTP {status}", request=request,
                                 response=httpx.Response(status, request=request))


class _CapturingBase:
    """Stands in for the real LLM._raw_chat: records the timeout it was given and replies
    (or raises) as instructed."""

    def __init__(self, monkeypatch, reply='{"ok": true}', raises=None, meta=None):
        self.timeouts = []
        self.options = []          # the per-call request options the client set for each call
        outer = self

        def fake(llm_self, system, user, num_ctx=8192, temperature=0.2, max_tokens=4000,
                 timeout_seconds=None):
            outer.timeouts.append(timeout_seconds)
            outer.options.append(getattr(runner._REQUEST_OPTIONS, "value", None))
            runner._RESPONSE_META.value = meta
            if raises is not None:
                raise raises
            return reply

        monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat", fake)


def _recording(**kw):
    return runner.RecordingLLM(provider="ollama", model="m", **kw)


class TestCallTimeout:
    def test_a_custom_timeout_replaces_the_timeout_of_every_call(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        llm = _recording(call_timeout=1800)
        llm._raw_chat("s", "u", 8192, 0.1, 100, timeout_seconds=180)
        llm._raw_chat("s", "u", 8192, 0.1, 100, timeout_seconds=300)
        llm._raw_chat("s", "u", 8192, 0.1, 100)
        assert base.timeouts == [1800, 1800, 1800]
        assert [c["timeout_seconds"] for c in llm.calls] == [1800, 1800, 1800]

    def test_without_an_override_each_call_keeps_the_pipelines_own_timeout(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        llm = _recording()
        llm._raw_chat("s", "u", 8192, 0.1, 100, timeout_seconds=180)
        llm._raw_chat("s", "u", 8192, 0.1, 100)
        assert base.timeouts == [180, None]
        assert [c["timeout_seconds"] for c in llm.calls] == [180, None]

    def test_the_override_is_confined_to_the_recording_client(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        _recording(call_timeout=1800)              # constructing it must not leak anywhere
        plain = runner.llm_module.LLM(provider="ollama", model="m")
        plain._raw_chat("s", "u", 8192, 0.1, 100, timeout_seconds=180)
        assert base.timeouts == [180]

    def test_the_timeout_is_recorded_in_the_metadata(self):
        cfg = _cfg(call_timeout=1800)
        meta = TestMetadataAndSecrets()._payload(cfg)["meta"]
        assert meta["run_parameters"]["call_timeout_seconds"] == 1800
        assert meta["run_parameters"]["call_timeout_mode"] == "override"

    def test_the_default_is_recorded_as_the_pipelines_own_timeouts(self):
        meta = TestMetadataAndSecrets()._payload(_cfg())["meta"]
        assert meta["run_parameters"]["call_timeout_seconds"] is None
        assert meta["run_parameters"]["call_timeout_mode"] == "pipeline-defaults"

    def test_each_repeat_records_the_timeout_it_ran_with(self):
        run = _run(_cfg(call_timeout=1800))
        assert run["runtime"]["call_timeout_seconds"] == 1800
        assert run["runtime"]["call_timeout_mode"] == "override"

    def test_the_cli_option_is_parsed_validated_and_given_to_the_client(self, monkeypatch, tmp_path):
        assert runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/"]).call_timeout is None
        assert runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/",
                                  "--call-timeout", "1800"]).call_timeout == 1800.0
        for bad in ("0", "-5"):
            with pytest.raises(SystemExit):
                runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/",
                                   "--call-timeout", bad])
        SpyLLM.instances.clear()
        TestModelSelection._wire(monkeypatch)
        runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--call-timeout", "1800",
                     "--out", str(tmp_path / "r.json")])
        assert SpyLLM.instances[0].kwargs["call_timeout"] == 1800.0


class TestCallClassification:
    def test_a_good_reply_is_ok(self, monkeypatch):
        _CapturingBase(monkeypatch, reply='{"summary": "x"}')
        llm = _recording()
        assert llm._raw_chat("s", "u") == '{"summary": "x"}'
        assert llm.calls[0]["outcome"] == "ok" and llm.calls[0]["error_type"] is None

    @pytest.mark.parametrize("exc", [httpx.ReadTimeout("timed out"),
                                     httpx.ConnectTimeout("timed out"),
                                     httpx.PoolTimeout("timed out")])
    def test_timeouts_are_classified_and_re_raised(self, monkeypatch, exc):
        _CapturingBase(monkeypatch, raises=exc)
        llm = _recording()
        with pytest.raises(httpx.TimeoutException):
            llm._raw_chat("s", "u")
        assert llm.calls[0]["outcome"] == "timeout"

    def test_an_http_error_records_the_status(self, monkeypatch):
        _CapturingBase(monkeypatch, raises=_http_status_error(500))
        llm = _recording()
        with pytest.raises(httpx.HTTPStatusError):
            llm._raw_chat("s", "u")
        call = llm.calls[0]
        assert call["outcome"] == "http_error" and call["http_status"] == 500

    @pytest.mark.parametrize("reply", ["this is not json", "", "{}", "[1, 2]", "   "])
    def test_a_reply_the_pipeline_cannot_parse_is_a_parse_error(self, monkeypatch, reply):
        _CapturingBase(monkeypatch, reply=reply)
        llm = _recording()
        assert llm._raw_chat("s", "u") == reply            # the reply is passed on unchanged
        assert llm.calls[0]["outcome"] == "parse_error"

    def test_a_reply_wrapped_in_text_that_the_pipeline_can_still_read_is_ok(self, monkeypatch):
        _CapturingBase(monkeypatch, reply='Sure! {"summary": "x"} hope that helps')
        llm = _recording()
        llm._raw_chat("s", "u")
        assert llm.calls[0]["outcome"] == "ok"

    def test_any_other_failure_is_other_and_keeps_only_the_exception_class(self, monkeypatch):
        leak = "http://admin:hunter2@ollama.internal/api/chat refused"
        _CapturingBase(monkeypatch, raises=ConnectionError(leak))
        llm = _recording()
        with pytest.raises(ConnectionError):
            llm._raw_chat("s", "u")
        call = llm.calls[0]
        assert call["outcome"] == "other" and call["error_type"] == "ConnectionError"
        assert "hunter2" not in json.dumps(call) and "ollama.internal" not in json.dumps(call)

    def test_a_connection_failure_is_an_infrastructure_failure(self, monkeypatch):
        _CapturingBase(monkeypatch, raises=httpx.ConnectError("refused"))
        llm = _recording()
        with pytest.raises(httpx.ConnectError):
            llm._raw_chat("s", "u")
        assert llm.calls[0]["outcome"] == "other"
        assert m.assess_completeness(llm.calls)["complete"] is False

    def test_token_and_timing_metadata_from_the_server_is_recorded(self, monkeypatch):
        _CapturingBase(monkeypatch, meta={"prompt_eval_count": 500, "eval_count": 120,
                                          "eval_duration": 10_000_000_000,
                                          "total_duration": 12_000_000_000,
                                          "done_reason": "stop"})
        llm = _recording()
        llm._raw_chat("s", "u")
        call = llm.calls[0]
        assert call["completion_tokens"] == 120 and call["prompt_tokens"] == 500
        assert call["decode_seconds"] == 10.0 and call["tokens_per_second"] == 12.0
        assert call["done_reason"] == "stop" and call["queue_wait_seconds_estimate"] >= 0

    def test_a_failed_call_never_reuses_the_previous_calls_metadata(self, monkeypatch):
        meta = {"prompt_eval_count": 5, "eval_count": 9, "eval_duration": 1_000_000_000,
                "total_duration": 1_000_000_000}
        base = _CapturingBase(monkeypatch, meta=meta)
        llm = _recording()
        llm._raw_chat("s", "u")
        _CapturingBase(monkeypatch, raises=httpx.ReadTimeout("t"), meta=None)
        with pytest.raises(httpx.TimeoutException):
            llm._raw_chat("s", "u")
        assert llm.calls[1]["completion_tokens"] is None and base.timeouts == [None]

    def test_response_stats_handles_missing_metadata(self):
        stats = runner.response_stats(None, 3.0)
        assert stats["completion_tokens"] is None and stats["tokens_per_second"] is None
        assert stats["queue_wait_seconds_estimate"] is None

    def test_the_http_shim_keeps_the_servers_metadata_for_the_call(self):
        class Resp:
            status_code = 200

            def json(self):
                return {"eval_count": 7, "eval_duration": 1_000_000_000, "message": {"content": "secret"}}

        class Fake:
            def post(self, url, *a, **k):
                return Resp()

        proxy = runner._HttpxWithSeed(Fake(), 1)
        runner._RESPONSE_META.value = None
        proxy.post("http://o/api/chat", json={"model": "m"})
        assert runner._RESPONSE_META.value["eval_count"] == 7
        assert "message" not in runner._RESPONSE_META.value      # the reply text is not kept
        runner._RESPONSE_META.value = None
        proxy.post("http://o/api/embeddings", json={"prompt": "x"})
        assert runner._RESPONSE_META.value is None


class TimeoutSpyLLM(SpyLLM):
    """A model whose every call times out."""

    def chat_json(self, system, user, **kw):
        self.calls.append({"label": "other", "outcome": "timeout", "seconds": 300.0})
        raise httpx.ReadTimeout("timed out")


class TestRepeatCompleteness:
    def test_a_repeat_with_no_infrastructure_failure_is_complete(self):
        run = _run()
        assert run["complete"] is True and run["completeness"]["reasons"] == []
        c = run["completeness"]
        assert (c["attempted_calls"], c["successful_calls"], c["failed_calls"]) == (1, 1, 0)
        assert (c["timeout_count"], c["other_error_count"]) == (0, 0)
        assert run["runtime"]["complete"] is True
        assert run["runtime"]["wall_clock_includes_timeout_waits"] is False

    def test_a_repeat_with_a_timed_out_call_is_incomplete_but_still_ran(self):
        run = _run(llm=TimeoutSpyLLM())
        assert run["ok"] is True and run["complete"] is False
        c = run["completeness"]
        assert c["timeout_count"] == 1 and c["failed_calls"] == 1
        assert "timed out" in c["reasons"][0]
        assert run["runtime"]["wall_clock_includes_timeout_waits"] is True
        assert run["calls"][0]["outcome"] == "timeout"

    def test_an_unreported_filter_block_makes_a_repeat_incomplete(self):
        out = real_shaped_output()
        out.pop("testgen_filter")
        run = _run(pipeline_fn=lambda **kw: out)
        assert run["complete"] is False
        assert "filter statistics" in " ".join(run["completeness"]["reasons"])

    def test_a_repeat_that_raised_is_incomplete_and_keeps_the_calls_it_made(self):
        def boom(**kw):
            raise ValueError("bad")

        run = _run(pipeline_fn=boom)
        assert run["ok"] is False and run["complete"] is False
        assert "raised an exception" in run["completeness"]["reasons"][0]
        assert run["llm_calls"]["attempted"] == 1 and len(run["calls"]) == 1

    def test_pipeline_errors_alone_do_not_make_a_repeat_incomplete(self):
        out = real_shaped_output()
        out["errors"] = ["API worker failed: LLM JSON generation failed after 2 attempts: bad json"]
        run = _run(pipeline_fn=lambda **kw: out)
        assert run["complete"] is True and run["completeness"]["pipeline_error_count"] == 1

    def test_runtime_separates_decode_speed_from_wall_clock(self):
        class MeteredLLM(SpyLLM):
            def chat_json(self, system, user, **kw):
                self.calls.append({"label": "other", "outcome": "ok", "seconds": 40.0,
                                   "completion_tokens": 120, "decode_seconds": 10.0,
                                   "queue_wait_seconds_estimate": 25.0})
                return {"summary": "Users who forgot their password can request a reset link by email."}

        rt = _run(llm=MeteredLLM())["runtime"]
        assert rt["tokens_per_second"] == 12.0 and rt["decode_seconds"] == 10.0
        assert rt["completion_tokens"] == 120 and rt["queue_wait_seconds_estimate"] == 25.0
        assert rt["wall_clock_seconds"] >= 0

    def test_main_exits_1_and_reports_no_valid_baseline_when_nothing_completed(self, monkeypatch, tmp_path):
        TestModelSelection._wire(monkeypatch)
        monkeypatch.setattr(runner, "RecordingLLM", TimeoutSpyLLM)
        out = tmp_path / "r.json"
        rc = runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "2",
                          "--out", str(out)])
        agg = json.loads(out.read_text())["aggregate"]
        assert rc == 1
        assert agg["valid_baseline"] is False and agg["statement"].startswith("NO VALID BASELINE")
        assert agg["repeats_incomplete"] == 2 and agg["metrics"] == {}

    def test_main_exits_0_only_when_every_repeat_is_complete(self, monkeypatch, tmp_path):
        TestModelSelection._wire(monkeypatch)
        rc = runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "2",
                          "--out", str(tmp_path / "r.json")])
        data = json.loads((tmp_path / "r.json").read_text())
        assert rc == 0 and data["aggregate"]["all_repeats_complete"] is True


class TestPerRepeatPersistence:
    ARGS = ["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "3"]

    def test_the_result_file_is_written_after_every_repeat(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        seen = []

        def pipeline(**kw):
            seen.append(json.loads(out.read_text()) if out.exists() else None)
            return fake_pipeline(**kw)

        TestModelSelection._wire(monkeypatch, pipeline)
        rc = runner.main(self.ARGS + ["--out", str(out)])
        assert rc == 0
        assert seen[0] is None                                   # nothing before repeat 1 ends
        assert seen[1]["status"] == "in_progress" and len(seen[1]["runs"]) == 1
        assert seen[2]["status"] == "in_progress" and len(seen[2]["runs"]) == 2
        final = json.loads(out.read_text())
        assert final["status"] == "finished" and len(final["runs"]) == 3
        assert final["repeats_planned"] == 3 and "finished_utc" in final["meta"]
        assert "finished_utc" not in seen[1]["meta"]

    def test_finished_repeats_survive_a_later_repeat_being_interrupted(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        n = {"calls": 0}

        def pipeline(**kw):
            n["calls"] += 1
            if n["calls"] == 3:
                raise KeyboardInterrupt
            return fake_pipeline(**kw)

        TestModelSelection._wire(monkeypatch, pipeline)
        with pytest.raises(KeyboardInterrupt):
            runner.main(self.ARGS + ["--out", str(out)])
        data = json.loads(out.read_text())
        assert data["status"] == "aborted" and data["abort_reason"] == "KeyboardInterrupt"
        assert [r["repeat"] for r in data["runs"]] == [1, 2]
        assert all(r["complete"] for r in data["runs"])
        assert data["aggregate"]["repeats_complete"] == 2

    def test_finished_repeats_survive_an_unexpected_exception_outside_the_repeat(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        TestModelSelection._wire(monkeypatch)
        original = runner.run_repeat
        n = {"calls": 0}

        def flaky(*a, **kw):
            n["calls"] += 1
            if n["calls"] == 2:
                raise RuntimeError("unexpected")
            return original(*a, **kw)

        monkeypatch.setattr(runner, "run_repeat", flaky)
        with pytest.raises(RuntimeError):
            runner.main(self.ARGS + ["--out", str(out)])
        data = json.loads(out.read_text())
        assert data["status"] == "aborted" and data["abort_reason"] == "RuntimeError"
        assert [r["repeat"] for r in data["runs"]] == [1]

    def test_a_failing_save_during_abort_does_not_hide_the_original_error(self, monkeypatch, tmp_path):
        TestModelSelection._wire(monkeypatch, lambda **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
        monkeypatch.setattr(runner, "write_json_atomic",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(KeyboardInterrupt):
            runner.main(self.ARGS + ["--out", str(tmp_path / "r.json")])

    def test_without_out_the_final_json_is_printed(self, monkeypatch, capsys):
        TestModelSelection._wire(monkeypatch)
        runner.main(["--model", "m", "--mongo-uri", "mongodb://x/"])
        assert '"status": "finished"' in capsys.readouterr().out


class TestAtomicWrite:
    def test_writes_valid_json_and_leaves_no_temporary_file(self, tmp_path):
        target = tmp_path / "sub" / "r.json"
        runner.write_json_atomic(target, {"a": 1})
        assert json.loads(target.read_text()) == {"a": 1}
        assert [p.name for p in target.parent.iterdir()] == ["r.json"]

    def test_replaces_an_existing_file(self, tmp_path):
        target = tmp_path / "r.json"
        runner.write_json_atomic(target, {"v": 1})
        runner.write_json_atomic(target, {"v": 2})
        assert json.loads(target.read_text()) == {"v": 2}

    def test_a_failed_write_keeps_the_previous_file_and_cleans_up(self, monkeypatch, tmp_path):
        target = tmp_path / "r.json"
        runner.write_json_atomic(target, {"v": "old"})

        def broken_replace(src, dst):
            raise OSError("simulated crash")

        monkeypatch.setattr(runner.os, "replace", broken_replace)
        with pytest.raises(OSError):
            runner.write_json_atomic(target, {"v": "new"})
        assert json.loads(target.read_text()) == {"v": "old"}
        assert [p.name for p in tmp_path.iterdir()] == ["r.json"]


class TestNoSecretsInRobustnessOutput:
    def test_calls_and_runtime_never_carry_exception_text_or_the_database_uri(self, monkeypatch, tmp_path):
        uri = "mongodb://evaluser:Sup3rS3cretPw@db.internal.example:27017/?authSource=admin"
        _CapturingBase(monkeypatch, raises=OSError(f"cannot reach {uri} with Sup3rS3cretPw"))
        llm = _recording(call_timeout=1800)
        with pytest.raises(OSError):
            llm._raw_chat("s", "u")
        run = _run(_cfg(mongo_uri=uri, call_timeout=1800), llm=TimeoutSpyLLM())
        run["calls"] = run.get("calls", []) + llm.calls
        text = json.dumps({"run": run, "agg": m.aggregate_repeats([run])}, default=str)
        for secret in ("Sup3rS3cretPw", "evaluser", "db.internal.example"):
            assert secret not in text


# =========================================================================== output cap
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402


class TestOutputCap:
    def test_the_default_is_the_pipelines_own_limit(self):
        assert _recording().output_cap == "pipeline"
        assert _cfg().output_cap == "pipeline"
        args = runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/"])
        assert args.max_output_tokens == "pipeline"

    def test_pipeline_mode_sends_each_calls_own_max_tokens_as_the_cap(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        llm = _recording()
        llm._raw_chat("s", "u", 8192, 0.1, 6500, timeout_seconds=180)
        llm._raw_chat("s", "u", 8192, 0.1, 3000)
        llm._raw_chat("s", "u", 8192, 0.1, 10000, timeout_seconds=300)
        assert base.options == [{"num_predict": 6500}, {"num_predict": 3000},
                                {"num_predict": 10000}]
        assert [c["output_cap_tokens"] for c in llm.calls] == [6500, 3000, 10000]
        assert [c["max_tokens_requested"] for c in llm.calls] == [6500, 3000, 10000]

    def test_a_fixed_cap_applies_to_every_call(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        llm = _recording(output_cap=4096)
        for requested in (10000, 3000, 6500):
            llm._raw_chat("s", "u", 8192, 0.1, requested)
        assert base.options == [{"num_predict": 4096}] * 3
        assert [c["output_cap_tokens"] for c in llm.calls] == [4096] * 3
        assert [c["max_tokens_requested"] for c in llm.calls] == [10000, 3000, 6500]

    def test_none_sends_no_cap_exactly_as_the_app_does(self, monkeypatch):
        base = _CapturingBase(monkeypatch)
        llm = _recording(output_cap="none")
        llm._raw_chat("s", "u", 8192, 0.1, 6500)
        assert base.options == [None]
        assert llm.calls[0]["output_cap_tokens"] is None

    @pytest.mark.parametrize("requested", [None, 0, -5, "6500", 1.5])
    def test_pipeline_mode_sends_no_cap_when_the_call_has_no_usable_limit(self, monkeypatch, requested):
        base = _CapturingBase(monkeypatch)
        _recording()._raw_chat("s", "u", 8192, 0.1, requested)
        assert base.options == [None]

    def test_the_cap_does_not_outlive_the_call_even_when_it_fails(self, monkeypatch):
        _CapturingBase(monkeypatch)
        llm = _recording()
        llm._raw_chat("s", "u", 8192, 0.1, 6500)
        assert runner._REQUEST_OPTIONS.value is None
        _CapturingBase(monkeypatch, raises=httpx.ReadTimeout("t"))
        with pytest.raises(httpx.TimeoutException):
            llm._raw_chat("s", "u", 8192, 0.1, 6500)
        assert runner._REQUEST_OPTIONS.value is None

    def test_the_cap_is_per_thread_so_parallel_workers_do_not_mix_up(self, monkeypatch):
        seen = {}
        gate = threading.Barrier(2)

        def fake(llm_self, system, user, num_ctx=8192, temperature=0.2, max_tokens=4000,
                 timeout_seconds=None):
            gate.wait(timeout=10)                  # both calls are in flight together
            seen[user] = getattr(runner._REQUEST_OPTIONS, "value", None)
            return '{"ok": true}'

        monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat", fake)
        llm = _recording()
        threads = [threading.Thread(target=llm._raw_chat, args=("s", name, 8192, 0.1, cap))
                   for name, cap in (("a", 3000), ("b", 10000))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        assert seen == {"a": {"num_predict": 3000}, "b": {"num_predict": 10000}}

    @pytest.mark.parametrize("text,expected", [("pipeline", "pipeline"), ("PIPELINE", "pipeline"),
                                               ("none", "none"), ("None", "none"),
                                               ("8000", 8000), (" 12 ", 12)])
    def test_the_cli_value_is_parsed(self, text, expected):
        args = runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/",
                                  "--max-output-tokens", text])
        assert args.max_output_tokens == expected

    @pytest.mark.parametrize("bad", ["abc", "0", "-3", "1.5", ""])
    def test_a_bad_cli_value_is_rejected(self, bad):
        with pytest.raises(SystemExit):
            runner.parse_args(["--model", "m", "--mongo-uri", "mongodb://x/",
                               "--max-output-tokens", bad])

    @pytest.mark.parametrize("cap,mode,tokens", [("pipeline", "pipeline", None),
                                                 ("none", "none", None), (4096, "fixed", 4096)])
    def test_the_cap_is_recorded_in_the_metadata_and_in_each_repeat(self, cap, mode, tokens):
        cfg = _cfg(output_cap=cap)
        params = TestMetadataAndSecrets()._payload(cfg)["meta"]["run_parameters"]
        assert params["output_cap_mode"] == mode and params["output_cap_tokens"] == tokens
        assert params["output_cap_rule"] == runner.OUTPUT_CAP_RULES[mode]
        runtime = _run(cfg)["runtime"]
        assert runtime["output_cap_mode"] == mode and runtime["output_cap_tokens"] == tokens

    def test_main_gives_the_chosen_cap_to_the_client(self, monkeypatch, tmp_path):
        SpyLLM.instances.clear()
        TestModelSelection._wire(monkeypatch)
        runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--max-output-tokens", "8000",
                     "--out", str(tmp_path / "r.json")])
        assert SpyLLM.instances[0].kwargs["output_cap"] == 8000
        SpyLLM.instances.clear()
        runner.main(["--model", "m", "--mongo-uri", "mongodb://x/", "--out", str(tmp_path / "r.json")])
        assert SpyLLM.instances[0].kwargs["output_cap"] == "pipeline"


class _FakeHttpx:
    """Records Ollama chat request bodies; replies like Ollama does."""

    def __init__(self, done_reason="stop", eval_count=10, content='{"ok": true}'):
        self.bodies = []
        self.reply = {"message": {"content": content}, "prompt_eval_count": 5,
                      "eval_count": eval_count, "eval_duration": 1_000_000_000,
                      "total_duration": 1_000_000_000, "done_reason": done_reason}

    def post(self, url, *args, **kwargs):
        self.bodies.append(kwargs.get("json"))
        reply = self.reply

        class Response:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return reply

        return Response()


class TestProductionClientIsUntouched:
    def test_the_apps_client_sends_no_output_cap_and_no_seed(self, monkeypatch):
        fake = _FakeHttpx()
        monkeypatch.setattr(runner.llm_module, "httpx", fake)
        runner.llm_module.LLM(provider="ollama", model="m")._raw_chat("s", "u", 8192, 0.1, 6500)
        options = fake.bodies[0]["options"]
        assert "num_predict" not in options and "seed" not in options

    def test_the_benchmark_client_sends_the_cap_and_the_seed_only_while_it_runs(self, monkeypatch):
        fake = _FakeHttpx()
        monkeypatch.setattr(runner.llm_module, "httpx", fake)
        with runner.seeded_ollama(7):
            _recording()._raw_chat("s", "u", 8192, 0.1, 6500)
            runner.llm_module.LLM(provider="ollama", model="m")._raw_chat("s", "u", 8192, 0.1, 6500)
        runner.llm_module.LLM(provider="ollama", model="m")._raw_chat("s", "u", 8192, 0.1, 6500)
        bench, plain_during, plain_after = (b["options"] for b in fake.bodies)
        assert bench["num_predict"] == 6500 and bench["seed"] == 7
        # A plain client inside the shim gets no cap (none was set for its call) ...
        assert "num_predict" not in plain_during
        # ... and nothing remains after the shim is removed.
        assert "num_predict" not in plain_after and "seed" not in plain_after

    def test_no_output_limit_was_added_to_the_production_llm_module(self):
        source = (ROOT / "app" / "llm.py").read_text(encoding="utf-8")
        assert "num_predict" not in source

    def test_the_shim_never_overrides_an_explicit_value_or_touches_other_endpoints(self):
        class Fake:
            def __init__(self):
                self.calls = []

            def post(self, url, *a, **k):
                self.calls.append((url, k.get("json")))

                class R:
                    def json(self):
                        return {}
                return R()

        fake = Fake()
        proxy = runner._HttpxWithSeed(fake, 1)
        runner._REQUEST_OPTIONS.value = {"num_predict": 500}
        try:
            proxy.post("http://o/api/chat", json={"options": {"num_predict": 99}})
            proxy.post("http://o/api/embeddings", json={"prompt": "x"})
        finally:
            runner._REQUEST_OPTIONS.value = None
        assert fake.calls[0][1]["options"]["num_predict"] == 99
        assert fake.calls[1][1] == {"prompt": "x"}


class TestLengthLimited:
    META = {"prompt_eval_count": 6000, "eval_duration": 10_000_000_000,
            "total_duration": 10_000_000_000}

    def _call(self, monkeypatch, *, reply, done_reason, tokens, output_cap="pipeline", max_tokens=6500):
        meta = {**self.META, "eval_count": tokens}
        if done_reason is not None:
            meta["done_reason"] = done_reason
        _CapturingBase(monkeypatch, reply=reply, meta=meta)
        llm = _recording(output_cap=output_cap)
        llm._raw_chat("s", "u", 8192, 0.1, max_tokens)
        return llm.calls[0]

    def test_a_reply_cut_off_at_the_cap_is_length_limited_and_never_ok(self, monkeypatch):
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason="length", tokens=6500)
        assert call["outcome"] == "length_limited" and call["done_reason"] == "length"
        assert call["output_cap_tokens"] == 6500 and call["completion_tokens"] == 6500
        assert call["parse_ok"] is True

    def test_length_limited_takes_precedence_over_parse_error_and_records_parseability(self, monkeypatch):
        call = self._call(monkeypatch, reply="not json at all", done_reason="length", tokens=6500)
        assert call["outcome"] == "length_limited" and call["parse_ok"] is False

    def test_a_natural_stop_exactly_at_the_cap_is_still_ok(self, monkeypatch):
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason="stop", tokens=6500)
        assert call["outcome"] == "ok" and call["parse_ok"] is None

    def test_without_a_done_reason_reaching_the_cap_is_inferred_as_length_limited(self, monkeypatch):
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason=None, tokens=6500)
        assert call["outcome"] == "length_limited"
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason=None, tokens=6499)
        assert call["outcome"] == "ok"

    def test_without_a_cap_and_without_a_done_reason_nothing_is_inferred(self, monkeypatch):
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason=None, tokens=99999,
                          output_cap="none")
        assert call["outcome"] == "ok"

    def test_a_length_stop_reported_by_the_server_counts_even_with_no_cap_sent(self, monkeypatch):
        call = self._call(monkeypatch, reply='{"ok": true}', done_reason="length", tokens=8000,
                          output_cap="none")
        assert call["outcome"] == "length_limited"

    def test_failures_keep_their_classification_when_a_cap_is_set(self, monkeypatch):
        _CapturingBase(monkeypatch, raises=httpx.ReadTimeout("t"), meta=self.META)
        llm = _recording()
        with pytest.raises(httpx.TimeoutException):
            llm._raw_chat("s", "u", 8192, 0.1, 6500)
        assert llm.calls[0]["outcome"] == "timeout"
        assert llm.calls[0]["output_cap_tokens"] == 6500 and llm.calls[0]["parse_ok"] is None

    def test_a_plain_parse_error_is_not_mistaken_for_a_length_stop(self, monkeypatch):
        call = self._call(monkeypatch, reply="not json", done_reason="stop", tokens=40)
        assert call["outcome"] == "parse_error"


class LengthSpyLLM(SpyLLM):
    """A model whose first call was cut off at the output cap."""

    def chat_json(self, system, user, **kw):
        self.calls.append({"label": "other", "outcome": "length_limited", "seconds": 90.0,
                           "output_cap_tokens": 6500, "completion_tokens": 6500,
                           "decode_seconds": 380.0, "done_reason": "length", "parse_ok": False})
        return {"summary": "Users who forgot their password can request a reset link by email."}


class TestLengthLimitedIsReportedNotHidden:
    def test_it_does_not_make_a_repeat_incomplete_but_is_counted_and_noted(self):
        run = _run(llm=LengthSpyLLM())
        c = run["completeness"]
        assert run["complete"] is True and c["reasons"] == []
        assert c["length_limited_count"] == 1
        assert c["successful_calls"] == 0 and c["answered_calls"] == 1 and c["failed_calls"] == 1
        assert "stopped at the output token cap" in c["notes"][0]
        assert run["llm_calls"]["length_limited"] == 1
        assert run["runtime"]["length_limited_calls"] == 1

    def test_it_shows_up_in_the_progress_line_and_the_aggregate_notes(self):
        run = _run(llm=LengthSpyLLM())
        assert "1 call(s) stopped at the output cap" in runner.summarize_run_line(run)
        agg = m.aggregate_repeats([run], planned=1)
        assert agg["valid_baseline"] is True
        assert agg["notes"] and "output token cap" in agg["notes"][0]
        assert agg["metrics"]["model_call_length_limited"]["mean"] == 1.0

    def test_a_clean_repeat_has_no_notes(self):
        run = _run()
        assert run["completeness"]["notes"] == [] and run["runtime"]["length_limited_calls"] == 0

    def test_metrics_level_rules(self):
        calls = [{"outcome": "ok"}, {"outcome": "length_limited"}, {"outcome": "parse_error"}]
        c = m.assess_completeness(calls)
        assert c["complete"] is True and c["length_limited_count"] == 1 and c["parse_error_count"] == 1
        assert len(c["notes"]) == 2
        assert m.call_outcome({"outcome": "length_limited"}) == "length_limited"
        assert "length_limited" in m.MODEL_OUTPUT_ISSUES
        assert "length_limited" not in m.INFRASTRUCTURE_FAILURES
        s = m.llm_call_summary(calls)
        assert (s["successful"], s["answered"], s["failed"]) == (1, 3, 2)


class TestValidBaselineEndToEnd:
    ARGS = ["--model", "m", "--mongo-uri", "mongodb://x/", "--repeats", "3"]

    def _flaky_repeat(self, monkeypatch, bad_repeat):
        TestModelSelection._wire(monkeypatch)
        made = {"n": 0}

        def factory(**kw):
            made["n"] += 1
            return (TimeoutSpyLLM if made["n"] == bad_repeat else SpyLLM)(**kw)

        monkeypatch.setattr(runner, "RecordingLLM", factory)

    def test_one_incomplete_repeat_out_of_three_is_not_a_valid_baseline(self, monkeypatch, tmp_path):
        self._flaky_repeat(monkeypatch, bad_repeat=2)
        out = tmp_path / "r.json"
        rc = runner.main(self.ARGS + ["--out", str(out)])
        agg = json.loads(out.read_text())["aggregate"]
        assert rc == 1
        assert agg["repeats_complete"] == 2 and agg["repeats_incomplete"] == 1
        assert agg["valid_baseline"] is False and agg["all_repeats_complete"] is False
        assert agg["metrics"] == {}
        assert agg["provisional_metrics"]["generated"]["n"] == 2
        assert agg["statement"].startswith("NOT A VALID BASELINE: 2 of 3 requested repeats")

    def test_three_complete_repeats_are_a_valid_baseline(self, monkeypatch, tmp_path):
        TestModelSelection._wire(monkeypatch)
        out = tmp_path / "r.json"
        rc = runner.main(self.ARGS + ["--out", str(out)])
        agg = json.loads(out.read_text())["aggregate"]
        assert rc == 0
        assert agg["valid_baseline"] is True and agg["all_repeats_complete"] is True
        assert agg["metrics"]["generated"]["n"] == 3 and agg["provisional_metrics"] == {}
        assert agg["statement"].startswith("VALID BASELINE")

    def test_an_interrupted_run_is_never_a_valid_baseline(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        n = {"calls": 0}

        def pipeline(**kw):
            n["calls"] += 1
            if n["calls"] == 3:
                raise KeyboardInterrupt
            return fake_pipeline(**kw)

        TestModelSelection._wire(monkeypatch, pipeline)
        with pytest.raises(KeyboardInterrupt):
            runner.main(self.ARGS + ["--out", str(out)])
        agg = json.loads(out.read_text())["aggregate"]
        assert agg["repeats_complete"] == 2 and agg["repeats_missing"] == 1
        assert agg["valid_baseline"] is False and agg["metrics"] == {}
        assert "1 not run" in agg["statement"]

    def test_the_in_progress_file_is_not_a_baseline_yet(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        seen = []

        def pipeline(**kw):
            seen.append(json.loads(out.read_text())["aggregate"] if out.exists() else None)
            return fake_pipeline(**kw)

        TestModelSelection._wire(monkeypatch, pipeline)
        runner.main(self.ARGS + ["--out", str(out)])
        assert seen[1]["valid_baseline"] is False and seen[1]["repeats_missing"] == 2
        assert seen[2]["valid_baseline"] is False and seen[2]["repeats_missing"] == 1


class _FakeOllamaServer:
    """A real local HTTP server that behaves like Ollama's /api/chat."""

    def __init__(self, done_reason, eval_count, content):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                payload = {"message": {"content": content}, "prompt_eval_count": 40,
                           "eval_count": eval_count, "eval_duration": 2_000_000_000,
                           "total_duration": 2_500_000_000, "done_reason": done_reason}
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TestOverRealHttp:
    def test_the_cap_reaches_the_server_and_a_length_stop_is_classified(self):
        server = _FakeOllamaServer("length", 6500, "cut off mid")
        try:
            llm = runner.RecordingLLM(provider="ollama", model="m", ollama_url=server.url)
            with runner.seeded_ollama(42):
                llm._raw_chat("sys", "TASK: x", 8192, 0.1, 6500, timeout_seconds=30)
        finally:
            server.close()
        sent = server.requests[0]["options"]
        assert sent["num_predict"] == 6500 and sent["seed"] == 42 and sent["num_ctx"] == 8192
        call = llm.calls[0]
        assert call["outcome"] == "length_limited" and call["done_reason"] == "length"
        assert call["completion_tokens"] == 6500 and call["tokens_per_second"] == 3250.0

    def test_the_apps_own_client_sends_no_cap_to_the_same_server(self):
        server = _FakeOllamaServer("stop", 10, '{"ok": true}')
        try:
            runner.llm_module.LLM(provider="ollama", model="m", ollama_url=server.url)._raw_chat(
                "sys", "u", 8192, 0.1, 6500, timeout_seconds=30)
        finally:
            server.close()
        assert "num_predict" not in server.requests[0]["options"]
