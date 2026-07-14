"""DB integration tests: exercise store.py against a REAL MongoDB, as opposed
to the mocked-Store unit tests elsewhere in tests/.

Requires MONGO_TEST_URI (e.g. mongodb://localhost:27017). If it's unset or the
server is unreachable, every test here is skipped — so a plain `pytest` run on
a laptop without MongoDB running still passes. CI runs these explicitly via
`pytest -m dbintegration` in the "db-integration-tests" job, which brings up a
`mongo` service container (see .github/workflows/ci.yml).

Scope note: this uses a single standalone `mongo` container, which has no
mongot / Atlas Search. `Store.ensure_indexes()` therefore fails partway
through (once it reaches the vector/text search indexes) — expected here, and
tolerated below — so vectorSearch-backed methods (search_features,
search_cases, dedup, ...) are NOT covered by this suite. Those need the full
docker-compose stack (PSMDB + mongot) and are exercised manually / in a real
deployment, per CLAUDE.md's architecture notes.

Each test gets its own throwaway database (dropped at teardown) so runs never
collide or leave data behind.
"""
import os
import time
import uuid

import pytest
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://localhost:27017")


def _server_reachable() -> bool:
    try:
        MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if not _server_reachable():
    pytest.skip(
        f"no MongoDB reachable at {MONGO_TEST_URI!r} (set MONGO_TEST_URI to run "
        "db-integration tests)",
        allow_module_level=True,
    )

# Import after the reachability check so a module without a live Mongo never
# pays the cost of importing store.py for nothing.
import crypto  # noqa: E402
from bson import ObjectId  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture()
def store():
    db_name = f"wardeniq_test_{uuid.uuid4().hex[:10]}"
    s = Store(MONGO_TEST_URI, db_name, dim=8)
    try:
        s.ensure_indexes()
    except Exception:  # noqa: BLE001
        # Expected against a plain mongod with no mongot/Atlas Search: the plain
        # (non-search) indexes created earlier in ensure_indexes() already landed.
        pass
    try:
        yield s
    finally:
        s.client.drop_database(db_name)
        s.client.close()


# ------------------------------------------------------------------ plumbing
def test_ping_succeeds(store):
    assert store.ping() is True


def test_ensure_indexes_creates_core_collections(store):
    names = set(store.db.list_collection_names())
    for expected in ("projects", "features", "test_steps", "test_cases",
                     "associations", "users"):
        assert expected in names
    # The plain unique index on users.email must exist even though the
    # search/vector indexes further down ensure_indexes() couldn't be created.
    idx_names = {i["name"] for i in store.users.list_indexes()}
    assert any("email" in n for n in idx_names)


# --------------------------------------------------------------- projects
def test_project_crud_round_trip(store):
    pid = store.create_project("Acme Checkout", description="payments flow")
    got = store.get_project(pid)
    assert got is not None
    assert got["id"] == pid
    assert got["name"] == "Acme Checkout"

    updated = store.update_project(pid, {"description": "updated desc"})
    assert updated["description"] == "updated desc"

    projects = store.list_projects()
    assert any(p["id"] == pid for p in projects)


def test_get_project_rejects_malformed_id(store):
    assert store.get_project("not-an-object-id") is None


# ------------------------------------------------------------------- users
def test_user_create_and_lookup_round_trip(store):
    u = store.create_user("qa@example.com", "QA Person", role="editor")
    assert u["email"] == "qa@example.com"
    assert u["role"] == "editor"

    by_id = store.get_user(u["id"])
    by_email = store.get_user_by_email("qa@example.com")
    assert by_id["id"] == u["id"]
    assert by_email["id"] == u["id"]


def test_user_email_unique_constraint_enforced(store):
    store.create_user("dup@example.com", "First")
    with pytest.raises(DuplicateKeyError):
        store.create_user("dup@example.com", "Second")


# ---------------------------------------------------------------- settings
def test_settings_round_trip_with_encrypted_secret(store):
    secret_plain = "sk-super-secret-api-key"
    store.save_settings({
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "llm_api_key_enc": crypto.encrypt(secret_plain),
        "configured": True,
    })
    s = store.get_settings()
    assert s["llm_provider"] == "openai"
    assert s["configured"] is True
    assert crypto.decrypt(s["llm_api_key_enc"]) == secret_plain


# ---------------------------------------------------------------- features
def test_feature_create_and_get(store):
    pid = store.create_project("Feature Test Project")
    dim = store.dim
    fid = store.create_feature(
        name="User can log in",
        project_id=pid,
        sources=["prd.pdf"],
        text="Users authenticate with email and password.",
        summary="Login",
        embedding=[0.1] * dim,
    )
    assert fid is not None
    feat = store.get_feature(fid)
    assert feat is not None
    assert feat["project_id"] == pid
    assert feat["name"] == "User can log in"


# ------------------------------------------------------------- misc timing
def test_created_at_timestamps_are_recent(store):
    pid = store.create_project("Timestamp check")
    raw = store.projects.find_one({"_id": ObjectId(pid)})
    assert abs(raw["created_at"] - time.time()) < 60
