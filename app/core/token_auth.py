"""Bearer-token principal resolver for API tokens (issue #37).

Registered against core/security.py's principal-resolver registry (see
main.py: `register_principal_resolver("/api/", bearer_token_principal)`), so
a machine caller (CI job, service account) can authenticate with
`Authorization: Bearer <token>` instead of a cookie session, with zero
changes to auth_gateway itself. A request with no Authorization header, or a
bearer value that isn't an active, unexpired token, returns None here so
resolve_principal() falls through to the cookie session unchanged — this
resolver is purely additive to the existing auth surface.

The returned principal dict carries the same shape core/security.py's
project-scope helpers already read off a cookie user (`role`, `all_projects`,
`project_ids`, `active`) — so `_require_project` and friends enforce a token
principal identically to a human one, with no new code there.
"""
import os

import auth
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)

# Rolling-window rate limit on FAILED token-auth attempts, keyed by caller IP
# (an unknown/garbage bearer token has no token doc of its own to throttle).
TOKEN_AUTH_FAILURE_WINDOW_SECONDS = int(os.getenv("TOKEN_AUTH_FAILURE_WINDOW_SECONDS", "300"))
TOKEN_AUTH_MAX_FAILURES_PER_WINDOW = int(os.getenv("TOKEN_AUTH_MAX_FAILURES_PER_WINDOW", "20"))


def _client_ip(request) -> str:
    return (request.headers.get("x-forwarded-for") or
            (request.client.host if request.client else "unknown"))


def bearer_token_principal(request):
    """core/security.py principal-resolver signature: `fn(request) -> user dict |
    None`. Never raises — a malformed header or a store hiccup must fail closed
    (None → 401 via the gateway), never surface as a 500."""
    try:
        header = request.headers.get("authorization") or ""
        if not header.lower().startswith("bearer "):
            return None
        token = header[len("bearer "):].strip()
        if not token:
            return None
        ip = _client_ip(request)
        if store.api_token_failure_count(ip, TOKEN_AUTH_FAILURE_WINDOW_SECONDS) \
                >= TOKEN_AUTH_MAX_FAILURES_PER_WINDOW:
            return None   # too many recent failures from this source — fail closed
        tok = store.get_api_token_by_hash(auth.hash_token(token))
        if not tok:
            store.record_api_token_failure(ip, TOKEN_AUTH_FAILURE_WINDOW_SECONDS)
            return None
        store.touch_api_token_last_used(tok["id"])
        return {"id": f"token:{tok['id']}", "email": None, "name": tok.get("name"),
                "role": tok.get("role", "viewer"), "active": True,
                "session_version": 0,
                "all_projects": tok.get("all_projects", True),
                "project_ids": tok.get("project_ids", []),
                "is_service_account": True, "token_id": tok["id"]}
    except Exception:  # noqa: BLE001
        return None
