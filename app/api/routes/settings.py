"""Settings (Configuration UI): LLM/Jira/SMTP/S3 config CRUD, Ollama model listing,
LLM connectivity test, audit-log listing, DB status/config/migrate, and the SMTP/S3
connectivity tests.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 6/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

This is one contiguous domain in the original main.py (get_settings through s3_test),
so it moves as a single router file rather than being split further — splitting it
would force artificial cross-imports between fragments that all read/write the same
`store.get_settings()`/`store.save_settings()` document.

``_svc_error``/``_ext_error`` (used by ``llm_test``) already live in core/deps.py as of
this same commit (documented deviation: they're called from a dozen-plus
still-in-main.py routes across other not-yet-extracted domains too, so keeping them in
exactly one router would force those other routes to import from this router, which
the plan explicitly forbids).
"""
import os

import crypto
import email_send
import jira
import usage
from fastapi import APIRouter, HTTPException, Request
from llm import LLM
from pydantic import BaseModel

import auth
from api.schemas import OtpRequestIn
from core.audit import _audit
from core.bootstrap import BOOT, _search_unsupported
from core.config import (
    DB_NAME, EMBED_DIM, EMBED_MODEL, ENV_FILE_PATH,
    GEN_MODEL, MIN_POLL_INTERVAL, PROVIDER_LOCK,
    _ENV_MONGO, _ENV_OLLAMA,
)
from core.deps import (
    _ext_error, _smtp_cfg, _write_env_var,
    current_llm, current_ollama_url, current_poll_interval,
)
from core.logging_setup import get_logger
from core.state import store
from workers.registry import launch_job

log = get_logger("settings")

router = APIRouter()


def _jira_token_status(s: dict) -> tuple[bool, bool, str]:
    """(has_enc, readable, plaintext) for the stored Jira API token.

    ``crypto.decrypt()`` swallows its own failures and returns "" on a bad
    token, so a non-empty ``jira_api_token_enc`` that decrypts to "" can only
    mean the ciphertext can no longer be read under the current
    ENCRYPTION_KEY/APP_SECRET (e.g. it was rotated, or the value was restored
    from an older backup) — the exact same ambiguity `_smtp_cfg()` (core/deps.py)
    already special-cases for the SMTP password. Settings previously treated
    "has_enc but unreadable" the same as "never set": the placeholder still said
    "Leave blank to keep current" (driven by has_enc alone), but re-saving with
    a blank token then resolved to "" and tripped the generic "all required"
    validation error — confusing, since the fields visibly looked configured.
    Callers now get all three states explicitly instead of collapsing them.
    """
    enc = s.get("jira_api_token_enc", "")
    if not enc:
        return False, False, ""
    plaintext = crypto.decrypt(enc)
    return True, bool(plaintext), plaintext


# Known embedding models per provider (id + native dimension) for the UI. The real
# dimension is always measured (probe_dim) at switch time, so these are just hints.
EMBED_MODEL_OPTIONS = {
    "ollama": [{"id": "nomic-embed-text", "dim": 768}, {"id": "mxbai-embed-large", "dim": 1024}],
    "openai": [{"id": "text-embedding-3-small", "dim": 1536}, {"id": "text-embedding-3-large", "dim": 3072}],
    "gemini": [{"id": "gemini-embedding-001", "dim": 3072}, {"id": "text-embedding-004", "dim": 768}],
    "voyage": [{"id": "voyage-3", "dim": 1024}, {"id": "voyage-3-lite", "dim": 512},
               {"id": "voyage-3-large", "dim": 1024}],
    "openai-compatible": [],
    "bedrock": [{"id": "amazon.titan-embed-text-v2:0", "dim": 1024},
                {"id": "amazon.titan-embed-text-v1", "dim": 1536},
                {"id": "cohere.embed-english-v3", "dim": 1024},
                {"id": "cohere.embed-multilingual-v3", "dim": 1024}],
}


