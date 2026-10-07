"""Semantic PR -> feature mapping with visible confidence (issue #54).

The keyword tiers (epic key, ticket->epic, match tag) are unchanged and always win. Below
them, `coverage.resolve_pr_mapping` adds an embedding-based SUGGESTION that carries its
method, score and margin. By default it does not map the PR for coverage accounting; only an
explicit opt-in does.

Duck-typed fakes, no MongoDB or embedding service required. The real store query behind
`semantic_feature_scores` is covered in tests/test_pr_semantic_mapping_db.py.
"""
import types

import pytest

import coverage as cov
from workers import code_coverage_worker as worker


class MapStore:
    """Only what resolve_pr_mapping touches. `ranked` is what semantic_feature_scores returns."""

    def __init__(self, epics=None, match_keys=None, ranked=None, fail=False):
        self._epics = epics or {}
        self._mk = match_keys or []
        self._ranked = ranked or []
        self._fail = fail
        self.semantic_calls = []

    def feature_by_epic(self, project_id, key):
        return self._epics.get(key)

    def features_with_match_key(self, project_id):
        return list(self._mk)

    def semantic_feature_scores(self, embedding, project_id, limit=5):
        self.semantic_calls.append((embedding, project_id, limit))
        if self._fail:
            raise RuntimeError("index unavailable")
        return list(self._ranked)


class Embedder:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    def embed(self, text, task="document"):
        self.calls.append({"text": text, "task": task})
        if self._fail:
            raise RuntimeError("embedding service down")
        return [0.1, 0.2, 0.3]


class Jira:
    def __init__(self, parents):
        self._parents = parents

    def ok(self):
        return True

    def parent_epic(self, key):
        return self._parents.get(key, "")


def row(fid, score):
    return {"feature_id": fid, "name": fid, "key": None, "score": score}


UNTAGGED = {"title": "Rate limit forgot-password requests", "body": "Limit reset emails per address.",
            "changed_files": ["app/auth/reset.py", "tests/test_reset.py"], "number": 7,
            "repo_full_name": "acme/app"}
CLEAR = [row("f-reset", 0.91), row("f-other", 0.80)]


def resolve(store, pr=UNTAGGED, embedder=None, jira=None, **kw):
    return cov.resolve_pr_mapping(store, jira, pr, "p1",
                                  embedder=embedder if embedder is not None else Embedder(), **kw)


class TestDefaults:
    def test_defaults_are_conservative(self):
        assert cov.PR_SEMANTIC_COUNTS_TOWARD_COVERAGE is False
        assert cov.PR_SEMANTIC_MAPPING is True
        assert cov.PR_SEMANTIC_FLOOR == pytest.approx(0.85)
        assert cov.PR_SEMANTIC_MARGIN == pytest.approx(0.05)

    def test_env_parsing_falls_back_on_garbage(self, monkeypatch):
        monkeypatch.setenv("PR_SEMANTIC_FLOOR", "not-a-number")
        assert cov._env_float("PR_SEMANTIC_FLOOR", 0.85) == 0.85
        monkeypatch.setenv("PR_SEMANTIC_FLOOR", "0.9")
        assert cov._env_float("PR_SEMANTIC_FLOOR", 0.85) == pytest.approx(0.9)
        monkeypatch.setenv("PR_SEMANTIC_COUNTS_TOWARD_COVERAGE", "YES")
        assert cov._env_flag("PR_SEMANTIC_COUNTS_TOWARD_COVERAGE", False) is True
        monkeypatch.delenv("PR_SEMANTIC_COUNTS_TOWARD_COVERAGE")
        assert cov._env_flag("PR_SEMANTIC_COUNTS_TOWARD_COVERAGE", False) is False


