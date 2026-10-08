"""The store query behind semantic PR mapping (issue #54), against a REAL MongoDB.

Requires MONGO_TEST_URI like the other dbintegration tests; skipped when no MongoDB is
reachable. A plain mongod has no mongot, so `$vectorSearch` fails here and these tests
exercise the in-memory fallback of `Store.semantic_feature_scores`. The `$vectorSearch`
branch is exercised two ways: against `VectorSearchEmulator` below (a stand-in that answers
the pipeline the way mongot does, including its "nearest 50 CHUNKS" truncation, so the
runner-up logic runs without a search engine), and against a real mongot when
MONGO_SEARCH_TEST_URI points at a replica set that runs one (skipped otherwise).
"""
import math
import os
import time
import uuid

import pytest
from bson import ObjectId
from pymongo import MongoClient

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")
MONGO_SEARCH_TEST_URI = os.getenv("MONGO_SEARCH_TEST_URI", "")


def _server_reachable() -> bool:
    try:
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if not _server_reachable():
    pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
                "db-integration tests)", allow_module_level=True)

import coverage as cov  # noqa: E402
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


# --------------------------------------------------------------------------- runner-up search
def angle(theta):
    """A unit vector at `theta` radians from the query [1, 0, 0]: its (1 + cos) / 2 score is
    exactly (1 + cos(theta)) / 2, so a test can say how far apart two features really are."""
    return [math.cos(theta), math.sin(theta), 0.0]


def true_score(theta):
    return (1 + math.cos(theta)) / 2


QUERY = [1.0, 0.0, 0.0]


class VectorSearchEmulator:
    """Stands in for `store.fchunks`: an aggregate() whose first stage is $vectorSearch is
    answered the way mongot answers it -- exact (1 + cosine) / 2 over the chunks that pass the
    filter, but only the nearest `limit` CHUNKS -- and everything else goes to the real
    collection. That truncation is what hid a close runner-up behind a feature that owns all of
    the nearest chunks."""

    def __init__(self, real):
        self._real = real
        self.searches = []            # the `filter` of every $vectorSearch, in order
        self.fail_excluding = False   # make any search that excludes features raise

    def __getattr__(self, name):
        return getattr(self._real, name)

    def aggregate(self, pipeline):
        stage = pipeline[0].get("$vectorSearch")
        if stage is None:
            return self._real.aggregate(pipeline)
        flt = stage["filter"]
        self.searches.append(flt)
        conditions = flt["$and"] if "$and" in flt else [flt]
        project, excluded = None, set()
        for c in conditions:
            if "project_id" in c:
                project = c["project_id"]["$eq"]
            if "feature_id" in c:
                excluded = set(c["feature_id"]["$nin"])
        if excluded and self.fail_excluding:
            raise RuntimeError("search unavailable")
        q = stage["queryVector"]
        scored = []
        for d in self._real.find({"project_id": project}):
            if d["feature_id"] in excluded:
                continue
            e = d["embedding"]
            cosine = sum(a * b for a, b in zip(q, e)) / (math.hypot(*q) * math.hypot(*e))
            scored.append(((1 + cosine) / 2, d["feature_id"]))
        scored.sort(reverse=True)
        best = {}
        for sc, fid in scored[:stage["limit"]]:
            best[fid] = max(best.get(fid, 0.0), sc)
        return iter([{"_id": fid, "score": sc} for fid, sc in best.items()])


@pytest.fixture()
def emulated(store):
    store.fchunks = VectorSearchEmulator(store.fchunks)
    return store


class Embedder:
    def embed(self, text, task="document"):
        return list(QUERY)


PR = {"title": "Rate limit forgot-password requests", "body": "Limit reset emails.",
      "number": 7, "repo_full_name": "acme/app"}


def thetas(n, lo, hi):
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def dominant(store, project="p1", name="A", chunks=60, lo=0.0, hi=0.02, **kw):
    """A feature whose `chunks` chunks are all very close to the query: more than the 50
    chunks a $vectorSearch returns, so it fills the whole result on its own."""
    return feature(store, project, name, [angle(t) for t in thetas(chunks, lo, hi)], **kw)


