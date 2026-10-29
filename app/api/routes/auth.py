"""Authentication: OTP sign-in, password sign-in (local admin), password change/reset
(including the APP_SECRET-based master reset), session, logout, and the current user's
own invite (accept/decline).

Moved out of main.py (Phase 6 of REFACTOR_PLAN.md — security-sensitive but contiguous
and self-contained, per the plan's suggested extraction order). Decorator changed from
`@app.` to `@router.` only — same 13 paths, same status codes, same cookie behavior.

`_smtp_cfg`/`_smtp_cfg_from_env` and `_user_public` moved to core/deps.py instead of
staying here, because the still-in-main.py users.py-domain code (`_issue_invite_link`,
`invite_user`, resend-invite — not yet extracted) also calls them; keeping them here
would force that code to import from this router, which the plan explicitly avoids (to
prevent router-to-router import cycles). `_deliver_otp`, `_deliver_reset_code`,
`_session_user`, and `_invite_view` stay in this file: every caller of each is a route
in this same file.
"""
import hmac
import secrets
import time

import auth
import email_send
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from api.schemas import OtpRequestIn
from core import throttle
from core.audit import _audit
from core.bootstrap import public_boot_status
from core.client_ip import client_ip
from core.config import (
    ADMIN_EMAIL, APP_WORKSPACE_NAME, DEFAULT_ADMIN_PASSWORD, OTP_DEV_CODES,
    OTP_MAX_PER_WINDOW, OTP_WINDOW_SECONDS, RESET_CODE_MAX_PER_WINDOW,
)
from core.deps import _smtp_cfg, _user_public
from core.logging_setup import get_logger
from core.security import _current_user
from core.state import store

log = get_logger("auth")

router = APIRouter()

# A throwaway hash of a random value, verified on sign-in paths where no real hash
# exists, so "no such account" / "account has no password" cost the same PBKDF2
# work as a wrong password and don't leak account existence through response time.
_DUMMY_PASSWORD_HASH = auth.hash_password(secrets.token_urlsafe(16))


def _deliver_otp(email, code, recipient_name="", is_admin=False, is_bootstrap=False):
    """Returns ('sent'|'logged'|'unavailable'|'error', detail).
    - 'sent'        : emailed via SMTP.
    - 'logged'      : no SMTP configured. The code is printed to the server log for
                      the bootstrap admin (the first admin / ADMIN_EMAIL) so they can
                      sign in and set email up; `detail` is "" (nothing returned to
                      the caller). Only with the explicit OTP_DEV_CODES=true opt-in
                      (ignored when APP_ENV=production) is every code logged AND
                      returned in `detail` for the sign-in screen (demo installs).
    - 'unavailable' : no SMTP and neither of the above -- no code is delivered.
    - 'error'       : SMTP configured but the send failed.
    """
    cfg = _smtp_cfg()
    if not cfg:
        if not (OTP_DEV_CODES or is_bootstrap):
            return "unavailable", ""
        role_hint = "admin" if is_admin else "user"
        log.info("\n" + "=" * 64 +
                "\nSMTP is not configured — one-time sign-in code"
                "\n  %s (%s): %s"
                "\nSet up email under Configuration → Email; codes will then"
                "\nonly be emailed.\n"
                + "=" * 64 + "\n", email, role_hint, code)
        return "logged", (code if OTP_DEV_CODES else "")

    ok, err = email_send.send_otp(cfg, email, code, recipient_name)
    if ok:
        return "sent", ""

    log.warning("OTP send failed for %s: %s", email, err)
    return "error", err


def _deliver_reset_code(target_name: str, email: str, code: str):
    """Deliver password reset code via SMTP email ONLY. Never prints codes to logs."""
    cfg = _smtp_cfg()
    if not cfg:
        return "no_smtp", "SMTP is not configured"

    if email and auth.is_valid_email(email):
        ok, err = email_send.send_otp(cfg, email, code, recipient_name=target_name)
        if ok:
            return "sent", ""
        log.warning("Password Reset send failed for %s: %s", email, err)
        return "error", err
    else:
        return "no_email", "User has no valid email address configured"