@router.get("/api/settings")
def get_settings():
    s = store.get_settings()
    return {
        # First-run gate: the UI lands on Configuration until the required LLM
        # section has been saved at least once (set in put_settings).
        "configured": bool(s.get("configured")),
        "llm_provider": s.get("llm_provider", "ollama"),
        "llm_base_url": s.get("llm_base_url", ""),
        "llm_model": s.get("llm_model", GEN_MODEL),
        "llm_region": s.get("llm_region", ""),
        "llm_api_key_set": bool(s.get("llm_api_key_enc")),
        # Deploy-time lock: pin the whole app to a single provider (e.g. an
        # air-gapped Bedrock-only client). Empty string = no lock (OSS build).
        "provider_lock": PROVIDER_LOCK,
        # Ollama endpoint: .env wins (locked); else the frontend-saved value; else bundled.
        "ollama_url": ("" if _ENV_OLLAMA else s.get("ollama_url", "")),
        "ollama_url_effective": current_ollama_url(),
        "ollama_url_env_locked": bool(_ENV_OLLAMA),
        # GitHub poller cadence (seconds). Frontend-saved value wins; "" means unset
        # (falls back to .env / the 30-min default, shown as *_effective).
        "poll_interval_s": s.get("poll_interval_s", ""),
        "poll_interval_s_effective": current_poll_interval(),
        "poll_interval_min_s": MIN_POLL_INTERVAL,
        # Whether a saved poll interval is also mirrored to .env (true) or applies at
        # runtime only because .env isn't writable in this deployment (false).
        "poll_interval_env_writable": _env_file_writable(),
        "jira_base_url": s.get("jira_base_url", ""),
        "jira_email": s.get("jira_email", ""),
        "jira_token_set": bool(s.get("jira_api_token_enc")),
        # True only when a stored token is present AND still decryptable — see
        # _jira_token_status(). The UI uses this (not jira_token_set) to decide
        # whether "Leave blank to keep current" is actually true.
        "jira_token_readable": _jira_token_status(s)[1],
        "jira_configured": bool(s.get("jira_base_url") and s.get("jira_email")
                                and _jira_token_status(s)[1]),
        "smtp_host": s.get("smtp_host", ""),
        "smtp_port": s.get("smtp_port", ""),
        "smtp_user": s.get("smtp_user", ""),
        "smtp_from": s.get("smtp_from", ""),
        "smtp_tls": s.get("smtp_tls", True),
        "smtp_ssl": s.get("smtp_ssl", False),
        "smtp_pass_set": bool(s.get("smtp_pass_enc")),
        "smtp_configured": bool(s.get("smtp_host")),
        "figma_token_set": bool(s.get("figma_api_token_enc")),
        # LLM cost model: per-1M-token prices, plus the built-in defaults for the editor.
        "llm_prices": s.get("llm_prices", {}),
        "llm_price_defaults": usage.DEFAULT_PRICES,
        # Embedding model (switching it rebuilds indexes + re-embeds everything).
        "embed_provider": s.get("embed_provider", "ollama"),
        "embed_model": s.get("embed_model", EMBED_MODEL),
        "embed_dim": int(s.get("embed_dim") or EMBED_DIM),
        "embed_base_url": s.get("embed_base_url", ""),
        "embed_region": s.get("embed_region", ""),
        "embed_api_key_set": bool(s.get("embed_api_key_enc")),
        "embed_model_options": EMBED_MODEL_OPTIONS,
        # AWS S3 Document Storage
        "s3_enabled": bool(s.get("s3_enabled")),
        "s3_bucket": s.get("s3_bucket", ""),
        "s3_region": s.get("s3_region", ""),
        "s3_access_key_id": s.get("s3_access_key_id", ""),
        "s3_secret_access_key_set": bool(s.get("s3_secret_access_key_enc")),
        "s3_prefix": s.get("s3_prefix", "documents"),
        "s3_configured": bool(s.get("s3_bucket")),
    }


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_region: str | None = None
    ollama_url: str | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str | None = None
    smtp_tls: bool | None = None
    smtp_ssl: bool | None = None
    figma_api_token: str | None = None
    llm_prices: dict | None = None
    poll_interval_s: int | None = None
    s3_enabled: bool | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_prefix: str | None = None


