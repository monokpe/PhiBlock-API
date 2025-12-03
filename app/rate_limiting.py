import os
import threading
from datetime import datetime, timezone

import redis
from fastapi import Depends, HTTPException, status

from . import models
from .auth import get_current_user

# Connect to Redis (lazy-ish, but we handle connection errors at runtime)
redis_host = "localhost" if os.environ.get("TESTING") else "redis"
try:
    redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
except Exception:
    # If creating the client fails for any reason, set to None and use in-process fallback
    redis_client = None

# In-memory fallback counter for environments without Redis (per-minute fixed window)
_fallback_lock = threading.Lock()
_fallback_counters = {}  # key -> (minute_str, count)


class RateLimiter:
    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute

    def __call__(self, user: models.APIKey = Depends(get_current_user)):
        rate_limit = user.rate_limit or self.requests_per_minute
        key = f"rate_limit:{user.id}"

        # Using a simple fixed window counter for now
        # A token bucket or sliding window would be more robust
        try:
            if redis_client is None:
                # Use in-process fallback counter (enforces limits within this process)
                minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
                with _fallback_lock:
                    mk, cnt = _fallback_counters.get(key, (None, 0))
                    if mk != minute:
                        _fallback_counters[key] = (minute, 1)
                        return True
                    if cnt >= rate_limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded. Allowed: {rate_limit} requests per minute.",
                        )
                    _fallback_counters[key] = (mk, cnt + 1)
                    return True

            try:
                current_requests = redis_client.get(key)
            except redis.exceptions.RedisError:
                # Redis is unreachable — fall back to in-process counter
                minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
                with _fallback_lock:
                    mk, cnt = _fallback_counters.get(key, (None, 0))
                    if mk != minute:
                        _fallback_counters[key] = (minute, 1)
                        return True
                    if cnt >= rate_limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded. Allowed: {rate_limit} requests per minute.",
                        )
                    _fallback_counters[key] = (mk, cnt + 1)
                    return True

            if current_requests is None:
                redis_client.set(key, 1, ex=60)  # Expire in 60 seconds
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
            # On any Redis error not related to HTTPException, fail-open
            return True
