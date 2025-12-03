"""
Tests for Redaction Service

Tests for:
- Redaction strategies (full mask, token, partial, hash)
- Entity-based redaction
- Pattern-based redaction
- Redaction pipelines
- Audit trail mapping
"""

import pytest

from app.compliance.models import ComplianceAction
from app.compliance.redaction import (
    RedactionPipeline,
    RedactionService,
    RedactionStrategy,
    get_redaction_service,
    reset_redaction_service,
)


class TestRedactionStrategies:
    """Test different redaction strategies"""

    def test_full_mask_strategy(self):
        """Test full mask strategy replaces with ****"""
        service = RedactionService(RedactionStrategy.FULL_MASK)

        text = "My name is John Doe"
        entities = [{"type": "PERSON", "value": "John Doe", "start": 11, "end": 19}]

        redacted, records = service.redact_text(text, entities)

        assert redacted == "My name is ****"
        assert records[0]["redacted"] == "****"

    def test_token_replacement_strategy(self):
        """Test token replacement with entity type"""
        service = RedactionService(RedactionStrategy.TOKEN_REPLACEMENT)

        text = "Email: john@example.com"
        entities = [{"type": "EMAIL", "value": "john@example.com", "start": 7, "end": 23}]

        redacted, records = service.redact_text(text, entities)

        assert redacted == "Email: [EMAIL]"
        assert records[0]["redacted"] == "[EMAIL]"

    def test_partial_mask_strategy(self):
        """Test partial mask shows first and last character"""
        service = RedactionService(RedactionStrategy.PARTIAL_MASK)

        text = "SSN: 123-45-6789"
        entities = [{"type": "SSN", "value": "123-45-6789", "start": 5, "end": 16}]

        redacted, records = service.redact_text(text, entities)

        assert redacted == "SSN: 1*********9"
        assert "*" in records[0]["redacted"]
        assert records[0]["redacted"][0] == "1"
        assert records[0]["redacted"][-1] == "9"

    def test_hash_replacement_strategy(self):
        """Test hash replacement for consistency"""
        service = RedactionService(RedactionStrategy.HASH_REPLACEMENT)

        text = "Card: 4532-1234-5678-9010"
        entities = [
            {
                "type": "CREDIT_CARD",
                "value": "4532-1234-5678-9010",
                "start": 6,
                "end": 25,
            }
        ]

        redacted, records = service.redact_text(text, entities)

        assert "[CREDIT_CARD:" in redacted
        assert records[0]["redacted"].startswith("[CREDIT_CARD:")

    def test_short_value_partial_mask(self):
        """Test partial mask on short values"""
        service = RedactionService(RedactionStrategy.PARTIAL_MASK)

        text = "ID: 123"
        entities = [{"type": "ID", "value": "123", "start": 4, "end": 7}]

        redacted, records = service.redact_text(text, entities)

        # Short values get fully masked
        assert redacted == "ID: ***"


class TestEntityRedaction:
    """Test entity-based redaction"""

    def test_single_entity_redaction(self):
        """Test redacting a single entity"""
        service = RedactionService()

        text = "Contact John Smith at john@example.com"
        entities = [
            {"type": "PERSON", "value": "John Smith", "start": 8, "end": 18},
        ]

        redacted, records = service.redact_text(text, entities)

        assert "[PERSON]" in redacted
        assert "John Smith" not in redacted
        assert len(records) == 1

    def test_multiple_entities_redaction(self):
        """Test redacting multiple entities"""
        service = RedactionService()

        text = "John Smith's SSN is 123-45-6789"
        entities = [
            {"type": "PERSON", "value": "John Smith", "start": 0, "end": 10},
            {"type": "SSN", "value": "123-45-6789", "start": 21, "end": 32},
        ]

        redacted, records = service.redact_text(text, entities)

        assert "[PERSON]" in redacted
        assert "[SSN]" in redacted
        assert "John Smith" not in redacted
        assert "123-45-6789" not in redacted
        assert len(records) == 2

    def test_overlapping_entities_handled(self):
        """Test handling of overlapping entities"""
        service = RedactionService()

        text = "My email is john@example.com"
        entities = [
            {"type": "EMAIL", "value": "john@example.com", "start": 12, "end": 28},
            {"type": "PERSON", "value": "john", "start": 12, "end": 16},
        ]

        # Should process without error (last one wins in reverse sort)
        redacted, records = service.redact_text(text, entities)

        assert "@" not in redacted or "[" in redacted
        assert len(records) > 0

    def test_empty_entity_list(self):
        """Test with no entities to redact"""
        service = RedactionService()

        text = "This is safe text"
        entities = []

        redacted, records = service.redact_text(text, entities)

        assert redacted == text
        assert len(records) == 0

    def test_invalid_entity_positions(self):
        """Test handling of invalid entity positions"""
        service = RedactionService()

        text = "Hello world"
        entities = [
            {"type": "TEST", "value": "test", "start": -1, "end": 5},
            {"type": "TEST", "value": "", "start": 2, "end": 2},
        ]

        # Should skip invalid entities
        redacted, records = service.redact_text(text, entities)

        assert redacted == text
        assert len(records) == 0


