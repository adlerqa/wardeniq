"""Issue #126: connecting a non-existent GitHub repository succeeded, the bogus
repo stayed in the repository list, and the PR poller later failed with a
"404 Not Found".

Root cause: add_repo() (app/api/routes/repos_prs.py) only parsed owner/name; it never
asked GitHub whether the repository exists. Its webhook registration failures are
deliberately swallowed ("don't fail the whole connect"), so a 404 from the webhook
call was swallowed too, and the repo was persisted and handed to the poller anyway.

Same e2e shape as tests/test_rbac_e2e.py: real auth_gateway middleware and a real
signed session cookie. Only the store, the GitHub/GitLab clients and the sync thread
are replaced, so no network or MongoDB is touched.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

import auth
import main
from api.routes import repos_prs

client = TestClient(main.app)

SESSION_COOKIE = auth.SESSION_COOKIE
FAKE_TOKEN = "ghp_FAKE_TOKEN_FOR_TESTS_ONLY"
PID = "6a7edbddc0ffee1234567890"


def _http_error(status, headers=None):
    req = httpx.Request("GET", "https://api.github.com/repos/o/n")
    resp = httpx.Response(status, request=req, headers=headers or {})
    return httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)


class FakeGitHub:
    """Stand-in for github.GitHub. `repo_error` is raised by get_repo(); an
    optional `hook_error` is raised by the webhook calls."""
    repo_error = None
    hook_error = None
    calls: list = []

    def __init__(self, token, api_base="https://api.github.com"):
        self.token = token

    def get_repo(self, owner, name):
        FakeGitHub.calls.append(("get_repo", owner, name))
        if FakeGitHub.repo_error:
            raise FakeGitHub.repo_error
        return {"full_name": f"{owner}/{name}", "private": False}

    def list_webhooks(self, owner, name):
        FakeGitHub.calls.append(("list_webhooks", owner, name))
        if FakeGitHub.hook_error:
            raise FakeGitHub.hook_error
        return []

    def register_pr_webhook(self, owner, name, url, secret):
        FakeGitHub.calls.append(("register_pr_webhook", owner, name))
        if FakeGitHub.hook_error:
            raise FakeGitHub.hook_error
        return {"id": 77}


class FakeThread:
    started: list = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        FakeThread.started.append((self.target, self.args))


@pytest.fixture
def env(monkeypatch):
    FakeGitHub.repo_error = None
    FakeGitHub.hook_error = None
    FakeGitHub.calls = []
    FakeThread.started = []
    persisted = []

    admin = {"id": "u1", "email": "u1@example.com", "role": "admin",
             "active": True, "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: admin if uid == "u1" else None)
    monkeypatch.setattr(main.store, "add_audit", lambda *a, **kw: True)

    def _add_repo(*args, **kwargs):
        persisted.append((args, kwargs))
        return "rid1"

    monkeypatch.setattr(main.store, "add_repo", _add_repo)
    monkeypatch.setattr(repos_prs, "project_github_token", lambda pid: FAKE_TOKEN)
    monkeypatch.setattr(repos_prs.github, "GitHub", FakeGitHub)
    monkeypatch.setattr(repos_prs.threading, "Thread", FakeThread)
    monkeypatch.setattr(repos_prs.crypto, "encrypt", lambda s: "enc:" + s)
    return persisted


def _connect(body, pid=PID):
    return client.post(f"/api/projects/{pid}/repos", json=body,
                       cookies={SESSION_COOKIE: auth.sign_session("u1", 0)})


def _gh(url="https://github.com/acme/ghost-repo", **extra):
    return {"url": url, "kind": "BE", "repo_type": "app", "git_provider": "github", **extra}


def _call_names():
    return [c[0] for c in FakeGitHub.calls]


# ------------------------------------------------------------ the reported bug
def test_nonexistent_repo_is_rejected_and_never_persisted_or_synced(env):
    FakeGitHub.repo_error = _http_error(404)

    r = _connect(_gh())

    assert r.status_code == 404
    assert "acme/ghost-repo" in r.json()["detail"]
    assert env == []                       # store.add_repo never called
    assert FakeThread.started == []        # no PR sync / monitoring started
    # Rejected before any webhook is created on a repo that doesn't exist.
    assert _call_names() == ["get_repo"]


def test_404_message_does_not_claim_more_than_github_told_us(env):
    # GitHub also answers 404 for a private repo the token can't see, so the message
    # must say "or the token cannot access it" rather than assert non-existence.
    FakeGitHub.repo_error = _http_error(404)
    detail = _connect(_gh()).json()["detail"]
    assert "token" in detail.lower() and "not found" in detail.lower()


def test_existence_check_runs_before_any_webhook_call_and_before_persistence(env):
    r = _connect(_gh())
    assert r.status_code == 200
    names = _call_names()
    assert names[0] == "get_repo"
    assert names.index("get_repo") < names.index("register_pr_webhook")


# ------------------------------------------------- valid repo keeps working
def test_valid_repo_connects_persists_and_starts_sync(env):
    r = _connect(_gh())

    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "acme/ghost-repo"
    assert body["watching"] is True and body["webhook_configured"] is True
    assert len(env) == 1
    args, kwargs = env[0]
    assert args[:3] == (PID, "acme", "ghost-repo")
    assert kwargs["repo_type"] == "app" and kwargs["git_provider"] == "github"
    assert kwargs["webhook_id"] == 77
    assert len(FakeThread.started) == 1 and FakeThread.started[0][1] == ("rid1",)


def test_owner_slash_name_form_is_checked_too(env):
    FakeGitHub.repo_error = _http_error(404)
    r = _connect({"repo_full_name": "acme/ghost-repo", "git_provider": "github"})
    assert r.status_code == 404 and env == []


# ----------------------------- webhook failure must NOT block a valid repo
@pytest.mark.parametrize("status", [403, 404, 422, 500])
def test_webhook_registration_failure_still_connects_a_valid_repo(env, status):
    FakeGitHub.hook_error = _http_error(status)

    r = _connect(_gh())

    assert r.status_code == 200
    assert r.json()["webhook_configured"] is False
    assert len(env) == 1
    assert env[0][1]["webhook_id"] is None
    assert len(FakeThread.started) == 1
    assert "get_repo" in _call_names()


# ------------------------- different failures are not all "repository not found"
def test_github_auth_failure_is_not_reported_as_repo_not_found(env):
    FakeGitHub.repo_error = _http_error(401)

    r = _connect(_gh())

    # Must not be 401 either: the UI treats any 401 as "session expired" and signs
    # the user out. The project's existing mapping turns a provider 401 into a 400.
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "authentication failed" in detail
    assert "not found" not in detail
    assert env == [] and FakeThread.started == []


def test_forbidden_is_reported_as_forbidden_not_as_missing(env):
    FakeGitHub.repo_error = _http_error(403)

    r = _connect(_gh())

    assert r.status_code == 403
    assert "not found" not in r.json()["detail"].lower()
    assert env == [] and FakeThread.started == []


@pytest.mark.parametrize("err", [
    _http_error(429),
    _http_error(403, {"x-ratelimit-remaining": "0"}),
    _http_error(403, {"retry-after": "30"}),
])
def test_rate_limiting_is_reported_as_rate_limiting(env, err):
    FakeGitHub.repo_error = err

    r = _connect(_gh())

    assert r.status_code == 429
    assert "rate" in r.json()["detail"].lower()
    assert env == [] and FakeThread.started == []


@pytest.mark.parametrize("err", [
    httpx.ConnectError("boom"),
    httpx.ReadTimeout("slow"),
    _http_error(500),
    _http_error(502),
])
def test_network_and_server_failures_never_persist_an_unverified_repo(env, err):
    FakeGitHub.repo_error = err

    r = _connect(_gh())

    assert r.status_code == 502
    assert "not found" not in r.json()["detail"].lower()
    assert env == [] and FakeThread.started == []


def test_token_never_appears_in_error_responses_or_logs(env, caplog):
    FakeGitHub.repo_error = _http_error(404)
    with caplog.at_level("DEBUG"):
        r = _connect(_gh())
    assert FAKE_TOKEN not in r.text
    assert FAKE_TOKEN not in caplog.text


# ---------------------------------------------- unchanged paths stay unchanged
def test_test_repositories_are_not_checked_against_github(env):
    # repo_type="test" never required a PAT or a GitHub call to connect. #126 is about
    # watched (app) repos, so that path is deliberately left as it was.
    FakeGitHub.repo_error = _http_error(404)

    r = _connect(_gh(repo_type="test", kind="test"))

    assert r.status_code == 200
    assert FakeGitHub.calls == []
    assert len(env) == 1 and env[0][1]["repo_type"] == "test"
    assert FakeThread.started == []        # test repos were never synced


def test_gitlab_connect_is_unchanged(env, monkeypatch):
    class FakeGitLab:
        def __init__(self, token):
            pass

        def register_mr_webhook(self, full_name, url, secret):
            return {"id": 5}

    monkeypatch.setattr(repos_prs, "project_gitlab_token", lambda pid: "glpat-fake")
    monkeypatch.setattr(repos_prs.gitlab_mod, "GitLab", FakeGitLab)

    r = _connect({"repo_full_name": "group/proj", "git_provider": "gitlab",
                  "repo_type": "app", "kind": "BE"})

    assert r.status_code == 200
    assert FakeGitHub.calls == []
    assert len(env) == 1 and env[0][1]["git_provider"] == "gitlab"


def test_unparseable_url_is_still_a_400_and_makes_no_github_call(env):
    r = _connect({"url": "not a repo", "git_provider": "github"})
    assert r.status_code == 400
    assert FakeGitHub.calls == [] and env == []


def test_missing_pat_still_reports_the_existing_message(env, monkeypatch):
    monkeypatch.setattr(repos_prs, "project_github_token", lambda pid: "")
    r = _connect(_gh())
    assert r.status_code == 400
    assert "PAT not configured" in r.json()["detail"]
    assert FakeGitHub.calls == [] and env == []
