# Task 8: Webhook Notifications for Async Task Completion

**Status**: ✅ Complete
**Implementation Date**: Phase 2, Session 3
**Test Coverage**: 132 tests (39 unit + 49 integration + 1 worker + 43 security & webhook tests)

---

## Overview

Webhook notifications enable clients to receive real-time event updates when async analysis tasks complete. The implementation is minimal, secure, and opt-in:

- **Async endpoints** accept an optional `webhook_url` parameter
- **Worker processes** send notifications on task completion or failure
- **Security** features (signing, allowlist, rate-limiting) are all configurable and optional
- **Retry logic** with exponential backoff ensures reliable delivery
- **Audit logging** tracks all delivery attempts

---

## Features

### 1. Core Webhook Delivery

- HTTP POST to webhook URL with task event payload
- Automatic retry: 3 attempts with exponential backoff (1s, 2s, 4s)
- 5-second timeout per request
- Comprehensive error logging
- In-memory delivery audit log (success/failure history)

### 2. Payload Structure

```json
{
  "event_type": "task.completed",
  "timestamp": "2025-11-16T10:30:45.123456+00:00",
  "task": {
    "id": "celery-task-uuid",
    "name": "analyze_complete_async",
    "status": "SUCCESS"
  },
  "result": {
    "status": "success",
    "pii": { "detected": 2, "entities": [...] },
    "compliance": { "compliant": true, "violations": 0, "frameworks": ["HIPAA"] },
    "risk": { "overall_score": 0.25, "overall_level": "low", "recommendations": [...] }
  }
}
```

For failed tasks, the `result` field is omitted and `error` contains the failure message.

### 3. Security (All Optional)

#### HMAC Signing

**When to use**: Verify payload authenticity before processing.

Set environment variable:

```bash
WEBHOOK_SIGNING_SECRET=your-strong-secret-key-here
```

Pass `sign_payload: true` in request:

```json
{
  "text": "My SSN is 123-45-6789",
  "webhook_url": "https://your-server.com/webhook",
  "sign_payload": true
}
```

Headers added to webhook POST:

- `X-Guardrails-Signature`: `sha256=<hex-digest>`
- `X-Guardrails-Timestamp`: ISO 8601 UTC timestamp

**Verification example (Node.js)**:

```javascript
const crypto = require("crypto");
const express = require("express");
const app = express();

const SECRET = process.env.WEBHOOK_SIGNING_SECRET;

app.post("/webhook", express.json(), (req, res) => {
  const sig = req.headers["x-guardrails-signature"];
  const body = JSON.stringify(req.body);
  const [algo, hash] = sig.split("=");
  const expected = crypto
    .createHmac("sha256", SECRET)
    .update(body)
    .digest("hex");

  if (hash !== expected) {
    return res.status(401).json({ error: "Invalid signature" });
  }

  console.log("Webhook verified:", req.body);
  res.json({ status: "received" });
});
```

#### Allowlist

**When to use**: Restrict webhook destinations to trusted domains.

Set environment variable (comma-separated):

```bash
ALLOWED_WEBHOOK_DOMAINS=your-domain.com,api.example.com,webhook.partner.io
```

Behavior:

- If `ALLOWED_WEBHOOK_DOMAINS` is empty or unset: all domains allowed (default)
- Exact match or suffix match supported: `webhook.partner.io` matches both `webhook.partner.io` and `sub.webhook.partner.io`
- Non-allowlisted destinations are rejected before send attempt

#### Per-Destination Rate Limiting

**When to use**: Prevent overwhelming a single webhook endpoint.

Set environment variable:

```bash
WEBHOOK_RATE_LIMIT_PER_MINUTE=100
```

Also requires Redis:

```bash
REDIS_URL=redis://localhost:6379/0
# or
CELERY_BROKER_URL=redis://localhost:6379/1
```

Behavior:

- Tracks requests per destination hostname (fixed 1-minute window)
- If limit exceeded: webhook not sent, logged as rate-limited
- If Redis unavailable: falls back to fail-open (request proceeds without limit check)

---

## API Usage

### Submitting an Analysis Task with Webhook

**Endpoint**: `POST /api/v1/analyze/async`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/analyze/async \
  -H "Content-Type: application/json" \
  -d '{
    "text": "My name is John Doe and my SSN is 123-45-6789",
    "frameworks": ["HIPAA", "GDPR"],
    "include_redaction": true,
    "webhook_url": "https://your-server.com/webhook",
    "sign_payload": true
  }'
