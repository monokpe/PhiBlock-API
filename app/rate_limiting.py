"""
Rate limiting module using Redis with fallback.

Provides a RateLimiter dependency for FastAPI that tracks usage via Redis
or an in-memory fallback if Redis is unavailable.
"""

import os
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import redis  # type: ignore
from fastapi import Depends, HTTPException, status

from . import models
from .auth import get_current_user

# Connect to Redis (lazy-ish, but we handle connection errors at runtime)
# Connect to Redis (lazy-ish, but we handle connection errors at runtime)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client: Optional[redis.Redis]
try:
    redis_client = redis.from_url(redis_url, decode_responses=True)
except Exception:
    redis_client = None

_fallback_lock = threading.Lock()
_fallback_counters: Dict[str, Tuple[Optional[str], int]] = {}


class RateLimiter:
    """
    Rate limiter dependency.

    Enforces a strict request limit per user per minute. Use with `Depends()`.
    """

    def __init__(self, requests_per_minute: int):
        """
        Initialize the rate limiter.

        Args:
            requests_per_minute: Number of allowed requests per minute window.
        """
        self.requests_per_minute = requests_per_minute

    def _handle_fallback(self, key: str, rate_limit: int):
        minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        with _fallback_lock:
            mk, cnt = _fallback_counters.get(key, (None, 0))
            if mk != minute:
                _fallback_counters[key] = (minute, 1)
                return True
            if cnt >= rate_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(f"Rate limit exceeded. Allowed: {rate_limit} " f"requests per minute."),
                )
            _fallback_counters[key] = (mk, cnt + 1)
            return True

    def __call__(self, user: models.APIKey = Depends(get_current_user)):
        """
        Check if the request allows proceeding.

        Args:
            user: The authenticated user (injected dependency).

        Raises:
            HTTPException: If the rate limit is exceeded.
        """
        rate_limit = int(user.rate_limit) if user.rate_limit else self.requests_per_minute
        key = f"rate_limit:{user.id}"

        try:
            if redis_client is None:
                return self._handle_fallback(key, rate_limit)

            try:
                current_requests = redis_client.get(key)
            except redis.exceptions.RedisError:
                return self._handle_fallback(key, rate_limit)

            if current_requests is None:
                redis_client.set(key, 1, ex=60)
                return True

            if int(current_requests) >= rate_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Allowed: {rate_limit} requests per minute.",
                )

            redis_client.incr(key)
            return True
        except HTTPException:
            raise
        except Exception:
            return True
