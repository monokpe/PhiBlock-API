"""
Tests for Analytics API.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import get_db
from app.main import app

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session is closed in db_session fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_db():
    models.Base.metadata.create_all(bind=engine)
    yield
    models.Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_db):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def setup_analytics_data(db_session):
    # Tenant A
    tenant_a = models.Tenant(name="Tenant A", slug="tenant-a")
    db_session.add(tenant_a)
    db_session.commit()

    customer_a = models.Customer(tenant_id=tenant_a.id, name="Cust A", email="a@a.com")
    db_session.add(customer_a)
    db_session.commit()

    import hashlib

    key_hash_a = hashlib.sha256("key-a".encode()).hexdigest()
    api_key_a = models.APIKey(
        tenant_id=tenant_a.id, customer_id=customer_a.id, key_hash=key_hash_a, name="Key A"
    )
    db_session.add(api_key_a)
    db_session.commit()

    # Tenant B
    tenant_b = models.Tenant(name="Tenant B", slug="tenant-b")
    db_session.add(tenant_b)
    db_session.commit()

    customer_b = models.Customer(tenant_id=tenant_b.id, name="Cust B", email="b@b.com")
    db_session.add(customer_b)
    db_session.commit()

    key_hash_b = hashlib.sha256("key-b".encode()).hexdigest()
    api_key_b = models.APIKey(
        tenant_id=tenant_b.id, customer_id=customer_b.id, key_hash=key_hash_b, name="Key B"
    )
    db_session.add(api_key_b)
    db_session.commit()

    # Add logs for Tenant A
    # 1. Normal request
    log1 = models.AuditLog(
        tenant_id=tenant_a.id,
        api_key_id=api_key_a.id,
        endpoint="/v1/analyze",
        http_method="POST",
        status_code=200,
        latency_ms=100,
        timestamp=datetime.datetime.utcnow(),
    )
    # 2. Injection attack
    log2 = models.AuditLog(
        tenant_id=tenant_a.id,
        api_key_id=api_key_a.id,
        endpoint="/v1/analyze",
        http_method="POST",
        status_code=200,
        latency_ms=150,
        injection_score=0.9,
        timestamp=datetime.datetime.utcnow(),
    )
    # 3. PII detected
    log3 = models.AuditLog(
        tenant_id=tenant_a.id,
        api_key_id=api_key_a.id,
        endpoint="/v1/analyze",
        http_method="POST",
        status_code=200,
        latency_ms=120,
        entities_detected=[{"type": "EMAIL", "text": "test@test.com"}],
        timestamp=datetime.datetime.utcnow(),
    )

    db_session.add_all([log1, log2, log3])

    # Add Token Usage for Tenant A
    usage1 = models.TokenUsage(
        tenant_id=tenant_a.id,
        api_key_id=api_key_a.id,
        input_tokens=80,
        output_tokens=20,
        total_tokens=100,
        estimated_cost_usd=0.002,
        timestamp=datetime.datetime.utcnow(),
        endpoint="/v1/analyze",
    )
    db_session.add(usage1)

    # Add logs for Tenant B (should not be seen by A)
    log_b = models.AuditLog(
        tenant_id=tenant_b.id,
        api_key_id=api_key_b.id,
        endpoint="/v1/analyze",
        http_method="POST",
        status_code=200,
        latency_ms=200,
        timestamp=datetime.datetime.utcnow(),
    )
    db_session.add(log_b)

    db_session.commit()

    return {"key_a": "key-a", "key_b": "key-b"}


def test_get_stats(client, setup_analytics_data):
    headers = {"X-API-Key": setup_analytics_data["key_a"]}
    response = client.get("/v1/analytics/stats?range=7d", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_requests"] == 3
    assert data["total_tokens"] == 100
    assert data["estimated_cost"] == 0.002
    assert data["injection_attacks_blocked"] == 1
    assert data["pii_detected_count"] == 1
    # Avg latency: (100 + 150 + 120) / 3 = 123.33
    assert 123 <= data["avg_latency_ms"] <= 124


def test_get_stats_tenant_isolation(client, setup_analytics_data):
    headers = {"X-API-Key": setup_analytics_data["key_b"]}
    response = client.get("/v1/analytics/stats?range=7d", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_requests"] == 1
    assert data["injection_attacks_blocked"] == 0


def test_get_timeseries(client, setup_analytics_data):
    headers = {"X-API-Key": setup_analytics_data["key_a"]}
    response = client.get("/v1/analytics/timeseries?range=7d", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert "data" in data
    assert len(data["data"]) >= 1
    point = data["data"][0]
    assert point["requests"] == 3
    assert point["violations"] == 2  # 1 injection + 1 PII


def test_get_violations(client, setup_analytics_data):
    headers = {"X-API-Key": setup_analytics_data["key_a"]}
    response = client.get("/v1/analytics/violations?range=7d", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # PII
    assert len(data["pii_types"]) == 1
    assert data["pii_types"][0]["type"] == "EMAIL"
    assert data["pii_types"][0]["count"] == 1

    # Injection
    assert len(data["injection_types"]) == 1
    assert data["injection_types"][0]["type"] == "Prompt Injection"
    assert data["injection_types"][0]["count"] == 1
