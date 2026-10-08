"""The accuracy harness must itself be trustworthy, so it is tested like any other code.

The two offline sections (adversarial grounding probes, dedup pairs) run in CI with no
model and no database. They are expected to score 1.0 — they measure deterministic logic,
so any drop is a real regression rather than model noise.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from testgen.lineage import lineage_token_set, token_set_similarity

from tests.eval import dataset, run_eval
from tests.eval.run_eval import (
    _confusion,
    _dataset_fingerprint,
    _overclaim_rate,
    _reuse_same,
    _run_metadata,
    _scoring_corpus,
    main,
    run_coverage,
    run_dedup,
    run_probes,
)


class TestHallucinationProbes:
    def test_grounding_catches_every_adversarial_claim(self):
        r = run_probes()
        failed = [row for row in r["rows"] if not row["pass"]]
        assert failed == [], f"grounding layer regressed on: {failed}"
        assert r["score"] == 1.0

    def test_control_probe_is_not_degraded(self):
        # The guard must not achieve its score by rejecting everything.
        r = run_probes()
        control = next(row for row in r["rows"] if row["id"] == "probe-honest-covered")
        assert control["actual"] == "covered"
        assert control["rejected"] == []

    def test_probe_set_contains_a_positive_control(self):
        assert any(p["expected_status"] == "covered"
                   for p in dataset.HALLUCINATION_PROBES)


class TestDedupScoring:
    def test_decidable_pairs_all_decided_correctly(self):
        r = run_dedup()
        failed = [row for row in r["rows"] if not row["pass"]]
        assert failed == [], f"dedup regressed on: {failed}"
        assert r["false_merge"] == 0        # never collapse two distinct behaviours

    def test_id_paths_normalize_to_the_same_case(self):
        pair = next(p for p in dataset.DEDUP_PAIRS if p["id"] == "same-path-id-normalized")
        assert _reuse_same(pair["a"], pair["b"]) is True

    def test_different_status_codes_are_never_merged(self):
        pair = next(p for p in dataset.DEDUP_PAIRS if p["id"] == "diff-status-same-endpoint")
        assert _reuse_same(pair["a"], pair["b"]) is False

    def test_known_limitations_are_reported_not_scored(self):
        # The measured overlap must stay visible without failing the gate, so nobody
        # "fixes" it by tuning a constant until the suite goes green.
        r = run_dedup()
        assert r["known_limitations"], "the measured limitation set went missing"
        assert r["score"] == 1.0, "limitations must not be folded into the score"


class TestMeasuredOverlapFinding:
    """Pins the measurement that says token-set Jaccard can't separate these classes.

    If these numbers move, the finding recorded in dataset.KNOWN_LIMITATION_PAIRS is
    stale and the accompanying analysis needs redoing.
    """

    def _sim(self, pair_id):
        p = next(x for x in dataset.KNOWN_LIMITATION_PAIRS if x["id"] == pair_id)
        return round(token_set_similarity(lineage_token_set(p["a"]),
                                          lineage_token_set(p["b"])), 3)

    def test_distinct_pairs_score_higher_than_a_duplicate_pair(self):
        same = self._sim("limit-same-functional-rewording")
        assert self._sim("limit-diff-delete-object") > same
        assert self._sim("limit-diff-export-format") > same

    def test_no_threshold_can_separate_the_classes(self):
        sames = [self._sim(p["id"]) for p in dataset.KNOWN_LIMITATION_PAIRS
                 if p["expected_same"]]
        diffs = [self._sim(p["id"]) for p in dataset.KNOWN_LIMITATION_PAIRS
                 if not p["expected_same"]]
        # A separating threshold would need min(same) > max(diff). It doesn't exist.
        assert min(sames) < max(diffs), (
            "classes are now separable — re-derive the threshold and update the analysis")


class TestScoringMath:
    def test_confusion_counts_and_accuracy(self):
        pairs = [("covered", "covered"), ("covered", "partial"),
                 ("uncovered", "uncovered"), ("partial", "partial")]
        c = _confusion(pairs)
        assert c["n"] == 4
        assert c["accuracy"] == 0.75
        assert c["per_status"]["covered"]["support"] == 2
        assert c["per_status"]["covered"]["recall"] == 0.5

    def test_overclaim_rate_only_counts_the_dangerous_direction(self):
        # said covered when it was uncovered -> overclaim; the reverse is not.
        assert _overclaim_rate([("uncovered", "covered")]) == 1.0
        assert _overclaim_rate([("covered", "uncovered")]) == 0.0
        assert _overclaim_rate([("partial", "covered"), ("covered", "partial")]) == 0.5

    def test_empty_input_does_not_divide_by_zero(self):
        assert _confusion([])["accuracy"] is None
        assert _overclaim_rate([]) is None


class TestCli:
    def test_default_run_passes_and_exits_zero(self, capsys):
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "hallucination_probes" in out
        assert "dedup" in out

    def test_json_output_is_parseable(self, capsys):
        import json
        assert main(["--probes", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["failures"] == []
        assert payload["reports"][0]["section"] == "hallucination_probes"

    def test_impossible_threshold_fails_the_run(self, capsys):
        # Proves the gate can actually fail, so a green CI run means something.
        assert main(["--probes", "--min-probes", "1.1"]) == 1
        assert "FAILED thresholds" in capsys.readouterr().out


class TestDatasetIntegrity:
    def test_every_expected_id_exists_in_its_case_list(self):
        for ex in dataset.COVERAGE_EXAMPLES:
            case_ids = {c["id"] for c in ex["cases"]}
            unknown = set(ex["expected"]) - case_ids
            assert not unknown, f"{ex['id']} labels unknown case(s): {unknown}"

    def test_labels_use_the_documented_vocabulary(self):
        for ex in dataset.COVERAGE_EXAMPLES:
            for cid, label in ex["expected"].items():
                assert label in ("covered", "partial", "uncovered"), f"{ex['id']}/{cid}"

    def test_every_example_documents_why_it_is_labelled_that_way(self):
        # The note is the audit trail for a human-assigned label; without it the label
        # is unreviewable and the dataset rots.
        for ex in dataset.COVERAGE_EXAMPLES:
            assert ex.get("note"), f"{ex['id']} has no rationale for its labels"
        for p in dataset.HALLUCINATION_PROBES:
            assert p.get("note"), f"{p['id']} has no rationale"


class TestRunMetadata:
    """Reproducibility metadata (#43 needs to be able to compare runs across models
    later, which requires knowing exactly what corpus and when a run scored)."""

    def test_fingerprint_is_stable_across_calls(self):
        assert _dataset_fingerprint() == _dataset_fingerprint()

    def test_fingerprint_changes_if_the_scored_content_changes(self, monkeypatch):
        before = _dataset_fingerprint()
        patched = list(dataset.HALLUCINATION_PROBES)
        patched[0] = dict(patched[0], expected_status="uncovered")
        monkeypatch.setattr(dataset, "HALLUCINATION_PROBES", patched)
        assert _dataset_fingerprint() != before

    def test_fingerprint_ignores_note_text_only_changes(self, monkeypatch):
        # A wording fix to the audit-trail note must not look like a corpus change.
        before = _dataset_fingerprint()
        patched = list(dataset.HALLUCINATION_PROBES)
        patched[0] = dict(patched[0], note="reworded, same claim/expectation")
        monkeypatch.setattr(dataset, "HALLUCINATION_PROBES", patched)
        assert _dataset_fingerprint() == before

    def test_metadata_never_labels_offline_sections_with_a_model(self):
        args = argparse.Namespace(coverage=False, provider="ollama", model="qwen2.5:7b")
        meta = _run_metadata(args, [run_probes()])
        assert meta["provider"] is None
        assert meta["model"] is None
        assert meta["sections_run"] == ["hallucination_probes"]

    def test_metadata_labels_the_model_only_when_coverage_ran(self):
        args = argparse.Namespace(coverage=True, provider="openai", model="gpt-4o-mini")
        meta = _run_metadata(args, [])
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o-mini"

    def test_metadata_has_no_api_key_or_ollama_url_field(self):
        # Locks in the "never include secrets" requirement structurally, not just by
        # inspection -- these two fields must never exist on the metadata dict at all.
        args = argparse.Namespace(coverage=True, provider="openai", model="gpt-4o-mini",
                                  api_key="sk-should-never-appear", ollama_url="http://x")
        meta = _run_metadata(args, [])
        assert "api_key" not in meta
        assert "ollama_url" not in meta
        assert "sk-should-never-appear" not in json.dumps(meta)


class TestJsonPayloadIncludesMetadata:
    def test_json_payload_has_a_meta_block(self, capsys):
        assert main(["--probes", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["dataset_fingerprint"]
        assert payload["meta"]["timestamp"]
        # Existing shape (already relied on elsewhere) must still be present.
        assert payload["failures"] == []
        assert payload["reports"][0]["section"] == "hallucination_probes"

    def test_no_secret_ever_appears_in_json_output_even_with_an_api_key_passed(self, capsys):
        assert main(["--probes", "--json", "--api-key", "sk-super-secret-value"]) == 0
        out = capsys.readouterr().out
        assert "sk-super-secret-value" not in out


class TestOutFile:
    def test_out_writes_the_same_payload_json_can_parse(self, tmp_path, capsys):
        out_path = tmp_path / "result.json"
        assert main(["--probes", "--out", str(out_path)]) == 0
        capsys.readouterr()  # human-readable output on stdout, not under test here
        payload = json.loads(out_path.read_text())
        assert payload["meta"]["dataset_fingerprint"]
        assert payload["reports"][0]["section"] == "hallucination_probes"

    def test_out_is_written_even_without_the_json_flag(self, tmp_path):
        out_path = tmp_path / "result.json"
        assert main(["--probes", "--out", str(out_path)]) == 0
        assert out_path.exists()

    def test_out_never_contains_a_passed_api_key(self, tmp_path):
        out_path = tmp_path / "result.json"
        main(["--probes", "--out", str(out_path), "--api-key", "sk-super-secret-value"])
        assert "sk-super-secret-value" not in out_path.read_text()


class TestCoverageWiring:
    """run_coverage()'s own wiring (pairs/rows construction, confusion matrix,
    overclaim rate) has no test today unless a real LLM is reachable -- this covers
    it with a mocked review_code_coverage() call instead, per the ground rule that
    eval-infra tests must not require real paid API credentials."""

    def test_perfect_verdicts_score_1_0_with_no_overclaim(self, monkeypatch):
        def fake_review(llm, feature_name, requirement, cases, code_excerpts,
                        samples=1, progress=None, contract_findings=None):
            ex = next(e for e in dataset.COVERAGE_EXAMPLES if e["cases"] == cases)
            return {"cases": [{"test_case_id": cid, "status": status, "confidence": 0.9,
                              "needs_review": False, "files_rejected": []}
                             for cid, status in ex["expected"].items()]}

        monkeypatch.setattr(run_eval.cov, "review_code_coverage", fake_review)
        r = run_coverage(llm=object())
        assert r["section"] == "coverage"
        assert r["score"] == 1.0
        assert r["overclaim_rate"] == 0.0

    def test_overclaiming_verdicts_are_detected(self, monkeypatch):
        def fake_review_overclaims(llm, feature_name, requirement, cases, code_excerpts,
                                   samples=1, progress=None, contract_findings=None):
            ex = next(e for e in dataset.COVERAGE_EXAMPLES if e["cases"] == cases)
            # Claim everything is "covered" regardless of ground truth -- the
            # dangerous direction (see run_eval._overclaim_rate's own docstring).
            return {"cases": [{"test_case_id": cid, "status": "covered", "confidence": 0.9,
                              "needs_review": False, "files_rejected": []}
                             for cid in ex["expected"]]}

        monkeypatch.setattr(run_eval.cov, "review_code_coverage", fake_review_overclaims)
        r = run_coverage(llm=object())
        assert r["overclaim_rate"] > 0
        assert r["score"] < 1.0

    def test_missing_case_id_in_the_response_counts_as_uncovered_not_a_crash(self, monkeypatch):
        def fake_review_empty(llm, feature_name, requirement, cases, code_excerpts,
                              samples=1, progress=None, contract_findings=None):
            return {"cases": []}   # model returned nothing for this batch

        monkeypatch.setattr(run_eval.cov, "review_code_coverage", fake_review_empty)
        r = run_coverage(llm=object())
        assert r["section"] == "coverage"
        assert all(row["actual"] == "uncovered" for row in r["rows"])
        # ...but a model that returned nothing is distinguishable from one that answered
        # "uncovered": every row is flagged and the report counts them.
        assert all(row["missing"] for row in r["rows"])
        assert r["missing_responses"] == len(r["rows"]) > 0

    def test_answered_cases_are_not_counted_as_missing(self, monkeypatch):
        monkeypatch.setattr(run_eval.cov, "review_code_coverage", _perfect_review)
        r = run_coverage(llm=object())
        assert r["missing_responses"] == 0
        assert not any(row["missing"] for row in r["rows"])

    def test_the_human_report_shows_the_missing_count(self, monkeypatch, capsys):
        monkeypatch.setattr(run_eval.cov, "review_code_coverage",
                            lambda *a, **k: {"cases": []})
        monkeypatch.setattr("llm.LLM", lambda **kw: object())
        main(["--coverage"])
        assert "missing model responses (scored as uncovered)" in capsys.readouterr().out


# --------------------------------------------------------------------------- helpers
REPO_ROOT = Path(__file__).resolve().parents[1]


def _perfect_review(llm, feature_name, requirement, cases, code_excerpts,
                    samples=1, progress=None, contract_findings=None):
    ex = next(e for e in dataset.COVERAGE_EXAMPLES if e["cases"] == cases)
    return {"cases": [{"test_case_id": cid, "status": status, "confidence": 0.9,
                       "needs_review": False, "files_rejected": []}
                      for cid, status in ex["expected"].items()]}


def _overclaiming_review(llm, feature_name, requirement, cases, code_excerpts,
                         samples=1, progress=None, contract_findings=None):
    ex = next(e for e in dataset.COVERAGE_EXAMPLES if e["cases"] == cases)
    return {"cases": [{"test_case_id": cid, "status": "covered", "confidence": 0.9,
                       "needs_review": False, "files_rejected": []} for cid in ex["expected"]]}


def _subprocess_eval(*argv, **env):
    """Run the real documented entry point, `python -m tests.eval.run_eval`, from the repo
    root, exactly as CI does."""
    return subprocess.run([sys.executable, "-m", "tests.eval.run_eval", *argv], cwd=REPO_ROOT,
                          capture_output=True, text=True, env={**os.environ, **env})


SECTIONS = ["HALLUCINATION_PROBES", "DEDUP_PAIRS", "KNOWN_LIMITATION_PAIRS", "COVERAGE_EXAMPLES"]


# --------------------------------------------------------------------------- fingerprint
class TestFingerprintCoversTheScoredCorpus:
    """The fingerprint exists so two runs can be compared only if they scored the same
    corpus. It therefore has to change when ANY input the scorers read changes -- not just
    an item's id or label -- and stay put for edits that do not affect scoring."""

    def _changed(self, monkeypatch, section, mutate):
        before = _dataset_fingerprint()
        patched = copy.deepcopy(getattr(dataset, section))
        mutate(patched)
        monkeypatch.setattr(dataset, section, patched)
        return _dataset_fingerprint() != before

    @pytest.mark.parametrize("label, section, mutate", [
        ("probe claim rationale", "HALLUCINATION_PROBES",
         lambda d: d[0]["claim"].__setitem__("rationale", "a different claim")),
        ("probe claim status", "HALLUCINATION_PROBES",
         lambda d: d[0]["claim"].__setitem__("status", "uncovered" if d[0]["claim"]["status"] != "uncovered" else "covered")),
        ("probe excerpt", "HALLUCINATION_PROBES",
         lambda d: d[0].__setitem__("excerpts", d[0]["excerpts"] + [{"path": "extra.py", "text": "x = 1"}])),
        ("probe excerpt text edited", "HALLUCINATION_PROBES",
         lambda d: d[0]["excerpts"][0].__setitem__("text", d[0]["excerpts"][0].get("text", "") + " # edited")),
        ("probe expected status", "HALLUCINATION_PROBES",
         lambda d: d[0].__setitem__("expected_status", "uncovered" if d[0]["expected_status"] != "uncovered" else "covered")),
        ("probe expect_rejected_citation", "HALLUCINATION_PROBES",
         lambda d: d[0].__setitem__("expect_rejected_citation", not d[0].get("expect_rejected_citation", False))),
        ("dedup pair side a", "DEDUP_PAIRS",
         lambda d: d[0]["a"].__setitem__("title", "an entirely different test case")),
        ("dedup pair side b", "DEDUP_PAIRS",
         lambda d: d[0]["b"].__setitem__("title", "an entirely different test case")),
        ("dedup pair label", "DEDUP_PAIRS",
         lambda d: d[0].__setitem__("expected_same", not d[0]["expected_same"])),
        ("known-limitation pair content", "KNOWN_LIMITATION_PAIRS",
         lambda d: d[0]["a"].__setitem__("title", "an entirely different test case")),
        ("coverage requirement", "COVERAGE_EXAMPLES",
         lambda d: d[0].__setitem__("requirement", d[0]["requirement"] + " It must also log every attempt.")),
        ("coverage feature name", "COVERAGE_EXAMPLES",
         lambda d: d[0].__setitem__("feature", "Another feature")),
        ("coverage excerpt", "COVERAGE_EXAMPLES",
         lambda d: d[0].__setitem__("excerpts", d[0]["excerpts"] + [{"path": "extra.py", "text": "y = 2"}])),
        ("coverage case", "COVERAGE_EXAMPLES",
         lambda d: d[0]["cases"][0].__setitem__("title", "a rewritten test case")),
        ("coverage expected label", "COVERAGE_EXAMPLES",
         lambda d: d[0]["expected"].__setitem__(next(iter(d[0]["expected"])), "partial" if next(iter(d[0]["expected"].values())) != "partial" else "covered")),
    ])
    def test_changing_a_scoring_input_changes_the_fingerprint(self, monkeypatch, label, section, mutate):
        assert self._changed(monkeypatch, section, mutate), f"editing the {label} left the fingerprint unchanged"

    @pytest.mark.parametrize("section", SECTIONS)
    def test_rewording_a_note_does_not_change_the_fingerprint(self, monkeypatch, section):
        assert not self._changed(monkeypatch, section,
                                 lambda d: d[0].__setitem__("note", "reworded; same labels and inputs"))

    @pytest.mark.parametrize("section", SECTIONS)
    def test_an_identical_copy_of_the_corpus_has_the_same_fingerprint(self, monkeypatch, section):
        assert not self._changed(monkeypatch, section, lambda d: None)

    @pytest.mark.parametrize("section", SECTIONS)
    def test_the_order_items_are_listed_in_does_not_matter(self, monkeypatch, section):
        assert not self._changed(monkeypatch, section, lambda d: d.reverse())

    @pytest.mark.parametrize("section", SECTIONS)
    def test_the_order_of_keys_inside_an_item_does_not_matter(self, monkeypatch, section):
        def reverse_keys(node):
            if isinstance(node, dict):
                return {k: reverse_keys(v) for k, v in reversed(list(node.items()))}
            if isinstance(node, list):
                return [reverse_keys(v) for v in node]
            return node

        def mutate(items):
            items[:] = [reverse_keys(i) for i in items]
        assert not self._changed(monkeypatch, section, mutate)

    def test_adding_or_removing_an_item_changes_it(self, monkeypatch):
        assert self._changed(monkeypatch, "DEDUP_PAIRS", lambda d: d.pop())
        assert self._changed(monkeypatch, "HALLUCINATION_PROBES",
                             lambda d: d.append(dict(d[0], id="a-new-probe")))

    def test_the_fingerprint_is_the_same_in_every_process(self):
        # Not just stable within one interpreter: independent of hash randomisation.
        code = "from tests.eval.run_eval import _dataset_fingerprint as f; print(f())"
        seen = {subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                               text=True, env={**os.environ, "PYTHONHASHSEED": seed}).stdout.strip()
                for seed in ("1", "2", "random")}
        assert len(seen) == 1 and len(seen.pop()) == 12

    def test_nothing_from_the_run_enters_the_fingerprint(self):
        quiet = json.loads(_subprocess_eval("--probes", "--dedup", "--json").stdout)
        noisy = json.loads(_subprocess_eval("--probes", "--dedup", "--json",
                                            "--api-key", "sk-must-not-appear",
                                            "--ollama-url", "http://secret.example:1234",
                                            "--provider", "openai", "--model", "gpt-x").stdout)
        assert quiet["meta"]["dataset_fingerprint"] == noisy["meta"]["dataset_fingerprint"]
        blob = json.dumps(noisy) + json.dumps(_scoring_corpus())
        assert "sk-must-not-appear" not in blob and "secret.example" not in blob


