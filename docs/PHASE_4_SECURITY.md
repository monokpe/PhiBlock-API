# Phase 4 — Security Hardening (Summary)

This document summarizes the security hardening work completed and operational guidance for Phase 4.

## Goals

- Secrets management (secrets manager + env fallback)
- API security (rate limiting, CORS, request signing)
- Column-level PII encryption
- Tamper-evident audit logging
- CI-integrated security scans (Bandit, Safety)

## Environment variables

- `USE_AWS_SECRETS` — when truthy, `app.secrets` will use AWS Secrets Manager.
- `AWS_REGION` — AWS region for Secrets Manager client.
- `DATABASE_URL` — SQLAlchemy database URL (production).
- `PII_ENCRYPTION_KEY` — URL-safe base64 32-byte key for Fernet encryption (or store in secrets manager).
- `AUDIT_ENCRYPTION_SECRET` — master secret for AES-GCM audit log encryption (used by `app.audit_encryption`).
- `AUDIT_LEDGER_KEY` — HMAC key for the append-only audit ledger (`app.audit_ledger`).
- `WEBHOOK_SIGNING_SECRET` — server-side secret used to sign outgoing webhooks and validate incoming ones.
- `ALLOWED_WEBHOOK_DOMAINS` — comma-separated allowlist for webhook destinations.
- `REDIS_URL` — optional redis URL for rate limiting and Celery broker.
- `CORS_ALLOWED_ORIGINS` — optional comma-separated origins for CORS; defaults to `*`.

## Files and Modules

- `app/secrets.py` — secrets manager wrapper (AWS + env fallback).
- `app/security.py` — CORS registration and request-signing middleware. Use `register_security(app)` in `app/main.py`.
- `app/rate_limiting.py` — Redis-backed rate limiter with in-process fallback.
- `app/pii_encryption.py` — Fernet-based PII encryption and SQLAlchemy `TypeDecorator`.
- `app/audit_encryption.py` — AES-GCM for encrypting large audit payloads.
- `app/audit_ledger.py` — append-only, HMAC-signed ledger for tamper evidence.

## CI Integration

- `.github/workflows/ci.yml` now installs and runs:
  - `bandit` (static code security scanner)
  - `safety` (dependency vulnerability scanner against `requirements.txt`)

CI failure behavior: Both tools are executed during the `tests` job and will cause the job to fail if issues are detected.

## Operational Guidance

- Secrets: store `PII_ENCRYPTION_KEY`, `AUDIT_LEDGER_KEY`, and `AUDIT_ENCRYPTION_SECRET` in AWS Secrets Manager and enable `USE_AWS_SECRETS=true` in staging/production.
- Key rotation: rotate Fernet keys carefully — plan backfill to re-encrypt existing data or use versioned keys; `audit_encryption` includes a `version` field to support rotation.
- Ledger: rotate ledger files daily and archive to S3 with SSE; restrict write permissions to the application service account only.
- Rate limiting: use Redis in production and configure `api_key.rate_limit` per-tenant; consider a distributed token-bucket implementation for stricter enforcement.
- Monitoring: alert on Bandit/Safety CI failures, audit ledger verification failures, and high rates of signature verification errors.

## Next Steps

- Add `bandit` baseline suppression file (if necessary) and triage current findings.
- Add `safety` policy to the team runbook for handling dependency advisories.
- Add runtime monitoring for audit ledger integrity (periodic verify job) and automated rotation/archival.

---

This file is a brief operational guide for Phase 4 security hardening. For more details, see `PHASE_HANDOFF.md` and in-code docstrings.
