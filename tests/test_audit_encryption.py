"""Tests for audit encryption module."""


import os
import sys
from unittest.mock import patch

# Reload the audit_encryption module to ensure cryptography import is fresh
if "app.audit_encryption" in sys.modules:
    del sys.modules["app.audit_encryption"]

from app.audit_encryption import (
    AuditEncryptor,
    AuditLogFilter,
    decrypt_audit_log,
    encrypt_audit_log,
    get_audit_encryptor,
)


class TestAuditEncryptor:
    """Tests for AuditEncryptor class."""

    def test_encryptor_disabled_when_no_secret(self):
        """Encryptor should be disabled if no secret provided."""
        encryptor = AuditEncryptor(master_secret="")
        assert not encryptor.enabled

    def test_encrypt_returns_none_when_disabled(self):
        """Encryption should return None when disabled."""
        encryptor = AuditEncryptor(master_secret="")
        result = encryptor.encrypt({"data": "test"})
        assert result is None

    def test_decrypt_returns_none_when_disabled(self):
        """Decryption should return None when encryption disabled."""
        encryptor = AuditEncryptor(master_secret="")
        result = encryptor.decrypt({"ciphertext": "abc", "nonce": "def", "salt": "ghi"})
        assert result is None


class TestAuditLogFilter:
    """Tests for AuditLogFilter class."""

    def test_is_sensitive_hipaa_fields(self):
        """Should identify HIPAA-sensitive fields."""
        assert AuditLogFilter.is_sensitive("ssn", ["HIPAA"])
        assert AuditLogFilter.is_sensitive("medical_record_number", ["HIPAA"])
        assert AuditLogFilter.is_sensitive("password", ["HIPAA"])

    def test_is_sensitive_gdpr_fields(self):
        """Should identify GDPR-sensitive fields."""
        assert AuditLogFilter.is_sensitive("email", ["GDPR"])
        assert AuditLogFilter.is_sensitive("phone", ["GDPR"])
        assert AuditLogFilter.is_sensitive("ip_address", ["GDPR"])

    def test_is_sensitive_pci_fields(self):
        """Should identify PCI-DSS-sensitive fields."""
        assert AuditLogFilter.is_sensitive("credit_card", ["PCI_DSS"])
        assert AuditLogFilter.is_sensitive("cvv", ["PCI_DSS"])

    def test_is_not_sensitive_for_other_framework(self):
        """Should not mark field as sensitive if not in requested framework."""
        # ssn is HIPAA+GDPR but not PCI_DSS specifically
        assert AuditLogFilter.is_sensitive("ssn", ["GDPR"])

    def test_mask_field_full(self):
        """Full mask should replace entire value with ***."""
        masked = AuditLogFilter.mask_field("sensitive-data", strategy="full")
        assert masked == "***"

    def test_mask_field_partial(self):
        """Partial mask should show first and last 2 chars."""
        masked = AuditLogFilter.mask_field("123456789", strategy="partial")
        assert masked == "12*****89"

    def test_mask_field_last4(self):
        """Last4 mask should show only last 4 chars."""
        masked = AuditLogFilter.mask_field("0123456789", strategy="last4")
        assert masked == "******6789"

    def test_mask_field_short_value(self):
        """Short values should mask to ***."""
        assert AuditLogFilter.mask_field("ab", strategy="partial") == "***"
        assert AuditLogFilter.mask_field("ab", strategy="last4") == "***"

    def test_filter_audit_log_mask_action(self):
        """filter_audit_log with mask should mask sensitive fields."""
        log = {
            "user_id": 123,
            "ssn": "123-45-6789",
            "action": "analyze",
            "email": "test@example.com",
        }

        filtered = AuditLogFilter.filter_audit_log(log, frameworks=["HIPAA"], action="mask")

        assert filtered["user_id"] == 123
        assert filtered["action"] == "analyze"
        assert filtered["ssn"] != "123-45-6789"  # Should be masked
        assert filtered["ssn"] == "12*******89"  # "123-45-6789" is 11 chars: 2 + (11-4=7) + 2

    def test_filter_audit_log_remove_action(self):
        """filter_audit_log with remove should replace sensitive fields."""
        log = {
            "user_id": 123,
            "password": "secret123",
            "action": "login",
        }

        filtered = AuditLogFilter.filter_audit_log(log, frameworks=["HIPAA"], action="remove")

        assert filtered["user_id"] == 123
        assert filtered["action"] == "login"
        assert filtered["password"] == "[REDACTED]"

    def test_filter_audit_log_multiple_frameworks(self):
        """Should apply masks for all requested frameworks."""
        log = {
            "user_id": 123,
            "ssn": "123-45-6789",
            "email": "test@example.com",
            "location": "US",
        }

        filtered = AuditLogFilter.filter_audit_log(log, frameworks=["HIPAA", "GDPR"], action="mask")

        # ssn is HIPAA and GDPR
        assert filtered["ssn"] != "123-45-6789"
        # email is GDPR
        assert filtered["email"] != "test@example.com"
        # location is GDPR
        assert filtered["location"] != "US"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_encrypt_audit_log_disabled_returns_original(self):
        """encrypt_audit_log should return original data when encryption disabled."""
        log = {"user_id": 123, "action": "test"}

        with patch.dict(os.environ, {}, clear=True):
            result = encrypt_audit_log(log)
            assert result == log

    def test_decrypt_audit_log_non_encrypted(self):
        """decrypt_audit_log should return unencrypted log as-is."""
        log = {"user_id": 123, "action": "test"}
        result = decrypt_audit_log(log)
        assert result == log

    def test_get_audit_encryptor_singleton(self):
        """get_audit_encryptor should return the same instance."""
        enc1 = get_audit_encryptor()
        enc2 = get_audit_encryptor()
        assert enc1 is enc2
