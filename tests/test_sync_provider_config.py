"""Expose the configured GitLab host for repository-provider detection in the UI."""
import pytest

from api.routes import system


@pytest.mark.parametrize("base_url,expected_host", [
    ("https://gitlab.com", "gitlab.com"),
    ("https://code.example.com", "code.example.com"),
    ("https://code.example.com:8443/gitlab", "code.example.com"),
])
def test_sync_status_exposes_configured_gitlab_host(monkeypatch, base_url, expected_host):
    monkeypatch.setattr(system, "GITLAB_BASE_URL", base_url)
    monkeypatch.setattr(system, "current_poll_interval", lambda: 1800)

    assert system.sync_status()["gitlab_host"] == expected_host
