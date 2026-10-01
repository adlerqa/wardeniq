"""Real capability validation for a candidate MONGO_URI (issue #110) —
app.api.routes.settings._probe_mongo()/_version_below(). Companion suites:
  tests/test_db_config_migrate_routes.py — the two endpoints that call this.
  tests/test_db_integration.py           — same "real MongoDB" pattern this
                                            suite's dbintegration test follows.

Fakes below duck-type just the pymongo surface _probe_mongo() actually calls
(admin.command, server_info, list_collection_names, insert_one,
create_search_index, list_search_indexes, drop_search_index, aggregate,
drop_collection) — no real MongoDB needed for most of this file. The one
dbintegration test hits a REAL standalone `mongo` (no replica set, no mongot —
exactly what CI's db-integration-tests job already provides, see
.github/workflows/ci.yml), which is genuine infrastructure for the
"no_replica_set" path without needing mongot anywhere.
"""
import os

import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from api.routes import settings as settings_mod
from api.routes.settings import MIN_MONGO_VERSION, _probe_mongo, _version_below
from store.base import TEXT_INDEX, VECTOR_INDEX


# --------------------------------------------------------------------- _version_below
def test_version_below_true_when_older():
    assert _version_below("5.0.9", MIN_MONGO_VERSION) is True


def test_version_below_false_when_equal_or_newer():
    assert _version_below("6.0.11", MIN_MONGO_VERSION) is False
    assert _version_below("8.3.1", MIN_MONGO_VERSION) is False


def test_version_below_fails_open_on_unparseable_version():
    # A weird/foreign version string must never block a real database — the
    # capability probe that follows is the actual gate, not this pre-check.
    assert _version_below("not-a-version", MIN_MONGO_VERSION) is False
    assert _version_below("", MIN_MONGO_VERSION) is False


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
    def __init__(self, create_error=None, ready_after_polls=0, aggregate_error=None):
        self.name = None
        self.inserted = []
        self._indexes = {}          # name -> queryable bool
        self.create_error = create_error
        self.ready_after_polls = ready_after_polls
        self._poll_count = 0
        self.dropped_index_names = []
        self.aggregate_calls = []
        self.aggregate_error = aggregate_error

    def insert_one(self, doc):
        self.inserted.append(doc)

    def create_search_index(self, model):
        if self.create_error:
            raise self.create_error
        self._indexes[model.document["name"]] = False

    def list_search_indexes(self):
        self._poll_count += 1
        ready = self._poll_count > self.ready_after_polls
        return [{"name": n, "queryable": ready} for n in self._indexes]

    def drop_search_index(self, name):
        self.dropped_index_names.append(name)
        self._indexes.pop(name, None)

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        if self.aggregate_error:
            raise self.aggregate_error
        return iter([{"_id": "probe"}])


class FakeDB:
    def __init__(self, coll, existing_names=None):
        self._coll = coll
        self.existing_names = set(existing_names or [])
        self.dropped_collections = []

    def list_collection_names(self):
        return list(self.existing_names)

    def __getitem__(self, name):
        self._coll.name = name
        return self._coll

    def drop_collection(self, name):
        self.dropped_collections.append(name)


class FakeMongoClient:
    def __init__(self, uri=None, serverSelectionTimeoutMS=None, admin=None, db=None,
                 construct_error=None):
        if construct_error:
            raise construct_error
        self.admin = admin or FakeAdmin()
        self._db = db or FakeDB(FakeCollection())
        self.closed = False

    def __getitem__(self, name):
        return self._db

    def server_info(self):
        return {"version": self.admin.version}

    def close(self):
        self.closed = True


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(settings_mod, "MongoClient", lambda *a, **kw: client)


# --------------------------------------------------------------------- _probe_mongo
def test_probe_mongo_construction_failure_is_unreachable(monkeypatch):
    def boom(*a, **kw):
        raise OSError("bad connection string")
    monkeypatch.setattr(settings_mod, "MongoClient", boom)
    result = _probe_mongo("mongodb://nope/")
    assert result == {"reachable": False, "replica_set": False, "server_version": None,
                       "search_ok": False, "status": "unreachable",
                       "detail": "bad connection string"}


def test_probe_mongo_ping_failure_is_unreachable(monkeypatch):
    client = FakeMongoClient(admin=FakeAdmin(ping_error=Exception("server selection timed out")))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://unreachable-host/")
    assert result["reachable"] is False
    assert result["status"] == "unreachable"
    assert "timed out" in result["detail"]
    assert client.closed  # always cleaned up, even on early failure


def test_probe_mongo_standalone_is_no_replica_set(monkeypatch):
    client = FakeMongoClient(admin=FakeAdmin(hello={}))  # no setName
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://standalone/")
    assert result["reachable"] is True
    assert result["replica_set"] is False
    assert result["status"] == "no_replica_set"
    assert "replica set" in result["detail"]
    # server_version is fetched unconditionally (before the replica-set gate), so a
    # caller learns it even when this earlier gate is what actually failed.
    assert result["server_version"] == "8.3.1"


