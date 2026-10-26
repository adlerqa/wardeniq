"""Tests for Store.search_feature_chunks() (app/store/features.py) -- the retrieval
half of the approved test-generation RAG fix: query-driven, category-scoped retrieval
of ONE feature's own chunks, used by generate_fresh_testcases_pipeline()'s API/UI/E2E
generation workers (see app/testgen/service.py's _retrieve_category_context()).

mongomock has no $vectorSearch support (that's an Atlas Search feature, not core
MongoDB), so this file tests the method in two separate halves, per the approved
implementation plan:

1. `$vectorSearch` PIPELINE SHAPE -- a fake collection that captures the aggregation
   pipeline it was called with (instead of executing it), so the filter/queryVector/
   limit/index construction can be asserted directly without needing a live Atlas
   cluster.
2. THE NUMPY FALLBACK -- exercised for real, against a real Store backed by mongomock,
   since mongomock DOES support plain find()/insert_many() with real MongoDB semantics.
   mongomock raises on $vectorSearch (an unrecognized aggregation stage), which drives
   search_feature_chunks() into its fallback path exactly the way a transient mongot
   outage would in production.
"""
from pathlib import Path
import logging
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

mongomock = pytest.importorskip("mongomock")
np = pytest.importorskip("numpy")

import store.base as store_base  # noqa: E402
from store import Store  # noqa: E402
from store.base import VECTOR_INDEX  # noqa: E402


@pytest.fixture
def mongo_store(monkeypatch):
    monkeypatch.setattr(store_base, "MongoClient", mongomock.MongoClient)
    return Store("mongodb://localhost/?", "wardeniq_test", 8)


# --------------------------------------------------------------------------------
# 1. $vectorSearch pipeline shape (fake collection, no real mongomock aggregate())
# --------------------------------------------------------------------------------

class _PipelineCapturingCollection:
    """Stands in for self.fchunks. Records the exact aggregate() pipeline it receives
    and returns a scripted result list -- lets us assert the pipeline SHAPE
    search_feature_chunks() builds without needing real $vectorSearch execution."""

    def __init__(self, result_docs=None):
        self.result_docs = result_docs or []
        self.aggregate_calls = []

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        return list(self.result_docs)

    def find(self, *args, **kwargs):  # pragma: no cover -- only hit if aggregate fails
        raise AssertionError("find() should not be reached when aggregate() succeeds")


class _StoreForPipelineShape:
    """Bare object exposing only what search_feature_chunks() needs, bound to the real
    unbound method so we test the ACTUAL implementation, not a reimplementation."""

    def __init__(self, fchunks):
        self.fchunks = fchunks

    search_feature_chunks = Store.search_feature_chunks
    _log_feature_chunk_retrieval = staticmethod(Store._log_feature_chunk_retrieval)


