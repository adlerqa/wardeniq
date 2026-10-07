"""User management + invite lifecycle routes.

Extracted from app/main.py (REFACTOR_PLAN.md section 14, Phase 6, router 5/20 —
grouped with auth.py as "security-sensitive"). Handler bodies are unchanged
aside from the ``@app.`` -> ``@router.`` decorator swap.

Shared with still-in-main.py code (documented deviation, same reasoning as
auth.py's move of _smtp_cfg/_user_public): _webhook_base_url, _smtp_cfg, and
_user_public already live in core/deps.py; APP_WORKSPACE_NAME in core/config.py.
Nothing defined in this file is (yet) needed elsewhere, so no new symbols were
promoted to core/deps.py or api/schemas.py for this router.
"""
import os
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import auth
import email_send
from core.audit import _audit
from core.config import APP_WORKSPACE_NAME
from core.deps import _smtp_cfg, _user_public, _webhook_base_url
from core.logging_setup import get_logger
from core.security import _current_user
from core.state import store

log = get_logger("users")

router = APIRouter()


@router.get("/api/users")
def list_users():
    return {"users": [_user_public(u) for u in store.list_users()]}


class UserIn(BaseModel):
    email: str
    name: str | None = None
    role: str = "viewer"
    # Project access: all_projects=True (default) grants every project; otherwise the
    # user is limited to project_ids. Admins always have all projects regardless.
    all_projects: bool = True
    project_ids: list[str] = []


