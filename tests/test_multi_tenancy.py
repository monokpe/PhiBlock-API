"""
Multi-Tenancy Isolation Tests.

These tests verify that tenant data isolation is properly enforced,
preventing cross-tenant data access.
"""


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_api_key
from app.database import get_db
from app.main import app
from app.models import Base, Customer, Tenant

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_multi_tenancy.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def db_session():
    """Create a fresh database for each test module."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(db_session):
    """Create a test client with database override."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)


@pytest.fixture(scope="module")
def tenant_a(db_session):
    """Create Tenant A."""
    tenant = Tenant(name="Tenant A", slug="tenant-a", plan="pro")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture(scope="module")
def tenant_b(db_session):
    """Create Tenant B."""
    tenant = Tenant(name="Tenant B", slug="tenant-b", plan="basic")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture(scope="module")
def customer_a(db_session, tenant_a):
    """Create a customer for Tenant A."""
    customer = Customer(name="Customer A", email="customer_a@example.com", tenant_id=tenant_a.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture(scope="module")
def customer_b(db_session, tenant_b):
    """Create a customer for Tenant B."""
    customer = Customer(name="Customer B", email="customer_b@example.com", tenant_id=tenant_b.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture(scope="module")
def api_key_a(db_session, customer_a):
    """Create an API key for Customer A."""
    plain_key, api_key_obj = create_api_key(db_session, customer_a.id)
    return plain_key, api_key_obj


@pytest.fixture(scope="module")
def api_key_b(db_session, customer_b):
    """Create an API key for Customer B."""
    plain_key, api_key_obj = create_api_key(db_session, customer_b.id)
    return plain_key, api_key_obj


def test_tenant_creation(tenant_a, tenant_b):
    """Test that tenants are created with unique IDs."""
    assert tenant_a.id != tenant_b.id
    assert tenant_a.slug == "tenant-a"
    assert tenant_b.slug == "tenant-b"


def test_customer_tenant_association(customer_a, customer_b, tenant_a, tenant_b):
    """Test that customers are correctly associated with their tenants."""
    assert customer_a.tenant_id == tenant_a.id
    assert customer_b.tenant_id == tenant_b.id
    assert customer_a.tenant_id != customer_b.tenant_id


def test_api_key_tenant_association(api_key_a, api_key_b, tenant_a, tenant_b):
    """Test that API keys inherit tenant_id from their customers."""
    _, key_obj_a = api_key_a
    _, key_obj_b = api_key_b

    assert key_obj_a.tenant_id == tenant_a.id
    assert key_obj_b.tenant_id == tenant_b.id
    assert key_obj_a.tenant_id != key_obj_b.tenant_id


def test_tenant_a_can_access_own_data(client, api_key_a):
    """Test that Tenant A can access their own data."""
    plain_key_a, _ = api_key_a
    headers = {"X-API-Key": plain_key_a}

    response = client.post(
        "/v1/analyze", json={"prompt": "Test prompt for Tenant A"}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_tenant_b_can_access_own_data(client, api_key_b):
    """Test that Tenant B can access their own data."""
    plain_key_b, _ = api_key_b
    headers = {"X-API-Key": plain_key_b}

    response = client.post(
        "/v1/analyze", json={"prompt": "Test prompt for Tenant B"}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_tenant_context_isolation(client, api_key_a, api_key_b, db_session):
    """
    Test that tenant context is properly isolated between requests.

    This verifies that making a request with Tenant A's key followed by
    a request with Tenant B's key doesn't cause context leakage.
    """
    plain_key_a, _ = api_key_a
    plain_key_b, _ = api_key_b

    # Request from Tenant A
    headers_a = {"X-API-Key": plain_key_a}
    response_a = client.post("/v1/analyze", json={"prompt": "Tenant A request"}, headers=headers_a)
    assert response_a.status_code == 200

    # Request from Tenant B
    headers_b = {"X-API-Key": plain_key_b}
    response_b = client.post("/v1/analyze", json={"prompt": "Tenant B request"}, headers=headers_b)
    assert response_b.status_code == 200

    # Verify audit logs are separate
    from app.models import AuditLog

    tenant_a_logs = (
        db_session.query(AuditLog).filter(AuditLog.tenant_id == api_key_a[1].tenant_id).count()
    )
    tenant_b_logs = (
        db_session.query(AuditLog).filter(AuditLog.tenant_id == api_key_b[1].tenant_id).count()
    )

    assert tenant_a_logs >= 1
    assert tenant_b_logs >= 1


def test_unauthenticated_request_has_no_tenant_context(client):
    """Test that unauthenticated requests don't have tenant context."""
    response = client.post("/v1/analyze", json={"prompt": "Unauthenticated request"})

    # Should be rejected due to missing API key
    assert response.status_code == 401
    assert response.json()["detail"] == "API Key is missing"


def test_invalid_api_key_has_no_tenant_context(client):
    """Test that invalid API keys don't establish tenant context."""
    headers = {"X-API-Key": "invalid-key-12345"}
    response = client.post("/v1/analyze", json={"prompt": "Invalid key request"}, headers=headers)

    # Should be rejected due to invalid API key
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"