def test_probe_mongo_version_too_old(monkeypatch):
    client = FakeMongoClient(admin=FakeAdmin(version="4.4.0"))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://old-server/")
    assert result["replica_set"] is True
    assert result["status"] == "version_too_old"
    assert "4.4.0" in result["detail"]


def test_probe_mongo_insufficient_privileges(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("not authorized on db", code=13))
    client = FakeMongoClient(db=FakeDB(coll))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://readonly-user/")
    assert result["status"] == "insufficient_privileges"
    assert "authorized" in result["detail"]
    # Cleanup must still run even though index creation never got anywhere.
    assert client._db.dropped_collections == [coll.name]


def test_probe_mongo_search_unsupported(monkeypatch):
    coll = FakeCollection(create_error=OperationFailure("no such command: 'createSearchIndexes'"))
    client = FakeMongoClient(db=FakeDB(coll))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://no-search/")
    assert result["status"] == "no_search"
    assert result["search_ok"] is False
    assert client._db.dropped_collections == [coll.name]


def test_probe_mongo_full_success_cleans_up_scratch_resources(monkeypatch):
    coll = FakeCollection(ready_after_polls=0)
    client = FakeMongoClient(db=FakeDB(coll))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://good-server/", dim=1536)
    assert result == {"reachable": True, "replica_set": True, "server_version": "8.3.1",
                       "search_ok": True, "status": "ok", "detail": "ok"}
    # The probe ran at the CALLER's dimension, not some hardcoded default.
    assert coll.inserted[0]["embedding"] == [0.0] * 1536
    # Both indexes (and only those) were created, verified, then dropped — nothing
    # left behind, and no real application collection was ever touched.
    assert set(coll.dropped_index_names) == {VECTOR_INDEX, TEXT_INDEX}
    assert client._db.dropped_collections == [coll.name]
    assert coll.name.startswith("wardeniq_probe_")
    assert len(coll.aggregate_calls) == 2  # one $vectorSearch, one $search
    assert client.closed


def test_probe_mongo_query_failure_after_index_ready(monkeypatch):
    coll = FakeCollection(ready_after_polls=0, aggregate_error=Exception("boom"))
    client = FakeMongoClient(db=FakeDB(coll))
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://flaky-query/")
    assert result["status"] == "no_search"
    assert "query failed" in result["detail"]
    # Still cleaned up despite the late failure.
    assert set(coll.dropped_index_names) == {VECTOR_INDEX, TEXT_INDEX}
    assert client._db.dropped_collections == [coll.name]


def test_probe_mongo_never_ready_times_out_and_still_cleans_up(monkeypatch):
    # ready_after_polls this high never trips within the bounded poll deadline —
    # a permanently-syncing/broken mongot must not hang the caller forever.
    coll = FakeCollection(ready_after_polls=10_000)
    client = FakeMongoClient(db=FakeDB(coll))
    _patch_client(monkeypatch, client)

    # Fast-forward the wall clock instead of sleeping for real 15s.
    fake_now = {"t": 0.0}
    def _time():
        fake_now["t"] += 2.0
        return fake_now["t"]
    monkeypatch.setattr(settings_mod.time, "time", _time)
    monkeypatch.setattr(settings_mod.time, "sleep", lambda s: None)

    result = _probe_mongo("mongodb://slow-sync/")
    assert result["status"] == "no_search"
    assert "didn't become queryable" in result["detail"]
    # The indexes exist (just never confirmed queryable) — cleanup must still drop
    # them, not just the collection, so nothing is left behind on the target.
    assert set(coll.dropped_index_names) == {VECTOR_INDEX, TEXT_INDEX}
    assert client._db.dropped_collections == [coll.name]


def test_probe_mongo_scratch_collection_name_avoids_existing_collision(monkeypatch):
    coll = FakeCollection()
    # Simulate every "random" name colliding once, forcing a retry — the probe
    # must never write into something that already exists.
    real_token_hex = settings_mod.secrets.token_hex
    calls = {"n": 0}
    def flaky_token_hex(nbytes):
        calls["n"] += 1
        return "collide" if calls["n"] == 1 else real_token_hex(nbytes)
    monkeypatch.setattr(settings_mod.secrets, "token_hex", flaky_token_hex)
    db = FakeDB(coll, existing_names={"wardeniq_probe_collide"})
    client = FakeMongoClient(db=db)
    _patch_client(monkeypatch, client)
    result = _probe_mongo("mongodb://good-server/")
    assert result["status"] == "ok"
    assert coll.name != "wardeniq_probe_collide"


# --------------------------------------------------------------------- real MongoDB
MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")


def _server_reachable() -> bool:
    try:
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.dbintegration
def test_probe_mongo_against_real_standalone_server_detects_no_replica_set():
    """CI's db-integration-tests job runs a bare `mongo:7` with no --replSet — the
    exact "reachable, real server, but not a replica set" shape this test exercises
    against genuine infrastructure rather than a fake, matching how
    tests/test_db_integration.py already validates against a real (search-less)
    MongoDB rather than mocks."""
    if not _server_reachable():
        pytest.skip(f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI)")
    result = _probe_mongo(MONGO_TEST_URI)
    assert result["reachable"] is True
    assert result["server_version"]  # a real version string came back
    assert result["replica_set"] is False
    assert result["status"] == "no_replica_set"
