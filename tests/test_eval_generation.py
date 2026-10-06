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
    def test_rollup(self):
        calls = [{"seconds": 2.0, "prompt_chars": 100, "response_chars": 10, "ok": True},
                 {"seconds": 4.0, "prompt_chars": 50, "response_chars": 0, "ok": False}]
        s = m.llm_call_summary(calls)
        assert s == {"count": 2, "failed": 1, "total_seconds": 6.0, "max_seconds": 4.0,
                     "mean_seconds": 3.0, "prompt_chars": 150, "response_chars": 10}

    def test_empty_has_no_mean(self):
        s = m.llm_call_summary([])
        assert s["count"] == 0 and s["mean_seconds"] is None and s["max_seconds"] is None

    def test_junk_entries_are_ignored(self):
        s = m.llm_call_summary([None, "x", {"seconds": "slow"}, {"seconds": 1.0}])
        assert s["count"] == 2 and s["total_seconds"] == 1.0


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
    def _run(generated, exemplar, seconds, ok=True):
        return {"ok": ok,
                "filter": m.summarize_filter({"generated": generated, "persisted": generated - exemplar,
                                              "rejected": exemplar,
                                              "rejected_by_reason": {"exemplar-copy": exemplar}}),
                "timings": {"pipeline_seconds": seconds, "ingest_seconds": 1.0},
                "requirement_coverage": {"rate": 0.5}, "requirement_gaps": {"count": 2},
                "usage": {"prompt_tokens": 100, "completion_tokens": 10}}

    def test_mean_min_max_across_successful_repeats(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0), self._run(10, 4, 140.0)])
        assert agg["repeats_total"] == 2 and agg["repeats_ok"] == 2
        ex = agg["metrics"]["exemplar_copy_rate"]
        assert (ex["n"], ex["mean"], ex["min"], ex["max"]) == (2, 0.3, 0.2, 0.4)
        assert agg["metrics"]["pipeline_seconds"]["mean"] == 120.0

    def test_failed_repeats_are_counted_but_excluded(self):
        agg = m.aggregate_repeats([self._run(10, 2, 100.0), {"ok": False, "error": "x"}])
        assert agg["repeats_total"] == 2 and agg["repeats_ok"] == 1
        assert agg["metrics"]["generated"]["n"] == 1

    def test_none_values_do_not_count_toward_n(self):
        zero = self._run(0, 0, 50.0)       # zero generated -> rates are None
        agg = m.aggregate_repeats([zero, self._run(10, 2, 100.0)])
        assert agg["metrics"]["exemplar_copy_rate"]["n"] == 1
        assert agg["metrics"]["exemplar_copy_count"]["n"] == 2

    def test_grounding_survivors_are_aggregated_when_present(self):
        a, b = self._run(10, 2, 100.0), self._run(10, 2, 100.0)
        a["grounding_survivors"] = {"entities": 0, "apis": 2, "ui_components": 1}
        b["grounding_survivors"] = {"entities": 2, "apis": 2, "ui_components": 3}
        agg = m.aggregate_repeats([a, b])["metrics"]
        assert agg["grounding_entities"]["mean"] == 1.0 and agg["grounding_ui_components"]["max"] == 3
        assert "grounding_apis" in agg
        assert "grounding_entities" not in m.aggregate_repeats([self._run(10, 2, 1.0)])["metrics"]

    def test_nothing_to_aggregate(self):
        assert m.aggregate_repeats([]) == {"repeats_total": 0, "repeats_ok": 0, "metrics": {}}
        assert m.aggregate_repeats([None, "x"])["repeats_total"] == 0

    def test_unavailable_filter_contributes_no_filter_metrics(self):
        agg = m.aggregate_repeats([{"ok": True, "filter": {"available": False},
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
        self.calls.append({"label": "other", "seconds": 0.5, "prompt_chars": 10,
                           "response_chars": 5, "ok": True})
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
        assert call["label"] == "Generate API tests" and call["ok"] is True
        assert call["response_chars"] == 12 and call["seconds"] >= 0

    def test_a_failing_call_is_recorded_and_re_raised(self, monkeypatch):
        def fail(self, *a, **k):
            raise RuntimeError("down")
        monkeypatch.setattr(runner.llm_module.LLM, "_raw_chat", fail)
        llm = self._llm()
        with pytest.raises(RuntimeError):
            llm._raw_chat("s", "no task header", 1, 0.1, 1)
        assert llm.calls[0]["ok"] is False and llm.calls[0]["label"] == "other"


def test_summary_prompt_stays_in_step_with_the_apps_ingest_prompt():
    deps = (ROOT / "app" / "core" / "deps.py").read_text(encoding="utf-8")
    prompt = runner.summary_prompt("NAME", "EVIDENCE")
    rule_lines = [ln for ln in prompt.splitlines()
                  if ln.startswith("- ") or ln.startswith("Create a clean feature summary")]
    assert len(rule_lines) >= 6
    for line in rule_lines:
        # The app's prompt is an f-string, so its literal braces are doubled in the source.
        assert line.replace("{", "{{").replace("}", "}}") in deps, line
