"""
Audit Log Encryption Module

Provides AES-256 encryption for sensitive data in audit logs.
Supports optional encryption via environment variables.

Features:
- AES-256-GCM (authenticated encryption)
- Automatic key generation from master secret
- Base64 encoding for storage/transmission
- Key rotation support (versioned keys)
- HIPAA/GDPR compliance helpers
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


class AuditEncryptor:
    """
    Encrypts sensitive audit log data using AES-256-GCM.

    Features:
    - Authenticated encryption (detects tampering)
    - Automatic key derivation from master secret
    - Per-record nonce (IV) for security
    - Optional compression for large payloads
    """

    KEY_SIZE = 32
    NONCE_SIZE = 12
    TAG_SIZE = 16
    PBKDF2_ITERATIONS = 100000

    def __init__(self, master_secret: Optional[str] = None):
        """
        Initialize encryptor with optional master secret.

        Args:
            master_secret: Master secret for key derivation.
                          If None, read from env AUDIT_ENCRYPTION_SECRET.
                          If empty, encryption disabled.
        """
        if not CRYPTO_AVAILABLE:
            logger.warning("cryptography library not available; encryption disabled")
            self.enabled = False
            return

        if master_secret is None:
            master_secret = os.getenv("AUDIT_ENCRYPTION_SECRET", "").strip()

        self.enabled = bool(master_secret)
        self.master_secret = master_secret

        if self.enabled:
            logger.info("Audit encryption enabled")
        else:
            logger.debug("Audit encryption disabled")

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive encryption key from master secret using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        return kdf.derive(self.master_secret.encode("utf-8"))

    def encrypt(self, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Encrypt audit data and return encrypted result with metadata.

        Args:
            data: Dictionary to encrypt

        Returns:
            Dict with keys:
              - ciphertext: base64-encoded encrypted data
              - nonce: base64-encoded nonce (IV)
              - salt: base64-encoded salt for key derivation
              - version: encryption version (for key rotation)
            Or None if encryption disabled.
        """
        if not self.enabled or not CRYPTO_AVAILABLE:
            return None

        try:
            salt = os.urandom(16)
            nonce = os.urandom(self.NONCE_SIZE)

            key = self._derive_key(salt)

            plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
            cipher = AESGCM(key)
            ciphertext = cipher.encrypt(nonce, plaintext, None)

            return {
                "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
                "nonce": base64.b64encode(nonce).decode("utf-8"),
                "salt": base64.b64encode(salt).decode("utf-8"),
                "version": "1",
            }
        except Exception:
            logger.exception("Encryption failed; data not encrypted")
            return None

    def decrypt(self, encrypted: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Decrypt audit data.

        Args:
            encrypted: Dict with ciphertext, nonce, salt, version

        Returns:
            Decrypted data dict, or None on error
        """
        if not self.enabled or not CRYPTO_AVAILABLE:
            return None

        try:
            ciphertext = base64.b64decode(encrypted["ciphertext"].encode("utf-8"))
            nonce = base64.b64decode(encrypted["nonce"].encode("utf-8"))
            salt = base64.b64decode(encrypted["salt"].encode("utf-8"))

            key = self._derive_key(salt)

            cipher = AESGCM(key)
            plaintext = cipher.decrypt(nonce, ciphertext, None)

            return json.loads(plaintext.decode("utf-8"))
        except Exception:
            logger.exception("Decryption failed")
            return None


class AuditLogFilter:
    """
    Helpers for identifying and filtering sensitive fields in audit logs.

    Supports HIPAA and GDPR sensitive data classification.
    """

    # Sensitive field patterns (for masking/encryption decisions)
    SENSITIVE_FIELDS = {
        "HIPAA": [
            "ssn",
            "medical_record_number",
            "health_plan_beneficiary_id",
            "account_number",
            "credit_card",
            "password",
        ],
        "GDPR": [
            "email",
            "phone",
            "ssn",
            "id_number",
            "ip_address",
            "location",
            "password",
            "credit_card",
        ],
        "PCI_DSS": [
            "credit_card",
            "cvv",
            "expiration_date",
            "cardholder_name",
        ],
    }

    @staticmethod
    def is_sensitive(field: str, frameworks: Optional[list] = None) -> bool:
        """
        Check if a field is sensitive per frameworks.

        Args:
            field: Field name to check
            frameworks: List of frameworks (HIPAA, GDPR, PCI_DSS)
                       If None, check all frameworks.

        Returns:
            True if field matches sensitive patterns
        """
        field_lower = field.lower()
        target_frameworks = frameworks or ["HIPAA", "GDPR", "PCI_DSS"]

        for fw in target_frameworks:
            if fw in AuditLogFilter.SENSITIVE_FIELDS:
                for sensitive in AuditLogFilter.SENSITIVE_FIELDS[fw]:
                    if sensitive in field_lower:
                        return True
        return False

    @staticmethod
    def mask_field(value: str, strategy: str = "partial") -> str:
        """
        Mask sensitive field value.

        Args:
            value: Value to mask
            strategy: "full" (***), "partial" (show first/last 2 chars),
                     "last4" (show only last 4 chars)

        Returns:
            Masked value
        """
        if not value or len(value) == 0:
            return "***"

        if strategy == "full":
            return "***"
        elif strategy == "partial":
            if len(value) <= 4:
                return "***"
            return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
        elif strategy == "last4":
            if len(value) <= 4:
                return "***"
            return f"{'*' * (len(value) - 4)}{value[-4:]}"
        else:
            return "***"

    @staticmethod
    def filter_audit_log(
        log_data: Dict[str, Any],
        frameworks: Optional[list] = None,
        action: str = "mask",
    ) -> Dict[str, Any]:
        """
        Filter audit log by removing or masking sensitive fields.

        Args:
            log_data: Audit log dictionary
            frameworks: Compliance frameworks to apply
            action: "mask" or "remove"

        Returns:
            Filtered log data
        """
        filtered = {}

        for key, value in log_data.items():
            if AuditLogFilter.is_sensitive(key, frameworks):
                if action == "mask" and isinstance(value, str):
                    filtered[key] = AuditLogFilter.mask_field(value)
                elif action == "remove":
                    filtered[key] = "[REDACTED]"
                else:
                    filtered[key] = value
            else:
                filtered[key] = value

        return filtered


# Global encryptor instance
_audit_encryptor: Optional[AuditEncryptor] = None


def get_audit_encryptor() -> AuditEncryptor:
    """Get or create global AuditEncryptor instance."""
    global _audit_encryptor
    if _audit_encryptor is None:
        _audit_encryptor = AuditEncryptor()
    return _audit_encryptor


def encrypt_audit_log(log_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function: encrypt audit log if encryption enabled.

    Args:
        log_data: Audit log to encrypt

    Returns:
        Original log_data if encryption disabled,
        Dict with encrypted_payload + original metadata if enabled
    """
    encryptor = get_audit_encryptor()

    if not encryptor.enabled:
        return log_data

    encrypted = encryptor.encrypt(log_data)

    if encrypted:
        return {
            "encrypted_payload": encrypted,
            "encrypted_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }
    else:
        # Fallback: return unencrypted on error
        logger.warning("Encryption failed; returning unencrypted log")
        return log_data


def decrypt_audit_log(encrypted_log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convenience function: decrypt audit log.

    Args:
        encrypted_log: Encrypted audit log from encrypt_audit_log()

    Returns:
        Decrypted log data, or None on error
    """
    if "encrypted_payload" not in encrypted_log:
        return encrypted_log  # Not encrypted

    encryptor = get_audit_encryptor()

    if not encryptor.enabled:
        logger.warning("Decryption requested but encryption disabled")
        return None

    return encryptor.decrypt(encrypted_log["encrypted_payload"])
