"""Best-effort audit-log writer.

Moved out of main.py (Phase 2 of REFACTOR_PLAN.md). Depends on
`core.security._current_user` for its generic actor-resolution fallback (used
when a caller doesn't pass `actor` explicitly) — `core/security.py`'s
`auth_gateway` in turn needs to call `_audit`, which it does via a
function-level import to avoid a module-level cycle (see the comment at that
call site).
"""
from core.logging_setup import get_logger
from core.security import _current_user
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)

log = get_logger("audit")


def _audit(request, action, target=None, old=None, new=None, actor=None, detail=None):
    """Best-effort audit-log write. Captures actor (from session), IP and user-agent.
    Never raises — auditing must not break the action it records."""
    try:
        actor = actor if actor is not None else _current_user(request)
        ip = None
        ua = None
        if request is not None:
            ip = (request.headers.get("x-forwarded-for") or
                  (request.client.host if request.client else None))
            ua = request.headers.get("user-agent")
        store.add_audit(action, actor=actor, target=target, old=old, new=new,
                        ip=ip, user_agent=ua, detail=detail)
    except Exception as e:  # noqa: BLE001
        log.warning("failed to record %s: %s", action, e)
