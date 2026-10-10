"""Settings (Configuration UI): LLM/Jira/SMTP/S3 config CRUD, Ollama model listing,
LLM connectivity test, audit-log listing, DB status/config/migrate, and the SMTP/S3
connectivity tests.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 6/20).
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
import secrets
import time

import crypto
import email_send
import jira
import usage
from fastapi import APIRouter, HTTPException, Request
from llm import LLM
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo.operations import SearchIndexModel

import auth
from api.schemas import OtpRequestIn
from core.audit import _audit
from core.bootstrap import (
    BOOT, _SEARCH_INDEX_LIMIT_MSG, _SEARCH_REQUIRED_MSG,
    _search_index_limit, _search_unsupported,
)
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
from core.security import _current_user
from core.state import store
from store.base import SELF_TARGET_MSG, TEXT_INDEX, VECTOR_INDEX
from workers.registry import JOB_RETRY_HANDLERS, launch_job, migration_blocker

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


# Absolute floor for the $vectorSearch aggregation stage across EITHER deployment
# shape: MongoDB Atlas supports it from 6.0.11+; self-managed (Community/Enterprise
# + mongot) needs a newer server still. We can't reliably tell "Atlas" from
# "self-managed" from server_version alone, so we only hard-fail below the LOWER of
# the two floors here -- anything above it but still too old for a self-managed
# mongot is caught by the real index-creation probe below, which is authoritative.
MIN_MONGO_VERSION = (6, 0, 11)

# Shared budget for the probe's search indexes to become queryable AND return the
# probe document. A fresh database can take well over 15s the first time mongot
# builds an index in it, so this is deliberately generous -- but still bounded.
PROBE_SEARCH_TIMEOUT_S = 60


def _version_below(version: str, floor: tuple) -> bool:
    """True if `version` ("8.3.1") is below `floor`. Fails OPEN (False, i.e. "not too
    old") on anything unparseable -- this is a fast pre-check, not the real gate; the
    capability probe that follows is what actually proves search works or doesn't."""
    try:
        parts = tuple(int(p) for p in version.split(".")[:len(floor)])
        parts = parts + (0,) * (len(floor) - len(parts))
        return parts < floor
    except (ValueError, AttributeError):
        return False


def _probe_vector(dim: int) -> list[float]:
    """The deterministic vector the capability probe indexes AND queries with.

    It must NOT be all zeros: the probe's vector index uses cosine similarity, which
    is undefined for a zero-magnitude vector, and a real mongot rejects the query
    ("Cosine similarity cannot be computed ...") -- which made a healthy MongoDB +
    mongot stack look search-incapable. The unit vector e0 = [1, 0, 0, ...] has
    magnitude exactly 1, is valid for cosine similarity at any dimension, needs no
    real embedding model, and is identical on every run. Built once per probe: O(dim)
    floats, shared by the inserted document and the query."""
    if not isinstance(dim, int) or dim < 1:
        raise ValueError(f"embedding dimension must be a positive integer, got {dim!r}")
    vec = [0.0] * dim
    vec[0] = 1.0
    return vec


def _probe_mongo(uri: str, dim: int | None = None) -> dict:
    """Real capability validation for a candidate MONGO_URI (issue #110) -- connect,
    confirm replica-set topology, sanity-check the server version, then actually
    CREATE a vectorSearch + search index on a disposable scratch collection, wait for
    them to become queryable, and run one real $vectorSearch and one real $search
    query that must return the probe document -- rather than just pinging or listing
    indexes on the real `test_cases` collection. The scratch collection and its
    indexes are always removed afterwards, whatever the outcome.

    `dim` is the embedding dimension the app is configured for (defaults to
    EMBED_DIM); the probe index and vector use exactly that dimension.

    Returns a dict: reachable, replica_set, server_version, search_ok, status (one of
    "unreachable" | "no_replica_set" | "version_too_old" | "insufficient_privileges" |
    "no_search" | "ok"), detail (safe and actionable: never the raw URI/credentials).
    Never raises."""
    result = {"reachable": False, "replica_set": False, "server_version": None,
              "search_ok": False, "status": "unreachable", "detail": ""}
    try:
        probe_dim = int(dim) if dim else EMBED_DIM
        vec = _probe_vector(probe_dim)
        c = MongoClient(uri, serverSelectionTimeoutMS=3500, connectTimeoutMS=5000,
                        socketTimeoutMS=30000)
    except Exception as e:  # noqa: BLE001
        result["detail"] = str(e)[:200]
        return result
    coll = None
    db = None
    name = None
    try:
        try:
            c.admin.command("ping")
        except Exception as e:  # noqa: BLE001
            result["detail"] = str(e)[:200]
            return result
        result["reachable"] = True

        # Fetched before any gate that might return early, so a caller always learns
        # the server version alongside whatever else failed.
        try:
            result["server_version"] = c.server_info().get("version")
        except Exception:  # noqa: BLE001
            pass

        # Topology: wardenIQ's bundled stacks (Community + Percona) are replica sets
        # and mongot's oplog tailing requires one; a standalone mongod can't run
        # Search at all. (A mongos router has no setName either; sharded clusters
        # aren't a supported deployment shape, so they're treated the same way.)
        try:
            hello = c.admin.command("hello")
        except Exception:  # noqa: BLE001
            try:
                hello = c.admin.command("ismaster")
            except Exception as e:  # noqa: BLE001
                result["status"] = "no_replica_set"
                result["detail"] = f"could not confirm replica-set membership: {str(e)[:150]}"
                return result
        if not hello.get("setName"):
            result["status"] = "no_replica_set"
            result["detail"] = ("this database is not a replica set. wardenIQ requires a "
                                "MongoDB replica set (Atlas, or self-managed with mongot) -- "
                                "a standalone mongod can't run Search.")
            return result
        result["replica_set"] = True

        version = result["server_version"]
        if isinstance(version, str) and _version_below(version, MIN_MONGO_VERSION):
            floor_str = ".".join(str(p) for p in MIN_MONGO_VERSION)
            result["status"] = "version_too_old"
            result["detail"] = (f"MongoDB {version} is too old -- wardenIQ's Vector Search "
                                f"needs at least MongoDB {floor_str}. Upgrade the database "
                                "or point at a newer one.")
            return result

        # Non-destructive capability probe on a disposable, unpredictably-named
        # scratch collection. Never touches a real application collection.
        db = c[DB_NAME]
        try:
            existing = set(db.list_collection_names())
        except Exception:  # noqa: BLE001
            existing = set()    # no listCollections privilege: the random suffix suffices
        for _ in range(5):
            candidate = f"wardeniq_probe_{secrets.token_hex(8)}"
            if candidate not in existing:
                name = candidate
                break
        if name is None:
            result["status"] = "no_search"
            result["detail"] = "could not allocate a unique scratch collection name for validation"
            return result
        coll = db[name]
        try:
            coll.insert_one({"title": "wardenIQ capability probe", "embedding": vec})
            coll.create_search_index(SearchIndexModel(
                definition={"fields": [{"type": "vector", "path": "embedding",
                                        "numDimensions": probe_dim, "similarity": "cosine"}]},
                name=VECTOR_INDEX, type="vectorSearch"))
            coll.create_search_index(SearchIndexModel(
                definition={"mappings": {"dynamic": False,
                                         "fields": {"title": {"type": "string"}}}},
                name=TEXT_INDEX, type="search"))
        except OperationFailure as e:
            if e.code == 13 or "not authorized" in str(e).lower():
                result["status"] = "insufficient_privileges"
                result["detail"] = ("connected, but this user isn't authorized to create search "
                                    "indexes -- wardenIQ needs index-management privileges on "
                                    "this database.")
            elif _search_index_limit(e):
                # Same classification + curated message core.bootstrap uses at startup:
                # the Atlas per-tier index cap is a distinct, common case, and the fix
                # (bigger tier or self-managed mongot) is not in the driver's error text.
                # The raw error goes to the server log, not to the caller.
                log.warning("[db-probe] search index limit reached on the candidate "
                            "database: %s", str(e)[:300])
                result["status"] = "no_search"
                result["detail"] = _SEARCH_INDEX_LIMIT_MSG
            elif _search_unsupported(e):
                result["status"] = "no_search"
                result["detail"] = _SEARCH_REQUIRED_MSG
            else:
                result["status"] = "no_search"
                result["detail"] = f"could not create a search index: {str(e)[:150]}"
            return result

        deadline = time.time() + PROBE_SEARCH_TIMEOUT_S
        ready = False
        while True:
            try:
                idx = {i.get("name"): i.get("queryable", False) for i in coll.list_search_indexes()}
            except Exception:  # noqa: BLE001
                idx = {}
            if idx.get(VECTOR_INDEX) and idx.get(TEXT_INDEX):
                ready = True
                break
            if time.time() >= deadline:
                break
            time.sleep(1)
        if not ready:
            result["status"] = "no_search"
            result["detail"] = ("search indexes were created but didn't become queryable in "
                                "time -- mongot may still be syncing, or Search isn't actually "
                                "available on this deployment.")
            return result

        # Both queries must execute AND find the probe document. A query that errors
        # is a definitive failure; an empty result may just be index lag, so retry
        # until the shared deadline.
        vector_stage = {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding",
                                          "queryVector": vec, "numCandidates": 10, "limit": 1}}
        text_stage = {"$search": {"index": TEXT_INDEX,
                                  "text": {"query": "wardenIQ", "path": "title"}}}
        found = False
        while True:
            try:
                found = bool(list(coll.aggregate([vector_stage]))) and \
                    bool(list(coll.aggregate([text_stage])))
            except Exception as e:  # noqa: BLE001
                result["status"] = "no_search"
                result["detail"] = f"search indexes exist but a query failed: {str(e)[:150]}"
                return result
            if found or time.time() >= deadline:
                break
            time.sleep(1)
        if not found:
            result["status"] = "no_search"
            result["detail"] = ("search indexes are queryable but returned no results for the "
                                "probe document -- mongot may still be syncing.")
            return result

        result["search_ok"] = True
        result["status"] = "ok"
        result["detail"] = "ok"
        return result
    except Exception as e:  # noqa: BLE001
        # Anything unexpected after connecting (network drop, driver error, ...): report
        # it as a validation result instead of letting it surface as an HTTP 500.
        result["status"] = "unreachable" if isinstance(e, ConnectionFailure) else "no_search"
        result["detail"] = f"validation could not complete: {str(e)[:150]}"
        result["search_ok"] = False
        return result
    finally:
        # Always clean up, on every path above -- success, failure, timeout, or crash.
        if coll is not None and db is not None and name is not None:
            try:
                have = {i.get("name") for i in coll.list_search_indexes()}
            except Exception:  # noqa: BLE001
                have = set()
            for idx_name in (VECTOR_INDEX, TEXT_INDEX):
                if idx_name in have:
                    try:
                        coll.drop_search_index(idx_name)
                    except Exception:  # noqa: BLE001
                        pass
            try:
                db.drop_collection(name)
            except Exception:  # noqa: BLE001
                pass
        c.close()


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
    probe = _probe_mongo(uri, dim=store.dim)
    if not probe["reachable"] and not body.force:
        raise HTTPException(400, f"Could not connect to that database: {probe['detail']}. Nothing "
                                 "was saved. Re-submit with 'save anyway' to store it regardless.")
    if probe["reachable"] and not probe["search_ok"] and not body.force:
        raise HTTPException(400, f"{probe['detail']} Nothing was saved. Use 'save anyway' only if "
                                 "this will be fixed before restart.")
    ok, err = _write_env_var(ENV_FILE_PATH, "MONGO_URI", uri)
    if not ok:
        raise HTTPException(500, f"Failed to write the config file: {err}")
    _audit(request, "db.config.updated", detail="MONGO_URI changed via UI")
    return {"ok": True, "restart_required": True, "reachable": probe["reachable"],
            "search_available": probe["search_ok"], "replica_set": probe["replica_set"],
            "server_version": probe["server_version"], "apply_cmd": "docker compose up -d"}


