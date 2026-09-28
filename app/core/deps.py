"""Cross-cutting request-time dependencies: GitHub/GitLab clients, the LLM and
embedder builders, and small repo/document helpers.

Moved out of main.py (Phase 2 of REFACTOR_PLAN.md).

CRITICAL — embedder wiring (see REFACTOR_PLAN.md section 2.6 and
core/state.py's docstring): `core/state.py` declares `embedder = None` as a
placeholder. This module populates it, as an import-time side effect, once
`current_embedder()` is defined below:

    state.embedder = current_embedder()

Every consumer of the live embedder (main.py's route handlers, and later the
workers extracted in Phase 3) must read `state.embedder` through the `state`
module object — never `from core.state import embedder` — because
`_reembed_worker` rebinds `state.embedder` at runtime when the admin switches
embedding models. A name-import would freeze a stale reference forever.
"""
import os
import re

import crypto
import extract as extractmod
import figma
import github
import gitlab as gitlab_mod
import jira
from bson import ObjectId
from embeddings import Embedder
from fastapi import HTTPException, Request
from llm import LLM

from core import state
from core.config import (
    EMBED_DIM, EMBED_MODEL, GEN_MODEL, GITHUB_API, GITHUB_TOKEN,
    MIN_POLL_INTERVAL, OLLAMA_URL_BUNDLED, POLL_INTERVAL_FALLBACK,
    PROVIDER_LOCK, _ENV_OLLAMA, _ENV_POLL,
)
from core.logging_setup import get_logger
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)

log = get_logger("deps")


def current_ollama_url() -> str:
    """Resolve the Ollama endpoint. Precedence: OLLAMA_URL in .env WINS (locked in
    the UI); else the value saved from the frontend (settings); else the bundled
    default. Read fresh so an in-app change applies immediately (no restart)."""
    if _ENV_OLLAMA:
        return _ENV_OLLAMA
    try:
        saved = (store.get_settings().get("ollama_url") or "").strip()
    except Exception:  # noqa: BLE001
        saved = ""
    return saved or OLLAMA_URL_BUNDLED


def current_poll_interval() -> int:
    """Resolve the GitHub poller cadence in seconds. Precedence: the value saved from
    the frontend (settings.poll_interval_s) WINS; else POLL_INTERVAL_SECONDS in .env;
    else the built-in 30-minute default. Read fresh so an in-app change applies on the
    next loop (no restart). Floored at MIN_POLL_INTERVAL so the API isn't hammered."""
    val = None
    try:
        saved = store.get_settings().get("poll_interval_s")
        if saved:
            val = int(saved)
    except Exception:  # noqa: BLE001
        val = None
    if val is None and _ENV_POLL:
        try:
            val = int(_ENV_POLL)
        except ValueError:
            val = None
    if val is None:
        val = POLL_INTERVAL_FALLBACK
    return max(MIN_POLL_INTERVAL, val)


def current_embedder() -> Embedder:
    """Build the embedding client from saved settings (local Ollama by default).
    Read fresh so a model switch takes effect for subsequent calls."""
    s = store.get_settings()
    # Embeddings are NOT hard-pinned by PROVIDER_LOCK — the admin chooses Bedrock or
    # the local bundled Ollama (both air-gapped-safe). We only clamp away internet
    # providers when a lock is active, so a locked install can never call out.
    provider = s.get("embed_provider") or "ollama"
    if PROVIDER_LOCK and provider not in ("ollama", PROVIDER_LOCK):
        provider = "ollama"
    key = crypto.decrypt(s.get("embed_api_key_enc", "")) if s.get("embed_api_key_enc") else ""
    return Embedder(provider=provider,
                    model=s.get("embed_model") or EMBED_MODEL,
                    dim=int(s.get("embed_dim") or EMBED_DIM),
                    api_key=key, base_url=s.get("embed_base_url", ""), ollama_url=current_ollama_url(),
                    region=s.get("embed_region", ""))


# Align the store's index dimension with the saved embedding model, then build the
# active embedder. (Indexes for an already-switched model exist at the right dim,
# so Store.__init__'s _ensure_vector left them untouched.)
_saved_embed = store.get_settings()
if _saved_embed.get("embed_dim"):
    store.dim = int(_saved_embed["embed_dim"])
state.embedder = current_embedder()


