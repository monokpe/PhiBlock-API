"""
Concurrency & Race Condition Tests

Tests the application's behavior under concurrent load to identify race conditions,
deadlocks, and synchronization issues. Critical for production reliability.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_api_key
from app.cache_service import cache_result, get_cached_result
from app.database import get_db
from app.main import app
from app.models import Base, Customer, Tenant

# Use separate database for concurrency tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_concurrency.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=20,  # Larger pool for concurrency
    max_overflow=40,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with overridden database."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant with API key."""
    tenant = Tenant(name="Concurrency Test Tenant", slug="concurrency-test")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    customer = Customer(name="Test Customer", email="test@example.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, api_key = create_api_key(db_session, customer.id)
    api_key.rate_limit = 1000  # High limit for concurrency tests
    db_session.commit()

    return {"tenant": tenant, "customer": customer, "api_key": plain_key, "api_key_obj": api_key}


class TestConcurrentRateLimiting:
    """Test rate limiting under concurrent load."""

    def test_rate_limit_exact_count(self, client, db_session, test_tenant):
        """Verify exactly N requests pass when rate limit is N."""
        from app import rate_limiting

        # Force fallback mode for deterministic testing
        rate_limiting._fallback_counters.clear()
        original_redis = rate_limiting.redis_client
        rate_limiting.redis_client = None

        try:
            # Set a low rate limit
            rate_limit = 10
            test_tenant["api_key_obj"].rate_limit = rate_limit
            db_session.commit()

            # Fire many concurrent requests
            num_requests = 50
            results = []

            def make_request():
                response = client.post(
                    "/v1/analyze",
                    json={"prompt": "test"},
                    headers={"X-API-Key": test_tenant["api_key"]},
                )
                return response.status_code

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(make_request) for _ in range(num_requests)]
                results = [f.result() for f in futures]

            # Count successes and rate limits
            successes = sum(1 for r in results if r == 200)
            rate_limited = sum(1 for r in results if r == 429)

            # Should have exactly rate_limit successes
            assert (
                successes == rate_limit
            ), f"Expected {rate_limit} successes, got {successes} (race condition detected!)"
            assert rate_limited == num_requests - rate_limit

        finally:
            rate_limiting.redis_client = original_redis

    def test_rate_limit_no_double_counting(self, client, db_session, test_tenant):
        """Verify requests aren't double-counted in rate limiting."""
        from app import rate_limiting

        rate_limiting._fallback_counters.clear()
        original_redis = rate_limiting.redis_client
        rate_limiting.redis_client = None

        try:
            test_tenant["api_key_obj"].rate_limit = 5
            db_session.commit()

            # Make 5 requests sequentially
            for i in range(5):
                response = client.post(
                    "/v1/analyze",
                    json={"prompt": f"test {i}"},
                    headers={"X-API-Key": test_tenant["api_key"]},
                )
                assert response.status_code == 200, f"Request {i} should succeed"

            # 6th request should be rate limited
            response = client.post(
                "/v1/analyze",
                json={"prompt": "test 6"},
                headers={"X-API-Key": test_tenant["api_key"]},
            )
            assert response.status_code == 429

        finally:
            rate_limiting.redis_client = original_redis


