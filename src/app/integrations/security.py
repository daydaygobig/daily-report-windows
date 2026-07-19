"""Utility helpers for encrypting and decrypting sensitive configuration."""

import base64
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings


def _normalize_key(raw_key: str) -> bytes:
    """Pad/trim the key to 32 url-safe base64 bytes."""

    key_bytes = raw_key.encode("utf-8")
    padded = base64.urlsafe_b64encode(key_bytes.ljust(32, b"0")[:32])
    return padded


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_normalize_key(settings.secrets_key))


def encrypt_value(value: Any) -> str:
    if value is None:
        raise ValueError("Cannot encrypt None value")
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(token: str) -> str:
    try:
        value = _fernet().decrypt(token.encode("utf-8"))
        return value.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted value") from exc
