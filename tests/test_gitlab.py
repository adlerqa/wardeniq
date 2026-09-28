"""GitLab host configurability (issue #14): gitlab.com must keep working with zero
config, and a self-hosted instance must work when GITLAB_BASE_URL is set.

GITLAB_BASE_URL is read once, at import time, into module-level constants in
`gitlab` and `automation` (mirroring the existing GITHUB_API pattern in
core/config.py). To exercise both the default and a configured host in the same
process, these tests reload core.config + the modules under test around a
monkeypatched env var, then restore the original (unconfigured) state so other
test files importing `gitlab`/`automation` see the real default.
"""
import importlib
import pathlib
import re

import pytest

_APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"

# A literal gitlab.com URL/host outside of core/config.py's own default value and
# a code comment. Catches a hardcoded host creeping back into any of the three
# files #14 fixed (app/gitlab.py, app/automation.py,
# app/workers/repo_scan_worker.py) or into any other file under app/.
_HARDCODED_GITLAB_HOST = re.compile(r"""(['"])(?:https?://)?gitlab\.com""")


def _non_comment_lines(text):
    return [ln for ln in text.splitlines() if not ln.strip().startswith("#")]


class TestNoHardcodedGitlabHostRemains:
    """Regression guard: every GitLab host reference must come from GITLAB_BASE_URL.

    Only scans code lines (comment lines are skipped) so a prose mention of
    "gitlab.com" explaining the default doesn't false-positive this check.
    """

    def test_gitlab_py_has_no_literal_host(self):
        code = "\n".join(_non_comment_lines(
            (_APP_ROOT / "gitlab.py").read_text(encoding="utf-8")))
        # The one legitimate literal is the `or "gitlab.com"` parse fallback,
        # which only fires if GITLAB_BASE_URL somehow has no netloc at all.
        matches = list(_HARDCODED_GITLAB_HOST.finditer(code))
        assert all('or "gitlab.com"' in code[max(0, m.start() - 10):m.end() + 5]
                   for m in matches), matches

    def test_automation_py_has_no_literal_host(self):
        code = "\n".join(_non_comment_lines(
            (_APP_ROOT / "automation.py").read_text(encoding="utf-8")))
        assert not _HARDCODED_GITLAB_HOST.search(code)

    def test_repo_scan_worker_has_no_literal_host(self):
        code = "\n".join(_non_comment_lines(
            (_APP_ROOT / "workers" / "repo_scan_worker.py").read_text(encoding="utf-8")))
        assert not _HARDCODED_GITLAB_HOST.search(code)


@pytest.fixture
def reload_with_gitlab_base_url(monkeypatch):
    """Set GITLAB_BASE_URL, reload core.config + gitlab + automation, then undo."""
    import core.config as core_config
    import gitlab as gitlab_mod
    import automation as automation_mod

    def _set(value=None):
        if value is None:
            monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
        else:
            monkeypatch.setenv("GITLAB_BASE_URL", value)
        importlib.reload(core_config)
        importlib.reload(gitlab_mod)
        importlib.reload(automation_mod)
        return gitlab_mod, automation_mod

    try:
        yield _set
    finally:
        # Restore the real (unconfigured) default for every other test module.
        monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
        importlib.reload(core_config)
        importlib.reload(gitlab_mod)
        importlib.reload(automation_mod)


