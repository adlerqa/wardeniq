"""Symmetric encryption for secrets at rest (GitHub PAT, LLM API keys).

Key is derived from ENCRYPTION_KEY if set, else APP_SECRET (backward compatible).
Change it in production; rotating it invalidates previously stored secrets (they'd
need re-entering). Keep it distinct from SESSION_SECRET if you rotate them on
different schedules.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from auth import DEFAULT_APP_SECRET


def _fernet() -> Fernet:
    secret = os.getenv("ENCRYPTION_KEY") or os.getenv("APP_SECRET") or DEFAULT_APP_SECRET
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


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