class TestSearchFeatureChunksPipelineShape:
    def test_pipeline_filters_by_the_given_feature_id(self):
        fake = _PipelineCapturingCollection(result_docs=[
            {"_id": "c1", "chunk_index": 0, "source": "prd", "text": "t1", "score": 0.9},
        ])
        store = _StoreForPipelineShape(fake)
        store.search_feature_chunks([0.1, 0.2, 0.3], "feature-42", limit=5)
        assert len(fake.aggregate_calls) == 1
        vector_search_stage = fake.aggregate_calls[0][0]["$vectorSearch"]
        assert vector_search_stage["filter"] == {"feature_id": {"$eq": "feature-42"}}

    def test_pipeline_uses_the_given_query_vector(self):
        fake = _PipelineCapturingCollection(result_docs=[
            {"_id": "c1", "chunk_index": 0, "source": "prd", "text": "t1", "score": 0.9},
        ])
        store = _StoreForPipelineShape(fake)
        query_vector = [0.11, 0.22, 0.33, 0.44]
        store.search_feature_chunks(query_vector, "feature-42", limit=5)
        vector_search_stage = fake.aggregate_calls[0][0]["$vectorSearch"]
        assert vector_search_stage["queryVector"] == query_vector
        assert vector_search_stage["index"] == VECTOR_INDEX
        assert vector_search_stage["path"] == "embedding"

    def test_pipeline_uses_the_given_limit_and_a_wider_candidate_pool(self):
        fake = _PipelineCapturingCollection(result_docs=[
            {"_id": "c1", "chunk_index": 0, "source": "prd", "text": "t1", "score": 0.9},
        ])
        store = _StoreForPipelineShape(fake)
        store.search_feature_chunks([0.1, 0.2], "feature-42", limit=5)
        vector_search_stage = fake.aggregate_calls[0][0]["$vectorSearch"]
        assert vector_search_stage["limit"] == 5
        # numCandidates must be wider than limit so the vector index has a real
        # candidate pool to rank, matching search_code_chunks()'s established pattern.
        assert vector_search_stage["numCandidates"] > 5

    def test_pipeline_result_propagates_similarity_score(self):
        fake = _PipelineCapturingCollection(result_docs=[
            {"_id": "c1", "chunk_index": 0, "source": "prd", "text": "t1", "score": 0.87654},
        ])
        store = _StoreForPipelineShape(fake)
        out = store.search_feature_chunks([0.1, 0.2], "feature-42", limit=5)
        assert out == [{
            "chunk_id": "c1", "chunk_index": 0, "source": "prd", "text": "t1",
            "score": 0.8765,
        }]

    def test_empty_atlas_result_falls_through_to_numpy_path(self):
        # An empty (but non-erroring) $vectorSearch result must NOT be treated as a
        # successful atlas answer -- it should still fall through to the numpy branch
        # (which, here, also finds nothing, since find() isn't stubbed to return docs).
        class _EmptyThenFindCollection(_PipelineCapturingCollection):
            def find(self, query, projection=None):
                self.find_query = query
                return []

        fake = _EmptyThenFindCollection(result_docs=[])
        store = _StoreForPipelineShape(fake)
        out = store.search_feature_chunks([0.1, 0.2], "feature-42", limit=5)
        assert out == []
        assert fake.find_query == {"feature_id": "feature-42"}


# --------------------------------------------------------------------------------
# 2. Numpy fallback -- real Store, real mongomock, real cosine math
# --------------------------------------------------------------------------------

def _unit_vector(angle_degrees, dims=3):
    """Build a small deterministic embedding whose cosine similarity to [1,0,0,...]
    is a known, predictable function of `angle_degrees` -- lets fallback-ranking
    assertions be exact rather than approximate."""
    radians = np.deg2rad(angle_degrees)
    vec = [np.cos(radians), np.sin(radians)] + [0.0] * (dims - 2)
    return [float(v) for v in vec]