class TestSemanticHitOnAnUntaggedPr:
    def test_a_strong_match_becomes_a_suggestion_with_method_confidence_and_margin(self):
        out = resolve(MapStore(ranked=CLEAR))
        s = out["suggestion"]
        assert s["method"] == "semantic" and s["feature_id"] == "f-reset"
        assert s["confidence"] == pytest.approx(0.91)
        assert s["margin"] == pytest.approx(0.11)
        assert s["runner_up"] == {"feature_id": "f-other", "confidence": 0.8}

    def test_by_default_the_pr_is_still_unmapped_for_coverage(self):
        out = resolve(MapStore(ranked=CLEAR))
        assert (out["feature_id"], out["confidence"], out["method"]) == (None, 0.0, "unmapped")

    def test_with_the_explicit_opt_in_it_maps_with_method_semantic_and_its_score(self):
        out = resolve(MapStore(ranked=CLEAR), counts_toward_coverage=True)
        assert out["feature_id"] == "f-reset" and out["method"] == "semantic"
        assert out["confidence"] == pytest.approx(0.91)
        assert out["suggestion"]["feature_id"] == "f-reset"

    def test_the_opt_in_flag_is_read_from_the_module_setting(self, monkeypatch):
        monkeypatch.setattr(cov, "PR_SEMANTIC_COUNTS_TOWARD_COVERAGE", True)
        assert resolve(MapStore(ranked=CLEAR))["method"] == "semantic"

    def test_a_single_feature_project_needs_only_the_floor(self):
        out = resolve(MapStore(ranked=[row("only", 0.9)]))
        assert out["suggestion"]["feature_id"] == "only"
        assert out["suggestion"]["margin"] is None and out["suggestion"]["runner_up"] is None


class TestKeywordTiersAlwaysWin:
    BETTER_SEMANTIC = [row("f-semantic", 0.99), row("f-x", 0.5)]

    def _assert_keyword_result(self, store, pr, jira=None):
        embedder = Embedder()
        expected = cov.map_pr_to_feature(store, jira, pr, "p1")
        out = cov.resolve_pr_mapping(store, jira, pr, "p1", embedder=embedder,
                                     counts_toward_coverage=True)
        assert (out["feature_id"], out["confidence"], out["method"]) == expected
        assert out["suggestion"] is None
        # Resolved by a keyword tier: neither the embedder nor the index was consulted.
        assert embedder.calls == [] and store.semantic_calls == []
        return out

    def test_an_epic_key_beats_a_better_semantic_score(self):
        store = MapStore(epics={"EP-1": "f-epic"}, ranked=self.BETTER_SEMANTIC)
        out = self._assert_keyword_result(store, {**UNTAGGED, "title": "EP-1 rate limit resets"})
        assert out["feature_id"] == "f-epic" and out["method"] == "epic:EP-1"

    def test_a_ticket_resolving_to_an_epic_beats_a_better_semantic_score(self):
        store = MapStore(epics={"EP-9": "f-epic9"}, ranked=self.BETTER_SEMANTIC)
        out = self._assert_keyword_result(store, {**UNTAGGED, "title": "ABC-5 fix reset"},
                                          jira=Jira({"ABC-5": "EP-9"}))
        assert out["feature_id"] == "f-epic9"

    def test_a_match_tag_beats_a_better_semantic_score(self):
        store = MapStore(match_keys=[("f-tag", "RESETS")], ranked=self.BETTER_SEMANTIC)
        out = self._assert_keyword_result(store, {**UNTAGGED, "title": "[RESETS] limit emails"})
        assert out["feature_id"] == "f-tag" and out["method"] == "tag:RESETS"

    def test_map_pr_to_feature_itself_never_consults_embeddings(self):
        # The coverage-grade function is unchanged: an untagged PR stays unmapped even though
        # a semantic match exists, so nothing that calls it can change coverage.
        store = MapStore(ranked=CLEAR)
        assert cov.map_pr_to_feature(store, None, UNTAGGED, "p1") == (None, 0.0, "unmapped")
        assert store.semantic_calls == []