# Shown for every "nothing was actually attempted" outcome of request_otp() below
# (unknown email, deactivated account, rate-limited) so the sign-in screen never
# claims a code was sent when none was. Wording deliberately mirrors the existing
# anti-enumeration message in request_password_reset() ("If an account exists...")
# a few lines below in this file: it neither confirms nor denies the account
# exists, which is the whole point of masking these cases in the first place —
# but unlike the OTP path before this fix, it no longer *asserts* delivery either.
OTP_MASKED_MESSAGE = "If an account exists for this email, a sign-in code has been sent. Check your inbox."


@router.post("/api/auth/request-otp")
def request_otp(body: OtpRequestIn, request: Request = None):
    email = (body.email or "").strip().lower()
    if not auth.is_valid_email(email):
        raise HTTPException(400, "a valid email is required")
    user = store.get_user_by_email(email)
    bootstrap = False
    if not user:
        # First-run convenience: with no users with valid emails yet, the first requester becomes admin.
        has_real_users = any(auth.is_valid_email(u.get("email")) for u in store.list_users())
        if not has_real_users:
            user = store.create_user(email, email.split("@")[0], "admin"); bootstrap = True
        else:
            # Don't reveal whether an account exists. No email is ever attempted on
            # this branch, so the response must say so honestly (OTP_MASKED_MESSAGE)
            # instead of the confident "Code sent" text used for a real send —
            # returning that here is exactly the false-positive success message QA
            # reported, for the extremely common case of testing with an email that
            # isn't (yet) a registered account.
            return {"sent": True, "message": OTP_MASKED_MESSAGE}
    if not user.get("active"):
        return {"sent": True, "message": OTP_MASKED_MESSAGE}
    # Rate-limit code issuance per account. Return the generic masked response on
    # limit so we don't reveal that the account exists or is being targeted — and,
    # as above, no email is sent for this request, so the message must not claim
    # one was.
    # Throttled requests are not recorded, so they can't extend the window.
    if store.otp_recent_issue_count(user["id"], OTP_WINDOW_SECONDS,
                                    OTP_MAX_PER_WINDOW) > OTP_MAX_PER_WINDOW:
        log.warning("OTP throttled: %s exceeded %d/%ds", email, OTP_MAX_PER_WINDOW,
                  OTP_WINDOW_SECONDS)
        return {"sent": True, "message": OTP_MASKED_MESSAGE}
    code = auth.gen_otp()
    store.set_otp(user["id"], auth.hash_otp(code), time.time() + auth.OTP_TTL)
    is_admin = user.get("role") == "admin"
    is_bootstrap = bootstrap or (is_admin and bool(ADMIN_EMAIL) and email == ADMIN_EMAIL)
    mode, detail = _deliver_otp(email, code, user.get("name") or email.split("@")[0],
                                is_admin=is_admin, is_bootstrap=is_bootstrap)
    if mode == "unavailable":
        # Nothing was delivered; same masked answer as for an unknown account.
        return {"sent": True, "message": OTP_MASKED_MESSAGE}
    if mode == "error":
        raise HTTPException(502, "could not send the sign-in email — please try again "
                                 "or contact your administrator")
    # delivery: "email" (SMTP) or "log" (no SMTP: code printed to the server log;
    # returned in `dev_code` only with the OTP_DEV_CODES opt-in).
    resp = {"sent": True, "bootstrap": bootstrap,
            "delivery": "log" if mode == "logged" else "email",
            "message": "Code sent. Check your inbox."}
    if mode == "logged" and detail:
        # `detail` holds the plaintext code only under OTP_DEV_CODES (see _deliver_otp).
        resp["dev_code"] = detail
    return resp


class OtpVerifyIn(BaseModel):
    email: str
    code: str