class TestSearchFeatureChunksNumpyFallback:
    def _seed_chunks(self, mongo_store, feature_id, rows):
        docs = [
            {
                "feature_id": feature_id,
                "project_id": "project-1",
                "chunk_index": index,
                "source": "prd",
                "text": text,
                "embedding": embedding,
            }
            for index, (text, embedding) in enumerate(rows)
        ]
        mongo_store.fchunks.insert_many(docs)

    def test_mongomock_has_no_vector_search_so_this_exercises_the_real_fallback(self, mongo_store):
        # Sanity check on the test setup itself: mongomock's aggregate() must actually
        # reject $vectorSearch, or this whole test class would be silently exercising
        # the atlas branch instead of the fallback it claims to test.
        with pytest.raises(Exception):
            list(mongo_store.fchunks.aggregate([{"$vectorSearch": {
                "index": VECTOR_INDEX, "path": "embedding", "queryVector": [0.1, 0.2, 0.3],
                "numCandidates": 40, "limit": 8,
            }}]))

    def test_fallback_ranks_by_cosine_similarity_to_the_query_vector(self, mongo_store):
        self._seed_chunks(mongo_store, "feature-1", [
            ("far chunk", _unit_vector(90)),     # orthogonal to the query -> cos = 0
            ("close chunk", _unit_vector(10)),   # near-parallel to the query -> cos ~ 0.98
            ("mid chunk", _unit_vector(45)),     # cos ~ 0.71
        ])
        query = _unit_vector(0)  # [1, 0, 0]
        out = mongo_store.search_feature_chunks(query, "feature-1", limit=3)
        assert [row["text"] for row in out] == ["close chunk", "mid chunk", "far chunk"]
        assert out[0]["score"] > out[1]["score"] > out[2]["score"]

    def test_fallback_respects_the_limit(self, mongo_store):
        self._seed_chunks(mongo_store, "feature-1", [
            (f"chunk {i}", _unit_vector(i)) for i in range(10)
        ])
        out = mongo_store.search_feature_chunks(_unit_vector(0), "feature-1", limit=3)
        assert len(out) == 3

    def test_fallback_scopes_strictly_to_the_given_feature_id(self, mongo_store):
        self._seed_chunks(mongo_store, "feature-1", [("feature-1 chunk", _unit_vector(0))])
        self._seed_chunks(mongo_store, "feature-2", [("feature-2 chunk", _unit_vector(0))])
        out = mongo_store.search_feature_chunks(_unit_vector(0), "feature-1", limit=10)
        assert [row["text"] for row in out] == ["feature-1 chunk"]

    def test_fallback_no_cross_feature_leakage_even_when_other_feature_scores_higher(self, mongo_store):
        # feature-2's chunk is a PERFECT match for the query; feature-1's chunk is a
        # weak match. If feature_id scoping were broken, feature-2's chunk would win
        # and leak into feature-1's results.
        self._seed_chunks(mongo_store, "feature-1", [("feature-1 weak match", _unit_vector(80))])
        self._seed_chunks(mongo_store, "feature-2", [("feature-2 perfect match", _unit_vector(0))])
        out = mongo_store.search_feature_chunks(_unit_vector(0), "feature-1", limit=10)
        assert len(out) == 1
        assert out[0]["text"] == "feature-1 weak match"

    def test_fallback_returns_empty_list_for_a_feature_with_no_chunks(self, mongo_store):
        out = mongo_store.search_feature_chunks(_unit_vector(0), "feature-with-no-chunks", limit=5)
        assert out == []

    def test_fallback_category_kwarg_is_accepted_and_purely_cosmetic(self, mongo_store):
        # `category` must not change filtering/ranking -- only the debug log line.
        self._seed_chunks(mongo_store, "feature-1", [
            ("only chunk", _unit_vector(0)),
        ])
        with_category = mongo_store.search_feature_chunks(_unit_vector(0), "feature-1", limit=5, category="api")
        without_category = mongo_store.search_feature_chunks(_unit_vector(0), "feature-1", limit=5)
        assert with_category == without_category


# --------------------------------------------------------------------------------
# 3. Embedding-model-switch hardening: numpy fallback degrades gracefully on a
#    dimension mismatch instead of raising and crashing the generation pipeline.
# --------------------------------------------------------------------------------

