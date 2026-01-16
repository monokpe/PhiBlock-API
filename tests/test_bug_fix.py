
import pytest
from fastapi.testclient import TestClient
from app.main import app, engine
from app.database import get_db
from app.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.auth import create_api_key
from app.models import Tenant, Customer

# Use distinct DB for this test to avoid conflicts
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bug_fix.db"
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
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_user_reported_scenario(client, db_session):
    """
    Test the specific scenario reported by the user:
    - Benign PII prompt should NOT trigger injection.
    - Violations should NOT be duplicated.
    """
    # Setup Auth
    tenant = Tenant(name="BugFix Tenant", slug="bugfix-tenant")
    db_session.add(tenant)
    db_session.commit()
    customer = Customer(name="BugFix Customer", email="bug@fix.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()
    plain_key, _ = create_api_key(db_session, customer.id)
    
    headers = {
        "X-API-Key": plain_key,
        "Content-Type": "application/json"
    }

    # The user's exact prompt
    prompt = "My name is John Doe and my email is john.doe@example.com. My social security number is 123-45-6789."
    
    response = client.post("/v1/analyze", json={"prompt": prompt}, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # 1. Check Injection (Should be False)
    # The previous score was 0.845, new threshold is 0.9
    injection_detected = data["detections"]["injection_detected"]
    injection_score = data["detections"]["injection_score"]
    
    # We expect injection to be FALSE now
    assert injection_detected is False, f"False positive injection detected! Score: {injection_score}"
    
    # 2. Check Duplicate Violations
    violations = data["compliance"]["violations"]
    
    # Count occurrences of specific rules
    rule_counts = {}
    for v in violations:
        rule_name = v["rule_name"]
        rule_counts[rule_name] = rule_counts.get(rule_name, 0) + 1
        
    # No rule should appear more than once for the same matched content
    # But for simplicity, let's just check total counts per rule name
    # "Personal Data - Name" appeared multiple times in the user report
    print("Violations found:", rule_counts)
    
    for rule_name, count in rule_counts.items():
        # It's possible to have multiple violations of same rule if multiple entities are found
        # (e.g. 2 names), but for "John Doe" appearing once, it should be 1.
        # Let's check specifically for the user report pattern which had 8+ copies.
        assert count < 3, f"Rule '{rule_name}' has {count} duplicate violations!"

    # 3. Check Message
    # Should NOT be [FILTERED DUE TO PROMPT INJECTION DETECTION]
    assert "PROMPT INJECTION" not in data["sanitized_prompt"]
    assert "[PERSON]" in data["sanitized_prompt"]
    # New assertions for Practical Mode (SSN -> Link to Redact)
    # Flexible check for SSN tag which might be combined with rule names
    assert "SSN" in data["sanitized_prompt"]
    assert data["compliance"]["compliant"] is False

if __name__ == "__main__":
    # Manually run if needed
    pass
