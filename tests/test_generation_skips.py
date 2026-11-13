"""Exercise skipped passes through the real pipeline, with no external services."""
import pytest

from testgen.service import generate_fresh_testcases_pipeline
from tests.test_generation_pipeline import FakeEmbedder, FakeStore, SpyLLM


def run(store=None, focus=None):
    llm, progress = SpyLLM(), []
    params = {"feature_id": "feature-1", "total": 10}
    if focus is not None:
        params["focus"] = focus
    try:
        result = generate_fresh_testcases_pipeline(
            store or FakeStore(), llm, FakeEmbedder(), params,
            update_job_fn=lambda **kwargs: progress.append(kwargs),
        )
    except RuntimeError as exc:
        # This fixture only emits API cases. With API disabled the real pipeline
        # correctly reports an empty result; the call assertions still exercise
        # every preceding generation stage, rather than mocking the scheduler.
        if not str(exc).startswith("EmptyGenerationError:") or not focus or focus.get("api") != 0:
            raise
        result = None
    return llm, result, progress


def test_empty_project_skips_fusion_but_generates_fresh_cases():
    llm, result, progress = run()
    assert not llm.calls_matching("Analyze Cross-Feature Overlap")
    assert result["cases_new"] > 0
    assert result["inherited_reused"] == result["inherited_rebuilt"] == 0
    assert any("Fusion skipped" in str(event) for event in progress)


@pytest.mark.parametrize("source", ["project", "previous_version"])
def test_fusion_still_runs_when_either_source_has_candidates(source):
    class CandidateStore(FakeStore):
        def __init__(self):
            super().__init__()
            if source == "previous_version":
                self.feature["version"] = 2
                self.features.find_one = lambda query: {"_id": "previous"}

        def list_test_cases(self, **kwargs):
            return {"items": [{"id": "existing", "title": "Create order"}]} if source == "project" else {"items": []}

        def get_feature_cases(self, feature_id):
            return [{"id": "existing", "title": "Create order"}]

    llm, _, _ = run(CandidateStore())
    assert len(llm.calls_matching("Analyze Cross-Feature Overlap")) == 1


@pytest.mark.parametrize("category,marker", [
    ("api", "Generate focused API worker test cases"),
    ("ui", "Generate UI validations"),
])
def test_zero_focus_skips_dedicated_workers(category, marker):
    focus = dict.fromkeys(("functional", "e2e", "api", "nfr", "ui"), 20)
    enabled, _, _ = run(focus=focus)
    assert enabled.calls_matching(marker)
    focus[category] = 0
    disabled, _, _ = run(focus=focus)
    assert not disabled.calls_matching(marker)


def test_api_only_skips_shared_worker_and_business_fallback():
    llm, result, _ = run(focus={"api": 100, "ui": 0, "e2e": 0, "nfr": 0, "functional": 0})
    assert llm.calls_matching("Generate focused API worker test cases")
    assert not llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")
    assert not llm.calls_matching("Generate one business rule test")
    assert result["cases_new"] > 0


@pytest.mark.parametrize("category", ["e2e", "nfr", "functional"])
def test_shared_worker_runs_for_each_enabled_output(category):
    focus = dict.fromkeys(("functional", "e2e", "api", "nfr", "ui"), 0)
    focus[category] = 100
    llm, _, _ = run(focus=focus)
    assert len(llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")) == 1
    assert bool(llm.calls_matching("Generate one business rule test")) == (category == "functional")


def test_omitted_focus_entries_keep_their_default_share():
    llm, _, _ = run(focus={"api": 0})
    assert not llm.calls_matching("Generate focused API worker test cases")
    assert llm.calls_matching("Generate UI validations")
    assert llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")


def test_zero_e2e_focus_skips_fallback_even_when_the_shared_worker_runs():
    class ManyEndpointsStore(FakeStore):
        def __init__(self):
            super().__init__()
            endpoints = "\n".join(f"GET /v1/orders/item-{i}" for i in range(12))
            self.feature["raw_api_spec"] = endpoints
            self.feature["text"] += endpoints

    focus = {"api": 50, "ui": 0, "e2e": 50, "nfr": 0, "functional": 0}
    enabled, _, _ = run(ManyEndpointsStore(), focus)
    assert enabled.calls_matching("Generate focused E2E flow test cases")
    focus.update(e2e=0, functional=50)
    disabled, _, _ = run(ManyEndpointsStore(), focus)
    assert disabled.calls_matching("Generate E2E flows, edge cases, and business rule tests")
    assert not disabled.calls_matching("Generate focused E2E flow test cases")