def current_llm() -> LLM:
    """Build the LLM client from saved settings (local Ollama by default, or a
    hosted provider with an API key). Read fresh each call so config changes apply."""
    s = store.get_settings()
    provider = PROVIDER_LOCK or s.get("llm_provider", "ollama")
    key = crypto.decrypt(s.get("llm_api_key_enc", "")) if s.get("llm_api_key_enc") else ""
    return LLM(provider=provider, model=(s.get("llm_model") or GEN_MODEL),
               api_key=key, base_url=s.get("llm_base_url", ""), ollama_url=current_ollama_url(),
               region=s.get("llm_region", ""))


def project_github_token(pid: str) -> str:
    """Project-level GitHub PAT (encrypted at rest). Falls back to env for compat."""
    enc = store.get_project_github_pat_enc(pid)
    return (crypto.decrypt(enc) if enc else "") or GITHUB_TOKEN


def project_gitlab_token(pid: str) -> str:
    enc = store.get_project_gitlab_pat_enc(pid)
    return crypto.decrypt(enc) if enc else ""


def gh_client_for_project(pid: str) -> github.GitHub:
    return github.GitHub(project_github_token(pid), GITHUB_API)


def gl_client_for_project(pid: str) -> "gitlab_mod.GitLab":
    return gitlab_mod.GitLab(project_gitlab_token(pid))


def gh_client_with_token(token: str) -> github.GitHub:
    return github.GitHub(token or GITHUB_TOKEN, GITHUB_API)


# Back-compat aliases (older code paths reference these names).
def current_token() -> str:
    return GITHUB_TOKEN


def gh_client() -> github.GitHub:
    return github.GitHub(GITHUB_TOKEN, GITHUB_API)


gh = github.GitHub(GITHUB_TOKEN, GITHUB_API)


def _provider_client(repo: dict):
    provider = (repo.get("git_provider") or "github").lower()
    pid = repo.get("project_id")
    if provider == "gitlab":
        token = project_gitlab_token(pid)
        if not token:
            raise RuntimeError("no GitLab PAT configured for this project")
        return provider, gitlab_mod.GitLab(token)
    token = project_github_token(pid)
    if not token:
        raise RuntimeError("no GitHub PAT configured for this project")
    return provider, github.GitHub(token, GITHUB_API)


def _repo_list_commits(repo: dict, since_iso: str, ref: str = "", per_page: int = 50):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.list_commits(repo["full_name"], since_iso, per_page=per_page, ref=ref)
    return client.list_commits(repo["owner"], repo["name"], since_iso, per_page=per_page, ref=ref)


def _repo_get_commit(repo: dict, sha: str, max_files: int = 40):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.get_commit(repo["full_name"], sha, max_files=max_files)
    return client.get_commit(repo["owner"], repo["name"], sha, max_files=max_files)


def _repo_branch_sha(repo: dict, ref: str):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.branch_sha(repo["full_name"], ref)
    return client.branch_sha(repo["owner"], repo["name"], ref)


def _repo_get_archive(repo: dict, ref: str = ""):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.get_archive(repo["full_name"], ref)
    return client.get_archive(repo["owner"], repo["name"], ref)


def _fetch_repo_snapshot_files(repo: dict, ref: str = "") -> list:
    """Whole-repo file snapshot for the deterministic cross-file dependency layer
    (app/contracts.py) — the SAME archive-fetch mechanism `_codeanalysis_worker` (Mind Map)
    already uses (`_repo_get_archive` + `extractmod.source_files_from_tar`), reused here so
    PR Code Coverage (`_pr_coverage`) and Code Analysis (`_analyze_worker`) can also see
    consumers of a changed contract that live OUTSIDE a PR's/commit's own diff — the
    structural gap `contracts.build_contract_breaks` exists to close (see
    WARDENIQ_CROSS_FILE_BEFORE_AFTER.md).

    Best-effort and defensive by design: any failure (no PAT configured, network error, rate
    limit, archive too large) returns `[]` rather than raising, so a fetch problem degrades to
    the ORIGINAL diff-only behaviour instead of failing the whole coverage/analysis run — the
    same "evidence, never a hard dependency" posture `contracts.py` itself documents.
    """
    try:
        data = _repo_get_archive(repo, ref or repo.get("default_branch", ""))
        files, _stats = extractmod.source_files_from_tar(data, return_stats=True)
        return [{"path": p, "text": t} for p, t in files]
    except Exception as e:  # noqa: BLE001
        log.warning("[contracts] repo snapshot fetch failed for %s: %s",
                  repo.get("full_name"), e)
        return []