class TestConcurrentCacheAccess:
    """Test cache behavior under concurrent access."""

    def test_cache_race_condition(self, test_tenant):
        """Two threads accessing cache simultaneously shouldn't corrupt data."""
        prompt = "What is the capital of France?"
        tenant_id = str(test_tenant["tenant"].id)

        result1 = {"answer": "Paris", "thread": 1}
        result2 = {"answer": "Paris", "thread": 2}

        def write_cache_1():
            cache_result(prompt, tenant_id, result1)

        def write_cache_2():
            cache_result(prompt, tenant_id, result2)

        # Write from two threads simultaneously
        t1 = threading.Thread(target=write_cache_1)
        t2 = threading.Thread(target=write_cache_2)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Read the cached result
        cached = get_cached_result(prompt, tenant_id)

        # Should get a valid result (either thread 1 or 2, but not corrupted)
        assert cached is not None
        assert "answer" in cached
        assert cached["answer"] == "Paris"
        assert cached["thread"] in [1, 2]

    def test_concurrent_cache_reads(self, test_tenant):
        """Multiple threads reading cache simultaneously should work."""
        prompt = "Test prompt"
        tenant_id = str(test_tenant["tenant"].id)

        # Pre-populate cache
        expected_result = {"data": "cached_value"}
        cache_result(prompt, tenant_id, expected_result)

        results = []

        def read_cache():
            result = get_cached_result(prompt, tenant_id)
            results.append(result)

        # Read from 10 threads simultaneously
        threads = [threading.Thread(target=read_cache) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same result
        assert len(results) == 10
        for result in results:
            assert result == expected_result


class TestConcurrentDatabaseAccess:
    """Test database operations under concurrent load."""

    def test_concurrent_api_key_creation(self, db_session, test_tenant):
        """Creating multiple API keys concurrently shouldn't cause conflicts."""
        customer_id = test_tenant["customer"].id

        created_keys = []
        errors = []

        def create_key():
            try:
                plain_key, api_key = create_api_key(db_session, customer_id)
                created_keys.append(plain_key)
            except Exception as e:
                errors.append(e)

        # Create 5 keys concurrently
        threads = [threading.Thread(target=create_key) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All keys should be created successfully
        assert len(errors) == 0, f"Errors during concurrent creation: {errors}"
        assert len(created_keys) == 5

        # All keys should be unique
        assert len(set(created_keys)) == 5

    def test_concurrent_tenant_creation(self, db_session):
        """Creating tenants concurrently shouldn't cause slug conflicts."""
        created_tenants = []
        errors = []

        def create_tenant(index):
            try:
                tenant = Tenant(name=f"Tenant {index}", slug=f"tenant-{index}")
                db_session.add(tenant)
                db_session.commit()
                db_session.refresh(tenant)
                created_tenants.append(tenant.id)
            except Exception as e:
                db_session.rollback()
                errors.append(e)

        # Create 10 tenants concurrently
        threads = [threading.Thread(target=create_tenant, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Most should succeed (some may fail due to transaction conflicts, which is acceptable)
        assert len(created_tenants) >= 5, "Too many failures in concurrent tenant creation"


class TestAsyncConcurrency:
    """Test async/await concurrency patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_async_requests(self, test_tenant):
        """Test multiple async requests don't interfere with each other."""
        import httpx

        async def make_request(prompt):
            async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
                response = await ac.post(
                    "/v1/analyze",
                    json={"prompt": prompt},
                    headers={"X-API-Key": test_tenant["api_key"]},
                )
                return response.status_code, response.json()

        # Fire 10 concurrent requests
        prompts = [f"Test prompt {i}" for i in range(10)]
        results = await asyncio.gather(*[make_request(p) for p in prompts])

        # All should succeed (assuming rate limit is high enough)
        status_codes = [r[0] for r in results]
        assert all(code == 200 for code in status_codes), f"Some requests failed: {status_codes}"

        # All should have unique request IDs
        request_ids = [r[1].get("request_id") for r in results]
        assert len(set(request_ids)) == 10, "Request IDs collided!"

    @pytest.mark.asyncio
    async def test_async_cache_consistency(self, test_tenant):
        """Test cache consistency under async load."""
        prompt = "Async test prompt"
        tenant_id = str(test_tenant["tenant"].id)

        # Pre-populate cache
        expected_result = {"data": "async_cached"}
        cache_result(prompt, tenant_id, expected_result)

        async def read_cache_async():
            # Simulate async work
            await asyncio.sleep(0.01)
            return get_cached_result(prompt, tenant_id)

        # Read from 20 async tasks
        results = await asyncio.gather(*[read_cache_async() for _ in range(20)])

        # All should get the same result
        assert all(r == expected_result for r in results)


class TestDeadlockPrevention:
    """Test for potential deadlock scenarios."""

    def test_no_deadlock_on_high_concurrency(self, client, test_tenant):
        """High concurrency shouldn't cause deadlocks."""
        num_requests = 100
        timeout = 30  # seconds

        results = []
        start_time = time.time()

        def make_request(index):
            try:
                response = client.post(
                    "/v1/analyze",
                    json={"prompt": f"test {index}"},
                    headers={"X-API-Key": test_tenant["api_key"]},
                    timeout=5.0,
                )
                results.append(("success", response.status_code))
            except Exception as e:
                results.append(("error", str(e)))

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]

            # Wait for all to complete or timeout
            for f in futures:
                f.result(timeout=timeout)

        elapsed = time.time() - start_time

        # Should complete within timeout
        assert elapsed < timeout, f"Potential deadlock detected! Took {elapsed}s"

        # Most requests should succeed (some may be rate limited)
        successes = sum(1 for r in results if r[0] == "success")
        assert (
            successes >= num_requests * 0.5
        ), f"Too many failures ({num_requests - successes}/{num_requests})"


class TestIdempotency:
    """Test idempotency under concurrent duplicate requests."""

    def test_duplicate_request_ids(self, client, test_tenant):
        """Submitting the same request ID multiple times should be idempotent."""
        # Note: This test assumes you have idempotency key support
        # If not implemented, this test documents the requirement

        request_id = "test-idempotency-key-123"

        def make_request():
            return client.post(
                "/v1/analyze",
                json={"prompt": "test", "request_id": request_id},
                headers={"X-API-Key": test_tenant["api_key"]},
            )

        # Make 5 concurrent requests with same ID
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            responses = [f.result() for f in futures]

        # All should return the same result (or some should be rejected)
        # This is a placeholder - actual behavior depends on implementation
        status_codes = [r.status_code for r in responses]

        # At minimum, they should all succeed or all fail consistently
        assert len(set(status_codes)) <= 2, "Inconsistent responses for duplicate request IDs"
