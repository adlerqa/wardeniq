"""_gen_worker's partial-timing-on-failure behavior (issue #48): when the
pipeline raises partway through, whatever stages already completed must still
reach the job record via store.merge_job_result(jid, stage_timings=...) before
the job is marked failed.

Monkeypatches generate_fresh_testcases_pipeline (and the collaborators
_gen_worker touches before/around it) rather than exercising the real
pipeline — this file is about the CALLER's wiring, not pipeline behavior
itself (see tests/test_generation_timing.py for that).
"""
import workers.generation as gen_mod


class _FakeStore:
    def __init__(self):
        self.merge_calls = []
        self.update_calls = []

    def get_feature(self, fid):
        return None  # short-circuits the auto-scan/import-recheck blocks

    def merge_job_result(self, jid, **fields):
        self.merge_calls.append((jid, fields))

    def update_job(self, jid, **fields):
        self.update_calls.append((jid, fields))

    def update_job_progress(self, jid, stage, progress=None):
        pass


def test_partial_stage_timings_are_saved_before_the_job_is_marked_failed(monkeypatch):
    fake_store = _FakeStore()
    monkeypatch.setattr(gen_mod, "store", fake_store)
    monkeypatch.setattr(gen_mod, "current_llm", lambda: object())
    monkeypatch.setattr(gen_mod.state, "embedder", object())

    def fake_pipeline(store, llm, embedder, params, update_job_fn=None, timing_sink=None):
        # Simulate two completed stages before a mid-run failure.
        timing_sink.append(("_start", 0.0))
        timing_sink.append(("discovery_pass_1", 1.0))
        timing_sink.append(("discovery_pass_2", 1.6))
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(gen_mod, "generate_fresh_testcases_pipeline", fake_pipeline)

    try:
        gen_mod._gen_worker("job-1", {"feature_id": "f1"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("_gen_worker should re-raise the pipeline's exception")

    # merge_job_result(stage_timings=...) must happen BEFORE update_job(status="failed").
    assert fake_store.merge_calls, "no stage_timings were ever saved"
    jid, fields = fake_store.merge_calls[-1]
    assert jid == "job-1"
    assert fields["stage_timings"] == {"discovery_pass_1": 1.0, "discovery_pass_2": 0.6}

    assert fake_store.update_calls[-1] == ("job-1", {"status": "failed", "stage": "error",
                                                      "error": "simulated pipeline failure"})
    assert len(fake_store.merge_calls) == 1  # not also called on some other unrelated path


def test_no_stage_timings_saved_when_pipeline_fails_before_any_stage_completes(monkeypatch):
    # Only the "_start" sentinel -- no real stage finished, so there is nothing
    # meaningful to report; _gen_worker should skip the extra merge_job_result call.
    fake_store = _FakeStore()
    monkeypatch.setattr(gen_mod, "store", fake_store)
    monkeypatch.setattr(gen_mod, "current_llm", lambda: object())
    monkeypatch.setattr(gen_mod.state, "embedder", object())

    def fake_pipeline(store, llm, embedder, params, update_job_fn=None, timing_sink=None):
        timing_sink.append(("_start", 0.0))
        raise ValueError("failed before anything completed")

    monkeypatch.setattr(gen_mod, "generate_fresh_testcases_pipeline", fake_pipeline)

    try:
        gen_mod._gen_worker("job-2", {"feature_id": "f1"})
    except ValueError:
        pass
    else:
        raise AssertionError("_gen_worker should re-raise")

    assert fake_store.merge_calls == []
    assert fake_store.update_calls[-1][1]["status"] == "failed"
