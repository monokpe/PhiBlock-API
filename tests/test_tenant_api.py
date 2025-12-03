"""
Tests for Tenant Management API.

Comprehensive tests for tenant CRUD operations.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Base, Tenant

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_tenant_api.db"

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


def test_create_tenant(client):
    """Test creating a new tenant."""
    response = client.post("/v1/tenants", json={"name": "Test Tenant", "plan": "pro"})

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Tenant"
    assert data["slug"] == "test-tenant"
    assert data["plan"] == "pro"
    assert "id" in data
    assert "created_at" in data


def test_create_tenant_with_custom_slug(client):
    """Test creating a tenant with a custom slug."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Custom Slug Tenant", "slug": "my-custom-slug", "plan": "basic"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "my-custom-slug"


def test_create_tenant_duplicate_slug(client):
    """Test that creating a tenant with duplicate slug fails."""
    # Create first tenant
    client.post("/v1/tenants", json={"name": "Duplicate Test", "slug": "duplicate-slug"})

    # Try to create second tenant with same slug
    response = client.post("/v1/tenants", json={"name": "Another Tenant", "slug": "duplicate-slug"})

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_tenant_invalid_plan(client):
    """Test that creating a tenant with invalid plan fails."""
    response = client.post(
        "/v1/tenants", json={"name": "Invalid Plan Tenant", "plan": "invalid-plan"}
    )

    assert response.status_code == 422


def test_create_tenant_invalid_slug(client):
    """Test that creating a tenant with invalid slug format fails."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Invalid Slug", "slug": "Invalid Slug!"},  # Contains spaces and special chars
    )

    assert response.status_code == 422


def test_list_tenants(client):
    """Test listing tenants with pagination."""
    # Create a few tenants
    for i in range(5):
        client.post("/v1/tenants", json={"name": f"List Test Tenant {i}"})

    # List tenants
    response = client.get("/v1/tenants?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert "tenants" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert len(data["tenants"]) > 0


def test_list_tenants_pagination(client):
    """Test tenant list pagination."""
    # Get first page
    response = client.get("/v1/tenants?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["tenants"]) <= 2


def test_get_tenant(client):
    """Test getting a specific tenant."""
    # Create a tenant
    create_response = client.post("/v1/tenants", json={"name": "Get Test Tenant"})
    tenant_id = create_response.json()["id"]

    # Get the tenant
    response = client.get(f"/v1/tenants/{tenant_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tenant_id
    assert data["name"] == "Get Test Tenant"


def test_get_tenant_not_found(client):
    """Test getting a non-existent tenant."""
    response = client.get("/v1/tenants/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_update_tenant(client):
    """Test updating a tenant."""
    # Create a tenant
    create_response = client.post(
        "/v1/tenants", json={"name": "Update Test Tenant", "plan": "basic"}
    )
    tenant_id = create_response.json()["id"]

    # Update the tenant
    response = client.put(
        f"/v1/tenants/{tenant_id}", json={"name": "Updated Tenant Name", "plan": "enterprise"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Tenant Name"
    assert data["plan"] == "enterprise"


def test_update_tenant_partial(client):
    """Test partially updating a tenant."""
    # Create a tenant
    create_response = client.post(
        "/v1/tenants", json={"name": "Partial Update Test", "plan": "pro"}
    )
    tenant_id = create_response.json()["id"]

    # Update only the plan
    response = client.put(f"/v1/tenants/{tenant_id}", json={"plan": "basic"})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Partial Update Test"  # Name unchanged
    assert data["plan"] == "basic"  # Plan updated


def test_update_tenant_not_found(client):
    """Test updating a non-existent tenant."""
    response = client.put(
        "/v1/tenants/00000000-0000-0000-0000-000000000000", json={"name": "Updated Name"}
    )

    assert response.status_code == 404


def test_delete_tenant(client):
    """Test deleting a tenant."""
    # Create a tenant
    create_response = client.post("/v1/tenants", json={"name": "Delete Test Tenant"})
    tenant_id = create_response.json()["id"]

    # Delete the tenant
    response = client.delete(f"/v1/tenants/{tenant_id}")

    assert response.status_code == 204

    # Verify tenant is deleted
    get_response = client.get(f"/v1/tenants/{tenant_id}")
    assert get_response.status_code == 404


def test_delete_tenant_not_found(client):
    """Test deleting a non-existent tenant."""
    response = client.delete("/v1/tenants/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
