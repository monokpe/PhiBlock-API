from app import webhook_security


def test_sign_payload_headers_format():
    payload = {"event": "test", "a": 1}
    secret = "supersecret"
    headers = webhook_security.sign_payload(payload, secret)

    assert "X-Guardrails-Signature" in headers
    assert headers["X-Guardrails-Signature"].startswith("sha256=")
    assert "X-Guardrails-Timestamp" in headers


def test_is_allowed_webhook_with_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_WEBHOOK_DOMAINS", "example.com,allowed.test")
    assert webhook_security.is_allowed_webhook("https://example.com/hook")
    assert webhook_security.is_allowed_webhook("https://sub.allowed.test/endpoint")
    assert not webhook_security.is_allowed_webhook("https://malicious.com/hook")


def test_rate_limit_fails_open_without_redis(monkeypatch):
    # Configure a rate limit but no REDIS URL -> fail-open should return False
    monkeypatch.setenv("WEBHOOK_RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)

    assert webhook_security.is_rate_limited("https://example.com/hook") is False