class TestDefaultHostUnchanged:
    """gitlab.com must keep working with no GITLAB_BASE_URL set at all."""

    def test_default_api_base_is_gitlab_com(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url(None)
        assert gitlab_mod.GitLab(token="x").api == "https://gitlab.com/api/v4"

    def test_default_parses_https_url(self, reload_with_gitlab_base_url):
        # NOTE: _URL_RE's non-greedy capture group stops at the first "/", so a
        # namespace/project URL currently resolves to just the namespace segment.
        # That is a PRE-EXISTING behavior of this regex (reproduced identically for
        # plain gitlab.com before #14's changes) and is unrelated to host
        # configurability — not something this issue asks us to fix. Asserted here
        # only so this test documents the real current output, not a guessed one.
        gitlab_mod, _ = reload_with_gitlab_base_url(None)
        assert gitlab_mod.parse_repo_url("https://gitlab.com/my-group/my-project") == "my-group"

    def test_default_parses_ssh_url(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url(None)
        assert gitlab_mod.parse_repo_url("git@gitlab.com:my-group/my-project.git") == "my-group"

    def test_default_parses_bare_namespace_path(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url(None)
        assert gitlab_mod.parse_repo_url("my-group/my-project") == "my-group/my-project"


class TestSelfHostedViaEnv:
    """GITLAB_BASE_URL=https://gitlab.example.com must be honoured end to end."""

    def test_api_base_uses_configured_host(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url("https://gitlab.example.com")
        assert gitlab_mod.GitLab(token="x").api == "https://gitlab.example.com/api/v4"

    def test_parses_self_hosted_https_url(self, reload_with_gitlab_base_url):
        # See the note on test_default_parses_https_url: the capture stops at the
        # first "/" regardless of host — pre-existing, unrelated to #14. What this
        # test actually verifies is that the CONFIGURED host is what's matched at
        # all (an unconfigured gitlab.example.com URL wouldn't match _URL_RE
        # before this issue's change).
        gitlab_mod, _ = reload_with_gitlab_base_url("https://gitlab.example.com")
        assert gitlab_mod.parse_repo_url(
            "https://gitlab.example.com/my-group/my-project") == "my-group"

    def test_parses_self_hosted_ssh_url(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url("https://gitlab.example.com")
        assert gitlab_mod.parse_repo_url(
            "git@gitlab.example.com:my-group/my-project.git") == "my-group"

    def test_configured_host_survives_a_trailing_slash_in_env(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url("https://gitlab.example.com/")
        assert gitlab_mod.GitLab(token="x").api == "https://gitlab.example.com/api/v4"

    def test_explicit_api_base_argument_still_overrides_default(self, reload_with_gitlab_base_url):
        gitlab_mod, _ = reload_with_gitlab_base_url("https://gitlab.example.com")
        client = gitlab_mod.GitLab(token="x", api_base="https://another-host.example/api/v4")
        assert client.api == "https://another-host.example/api/v4"


class TestBlobAndCommitUrls:
    """build_blob_url / build_commit_url must use the configured GitLab host."""

    def test_default_blob_url_uses_gitlab_com(self, reload_with_gitlab_base_url):
        _, automation_mod = reload_with_gitlab_base_url(None)
        url = automation_mod.build_blob_url("gitlab", "my-group/my-project", "main",
                                            "app/main.py", line=10)
        assert url == "https://gitlab.com/my-group/my-project/-/blob/main/app/main.py#L10"

    def test_default_commit_url_uses_gitlab_com(self, reload_with_gitlab_base_url):
        _, automation_mod = reload_with_gitlab_base_url(None)
        url = automation_mod.build_commit_url("gitlab", "my-group/my-project", "abc123")
        assert url == "https://gitlab.com/my-group/my-project/-/commit/abc123"

    def test_self_hosted_blob_url_uses_configured_host(self, reload_with_gitlab_base_url):
        _, automation_mod = reload_with_gitlab_base_url("https://gitlab.example.com")
        url = automation_mod.build_blob_url("gitlab", "my-group/my-project", "main",
                                            "app/main.py", line=10)
        assert url == "https://gitlab.example.com/my-group/my-project/-/blob/main/app/main.py#L10"

    def test_self_hosted_commit_url_uses_configured_host(self, reload_with_gitlab_base_url):
        _, automation_mod = reload_with_gitlab_base_url("https://gitlab.example.com")
        url = automation_mod.build_commit_url("gitlab", "my-group/my-project", "abc123")
        assert url == "https://gitlab.example.com/my-group/my-project/-/commit/abc123"

    def test_github_urls_are_unaffected_by_gitlab_config(self, reload_with_gitlab_base_url):
        _, automation_mod = reload_with_gitlab_base_url("https://gitlab.example.com")
        url = automation_mod.build_blob_url("github", "my-org/my-repo", "main", "app/main.py")
        assert url == "https://github.com/my-org/my-repo/blob/main/app/main.py"
