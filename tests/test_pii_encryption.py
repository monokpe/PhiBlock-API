import os

from app.pii_encryption import PIIEncryptor, PIIEncryptedType, get_pii_encryptor


def test_encryptor_disabled_by_default(tmp_env=None):
    # Ensure no key is set
    os.environ.pop("PII_ENCRYPTION_KEY", None)
    enc = PIIEncryptor()
    assert enc.enabled is False
    assert enc.encrypt("secret") == "secret"
    assert enc.decrypt("secret") == "secret"


def test_encrypt_decrypt_roundtrip_with_key(tmp_path, monkeypatch):
    # Generate a Fernet key and set it
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", key)
    enc = PIIEncryptor()
    assert enc.enabled is True
    secret = "sensitive-data-123"
    token = enc.encrypt(secret)
    assert token is not None and token != secret
    plain = enc.decrypt(token)
    assert plain == secret


def test_type_decorator_process(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", key)
    t = PIIEncryptedType()
    original = "email@example.com"
    bound = t.process_bind_param(original, None)
    assert bound is not None and bound != original
    result = t.process_result_value(bound, None)
    assert result == original
