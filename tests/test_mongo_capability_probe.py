"""Real capability validation for a candidate MONGO_URI (issue #110) --
app.api.routes.settings._probe_mongo() / _probe_vector() / _version_below().

Regression focus: the probe's vector index uses cosine similarity, and cosine
similarity is undefined for an all-zero vector. A real mongot rejects a $vectorSearch
whose queryVector has zero magnitude, so a probe that indexed/queried [0.0] * dim
reported a healthy MongoDB + mongot stack as search-incapable. The fake-client tests
below pin the exact vector the probe sends; the dbintegration tests at the bottom
prove the behavior against real servers:

  MONGO_TEST_URI         a plain standalone mongod (what CI's db-integration-tests
                         job already provides) -> the "no_replica_set" path.
  MONGO_SEARCH_TEST_URI  a replica set WITH mongot (e.g. the bundled stack, or the
                         Percona stack) -> the full "ok" path, plus a direct
                         demonstration that mongot rejects a zero vector. Skipped
                         when unset, since CI has no mongot.

Both dbintegration tests use a throwaway database name and drop it afterwards.
"""
import math
import os
import uuid

import pytest
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, OperationFailure
from pymongo.operations import SearchIndexModel

from api.routes import settings as settings_mod
from api.routes.settings import (
    MIN_MONGO_VERSION, _probe_mongo, _probe_vector, _version_below,
)
from core.bootstrap import _SEARCH_INDEX_LIMIT_MSG, _SEARCH_REQUIRED_MSG, _search_index_limit
from store.base import TEXT_INDEX, VECTOR_INDEX


def _norm(vec):
    return math.sqrt(sum(x * x for x in vec))


# ------------------------------------------------------------- _version_below
def test_version_below_true_when_older():
    assert _version_below("5.0.9", MIN_MONGO_VERSION) is True


def test_version_below_false_when_equal_or_newer():
    assert _version_below("6.0.11", MIN_MONGO_VERSION) is False
    assert _version_below("8.3.1", MIN_MONGO_VERSION) is False


def test_version_below_fails_open_on_unparseable_version():
    assert _version_below("not-a-version", MIN_MONGO_VERSION) is False
    assert _version_below("", MIN_MONGO_VERSION) is False


# ------------------------------------------------------------- _probe_vector
@pytest.mark.parametrize("dim", [1, 8, 768, 1536, 4096])
def test_probe_vector_has_exactly_the_configured_dimension(dim):
    assert len(_probe_vector(dim)) == dim


@pytest.mark.parametrize("dim", [1, 8, 768, 1536, 4096])
def test_probe_vector_is_non_zero_and_valid_for_cosine(dim):
    vec = _probe_vector(dim)
    assert any(x != 0.0 for x in vec)
    # Cosine similarity divides by the magnitude, so it must be strictly positive
    # and finite; a unit vector also keeps the probe independent of any real model.
    assert _norm(vec) > 0
    assert math.isfinite(_norm(vec))
    assert _norm(vec) == pytest.approx(1.0)


def test_probe_vector_is_deterministic():
    assert _probe_vector(768) == _probe_vector(768)


def test_old_all_zero_vector_was_invalid_for_cosine_similarity():
    # Documents the regression: the vector the probe used before this fix.
    old = [0.0] * 768
    assert _norm(old) == 0.0           # cosine(old, anything) = dot / (0 * |b|) -> undefined
    assert _norm(_probe_vector(768)) != 0.0


@pytest.mark.parametrize("bad", [0, -1, None, "768", 1.5])
def test_probe_vector_rejects_invalid_dimension(bad):
    with pytest.raises(ValueError):
        _probe_vector(bad)


# --------------------------------------------------------------------- fakes
class FakeAdmin:
    def __init__(self, ping_error=None, hello=None, version="8.3.1"):
        self.ping_error = ping_error
        self.hello = hello if hello is not None else {"setName": "rs0"}
        self.version = version

    def command(self, name, *a, **kw):
        if name == "ping":
            if self.ping_error:
                raise self.ping_error
            return {"ok": 1.0}
        if name in ("hello", "ismaster"):
            return self.hello
        raise NotImplementedError(name)


