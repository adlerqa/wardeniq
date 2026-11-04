"""Brute-force throttling helpers for the public auth routes.

Thin wrappers over the Store's `throttle_*` methods (store/users_auth.py) that apply
the configured limits and fail OPEN on a storage error -- the database being down
already makes sign-in fail, and a throttle hiccup must never lock everyone out.
"""
import math

from fastapi import HTTPException

from core.config import (
    AUTH_FAILURE_WINDOW_SECONDS, AUTH_LOCKOUT_SECONDS,
    AUTH_MAX_FAILURES_PER_ACCOUNT, AUTH_MAX_FAILURES_PER_IP,
)
from core.logging_setup import get_logger

log = get_logger("throttle")


def keys(scope: str, account: str | None, ip: str | None):
    """[(key, max_failures)] for a scope; account names are case-normalised."""
    out = []
    if account:
        out.append((f"{scope}:acct:{account.strip().lower()}", AUTH_MAX_FAILURES_PER_ACCOUNT))
    if ip:
        out.append((f"{scope}:ip:{ip}", AUTH_MAX_FAILURES_PER_IP))
    return out


def check(store, key_list):
    """Raise 429 if any key is locked out (nothing is recorded for this request)."""
    for key, _ in key_list:
        try:
            left = store.throttle_locked_for(key)
        except Exception as e:  # noqa: BLE001
            log.warning("throttle check failed for %s: %r", key, e)
            continue
        if left > 0:
            minutes = max(1, math.ceil(left / 60))
            raise HTTPException(429, f"Too many failed attempts — try again in {minutes} "
                                     f"minute{'s' if minutes != 1 else ''}.",
                                headers={"Retry-After": str(int(math.ceil(left)))})


def fail(store, key_list):
    for key, limit in key_list:
        try:
            store.throttle_record_failure(key, limit, AUTH_FAILURE_WINDOW_SECONDS,
                                          AUTH_LOCKOUT_SECONDS)
        except Exception as e:  # noqa: BLE001
            log.warning("throttle record failed for %s: %r", key, e)


def succeed(store, key_list):
    """Clear the per-account counters after a success (per-IP counters stay)."""
    for key, _ in key_list:
        if ":acct:" not in key:
            continue
        try:
            store.throttle_clear(key)
        except Exception as e:  # noqa: BLE001
            log.warning("throttle clear failed for %s: %r", key, e)
