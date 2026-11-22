"""
Symmetric encryption helpers for secrets at rest (client secrets, refresh tokens).

Uses Fernet (AES-128-CBC + HMAC). The Fernet key is derived from the
ENCRYPTION_KEY env var via SHA-256, so any string of any length works as the key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    raw = (settings.encryption_key or "talksuite-dev-default-key-change-me").encode()
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string. Returns None if input is None/empty."""
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Decrypt a string. Returns None if input is None/empty or invalid."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return None