INVITE_TTL = int(os.getenv("INVITE_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days


def _issue_invite_link(u, request=None, inviter_name=""):
    """Generate a single-use, time-limited invite TOKEN and email an invite LINK
    (NOT a login OTP — the two are separate now, so a later login can't overwrite the
    invite). Returns ((delivery_mode, detail), token).

    delivery_mode: 'sent' (emailed) | 'refused' (no SMTP) | 'error' (send failed).
    The invite link is never logged or returned over the network.
    """
    token = auth.gen_invite_token()
    store.set_invite_token(u["id"], auth.hash_token(token), time.time() + INVITE_TTL)
    base = _webhook_base_url(request)
    link = f"{base}/invite?token={token}" if base else f"/invite?token={token}"
    cfg = _smtp_cfg()
    if not cfg:
        log.warning("[invite refused] SMTP not configured for %s", u["email"])
        return ("refused", "smtp not configured"), token
    ok, err = email_send.send_invite(
        cfg, u["email"], link, inviter=inviter_name,
        role=u.get("role", "viewer"), workspace=APP_WORKSPACE_NAME,
        recipient_name=u.get("name") or "")
    if ok:
        return ("sent", link), token
    log.warning("invite send failed for %s: %s", u["email"], err)
    return ("error", err), token


@router.post("/api/users")
def invite_user(body: UserIn, request: Request):
    email = (body.email or "").strip().lower()
    if not auth.is_valid_email(email):
        raise HTTPException(400, "a valid email is required")
    if store.get_user_by_email(email):
        raise HTTPException(409, "a user with that email already exists")
    role = body.role if body.role in auth.ROLES else "viewer"
    me = _current_user(request)
    # Admins implicitly have all projects; for others honor the selection. Validate
    # that any specified project ids actually exist.
    all_projects = True if role == "admin" else bool(body.all_projects)
    project_ids = [] if all_projects else [p for p in (body.project_ids or []) if store.get_project(p)]
    if not all_projects and not project_ids:
        raise HTTPException(400, "select at least one project, or grant access to all projects")
    u = store.create_user(email, (body.name or email.split("@")[0]), role,
                          invite_status="pending",
                          invited_by=(me.get("id") if me else None),
                          all_projects=all_projects, project_ids=project_ids)
    _audit(request, "user.invited", target=email,
           new={"role": role, "all_projects": all_projects, "project_ids": project_ids})
    (mode, detail), token = _issue_invite_link(
        u, request, inviter_name=(me.get("name") or me.get("email")) if me else "")
    # Report delivery honestly. A failed/absent email must NOT be reported as sent,
    # but the user is still created (admin can resend once SMTP is fixed).
    resp = {"user": _user_public(store.get_user(u["id"])), "delivery": mode}
    if mode == "sent":
        resp["message"] = f"Invite sent — an invitation link was emailed to {email}."
    elif mode == "refused":
        resp["message"] = ("User created, but no invitation email was sent: SMTP is "
                           "not configured. Configure email, then use Resend.")
    else:  # error
        resp["message"] = ("User created, but the invitation email failed to send. "
                           "Check the SMTP configuration and use Resend.")
    return resp


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    name: str | None = None
    all_projects: bool | None = None
    project_ids: list[str] | None = None


@router.patch("/api/users/{uid}")
def patch_user(uid: str, body: UserPatch, request: Request):
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    upd = {}
    if body.name is not None:
        upd["name"] = body.name
    if body.role is not None and body.role in auth.ROLES:
        upd["role"] = body.role
    if body.active is not None:
        upd["active"] = body.active
    # Don't let the last active admin be demoted or disabled (lockout guard).
    demoting = (upd.get("role") and upd["role"] != "admin") or (upd.get("active") is False)
    if target.get("role") == "admin" and target.get("active") and demoting \
            and store.count_active_admins() <= 1:
        raise HTTPException(400, "cannot demote or disable the last active admin")
    # Project access change. An admin always has all projects, so if the resulting
    # role is admin we force all_projects. Otherwise honor the payload.
    projects_changed = body.all_projects is not None or body.project_ids is not None
    if projects_changed:
        result_role = upd.get("role", target.get("role"))
        if result_role == "admin":
            all_proj, pids = True, []
        else:
            all_proj = target.get("all_projects", True) if body.all_projects is None else bool(body.all_projects)
            pids = ([] if all_proj
                    else [p for p in (body.project_ids if body.project_ids is not None
                                      else target.get("project_ids", [])) if store.get_project(p)])
            if not all_proj and not pids:
                raise HTTPException(400, "select at least one project, or grant access to all projects")
    updated = store.update_user(uid, upd) if upd else target
    if projects_changed:
        updated = store.set_user_projects(uid, all_proj, pids)
    # A role/active/project change must take effect immediately: bump session_version
    # so existing sessions re-auth with the new authorization. (Name-only doesn't.)
    role_changed = "role" in upd and upd["role"] != target.get("role")
    active_changed = "active" in upd and upd["active"] != target.get("active")
    if role_changed or active_changed or projects_changed:
        updated = store.bump_session_version(uid)
    if role_changed:
        _audit(request, "user.role_changed", target=target.get("email"),
               old={"role": target.get("role")}, new={"role": upd.get("role")})
    if active_changed:
        _audit(request, "user.enabled" if upd.get("active") else "user.disabled",
               target=target.get("email"))
    if projects_changed:
        _audit(request, "user.projects_changed", target=target.get("email"),
               old={"all_projects": target.get("all_projects"), "project_ids": target.get("project_ids")},
               new={"all_projects": all_proj, "project_ids": pids})
    return {"user": _user_public(updated)}


@router.delete("/api/users/{uid}")
def remove_user(uid: str, request: Request):
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    me = _current_user(request)
    if me and me.get("id") == uid:
        raise HTTPException(400, "you can't delete your own account")
    if target.get("role") == "admin" and target.get("active") \
            and store.count_active_admins() <= 1:
        raise HTTPException(400, "cannot delete the last active admin")
    _audit(request, "user.deleted", target=target.get("email"),
           old={"role": target.get("role")})
    return store.delete_user(uid)


@router.post("/api/users/{uid}/resend-invite")
def resend_invite(uid: str, request: Request):
    """Re-issue and re-deliver the invitation LINK for a user (e.g. after SMTP was
    fixed, or the link expired). Admin-only. Reports delivery honestly."""
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    if not target.get("active"):
        raise HTTPException(400, "user is disabled — enable them before resending")
    me = _current_user(request)
    (mode, detail), token = _issue_invite_link(
        target, request, inviter_name=(me.get("name") or me.get("email")) if me else "")
    resp = {"user": _user_public(store.get_user(uid)), "delivery": mode}
    if mode == "sent":
        resp["message"] = f"Invitation link re-sent to {target['email']}."
    elif mode == "refused":
        resp["message"] = "Could not send: SMTP is not configured."
    else:
        resp["message"] = "Email failed to send. Check the SMTP configuration."
    return resp


class InviteVerifyIn(BaseModel):
    token: str


@router.get("/api/invite/verify")
def verify_invite(token: str):
    """Public: resolve an invite token to its invite view (who/role/workspace) + the
    invited email, so the /invite landing page can prompt the right login. Does NOT
    consume the token. Returns 404 for unknown/expired tokens (no enumeration)."""
    u = store.get_user_by_invite_token(token)
    if not u or u.get("invite_status") != "pending":
        raise HTTPException(404, "this invitation link is invalid or has expired")
    inviter = None
    try:
        inviter = store.invite_inviter_info(u["id"])
    except Exception:  # noqa: BLE001
        inviter = None
    return {"email": u["email"], "invite": {
        "pending": True, "role": u.get("role", "viewer"),
        "invited_at": u.get("invited_at"), "invited_by": inviter,
        "workspace": APP_WORKSPACE_NAME}}


@router.post("/api/users/{uid}/cancel-invite")
def cancel_invite(uid: str):
    """Cancel a still-pending invite by deleting the user record. Only valid while
    the invite is pending (the user has never signed in). Admin-only."""
    target = store.get_user(uid)
    if not target:
        raise HTTPException(404, "user not found")
    if target.get("invite_status") != "pending":
        raise HTTPException(400, "this user has already accepted — use disable/delete instead")
    # Invalidate any outstanding code, then remove the pending record.
    store.clear_otp(uid)
    store.delete_user(uid)
    return {"cancelled": uid}
