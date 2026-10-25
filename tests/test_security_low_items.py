"""Smaller hardening items: Ollama model listing access/keys, SSRF ranges, download
filenames, storage error messages, defect-link schemes, logout revocation and
self-service password change for viewers."""
from unittest.mock import MagicMock

import auth
import crypto
import main
import pytest
from fastapi.testclient import TestClient

import weblinks
from api.routes import settings as settings_routes

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)


def _cookie(monkeypatch, role="admin", sv=0, **extra):
    user = {"id": "u1", "email": "u1@example.com", "role": role, "active": True,
            "session_version": sv, "all_projects": True, **extra}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}, user


# ------------------------------------------------------------ ollama models
def test_ollama_models_requires_editor(monkeypatch):
    cookie, _ = _cookie(monkeypatch, "viewer")
    assert client.get("/api/ollama/models", cookies=cookie).status_code == 403


@pytest.mark.parametrize("provider,expect_auth", [("openai", False), ("ollama", True)])
def test_ollama_models_only_sends_ollama_token(monkeypatch, provider, expect_auth):
    cookie, _ = _cookie(monkeypatch, "editor")
    monkeypatch.setattr(main.store, "get_settings", lambda: {
        "llm_provider": provider, "llm_api_key_enc": crypto.encrypt("secret-key")})
    monkeypatch.setattr(settings_routes, "PROVIDER_LOCK", "")
    seen = {}

    def fake_get(url, timeout=None, headers=None):
        seen["headers"] = headers
        r = MagicMock()
        r.json.return_value = {"models": []}
        return r
    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    assert client.get("/api/ollama/models", cookies=cookie).status_code == 200
    assert ("Authorization" in seen["headers"]) is expect_auth


# ------------------------------------------------------------ SSRF ranges
@pytest.mark.parametrize("ip", ["100.64.0.1", "100.127.255.254", "192.0.2.1", "198.18.0.1",
                                "::ffff:10.0.0.1", "::ffff:127.0.0.1", "fc00::1", "127.0.0.1",
                                "169.254.169.254", "0.0.0.0"])
def test_non_global_addresses_blocked(ip):
    assert weblinks._is_blocked_ip(ip)


def test_public_address_allowed():
    assert not weblinks._is_blocked_ip("93.184.216.34")


# ------------------------------------------------------------ documents
def test_download_filename_is_encoded(monkeypatch):
    from api.routes import documents
    h = documents._content_disposition('evil"; x=1\r\nSet-Cookie: a=b.pdf')
    assert "\r" not in h and "\n" not in h
    assert h.startswith('attachment; filename="evil__ x_1Set-Cookie_ a_b.pdf"')
    assert "filename*=UTF-8''evil%22%3B%20x%3D1Set-Cookie%3A%20a%3Db.pdf" in h
    assert "filename*=UTF-8''r%C3%A9sum%C3%A9.pdf" in documents._content_disposition("résumé.pdf")


def test_storage_errors_are_not_echoed(monkeypatch):
    import s3_storage
    cookie, _ = _cookie(monkeypatch, "admin")
    monkeypatch.setattr(main.store, "get_stored_document",
                        lambda d: {"id": d, "s3_key": "k", "project_id": "p1"})
    monkeypatch.setattr(s3_storage.s3_storage, "download_document",
                        MagicMock(side_effect=RuntimeError("AccessDenied arn:aws:iam::123:role/x")))
    r = client.get("/api/documents/abc/download", cookies=cookie)
    assert r.status_code == 500
    assert "arn:aws" not in r.text


# ------------------------------------------------------------ defect links
@pytest.mark.parametrize("link,ok", [("javascript:alert(1)", False), ("data:text/html,x", False),
                                     ("https://jira.example.com/browse/X-1", True), ("", True),
                                     ("http://x y", False), ("//evil.example", False)])
def test_defect_link_scheme(monkeypatch, link, ok):
    cookie, _ = _cookie(monkeypatch, "editor")
    monkeypatch.setattr(main.store, "get_cycle", lambda c: {"id": c, "project_id": "p1"})
    monkeypatch.setattr(main.store, "set_cycle_item_status", lambda *a, **k: {"ok": True})
    r = client.patch("/api/test-cycles/c1/items", cookies=cookie,
                     json={"item_id": "i1", "status": "failed", "defect_link": link})
    assert (r.status_code == 200) is ok, r.text


# ------------------------------------------------------------ logout / password
def test_logout_revokes_session(monkeypatch):
    cookie, user = _cookie(monkeypatch, "viewer")
    bumped = []
    monkeypatch.setattr(main.store, "bump_session_version",
                        lambda uid: bumped.append(uid) or user.update(session_version=1))
    assert client.post("/api/auth/logout", cookies=cookie).status_code == 200
    assert bumped == ["u1"]
    assert client.get("/api/auth/me", cookies=cookie).status_code == 401


def test_logout_without_session_still_ok():
    assert client.post("/api/auth/logout").json() == {"ok": True}


def test_viewer_can_change_own_password(monkeypatch):
    cookie, user = _cookie(monkeypatch, "viewer",
                           password_hash=auth.hash_password("Old-pass-1"))
    monkeypatch.setattr(main.store, "get_user_by_email", lambda e: user)
    monkeypatch.setattr(main.store, "set_user_password",
                        lambda uid, h: {**user, "password_hash": h})
    r = client.post("/api/auth/change-password", cookies=cookie,
                    json={"current_password": "Old-pass-1", "new_password": "New-pass-22"})
    assert r.status_code == 200, r.text
