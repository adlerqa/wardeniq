"""The accuracy harness must itself be trustworthy, so it is tested like any other code.

The two offline sections (adversarial grounding probes, dedup pairs) run in CI with no
model and no database. They are expected to score 1.0 — they measure deterministic logic,
so any drop is a real regression rather than model noise.
"""
import argparse
import json

from testgen.lineage import lineage_token_set, token_set_similarity

from tests.eval import dataset, run_eval
from tests.eval.run_eval import (
    _confusion,
    _dataset_fingerprint,
    _overclaim_rate,
    _reuse_same,
    _run_metadata,
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
