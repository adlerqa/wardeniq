"""Regression coverage for malformed LLM JSON and atomic feature versions."""

import asyncio
from types import SimpleNamespace

import pytest
import coverage as cov
from api.routes import features as feature_routes
from llm import LLM


class _ResponseLLM:
    def __init__(self, response):
        self.response = response

    def chat_json(self, *args, **kwargs):
        return self.response


class _FailedLLM:
    def __init__(self, events):
        self.events = events

    def chat_json(self, *args, **kwargs):
        self.events.append("diff")
        raise RuntimeError("provider timeout")


def _case():
    return [{"id": "c1", "title": "Case", "type": "functional", "steps": []}]


class _FakeStore:
    def __init__(self):
        self.events = []
        self.created = []
        self.associations = []
        self.diff_summary = None

    def get_feature(self, fid):
        return {
            "id": fid,
            "name": "Feature",
            "project_id": "project",
            "version": 1,
            "text": "old requirement",
            "group_id": fid,
            "key": None,
            "match_key": None,
        }

    def feature_test_case_ids(self, fid):
        return ["c1"]

    def cases_brief(self, ids):
        return _case()

    def epic_bound_group(self, *args, **kwargs):
        return False

    def create_feature(self, *args, **kwargs):
        self.events.append("create")
        self.created.append((args, kwargs))
        return "new-feature"

    def associate(self, feature_id, case_id, kind, reason):
        self.events.append("associate")
        self.associations.append((feature_id, case_id, kind, reason))

    def set_version_diff(self, feature_id, diff):
        self.events.append("set-diff")
        self.diff_summary = diff

    def add_feature_chunks(self, *args, **kwargs):
        self.events.append("chunks")


def _new_version(monkeypatch, store, llm, diff_result=None):
    monkeypatch.setattr(feature_routes, "store", store)
    monkeypatch.setattr(feature_routes.state, "embedder", SimpleNamespace(embed=lambda text: [0.0]))
    monkeypatch.setattr(feature_routes, "_generate_feature_summary", lambda *args: "summary")
    monkeypatch.setattr(feature_routes, "current_llm", lambda: llm)
    monkeypatch.setattr(feature_routes, "launch_job", lambda *args, **kwargs: "job-1")
    if diff_result is not None:
        def diff_versions(*args, **kwargs):
            store.events.append("diff")
            return diff_result

        monkeypatch.setattr(feature_routes.cov, "diff_versions", diff_versions)
    return asyncio.run(
        feature_routes.new_version(
            "feature",
            text="new requirement",
            name="",
            key="",
            focus="",
            total=16,
            replace="false",
            confluence_url=[],
            confluence_children=True,
            figma_url=[],
            files=[],
        )
    )


@pytest.mark.parametrize("raw", ["true", "[]"])
def test_chat_json_rejects_non_object_json(monkeypatch, raw):
    llm = LLM()
    calls = []

    def raw_chat(*args, **kwargs):
        calls.append(None)
        return raw

    monkeypatch.setattr(llm, "_raw_chat", raw_chat)

    with pytest.raises(RuntimeError, match="must be an object"):
        llm.chat_json("system", "user")
    assert len(calls) == 1


def test_chat_json_does_not_retry_value_error_from_provider(monkeypatch):
    llm = LLM()
    calls = []

    def raw_chat(*args, **kwargs):
        calls.append(None)
        raise ValueError("invalid provider region")

    monkeypatch.setattr(llm, "_raw_chat", raw_chat)

    with pytest.raises(RuntimeError, match="LLM request failed.*invalid provider region"):
        llm.chat_json("system", "user")
    assert len(calls) == 1


def test_chat_json_retries_malformed_json(monkeypatch):
    llm = LLM()
    calls = []

    def raw_chat(*args, **kwargs):
        calls.append(None)
        return "not json"

    monkeypatch.setattr(llm, "_raw_chat", raw_chat)

    with pytest.raises(RuntimeError, match="unparseable JSON"):
        llm.chat_json("system", "user")
    assert len(calls) == 2


@pytest.mark.parametrize("response", [[], {"keep": None, "retire": None}])
def test_diff_versions_normalizes_malformed_shape(response):
    out = cov.diff_versions(_ResponseLLM(response), "old", "new", _case())

    assert out["keep"] == ["c1"]
    assert out["retire"] == []


@pytest.mark.parametrize(
    ("function", "args", "key"),
    [
        (cov.analyze_impact, ("change", _case()), "impacted"),
        (cov.review_coverage, ({"number": 1}, [], _case()), "covered"),
    ],
)
def test_coverage_reviewers_treat_non_array_fields_as_empty(function, args, key):
    response = {key: None}
    out = function(_ResponseLLM(response), *args)

    assert out[key] == []


def test_normalize_coerces_string_tags_and_invalid_lists():
    normalized = LLM._normalize(
        {"title": "Case", "steps": None, "tags": "smoke"}, "functional"
    )

    assert normalized["tags"] == ["smoke"]
    assert normalized["steps"] == []


def test_new_version_keeps_existing_cases_when_diff_fails(monkeypatch):
    store = _FakeStore()

    result = _new_version(monkeypatch, store, _FailedLLM(store.events))

    assert result["feature_id"] == "new-feature"
    assert result["job_id"] == "job-1"
    assert result["diff"]["error"] == "provider timeout"
    assert result["diff"]["kept"] == 1
    assert store.diff_summary == result["diff"]
    assert store.created
    assert store.associations == [("new-feature", "c1", "carried", None)]
    assert store.events.index("diff") < store.events.index("create")


def test_new_version_keeps_successful_diff_before_persistence(monkeypatch):
    store = _FakeStore()
    result = _new_version(
        monkeypatch,
        store,
        object(),
        {"keep": ["c1"], "retire": []},
    )

    assert result["feature_id"] == "new-feature"
    assert result["job_id"] == "job-1"
    assert store.events.index("diff") < store.events.index("create")
