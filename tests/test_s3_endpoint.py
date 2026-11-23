"""S3-compatible endpoint support (issue #283): MinIO / LocalStack / Garage / R2."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main
import auth as auth_mod
import crypto
from s3_storage import S3StorageManager, s3_storage

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)

_S3_ENV = ("AWS_S3_ENDPOINT_URL", "AWS_S3_FORCE_PATH_STYLE", "AWS_S3_BUCKET")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _S3_ENV:
        monkeypatch.delenv(k, raising=False)


def _admin_cookie():
    user = {"id": "admin1", "email": "admin@example.com", "role": "admin", "active": True,
            "session_version": 0, "all_projects": True}
    main.store.get_user = lambda uid: user
    return {auth_mod.SESSION_COOKIE: auth_mod.sign_session("admin1", 0)}


def _settings(monkeypatch, s):
    monkeypatch.setattr(main.store, "get_settings", lambda: dict(s))


# ------------------------------------------------------------- config resolution
def test_no_endpoint_by_default(monkeypatch):
    _settings(monkeypatch, {"s3_bucket": "b"})
    cfg = S3StorageManager()._get_config()
    assert cfg["endpoint_url"] == ""
    assert cfg["force_path_style"] is False


def test_endpoint_from_settings_defaults_path_style_on(monkeypatch):
    _settings(monkeypatch, {"s3_bucket": "b", "s3_endpoint_url": "http://minio:9000"})
    cfg = S3StorageManager()._get_config()
    assert cfg["endpoint_url"] == "http://minio:9000"
    assert cfg["force_path_style"] is True


def test_endpoint_from_env_and_explicit_path_style_off(monkeypatch):
    _settings(monkeypatch, {})
    monkeypatch.setenv("AWS_S3_ENDPOINT_URL", "https://acct.r2.cloudflarestorage.com")
    monkeypatch.setenv("AWS_S3_FORCE_PATH_STYLE", "false")
    cfg = S3StorageManager()._get_config()
    assert cfg["endpoint_url"] == "https://acct.r2.cloudflarestorage.com"
    assert cfg["force_path_style"] is False


def test_settings_endpoint_beats_env(monkeypatch):
    _settings(monkeypatch, {"s3_endpoint_url": "http://from-settings:9000"})
    monkeypatch.setenv("AWS_S3_ENDPOINT_URL", "http://from-env:9000")
    assert S3StorageManager()._get_config()["endpoint_url"] == "http://from-settings:9000"


# ------------------------------------------------------------- boto3 client args
def _client_kwargs(mgr):
    with patch("boto3.session.Session") as Sess:
        mgr._get_client()
        return Sess.return_value.client.call_args


def test_client_without_endpoint_is_plain_aws(monkeypatch):
    _settings(monkeypatch, {})
    call = _client_kwargs(S3StorageManager(bucket="b", region="us-east-1"))
    assert call.args == ("s3",)
    assert call.kwargs == {}


def test_client_with_endpoint_uses_path_style(monkeypatch):
    _settings(monkeypatch, {})
    call = _client_kwargs(S3StorageManager(bucket="b", endpoint_url="http://localhost:9000"))
    assert call.kwargs["endpoint_url"] == "http://localhost:9000"
    assert call.kwargs["config"].s3 == {"addressing_style": "path"}


def test_test_connection_overrides_endpoint(monkeypatch):
    _settings(monkeypatch, {})
    mgr = S3StorageManager(bucket="b")
    fake = MagicMock()
    with patch.object(mgr, "_get_client", return_value=fake) as gc:
        res = mgr.test_connection(endpoint_url="http://localhost:9000")
    assert res["ok"] is True
    cfg = gc.call_args.args[0]
    assert cfg["endpoint_url"] == "http://localhost:9000"
    assert cfg["force_path_style"] is True
    assert "http://localhost:9000" in res["message"]


# ------------------------------------------------------------- API
def test_s3_test_api_passes_endpoint(monkeypatch):
    cookie = _admin_cookie()
    _settings(monkeypatch, {})
    seen = {}

    def fake_test(**kw):
        seen.update(kw)
        return {"ok": True, "message": "ok"}

    monkeypatch.setattr(s3_storage, "test_connection", fake_test)
    r = client.post("/api/settings/s3/test", cookies=cookie,
                    json={"bucket": "b", "endpoint_url": "http://localhost:9000/"})
    assert r.status_code == 200
    assert seen["endpoint_url"] == "http://localhost:9000"


def test_s3_test_api_rejects_bad_endpoint(monkeypatch):
    cookie = _admin_cookie()
    _settings(monkeypatch, {})
    r = client.post("/api/settings/s3/test", cookies=cookie,
                    json={"bucket": "b", "endpoint_url": "ftp://nope"})
    assert r.status_code == 400


def test_s3_test_api_does_not_send_stored_secret_to_new_endpoint(monkeypatch):
    cookie = _admin_cookie()
    _settings(monkeypatch, {"s3_endpoint_url": "",
                            "s3_secret_access_key_enc": crypto.encrypt("TOPSECRET")})
    seen = {}
    monkeypatch.setattr(s3_storage, "test_connection",
                        lambda **kw: seen.update(kw) or {"ok": True})
    client.post("/api/settings/s3/test", cookies=cookie,
                json={"bucket": "b", "endpoint_url": "http://attacker:9000"})
    assert seen["secret_access_key"] != "TOPSECRET"


def test_put_settings_saves_endpoint_and_clears_secret_on_change(monkeypatch):
    cookie = _admin_cookie()
    _settings(monkeypatch, {"s3_secret_access_key_enc": crypto.encrypt("OLD")})
    saved = {}
    monkeypatch.setattr(main.store, "save_settings", lambda upd: saved.update(upd))
    r = client.put("/api/settings", cookies=cookie, json={
        "s3_endpoint_url": "http://localhost:9000", "s3_force_path_style": True})
    assert r.status_code == 200, r.text
    assert saved["s3_endpoint_url"] == "http://localhost:9000"
    assert saved["s3_force_path_style"] is True
    assert saved["s3_secret_access_key_enc"] == ""


def test_storage_status_endpoint(monkeypatch):
    cookie = _admin_cookie()
    monkeypatch.setattr(s3_storage, "is_configured", lambda: False)
    r = client.get("/api/documents/storage-status", cookies=cookie)
    assert r.status_code == 200
    assert r.json() == {"configured": False}