def _merged_settings_dict(body: SettingsIn):
    s = store.get_settings()
    return {
        "llm_provider": body.llm_provider if body.llm_provider is not None else s.get("llm_provider", "ollama"),
        "llm_base_url": body.llm_base_url.strip() if body.llm_base_url is not None else s.get("llm_base_url", ""),
        "llm_model": body.llm_model if body.llm_model is not None else s.get("llm_model", GEN_MODEL),
        "llm_region": body.llm_region.strip() if body.llm_region is not None else s.get("llm_region", ""),
        "llm_api_key": body.llm_api_key.strip() if (body.llm_api_key is not None and body.llm_api_key.strip() != "") else (
            crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
        ),
        "jira_base_url": body.jira_base_url.strip() if body.jira_base_url is not None else s.get("jira_base_url", ""),
        "jira_email": body.jira_email.strip() if body.jira_email is not None else s.get("jira_email", ""),
        "jira_api_token": body.jira_api_token.strip() if (body.jira_api_token is not None and body.jira_api_token.strip() != "") else _jira_token_status(s)[2],
        "smtp_host": body.smtp_host.strip() if body.smtp_host is not None else s.get("smtp_host", ""),
        "smtp_port": body.smtp_port if body.smtp_port is not None else s.get("smtp_port", ""),
        "smtp_user": body.smtp_user.strip() if body.smtp_user is not None else s.get("smtp_user", ""),
        "smtp_pass": body.smtp_pass if (body.smtp_pass is not None and body.smtp_pass != "") else (
            crypto.decrypt(s.get("smtp_pass_enc", "")) if s.get("smtp_pass_enc") else ""
        ),
        "smtp_from": body.smtp_from.strip() if body.smtp_from is not None else s.get("smtp_from", ""),
        "smtp_tls": body.smtp_tls if body.smtp_tls is not None else s.get("smtp_tls", True),
        "smtp_ssl": body.smtp_ssl if body.smtp_ssl is not None else s.get("smtp_ssl", False),
        "s3_enabled": body.s3_enabled if body.s3_enabled is not None else s.get("s3_enabled", False),
        "s3_bucket": body.s3_bucket.strip() if body.s3_bucket is not None else s.get("s3_bucket", ""),
        "s3_region": body.s3_region.strip() if body.s3_region is not None else s.get("s3_region", ""),
        "s3_access_key_id": body.s3_access_key_id.strip() if body.s3_access_key_id is not None else s.get("s3_access_key_id", ""),
        "s3_secret_access_key": body.s3_secret_access_key.strip() if (body.s3_secret_access_key is not None and body.s3_secret_access_key.strip() != "") else (
            crypto.decrypt(s.get("s3_secret_access_key_enc", "")) if s.get("s3_secret_access_key_enc") else ""
        ),
        "s3_prefix": body.s3_prefix.strip() if body.s3_prefix is not None else s.get("s3_prefix", "documents"),
    }


