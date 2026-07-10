"""Shared fixtures + lightweight fakes for the coverage / commit-analysis / mind-map tests.

These fakes duck-type the real collaborators (LLM, Embedder, Store) so subsystem logic
can be unit-tested with no MongoDB, no Ollama and no GitHub. The golden fixtures
(`sample_diff_patch`, `sample_pr_files`, `feature_with_cases`) are the labelled inputs that
later phases assert grounded-matching accuracy against.
"""
import pytest


# --------------------------------------------------------------------------- fakes
class FakeLLM:
    """Stand-in for app.llm.LLM. Returns a scripted dict from `chat_json`.

    Pass `response` for a fixed reply, or `handler(system, user) -> dict` for dynamic
    replies. `calls` records every invocation so tests can assert prompt content.
    """

    def __init__(self, response=None, handler=None, raise_exc=None):
        self.response = response if response is not None else {}
        self.handler = handler
        self.raise_exc = raise_exc
        self.calls = []

    def chat_json(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, "kwargs": kwargs})
        if self.raise_exc:
            raise self.raise_exc
        if self.handler:
            return self.handler(system, user)
        return self.response


class FakeEmbedder:
    """Stand-in for app.embeddings.Embedder. Deterministic vectors, no network.

    The vector is irrelevant for tests that fake `search_features`; it just needs to
    be a stable list so callers don't blow up.
    """

    def __init__(self, dim=8):
        self.dim = dim
        self.calls = []

    def embed(self, text, task="document"):
        self.calls.append({"text": text, "task": task})
        # cheap stable pseudo-vector derived from the text length
        n = float(len(text or "") % 97)
        return [(n + i) / 100.0 for i in range(self.dim)]


class FakeStore:
    """Stand-in for the parts of store.Store that coverage helpers touch.

    Configure with `keyed={key: [feature_id, ...]}` and `feature_matches=[{id,score}, ...]`.
    """

    def __init__(self, keyed=None, feature_matches=None, epics=None):
        self._keyed = keyed or {}
        self._feature_matches = feature_matches or []
        # epics: {epic_key: feature_id} — 1:1 epic<->feature binding
        self._epics = epics or {}
        self.calls = []

    def features_by_key(self, project_id, key):
        self.calls.append(("features_by_key", project_id, key))
        return self._keyed.get(key, [])

    def feature_by_epic(self, project_id, epic_key):
        self.calls.append(("feature_by_epic", project_id, epic_key))
        return self._epics.get(epic_key)

    def search_features(self, emb, project_id=None, limit=3):
        self.calls.append(("search_features", project_id, limit))
        return self._feature_matches[:limit]


class FakeJira:
    """Stand-in for jira.Jira used by PR->epic->feature mapping."""

    def __init__(self, parents=None, ok=True):
        self._parents = parents or {}   # ticket_key -> epic_key
        self._ok = ok

    def ok(self):
        return self._ok

    def parent_epic(self, key):
        return self._parents.get(key, "")


# --------------------------------------------------------------------------- fixtures
@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def sample_diff_patch():
    """A unified-diff hunk that adds an HTTP route AND a function symbol.

    Grounded extraction (Phase 1) must find: endpoint POST /api/login and symbol `login`.
    """
    return (
        "@@ -0,0 +1,9 @@\n"
        "+from fastapi import APIRouter\n"
        "+router = APIRouter()\n"
        "+\n"
        "+@router.post(\"/api/login\")\n"
        "+def login(payload):\n"
        "+    user = authenticate(payload)\n"
        "+    return issue_session(user)\n"
        "+\n"
        "+def logout(session_id):\n"
        "+    return revoke_session(session_id)\n"
    )


@pytest.fixture
def sample_pr_files(sample_diff_patch):
    """PR file list as returned by github.get_pull_files — one impl file + one test file."""
    return [
        {"filename": "app/auth/login.py", "status": "added",
         "additions": 9, "deletions": 0, "patch": sample_diff_patch},
        {"filename": "tests/test_login.py", "status": "added",
         "additions": 12, "deletions": 0,
         "patch": "@@ +1,5 @@\n+def test_login_ok():\n+    assert login({}) is not None\n"},
    ]


@pytest.fixture
def feature_with_cases():
    """A feature + 3 labelled cases: one clearly implemented, one partial, one absent.

    Used by later phases to assert covered / partial / uncovered verdicts.
    """
    return {
        "feature": {"id": "f1", "name": "User authentication", "version": 1,
                    "text": "Users can log in with email+password and log out. "
                            "Deleting an account is also supported."},
        "cases": [
            {"id": "c-login", "title": "Login with valid credentials issues a session",
             "type": "functional",
             "steps": [{"action": "POST /api/login with valid creds",
                        "expected": "200 + session token"}]},
            {"id": "c-logout", "title": "Logout revokes the active session",
             "type": "functional",
             "steps": [{"action": "call logout(session_id)", "expected": "session revoked"}]},
            {"id": "c-delete", "title": "Delete account removes all user data",
             "type": "functional",
             "steps": [{"action": "DELETE /api/account", "expected": "user data purged"}]},
        ],
    }