class TestWhenNothingClearsTheBar:
    def test_below_the_floor_stays_unmapped_with_no_suggestion(self):
        out = resolve(MapStore(ranked=[row("f1", 0.80), row("f2", 0.70)]))
        assert out["suggestion"] is None
        assert (out["feature_id"], out["method"]) == (None, "unmapped")

    def test_below_the_floor_stays_unmapped_even_when_opted_in(self):
        out = resolve(MapStore(ranked=[row("f1", 0.80)]), counts_toward_coverage=True)
        assert (out["feature_id"], out["method"], out["suggestion"]) == (None, "unmapped", None)

    def test_two_nearly_tied_features_are_ambiguous_and_stay_unmapped(self):
        out = resolve(MapStore(ranked=[row("f1", 0.88), row("f2", 0.87)]))
        assert out["suggestion"] is None

    def test_a_lead_exactly_at_the_margin_is_accepted_and_just_under_it_is_not(self):
        assert resolve(MapStore(ranked=[row("f1", 0.90), row("f2", 0.85)]))["suggestion"] is not None
        assert resolve(MapStore(ranked=[row("f1", 0.90), row("f2", 0.851)]))["suggestion"] is None

    def test_a_score_exactly_at_the_floor_is_accepted(self):
        assert resolve(MapStore(ranked=[row("f1", 0.85)]))["suggestion"] is not None

    def test_floor_and_margin_can_be_overridden(self):
        ranked = [row("f1", 0.80), row("f2", 0.70)]
        assert resolve(MapStore(ranked=ranked), floor=0.75, margin=0.05)["suggestion"]["feature_id"] == "f1"

    def test_no_features_at_all(self):
        assert resolve(MapStore(ranked=[]))["suggestion"] is None


class TestItNeverBreaksIngest:
    def test_an_embedding_failure_degrades_to_unmapped(self):
        out = resolve(MapStore(ranked=CLEAR), embedder=Embedder(fail=True))
        assert (out["feature_id"], out["method"], out["suggestion"]) == (None, "unmapped", None)

    def test_an_index_failure_degrades_to_unmapped(self):
        out = resolve(MapStore(ranked=CLEAR, fail=True))
        assert (out["feature_id"], out["method"], out["suggestion"]) == (None, "unmapped", None)

    def test_no_embedder_configured(self):
        out = cov.resolve_pr_mapping(MapStore(ranked=CLEAR), None, UNTAGGED, "p1", embedder=None)
        assert out["suggestion"] is None

    def test_a_pr_with_no_text_is_not_embedded(self):
        embedder = Embedder()
        out = resolve(MapStore(ranked=CLEAR), pr={"title": "", "body": None, "number": 1},
                      embedder=embedder)
        assert embedder.calls == [] and out["suggestion"] is None

    def test_the_master_switch_turns_semantic_mapping_off(self, monkeypatch):
        monkeypatch.setattr(cov, "PR_SEMANTIC_MAPPING", False)
        embedder = Embedder()
        store = MapStore(ranked=CLEAR)
        out = resolve(store, embedder=embedder, counts_toward_coverage=True)
        assert embedder.calls == [] and store.semantic_calls == []
        assert (out["feature_id"], out["method"], out["suggestion"]) == (None, "unmapped", None)


class TestWhatIsEmbedded:
    def test_title_body_and_changed_paths_are_sent_as_a_query_embedding(self):
        embedder = Embedder()
        resolve(MapStore(ranked=CLEAR), embedder=embedder)
        (call,) = embedder.calls
        assert call["task"] == "query"
        for part in ("Rate limit forgot-password requests", "Limit reset emails per address.",
                     "app/auth/reset.py", "tests/test_reset.py"):
            assert part in call["text"]

    def test_the_text_is_bounded(self):
        text = cov.pr_mapping_text({"title": "t", "body": "b" * 9000,
                                    "changed_files": [f"f{i}.py" for i in range(200)]})
        assert text.count("\n- ") == 40
        assert len(text) < 3000 + 2000       # body capped at 1500 chars, 40 paths at most
        embedder = Embedder()
        resolve(MapStore(ranked=CLEAR), pr={"title": "t", "body": "b" * 9000,
                                            "changed_files": ["x"] * 500, "number": 1},
                embedder=embedder)
        assert len(embedder.calls[0]["text"]) <= 3000

    def test_the_project_is_scoped(self):
        store = MapStore(ranked=CLEAR)
        resolve(store)
        assert store.semantic_calls[0][1] == "p1"


