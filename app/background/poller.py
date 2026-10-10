"""The GitHub polling loop (`poller`), its per-repo sync step (`sync_repo`),
and the webhook signature/action-filter helpers shared by the GitHub/GitLab
webhook route handlers.

Moved out of main.py (Phase 4 of docs/internal/REFACTOR_PLAN.md). `poller` is started
exactly once per process by main.py's `@app.on_event("startup")` handler
(`threading.Thread(target=poller, daemon=True).start()`) — this module only
defines the loop, it does not start any threads itself.

The `/api/webhook/*` route handlers stay in main.py until Phase 6 (this phase
moves only the logic they call — signature verification and the accepted-
action sets — so that later extraction is a thin wrapper, per
docs/internal/REFACTOR_PLAN.md section 12 item 4). main.py re-imports `_ACCEPTED_GH_ACTIONS`,
`_ACCEPTED_GL_ACTIONS`, and `_verify_github_signature` from this module.

Signature logic is kept byte-identical to the original — `hmac.compare_digest`
is a constant-time comparison; do not "simplify" it to `==`.
"""
import hashlib
import hmac
import time

import github

from core.config import GITHUB_API
from core.deps import _oid, current_poll_interval, project_github_token
from core.state import SYNC, store  # noqa: F401  (bare name-imports are safe:
                                     # both are mutated in place, never rebound)

from workers.code_coverage_worker import ingest_pr_tracked


def sync_repo(rid: str):
    repo = next((r for r in store.repos.find({"_id": _oid(rid)})), None)
    if not repo:
        return
    repo = {**repo, "id": str(repo["_id"])}
    provider = (repo.get("git_provider") or "github").lower()
    if provider != "github":
        # GitLab MR polling is webhook-driven; skip in the poller.
        return
    try:
        token = project_github_token(repo.get("project_id"))
        # Ingest ALL PRs (including already-merged ones) — a feature may have
        # merged PRs from before it was tracked in wardenIQ. Users can exclude
        # individual PRs from Gap Analysis afterwards (see set_pr_excluded).
        pulls = github.GitHub(token, GITHUB_API).list_pulls(
            repo["owner"], repo["name"], state="all", per_page=30)
    except Exception as e:  # noqa: BLE001
        SYNC["errors"].append(f"{repo['full_name']} list: {e}")
        return
    last = repo.get("last_synced", 0)
    newest = last
    for pr in pulls:
        upd = _ts(pr.get("updated_at"))
        if upd <= last:
            continue
        ingest_pr_tracked(repo, pr)
        newest = max(newest, upd)
    store.set_repo_synced(repo["id"], newest)


def _ts(iso):
    if not iso:
        return 0
    try:
        from datetime import datetime
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except Exception:  # noqa: BLE001
        return 0


def poller():
    while True:
        # Resolved each loop so an in-app change to the interval takes effect next cycle.
        time.sleep(current_poll_interval())
        try:
            SYNC["running"] = True
            for r in store.repos_watching():
                sync_repo(str(r["_id"]))
            SYNC["last"] = time.time()
        except Exception as e:  # noqa: BLE001
            SYNC["errors"].append(f"poller: {e}")
        finally:
            SYNC["running"] = False


_ACCEPTED_GH_ACTIONS = {"opened", "synchronize", "reopened"}
_ACCEPTED_GL_ACTIONS = {"open", "update", "reopen"}


def _verify_github_signature(secret: str, raw_body: bytes, sig_header: str) -> bool:
    if not secret or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)
