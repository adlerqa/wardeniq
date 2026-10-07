"""The store query behind semantic PR mapping (issue #54), against a REAL MongoDB.

Requires MONGO_TEST_URI like the other dbintegration tests; skipped when no MongoDB is
reachable. A plain mongod has no mongot, so `$vectorSearch` fails here and these tests
exercise the in-memory fallback of `Store.semantic_feature_scores`. The `$vectorSearch`
branch is the same pipeline `search_features` already runs and needs the full compose stack,
so it is not covered by this suite.
"""
import math
import os
import uuid

import pytest
from bson import ObjectId
from pymongo import MongoClient

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")


def _server_reachable() -> bool:
    try:
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if not _server_reachable():
    pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
                "db-integration tests)", allow_module_level=True)

from store import Store  # noqa: E402


@pytest.fixture()
def store():
    db_name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
    s = Store(MONGO_TEST_URI, db_name, dim=3)
    try:
        yield s
    finally:
        s.client.drop_database(db_name)


def feature(store, project, name, vectors, group_id=None, version=1):
    """A feature with one chunk per vector."""
    fid = store.create_feature(name, project, "doc.md", "text", "summary", [0.0, 0.0, 1.0],
                               group_id=group_id, version=version)
    store.add_feature_chunks(fid, project, [
        {"source": "doc.md", "chunk_index": i, "text": f"{name} chunk {i}", "embedding": v}
        for i, v in enumerate(vectors)])
    return fid


class TestSemanticFeatureScores:
    def test_ranks_features_best_first_on_the_zero_to_one_cosine_scale(self, store):
        same = feature(store, "p1", "same", [[1.0, 0.0, 0.0]])
        orthogonal = feature(store, "p1", "orthogonal", [[0.0, 1.0, 0.0]])
        opposite = feature(store, "p1", "opposite", [[-1.0, 0.0, 0.0]])
        rows = store.semantic_feature_scores([1.0, 0.0, 0.0], "p1")
        assert [r["feature_id"] for r in rows] == [same, orthogonal, opposite]
        # (1 + cosine) / 2: identical -> 1.0, orthogonal -> 0.5, opposite -> 0.0 (as mongot reports)
        assert [r["score"] for r in rows] == [1.0, 0.5, 0.0]
        assert rows[0]["name"] == "same"

    def test_a_feature_is_scored_by_its_best_chunk(self, store):
        fid = feature(store, "p1", "multi", [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
        (row,) = store.semantic_feature_scores([1.0, 0.0, 0.0], "p1")
        assert row["feature_id"] == fid
        assert row["score"] == pytest.approx((1 + math.cos(math.pi / 4)) / 2, abs=1e-4)

    def test_only_the_projects_own_features_are_considered(self, store):
        mine = feature(store, "p1", "mine", [[0.0, 1.0, 0.0]])
        feature(store, "p2", "theirs", [[1.0, 0.0, 0.0]])        # a perfect match, wrong project
        rows = store.semantic_feature_scores([1.0, 0.0, 0.0], "p1")
        assert [r["feature_id"] for r in rows] == [mine]

    def test_versions_collapse_to_the_latest_scored_by_the_best_of_them(self, store):
        v1 = feature(store, "p1", "doc", [[1.0, 0.0, 0.0]])
        v2 = feature(store, "p1", "doc", [[0.0, 1.0, 0.0]], group_id=v1, version=2)
        other = feature(store, "p1", "other", [[1.0, 1.0, 0.0]])
        rows = store.semantic_feature_scores([1.0, 0.0, 0.0], "p1")
        assert [r["feature_id"] for r in rows] == [v2, other]    # the LATEST version, not v1
        assert rows[0]["score"] == 1.0                            # v1's chunk matched best

    def test_limit_caps_the_rows(self, store):
        for n in range(4):
            feature(store, "p1", f"f{n}", [[1.0, n * 0.1, 0.0]])
        assert len(store.semantic_feature_scores([1.0, 0.0, 0.0], "p1", limit=2)) == 2

    def test_chunks_of_a_deleted_feature_are_ignored(self, store):
        keep = feature(store, "p1", "keep", [[0.0, 1.0, 0.0]])
        gone = feature(store, "p1", "gone", [[1.0, 0.0, 0.0]])
        store.features.delete_one({"_id": ObjectId(gone)})
        assert [r["feature_id"] for r in store.semantic_feature_scores([1.0, 0.0, 0.0], "p1")] == [keep]

    def test_degrades_to_empty_instead_of_raising(self, store):
        feature(store, "p1", "f", [[1.0, 0.0, 0.0]])
        assert store.semantic_feature_scores([1.0, 0.0], "p1") == []        # wrong dimension
        assert store.semantic_feature_scores([], "p1") == []
        assert store.semantic_feature_scores([1.0, 0.0, 0.0], "") == []
        assert store.semantic_feature_scores([1.0, 0.0, 0.0], "no-such-project") == []

    def test_the_in_memory_fallback_is_skipped_above_its_chunk_cap(self, store, monkeypatch):
        feature(store, "p1", "f", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        monkeypatch.setattr(type(store), "SEMANTIC_FALLBACK_MAX_CHUNKS", 1)
        assert store.semantic_feature_scores([1.0, 0.0, 0.0], "p1") == []


class TestPrSuggestionPersistence:
    def _pr(self, store):
        return store.upsert_pr({"repo_id": "r1", "number": 1, "project_id": "p1", "title": "t"})

    def _doc(self, store, pr_id):
        return store.prs.find_one({"_id": ObjectId(pr_id)})

    def test_a_suggestion_is_stored_apart_from_the_coverage_mapping(self, store):
        pr_id = self._pr(store)
        store.set_pr_mapping(pr_id, None, 0.0, "unmapped")
        store.set_pr_suggestion(pr_id, {"method": "semantic", "feature_id": "f1", "confidence": 0.9})
        doc = self._doc(store, pr_id)
        assert doc["mapping_suggestion"]["feature_id"] == "f1"
        assert doc["feature_id"] is None and doc["mapping_method"] == "unmapped"
        assert store.list_unmapped_prs("p1")[0]["mapping_suggestion"]["confidence"] == 0.9

    def test_none_clears_the_suggestion(self, store):
        pr_id = self._pr(store)
        store.set_pr_suggestion(pr_id, {"method": "semantic", "feature_id": "f1", "confidence": 0.9})
        store.set_pr_suggestion(pr_id, None)
        assert "mapping_suggestion" not in self._doc(store, pr_id)

    def test_a_resolved_mapping_supersedes_a_stale_suggestion(self, store):
        pr_id = self._pr(store)
        store.set_pr_suggestion(pr_id, {"method": "semantic", "feature_id": "f1", "confidence": 0.9})
        store.set_pr_mapping(pr_id, "f2", 1.0, "manual")
        doc = self._doc(store, pr_id)
        assert "mapping_suggestion" not in doc and doc["feature_id"] == "f2"

    def test_an_unmapped_result_leaves_a_suggestion_alone(self, store):
        pr_id = self._pr(store)
        store.set_pr_suggestion(pr_id, {"method": "semantic", "feature_id": "f1", "confidence": 0.9})
        store.set_pr_mapping(pr_id, None, 0.0, "unmapped")
        assert self._doc(store, pr_id)["mapping_suggestion"]["feature_id"] == "f1"