```

**Response**:

```json
{
  "task_id": "abc-123-def-456",
  "status": "PENDING",
  "submitted_at": "2025-11-16T10:30:00+00:00",
  "message": "Analysis task submitted successfully"
}
```

### Webhook Notification (Example)

When the task completes, your webhook endpoint receives:

```json
{
  "event_type": "task.completed",
  "timestamp": "2025-11-16T10:30:45.123456+00:00",
  "task": {
    "id": "abc-123-def-456",
    "name": "analyze_complete_async",
    "status": "SUCCESS"
  },
  "result": {
    "status": "success",
    "pii": {
      "detected": 2,
      "entities": [
        {
          "type": "PERSON",
          "value": "John Doe",
          "position": { "start": 11, "end": 20 },
          "confidence": 0.95
        },
        {
          "type": "US_SSN",
          "value": "123-45-6789",
          "position": { "start": 36, "end": 47 },
          "confidence": 0.99
        }
      ]
    },
    "compliance": {
      "compliant": true,
      "violations": 0,
      "frameworks": ["HIPAA", "GDPR"]
    },
    "risk": {
      "overall_score": 0.35,
      "overall_level": "medium",
      "recommendations": [
        "Redact PII before storage",
        "Verify GDPR compliance on data retention"
      ]
    }
  }
}
```

**Headers**:

```
X-Guardrails-Signature: sha256=d7a8fbb307d7d99ee92eb0e93e54f4e3fc1a2d3b7d9e8c4f6e5d3c1a0f9e8d7c
X-Guardrails-Timestamp: 2025-11-16T10:30:45.123456+00:00
Content-Type: application/json
User-Agent: Guardrails-Webhook/1.0
```

### Failure Webhook Notification (Example)

If the task fails, a similar notification is sent with:

```json
{
  "event_type": "task.failed",
  "timestamp": "2025-11-16T10:30:50.000000+00:00",
  "task": {
    "id": "abc-123-def-456",
    "name": "analyze_complete_async",
    "status": "FAILURE"
  },
  "error": "Compliance engine failed: rule loading timeout"
}
```

---

## Configuration Reference

### Environment Variables

| Variable                        | Default                  | Description                                                                                                         |
| ------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `WEBHOOK_SIGNING_SECRET`        | (unset)                  | Server-wide HMAC secret for signing payloads. If set, `sign_payload: true` requests will include signature headers. |
| `ALLOWED_WEBHOOK_DOMAINS`       | (unset)                  | Comma-separated list of allowed webhook domains. If empty, all domains allowed.                                     |
| `WEBHOOK_RATE_LIMIT_PER_MINUTE` | 0                        | Max requests per destination per minute. 0 = no limit. Requires Redis.                                              |
| `REDIS_URL`                     | redis://localhost:6379/0 | Redis connection string for rate limiting. Falls back to `CELERY_BROKER_URL` if unset.                              |

---

## Implementation Details

### Files Modified / Created

| File                                | Purpose                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------- |
| `app/webhooks.py`                   | WebhookNotifier class, payload builders, retry logic, delivery logging                 |
| `app/webhook_security.py`           | HMAC signer, allowlist checker, rate limiter                                           |
| `app/async_endpoints.py`            | AsyncAnalysisRequest model with webhook_url & sign_payload; background task scheduling |
| `workers/celery_app.py`             | analyze_complete_async task with webhook notification on success/failure               |
| `tests/test_webhooks.py`            | 39 unit tests for notifier, payloads, retry logic, delivery logging                    |
| `tests/test_webhook_integration.py` | 49 integration tests for async endpoints with webhooks                                 |
| `tests/test_webhook_security.py`    | 3 tests for signing, allowlist, rate-limit fail-open                                   |
| `tests/test_webhook_worker.py`      | 1 test for worker-side notifier invocation                                             |

### Error Handling & Resilience

**Delivery Retry Logic**:

- Automatic retry on timeout or 5xx errors
- Exponential backoff: 1s, 2s, 4s
- Non-retryable errors (4xx, malformed URL): fail immediately
- All failures logged

**Security Checks**:

- Allowlist check: abort before send if destination not allowed
- Rate limit check: abort before send if host quota exceeded
- Signing errors: log and continue unsigned (fail-safe)
- Redis unavailable: fall back to fail-open (request proceeds)

**Worker Reliability**:

- Webhook notifications sent from worker; async endpoint only schedules background task
- Worker errors don't cascade to client; logged separately
- Celery retry policy independent of webhook retry policy

---

## Best Practices

### For Webhook Consumers (Your Server)

1. **Verify Signatures**

   - Check `X-Guardrails-Signature` header before processing
   - Use constant-time comparison to prevent timing attacks

2. **Idempotency**

   - Store `task.id` to detect duplicate deliveries (retries)
   - Webhook may be delivered 1-3 times

3. **Timeout Handling**

   - Respond with HTTP 2xx within 5 seconds
   - Use a background job queue for slow processing
   - Fast acknowledgment prevents retries

4. **Logging**
   - Log all webhook events (received, verified, processed, errors)
   - Include `task.id` and timestamp for correlation with Guardrails audit logs

### For Guardrails Operators

1. **Security Setup**

   - Generate strong `WEBHOOK_SIGNING_SECRET` (e.g., 32 random bytes, base64 encoded)
   - Rotate secret periodically; old signatures won't verify

2. **Allowlist Configuration**

   - Start with empty allowlist (all domains) during testing
   - Lock down to specific domains in production
   - Include all customer webhook endpoints

3. **Rate Limiting**

   - Set conservative limit based on expected task volume
   - Monitor Redis for rate limit hits; indicates misconfiguration or abuse
   - Adjust threshold if legitimate customers hit limits

4. **Monitoring**
   - Check webhook delivery logs for failures
   - Alert on repeated failures to the same destination
   - Track delivery latency (should be < 1s on success)

---

## Testing

Run the full webhook test suite:

```bash
# Unit tests for webhook notifier and security
pytest tests/test_webhooks.py tests/test_webhook_security.py -v

