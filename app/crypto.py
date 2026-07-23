"""Symmetric encryption for secrets at rest (GitHub PAT, LLM API keys).

Key is derived from ENCRYPTION_KEY if set, else APP_SECRET (backward compatible).
Change it in production; rotating it invalidates previously stored secrets (they'd
need re-entering). Keep it distinct from SESSION_SECRET if you rotate them on
different schedules.

Key derivation uses PBKDF2-HMAC-SHA256 (a slow, salted KDF) so that a leaked or
low-entropy secret can't be turned into the encryption key with a single cheap
hash. A fixed application salt is used because the KDF protects one global key
(not per-record passwords), so the salt's role here is domain separation and
KDF-standard compliance rather than defeating cross-record rainbow tables.

Backward compatibility: older installs derived the key with a single unsalted
SHA-256. We decrypt with a MultiFernet that tries the new PBKDF2 key first and
falls back to the legacy SHA-256 key, so existing stored secrets keep working.
New writes (and any re-save of a setting) are encrypted with the strong key;
MultiFernet.rotate() could be used later to migrate old ciphertext in place.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from auth import DEFAULT_APP_SECRET

# Domain-separation salt for the KDF. Changing this value rotates the key and
# invalidates previously stored secrets, exactly like changing APP_SECRET.
_KDF_SALT = b"wardeniq.secret-encryption.v1"
_KDF_ITERATIONS = 200_000


def _current_secret() -> str:
    return os.getenv("ENCRYPTION_KEY") or os.getenv("APP_SECRET") or DEFAULT_APP_SECRET


def _strong_key(secret: str) -> bytes:
    """PBKDF2-HMAC-SHA256 derived Fernet key (the format we encrypt with today)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KDF_SALT,
        iterations=_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def _legacy_key(secret: str) -> bytes:
    """Original unsalted single-SHA-256 key — kept only so secrets encrypted by
    earlier versions can still be decrypted (read path)."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _fernet() -> MultiFernet:
    secret = _current_secret()
    # Order matters: the FIRST fernet is used for encryption. Decryption tries
    # each in order, so legacy-encrypted tokens still resolve via the fallback.
    return MultiFernet([Fernet(_strong_key(secret)), Fernet(_legacy_key(secret))])


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception):  # noqa: BLE001
        return ""
