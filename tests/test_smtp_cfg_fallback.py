"""_smtp_cfg() when the stored SMTP password is missing or unreadable.

scripts/reset-smtp-secret.sh clears only ``smtp_pass_enc`` and leaves host/user, so a
configured user with no password must be treated as unusable (fall back to .env, else
None so the bootstrap admin's sign-in code is logged) rather than returned as a config
whose every send fails with an auth error.
"""
import pytest

from core import deps


class _Store:
    def __init__(self, settings):
        self._settings = settings

    def get_settings(self):
        return self._settings


@pytest.fixture
def cfg(monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_PORT", "SMTP_FROM",
              "SMTP_SSL", "SMTP_TLS"):
        monkeypatch.delenv(k, raising=False)

    def _cfg(settings, env=None):
        monkeypatch.setattr(deps, "store", _Store(settings))
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        return deps._smtp_cfg()

    return _cfg


_GMAIL = {"smtp_host": "smtp.gmail.com", "smtp_user": "ops@example.com", "smtp_port": 587}


def test_user_without_password_is_unusable_and_logs_the_code(cfg):
    # The state reset-smtp-secret.sh leaves behind.
    assert cfg(dict(_GMAIL)) is None


def test_user_without_password_falls_back_to_env_smtp(cfg):
    out = cfg(dict(_GMAIL), env={"SMTP_HOST": "smtp.fallback.test", "SMTP_USER": "u", "SMTP_PASS": "p"})
    assert out["host"] == "smtp.fallback.test"
    assert out["password"] == "p"


def test_undecryptable_password_still_falls_back(cfg, monkeypatch):
    monkeypatch.setattr(deps.crypto, "decrypt", lambda _v: "")
    assert cfg({**_GMAIL, "smtp_pass_enc": "garbage"}) is None


def test_usable_db_config_is_returned(cfg, monkeypatch):
    monkeypatch.setattr(deps.crypto, "decrypt", lambda _v: "app-password")
    out = cfg({**_GMAIL, "smtp_pass_enc": "enc"})
    assert out["host"] == "smtp.gmail.com"
    assert out["user"] == "ops@example.com"
    assert out["password"] == "app-password"


def test_host_only_relay_without_credentials_is_still_returned(cfg):
    # No user -> send_otp() skips login(), so an unauthenticated relay is a working config.
    out = cfg({"smtp_host": "relay.internal", "smtp_port": 25})
    assert out["host"] == "relay.internal"
    assert out["password"] == ""