@router.post("/api/auth/verify-otp")
def verify_otp(body: OtpVerifyIn, response: Response, request: Request = None):
    email = (body.email or "").strip().lower()
    tkeys = throttle.keys("otp", email, client_ip(request) if request else None)
    throttle.check(store, tkeys)
    user = store.get_user_by_email(email)
    migrating = False
    if not user:
        # Check if there are no users with a valid email yet
        has_real_users = any(auth.is_valid_email(u.get("email")) for u in store.list_users())
        if not has_real_users:
            user = store.get_user_by_email("admin")
            if user:
                migrating = True

    if not user or not user.get("active"):
        throttle.fail(store, tkeys)
        raise HTTPException(401, "invalid email or code")
    if not user.get("otp_hash") or user.get("otp_expires", 0) < time.time():
        throttle.fail(store, tkeys)
        raise HTTPException(401, "code expired — request a new one")
    if user.get("otp_attempts", 0) >= auth.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "too many attempts — request a new code")
    if not auth.otp_matches(user["otp_hash"], body.code):
        store.inc_otp_attempts(user["id"])
        throttle.fail(store, tkeys)
        _audit(request, "auth.login_failed", target=email, actor={}, detail="one-time code")
        raise HTTPException(401, "invalid email or code")

    throttle.succeed(store, tkeys)
    _audit(request, "auth.login", target=email, actor=user, detail="one-time code")
    store.clear_otp(user["id"])
    if migrating:
        store.update_user(user["id"], {"email": email, "name": email.split("@")[0]})

    store.touch_login(user["id"])

    fresh = store.get_user(user["id"]) or user
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(user["id"], fresh.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"user": _user_public(fresh)}


@router.get("/api/auth/smtp-status")
def smtp_status():
    cfg = _smtp_cfg()
    return {"smtp_setup": cfg is not None}


_NO_USERS_MESSAGE = (
    "No user accounts exist. Run scripts/reset-admin-password.sh from the "
    "installation directory to create the admin account and set its password. "
    "This also works when bootstrap stops before creating the admin."
)
_DATABASE_UNAVAILABLE_MESSAGE = (
    "Unable to check user accounts. Check MongoDB connectivity and the server logs, then try again."
)


@router.get("/api/auth/boot-status")
def boot_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    status = public_boot_status()
    status.update(users_empty=None, recovery="")
    if not status["ready"]:
        try:
            status["users_empty"] = not store.has_users()
        except Exception:  # DB unavailable is unknown, not an empty collection.
            status["recovery"] = _DATABASE_UNAVAILABLE_MESSAGE
        else:
            if status["users_empty"]:
                status["recovery"] = _NO_USERS_MESSAGE
    return status


