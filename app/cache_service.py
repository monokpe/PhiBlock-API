"""
Request Caching Service for Deduplication.

Provides tenant-aware caching of analysis results to avoid re-processing
identical prompts within a configurable time window.
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 minutes default

try:
    import redis

    REDIS_AVAILABLE = True
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except (ImportError, redis.ConnectionError) as e:
    REDIS_AVAILABLE = False
    redis_client = None
    logger.warning(f"Redis not available: {e}. Caching will be disabled.")


def generate_cache_key(prompt: str, tenant_id: str) -> str:
    """
    Generate a tenant-scoped cache key for a prompt.

    Args:
        prompt: The prompt text
        tenant_id: The tenant UUID

    Returns:
        Cache key in format: guardrails:cache:{tenant_id}:{prompt_hash}
    """
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    return f"guardrails:cache:{tenant_id}:{prompt_hash}"


def get_cached_result(prompt: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached analysis result for a prompt.

    Args:
        prompt: The prompt text
        tenant_id: The tenant UUID

    Returns:
        Cached result dict if found, None otherwise
    """
    if not CACHE_ENABLED or not REDIS_AVAILABLE or not redis_client:
        return None

    try:
        cache_key = generate_cache_key(prompt, tenant_id)
        cached_data = redis_client.get(cache_key)

        if cached_data:
            logger.info(f"Cache hit for tenant {tenant_id}")
            return json.loads(cached_data)

        logger.debug(f"Cache miss for tenant {tenant_id}")
        return None

    except Exception as e:
        logger.error(f"Error retrieving from cache: {e}")
        return None


def cache_result(
    prompt: str, tenant_id: str, result: Dict[str, Any], ttl: Optional[int] = None
) -> bool:
    """
    Cache an analysis result.

    Args:
        prompt: The prompt text
        tenant_id: The tenant UUID
        result: The analysis result to cache
        ttl: Time-to-live in seconds (default: CACHE_TTL)

    Returns:
        True if cached successfully, False otherwise
    """
    if not CACHE_ENABLED or not REDIS_AVAILABLE or not redis_client:
        return False

    try:
        cache_key = generate_cache_key(prompt, tenant_id)
        ttl = ttl or CACHE_TTL

        cached_data = json.dumps(result)

        redis_client.setex(cache_key, ttl, cached_data)
        logger.info(f"Cached result for tenant {tenant_id} (TTL: {ttl}s)")
        return True

    except Exception as e:
        logger.error(f"Error caching result: {e}")
        return False


def clear_tenant_cache(tenant_id: str) -> int:
    """
    Clear all cached results for a specific tenant.

    Args:
        tenant_id: The tenant UUID

    Returns:
        Number of keys deleted
    """
    if not REDIS_AVAILABLE or not redis_client:
        return 0

    try:
        pattern = f"guardrails:cache:{tenant_id}:*"
        keys = redis_client.keys(pattern)

        if keys:
            deleted = redis_client.delete(*keys)
            logger.info(f"Cleared {deleted} cache entries for tenant {tenant_id}")
            return deleted

        return 0

    except Exception as e:
        logger.error(f"Error clearing tenant cache: {e}")
        return 0


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.

    Returns:
        Dict with cache stats (enabled, available, key count)
    """
    stats = {
        "enabled": CACHE_ENABLED,
        "available": REDIS_AVAILABLE,
        "ttl": CACHE_TTL,
    }

    if REDIS_AVAILABLE and redis_client:
        try:
            info = redis_client.info("stats")
            stats["total_keys"] = redis_client.dbsize()
            stats["hits"] = info.get("keyspace_hits", 0)
            stats["misses"] = info.get("keyspace_misses", 0)
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")

    return stats
