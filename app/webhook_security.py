"""
Webhook security utilities: HMAC signing, allowlist, and optional rate-limiting.

Minimal, opt-in server-wide signing using an env secret (WEBHOOK_SIGNING_SECRET).
Allowlist via env var ALLOWED_WEBHOOK_DOMAINS (comma-separated). Rate-limiting via
Redis if available (WEBHOOK_RATE_LIMIT_PER_MINUTE).

This file intentionally keeps the implementation small to avoid scope creep.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_signing_secret() -> Optional[str]:
    """Return the server-wide signing secret from env or None."""
    return os.getenv("WEBHOOK_SIGNING_SECRET")


def sign_payload(payload: Dict, secret: str) -> Dict[str, str]:
    """Return signature headers for a payload using HMAC-SHA256."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    sig = mac.hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "X-PhiBlock-Signature": f"sha256={sig}",
        "X-PhiBlock-Timestamp": timestamp,
    }


def is_allowed_webhook(url: str) -> bool:
    """Check webhook URL against allowed domains from env."""
    env = os.getenv("ALLOWED_WEBHOOK_DOMAINS", "").strip()
    if not env:
        logger.warning("ALLOWED_WEBHOOK_DOMAINS not configured; rejecting by default")
        return False

    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        allowed = [h.strip().lower() for h in env.split(",") if h.strip()]
        host_l = host.lower()
        for a in allowed:
            if host_l == a or host_l.endswith("." + a):
                return True
        logger.warning(f"Webhook host {host} not in allowlist")
        return False
    except Exception:
        logger.exception("Error parsing webhook URL for allowlist check")
        return False


def is_rate_limited(url: str) -> bool:
    """Check and increment rate limit for host using Redis if configured."""
    limit = int(os.getenv("WEBHOOK_RATE_LIMIT_PER_MINUTE", "0") or 0)
    if limit <= 0:
        return False

    redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
    if not redis_url:
        logger.debug("No Redis URL configured for webhook rate limiting; failing open")
        return False

    try:
        import redis

        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        r = redis.from_url(redis_url)
        key = f"webhook_rate:{host}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 70)
        if count > limit:
            logger.warning(f"Rate limit exceeded for webhook host {host}: {count}/{limit}")
            return True
        return False
    except Exception:
        logger.exception("Rate limit check failed; failing open")
        return False