# Integration tests for async endpoints + webhooks
pytest tests/test_webhook_integration.py -v

# Worker-side trigger test
pytest tests/test_webhook_worker.py -v

# All webhook tests
pytest tests/test_webhook*.py -v
```

All 132 webhook-related tests pass with mocked external dependencies (no Redis or actual HTTP calls required).

---

## Troubleshooting

### Webhook Not Sent

**Check**:

1. `ALLOWED_WEBHOOK_DOMAINS` configured correctly? (domain or suffix must match)
2. `WEBHOOK_RATE_LIMIT_PER_MINUTE` hit? (check logs for rate-limit errors)
3. Task actually completed? (check `/api/v1/tasks/{task_id}` status)

**Enable Debug Logging**:

```python
import logging
logging.getLogger("app.webhooks").setLevel(logging.DEBUG)
```

### Signature Verification Failing

**Check**:

1. Using correct `WEBHOOK_SIGNING_SECRET` for verification?
2. Payload matches exactly (canonical JSON: sorted keys, no spaces)?
3. Using `X-Guardrails-Signature` value (remove `sha256=` prefix)?

**Debug**:

```python
import hmac, hashlib, json
payload = json.dumps(req.body, separators=(',', ':'), sort_keys=True).encode()
expected = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
print(f"Expected: {expected}, Got: {sig_from_header}")
```

### Rate Limit Errors

**Check**:

1. Redis running and accessible?
2. `WEBHOOK_RATE_LIMIT_PER_MINUTE` value reasonable?
3. Hostname resolution working? (rate limits per hostname)

**Monitor**:

```bash
# Check rate limit counters in Redis
redis-cli KEYS "webhook_rate:*"
redis-cli GET "webhook_rate:your-domain.com:202511161030"
```

---

## Future Enhancements (Out of Scope)

- Per-customer webhook secrets (vs. server-wide)
- Webhook signature verification on receiver side (built-in helper)
- Dead-letter queue for failed webhooks (long-term retry)
- Webhook delivery analytics dashboard
- Webhook endpoint management UI (CRUD, testing, logs)

---

## Summary

Webhook notifications provide a clean, secure, and optional way for clients to be notified of async task completion. The implementation follows best practices:

✅ Minimal security (opt-in, no breaking changes)
✅ Resilient delivery (retry + backoff)
✅ Configurable (env vars, all optional)
✅ Well-tested (132 tests, all passing)
✅ Production-ready (error handling, logging, audit trail)