class DbMigrateIn(BaseModel):
    target_uri: str | None = None
    overwrite: bool | None = False
    # #111: start even though something else is running (see workers.registry's
    # migration_blocker()) -- accepts a best-effort snapshot. Separate from `overwrite`,
    # which answers a different question (may the TARGET's existing data be replaced?).
    override_busy: bool | None = False


def _preflight_migration(uri, overwrite: bool, override_busy: bool, via_retry: bool = False) -> str:
    """Everything that must hold before a migration job may be launched. Shared by EVERY
    way of starting one (POST /api/db-migrate and the retry of a failed migrate job), so
    the checks cannot be skipped by choosing a different entry point (#111). Returns the
    cleaned URI; raises HTTPException otherwise.

    The idle / one-migration-at-a-time rules are enforced again, atomically with the job
    creation, inside workers.registry.launch_job() -- the check here is the cheap
    fast-fail that avoids a long capability probe when the answer would be "no" anyway.
    Likewise the "target is this very database" rule is enforced again inside
    Store.migrate_to() and verify_migration(), where the data would actually be erased.

    `overwrite` is the caller's explicit, per-request choice to replace data already in the
    target; it is never taken from a stored job (see _retry_migration)."""
    uri = (uri or "").strip()
    if not uri:
        raise HTTPException(400, "Enter the target MongoDB connection string.")
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        raise HTTPException(400, "Connection string must start with mongodb:// or mongodb+srv://")
    if not _env_file_writable():
        raise HTTPException(500, f"Cannot write to the config file ({ENV_FILE_PATH}); the ./.env "
                                 "bind-mount in docker-compose.app.yml must be present and writable.")
    blocker = migration_blocker(override_busy)
    if blocker:
        raise HTTPException(409, blocker)
    # The target must be reachable AND search-capable — otherwise the copy would land
    # in a database the app can't actually run on.
    probe = _probe_mongo(uri, dim=store.dim)
    if not probe["reachable"]:
        raise HTTPException(400, f"Couldn't connect to the target database: {probe['detail']}. "
                                 "Nothing copied.")
    if not probe["search_ok"]:
        raise HTTPException(400, f"{probe['detail']} Migration cancelled — nothing copied.")
    # The target must be a DIFFERENT database. A migration with `overwrite` deletes the
    # target's documents before copying, so a target that is this very database (however its
    # URI is spelled -- this is proven, not guessed from the string) would erase the data.
    # Fails closed: if it cannot be determined, nothing is copied.
    try:
        if store.target_is_this_database(uri):
            raise HTTPException(400, SELF_TARGET_MSG)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("[db-config] could not confirm the target is a different database: %r", e)
        raise HTTPException(400, "Couldn't confirm that the target is a different database "
                                 "from the one wardenIQ is using, so nothing was copied "
                                 "(details in the server logs).")
    # Guard against clobbering a target that already has data (unless the caller insists).
    try:
        if not overwrite and store.target_has_data(uri):
            if via_retry:
                raise HTTPException(409, "The target database already contains data (for "
                                         "example from the earlier attempt). A retry never "
                                         "replaces existing data, so to replace it start the "
                                         "switch again from Configuration > Database and "
                                         "choose to replace it.")
            raise HTTPException(409, "The target database already contains data. Re-run with "
                                     "'overwrite' to replace it, or pick an empty database.")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("[db-config] target inspection failed: %r", e)
        raise HTTPException(400, "Couldn't inspect the target database — check the "
                                 "connection string, credentials and network access "
                                 "(details in the server logs)")
    return uri


