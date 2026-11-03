"""Stored credentials are only reused for the destination they were saved for.

Covers POST /api/embedding/switch (admin-only; stored embedding key never forwarded to
a different provider/base URL) and PUT /api/settings (LLM key / Jira token / SMTP
password are not reused, and are cleared, when their endpoint/host changes without a
new secret being supplied).
"""
import auth
import crypto
import main
import pytest
from fastapi.testclient import TestClient

from api.routes import jobs_usage, settings as settings_routes

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)


def _cookie(monkeypatch, role="admin"):
    user = {"id": "u1", "email": "u1@example.com", "role": role, "active": True,
            "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}


@pytest.fixture
def saved(monkeypatch):
    doc = {}
    monkeypatch.setattr(main.store, "get_settings", lambda: doc)
    monkeypatch.setattr(main.store, "save_settings", lambda upd: doc.update(upd))
    return doc


class _RecordingEmbedder:
    calls = []

    def __init__(self, **kw):
        _RecordingEmbedder.calls.append(kw)

    def probe_dim(self):
        return 16


@pytest.fixture
def embedder(monkeypatch):
    _RecordingEmbedder.calls = []
    monkeypatch.setattr(jobs_usage, "Embedder", _RecordingEmbedder)
    monkeypatch.setattr(jobs_usage, "launch_job", lambda *a, **kw: "job1")
    return _RecordingEmbedder


# ------------------------------------------------------------ embedding switch
def test_embedding_switch_is_admin_only(monkeypatch, saved, embedder):
    r = client.post("/api/embedding/switch", cookies=_cookie(monkeypatch, "editor"),
                    json={"provider": "openai", "model": "m"})
    assert r.status_code == 403
    assert embedder.calls == []


def test_embedding_switch_reuses_key_for_same_destination(monkeypatch, saved, embedder):
    saved.update(embed_provider="openai", embed_base_url="",
                 embed_api_key_enc=crypto.encrypt("sk-stored"))
    r = client.post("/api/embedding/switch", cookies=_cookie(monkeypatch),
                    json={"provider": "openai", "model": "text-embedding-3-large"})
    assert r.status_code == 200, r.text
    assert embedder.calls[-1]["api_key"] == "sk-stored"
    assert crypto.decrypt(saved["embed_api_key_enc"]) == "sk-stored"


@pytest.mark.parametrize("change", [
    {"provider": "openai-compatible", "base_url": ""},
    {"provider": "openai", "base_url": "https://other.example.com/v1"},
])
def test_embedding_switch_never_forwards_stored_key_to_new_destination(
        monkeypatch, saved, embedder, change):
    saved.update(embed_provider="openai", embed_base_url="",
                 embed_api_key_enc=crypto.encrypt("sk-stored"))
    r = client.post("/api/embedding/switch", cookies=_cookie(monkeypatch),
                    json={"model": "m", **change})
    assert r.status_code == 400
    assert all(c["api_key"] != "sk-stored" for c in embedder.calls)
    assert crypto.decrypt(saved["embed_api_key_enc"]) == "sk-stored"


def test_embedding_switch_to_keyless_destination_drops_stored_key(monkeypatch, saved, embedder):
    saved.update(embed_provider="openai", embed_base_url="",
                 embed_api_key_enc=crypto.encrypt("sk-stored"))
    r = client.post("/api/embedding/switch", cookies=_cookie(monkeypatch),
                    json={"provider": "ollama", "model": "nomic-embed-text"})
    assert r.status_code == 200, r.text
    assert embedder.calls[-1]["api_key"] == ""
    assert saved["embed_api_key_enc"] == ""


# ------------------------------------------------------------ PUT /api/settings
class _FakeLLM:
    calls = []

    def __init__(self, **kw):
        _FakeLLM.calls.append(kw)

    def ping(self):
        return {"ok": True}


@pytest.fixture
def fake_llm(monkeypatch):
    _FakeLLM.calls = []
    monkeypatch.setattr(settings_routes, "LLM", _FakeLLM)
    return _FakeLLM


def test_llm_key_reused_when_only_model_changes(monkeypatch, saved, fake_llm):
    saved.update(llm_provider="openai", llm_base_url="https://api.openai.com/v1",
                 llm_api_key_enc=crypto.encrypt("sk-llm"))
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"llm_provider": "openai", "llm_base_url": "https://api.openai.com/v1",
                         "llm_model": "gpt-x", "llm_api_key": ""})
    assert r.status_code == 200, r.text
    assert fake_llm.calls[-1]["api_key"] == "sk-llm"
    assert crypto.decrypt(saved["llm_api_key_enc"]) == "sk-llm"


def test_llm_key_not_sent_to_new_base_url(monkeypatch, saved, fake_llm):
    saved.update(llm_provider="openai", llm_base_url="https://api.openai.com/v1",
                 llm_api_key_enc=crypto.encrypt("sk-llm"))
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"llm_provider": "openai", "llm_base_url": "https://elsewhere.example/v1",
                         "llm_api_key": ""})
    assert r.status_code == 400
    assert fake_llm.calls == []
    assert crypto.decrypt(saved["llm_api_key_enc"]) == "sk-llm"


def test_llm_key_dropped_when_moving_to_new_ollama_url(monkeypatch, saved, fake_llm):
    monkeypatch.setattr(settings_routes, "_ENV_OLLAMA", "")
    saved.update(llm_provider="ollama", ollama_url="http://ollama-a:11434",
                 llm_api_key_enc=crypto.encrypt("ollama-token"))
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"llm_provider": "ollama", "ollama_url": "http://ollama-b:11434",
                         "llm_base_url": ""})
    assert r.status_code == 200, r.text
    assert fake_llm.calls[-1]["api_key"] == ""
    assert saved["llm_api_key_enc"] == ""


def test_jira_token_not_reused_for_new_site(monkeypatch, saved):
    seen = []

    class _J:
        def __init__(self, base, email, token):
            seen.append(token)

        def myself(self):
            return {"accountId": "x"}

    monkeypatch.setattr(settings_routes.jira, "Jira", _J)
    saved.update(jira_base_url="https://a.atlassian.net", jira_email="a@example.com",
                 jira_api_token_enc=crypto.encrypt("jira-tok"))
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"jira_base_url": "https://b.example.com", "jira_email": "a@example.com",
                         "jira_api_token": ""})
    assert r.status_code == 400
    assert seen == []
    # Same site, blank token: stored token is kept and reused.
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"jira_base_url": "https://a.atlassian.net", "jira_email": "a@example.com",
                         "jira_api_token": ""})
    assert r.status_code == 200, r.text
    assert seen == ["jira-tok"]


def test_smtp_password_not_reused_for_new_host(monkeypatch, saved):
    seen = []

    def _validate(cfg):
        seen.append(cfg["password"])
        return True, ""

    monkeypatch.setattr(settings_routes.email_send, "validate_config", _validate)
    saved.update(smtp_host="smtp.a.example", smtp_user="u", smtp_pass_enc=crypto.encrypt("pw"))
    r = client.put("/api/settings", cookies=_cookie(monkeypatch),
                   json={"smtp_host": "smtp.b.example", "smtp_user": "u", "smtp_pass": ""})
    assert r.status_code == 200, r.text
    assert seen == [""]
    assert saved["smtp_pass_enc"] == ""