class TestRunnerUpBehindADominantFeature:
    """$vectorSearch returns the nearest 50 CHUNKS. A feature that owns all of them used to be
    the only one returned, and with no runner-up the margin check was skipped (issue #54)."""

    def test_the_first_search_returns_only_the_dominant_feature(self, emulated):
        # Guards the fixture: the emulator really does reproduce the truncation.
        a = dominant(emulated)
        feature(emulated, "p1", "B", [angle(0.05)])
        result = list(emulated.fchunks.aggregate([{"$vectorSearch": {
            "queryVector": QUERY, "limit": 50, "filter": {"project_id": {"$eq": "p1"}}}}]))
        assert [r["_id"] for r in result] == [a]

    def test_a_close_runner_up_is_found_and_the_margin_is_the_true_one(self, emulated):
        a = dominant(emulated)
        b = feature(emulated, "p1", "B", [angle(0.05)])
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert [r["feature_id"] for r in rows] == [a, b]
        assert rows[0]["score"] == pytest.approx(1.0)
        assert rows[1]["score"] == pytest.approx(true_score(0.05), abs=1e-4)
        assert rows[0]["score"] - rows[1]["score"] == pytest.approx(1 - true_score(0.05), abs=1e-3)
        # one search for the nearest chunks, then one that leaves the feature already found out
        assert len(emulated.fchunks.searches) == 2
        assert emulated.fchunks.searches[0] == {"project_id": {"$eq": "p1"}}
        assert emulated.fchunks.searches[1] == {"$and": [{"project_id": {"$eq": "p1"}},
                                                         {"feature_id": {"$nin": [a]}}]}

    def test_a_close_runner_up_makes_the_pr_ambiguous_so_there_is_no_suggestion(self, emulated):
        dominant(emulated)
        feature(emulated, "p1", "B", [angle(0.05)])      # lead ~0.0006, far under the 0.05 margin
        assert cov.semantic_pr_match(emulated, Embedder(), PR, "p1") is None

    def test_a_clear_runner_up_still_yields_a_suggestion_with_its_margin(self, emulated):
        a = dominant(emulated)
        b = feature(emulated, "p1", "B", [angle(1.2)])
        out = cov.semantic_pr_match(emulated, Embedder(), PR, "p1")
        assert out["feature_id"] == a
        assert out["margin"] == pytest.approx(1.0 - true_score(1.2), abs=1e-3)
        assert out["runner_up"]["feature_id"] == b
        assert out["runner_up"]["confidence"] == pytest.approx(true_score(1.2), abs=1e-3)

    def test_a_genuine_single_feature_project_is_not_rejected(self, emulated):
        a = dominant(emulated)
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert [r["feature_id"] for r in rows] == [a]
        assert len(emulated.fchunks.searches) == 2       # it looked for a runner-up and found none
        out = cov.semantic_pr_match(emulated, Embedder(), PR, "p1")
        assert out["feature_id"] == a and out["margin"] is None and out["runner_up"] is None

    def test_no_extra_search_when_two_features_are_already_in_the_first_result(self, emulated):
        feature(emulated, "p1", "A", [angle(0.0)] * 5)
        feature(emulated, "p1", "B", [angle(0.5)])
        assert len(emulated.semantic_feature_scores(QUERY, "p1")) == 2
        assert len(emulated.fchunks.searches) == 1

    def test_the_runner_up_search_leaves_out_every_version_of_the_dominant_feature(self, emulated):
        v1 = dominant(emulated, name="doc")                                   # fills the page
        v2 = feature(emulated, "p1", "doc", [angle(t) for t in thetas(5, 0.03, 0.04)],
                     group_id=v1, version=2)                                  # same group, further
        b = feature(emulated, "p1", "B", [angle(0.1)])
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert [r["feature_id"] for r in rows] == [v2, b]                     # latest version named
        assert emulated.fchunks.searches[1]["$and"][1] == {"feature_id": {"$nin": sorted([v1, v2])}}
        assert len(emulated.fchunks.searches) == 2

    def test_leftover_chunks_of_a_deleted_feature_do_not_hide_the_real_features(self, emulated):
        gone = dominant(emulated, name="gone")
        emulated.features.delete_one({"_id": ObjectId(gone)})                 # its chunks remain
        a = feature(emulated, "p1", "A", [angle(0.05)])
        b = feature(emulated, "p1", "B", [angle(0.3)])
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert [r["feature_id"] for r in rows] == [a, b]

    def test_another_projects_feature_never_shows_up_as_the_runner_up(self, emulated):
        a = dominant(emulated)
        feature(emulated, "p2", "perfect elsewhere", [angle(0.0)])
        assert [r["feature_id"] for r in emulated.semantic_feature_scores(QUERY, "p1")] == [a]

    def test_if_the_runner_up_search_fails_the_exact_scan_answers_instead(self, emulated):
        a = dominant(emulated)
        b = feature(emulated, "p1", "B", [angle(0.05)])
        emulated.fchunks.fail_excluding = True
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert [r["feature_id"] for r in rows] == [a, b]
        assert rows[1]["score"] == pytest.approx(true_score(0.05), abs=1e-4)

    def test_if_nothing_can_confirm_the_runner_up_it_never_answers_with_a_lone_feature(
            self, emulated, monkeypatch):
        dominant(emulated)
        feature(emulated, "p1", "B", [angle(0.05)])
        emulated.fchunks.fail_excluding = True
        monkeypatch.setattr(type(emulated), "SEMANTIC_FALLBACK_MAX_CHUNKS", 1)   # exact scan unavailable
        assert emulated.semantic_feature_scores(QUERY, "p1") == []
        assert cov.semantic_pr_match(emulated, Embedder(), PR, "p1") is None

    def test_the_runner_up_searches_are_bounded_and_the_exact_scan_decides_when_they_run_out(
            self, emulated):
        for n in range(6):          # six deleted features whose leftover chunks each fill a page
            gone = dominant(emulated, name=f"gone{n}", lo=0.01 * n, hi=0.01 * n + 0.001)
            emulated.features.delete_one({"_id": ObjectId(gone)})
        a = feature(emulated, "p1", "A", [angle(0.5)])
        b = feature(emulated, "p1", "B", [angle(0.6)])
        rows = emulated.semantic_feature_scores(QUERY, "p1")
        assert len(emulated.fchunks.searches) == 1 + type(emulated).SEMANTIC_RUNNER_UP_QUERIES
        assert [r["feature_id"] for r in rows] == [a, b]          # still found, by the exact scan


