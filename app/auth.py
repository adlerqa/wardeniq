"""Passwordless auth primitives: stateless signed-cookie sessions and email OTP.

No new dependencies — sessions are HMAC-signed tokens keyed by APP_SECRET (the same
secret crypto.py uses). Rotating APP_SECRET invalidates all sessions and pending OTPs.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time

# Pragmatic email validation: one @, non-empty local part, a dotted domain, no
# spaces. Not RFC-perfect, but rejects the obviously-invalid values (including the
# ".env comment leaked as ADMIN_EMAIL" case that created a garbage admin row).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))

SESSION_COOKIE = "wq_session"
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", str(7 * 24 * 3600)))   # 7 days
OTP_TTL = int(os.getenv("OTP_TTL_SECONDS", "600"))                        # 10 minutes
OTP_MAX_ATTEMPTS = 5
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3}
ROLES = set(ROLE_RANK)

# The single fallback secret. Used ONLY when APP_SECRET is unset. It is
# intentionally recognizable so `secret_is_weak()` can refuse to run with it in a
# production posture. crypto.py imports this constant so the two stay in lockstep.
DEFAULT_APP_SECRET = "mongoT-qa-dev-key-change-me"
# Any of these (case-insensitive, trimmed) count as "not really set".
_WEAK_SECRETS = {
    DEFAULT_APP_SECRET.lower(),
    "change-me-in-production",
    "change-me",
    "changeme",
    "",
}
MIN_SECRET_LEN = 16


def _session_secret() -> str:
    """The secret used to sign sessions/OTPs. Prefers SESSION_SECRET, falling back to
    APP_SECRET (backward compatible), then the shipped placeholder."""
    return os.getenv("SESSION_SECRET") or os.getenv("APP_SECRET") or DEFAULT_APP_SECRET


def _secret() -> bytes:
    return _session_secret().encode()


def _value_is_weak(v: str) -> bool:
    s = (v or "").strip()
    return s.lower() in _WEAK_SECRETS or len(s) < MIN_SECRET_LEN


def secret_is_weak() -> bool:
    """True if the EFFECTIVE session secret or encryption key is unset, the shipped
    placeholder, or too short.

    These secrets sign sessions/OTPs and derive the Fernet key for every secret at
    rest — a predictable value lets an attacker forge an admin session and decrypt
    stored credentials. By default a single APP_SECRET fills both roles; operators may
    split them into SESSION_SECRET + ENCRYPTION_KEY, in which case BOTH must be strong.
    """
    session = os.getenv("SESSION_SECRET") or os.getenv("APP_SECRET") or ""
    encryption = os.getenv("ENCRYPTION_KEY") or os.getenv("APP_SECRET") or ""
    return _value_is_weak(session) or _value_is_weak(encryption)


# ---- sessions ---------------------------------------------------------------
# Tokens embed a session_version (sv). Bumping a user's sv (on role change / disable)
# invalidates every session that user already holds — enabling targeted revocation
# and forcing a demoted/promoted user to re-authenticate so they pick up the change.
def sign_session(user_id: str, session_version: int = 0, ttl: int = SESSION_TTL) -> str:
    exp = int(time.time()) + ttl
    msg = f"{user_id}.{int(session_version)}.{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{msg}.{sig}".encode()).decode()


def verify_session(token: str):
    """Verify a session token.

    Returns (user_id, session_version) if valid and unexpired, else None.
    Backward compatible: legacy 3-part tokens (user_id.exp.sig, no sv) verify with
    session_version 0 so existing cookies keep working across the upgrade.
    """
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.rsplit(".", 3)
        if len(parts) == 4:
            user_id, sv, exp, sig = parts
            signed = f"{user_id}.{sv}.{exp}"
        elif len(parts) == 3:  # legacy token without session_version
            user_id, exp, sig = parts
            sv, signed = "0", f"{user_id}.{exp}"
        else:
            return None
        good = hmac.new(_secret(), signed.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig):
            return None
        if int(exp) < time.time():
            return None
        return user_id, int(sv)
    except Exception:  # noqa: BLE001
        return None


# ---- one-time passwords -----------------------------------------------------
def gen_otp() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(_secret() + (code or "").strip().encode()).hexdigest()


def otp_matches(stored_hash: str, code: str) -> bool:
    return bool(stored_hash) and hmac.compare_digest(stored_hash, hash_otp(code))


# ---- invite tokens ----------------------------------------------------------
# A high-entropy, single-use, time-limited token emailed as an invite LINK (distinct
# from the login OTP, so the two never collide on the same field).
def gen_invite_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(_secret() + (token or "").strip().encode()).hexdigest()


def token_matches(stored_hash: str, token: str) -> bool:
    return bool(stored_hash) and hmac.compare_digest(stored_hash, hash_token(token))


# ---- role checks ------------------------------------------------------------
def has_role(user_role: str, minimum: str) -> bool:
    return ROLE_RANK.get(user_role, 0) >= ROLE_RANK.get(minimum, 99)
