
import pytest
from fastapi.testclient import TestClient
from app.main import app, engine
from app.database import get_db
from app.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.auth import create_api_key
from app.models import Tenant, Customer

# Use distinct DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_secrets.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    # Mock Injection Detection to avoid False Positives
    from unittest.mock import patch
    # Patch get_injection_score inside app.main or wherever it's used
    with patch("app.main.get_injection_score", return_value=0.0):
        # Flush Redis
        try:
            from app.cache_service import redis_client
            if redis_client:
                redis_client.flushall()
        except Exception as e:
            print(f"Redis flush failed: {e}")

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()

def test_secrets_redaction(client, db_session):
    # Setup Auth
    tenant = Tenant(name="Secrets Tenant", slug="secrets-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(name="Sec Customer", email="sec@test.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()
    plain_key, _ = create_api_key(db_session, customer.id)
    
    headers = {"X-API-Key": plain_key, "Content-Type": "application/json"}

    # 1. AWS Key Redaction
    # Standard AKIA pattern (20 chars starting with AKIA)
    aws_key = "AKIAIOSFODNN7EXAMPLE" 
    prompt = f"Key: {aws_key}"
    
    response = client.post("/v1/analyze", json={"prompt": prompt}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    print("Full Response Data:", data)
    print("Sanitized:", data["sanitized_prompt"])
    assert aws_key not in data["sanitized_prompt"]
    assert "[Secret - AWS Access Key]" in data["sanitized_prompt"] or "[SECRET]" in data["sanitized_prompt"] or "REDACTED" in data["sanitized_prompt"] or "****" in data["sanitized_prompt"]
    # Based on redaction.py token strategy, it should be [Secret - AWS Access Key] or similar derived from entity type/rule name
    
    # 2. Confidential Block
    confidential_prompt = "This is INTERNAL USE ONLY. Do not share."
    response = client.post("/v1/analyze", json={"prompt": confidential_prompt}, headers=headers)
    
    # Expecting Block (403 or similar)
    print("Confidential Response:", response.json())
    # If blocked, status might be 'blocked' in body or 403 status code
    # App usually returns 403 for BLOCK action
    assert response.status_code == 403 or (response.status_code == 200 and response.json().get("status") == "blocked")
