import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_api_key
from app.database import get_db
from app.main import app
from app.models import Base, Customer, Tenant

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_endpoints.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    # Setup: create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    # Teardown: drop tables
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)


def test_health_check(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.0"}


def test_analyze_endpoint_success(client, db_session):
    tenant = Tenant(name="Endpoint Test Tenant", slug="endpoint-test-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(
        name="Endpoint Test Customer", email="endpoint@example.com", tenant_id=tenant.id
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, _ = create_api_key(db_session, customer.id)
    headers = {"X-API-Key": plain_key}
    response = client.post("/v1/analyze", json={"prompt": "My name is John Doe"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["detections"]["pii_found"] is True


def test_rate_limiting(client, db_session):
    tenant = Tenant(name="Rate Limit Test Tenant", slug="rate-limit-test-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(
        name="Rate Limit Test Customer", email="ratelimit@example.com", tenant_id=tenant.id
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, api_key = create_api_key(db_session, customer.id)
    # Set a low rate limit for this key for testing purposes
    api_key.rate_limit = 2
    db_session.commit()

    headers = {"X-API-Key": plain_key}

    # First two requests should succeed
    assert client.post("/v1/analyze", json={"prompt": "test 1"}, headers=headers).status_code == 200
    assert client.post("/v1/analyze", json={"prompt": "test 2"}, headers=headers).status_code == 200

    # Third request should be rate limited
    response = client.post("/v1/analyze", json={"prompt": "test 3"}, headers=headers)
    assert response.status_code == 429


def test_analyze_endpoint_no_api_key(client):
    response = client.post("/v1/analyze", json={"prompt": "test"})
    assert response.status_code == 401
    assert response.json() == {"detail": "API Key is missing"}


def test_analyze_endpoint_invalid_api_key(client):
    headers = {"X-API-Key": "invalid-key"}
    response = client.post("/v1/analyze", json={"prompt": "test"}, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}


@pytest.mark.parametrize("invalid_payload", [{}, {"text": "instead of prompt"}, {"prompt": ""}])
def test_analyze_endpoint_invalid_input(client, db_session, invalid_payload):
    tenant = Tenant(name="Invalid Input Test Tenant", slug="invalid-input-test-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(
        name="Invalid Input Test Customer", email="invalidinput@example.com", tenant_id=tenant.id
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, _ = create_api_key(db_session, customer.id)
    headers = {"X-API-Key": plain_key}

    response = client.post("/v1/analyze", json=invalid_payload, headers=headers)
    assert response.status_code == 422
