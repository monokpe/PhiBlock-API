

from app.compliance.redaction import RedactionService, RedactionStrategy


def test_hmac_redaction_with_key(monkeypatch):
    monkeypatch.setenv("PII_REDACTION_KEY", "super-secret-key")
    svc = RedactionService(strategy=RedactionStrategy.HASH_REPLACEMENT)
    original = "user@example.com"
    redacted, records = svc.redact_text(
        original,
        [{"value": original, "start": 0, "end": len(original), "type": "EMAIL"}],
    )
    assert records and "redacted" in records[0]
    # Redacted label should include EMAIL and a hex suffix
    assert records[0]["redacted"].startswith("[EMAIL:")


def test_sha256_fallback_no_key(monkeypatch):
    monkeypatch.delenv("PII_REDACTION_KEY", raising=False)
    svc = RedactionService(strategy=RedactionStrategy.HASH_REPLACEMENT)
    original = "user@example.com"
    redacted, records = svc.redact_text(
        original,
        [{"value": original, "start": 0, "end": len(original), "type": "EMAIL"}],
    )
    assert records and "redacted" in records[0]
    assert records[0]["redacted"].startswith("[EMAIL:")
