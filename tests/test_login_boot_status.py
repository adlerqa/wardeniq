"""Public startup diagnostics must never expose driver exceptions or user data."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main
from api.routes import auth as routes
from core import bootstrap
from store.users_auth import UsersAuthMixin


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(bootstrap, "BOOT", {
        "stage": "error", "ready": False,
        "detail": "mongodb://private-user:secret@internal-host:27017 raw driver error",
    })
    monkeypatch.setattr(routes.store, "has_users", lambda: False)
    # Sign-in throttling bookkeeping would otherwise reach for a real database.
    monkeypatch.setattr(routes.store, "throttle_locked_for", lambda key: 0)
    monkeypatch.setattr(routes.store, "throttle_record_failure", lambda *a, **k: 1)
    monkeypatch.setattr(routes.store, "throttle_clear", lambda key: None)
    return TestClient(main.app)


@pytest.mark.parametrize("stage", ["starting", "connecting", "indexing", "error", "unexpected"])
def test_public_status_does_not_expose_raw_detail(client, stage):
    bootstrap.BOOT["stage"] = stage
    response = client.get("/api/auth/boot-status")
    assert response.status_code == 200  # no session needed
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["stage"] == stage
    assert body["ready"] is False
    assert body["detail"]
    assert body["users_empty"] is True
    assert "scripts/reset-admin-password.sh" in body["recovery"]
    assert "No user accounts exist" in body["recovery"]
    for secret in ("private-user", "secret", "internal-host", "raw driver"):
        assert secret not in response.text


@pytest.mark.parametrize("error,message", [
    ("no such command: createSearchIndexes", bootstrap._SEARCH_REQUIRED_MSG),
    ("maximum number of FTS indexes", bootstrap._SEARCH_INDEX_LIMIT_MSG),
])
def test_real_failed_boot_is_visible_before_login(client, monkeypatch, error, message):
    fake = SimpleNamespace(ping=Mock(), fail_orphaned_jobs=Mock(),
                           ensure_indexes=Mock(side_effect=RuntimeError(error)),
                           create_user=Mock())
    monkeypatch.setattr(bootstrap, "store", fake)
    monkeypatch.setattr(bootstrap, "AUTO_SETUP", True)
    for name in ("_ensure_app_secret", "_check_app_secret", "_check_production_posture"):
        monkeypatch.setattr(bootstrap, name, lambda: None)
    bootstrap.bootstrap()
    body = client.get("/api/auth/boot-status").json()
    assert body["detail"] == message
    assert body["users_empty"] is True
    fake.create_user.assert_not_called()


def test_weak_secret_failure_has_safe_actionable_copy(client, monkeypatch):
    monkeypatch.setattr(bootstrap.auth, "secret_is_weak", lambda: True)
    monkeypatch.setattr(bootstrap, "ALLOW_WEAK_SECRET", False)
    with pytest.raises(RuntimeError):
        bootstrap._check_app_secret()
    assert "Set a strong APP_SECRET" in client.get("/api/auth/boot-status").json()["detail"]


def test_production_failure_preserves_configuration_guidance(client, monkeypatch):
    from core import deps
    monkeypatch.setattr(bootstrap, "IS_PRODUCTION", True)
    monkeypatch.setattr(bootstrap, "ALLOW_WEAK_SECRET", False)
    monkeypatch.setattr(bootstrap.auth, "COOKIE_SECURE", False)
    monkeypatch.setattr(deps, "_smtp_cfg", lambda: None)
    with pytest.raises(RuntimeError):
        bootstrap._check_production_posture()
    detail = client.get("/api/auth/boot-status").json()["detail"]
    assert "COOKIE_SECURE=false" in detail
    assert "SMTP not configured" in detail


def test_unreachable_database_is_not_reported_as_empty(client, monkeypatch):
    monkeypatch.setattr(routes.store, "has_users", Mock(side_effect=RuntimeError("private-host password")))
    response = client.get("/api/auth/boot-status")
    assert response.status_code == 200
    assert response.json()["users_empty"] is None
    assert "Unable to check user accounts" in response.json()["recovery"]
    assert "private-host" not in response.text
    assert "reset-admin-password.sh" not in response.text


def test_existing_users_do_not_get_empty_account_guidance(client, monkeypatch):
    monkeypatch.setattr(routes.store, "has_users", lambda: True)
    body = client.get("/api/auth/boot-status").json()
    assert body["users_empty"] is False
    assert body["recovery"] == ""


def test_healthy_boot_has_no_warning_or_database_query(client, monkeypatch):
    bootstrap.BOOT.update(stage="ready", ready=True)
    probe = Mock(side_effect=AssertionError("healthy boot should not query users"))
    monkeypatch.setattr(routes.store, "has_users", probe)
    assert client.get("/api/auth/boot-status").json() == {
        "stage": "ready", "ready": True, "detail": "", "users_empty": None, "recovery": "",
    }
    probe.assert_not_called()


@pytest.mark.parametrize("ready", [False, True])
def test_empty_users_password_failure_is_actionable(client, monkeypatch, ready):
    bootstrap.BOOT.update(ready=ready)
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: None)
    monkeypatch.setattr(routes.store, "get_user_by_email", lambda email: None)
    response = client.post("/api/auth/login-password", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 503
    assert "No user accounts exist" in response.json()["detail"]
    assert "scripts/reset-admin-password.sh" in response.json()["detail"]
    assert "Invalid username or password" not in response.text
    assert "private-user" not in response.text


def test_wrong_credentials_remain_generic_when_users_exist(client, monkeypatch):
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: None)
    monkeypatch.setattr(routes.store, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(routes.store, "has_users", lambda: True)
    response = client.post("/api/auth/login-password", json={"username": "unknown", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_has_users_includes_inactive_accounts_without_loading_user_data():
    fake = SimpleNamespace(users=Mock())
    fake.users.find_one.return_value = {"_id": "inactive-user"}
    assert UsersAuthMixin.has_users(fake) is True
    fake.users.find_one.assert_called_once_with({}, {"_id": 1})
    fake.users.find_one.return_value = None
    assert UsersAuthMixin.has_users(fake) is False