def _repo_list_branches(repo: dict):
    provider, client = _provider_client(repo)
    if provider == "gitlab":
        return client.list_branches(repo["full_name"])
    return client.list_branches(repo["owner"], repo["name"])


def _is_app_repo(repo: dict | None) -> bool:
    return bool(repo) and (repo.get("repo_type") or "app") == "app"


def _oid(s):
    # Not in REFACTOR_PLAN.md's explicit deps.py list, but moved here (rather than
    # left in main.py) because _implementation_repo_docs (below, which IS listed)
    # needs it, and main.py importing it back from core.deps avoids a main<->deps
    # circular import. main.py still uses _oid extensively for its own route
    # handlers (Phase 6 concern) via `from core.deps import _oid`.
    return ObjectId(s)


def _implementation_repo_docs(project_id: str, repo_ids=None):
    """Implementation repos only.

    Test repos are reserved for automation coverage and must not participate in
    commit analysis, code coverage / mind map, or code generation flows.
    """
    repo_ids = repo_ids or []
    if repo_ids:
        docs = [store.repos.find_one({"_id": _oid(r)}) for r in repo_ids]
    else:
        docs = list(store.repos.find({"project_id": project_id, "repo_type": "app"}))
    return [r for r in docs if _is_app_repo(r)]


def jira_client():
    # Not in REFACTOR_PLAN.md's explicit deps.py list, but moved here (Phase 3,
    # documented deviation — same reasoning as `_oid` above) because `ingest_pr`
    # / `_pr_coverage` (app/workers/code_coverage_worker.py) need it, and that
    # module importing it back from main.py would create a main<->workers
    # circular import. main.py still uses `jira_client` extensively for its own
    # route handlers (jira_sync, jira_test, etc. — Phase 6 concern) via
    # `from core.deps import jira_client`.
    s = store.get_settings()
    return jira.Jira(s.get("jira_base_url", ""), s.get("jira_email", ""),
                     crypto.decrypt(s.get("jira_api_token_enc", "")))


def _fallback_feature_summary(name: str, raw: str) -> str:
    # Not in REFACTOR_PLAN.md's explicit deps.py list, but moved here (Phase 3,
    # documented deviation — same reasoning as `_oid`/`jira_client` above)
    # because `_generate_feature_summary` (below) needs it, and `_ingest_worker`
    # (app/workers/generation.py) needs `_generate_feature_summary`. Keeping
    # this trio here — rather than in workers/generation.py — lets main.py's
    # own route handlers (`create_feature`, `_display_feature_summary`, the
    # new-version endpoint — all Phase 6 concerns, still in main.py) import
    # them back from core.deps too, without a main<->workers circular import
    # either way.
    original = str(raw or "")
    lower_original = original.lower()
    if "profile" in lower_original and "event" in lower_original and ("join" in lower_original or "create" in lower_original):
        return (
            "Users can join or create events while completing required profile information inline. "
            "The feature gates event actions on required profile fields, shows clear prompts or errors, "
            "and avoids forcing users through a separate onboarding flow."
        )
    def clean_piece(value: str) -> str:
        value = re.sub(r"###\s*(?:Document|Uploaded Documents?|Pasted requirement)\s*:?.*?(?=\n|$)", " ", value, flags=re.I)
        value = re.sub(r"\b[\w.-]+\.(?:pdf|docx?|md|txt|markdown)\b", " ", value, flags=re.I)
        value = re.sub(r"\b(?:PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}", " ", value, flags=re.I)
        value = re.sub(r"\b(?:PRD|HLD|LLD)\b\s*:?", " ", value, flags=re.I)
        return " ".join(value.replace("#", " ").split())

    raw_lines = [clean_piece(x) for x in original.splitlines()]
    product_terms = re.compile(r"\b(user|customer|profile|event|join|create|select|submit|validate|must|should|required|allow|prevent|display|error)\b", re.I)
    bad_terms = re.compile(r"\b(architecture|monolith|database|table|redis|queue|deployment|module|component|system overview)\b", re.I)
    candidates = []
    for line in raw_lines:
        if 60 <= len(line) <= 360 and product_terms.search(line) and not bad_terms.search(line):
            candidates.append(line)
        if len(candidates) >= 2:
            break
    if candidates:
        clean = " ".join(candidates)
    else:
        clean = clean_piece(original)
    if len(clean) > 260:
        clean = clean[:260].rsplit(" ", 1)[0] + "…"
    return clean or f"{name} is ready for QA review with generated test coverage."


