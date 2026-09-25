"""API tokens (issue #37): unit tests for the ApiTokensMixin store methods and
the bearer-token principal resolver, in isolation (no real MongoDB — an
in-memory fake store, same pattern as tests/test_dashboard_automation_coverage.py
and tests/test_store_degradation.py).
"""
import time

import auth
from bson import ObjectId
from store import Store


class _FakeCollection:
    """In-memory stand-in supporting exactly the query shapes api_tokens.py and
    token_auth.py issue: find_one({...}), find({...}).sort(...), insert_one,
    update_one (with $set / upsert)."""

    def __init__(self, docs=None):
        self.docs = docs or []

    def _matches(self, doc, query):
        for k, v in (query or {}).items():
            if doc.get(k) != v:
                return False
        return True

    def find_one(self, query=None, projection=None, **kw):
        for d in self.docs:
            if self._matches(d, query):
                return d
        return None

    class _Cursor(list):
        def sort(self, *a, **kw):
            return self

    def find(self, query=None, projection=None):
        return self._Cursor(d for d in self.docs if self._matches(d, query))

    def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = ObjectId()
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()

    def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if self._matches(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)


def _store():
    s = Store.__new__(Store)
    s.api_tokens = _FakeCollection()
    s.api_token_failures = _FakeCollection()
    return s


class TestHashingReuse:
    """The issue explicitly asks to reuse auth.py's existing token hashing rather
    than inventing a scheme — confirm it round-trips and rejects tampering."""

    def test_hash_roundtrip(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        plaintext = "wq_" + auth.gen_invite_token()
        h = auth.hash_token(plaintext)
        assert auth.token_matches(h, plaintext)

    def test_hash_rejects_wrong_token(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        h = auth.hash_token("wq_" + auth.gen_invite_token())
        assert not auth.token_matches(h, "wq_" + auth.gen_invite_token())


class TestApiTokensMixin:
    def test_create_and_list(self):
        s = _store()
        s.create_api_token("CI runner", "hash1", role="viewer")
        tokens = s.list_api_tokens()
        assert len(tokens) == 1
        assert tokens[0]["name"] == "CI runner"
        assert tokens[0]["role"] == "viewer"
        assert tokens[0]["active"] is True
        assert tokens[0]["revoked_at"] is None

    def test_created_token_never_exposes_the_hash(self):
        s = _store()
        out = s.create_api_token("CI runner", "supersecrethash", role="editor")
        assert "token_hash" not in out
        assert "hash" not in str(out.values())

    def test_get_by_hash_returns_active_token(self):
        s = _store()
        s.create_api_token("CI runner", "hash1", role="viewer",
                           all_projects=False, project_ids=["p1"])
        tok = s.get_api_token_by_hash("hash1")
        assert tok is not None
        assert tok["role"] == "viewer"
        assert tok["all_projects"] is False
        assert tok["project_ids"] == ["p1"]

    def test_get_by_hash_unknown_returns_none(self):
        s = _store()
        assert s.get_api_token_by_hash("nope") is None

    def test_revoke_takes_effect_immediately(self):
        s = _store()
        created = s.create_api_token("CI runner", "hash1")
        assert s.get_api_token_by_hash("hash1") is not None
        s.revoke_api_token(created["id"])
        # Revoked — the exact same hash must no longer resolve to a principal.
        assert s.get_api_token_by_hash("hash1") is None
        assert s.get_api_token(created["id"])["revoked_at"] is not None

    def test_expired_token_is_not_returned(self):
        s = _store()
        s.create_api_token("CI runner", "hash1", expires_at=time.time() - 10)
        assert s.get_api_token_by_hash("hash1") is None

    def test_unexpired_token_is_returned(self):
        s = _store()
        s.create_api_token("CI runner", "hash1", expires_at=time.time() + 3600)
        assert s.get_api_token_by_hash("hash1") is not None

    def test_touch_last_used(self):
        s = _store()
        created = s.create_api_token("CI runner", "hash1")
        assert s.get_api_token(created["id"])["last_used_at"] is None
        s.touch_api_token_last_used(created["id"])
        assert s.get_api_token(created["id"])["last_used_at"] is not None


class TestFailureRateLimit:
    def test_count_starts_at_zero(self):
        s = _store()
        assert s.api_token_failure_count("1.2.3.4", 300) == 0

    def test_record_increments_count(self):
        s = _store()
        s.record_api_token_failure("1.2.3.4", 300)
        s.record_api_token_failure("1.2.3.4", 300)
        assert s.api_token_failure_count("1.2.3.4", 300) == 2

    def test_old_failures_outside_window_are_not_counted(self):
        s = _store()
        s.api_token_failures.docs.append(
            {"_id": "1.2.3.4", "attempts": [time.time() - 9999]})
        assert s.api_token_failure_count("1.2.3.4", 300) == 0

    def test_failures_are_scoped_per_key(self):
        s = _store()
        s.record_api_token_failure("1.2.3.4", 300)
        assert s.api_token_failure_count("5.6.7.8", 300) == 0
