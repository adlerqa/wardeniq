"""Regression coverage for malformed LLM JSON and atomic feature versions."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import coverage as cov
from api.routes import features as feature_routes
from llm import LLM


class _ResponseLLM:
    def __init__(self, response):
        self.response = response

    def chat_json(self, *args, **kwargs):
        return self.response


def _case():
    return [{"id": "c1", "title": "Case", "type": "functional", "steps": []}]


@pytest.mark.parametrize("raw", ["true", "[]"])
def test_chat_json_rejects_non_object_json(monkeypatch, raw):
    llm = LLM()
    monkeypatch.setattr(llm, "_raw_chat", lambda *args, **kwargs: raw)

    with pytest.raises(RuntimeError, match="must be an object"):
        llm.chat_json("system", "user")


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


def test_new_version_does_not_create_feature_when_diff_fails(monkeypatch):
    created = []

    class FakeStore:
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
            created.append((args, kwargs))
            return "new-feature"

    monkeypatch.setattr(feature_routes, "store", FakeStore())
    monkeypatch.setattr(feature_routes.state, "embedder", SimpleNamespace(embed=lambda text: [0.0]))
    monkeypatch.setattr(feature_routes, "_generate_feature_summary", lambda *args: "summary")
    monkeypatch.setattr(feature_routes, "current_llm", lambda: object())
    monkeypatch.setattr(
        feature_routes.cov,
        "diff_versions",
        lambda *args: {"keep": [], "retire": [], "error": "invalid response"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
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

    assert exc_info.value.status_code == 502
    assert created == []


def test_new_version_keeps_successful_diff_before_persistence(monkeypatch):
    events = []

    class FakeStore:
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
            events.append("create")
            return "new-feature"

        def associate(self, *args, **kwargs):
            events.append("associate")

        def set_version_diff(self, *args, **kwargs):
            events.append("set-diff")

        def add_feature_chunks(self, *args, **kwargs):
            events.append("chunks")

    monkeypatch.setattr(feature_routes, "store", FakeStore())
    monkeypatch.setattr(feature_routes.state, "embedder", SimpleNamespace(embed=lambda text: [0.0]))
    monkeypatch.setattr(feature_routes, "_generate_feature_summary", lambda *args: "summary")
    monkeypatch.setattr(feature_routes, "current_llm", lambda: object())
    monkeypatch.setattr(
        feature_routes.cov,
        "diff_versions",
        lambda *args: (events.append("diff") or {"keep": ["c1"], "retire": []}),
    )
    monkeypatch.setattr(feature_routes, "launch_job", lambda *args, **kwargs: "job-1")

    result = asyncio.run(
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

    assert result["feature_id"] == "new-feature"
    assert result["job_id"] == "job-1"
    assert events.index("diff") < events.index("create")