def _start_migration(request: Request, uri, overwrite: bool, override_busy: bool,
                     label: str, via_retry: bool = False) -> str:
    """Preflight, then launch. launch_job() makes the final admission decision atomically
    with creating the job row (raising MigrationBlocked -> 409 if another migration or,
    without override_busy, any other job is running) and writes the audit entry first, so
    the audit insert cannot land mid-copy and count as the source changing."""
    uri = _preflight_migration(uri, overwrite, override_busy, via_retry=via_retry)
    return launch_job(
        "migrate",
        {"target_uri": uri, "overwrite": bool(overwrite), "override_busy": bool(override_busy)},
        label=label,
        before_start=lambda: _audit(request, "db.migrate.started",
                                    detail="migration to a new MongoDB started"))


@router.post("/api/db-migrate")
def db_migrate(body: DbMigrateIn, request: Request):
    """Copy ALL data from the current database into a target MongoDB and point
    MONGO_URI at it (admin-only). Runs as a background job; the app stays on the
    current DB until the user restarts, so a partial copy never loses data."""
    jid = _start_migration(request, body.target_uri, bool(body.overwrite),
                           bool(body.override_busy), label="Migrate data to a new database")
    return {"job_id": jid}


def _retry_migration(request: Request, job: dict, override_busy: bool = False) -> str:
    """POST /api/jobs/{id}/retry for a `migrate` job (registered in JOB_RETRY_HANDLERS).

    A retry is a NEW migration request, so it goes through exactly the same preflight and
    admission as POST /api/db-migrate: admin only, capability probe, "not this very
    database", non-empty-target guard, idle check, never two migrations at once. It keeps
    the original target and nothing else that was a choice:
      * `override_busy` (accepting a best-effort snapshot) must be repeated explicitly
        (`?override_busy=true`) for each attempt;
      * `overwrite` (replacing the target's existing data) is NEVER re-applied. It was a
        destructive confirmation for one particular attempt against whatever the target held
        then; the target may hold something else now (another application's data, or --
        because a migration copies the jobs table -- this very database), and a retry button
        offers no chance to confirm again. A retry therefore always runs with overwrite off:
        a non-empty target is refused and the user is told to start the switch again from
        Configuration > Database, where replacing data is asked for explicitly."""
    user = _current_user(request)
    if user and user.get("role") != "admin":
        raise HTTPException(403, "Only an admin can start a database migration.")
    params = job.get("params") or {}
    label = (job.get("label") or "Migrate data to a new database") + " (retry)"
    return _start_migration(request, params.get("target_uri"), False,
                            bool(override_busy), label=label, via_retry=True)


JOB_RETRY_HANDLERS["migrate"] = _retry_migration


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
