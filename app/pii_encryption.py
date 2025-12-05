"""Column-level PII encryption utilities.

Provides a small wrapper around Fernet symmetric encryption and a
SQLAlchemy `TypeDecorator` for transparent encryption/decryption of
text columns.

Behavior:
- If `PII_ENCRYPTION_KEY` (or secret via app.secrets) is present, data
  is encrypted with Fernet and stored as a base64 string.
- If no key is configured, the type passes values through unmodified
  (encryption disabled) to keep test/dev workflow simple. Production
  SHOULD set the key.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TEXT, TypeDecorator

from .secrets import secrets

logger = logging.getLogger(__name__)


class PIIEncryptor:
    def __init__(self, key: Optional[str] = None):
        if key is None:
            key = secrets.get("PII_ENCRYPTION_KEY") or os.getenv("PII_ENCRYPTION_KEY")

        if key:
            try:
                if isinstance(key, str) and len(key) == 44 and key.endswith("="):
                    self.fernet = Fernet(key.encode("utf-8"))
                else:
                    derived = base64.urlsafe_b64encode(key.encode("utf-8"))
                    derived = derived[:44]
                    self.fernet = Fernet(derived)
                self.enabled = True
            except Exception:
                logger.exception("Failed to initialize Fernet from provided key")
                self.fernet = None
                self.enabled = False
        else:
            self.fernet = None
            self.enabled = False

    def encrypt(self, plaintext: str) -> Optional[str]:
        if not self.enabled or plaintext is None:
            return plaintext
        try:
            token = self.fernet.encrypt(plaintext.encode("utf-8"))
            return token.decode("utf-8")
        except Exception:
            logger.exception("PII encryption failed")
            return None

    def decrypt(self, token: str) -> Optional[str]:
        if not self.enabled or token is None:
            return token
        try:
            data = self.fernet.decrypt(token.encode("utf-8"))
            return data.decode("utf-8")
        except InvalidToken:
            logger.exception("Invalid encryption token")
            return None
        except Exception:
            logger.exception("PII decryption failed")
            return None


# module-level singleton
_pii_encryptor: Optional[PIIEncryptor] = None


def get_pii_encryptor() -> PIIEncryptor:
    global _pii_encryptor
    if _pii_encryptor is None:
        _pii_encryptor = PIIEncryptor()
    return _pii_encryptor


class PIIEncryptedType(TypeDecorator):
    """SQLAlchemy TypeDecorator that transparently encrypts/decrypts TEXT."""

    impl = TEXT

    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        enc = get_pii_encryptor()
        if not enc.enabled:
            return value
        out = enc.encrypt(value)
        return out if out is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        enc = get_pii_encryptor()
        if not enc.enabled:
            return value
        return enc.decrypt(value)


__all__ = ["PIIEncryptedType", "get_pii_encryptor", "PIIEncryptor"]