@router.put("/api/settings")
def put_settings(body: SettingsIn, request: Request):
    s = store.get_settings()
    merged = _merged_settings_dict(body)
    # LLM connectivity validation if updated
    llm_updated = (
        body.llm_provider is not None or
        body.llm_base_url is not None or
        body.llm_model is not None or
        body.llm_api_key is not None or
        body.llm_region is not None
    )
    if llm_updated:
        # Validate against the Ollama URL being submitted now (if any), not the stale
        # saved one — otherwise a combined provider+endpoint change pings the old host.
        _val_ollama = (body.ollama_url.strip() if body.ollama_url is not None else "") or current_ollama_url()
        temp_llm = LLM(
            provider=merged["llm_provider"],
            model=merged["llm_model"],
            api_key=merged["llm_api_key"],
            base_url=merged["llm_base_url"],
            ollama_url=_val_ollama,
            region=merged["llm_region"],
        )
        try:
            temp_llm.ping()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"LLM validation failed: {e}")

    jira_updated = (
        body.jira_base_url is not None or
        body.jira_email is not None or
        body.jira_api_token is not None
    )
    if jira_updated:
        jira_values = [merged["jira_base_url"], merged["jira_email"], merged["jira_api_token"]]
        if any(jira_values):
            if not all(jira_values):
                # A blank submitted token normally means "keep the current one" (merged
                # above falls back to the stored value) — so landing here with an empty
                # merged token, while base URL/email ARE present, means there either was
                # never a token saved, or one WAS saved but can no longer be decrypted
                # (has_enc True, readable False — e.g. after an ENCRYPTION_KEY/APP_SECRET
                # change). Those need different messages: the second case isn't "you
                # forgot to fill in fields you can see are already there", it's "the
                # token you already entered can't be used anymore, re-enter it".
                has_enc, readable, _ = _jira_token_status(s)
                if (body.jira_api_token is None or body.jira_api_token.strip() == "") and has_enc and not readable:
                    raise HTTPException(status_code=400, detail=(
                        "Jira validation failed: the saved API token can no longer be "
                        "decrypted (the app's encryption key may have changed) — please "
                        "re-enter your Jira API token."))
                raise HTTPException(status_code=400, detail="Jira validation failed: base URL, email, and API token are all required")
            try:
                me = jira.Jira(
                    merged["jira_base_url"],
                    merged["jira_email"],
                    merged["jira_api_token"],
                ).myself()
                if not me:
                    raise HTTPException(status_code=400, detail="Jira validation failed: could not verify account")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Jira validation failed: {e}")

    smtp_updated = (
        body.smtp_host is not None or
        body.smtp_port is not None or
        body.smtp_user is not None or
        body.smtp_pass is not None or
        body.smtp_from is not None or
        body.smtp_tls is not None or
        body.smtp_ssl is not None
    )
    if smtp_updated and merged["smtp_host"]:
        # Gmail always requires an authenticated App Password; catch the missing-
        # credentials case up front so validation doesn't "pass" on a bare connect.
        if email_send.is_gmail(merged["smtp_host"]) and not (merged["smtp_user"] and merged["smtp_pass"]):
            raise HTTPException(status_code=400, detail="SMTP validation failed: Gmail "
                "requires a username (your full Gmail address) and a 16-character App "
                "Password (with 2-Step Verification enabled on the account).")
        # Validate with the SAME normalized password we'll persist — otherwise a
        # Gmail App Password pasted with its display spaces ("abcd efgh …") is sent
        # verbatim and Gmail rejects it (535 BadCredentials) even though it's valid.
        validate_pass = email_send.normalize_smtp_password(merged["smtp_host"], merged["smtp_pass"])
        ok, err = email_send.validate_config({
            "host": merged["smtp_host"],
            "port": merged["smtp_port"],
            "user": merged["smtp_user"],
            "password": validate_pass,
            "from": merged["smtp_from"],
            "tls": merged["smtp_tls"],
            "ssl": merged["smtp_ssl"],
        })
        if not ok:
            raise HTTPException(status_code=400, detail=f"SMTP validation failed: {err}")

    upd = {}
    if body.llm_provider is not None:
        upd["llm_provider"] = body.llm_provider
    if body.llm_base_url is not None:
        upd["llm_base_url"] = body.llm_base_url
    if body.llm_model is not None:
        upd["llm_model"] = body.llm_model
    if body.llm_region is not None:
        upd["llm_region"] = body.llm_region.strip()
    if body.llm_api_key is not None:
        if body.llm_api_key.strip() != "":
            upd["llm_api_key_enc"] = crypto.encrypt(body.llm_api_key.strip())
        elif not s.get("llm_api_key_enc") or (body.llm_provider or merged["llm_provider"]) in ("ollama", "bedrock"):
            upd["llm_api_key_enc"] = ""
    if body.ollama_url is not None:
        # Ignored when OLLAMA_URL is locked by .env; otherwise applies live (no restart).
        upd["ollama_url"] = body.ollama_url.strip()
    if llm_updated:
        # Saving the required LLM section marks first-run setup complete, so the UI
        # stops force-landing on Configuration after sign-in.
        upd["configured"] = True
    if body.jira_base_url is not None:
        upd["jira_base_url"] = body.jira_base_url
    if body.jira_email is not None:
        upd["jira_email"] = body.jira_email
    if body.jira_api_token is not None:
        if body.jira_api_token.strip() != "":
            upd["jira_api_token_enc"] = crypto.encrypt(body.jira_api_token.strip())
        elif not body.jira_base_url and not body.jira_email:
            upd["jira_api_token_enc"] = ""
    if body.smtp_host is not None:
        upd["smtp_host"] = body.smtp_host.strip()
    if body.smtp_port is not None:
        upd["smtp_port"] = body.smtp_port
    if body.smtp_user is not None:
        upd["smtp_user"] = body.smtp_user.strip()
    if body.smtp_pass is not None:
        if body.smtp_pass != "":
            clean_pass = email_send.normalize_smtp_password(merged["smtp_host"], body.smtp_pass)
            upd["smtp_pass_enc"] = crypto.encrypt(clean_pass) if clean_pass else ""
        elif not body.smtp_host:
            upd["smtp_pass_enc"] = ""
    if body.smtp_from is not None:
        upd["smtp_from"] = body.smtp_from.strip()
    if body.smtp_tls is not None:
        upd["smtp_tls"] = body.smtp_tls
    if body.smtp_ssl is not None:
        upd["smtp_ssl"] = body.smtp_ssl
    if body.figma_api_token is not None:
        upd["figma_api_token_enc"] = crypto.encrypt(body.figma_api_token) if body.figma_api_token else ""
    if body.s3_enabled is not None:
        upd["s3_enabled"] = body.s3_enabled
    if body.s3_bucket is not None:
        upd["s3_bucket"] = body.s3_bucket.strip()
    if body.s3_region is not None:
        upd["s3_region"] = body.s3_region.strip()
    if body.s3_access_key_id is not None:
        upd["s3_access_key_id"] = body.s3_access_key_id.strip()
    if body.s3_secret_access_key is not None:
        if body.s3_secret_access_key.strip() != "":
            upd["s3_secret_access_key_enc"] = crypto.encrypt(body.s3_secret_access_key.strip())
        elif not body.s3_bucket:
            upd["s3_secret_access_key_enc"] = ""
    if body.s3_prefix is not None:
        upd["s3_prefix"] = body.s3_prefix.strip()
    if body.poll_interval_s is not None:
        # Floor to MIN_POLL_INTERVAL so a stray small value can't hammer the GitHub API.
        # Applies to the poller on its next loop — no restart needed.
        pv = max(MIN_POLL_INTERVAL, int(body.poll_interval_s))
        upd["poll_interval_s"] = pv
        # Keep .env in sync with the UI so the two never appear to disagree — this is a
        # self-hosted, open-source app and operators read .env directly. Best-effort:
        # if .env isn't writable (e.g. not bind-mounted) the Mongo value still applies
        # live, so we don't fail the save; we just note it in the log.
        if _env_file_writable():
            ok, err = _write_env_var(ENV_FILE_PATH, "POLL_INTERVAL_SECONDS", str(pv))
            if not ok:
                log.warning("could not persist POLL_INTERVAL_SECONDS to %s: %s",
                          ENV_FILE_PATH, err)
    if body.llm_prices is not None:
        # keep only well-formed {model: {in, out}} entries
        clean = {}
        for m, p in (body.llm_prices or {}).items():
            if isinstance(p, dict):
                try:
                    clean[str(m)] = {"in": float(p.get("in", 0)), "out": float(p.get("out", 0))}
                except (TypeError, ValueError):
                    continue
        upd["llm_prices"] = clean
    if upd:
        store.save_settings(upd)
        # Record which settings groups changed (never the secret values themselves).
        changed = sorted({k.replace("_enc", "").split("_")[0] for k in upd})
        _audit(request, "settings.updated", detail=", ".join(changed))
    return get_settings()


