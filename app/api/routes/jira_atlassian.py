"""Jira/Confluence/Atlassian integration: settings-level Jira/Confluence browsing,
per-project Jira epic listing, connectivity test, outbound coverage sync-to-issue, and
the inbound Jira webhook (create a feature from a Jira issue).

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 7/20).
Handler bodies are unchanged aside from the ``@app.`` -> ``@router.`` decorator swap.

These 6 routes + 1 private helper (``_jira_text``) were NOT contiguous in the original
main.py — they lived in three separate places (the "atlassian helpers" block near the
GitHub/GitLab repo routes, a "jira_test"/"jira_sync" pair near the settings domain, and
a "Jira (inbound)" block near the outbound GitHub/GitLab webhook receivers). All three
are genuinely the same domain (Jira/Confluence integration), so they're consolidated
into one router file here rather than three, matching how the plan already groups
"settings/jira/repos_prs" together as one extraction step.

``GEN_TOTAL`` moved to core/config.py in this same commit (documented deviation, same
reasoning as the other core/config.py env-derived constants) because both main.py's own
generate-job code and this router's ``jira_webhook`` need it, and it was previously
defined ad-hoc in main.py with no shared home.
"""
import hmac

from fastapi import APIRouter, HTTPException, Request
from extract import chunk as chunk_doc

from core import state
from core.config import GEN_TOTAL, WEBHOOK_SECRET
from core.deps import _ext_error, jira_client
from core.logging_setup import get_logger
from core.state import store
from workers.registry import launch_job

log = get_logger("jira")

router = APIRouter()


# ---- atlassian helpers (settings-level creds) ------------------------------
@router.get("/api/atlassian/accessible-jira-projects")
def list_accessible_jira_projects():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured in Settings")
    try:
        projects = j.list_projects()
        for p in projects:
            p["in_use"] = bool(store.jira_project_in_use(p.get("key")))
        return {"projects": projects}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


@router.get("/api/atlassian/accessible-confluence-spaces")
def list_accessible_confluence_spaces():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira/Confluence not configured in Settings")
    try:
        return {"spaces": j.list_confluence_spaces()}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Confluence", e)


@router.get("/api/projects/{pid}/jira-issues")
def list_project_jira_issues(pid: str, exclude_feature_id: str | None = None):
    """Epics available to associate with a feature: every Epic in the linked Jira
    project MINUS any Epic already bound to a feature (1 Epic : 1 feature).
    `exclude_feature_id` keeps the epic already bound to that feature visible
    (so its own selection shows when editing / re-versioning)."""
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    project_key = (p.get("jira_project_key") or "").strip()
    if not project_key:
        return {"project_key": "", "issues": []}
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured in Settings")
    exclude_group = None
    if exclude_feature_id:
        f = store.get_feature(exclude_feature_id)
        if f:
            exclude_group = f.get("group_id", f.get("id"))
    try:
        epics = j.list_project_epics(project_key)
        bound = store.bound_epic_keys(pid, exclude_group_id=exclude_group)
        available = [e for e in epics if e.get("key") not in bound]
        return {"project_key": project_key, "issues": available}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


@router.post("/api/jira/test")
def jira_test():
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured (base URL, email, API token)")
    try:
        me = j.myself()
        return {"ok": True, "user": me.get("displayName") or me.get("emailAddress")}
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)


@router.post("/api/features/{fid}/jira-sync")
def jira_sync(fid: str):
    """Write the feature's current coverage + open PRs back to its Jira issue."""
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    key = f.get("key")
    if not key:
        raise HTTPException(400, "feature has no Jira key (set a ticket key on the feature)")
    j = jira_client()
    if not j.ok():
        raise HTTPException(400, "Jira not configured")
    cov_rep = store.feature_coverage_report(fid)
    open_prs = [p for p in store.list_prs(feature_id=fid) if p.get("state") == "open"]
    lines = [
        f"*wardenIQ* — feature *{f.get('name')}* (v{f.get('version', 1)})",
        f"Test cases: {cov_rep['total_test_cases']} · code coverage: {cov_rep['coverage_pct']}% "
        f"· automation: {cov_rep['dev_test_pct']}%",
        f"PRs mapped: {cov_rep['pr_count']} across {cov_rep['repos_touched']} repo(s); "
        f"{len(open_prs)} still open.",
    ]
    for p in open_prs[:10]:
        lines.append(f"- open PR #{p.get('number')} ({p.get('repo_full_name')}): {p.get('url')}")
    try:
        j.add_comment(key, "\n".join(lines))
    except Exception as e:  # noqa: BLE001
        raise _ext_error("Jira", e)
    return {"ok": True, "issue": key}


# --------------------------------------------------------------- Jira (inbound)
def _jira_text(desc):
    """Extract plain text from a Jira description (string, or Cloud ADF JSON)."""
    if not desc:
        return ""
    if isinstance(desc, str):
        return desc
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                out.append(node["text"])
            for v in node.get("content", []) or []:
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(desc)
    return "\n".join(out)


@router.post("/api/integrations/jira/webhook")
async def jira_webhook(request: Request):
    """Create a wardenIQ feature from a Jira issue. Wire via Jira Automation
    ('Send web request' on issue create/transition).

    Auth: requires WEBHOOK_SECRET, supplied ONLY in the `X-Webhook-Token` header
    (headers, unlike query strings, aren't captured in proxy/access logs). Comparison
    is constant-time. This endpoint creates features and launches generate jobs, so
    with no secret configured it refuses (rather than silently accepting
    unauthenticated writes)."""
    if not WEBHOOK_SECRET:
        log.warning("[jira-webhook] refused: WEBHOOK_SECRET not configured")
        raise HTTPException(503, "webhook receiver not configured (set WEBHOOK_SECRET)")
    supplied = request.headers.get("X-Webhook-Token", "") or ""
    if not hmac.compare_digest(supplied, WEBHOOK_SECRET):
        raise HTTPException(401, "bad token")
    payload = await request.json()
    issue = payload.get("issue", {}) if isinstance(payload, dict) else {}
    fields = issue.get("fields", {}) or {}
    key = issue.get("key") or payload.get("key")
    name = fields.get("summary") or key or "Jira issue"
    text = _jira_text(fields.get("description")) or name
    pid = store.get_or_default_project()
    if key and store.epic_bound_group(pid, key):
        raise HTTPException(409, f"Epic '{key}' is already associated with another feature")
    emb = state.embedder.embed(text[:2000])
    fid = store.create_feature(name, pid, [f"jira:{key}"], text, text[:600], emb, key=key)
    chunks = [{"source": f"jira:{key}", "chunk_index": i, "text": ch, "embedding": state.embedder.embed(ch)}
              for i, ch in enumerate(chunk_doc(text, max_chars=1200, overlap=150))]
    store.add_feature_chunks(fid, pid, chunks)
    launch_job("generate", {"feature_id": fid, "text": text, "focus": None, "total": GEN_TOTAL},
               label=f"Generate (Jira {key})", project_id=pid, feature_id=fid)
    return {"created_feature": fid, "jira_key": key, "name": name}