class FakeCollection:
    def __init__(self, create_error=None, ready_after_polls=0, aggregate_error=None,
                 insert_error=None, empty_results=False, create_error_after=0):
        self.inserted = []
        self.create_error_after = create_error_after    # creates that succeed before create_error
        self.index_definitions = {}     # name -> SearchIndexModel.document
        self._queryable = {}
        self.create_error = create_error
        self.insert_error = insert_error
        self.ready_after_polls = ready_after_polls
        self._poll_count = 0
        self.dropped_index_names = []
        self.aggregate_calls = []
        self.aggregate_error = aggregate_error
        self.empty_results = empty_results

    def insert_one(self, doc):
        if self.insert_error:
            raise self.insert_error
        self.inserted.append(doc)

    def create_search_index(self, model):
        if self.create_error and len(self.index_definitions) >= self.create_error_after:
            raise self.create_error
        self.index_definitions[model.document["name"]] = model.document
        self._queryable[model.document["name"]] = False

    def list_search_indexes(self):
        self._poll_count += 1
        ready = self._poll_count > self.ready_after_polls
        return [{"name": n, "queryable": ready} for n in self._queryable]

    def drop_search_index(self, name):
        self.dropped_index_names.append(name)
        self._queryable.pop(name, None)

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        if self.aggregate_error:
            raise self.aggregate_error
        return iter([] if self.empty_results else [{"_id": "probe"}])


class FakeDB:
    def __init__(self, coll, existing_names=None, list_error=None):
        self._coll = coll
        self.existing_names = set(existing_names or [])
        self.list_error = list_error
        self.dropped_collections = []
        self.requested_names = []

    def list_collection_names(self):
        if self.list_error:
            raise self.list_error
        return list(self.existing_names)

    def __getitem__(self, name):
        self.requested_names.append(name)
        return self._coll

    def drop_collection(self, name):
        self.dropped_collections.append(name)


class FakeMongoClient:
    def __init__(self, admin=None, db=None, server_info_error=None):
        self.admin = admin or FakeAdmin()
        self._db = db or FakeDB(FakeCollection())
        self.server_info_error = server_info_error
        self.closed = False

    def __getitem__(self, name):
        return self._db

    def server_info(self):
        if self.server_info_error:
            raise self.server_info_error
        return {"version": self.admin.version}

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fast_probe(monkeypatch):
    # No real waiting: the poll loops sleep 1s between attempts.
    monkeypatch.setattr(settings_mod.time, "sleep", lambda s: None)


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(settings_mod, "MongoClient", lambda *a, **kw: client)


def _healthy(coll=None, **kw):
    coll = coll or FakeCollection()
    return FakeMongoClient(db=FakeDB(coll), **kw), coll


# --------------------------------------------------- probe uses the valid vector
def test_probe_indexes_and_queries_with_the_non_zero_vector_at_the_configured_dim(monkeypatch):
    client, coll = _healthy()
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/", dim=384)
    assert r["status"] == "ok"

    expected = _probe_vector(384)
    # The inserted probe document carries the valid vector...
    assert coll.inserted[0]["embedding"] == expected
    assert len(coll.inserted[0]["embedding"]) == 384
    assert _norm(coll.inserted[0]["embedding"]) > 0
    # ...the vector index is declared at exactly that dimension with cosine...
    field = coll.index_definitions[VECTOR_INDEX]["definition"]["fields"][0]
    assert field["numDimensions"] == 384 and field["similarity"] == "cosine"
    # ...and the $vectorSearch query vector is the same valid, non-zero vector.
    vs = [p[0]["$vectorSearch"] for p in coll.aggregate_calls if "$vectorSearch" in p[0]]
    assert len(vs) == 1
    assert vs[0]["queryVector"] == expected
    assert len(vs[0]["queryVector"]) == 384
    assert _norm(vs[0]["queryVector"]) > 0


def test_probe_never_sends_a_zero_vector_anywhere(monkeypatch):
    client, coll = _healthy()
    _patch_client(monkeypatch, client)
    _probe_mongo("mongodb://x/", dim=768)
    assert _norm(coll.inserted[0]["embedding"]) > 0
    for pipeline in coll.aggregate_calls:
        stage = pipeline[0].get("$vectorSearch")
        if stage:
            assert _norm(stage["queryVector"]) > 0


def test_probe_defaults_to_the_configured_embedding_dimension(monkeypatch):
    client, coll = _healthy()
    _patch_client(monkeypatch, client)
    _probe_mongo("mongodb://x/")
    assert len(coll.inserted[0]["embedding"]) == settings_mod.EMBED_DIM