def _generate_feature_summary(name: str, raw: str) -> str:
    """Generate a clean product summary for UI/reporting; never block creation."""
    prompt = f"""
Create a clean feature summary for a QA workspace.

Rules:
- 2 to 3 concise sentences.
- Describe product/user behavior, not document filenames.
- Do not mention PRD, HLD, LLD, source document, uploaded file, or markdown headings.
- Do not include test-case counts.
- Return JSON only: {{"summary": "..."}}

Feature name: {name}

Evidence:
{(raw or '')[:6000]}
""".strip()
    try:
        data = current_llm().chat_json(
            "You write concise feature summaries for QA managers.",
            prompt,
            temperature=0.1,
        )
        summary = " ".join(str((data or {}).get("summary") or "").split()).strip()
        if summary and len(summary) >= 40:
            return summary[:700]
    except Exception:  # noqa: BLE001
        pass
    return _fallback_feature_summary(name, raw)


def _gather_external(parts, sources, *, figma_urls=(), pdf_figma=(), confluence_urls=(),
                     confluence_children=True, crawl_seeds=(), jid=None):
    """Fetch external evidence (multiple Figma designs, multiple Confluence pages +
    children, and non-Figma links) and append it to `parts`/`sources` in place.
    Best-effort: a source that fails is skipped and recorded in the returned
    warnings list. Returns (figma_data, warnings). Shared by the ingest worker
    (background, with progress) and the new-version endpoint (synchronous)."""
    def prog(stage, pct):
        if jid:
            store.update_job_progress(jid, stage, pct)

    warnings = []
    figma_data = None

    # ---- Figma designs (explicit links + figma.com links found in PDFs) ----
    figma_keys = []
    for u in list(figma_urls) + list(pdf_figma):
        k = figma.Figma.file_key_from_url(u)
        if k:
            figma_keys.append(k)
    figma_keys = list(dict.fromkeys(figma_keys))
    if figma_keys:
        prog(f"Reading {len(figma_keys)} Figma design(s)", 8)
        fc = figma_client()
        summaries = []
        if fc.ok():
            for k in figma_keys:
                try:
                    summaries.append(fc.read_design(k))
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"Figma {k}: {e}")
        figma_data = figma.Figma.merge_summaries(summaries)
        if figma_data:
            scr = "; ".join(s.get("name", "") for s in (figma_data.get("sampleScreens") or [])[:20])
            uitext = " | ".join((figma_data.get("textBlocks") or [])[:60])
            parts.append(f"### Document: Figma — {figma_data.get('fileName', 'design')}\n"
                         f"Screens: {scr}\nUI text: {uitext}")
            sources.append("figma")

    # ---- Confluence pages (each with its child pages) ----
    confluence_urls = list(confluence_urls)
    if confluence_urls:
        prog(f"Reading {len(confluence_urls)} Confluence page(s)", 20)
        j = jira_client()
        if j.ok():
            for url in confluence_urls:
                page_id = extractmod.confluence_page_id_from_url(url)
                if not page_id:
                    warnings.append(f"Confluence: unreadable link {url[:60]}")
                    continue
                try:
                    page = j.get_confluence_page(page_id)
                    ptxt = extractmod.html_to_text(page.get("html", ""))
                    if ptxt.strip():
                        parts.append(f"### Document: Confluence — {page.get('title', 'page')}\n{ptxt}")
                        sources.append(f"confluence:{page.get('id')}")
                    if confluence_children:
                        for child in j.get_confluence_children(page_id):
                            cp = j.get_confluence_page(child["id"])
                            ctxt = extractmod.html_to_text(cp.get("html", ""))
                            if ctxt.strip():
                                parts.append(f"### Document: Confluence — {cp.get('title', 'subpage')}\n{ctxt}")
                                sources.append(f"confluence:{cp.get('id')}")
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"Confluence {page_id}: {e}")

    # ---- Follow the remaining (non-Figma) links ----
    crawl_seeds = list(dict.fromkeys(crawl_seeds))
    if crawl_seeds:
        prog("Following linked pages", 30)
        import weblinks
        try:
            for pg in weblinks.crawl(crawl_seeds):
                parts.append(f"### Document: Linked page — {pg['url']}\n{pg['text'][:20000]}")
                sources.append(f"link:{pg['url'][:80]}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Link crawl: {e}")

    return figma_data, warnings


