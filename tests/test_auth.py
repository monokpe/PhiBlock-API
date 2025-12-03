import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_api_key
from app.database import get_db
from app.main import app
from app.models import Base, Customer, Tenant

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def db_session():
    # Setup: create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    # Teardown: drop tables
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)


def test_create_api_key(db_session):
    # A dummy customer is needed
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(name="Test Customer", email="test@example.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, api_key_obj = create_api_key(db_session, customer.id)
    assert api_key_obj is not None
    assert api_key_obj.customer_id == customer.id
    assert plain_key is not None


def test_unauthorized_access(client):
    response = client.post("/v1/analyze", json={"prompt": "test"})
    assert response.status_code == 401


def test_authorized_access(client, db_session):
    tenant = Tenant(name="Test Tenant 2", slug="test-tenant-2")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(name="Test Customer 2", email="test2@example.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    plain_key, _ = create_api_key(db_session, customer.id)

    headers = {"X-API-Key": plain_key}
    response = client.post("/v1/analyze", json={"prompt": "test"}, headers=headers)
    assert response.status_code == 200
