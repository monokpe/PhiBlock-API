"""
Tests for Cache Service.

Comprehensive tests for request deduplication caching.
"""


from unittest.mock import MagicMock, patch


from app.cache_service import (
    cache_result,
    clear_tenant_cache,
    generate_cache_key,
    get_cache_stats,
    get_cached_result,
)


def test_generate_cache_key():
    """Test cache key generation."""
    tenant_id = "550e8400-e29b-41d4-a716-446655440000"
    prompt = "Test prompt"

    key = generate_cache_key(prompt, tenant_id)

    # Should have correct format
    assert key.startswith("guardrails:cache:")
    assert tenant_id in key

    # Same prompt should generate same key
    key2 = generate_cache_key(prompt, tenant_id)
    assert key == key2

    # Different prompt should generate different key
    key3 = generate_cache_key("Different prompt", tenant_id)
    assert key != key3


def test_generate_cache_key_tenant_isolation():
    """Test that different tenants get different cache keys."""
    prompt = "Same prompt"
    tenant_a = "tenant-a-uuid"
    tenant_b = "tenant-b-uuid"

    key_a = generate_cache_key(prompt, tenant_a)
    key_b = generate_cache_key(prompt, tenant_b)

    assert key_a != key_b
    assert tenant_a in key_a
    assert tenant_b in key_b


@patch("app.cache_service.redis_client")
@patch("app.cache_service.REDIS_AVAILABLE", True)
@patch("app.cache_service.CACHE_ENABLED", True)
def test_cache_result_success(mock_redis):
    """Test successfully caching a result."""
    tenant_id = "test-tenant"
    prompt = "Test prompt"
    result = {"status": "completed", "data": "test"}

    # Mock Redis setex
    mock_redis.setex = MagicMock(return_value=True)

    success = cache_result(prompt, tenant_id, result, ttl=60)

    assert success is True
    mock_redis.setex.assert_called_once()


@patch("app.cache_service.redis_client")
@patch("app.cache_service.REDIS_AVAILABLE", True)
@patch("app.cache_service.CACHE_ENABLED", True)
def test_get_cached_result_hit(mock_redis):
    """Test retrieving a cached result (cache hit)."""
    tenant_id = "test-tenant"
    prompt = "Test prompt"
    cached_data = '{"status": "completed", "cached": true}'

    # Mock Redis get
    mock_redis.get = MagicMock(return_value=cached_data)

    result = get_cached_result(prompt, tenant_id)

    assert result is not None
    assert result["status"] == "completed"
    assert result["cached"] is True
    mock_redis.get.assert_called_once()


@patch("app.cache_service.redis_client")
@patch("app.cache_service.REDIS_AVAILABLE", True)
@patch("app.cache_service.CACHE_ENABLED", True)
def test_get_cached_result_miss(mock_redis):
    """Test cache miss."""
    tenant_id = "test-tenant"
    prompt = "Test prompt"

    # Mock Redis get returning None
    mock_redis.get = MagicMock(return_value=None)

    result = get_cached_result(prompt, tenant_id)

    assert result is None
    mock_redis.get.assert_called_once()


@patch("app.cache_service.CACHE_ENABLED", False)
def test_cache_disabled():
    """Test that caching is skipped when disabled."""
    tenant_id = "test-tenant"
    prompt = "Test prompt"
    result = {"status": "completed"}

    # Should return None/False when disabled
    cached = get_cached_result(prompt, tenant_id)
    assert cached is None

    success = cache_result(prompt, tenant_id, result)
    assert success is False


@patch("app.cache_service.REDIS_AVAILABLE", False)
def test_redis_unavailable():
    """Test graceful degradation when Redis is unavailable."""
    tenant_id = "test-tenant"
    prompt = "Test prompt"
    result = {"status": "completed"}

    # Should return None/False when Redis unavailable
    cached = get_cached_result(prompt, tenant_id)
    assert cached is None

    success = cache_result(prompt, tenant_id, result)
    assert success is False


@patch("app.cache_service.redis_client")
@patch("app.cache_service.REDIS_AVAILABLE", True)
def test_clear_tenant_cache(mock_redis):
    """Test clearing all cache entries for a tenant."""
    tenant_id = "test-tenant"

    # Mock Redis keys and delete
    mock_redis.keys = MagicMock(return_value=["key1", "key2", "key3"])
    mock_redis.delete = MagicMock(return_value=3)

    deleted = clear_tenant_cache(tenant_id)

    assert deleted == 3
    mock_redis.keys.assert_called_once()
    mock_redis.delete.assert_called_once_with("key1", "key2", "key3")


@patch("app.cache_service.redis_client")
@patch("app.cache_service.REDIS_AVAILABLE", True)
def test_get_cache_stats(mock_redis):
    """Test getting cache statistics."""
    # Mock Redis info and dbsize
    mock_redis.info = MagicMock(return_value={"keyspace_hits": 100, "keyspace_misses": 20})
    mock_redis.dbsize = MagicMock(return_value=50)

    stats = get_cache_stats()

    assert stats["enabled"] is True
    assert stats["available"] is True
    assert stats["total_keys"] == 50
    assert stats["hits"] == 100
    assert stats["misses"] == 20


def test_cache_key_consistency():
    """Test that cache keys are consistent across calls."""
    tenant_id = "test-tenant"
    prompt = "Consistent prompt"

    keys = [generate_cache_key(prompt, tenant_id) for _ in range(10)]

    # All keys should be identical
    assert len(set(keys)) == 1


def test_cache_key_different_prompts():
    """Test that different prompts generate different keys."""
    tenant_id = "test-tenant"
    prompts = [
        "Prompt 1",
        "Prompt 2",
        "Prompt 3",
        "Different content",
    ]

    keys = [generate_cache_key(p, tenant_id) for p in prompts]

    # All keys should be unique
    assert len(set(keys)) == len(prompts)