def figma_client():
    # Not in REFACTOR_PLAN.md's explicit deps.py list, but moved here (Phase 3,
    # documented deviation) alongside `_gather_external` above, which needs it.
    # main.py's own figma-related route handlers keep using it via
    # `from core.deps import figma_client`.
    s = store.get_settings()
    return figma.Figma(crypto.decrypt(s.get("figma_api_token_enc", "")))


def _webhook_base_url(request: Request | None = None) -> str:
    """Pick the public API base URL for webhooks. Honors env first, falls back
    to the inbound request's host."""
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("API_BASE_URL") or "").rstrip("/")
    if base:
        return base
    if request is not None:
        # `request.base_url` ends with `/`.
        base_url = getattr(request, "base_url", None)
        if base_url:
            return str(base_url).rstrip("/")
    return ""


def _write_env_var(path: str, key: str, value: str):
    """Upsert `KEY=value` in a .env file, preserving all other lines and comments.
    Only an ACTIVE assignment is replaced; commented example lines are left intact.
    Returns (ok, error).

    Not in REFACTOR_PLAN.md's explicit deps.py list, but moved here (Phase 3,
    documented deviation, same reasoning as the helpers above) because
    `_migrate_worker` (app/workers/generation.py) needs it, and several of
    main.py's own route handlers (settings, DB-migration endpoints — Phase 6
    concerns) keep using it via `from core.deps import _write_env_var`.
    """
    # Guard against .env line injection: a value (or key) containing CR/LF would
    # otherwise be written as-is and split into extra lines, letting a caller
    # smuggle additional KEY=value assignments into the file (e.g. a Mongo URI
    # like "mongodb://h/db\nALLOW_WEAK_SECRET=true"). Reject any embedded newline
    # outright rather than silently stripping, so the caller sees a clear error.
    for part_name, part in (("key", key), ("value", value)):
        if any(ch in str(part) for ch in ("\n", "\r", "\x00")):
            return False, f"illegal newline or null byte in .env {part_name}"
    try:
        lines = []
        if os.path.exists(path):
            with open(path, "r") as f:
                lines = f.read().splitlines()
        prefix = key + "="
        out, found = [], False
        for ln in lines:
            if ln.lstrip().startswith(prefix):
                out.append(f"{key}={value}"); found = True
            else:
                out.append(ln)
        if not found:
            out.append(f"{key}={value}")
        with open(path, "w") as f:
            f.write("\n".join(out) + "\n")
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# Phase 6 (REFACTOR_PLAN.md): _smtp_cfg_from_env/_smtp_cfg/_user_public moved here
# (documented deviation, same reasoning as _oid/jira_client above) because both the
# api/routes/auth.py router AND the api/routes/users.py router (_issue_invite_link,
# invite_user, resend-invite) call them. Moving to core/deps.py avoids either
# duplicating the logic or having one router import from another (which the plan
# explicitly forbids, to prevent cycles).
def _smtp_cfg_from_env():
    """SMTP config from environment variables, if SMTP_HOST is set.

    This lets an operator configure email delivery entirely from .env so OTP emails
    work from first boot — no in-app setup, and the password is never encrypted with
    APP_SECRET (so rotating APP_SECRET can't break email). Env takes precedence over
    the in-app (DB) config below.
    """
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        return None
    port_raw = (os.getenv("SMTP_PORT") or "").strip()
    ssl_flag = (os.getenv("SMTP_SSL", "false").strip().lower() == "true")
    tls_flag = (os.getenv("SMTP_TLS", "true").strip().lower() == "true")
    # Normalize the password: Gmail shows App Passwords as "abcd efgh ijkl mnop" for
    # readability, but the real secret is 16 chars with NO spaces. Leaving spaces in
    # is the #1 cause of Gmail's "535 Username and Password not accepted". Always trim
    # ends; for Gmail, strip all internal whitespace too.
    raw_pass = (os.getenv("SMTP_PASS") or "").strip()
    is_gmail = host.lower().endswith(("gmail.com", "googlemail.com"))
    if is_gmail:
        password = re.sub(r"\s+", "", raw_pass)
        # Gmail App Passwords are exactly 16 chars. A wrong length is a config error
        # that would otherwise surface as an opaque "535 BadCredentials" — warn early.
        if password and len(password) != 16:
            log.warning("[SMTP] SMTP_PASS is %d chars after removing spaces, but a "
                      "Gmail App Password must be exactly 16. Gmail will reject this "
                      "with 535 BadCredentials. Re-copy the 16-char App Password from "
                      "Google → Security → App passwords.", len(password))
    else:
        password = raw_pass
    return {
        "host": host,
        "port": int(port_raw) if port_raw.isdigit() else (465 if ssl_flag else 587),
        "user": (os.getenv("SMTP_USER") or "").strip(),
        "password": password,
        "from": (os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "").strip(),
        "tls": tls_flag,
        "ssl": ssl_flag,
    }