@router.get("/api/ollama/models")
def ollama_models():
    """List the models actually installed in the connected Ollama, so the UI can offer
    only real choices (avoids picking a model that isn't downloaded). Uses the effective
    Ollama URL + the saved LLM token (for a secured/remote Ollama). Best-effort."""
    url = current_ollama_url().rstrip("/")
    s = store.get_settings()
    key = crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        import httpx
        r = httpx.get(f"{url}/api/tags", timeout=8.0, headers=headers)
        r.raise_for_status()
        models = sorted(m.get("name") for m in r.json().get("models", []) if m.get("name"))
        return {"ok": True, "models": models, "url": url}
    except Exception as e:  # noqa: BLE001
        log.warning("[ollama-tags] %s: %r", url, e)
        return {"ok": False, "models": [], "url": url,
                "error": "could not reach Ollama at this URL"}


@router.post("/api/llm/test")
def llm_test():
    try:
        return {"ok": True, **current_llm().ping()}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("LLM", e)


@router.get("/api/audit-logs")
def audit_logs(limit: int = 100, action: str | None = None, actor: str | None = None):
    """Admin-only audit trail (gated by ADMIN_PATHS)."""
    return {"logs": store.list_audit(limit=limit, action=action, actor_email=actor)}


@router.get("/api/db-status")
def db_status():
    """Read-only database snapshot for the Configuration UI (admin-only, gated by
    ADMIN_PATHS). No credentials are returned — the database is configured via the
    MONGO_URI env var, not here; this is observability only. Includes whether the
    bundled/managed search engine is available and whether the URI is externally set."""
    info = store.db_info()
    info["db_name"] = DB_NAME
    # Bundled vs bring-your-own is inferred from the actual connected host, not from
    # the env var (compose always injects MONGO_URI, so its mere presence is not a
    # reliable signal). The bundled nodes live on the internal *.warden-net aliases.
    hosts = info.get("hosts") or []
    info["managed"] = not any(".warden-net" in h for h in hosts)
    info["boot"] = BOOT
    # Frontend-config capabilities: whether MONGO_URI is pinned in .env, and whether
    # we can persist a new one (the .env bind-mount must be writable).
    info["configured_via_env"] = bool(_ENV_MONGO)
    info["env_file"] = ENV_FILE_PATH
    info["env_writable"] = _env_file_writable()
    return info