class TestPatternRedaction:
    """Test pattern-based redaction"""

    def test_ssn_pattern_redaction(self):
        """Test SSN pattern redaction"""
        service = RedactionService()

        text = "My SSN is 123-45-6789 and yours is 987-65-4321"
        patterns = {"SSN": r"\d{3}-\d{2}-\d{4}"}

        redacted, records = service.redact_by_pattern(text, patterns)

        assert "123-45-6789" not in redacted
        assert "987-65-4321" not in redacted
        assert "[SSN]" in redacted
        assert len(records) == 2

    def test_email_pattern_redaction(self):
        """Test email pattern redaction"""
        service = RedactionService()

        text = "Contact us at support@company.com or sales@company.com"
        patterns = {"EMAIL": r"[\w\.-]+@[\w\.-]+\.\w+"}

        redacted, records = service.redact_by_pattern(text, patterns)

        assert "support@company.com" not in redacted
        assert "sales@company.com" not in redacted
        assert redacted.count("[EMAIL]") == 2

    def test_credit_card_pattern_redaction(self):
        """Test credit card pattern redaction"""
        service = RedactionService()

        text = "Card 1: 4532-1234-5678-9010 or 5425 1234 5678 9010"
        patterns = {"CREDIT_CARD": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"}

        redacted, records = service.redact_by_pattern(text, patterns)

        assert "4532-1234-5678-9010" not in redacted
        assert "5425 1234 5678 9010" not in redacted
        assert len(records) == 2

    def test_invalid_pattern_handling(self):
        """Test handling of invalid regex patterns"""
        service = RedactionService()

        text = "Some text"
        patterns = {"BAD": "[invalid(regex"}

        # Should not crash, just skip invalid pattern
        redacted, records = service.redact_by_pattern(text, patterns)

        assert redacted == text
        assert len(records) == 0

    def test_multiple_patterns(self):
        """Test multiple patterns in one operation"""
        service = RedactionService()

        text = "SSN: 123-45-6789, Email: test@example.com"
        patterns = {
            "SSN": r"\d{3}-\d{2}-\d{4}",
            "EMAIL": r"[\w\.-]+@[\w\.-]+\.\w+",
        }

        redacted, records = service.redact_by_pattern(text, patterns)

        assert "123-45-6789" not in redacted
        assert "test@example.com" not in redacted
        assert len(records) == 2


class TestRedactionActions:
    """Test redaction based on compliance actions"""

    def test_block_action(self):
        """Test BLOCK action returns empty"""
        service = RedactionService()

        text = "Sensitive data here"
        entities = [{"type": "SENSITIVE", "value": "Sensitive data", "start": 0, "end": 14}]

        result, records = service.redact_action(text, entities, ComplianceAction.BLOCK)

        assert result == ""
        assert len(records) == 0

    def test_redact_action(self):
        """Test REDACT action redacts content"""
        service = RedactionService()

        text = "Name: John Doe"
        entities = [{"type": "PERSON", "value": "John Doe", "start": 6, "end": 14}]

        result, records = service.redact_action(text, entities, ComplianceAction.REDACT)

        assert "John Doe" not in result
        assert "[PERSON]" in result
        assert len(records) == 1

    def test_flag_action(self):
        """Test FLAG action returns unchanged"""
        service = RedactionService()

        text = "Name: John Doe"
        entities = [{"type": "PERSON", "value": "John Doe", "start": 6, "end": 14}]

        result, records = service.redact_action(text, entities, ComplianceAction.FLAG)

        assert result == text
        assert len(records) == 0


class TestRedactionMapping:
    """Test redaction audit trail mapping"""

    def test_redaction_mapping_stored(self):
        """Test mapping is stored for audit"""
        service = RedactionService()

        text = "John and Jane"
        entities = [
            {"type": "PERSON", "value": "John", "start": 0, "end": 4},
            {"type": "PERSON", "value": "Jane", "start": 9, "end": 13},
        ]

        redacted, records = service.redact_text(text, entities)

        mapping = service.get_mapping()

        assert "John" in mapping
        assert "Jane" in mapping
        assert mapping["John"] == "[PERSON]"
        assert mapping["Jane"] == "[PERSON]"

    def test_mapping_not_stored_when_disabled(self):
        """Test mapping can be disabled"""
        service = RedactionService()

        text = "Secret: password123"
        entities = [{"type": "PASSWORD", "value": "password123", "start": 8, "end": 19}]

        redacted, records = service.redact_text(text, entities, keep_mapping=False)

        mapping = service.get_mapping()

        assert len(mapping) == 0

    def test_mapping_cleared(self):
        """Test mapping can be cleared"""
        service = RedactionService()

        text = "Data: sensitive"
        entities = [{"type": "DATA", "value": "sensitive", "start": 6, "end": 15}]

        service.redact_text(text, entities)
        assert len(service.get_mapping()) > 0

        service.clear_mapping()
        assert len(service.get_mapping()) == 0


class TestRedactionPipeline:
    """Test redaction pipeline chaining"""

    def test_entity_then_pattern_pipeline(self):
        """Test pipeline with entity and pattern redaction"""
        service = RedactionService()
        pipeline = RedactionPipeline(service)

        text = "John's SSN is 123-45-6789 and email is john@example.com"
        entities = [
            {"type": "PERSON", "value": "John", "start": 0, "end": 4},
        ]

        pipeline.add_entity_redaction(RedactionStrategy.TOKEN_REPLACEMENT)
        pipeline.add_pattern_redaction(
            {"SSN": r"\d{3}-\d{2}-\d{4}"},
            RedactionStrategy.TOKEN_REPLACEMENT,
        )

        redacted, all_records = pipeline.execute(text, entities)

        assert "[PERSON]" in redacted
        assert "[SSN]" in redacted

    def test_pipeline_fluent_api(self):
        """Test pipeline fluent API"""
        pipeline = RedactionPipeline()

        # Should support method chaining
        result = pipeline.add_entity_redaction().add_pattern_redaction({})

        assert result is pipeline

    def test_pipeline_preserves_order(self):
        """Test pipeline operations execute in order"""
        service = RedactionService()
        pipeline = RedactionPipeline(service)

        text = "Test content"
        entities = []

        # Add operations
        pipeline.add_entity_redaction(RedactionStrategy.FULL_MASK)
        pipeline.add_pattern_redaction(
            {"TEST": r"Test"},
            RedactionStrategy.TOKEN_REPLACEMENT,
        )

        assert len(pipeline.operations) == 2

    def test_empty_pipeline(self):
        """Test pipeline with no operations"""
        pipeline = RedactionPipeline()

        text = "Unchanged text"
        redacted, records = pipeline.execute(text)

        assert redacted == text
        assert len(records) == 0


class TestRedactionEdgeCases:
    """Test edge cases and special scenarios"""

    def test_unicode_text_redaction(self):
        """Test redaction with unicode characters"""
        service = RedactionService()

        text = "Name: José García"
        entities = [{"type": "PERSON", "value": "José García", "start": 6, "end": 17}]

        redacted, records = service.redact_text(text, entities)

        assert "José García" not in redacted
        assert "[PERSON]" in redacted

    def test_special_characters_redaction(self):
        """Test redaction with special characters"""
        service = RedactionService()

        text = "Email: user+tag@sub.domain.com"
        entities = [{"type": "EMAIL", "value": "user+tag@sub.domain.com", "start": 7, "end": 30}]

        redacted, records = service.redact_text(text, entities)

        assert "user+tag@sub.domain.com" not in redacted

    def test_multiline_text_redaction(self):
        """Test redaction in multiline text"""
        service = RedactionService()

        text = """Line 1: John Doe
Line 2: jane@example.com
Line 3: Safe text"""

        entities = [
            {"type": "PERSON", "value": "John Doe", "start": 7, "end": 15},
            {"type": "EMAIL", "value": "jane@example.com", "start": 24, "end": 40},
        ]

        redacted, records = service.redact_text(text, entities)

        assert "John Doe" not in redacted
        assert "jane@example.com" not in redacted
        assert "Safe text" in redacted
        assert len(records) == 2

    def test_same_value_multiple_times(self):
        """Test redacting same value appearing multiple times"""
        service = RedactionService()

        text = "test@example.com and test@example.com"
        entities = [
            {"type": "EMAIL", "value": "test@example.com", "start": 0, "end": 16},
            {"type": "EMAIL", "value": "test@example.com", "start": 21, "end": 37},
        ]

        redacted, records = service.redact_text(text, entities)

        assert "test@example.com" not in redacted
        assert redacted.count("[EMAIL]") == 2


class TestGlobalRedactionService:
    """Test global redaction service instance"""

    def test_get_redaction_service(self):
        """Test getting global service"""
        reset_redaction_service()

        service1 = get_redaction_service()
        service2 = get_redaction_service()

        assert service1 is service2

    def test_reset_redaction_service(self):
        """Test resetting global service"""
        reset_redaction_service()

        service1 = get_redaction_service()
        reset_redaction_service()
        service2 = get_redaction_service()

        assert service1 is not service2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
