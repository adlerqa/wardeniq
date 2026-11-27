"""Unit and integration tests for AWS S3 document storage and related API endpoints."""
import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import main
import auth as auth_mod
from s3_storage import S3StorageManager, s3_storage

# Prevent audit logging in tests from trying to reach unmocked MongoDB
main.store.add_audit = lambda *a, **kw: True

client = TestClient(main.app)


def _admin_cookie():
    user = {
        "id": "admin1",
        "email": "admin@example.com",
        "role": "admin",
        "active": True,
        "session_version": 0,
        "all_projects": True,
    }
    main.store.get_user = lambda uid: user
    return {auth_mod.SESSION_COOKIE: auth_mod.sign_session("admin1", 0)}


# ===================================================================== S3StorageManager Unit Tests
def test_s3_storage_manager_config_resolution(monkeypatch):
    monkeypatch.setattr(
        main.store,
        "get_settings",
        lambda: {
            "s3_bucket": "settings-bucket",
            "s3_region": "us-west-2",
            "s3_access_key_id": "AKIASETTINGS",
            "s3_secret_access_key_enc": "",
            "s3_enabled": True,
            "s3_prefix": "my-docs",
        },
    )

    mgr = S3StorageManager()
    cfg = mgr._get_config()
    assert cfg["bucket"] == "settings-bucket"
    assert cfg["region"] == "us-west-2"
    assert cfg["access_key_id"] == "AKIASETTINGS"
    assert cfg["enabled"] is True
    assert cfg["prefix"] == "my-docs"
    assert mgr.is_configured() is True


def test_s3_storage_manager_test_connection_success(monkeypatch):
    mgr = S3StorageManager(bucket="test-bucket", region="us-east-1")
    mock_boto_client = MagicMock()
    mock_boto_client.head_bucket.return_value = {}

    with patch.object(mgr, "_get_client", return_value=mock_boto_client):
        res = mgr.test_connection()
        assert res["ok"] is True
        assert "Successfully connected" in res["message"]
        mock_boto_client.head_bucket.assert_called_once_with(Bucket="test-bucket")


def test_s3_storage_manager_test_connection_failure(monkeypatch):
    mgr = S3StorageManager(bucket="test-bucket", region="us-east-1")
    mock_boto_client = MagicMock()
    mock_boto_client.head_bucket.side_effect = Exception("Access Denied")

    with patch.object(mgr, "_get_client", return_value=mock_boto_client):
        res = mgr.test_connection()
        assert res["ok"] is False
        assert "Access Denied" in res["error"]


def test_s3_storage_manager_upload_and_download(monkeypatch):
    mgr = S3StorageManager(
        bucket="my-bucket",
        region="us-east-1",
        access_key_id="KEY",
        secret_access_key="SECRET",
        enabled=True,
    )

    mock_s3 = MagicMock()
    mock_s3.put_object.return_value = {}
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"PDF file content")}
    mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/my-bucket/presigned-url"

    with patch.object(mgr, "_get_client", return_value=mock_s3):
        # Test Upload
        meta = mgr.upload_document(
            filename="PRD.pdf",
            content=b"PDF file content",
            content_type="application/pdf",
            project_id="p1",
            feature_id="f1",
        )
        assert meta["s3_bucket"] == "my-bucket"
        assert meta["filename"] == "PRD.pdf"
        assert meta["size_bytes"] == len(b"PDF file content")
        assert meta["s3_key"].startswith("documents/p1/")
        assert meta["s3_key"].endswith("_PRD.pdf")
        mock_s3.put_object.assert_called_once()

        # Test Download
        data = mgr.download_document(meta["s3_key"])
        assert data == b"PDF file content"

        # Test Presigned URL
        url = mgr.generate_presigned_url(meta["s3_key"])
        assert url == "https://s3.amazonaws.com/my-bucket/presigned-url"

        # Test Delete
        mgr.delete_document(meta["s3_key"])
        mock_s3.delete_object.assert_called_once_with(Bucket="my-bucket", Key=meta["s3_key"])


# ===================================================================== API Endpoint Tests
def test_get_and_put_settings_s3(monkeypatch):
    saved_settings = {}

    def mock_get_settings():
        return saved_settings

    def mock_save_settings(doc):
        saved_settings.update(doc)

    monkeypatch.setattr(main.store, "get_settings", mock_get_settings)
    monkeypatch.setattr(main.store, "save_settings", mock_save_settings)

    cookie = _admin_cookie()

    # GET settings
    r = client.get("/api/settings", cookies=cookie)
    assert r.status_code == 200
    data = r.json()
    assert "s3_enabled" in data
    assert "s3_bucket" in data
    assert "s3_configured" in data

    # PUT settings to save S3 configuration
    s3_payload = {
        "s3_enabled": True,
        "s3_bucket": "production-docs-bucket",
        "s3_region": "us-east-1",
        "s3_access_key_id": "AKIA123456",
        "s3_secret_access_key": "secret123456",
        "s3_prefix": "app-docs",
    }
    r_put = client.put("/api/settings", json=s3_payload, cookies=cookie)
    assert r_put.status_code == 200

    # Verify settings persisted
    assert saved_settings["s3_enabled"] is True
    assert saved_settings["s3_bucket"] == "production-docs-bucket"
    assert saved_settings["s3_region"] == "us-east-1"
    assert saved_settings["s3_access_key_id"] == "AKIA123456"
    assert saved_settings["s3_secret_access_key_enc"] != ""
    assert saved_settings["s3_prefix"] == "app-docs"