def _env_file_writable() -> bool:
    """True if we can persist config into the .env file (it exists & is writable, or
    its directory is writable so we could create it). In Docker this requires the
    ./.env bind-mount from docker-compose.app.yml."""
    try:
        if os.path.exists(ENV_FILE_PATH):
            return os.access(ENV_FILE_PATH, os.W_OK)
        return os.access(os.path.dirname(ENV_FILE_PATH) or ".", os.W_OK)
    except Exception:  # noqa: BLE001
        return False


def _probe_mongo(uri: str):
    """Best-effort connectivity + Vector Search check for a candidate URI, so we never
    persist a connection string that would brick startup. Returns (reachable, search_ok, detail)."""
    try:
        from pymongo import MongoClient
        c = MongoClient(uri, serverSelectionTimeoutMS=3500)
        try:
            c.admin.command("ping")
            search_ok = True
            try:
                list(c[DB_NAME]["test_cases"].list_search_indexes())
            except Exception as e:  # noqa: BLE001
                # A search-less server rejects the command outright; a missing namespace
                # (fresh DB) does NOT mean search is unsupported.
                search_ok = not _search_unsupported(e)
            return True, search_ok, "ok"
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        return False, False, str(e)[:200]


class DbConfigIn(BaseModel):
    uri: str | None = None
    force: bool | None = False   # save even if the connection test fails


@router.post("/api/db-config")
def set_db_config(body: DbConfigIn, request: Request):
    """Persist a new MongoDB connection string into .env (admin-only). Joomla-style:
    the value is written to the config file, never echoed back, and takes effect on the
    next `docker compose up -d`. We test-connect first and refuse to save an unreachable
    or search-incapable DB unless `force` is set."""
    uri = (body.uri or "").strip()
    if not uri:
        raise HTTPException(400, "Enter a MongoDB connection string.")
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        raise HTTPException(400, "Connection string must start with mongodb:// or mongodb+srv://")
    if not _env_file_writable():
        raise HTTPException(500, f"Cannot write to the config file ({ENV_FILE_PATH}). In Docker, "
                                 "the ./.env bind-mount in docker-compose.app.yml must be present "
                                 "and writable.")
    reachable, search_ok, detail = _probe_mongo(uri)
    if not reachable and not body.force:
        raise HTTPException(400, f"Could not connect to that database: {detail}. Nothing was saved. "
                                 "Re-submit with 'save anyway' to store it regardless.")
    if reachable and not search_ok and not body.force:
        raise HTTPException(400, "That database connected but has no Vector Search (not Atlas and no "
                                 "mongot). wardenIQ requires search. Nothing was saved. Use 'save "
                                 "anyway' only if search will be enabled before restart.")
    ok, err = _write_env_var(ENV_FILE_PATH, "MONGO_URI", uri)
    if not ok:
        raise HTTPException(500, f"Failed to write the config file: {err}")
    _audit(request, "db.config.updated", detail="MONGO_URI changed via UI")
    return {"ok": True, "restart_required": True, "reachable": reachable,
            "search_available": search_ok, "apply_cmd": "docker compose up -d"}


