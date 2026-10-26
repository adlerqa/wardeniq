"""Inbound GitHub/GitLab webhook receivers: verify the request's signature/token
against each registered repo's own webhook secret, then kick off PR/MR coverage
ingestion (``ingest_pr_tracked``) in a background thread per matching project.

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router 18/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator
swap. The inbound Jira webhook was already grouped with
``api/routes/jira_atlassian.py`` in an earlier router (a documented deviation
from the plan's "webhooks.py (jira, github, gitlab)" grouping) — see that
router's docstring; nothing further to do here.

Signature verification (GitHub HMAC via ``hmac.compare_digest``, GitLab
shared-token comparison) is a security boundary and moves verbatim, per
docs/internal/REFACTOR_PLAN.md section 4 ("not a cleanup opportunity"). No new shared-helper
deviation was needed: ``_ACCEPTED_GH_ACTIONS``/``_ACCEPTED_GL_ACTIONS``/
``_verify_github_signature`` (background/poller.py) and ``ingest_pr_tracked``
(workers/code_coverage_worker.py) were already centralized in earlier phases.
"""
import hmac
import json
import threading

from fastapi import APIRouter, Request

from background.poller import _ACCEPTED_GH_ACTIONS, _ACCEPTED_GL_ACTIONS, _verify_github_signature
from core.config import WEBHOOK_SECRET
from core.exceptions import MigrationInProgress
from core.logging_setup import get_logger
from core.state import store
from workers.code_coverage_worker import ingest_pr_tracked
import crypto

router = APIRouter()
log = get_logger("webhooks")


def _ingest_pr_in_thread(repo, pr):
    """Thread target for webhook-driven ingestion. While a database migration is running
    new background work is refused (#111); for a webhook that means the event is dropped,
    so say so explicitly instead of dying with an unhandled thread traceback. (GitHub PRs
    are picked up again by the next poll; GitLab MRs are webhook-driven only, so that
    event needs a manual redelivery.)"""
    try:
        ingest_pr_tracked(repo, pr)
    except MigrationInProgress:
        log.warning("[webhook] PR/MR event for %s dropped: a database migration is in "
                    "progress. Redeliver it once the migration has finished.",
                    (repo or {}).get("full_name", "?"))


@router.post("/api/webhook/github")
async def github_webhook(request: Request):
    """Per-repo secret webhook. Verifies HMAC against each registered repo's
    own webhook secret; fans the event out to all matching projects."""
    body = await request.body()
    event = request.headers.get("X-GitHub-Event", "")
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if event != "pull_request":
        # Drop opaquely (200 so we don't leak which events we accept).
        return {"ok": True}
    try:
        payload = json.loads(body or b"{}")
    except Exception:  # noqa: BLE001
        return {"ok": True}
    action = payload.get("action", "")
    if action not in _ACCEPTED_GH_ACTIONS:
        return {"ok": True}
    full = (payload.get("repository") or {}).get("full_name", "")
    if not full:
        return {"ok": True}
    candidates = store.repos_by_fullname_app(full, git_provider="github")
    if not candidates:
        # Legacy fallback: try env secret + single repo lookup.
        if WEBHOOK_SECRET and _verify_github_signature(WEBHOOK_SECRET, body, sig_header):
            repo = store.repo_by_fullname(full)
            if repo:
                threading.Thread(target=_ingest_pr_in_thread, args=(repo, payload.get("pull_request", {})),
                                 daemon=True).start()
                return {"handled": True, "repo": full}
        return {"ok": True}
    verified = []
    for c in candidates:
        enc = c.get("webhook_secret_enc") or ""
        secret = crypto.decrypt(enc) if enc else ""
        if secret and _verify_github_signature(secret, body, sig_header):
            verified.append(c)
    if not verified:
        return {"ok": True}
    seen = set()
    for repo in verified:
        if repo["project_id"] in seen:
            continue
        seen.add(repo["project_id"])
        threading.Thread(target=_ingest_pr_in_thread, args=(repo, payload.get("pull_request", {})),
                         daemon=True).start()
    return {"handled": True, "projects": len(seen), "repo": full}


@router.post("/api/webhook/gitlab")
async def gitlab_webhook(request: Request):
    """GitLab uses a shared `X-Gitlab-Token` header (no HMAC). We compare it
    against the per-repo encrypted secret stored at connect time."""
    body = await request.body()
    token_header = request.headers.get("X-Gitlab-Token", "") or ""
    event = request.headers.get("X-Gitlab-Event", "")
    if "Merge Request Hook" not in event and event != "Merge Request Hook":
        return {"ok": True}
    try:
        payload = json.loads(body or b"{}")
    except Exception:  # noqa: BLE001
        return {"ok": True}
    attrs = payload.get("object_attributes") or {}
    action = attrs.get("action") or ""
    if action not in _ACCEPTED_GL_ACTIONS:
        return {"ok": True}
    full = (payload.get("project") or {}).get("path_with_namespace") or ""
    if not full:
        return {"ok": True}
    candidates = store.repos_by_fullname_app(full, git_provider="gitlab")
    verified = []
    for c in candidates:
        enc = c.get("webhook_secret_enc") or ""
        secret = crypto.decrypt(enc) if enc else ""
        if secret and hmac.compare_digest(secret, token_header):
            verified.append(c)
    if not verified:
        return {"ok": True}
    # Translate the MR payload into the same shape ingest_pr expects.
    iid = attrs.get("iid")
    pseudo_pr = {
        "number": iid,
        "title": attrs.get("title") or "",
        "user": {"login": (payload.get("user") or {}).get("username") or ""},
        "head": {"ref": attrs.get("source_branch") or ""},
        "state": "merged" if action == "merge" else attrs.get("state") or "open",
        "html_url": attrs.get("url") or "",
        "body": attrs.get("description") or "",
        "updated_at": attrs.get("updated_at") or "",
        "merged_at": attrs.get("merged_at") or None,
    }
    seen = set()
    for repo in verified:
        if repo["project_id"] in seen:
            continue
        seen.add(repo["project_id"])
        threading.Thread(target=_ingest_pr_in_thread, args=(repo, pseudo_pr), daemon=True).start()
    return {"handled": True, "projects": len(seen), "repo": full}