def test_post_s3_test_endpoint(monkeypatch):
    cookie = _admin_cookie()

    def mock_test_connection(bucket=None, region=None, access_key_id=None, secret_access_key=None, **_kw):
        if bucket == "valid-bucket":
            return {"ok": True, "message": "Successfully connected", "bucket": bucket, "region": region}
        return {"ok": False, "error": "Bucket does not exist"}

    monkeypatch.setattr(s3_storage, "test_connection", mock_test_connection)

    # Success case
    r = client.post(
        "/api/settings/s3/test",
        json={"bucket": "valid-bucket", "region": "us-east-1"},
        cookies=cookie,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Failure case
    r_err = client.post(
        "/api/settings/s3/test",
        json={"bucket": "invalid-bucket", "region": "us-east-1"},
        cookies=cookie,
    )
    assert r_err.status_code == 400
    assert "Bucket does not exist" in r_err.json()["detail"]


def test_document_management_endpoints(monkeypatch):
    cookie = _admin_cookie()
    mock_db_docs = {}

    def mock_save_doc(doc):
        doc_id = f"doc_{len(mock_db_docs) + 1}"
        doc_copy = dict(doc)
        doc_copy["id"] = doc_id
        mock_db_docs[doc_id] = doc_copy
        return doc_id

    def mock_get_doc(doc_id):
        return mock_db_docs.get(doc_id)

    def mock_list_docs(project_id=None, feature_id=None, limit=100):
        out = []
        for d in mock_db_docs.values():
            if project_id and d.get("project_id") != project_id:
                continue
            if feature_id and d.get("feature_id") != feature_id:
                continue
            out.append(d)
        return out

    def mock_delete_doc(doc_id):
        return mock_db_docs.pop(doc_id, None) is not None

    monkeypatch.setattr(main.store, "save_stored_document", mock_save_doc)
    monkeypatch.setattr(main.store, "get_stored_document", mock_get_doc)
    monkeypatch.setattr(main.store, "list_stored_documents", mock_list_docs)
    monkeypatch.setattr(main.store, "delete_stored_document", mock_delete_doc)

    monkeypatch.setattr(s3_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        s3_storage,
        "upload_document",
        lambda filename, content, content_type=None, project_id=None, feature_id=None: {
            "s3_key": f"documents/{project_id or 'global'}/123_{filename}",
            "s3_bucket": "test-bucket",
            "s3_region": "us-east-1",
            "filename": filename,
            "content_type": content_type or "application/octet-stream",
            "size_bytes": len(content),
            "created_at": time.time(),
        },
    )
    monkeypatch.setattr(
        s3_storage,
        "generate_presigned_url",
        lambda s3_key, bucket=None, expires_in=3600: f"https://s3.amazonaws.com/{s3_key}",
    )
    monkeypatch.setattr(
        s3_storage,
        "download_document",
        lambda s3_key, bucket=None: b"Hello S3 Document Content",
    )
    monkeypatch.setattr(s3_storage, "delete_document", lambda s3_key, bucket=None: True)

    # 1. Upload document
    files = {"file": ("requirements.pdf", b"Hello S3 Document Content", "application/pdf")}
    r_up = client.post("/api/documents/upload", files=files, data={"project_id": "proj1"}, cookies=cookie)
    assert r_up.status_code == 200
    doc_res = r_up.json()
    assert doc_res["filename"] == "requirements.pdf"
    assert doc_res["s3_bucket"] == "test-bucket"
    assert "presigned_url" in doc_res
    doc_id = doc_res["id"]

    # 2. List documents
    r_list = client.get("/api/documents?project_id=proj1", cookies=cookie)
    assert r_list.status_code == 200
    list_data = r_list.json()
    assert len(list_data["documents"]) == 1
    assert list_data["s3_enabled"] is True

    # 3. Get single document info
    r_get = client.get(f"/api/documents/{doc_id}", cookies=cookie)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == doc_id

    # 4. Download document
    r_dl = client.get(f"/api/documents/{doc_id}/download", cookies=cookie)
    assert r_dl.status_code == 200
    assert r_dl.content == b"Hello S3 Document Content"
    assert "attachment" in r_dl.headers.get("Content-Disposition", "")

    # 5. Delete document
    r_del = client.delete(f"/api/documents/{doc_id}", cookies=cookie)
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    # Verify deleted
    r_get_del = client.get(f"/api/documents/{doc_id}", cookies=cookie)
    assert r_get_del.status_code == 404