class DbMigrateIn(BaseModel):
    target_uri: str | None = None
    overwrite: bool | None = False


@router.post("/api/db-migrate")
def db_migrate(body: DbMigrateIn, request: Request):
    """Copy ALL data from the current database into a target MongoDB and point
    MONGO_URI at it (admin-only). Runs as a background job; the app stays on the
    current DB until the user restarts, so a partial copy never loses data."""
    uri = (body.target_uri or "").strip()
    if not uri:
        raise HTTPException(400, "Enter the target MongoDB connection string.")
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        raise HTTPException(400, "Connection string must start with mongodb:// or mongodb+srv://")
    if not _env_file_writable():
        raise HTTPException(500, f"Cannot write to the config file ({ENV_FILE_PATH}); the ./.env "
                                 "bind-mount in docker-compose.app.yml must be present and writable.")
    # The target must be reachable AND search-capable — otherwise the copy would land
    # in a database the app can't actually run on.
    reachable, search_ok, detail = _probe_mongo(uri)
    if not reachable:
        raise HTTPException(400, f"Couldn't connect to the target database: {detail}. Nothing copied.")
    if not search_ok:
        raise HTTPException(400, "The target has no Vector Search (not Atlas, and no mongot), so "
                                 "wardenIQ couldn't run on it. Migration cancelled — nothing copied.")
    # Guard against clobbering a target that already has data (unless the caller insists).
    try:
        if not body.overwrite and store.target_has_data(uri):
            raise HTTPException(409, "The target database already contains data. Re-run with "
                                     "'overwrite' to replace it, or pick an empty database.")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("[db-config] target inspection failed: %r", e)
        raise HTTPException(400, "Couldn't inspect the target database — check the "
                                 "connection string, credentials and network access "
                                 "(details in the server logs)")
    jid = launch_job("migrate", {"target_uri": uri, "overwrite": bool(body.overwrite)},
                     label="Migrate data to a new database")
    _audit(request, "db.migrate.started", detail="migration to a new MongoDB started")
    return {"job_id": jid}


@router.post("/api/smtp/test")
def smtp_test(body: OtpRequestIn):
    cfg = _smtp_cfg()
    if not cfg:
        raise HTTPException(400, "SMTP is not configured — add email settings to send sign-in codes")
    ok, err = email_send.send_otp(cfg, (body.email or "").strip(), auth.gen_otp())
    if not ok:
        log.warning("[smtp-test] send failed: %s", err)
        raise HTTPException(502, "could not send the test email — check the SMTP host, "
                                 "port, credentials and TLS/SSL settings")
    return {"ok": True, "sent_to": body.email}


class S3TestIn(BaseModel):
    bucket: str | None = None
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None


@router.post("/api/settings/s3/test")
def s3_test(body: S3TestIn):
    from s3_storage import s3_storage
    secret_key = body.secret_access_key
    if not secret_key:
        s = store.get_settings()
        if s.get("s3_secret_access_key_enc"):
            secret_key = crypto.decrypt(s.get("s3_secret_access_key_enc"))
    res = s3_storage.test_connection(
        bucket=body.bucket,
        region=body.region,
        access_key_id=body.access_key_id,
        secret_access_key=secret_key,
    )
    if not res.get("ok"):
        raise HTTPException(400, detail=res.get("error", "AWS S3 connection test failed"))
    return res