def test_probe_still_creates_both_search_indexes_and_runs_both_queries(monkeypatch):
    # The fix must not weaken the check: it still creates a vector AND a text index
    # and must get a result back from a real $vectorSearch and a real $search.
    client, coll = _healthy()
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/", dim=8)
    assert r["status"] == "ok" and r["search_ok"] is True
    assert coll.index_definitions[VECTOR_INDEX]["type"] == "vectorSearch"
    assert coll.index_definitions[TEXT_INDEX]["type"] == "search"
    stages = [list(p[0])[0] for p in coll.aggregate_calls]
    assert "$vectorSearch" in stages and "$search" in stages


# ------------------------------------------------------------------ status semantics
def test_probe_construction_failure_is_unreachable(monkeypatch):
    def boom(*a, **kw):
        raise OSError("bad connection string")
    monkeypatch.setattr(settings_mod, "MongoClient", boom)
    r = _probe_mongo("not-a-uri")
    assert r["status"] == "unreachable" and r["reachable"] is False


def test_probe_ping_failure_is_unreachable(monkeypatch):
    client = FakeMongoClient(admin=FakeAdmin(ping_error=OSError("connection refused")))
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "unreachable" and r["reachable"] is False
    assert "connection refused" in r["detail"]
    assert client.closed is True


def test_probe_standalone_is_no_replica_set(monkeypatch):
    client, coll = _healthy(admin=FakeAdmin(hello={"isWritablePrimary": True}))
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_replica_set"
    assert r["reachable"] is True and r["replica_set"] is False
    assert coll.inserted == []      # gated before anything is written


def test_probe_old_server_is_version_too_old(monkeypatch):
    client, coll = _healthy(admin=FakeAdmin(version="5.0.9"))
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "version_too_old" and r["server_version"] == "5.0.9"
    assert coll.inserted == []


def test_probe_unauthorized_index_creation_is_insufficient_privileges(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("not authorized on x to execute command", code=13))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "insufficient_privileges"
    assert "not authorized" not in r["detail"]      # actionable text, not the raw driver error


def test_probe_search_unsupported_is_no_search(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("no such command: 'createSearchIndexes'"))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search" and r["search_ok"] is False


# Raw text a real Atlas tier cap produces; the marker lets tests prove the raw driver
# text is not what the caller is shown.
RAW_LIMIT_MARKER = "raw-driver-marker-7f3a"
ATLAS_LIMIT_ERROR = (
    "Error: you have reached the maximum number of FTS indexes allowed for this instance "
    f"size (M0: 3). {RAW_LIMIT_MARKER} Upgrade the cluster tier to create more search indexes."
)


def test_limit_error_text_is_recognised_by_the_existing_helper():
    # Guards the fixture itself: the probe must be reusing core.bootstrap's helper,
    # not matching its own strings, so the fixture has to be something that helper accepts.
    assert _search_index_limit(OperationFailure(ATLAS_LIMIT_ERROR)) is True


@pytest.mark.parametrize("after", [0, 1], ids=["cap_hit_on_vector_index", "cap_hit_on_text_index"])
def test_probe_index_limit_error_returns_no_search_with_the_curated_message(monkeypatch, after):
    coll = FakeCollection(create_error=OperationFailure(ATLAS_LIMIT_ERROR, code=8000),
                          create_error_after=after)
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search" and r["search_ok"] is False
    # The existing, curated, actionable message -- exactly, not a copy of it.
    assert r["detail"] == _SEARCH_INDEX_LIMIT_MSG
    # ...and not the raw (previously truncated) driver text.
    assert RAW_LIMIT_MARKER not in r["detail"]
    assert "could not create a search index" not in r["detail"]


def test_probe_index_limit_error_still_cleans_up(monkeypatch):
    # Cap hit on the SECOND index: the first one already exists and must be removed.
    coll = FakeCollection(create_error=OperationFailure(ATLAS_LIMIT_ERROR), create_error_after=1)
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search"
    assert coll.dropped_index_names == [VECTOR_INDEX]
    assert client._db.dropped_collections == client._db.requested_names
    assert client.closed is True


def test_probe_index_limit_error_is_logged_server_side_not_returned(monkeypatch):
    class Recorder:
        def __init__(self):
            self.lines = []

        def warning(self, fmt, *args):
            self.lines.append(fmt % args)

        def __getattr__(self, name):        # info/error/... are irrelevant here
            return lambda *a, **k: None

    rec = Recorder()
    monkeypatch.setattr(settings_mod, "log", rec)
    coll = FakeCollection(create_error=OperationFailure(ATLAS_LIMIT_ERROR))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://user:Pw0rdMarker@db.example.test/")
    logged = "\n".join(rec.lines)
    assert RAW_LIMIT_MARKER in logged               # diagnosable by an operator...
    assert RAW_LIMIT_MARKER not in repr(r)          # ...but not handed to the caller
    assert "Pw0rdMarker" not in logged and "db.example.test" not in logged