# --------------------------------------------------------------------------- --json / --out
class TestJsonStdoutStaysPure:
    def test_json_with_out_leaves_stdout_parseable_and_free_of_status_text(self, tmp_path, capsys):
        out_path = tmp_path / "result.json"
        assert main(["--probes", "--dedup", "--json", "--out", str(out_path)]) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)            # parses directly: JSON and nothing else
        assert "results written" not in captured.out
        assert "results written" in captured.err      # the status note is still shown, on stderr
        assert out_path.exists()
        assert json.loads(out_path.read_text()) == payload
        assert payload["failures"] == [] and payload["meta"]["dataset_fingerprint"]

    def test_the_real_cli_with_json_and_out(self, tmp_path):
        # The same through the documented entry point, as a shell pipeline would use it.
        out_path = tmp_path / "result.json"
        r = _subprocess_eval("--probes", "--dedup", "--json", "--out", str(out_path))
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert "results written" not in r.stdout and str(out_path) in r.stderr
        assert json.loads(out_path.read_text()) == payload

    def test_without_json_the_human_report_and_the_note_stay_on_stdout(self, tmp_path, capsys):
        out_path = tmp_path / "result.json"
        assert main(["--probes", "--out", str(out_path)]) == 0
        captured = capsys.readouterr()
        assert "=== hallucination_probes ===" in captured.out
        assert f"results written to {out_path}" in captured.out
        assert json.loads(out_path.read_text())["reports"][0]["section"] == "hallucination_probes"