# --------------------------------------------------------------------------- real mongot
def _wait_for(predicate, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(2)
    return False


@pytest.fixture()
def search_store():
    if not MONGO_SEARCH_TEST_URI:
        pytest.skip("set MONGO_SEARCH_TEST_URI to a replica set with mongot to run this")
    db_name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
    s = Store(MONGO_SEARCH_TEST_URI, db_name, dim=3)
    try:
        if "feature_chunks" not in s.db.list_collection_names():
            s.db.create_collection("feature_chunks")       # a search index needs the collection
        if "vector_index" not in s._existing(s.fchunks):
            s._ensure_vector(s.fchunks, extra_filters=["project_id", "feature_id"])
        ready = _wait_for(lambda: any(i.get("queryable") for i in s.fchunks.list_search_indexes()), 120)
        if not ready:
            pytest.skip("the feature_chunks vector index did not become queryable in time")
        yield s
    finally:
        s.client.drop_database(db_name)


def test_real_mongot_finds_a_close_runner_up_behind_a_dominant_feature(search_store):
    """The case that exposed the bug, against a real $vectorSearch: feature A owns the 50
    nearest chunks, feature B is a hair behind it."""
    a = dominant(search_store)
    b = feature(search_store, "p1", "B", [angle(0.05)])
    total = search_store.fchunks.count_documents({})

    def fully_indexed():       # asserting before mongot has seen every chunk would be a race
        return len(list(search_store.fchunks.aggregate([{"$vectorSearch": {
            "index": "vector_index", "path": "embedding", "queryVector": QUERY, "numCandidates": 200,
            "limit": total, "filter": {"project_id": {"$eq": "p1"}}}}]))) == total
    if not _wait_for(fully_indexed, 120):
        pytest.skip("mongot did not finish indexing the test chunks in time")
    rows = search_store.semantic_feature_scores(QUERY, "p1")
    assert [r["feature_id"] for r in rows] == [a, b]
    assert rows[1]["score"] == pytest.approx(true_score(0.05), abs=1e-3)
    assert cov.semantic_pr_match(search_store, Embedder(), PR, "p1") is None