# --------------------------------------------------------------------------- ingest_pr wiring
class IngestStore(MapStore):
    """The store surface ingest_pr touches, recording what it persisted."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mappings, self.suggestions, self.run_updates = [], [], []
        self.created_runs = []
        self.prs = types.SimpleNamespace(find_one=lambda *a, **k: None)

    def upsert_pr(self, doc):
        return "0123456789abcdef01234567"

    def set_pr_mapping(self, pr_id, fid, score, method):
        self.mappings.append((fid, score, method))

    def set_pr_suggestion(self, pr_id, suggestion):
        self.suggestions.append(suggestion)

    def get_feature(self, fid):
        return {"id": fid, "version": 1}

    def create_code_coverage_run(self, doc):
        self.created_runs.append(doc)
        return "run-1"

    def update_code_coverage_run(self, run_id, **kw):
        self.run_updates.append(kw)

    def feature_test_case_ids(self, fid):
        return []

    def cases_brief(self, ids):
        return []

    def save_coverage_snapshot(self, *a, **k):
        return None


REPO = {"id": "r1", "project_id": "p1", "owner": "acme", "name": "app", "full_name": "acme/app"}
GH_PR = {"number": 7, "title": UNTAGGED["title"], "body": UNTAGGED["body"],
         "html_url": "https://example.test/pr/7", "head": {"sha": "abc", "ref": "feat/x"},
         "user": {"login": "dev"}, "state": "open",
         "_files": [{"filename": "app/auth/reset.py", "status": "modified", "additions": 3, "deletions": 1}]}


@pytest.fixture
def ingest(monkeypatch):
    def run(store, pr=GH_PR, embedder=None, **settings):
        monkeypatch.setattr(worker, "store", store)
        monkeypatch.setattr(worker, "state", types.SimpleNamespace(embedder=embedder or Embedder()))
        monkeypatch.setattr(worker, "jira_client", lambda: None)
        for name, value in settings.items():
            monkeypatch.setattr(cov, name, value)
        return worker.ingest_pr(REPO, dict(pr))
    return run


class TestIngestPrWiring:
    def test_default_records_a_suggestion_but_leaves_coverage_unmapped(self, ingest):
        store = IngestStore(ranked=CLEAR)
        ingest(store)
        assert store.suggestions[-1]["feature_id"] == "f-reset"
        assert store.suggestions[-1]["method"] == "semantic"
        assert store.mappings[-1] == (None, 0.0, "unmapped")           # coverage mapping untouched
        assert store.created_runs[0]["feature_id"] is None
        assert not any("feature_id" in u and u["feature_id"] for u in store.run_updates)
        assert store.run_updates[-1]["result"] == {"unmatched": True, "mapping_score": 0.0}

    def test_opt_in_maps_the_pr_and_its_run_onto_the_suggested_feature(self, ingest):
        store = IngestStore(ranked=CLEAR)
        ingest(store, PR_SEMANTIC_COUNTS_TOWARD_COVERAGE=True)
        assert store.mappings[-1] == ("f-reset", pytest.approx(0.91), "semantic")
        moved = [u for u in store.run_updates if u.get("feature_id") == "f-reset"]
        assert moved and moved[0]["confidence"] == "semantic"
        assert moved[0]["mapping_score"] == pytest.approx(0.91)

    def test_a_tagged_pr_is_mapped_by_its_tag_and_never_embedded(self, ingest):
        store = IngestStore(match_keys=[("f-tag", "RESETS")], ranked=CLEAR)
        embedder = Embedder()
        ingest(store, {**GH_PR, "title": "[RESETS] " + GH_PR["title"]}, embedder=embedder)
        assert store.mappings[0][2] == "tag:RESETS" and store.mappings[0][0] == "f-tag"
        assert embedder.calls == [] and store.semantic_calls == [] and store.suggestions == []

    def test_a_pr_that_matches_nothing_clears_any_stale_suggestion(self, ingest):
        store = IngestStore(ranked=[row("f1", 0.5)])
        ingest(store)
        assert store.suggestions == [None]

    def test_a_semantic_failure_does_not_break_ingest(self, ingest):
        store = IngestStore(ranked=CLEAR, fail=True)
        assert ingest(store) == "0123456789abcdef01234567"
        assert store.run_updates[-1]["status"] == "done"