# --------------------------------------------------------------------------- the gate fails closed
class TestAnEmptyCorpusDoesNotPassTheGate:
    """The offline sections run as a CI merge gate. A section with nothing to score has no
    score; comparing that against the threshold used to be skipped, so an emptied corpus
    exited 0 and printed "all scored sections met their thresholds"."""

    @pytest.mark.parametrize("flag, section, name", [
        ("--probes", "HALLUCINATION_PROBES", "probes"),
        ("--dedup", "DEDUP_PAIRS", "dedup"),
    ])
    def test_an_empty_offline_section_fails_and_names_itself(self, monkeypatch, capsys, flag, section, name):
        monkeypatch.setattr(dataset, section, [])
        assert main([flag]) == 1
        out = capsys.readouterr().out
        assert f"{name}: no scorable items (empty corpus)" in out
        assert "FAILED thresholds" in out
        assert "all scored sections met their thresholds" not in out

    def test_an_empty_coverage_corpus_fails_when_that_section_is_requested(self, monkeypatch, capsys):
        monkeypatch.setattr(dataset, "COVERAGE_EXAMPLES", [])
        monkeypatch.setattr("llm.LLM", lambda **kw: object())
        assert main(["--coverage"]) == 1
        out = capsys.readouterr().out
        assert "coverage: no scorable items (empty corpus)" in out
        assert "all scored sections met their thresholds" not in out

    def test_the_failure_is_in_the_json_payload_and_the_out_file_too(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(dataset, "HALLUCINATION_PROBES", [])
        out_path = tmp_path / "result.json"
        assert main(["--probes", "--dedup", "--json", "--out", str(out_path)]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert [f for f in payload["failures"] if f.startswith("probes: no scorable items")]
        assert json.loads(out_path.read_text())["failures"] == payload["failures"]

    def test_one_empty_section_fails_the_run_even_if_the_other_passes(self, monkeypatch, capsys):
        monkeypatch.setattr(dataset, "DEDUP_PAIRS", [])
        assert main(["--probes", "--dedup"]) == 1      # probes score 1.0; dedup has nothing
        assert "dedup: no scorable items" in capsys.readouterr().out

    def test_the_real_cli_exits_non_zero_for_an_empty_corpus(self):
        code = ("import sys; from tests.eval import dataset; dataset.DEDUP_PAIRS = []; "
                "from tests.eval.run_eval import main; sys.exit(main(['--probes', '--dedup']))")
        r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
        assert r.returncode == 1 and "dedup: no scorable items" in r.stdout

    def test_a_section_that_is_not_scored_may_be_empty(self, monkeypatch):
        # KNOWN_LIMITATION_PAIRS are reported, never scored (see run_dedup): emptying them
        # is not an unscored gate.
        monkeypatch.setattr(dataset, "KNOWN_LIMITATION_PAIRS", [])
        assert main(["--dedup"]) == 0

    def test_a_section_that_was_not_requested_does_not_matter(self, monkeypatch):
        monkeypatch.setattr(dataset, "COVERAGE_EXAMPLES", [])
        assert main(["--probes", "--dedup"]) == 0


class TestThresholdExitCodes:
    def test_the_dedup_threshold_gates_the_run(self, capsys):
        assert main(["--dedup", "--min-dedup", "1.1"]) == 1
        out = capsys.readouterr().out
        assert "dedup 1.0 < 1.1" in out and "FAILED thresholds" in out

    def test_a_passing_corpus_exits_zero_and_says_so(self, capsys):
        assert main(["--probes", "--dedup"]) == 0
        assert "all scored sections met their thresholds" in capsys.readouterr().out

    def test_a_real_regression_in_the_dedup_decision_fails_the_gate(self, monkeypatch):
        monkeypatch.setattr(run_eval, "_reuse_same", lambda a, b: True)    # merge everything
        assert main(["--dedup"]) == 1

    def test_min_coverage_gates_the_coverage_section(self, monkeypatch, capsys):
        monkeypatch.setattr("llm.LLM", lambda **kw: object())
        monkeypatch.setattr(run_eval.cov, "review_code_coverage", _overclaiming_review)
        assert main(["--coverage", "--min-coverage", "0.99"]) == 1
        out = capsys.readouterr().out
        assert re.search(r"coverage 0\.\d+ < 0\.99", out) and "FAILED thresholds" in out
        monkeypatch.setattr(run_eval.cov, "review_code_coverage", _perfect_review)
        assert main(["--coverage", "--min-coverage", "0.99"]) == 0

    def test_without_a_floor_coverage_never_fails_the_run(self, monkeypatch):
        # --min-coverage defaults to 0.0 on purpose ("set a floor once you have a baseline").
        monkeypatch.setattr("llm.LLM", lambda **kw: object())
        monkeypatch.setattr(run_eval.cov, "review_code_coverage", _overclaiming_review)
        assert main(["--coverage"]) == 0
