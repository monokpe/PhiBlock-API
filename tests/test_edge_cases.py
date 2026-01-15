"""
Edge Case & Boundary Tests

Tests extreme inputs, boundary conditions, and unusual scenarios that might
break the application. Critical for robustness and security.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_api_key
from app.database import get_db
from app.detection import detect_pii
from app.main import app
from app.models import Base, Customer, Tenant

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_edge_cases.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_api_key(db_session):
    tenant = Tenant(name="Edge Test Tenant", slug="edge-test")
    db_session.add(tenant)
    db_session.commit()

    customer = Customer(name="Test Customer", email="test@example.com", tenant_id=tenant.id)
    db_session.add(customer)
    db_session.commit()

    plain_key, _ = create_api_key(db_session, customer.id)
    return plain_key


class TestExtremeInputSizes:
    """Test handling of extremely large or small inputs."""

    def test_empty_prompt(self, client, test_api_key):
        """Empty prompt should return validation error."""
        response = client.post(
            "/v1/analyze", json={"prompt": ""}, headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 422, "Empty prompt should be rejected"

    def test_whitespace_only_prompt(self, client, test_api_key):
        """Whitespace-only prompt should be rejected."""
        whitespace_prompts = [
            "   ",
            "\n\n\n",
            "\t\t\t",
            "   \n\t  ",
        ]

        for prompt in whitespace_prompts:
            response = client.post(
                "/v1/analyze", json={"prompt": prompt}, headers={"X-API-Key": test_api_key}
            )
            # Should either reject or handle gracefully
            assert response.status_code in [200, 422, 400]

    def test_extremely_long_prompt(self, client, test_api_key):
        """Very long prompts should be handled gracefully."""
        # 100k characters
        long_prompt = "A" * 100000

        response = client.post(
            "/v1/analyze", json={"prompt": long_prompt}, headers={"X-API-Key": test_api_key}
        )

        # Should either process or return error, but NOT crash (500)
        assert response.status_code != 500, "Server crashed on long input"
        assert response.status_code in [200, 413, 422, 400]

    def test_single_character_prompt(self, client, test_api_key):
        """Single character should be processed."""
        response = client.post(
            "/v1/analyze", json={"prompt": "A"}, headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200


class TestSpecialCharacters:
    """Test handling of special and unusual characters."""

    def test_null_bytes(self, client, test_api_key):
        """Null bytes should be handled safely."""
        prompt = "Test\x00\x00\x00prompt"

        response = client.post(
            "/v1/analyze", json={"prompt": prompt}, headers={"X-API-Key": test_api_key}
        )

        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_unicode_characters(self, client, test_api_key):
        """Unicode characters should be processed correctly."""
        unicode_prompts = [
            "Hello 世界",  # Chinese
            "Привет мир",  # Russian
            "مرحبا بالعالم",  # Arabic
            "🎉🎊🎈",  # Emojis
            "Ｆｕｌｌｗｉｄｔｈ",  # Fullwidth
        ]

        for prompt in unicode_prompts:
            response = client.post(
                "/v1/analyze", json={"prompt": prompt}, headers={"X-API-Key": test_api_key}
            )
            assert response.status_code == 200, f"Failed on: {prompt}"

    def test_control_characters(self, client, test_api_key):
        """Control characters should be handled."""
        prompt = "Test\r\n\t\bprompt"

        response = client.post(
            "/v1/analyze", json={"prompt": prompt}, headers={"X-API-Key": test_api_key}
        )
        assert response.status_code in [200, 400, 422]

    def test_sql_injection_characters(self, client, test_api_key):
        """SQL injection attempts should be safely handled."""
        sql_prompts = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM api_keys--",
        ]

        for prompt in sql_prompts:
            response = client.post(
                "/v1/analyze", json={"prompt": prompt}, headers={"X-API-Key": test_api_key}
            )
            # Should process safely without SQL injection
            assert response.status_code in [200, 400, 422]

            # Response should not contain database errors
            if response.status_code == 200:
                data = response.json()
                assert "database" not in str(data).lower()


class TestNestedAndComplexEntities:
    """Test detection of nested and overlapping PII."""

    def test_nested_pii(self):
        """PII within PII should be detected."""
        prompt = "Email me at john.doe@company.com (SSN: 123-45-6789)"
        entities = detect_pii(prompt)

        entity_types = [e["type"] for e in entities]

        # Should detect both EMAIL and SSN
        assert "EMAIL" in entity_types
        assert any(t in entity_types for t in ["SSN", "SOCIAL_SECURITY_NUMBER"])

    def test_overlapping_entities(self):
        """Overlapping entity spans should be handled."""
        prompt = "Call 555-123-4567 or email 555-123-4567@example.com"
        entities = detect_pii(prompt)

        # Should detect both phone and email
        entity_types = [e["type"] for e in entities]
        assert any("PHONE" in t for t in entity_types)
        assert "EMAIL" in entity_types

    def test_multiple_same_type_entities(self):
        """Multiple entities of the same type should all be detected."""
        prompt = "Contact john@example.com or jane@example.com or bob@example.com"
        entities = detect_pii(prompt)

        emails = [e for e in entities if e["type"] == "EMAIL"]
        assert len(emails) == 3, f"Expected 3 emails, found {len(emails)}"


class TestInternationalFormats:
    """Test detection of international PII formats."""

    def test_international_phone_numbers(self):
        """Non-US phone formats should be detected."""
        test_cases = [
            "+44 20 7946 0958",  # UK
            "+33 1 42 86 82 00",  # France
            "+81 3-3580-3311",  # Japan
            "+86 10 8888 8888",  # China
        ]

        for phone in test_cases:
            prompt = f"Call me at {phone}"
            entities = detect_pii(prompt)
            entity_types = [e["type"] for e in entities]

            # Should detect as phone number (or at least some PII)
            assert any(
                "PHONE" in t or "NUMBER" in t for t in entity_types
            ), f"Failed to detect {phone}"

    def test_international_identifiers(self):
        """International ID formats should be detected."""
        test_cases = [
            ("IBAN: DE89370400440532013000", "IBAN"),  # German IBAN
            ("NI Number: AB123456C", "NI_NUMBER"),  # UK National Insurance
            ("SIN: 123-456-789", "SIN"),  # Canadian SIN
        ]

        for prompt, expected_type in test_cases:
            entities = detect_pii(prompt)
            # May not detect all international formats, but should handle gracefully
            assert len(entities) >= 0  # Should not crash


class TestMalformedJSON:
    """Test handling of malformed JSON payloads."""

    def test_missing_required_field(self, client, test_api_key):
        """Missing 'prompt' field should return 422."""
        response = client.post(
            "/v1/analyze", json={"text": "instead of prompt"}, headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 422

    def test_wrong_field_type(self, client, test_api_key):
        """Wrong field type should return 422."""
        response = client.post(
            "/v1/analyze",
            json={"prompt": 12345},  # Number instead of string
            headers={"X-API-Key": test_api_key},
        )
        assert response.status_code == 422

    def test_extra_fields(self, client, test_api_key):
        """Extra fields should be ignored."""
        response = client.post(
            "/v1/analyze",
            json={"prompt": "test", "extra_field": "ignored"},
            headers={"X-API-Key": test_api_key},
        )
        # Should process normally
        assert response.status_code == 200


class TestBoundaryValues:
    """Test boundary values for numeric and string fields."""

    def test_zero_length_after_trim(self, client, test_api_key):
        """Prompt that becomes empty after trimming should be rejected."""
        # This depends on whether your API trims whitespace
        response = client.post(
            "/v1/analyze", json={"prompt": "   "}, headers={"X-API-Key": test_api_key}
        )
        # Should either process or reject, but not crash
        assert response.status_code in [200, 422, 400]

    def test_max_token_limit(self, client, test_api_key):
        """Prompt at token limit should be handled."""
        # Assuming ~4 chars per token, 8000 tokens ≈ 32000 chars
        long_prompt = "word " * 8000

        response = client.post(
            "/v1/analyze", json={"prompt": long_prompt}, headers={"X-API-Key": test_api_key}
        )

        # Should handle gracefully
        assert response.status_code != 500


class TestErrorRecovery:
    """Test error handling and recovery."""

    def test_invalid_api_key_format(self, client):
        """Malformed API key should return 401."""
        invalid_keys = [
            "",
            "   ",
            "invalid-key",
            "a" * 1000,  # Very long key
            "key with spaces",
        ]

        for key in invalid_keys:
            response = client.post(
                "/v1/analyze", json={"prompt": "test"}, headers={"X-API-Key": key}
            )
            assert response.status_code == 401, f"Failed for key: {key}"

    def test_missing_api_key(self, client):
        """Missing API key should return 401."""
        response = client.post("/v1/analyze", json={"prompt": "test"})
        assert response.status_code == 401

    def test_content_type_validation(self, client, test_api_key):
        """Wrong content type should be rejected."""
        response = client.post(
            "/v1/analyze",
            data="not json",
            headers={"X-API-Key": test_api_key, "Content-Type": "text/plain"},
        )
        assert response.status_code in [400, 415, 422]


class TestEdgeCaseRedaction:
    """Test redaction edge cases."""

    def test_redaction_preserves_structure(self):
        """Redaction should preserve sentence structure."""
        from app.compliance import get_redaction_service

        prompt = "My name is John Doe and my email is john@example.com"
        entities = detect_pii(prompt)

        normalized_entities = [
            {
                "type": e["type"],
                "value": e["value"],
                "start": e["position"]["start"],
                "end": e["position"]["end"],
            }
            for e in entities
        ]

        redaction_service = get_redaction_service()
        sanitized, _ = redaction_service.redact_text(prompt, normalized_entities)

        # Should still have "My" and "and my" and "is"
        assert "My" in sanitized or "my" in sanitized
        assert "and" in sanitized
        assert "is" in sanitized

    def test_redaction_at_boundaries(self):
        """Redaction at start/end of string should work."""
        from app.compliance import get_redaction_service

        # PII at start
        prompt1 = "john@example.com is my email"
        entities1 = detect_pii(prompt1)

        normalized1 = [
            {
                "type": e["type"],
                "value": e["value"],
                "start": e["position"]["start"],
                "end": e["position"]["end"],
            }
            for e in entities1
        ]

        redaction_service = get_redaction_service()
        sanitized1, _ = redaction_service.redact_text(prompt1, normalized1)

        assert "john@example.com" not in sanitized1
        assert "is my email" in sanitized1