@pytest.mark.parametrize("raw", [
    "Search index creation failed: index definition is invalid for field embedding",
    "an unrelated server error occurred while creating the index",
    "FTS index build queue is busy, try again",          # mentions FTS indexes, but not a cap
])
def test_probe_generic_create_failure_is_not_misclassified_as_the_index_limit(monkeypatch, raw):
    coll = FakeCollection(create_error=OperationFailure(raw))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search"
    assert r["detail"] != _SEARCH_INDEX_LIMIT_MSG
    assert r["detail"].startswith("could not create a search index:")
    assert raw[:60] in r["detail"]                      # generic diagnostic preserved


def test_probe_search_unsupported_still_uses_the_requires_search_message(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("no such command: 'createSearchIndexes'"))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["detail"] == _SEARCH_REQUIRED_MSG
    assert r["detail"] != _SEARCH_INDEX_LIMIT_MSG


def test_probe_unauthorized_is_still_insufficient_privileges_not_index_limit(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("not authorized on x to execute command", code=13))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "insufficient_privileges"
    assert r["detail"] != _SEARCH_INDEX_LIMIT_MSG


def test_probe_full_success_reports_ok_and_cleans_up(monkeypatch):
    client, coll = _healthy()
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/", dim=8)
    assert r["status"] == "ok" and r["search_ok"] and r["replica_set"] and r["reachable"]
    assert set(coll.dropped_index_names) == {VECTOR_INDEX, TEXT_INDEX}
    assert client._db.dropped_collections == client._db.requested_names
    assert client._db.requested_names[0].startswith("wardeniq_probe_")
    assert client.closed is True


def test_probe_query_failure_is_no_search_and_still_cleans_up(monkeypatch):
    coll = FakeCollection(aggregate_error=OperationFailure("Cosine similarity cannot be computed"))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search"
    assert "a query failed" in r["detail"]
    assert client._db.dropped_collections       # scratch collection still removed


def test_probe_empty_results_after_queryable_is_no_search(monkeypatch):
    monkeypatch.setattr(settings_mod, "PROBE_SEARCH_TIMEOUT_S", 0)
    client, coll = _healthy(FakeCollection(empty_results=True))
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search" and "no results" in r["detail"]
    assert client._db.dropped_collections


def test_probe_indexes_never_queryable_times_out_and_cleans_up(monkeypatch):
    monkeypatch.setattr(settings_mod, "PROBE_SEARCH_TIMEOUT_S", 0)
    client, coll = _healthy(FakeCollection(ready_after_polls=10**9))
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")
    assert r["status"] == "no_search" and "didn't become queryable" in r["detail"]
    assert client._db.dropped_collections
    assert set(coll.dropped_index_names) == {VECTOR_INDEX, TEXT_INDEX}


def test_probe_scratch_name_avoids_an_existing_collision(monkeypatch):
    seq = iter(["aa" * 8, "bb" * 8])
    monkeypatch.setattr(settings_mod.secrets, "token_hex", lambda n: next(seq))
    coll = FakeCollection()
    db = FakeDB(coll, existing_names={"wardeniq_probe_" + "aa" * 8})
    _patch_client(monkeypatch, FakeMongoClient(db=db))
    assert _probe_mongo("mongodb://x/", dim=8)["status"] == "ok"
    assert db.requested_names[0] == "wardeniq_probe_" + "bb" * 8


def test_probe_works_without_list_collections_privilege(monkeypatch):
    db = FakeDB(FakeCollection(), list_error=OperationFailure("not authorized", code=13))
    _patch_client(monkeypatch, FakeMongoClient(db=db))
    assert _probe_mongo("mongodb://x/", dim=8)["status"] == "ok"


def test_probe_unexpected_error_is_reported_not_raised(monkeypatch):
    coll = FakeCollection(insert_error=AutoReconnect("connection dropped"))
    client, _ = _healthy(coll)
    _patch_client(monkeypatch, client)
    r = _probe_mongo("mongodb://x/")            # must not raise
    assert r["status"] == "unreachable" and "validation could not complete" in r["detail"]
    assert r["search_ok"] is False
    assert client._db.dropped_collections       # cleanup still ran
    assert client.closed is True