def _smtp_cfg():
    # In-app SMTP (saved in the DB) takes precedence when configured — "what you set in
    # the app is what's used". .env SMTP is the FALLBACK: it bootstraps OTP email for the
    # very first admin login (before anyone can sign in to configure it in-app), and it
    # covers the case where the DB value can't be decrypted (e.g. after APP_SECRET rotation).
    s = store.get_settings()
    if s.get("smtp_host"):
        pw = ""
        if s.get("smtp_pass_enc"):
            pw = crypto.decrypt(s.get("smtp_pass_enc", ""))
            # crypto.decrypt() swallows its own failures and returns "" rather than
            # raising — so we can't catch an exception here. But crypto.encrypt() only
            # ever produces "" from an empty plaintext, so a non-empty smtp_pass_enc
            # that decrypts to "" can only mean the key no longer matches (APP_SECRET
            # rotated) — treat that as unreadable and fall back to .env, same as if
            # decrypt() had raised.
            if not pw:
                pw = None
        if pw is not None:
            return {"host": s.get("smtp_host"), "port": s.get("smtp_port"),
                    "user": s.get("smtp_user"), "password": pw,
                    "from": s.get("smtp_from"), "tls": s.get("smtp_tls", True),
                    "ssl": s.get("smtp_ssl", False)}
    # No usable in-app SMTP → fall back to environment (.env) config, if any.
    return _smtp_cfg_from_env()


def _user_public(u):
    return {"id": u["id"], "email": u["email"], "name": u.get("name"),
            "role": u.get("role", "viewer"), "active": u.get("active", True),
            "created_at": u.get("created_at"), "last_login": u.get("last_login"),
            "invite_status": u.get("invite_status", "active"),
            "invited_at": u.get("invited_at"),
            "all_projects": u.get("all_projects", True),
            "project_ids": u.get("project_ids", []),
            # True only for the local "admin" bootstrap account while it's still on
            # the shipped default password — drives the mandatory change-password
            # prompt on first login. Always False for email-based accounts (they
            # sign in with a one-time code and have no password at all).
            "must_change_password": u.get("email") == "admin" and not bool(u.get("password_hash"))}


# Phase 6 (REFACTOR_PLAN.md): _svc_error/_ext_error moved here (documented deviation,
# same reasoning as the other core/deps.py helpers above) because they're called from
# a dozen-plus still-in-main.py routes across many not-yet-extracted domains (GitHub,
# GitLab, Jira, Confluence, validator, embeddings, ...) as well as the new
# api/routes/settings.py router's llm_test. Keeping them in exactly one
# not-yet-extracted router would force every other caller to import from that router,
# which the plan explicitly forbids (to prevent router-to-router cycles).
def _svc_error(prefix, e, code=500):
    """Log an internal exception server-side and return a generic HTTPException.
    Prevents raw stack/exception text (which can reveal internals) reaching clients."""
    if isinstance(e, HTTPException):
        return e   # already a clean, intentional status/message — pass through
    log.error("[%s] %r", prefix, e)
    return HTTPException(code, f"{prefix} failed — please try again or check the logs")


def _ext_error(prefix, e):
    """Map an external-service exception to a clean, user-facing HTTPException (no raw
    httpx URLs / MDN links reaching the UI)."""
    import httpx as _hx
    if isinstance(e, _hx.HTTPStatusError):
        sc = e.response.status_code
        table = {
            400: (400, "the request was rejected — check the link or id"),
            401: (400, "authentication failed — check the token in Configuration"),
            403: (403, "access denied — the token lacks permission for this resource"),
            404: (404, "not found — check the link is correct and the token can access it"),
            429: (429, "rate limited — please try again shortly"),
        }
        code, msg = table.get(sc, (502, f"service returned HTTP {sc}"))
    elif isinstance(e, _hx.RequestError):
        code, msg = 502, "could not reach the service (network or timeout)"
    else:
        # Never reflect a raw exception (may carry internal URLs, hostnames, provider
        # errors, or credential hints). Log the detail server-side; return a safe message.
        log.error("[ext-error] %s: %r", prefix, e)
        code, msg = 502, "the request failed unexpectedly — see server logs for details"
    return HTTPException(code, f"{prefix}: {msg}")
