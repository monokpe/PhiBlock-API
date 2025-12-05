"""
Tests for GraphQL queries.
"""

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
def setup_data(db_session):
    # Create Tenant
    tenant = models.Tenant(name="GraphQL Test Tenant", slug="graphql-test", plan="pro")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    # Create Customer
    customer = models.Customer(
        tenant_id=tenant.id, name="GraphQL Customer", email="graphql@example.com"
    )
    db_session.add(customer)
    db_session.commit()

    # Create API Key
    api_key = models.APIKey(
        tenant_id=tenant.id, customer_id=customer.id, key_hash="hash_123", name="GraphQL Key"
    )
    db_session.add(api_key)
    db_session.commit()

    # Create Audit Log
    log = models.AuditLog(
        tenant_id=tenant.id,
        api_key_id=api_key.id,
        endpoint="/v1/analyze",
        http_method="POST",
        status_code=200,
        latency_ms=100,
        prompt_length=10,
    )
    db_session.add(log)
    db_session.commit()

    return {"tenant": tenant, "customer": customer, "api_key": api_key, "log": log}


def test_query_tenants(client, setup_data):
    query = """
    query {
        tenants {
            id
            name
            slug
        }
    }
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "tenants" in data["data"]
    assert len(data["data"]["tenants"]) >= 1
    assert data["data"]["tenants"][0]["slug"] == "graphql-test"


def test_query_tenant_by_id(client, setup_data):
    tenant_id = str(setup_data["tenant"].id)
    query = f"""
    query {{
        tenant(tenantId: "{tenant_id}") {{
            id
            name
            plan
        }}
    }}
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["tenant"]["id"] == tenant_id
    assert data["data"]["tenant"]["name"] == "GraphQL Test Tenant"


def test_query_customers(client, setup_data):
    tenant_id = str(setup_data["tenant"].id)
    query = f"""
    query {{
        customers(tenantId: "{tenant_id}") {{
            id
            name
            email
        }}
    }}
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["customers"]) == 1
    assert data["data"]["customers"][0]["name"] == "GraphQL Customer"


def test_query_audit_logs(client, setup_data):
    tenant_id = str(setup_data["tenant"].id)
    query = f"""
    query {{
        auditLogs(tenantId: "{tenant_id}") {{
            id
            endpoint
            statusCode
        }}
    }}
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["auditLogs"]) == 1
    assert data["data"]["auditLogs"][0]["endpoint"] == "/v1/analyze"