def test_probe_result_never_contains_the_uri_or_credentials(monkeypatch):
    secret_uri = "mongodb://user:Sup3rSecretPw@db.example.test:27017/?replicaSet=rs0"
    client = FakeMongoClient(admin=FakeAdmin(ping_error=OSError("connection refused")))
    _patch_client(monkeypatch, client)
    r = _probe_mongo(secret_uri)
    assert "Sup3rSecretPw" not in repr(r) and secret_uri not in repr(r)


# ------------------------------------------------------------ dbintegration (real servers)
MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")
MONGO_SEARCH_TEST_URI = os.getenv("MONGO_SEARCH_TEST_URI", "")


def _reachable(uri):
    try:
        MongoClient(uri, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


def _is_replica_set(uri):
    c = MongoClient(uri, serverSelectionTimeoutMS=1500)
    try:
        return bool(c.admin.command("hello").get("setName"))
    finally:
        c.close()


@pytest.fixture()
def throwaway_db(monkeypatch):
    """Point the probe at a unique database so a real run can never touch app data,
    and drop it afterwards."""
    name = f"wardeniq_probe_it_{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings_mod, "DB_NAME", name)
    yield name


@pytest.mark.dbintegration
def test_real_standalone_server_is_reported_as_no_replica_set(throwaway_db):
    if not _reachable(MONGO_TEST_URI):
        pytest.skip(f"no MongoDB reachable at MONGO_TEST_URI={MONGO_TEST_URI!r}")
    if _is_replica_set(MONGO_TEST_URI):
        pytest.skip("MONGO_TEST_URI is a replica set; this test needs a standalone mongod")
    r = _probe_mongo(MONGO_TEST_URI, dim=8)
    assert r["status"] == "no_replica_set"
    assert r["reachable"] is True and r["replica_set"] is False and r["search_ok"] is False
    assert r["server_version"]


@pytest.mark.dbintegration
def test_real_mongot_target_reaches_ok_and_leaves_nothing_behind(throwaway_db):
    if not MONGO_SEARCH_TEST_URI:
        pytest.skip("set MONGO_SEARCH_TEST_URI to a replica set with mongot to run this")
    dim = 768
    r = _probe_mongo(MONGO_SEARCH_TEST_URI, dim=dim)
    c = MongoClient(MONGO_SEARCH_TEST_URI, serverSelectionTimeoutMS=4000)
    try:
        leftovers = c[throwaway_db].list_collection_names()
        assert r["status"] == "ok", r
        assert r["search_ok"] is True and r["replica_set"] is True
        assert leftovers == [], f"probe left scratch collections behind: {leftovers}"
    finally:
        c.drop_database(throwaway_db)
        c.close()


@pytest.mark.dbintegration
def test_real_mongot_rejects_a_zero_vector_but_accepts_the_probe_vector(throwaway_db):
    """The root cause, against a real mongot: a cosine vector index cannot be queried
    with a zero-magnitude vector, but can with the probe's deterministic vector."""
    if not MONGO_SEARCH_TEST_URI:
        pytest.skip("set MONGO_SEARCH_TEST_URI to a replica set with mongot to run this")
    import time
    dim = 8
    c = MongoClient(MONGO_SEARCH_TEST_URI, serverSelectionTimeoutMS=4000)
    coll = c[throwaway_db][f"zero_vec_{uuid.uuid4().hex[:8]}"]
    try:
        good = _probe_vector(dim)
        coll.insert_one({"embedding": good})
        coll.create_search_index(SearchIndexModel(
            definition={"fields": [{"type": "vector", "path": "embedding",
                                    "numDimensions": dim, "similarity": "cosine"}]},
            name=VECTOR_INDEX, type="vectorSearch"))
        deadline = time.time() + 90
        while time.time() < deadline and not all(i.get("queryable") for i in coll.list_search_indexes()):
            time.sleep(1)

        def query(vec):
            return list(coll.aggregate([{"$vectorSearch": {
                "index": VECTOR_INDEX, "path": "embedding", "queryVector": vec,
                "numCandidates": 10, "limit": 1}}]))

        assert len(query(good)) == 1
        with pytest.raises(OperationFailure) as exc:
            query([0.0] * dim)
        assert "cosine" in str(exc.value).lower()
    finally:
        for i in list(coll.list_search_indexes()):
            coll.drop_search_index(i["name"])
        c.drop_database(throwaway_db)
        c.close()