class LoginPasswordIn(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login-password")
def login_password(body: LoginPasswordIn, response: Response, request: Request = None):
    cfg = _smtp_cfg()
    if cfg is not None:
        raise HTTPException(400, "Password login is disabled because SMTP is configured. Please use email OTP.")

    username = (body.username or "").strip()
    password = body.password or ""
    # Per-account and per-IP failure limits with a lockout window. A locked key is
    # refused before any password check, and the refusal itself isn't counted.
    tkeys = throttle.keys("login", username, client_ip(request) if request else None)
    throttle.check(store, tkeys)

    # Accept the bootstrap `admin` username OR any account's email address — the
    # sign-in form is labelled "Username or email", and /api/auth/reset-password
    # already sets a password on ANY user by email, so restricting sign-in to the
    # literal "admin" left those users unable to use the password they just set.
    # get_user_by_email() lowercases/strips, and the bootstrap row's email IS
    # "admin", so one lookup resolves both forms.
    user = store.get_user_by_email(username)
    if not user:
        # First boot: no local admin row yet, so only the configured default works
        # (ADMIN_PASSWORD if the operator set one, else the shipped admin123), and
        # only under the bootstrap username. Verify a dummy hash first so a missing
        # account costs the same time as a wrong password (no user enumeration).
        auth.password_matches(_DUMMY_PASSWORD_HASH, password)
        if username.lower() != "admin" or password != DEFAULT_ADMIN_PASSWORD:
            try:
                has_users = store.has_users()
            except Exception:
                raise HTTPException(503, _DATABASE_UNAVAILABLE_MESSAGE) from None
            if not has_users:
                status = public_boot_status()
                raise HTTPException(503, " ".join(filter(None, [status["detail"], _NO_USERS_MESSAGE])))
            throttle.fail(store, tkeys)
            _audit(request, "auth.login_failed", target=username, actor={}, detail="password")
            raise HTTPException(401, "Invalid username or password")
        user = store.create_user("admin", "Admin", "admin")
    else:
        stored_hash = user.get("password_hash")
        if stored_hash:
            # Once a real password has been set (via ADMIN_PASSWORD seeding,
            # /api/auth/change-password or /api/auth/reset-password), it's the only
            # one accepted — the shipped default stops working so it can't be
            # bypassed with the old admin123.
            ok = auth.password_matches(stored_hash, password)
        elif user.get("email") == "admin":
            # Bootstrap admin that has never had a password set.
            ok = password == DEFAULT_ADMIN_PASSWORD
        else:
            # An email account with no password has OTP only: never let an empty
            # or arbitrary password in through this door.
            auth.password_matches(_DUMMY_PASSWORD_HASH, password)
            ok = False
        if not ok:
            throttle.fail(store, tkeys)
            _audit(request, "auth.login_failed", target=username, actor={}, detail="password")
            raise HTTPException(401, "Invalid username or password")

    if not user.get("active"):
        _audit(request, "auth.login_failed", target=username, actor={},
               detail="password; account deactivated")
        raise HTTPException(401, "User account is deactivated")

    throttle.succeed(store, tkeys)
    _audit(request, "auth.login", target=user.get("email"), actor=user, detail="password")
    store.touch_login(user["id"])
    fresh = store.get_user(user["id"]) or user
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(user["id"], fresh.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"user": _user_public(fresh)}


class ChangePasswordIn(BaseModel):
    current_password: str = ""
    new_password: str


@router.post("/api/auth/change-password")
def change_password(body: ChangePasswordIn, request: Request, response: Response):
    """Self-service password change for any account that HAS a password: the bootstrap
    `admin` / admin123 account, and any email account given one by the ADMIN_PASSWORD
    seed, an APP_SECRET master reset, or a reset code. An account with no password
    signs in by one-time code only and has nothing to change — it gets a 400 rather
    than a way to set a first password here (that would turn this route into an
    unauthenticated-password bootstrap for OTP-only users). Requires an authenticated
    session (this route is NOT public — the auth_gateway already resolved
    request.state.user)."""
    user = _current_user(request)
    if not user:
        raise HTTPException(401, "not authenticated")
    full = store.get_user_by_email(user.get("email")) or user
    stored_hash = full.get("password_hash")
    is_local_admin = full.get("email") == "admin"
    if not stored_hash and not is_local_admin:
        raise HTTPException(400, "this account has no password — it signs in with a "
                                 "one-time code. Set ADMIN_PASSWORD in .env, or use a "
                                 "password reset, to give it one.")
    current = body.current_password or ""
    # Only the bootstrap admin may authenticate with the shipped default; every other
    # account must present its real hash.
    current_ok = (auth.password_matches(stored_hash, current) if stored_hash
                  else current == DEFAULT_ADMIN_PASSWORD)
    if not current_ok:
        raise HTTPException(400, "current password is incorrect")

    errs = auth.password_policy_errors(body.new_password)
    if errs:
        raise HTTPException(400, auth.password_policy_message(errs))
    if body.new_password == current:
        raise HTTPException(400, "new password must be different from the current one")

    updated = store.set_user_password(full["id"], auth.hash_password(body.new_password))
    _audit(request, "user.password_changed", target=full.get("email", "admin"), actor=user)
    # set_user_password() bumps session_version, invalidating every session this
    # user holds — including the one making this request — so re-issue a fresh
    # cookie for THIS session immediately, or the caller would be logged out by
    # their own password change.
    response.set_cookie(auth.SESSION_COOKIE,
                        auth.sign_session(full["id"], updated.get("session_version", 0)),
                        max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.COOKIE_SECURE, path="/")
    return {"changed": True, "user": _user_public(updated)}


class RequestPasswordResetIn(BaseModel):
    username_or_email: str


class ResetPasswordIn(BaseModel):
    username_or_email: str
    code: str
    new_password: str


@router.post("/api/auth/request-password-reset")
def request_password_reset(body: RequestPasswordResetIn):
    cfg = _smtp_cfg()
    if not cfg:
        return {"sent": False, "smtp_configured": False,
                "message": "SMTP is not configured. Admin password can be reset via Docker CLI or environment variable."}

    target = (body.username_or_email or "").strip()
    if not target:
        raise HTTPException(400, "Username or email is required")

    user = store.get_user_by_email(target.lower())
    if not user and (target.lower() == "admin" or target == "admin"):
        user = store.get_user_by_email("admin")

    if not user or not user.get("active"):
        # Generic response to prevent user enumeration
        return {"sent": True, "smtp_configured": True, "message": "If an account exists, a 6-digit reset code has been sent to your email."}

    # Limit how many codes one account can be sent. A throttled request is not
    # recorded and does NOT replace the outstanding code (so it can't reset that
    # code's attempt counter). Same generic answer as above.
    try:
        allowed = store.reset_code_try_issue(user["id"], OTP_WINDOW_SECONDS,
                                             RESET_CODE_MAX_PER_WINDOW)
    except AttributeError:
        allowed = True
    if not allowed:
        log.warning("password-reset code throttled for %s", target)
        return {"sent": True, "smtp_configured": True, "message": "If an account exists, a 6-digit reset code has been sent to your email."}

    code = auth.gen_otp()
    store.set_reset_code(user["id"], auth.hash_otp(code), time.time() + auth.OTP_TTL)

    target_email = user.get("email") if auth.is_valid_email(user.get("email")) else ""
    mode, detail = _deliver_reset_code(user.get("name") or target, target_email, code)

    if mode == "error":
        raise HTTPException(502, "Could not send password reset email. Please check your SMTP configuration under Settings.")
    if mode in ("no_smtp", "no_email"):
        return {"sent": False, "smtp_configured": False,
                "message": "Password reset via email is unavailable. Use Docker CLI to reset the password."}

    return {"sent": True, "smtp_configured": True, "message": "A 6-digit reset code has been sent to your email address."}


@router.post("/api/auth/reset-password")
def reset_password(body: ResetPasswordIn, request: Request = None):
    target = (body.username_or_email or "").strip()
    if not target:
        raise HTTPException(400, "Username or email is required")
    if not body.code or not body.code.strip():
        raise HTTPException(400, "Reset code is required")
    tkeys = throttle.keys("reset", target, client_ip(request) if request else None)
    throttle.check(store, tkeys)

    user = store.get_user_by_email(target.lower())
    if not user and (target.lower() == "admin" or target == "admin"):
        user = store.get_user_by_email("admin")

    if not user or not user.get("active"):
        throttle.fail(store, tkeys)
        raise HTTPException(401, "Invalid request or reset code")

    if not user.get("reset_hash") or user.get("reset_expires", 0) < time.time():
        throttle.fail(store, tkeys)
        raise HTTPException(401, "Reset code expired — please request a new one")

    if user.get("reset_attempts", 0) >= auth.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many failed attempts — please request a new reset code")

    if not auth.otp_matches(user["reset_hash"], body.code.strip()):
        store.inc_reset_attempts(user["id"])
        throttle.fail(store, tkeys)
        raise HTTPException(401, "Invalid reset code")

    errs = auth.password_policy_errors(body.new_password)
    if errs:
        raise HTTPException(400, auth.password_policy_message(errs))

    throttle.succeed(store, tkeys)
    store.clear_reset_code(user["id"])
    store.set_user_password(user["id"], auth.hash_password(body.new_password))

    return {"reset": True, "message": "Password reset successfully. You can now sign in."}


class ResetPasswordMasterIn(BaseModel):
    username: str = "admin"
    app_secret: str
    new_password: str


@router.post("/api/auth/reset-password-master")
def reset_password_master(body: ResetPasswordMasterIn, request: Request = None):
    """Web-native admin password reset using the container's APP_SECRET."""
    provided_secret = (body.app_secret or "").strip()
    if not provided_secret:
        raise HTTPException(400, "App Master Secret (APP_SECRET) is required")
    # The master secret gets the stricter (per-account) limit, applied per client IP.
    tkeys = [(k, throttle.AUTH_MAX_FAILURES_PER_ACCOUNT)
             for k, _ in throttle.keys("master", None, client_ip(request) if request else None)]
    throttle.check(store, tkeys)

    effective_secret = auth._session_secret()
    if not hmac.compare_digest(provided_secret.encode(), effective_secret.encode()):
        throttle.fail(store, tkeys)
        _audit(request, "auth.master_reset_failed", target=(body.username or "admin").strip(),
               actor={}, detail="invalid master secret")
        raise HTTPException(401, "Invalid App Master Secret")

    target = (body.username or "admin").strip()
    user = store.get_user_by_email(target.lower())
    if not user and (target.lower() == "admin" or target == "admin"):
        user = store.get_user_by_email("admin")

    if not user:
        if target.lower() == "admin" or target == "admin":
            user = store.create_user("admin", "Admin", "admin")
        else:
            raise HTTPException(404, f"User '{target}' not found")

    if not user.get("active"):
        raise HTTPException(401, "User account is deactivated")
    # Recovery path for administrators only (incl. the bootstrap `admin` account);
    # other accounts reset via an emailed code or an administrator.
    if user.get("role") != "admin":
        _audit(request, "auth.master_reset_failed", target=target, actor={},
               detail="target is not an admin account")
        raise HTTPException(403, "The master reset only applies to administrator accounts")

    errs = auth.password_policy_errors(body.new_password)
    if errs:
        raise HTTPException(400, auth.password_policy_message(errs))

    # set_user_password() bumps session_version, so every existing session of this
    # account is signed out.
    store.set_user_password(user["id"], auth.hash_password(body.new_password))
    store.clear_reset_code(user["id"])
    _audit(request, "auth.master_reset", target=user.get("email") or target, actor={},
           detail="password reset with the master secret; sessions revoked")
    return {"reset": True, "message": "Password reset successfully using App Master Secret. You can now sign in."}


@router.get("/api/auth/me")
def auth_me(request: Request):
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    if not user or not user.get("active"):
        raise HTTPException(401, "not authenticated")
    if int(user.get("session_version", 0)) != int(tok_sv):
        raise HTTPException(401, "session expired — please sign in again")
    return {"user": _user_public(user), "auth_enabled": True}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    """Sign out. A valid, current session is also revoked server-side (the user's
    session_version is bumped), so the cookie value can't be replayed afterwards.
    Note this ends every session of that user, on all devices."""
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    if sess:
        uid, tok_sv = sess
        try:
            user = store.get_user(uid)
            if user and int(user.get("session_version", 0)) == int(tok_sv):
                store.bump_session_version(uid)
                _audit(request, "auth.logout", target=user.get("email"), actor=user)
        except Exception as e:  # noqa: BLE001 — logout must always clear the cookie
            log.warning("logout: could not revoke session for %s: %r", uid, e)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


def _session_user(request: Request):
    """Resolve the current user from the session cookie for self-service /api/auth
    endpoints (these are public-prefixed, so the gateway hasn't populated
    request.state.user). Enforces the same session_version check as the gateway."""
    sess = auth.verify_session(request.cookies.get(auth.SESSION_COOKIE))
    uid, tok_sv = sess if sess else (None, None)
    user = store.get_user(uid) if uid else None
    if not user or not user.get("active"):
        raise HTTPException(401, "not authenticated")
    if int(user.get("session_version", 0)) != int(tok_sv):
        raise HTTPException(401, "session expired — please sign in again")
    return user


def _invite_view(user):
    """Shape a pending invite for the invited user's banner, with inviter info."""
    inviter = None
    try:
        inviter = store.invite_inviter_info(user["id"])
    except Exception:  # noqa: BLE001
        inviter = None
    return {
        "pending": user.get("invite_status") == "pending",
        "role": user.get("role", "viewer"),
        "invited_at": user.get("invited_at"),
        "invited_by": inviter,               # {email, name} or None
        "workspace": APP_WORKSPACE_NAME,     # single-tenant label
    }


@router.get("/api/auth/my-invite")
def my_invite(request: Request):
    """The current user's own invite state (for the post-login invite banner)."""
    user = _session_user(request)
    return {"invite": _invite_view(user)}


@router.post("/api/auth/invite/accept")
def accept_my_invite(request: Request):
    user = _session_user(request)
    if user.get("invite_status") != "pending":
        # Idempotent: nothing to do if already resolved.
        return {"invite": _invite_view(store.get_user(user["id"]))}
    updated = store.accept_invite(user["id"])
    store.clear_invite_token(user["id"])   # consume the single-use invite token
    _audit(request, "invite.accepted", target=user.get("email"), actor=user)
    return {"invite": _invite_view(updated), "user": _user_public(updated)}


@router.post("/api/auth/invite/decline")
def decline_my_invite(request: Request, response: Response):
    user = _session_user(request)
    if user.get("invite_status") != "pending":
        return {"declined": False}
    store.decline_invite(user["id"])
    store.clear_invite_token(user["id"])   # consume the single-use invite token
    _audit(request, "invite.declined", target=user.get("email"), actor=user)
    # Declining deactivates the account; end the session too.
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"declined": True}