class TestSearchFeatureChunksDimensionMismatchDegradesGracefully:
    def _seed_chunks(self, mongo_store, feature_id, rows):
        docs = [
            {
                "feature_id": feature_id,
                "project_id": "project-1",
                "chunk_index": index,
                "source": "prd",
                "text": text,
                "embedding": embedding,
            }
            for index, (text, embedding) in enumerate(rows)
        ]
        mongo_store.fchunks.insert_many(docs)

    def test_query_vector_dimension_differs_from_all_stored_chunks_degrades_to_empty(self, mongo_store):
        # The realistic model-switch scenario: every stored chunk shares ONE dimension
        # (768, say, from before a switch), and a NEW query embedding comes in at a
        # different dimension (the new model). All stored rows are internally
        # consistent with each other -- only the query vector is the odd one out.
        self._seed_chunks(mongo_store, "feature-1", [
            ("chunk one", _unit_vector(0, dims=5)),
            ("chunk two", _unit_vector(30, dims=5)),
        ])
        query = _unit_vector(0, dims=3)  # different dimension than the stored chunks
        out = mongo_store.search_feature_chunks(query, "feature-1", limit=5)
        assert out == []  # degraded, not a raised exception

    def test_ragged_stored_embeddings_across_chunks_degrades_to_empty(self, mongo_store):
        # A more pathological case: stored chunks themselves don't even agree with each
        # other (e.g. a reembed job crashed partway through). np.asarray(..., dtype=float)
        # over a ragged list raises ValueError before any dimension comparison is even
        # possible -- must still degrade, not propagate.
        mongo_store.fchunks.insert_many([
            {"feature_id": "feature-1", "project_id": "project-1", "chunk_index": 0,
             "source": "prd", "text": "three-d chunk", "embedding": [0.1, 0.2, 0.3]},
            {"feature_id": "feature-1", "project_id": "project-1", "chunk_index": 1,
             "source": "prd", "text": "five-d chunk", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]},
        ])
        out = mongo_store.search_feature_chunks([0.1, 0.2, 0.3], "feature-1", limit=5)
        assert out == []

    def test_malformed_non_numeric_embedding_degrades_to_empty(self, mongo_store):
        # A corrupt/malformed stored embedding (e.g. a partially-written document) must
        # not crash the pipeline either.
        mongo_store.fchunks.insert_many([
            {"feature_id": "feature-1", "project_id": "project-1", "chunk_index": 0,
             "source": "prd", "text": "corrupt chunk", "embedding": ["not", "a", "number"]},
        ])
        out = mongo_store.search_feature_chunks([0.1, 0.2, 0.3], "feature-1", limit=5)
        assert out == []

    def test_a_degraded_call_does_not_corrupt_a_later_healthy_call(self, mongo_store):
        # Retrieval for one feature hitting a dimension mismatch must not leave any
        # state behind that breaks a subsequent, well-formed call (same or different
        # feature) -- each call is independent.
        self._seed_chunks(mongo_store, "feature-1", [("mismatched", _unit_vector(0, dims=5))])
        bad = mongo_store.search_feature_chunks(_unit_vector(0, dims=3), "feature-1", limit=5)
        assert bad == []

        self._seed_chunks(mongo_store, "feature-2", [("healthy", _unit_vector(0, dims=3))])
        good = mongo_store.search_feature_chunks(_unit_vector(0, dims=3), "feature-2", limit=5)
        assert [row["text"] for row in good] == ["healthy"]

    def test_dimension_mismatch_still_respects_feature_id_filtering(self, mongo_store):
        # The degrade-gracefully fix must not weaken feature_id scoping: a mismatch on
        # feature-1's chunks must not somehow fall through to feature-2's chunks.
        self._seed_chunks(mongo_store, "feature-1", [("feature-1 mismatched", _unit_vector(0, dims=5))])
        self._seed_chunks(mongo_store, "feature-2", [("feature-2 healthy", _unit_vector(0, dims=3))])
        out = mongo_store.search_feature_chunks(_unit_vector(0, dims=3), "feature-1", limit=5)
        assert out == []  # degraded -- NOT feature-2's chunk leaking in

    def test_degraded_retrieval_is_observable_in_logs(self, mongo_store, caplog):
        # A silent empty-list return is indistinguishable from "this feature genuinely
        # has no chunks" -- degrade-gracefully must still be diagnosable after the fact
        # (e.g. by grepping worker logs), not just non-crashing. search_feature_chunks()
        # prints two lines on this path: a "[store][feature_chunks] numpy fallback
        # failed for feature_id=... <exception>" diagnostic with the actual mismatch
        # reason, and the standard "[store][feature_chunks] ... source=numpy_failed
        # results=0 ..." observability line _log_feature_chunk_retrieval() emits on
        # every path -- both must be present, and the source must read "numpy_failed"
        # rather than the healthy "numpy"/"atlas" values, so a log reader (or this
        # test) can tell a degraded call apart from "zero real results, cleanly".
        # These lines go through the app's "wardeniq" logger (core/logging_setup.py),
        # which doesn't propagate to the root logger, so attach caplog's handler to it.
        self._seed_chunks(mongo_store, "feature-1", [("mismatched", _unit_vector(0, dims=5))])
        wq = logging.getLogger("wardeniq")
        wq.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.DEBUG, logger="wardeniq"):
                out = mongo_store.search_feature_chunks(
                    _unit_vector(0, dims=3), "feature-1", limit=5, category="business",
                )
        finally:
            wq.removeHandler(caplog.handler)
        assert out == []
        logged = caplog.text
        assert "numpy fallback failed for feature_id=feature-1" in logged
        assert "dimension mismatch" in logged
        assert "source=numpy_failed" in logged
        assert "category=business" in logged
        assert "results=0" in logged
