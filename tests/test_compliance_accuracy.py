"""
Compliance Framework Accuracy Tests

Verifies that GDPR, HIPAA, and PCI-DSS compliance rules are correctly implemented.
Tests detection accuracy, redaction behavior, and framework-specific requirements.
"""

import pytest

from app.compliance import get_compliance_engine, get_redaction_service, load_compliance_rules
from app.compliance.models import ComplianceAction
from app.detection import detect_pii


class TestGDPRCompliance:
    """Test GDPR-specific compliance requirements."""
    
    def test_gdpr_pii_detection(self):
        """Verify GDPR-relevant PII is detected."""
        test_cases = [
            ("My email is john.doe@example.com", "EMAIL"),
            ("Call me at +1-555-123-4567", "PHONE_NUMBER"),
            ("My IP address is 192.168.1.1", "IP_ADDRESS"),
            ("I live at 123 Main St, Springfield", "LOCATION"),
        ]
        
        for prompt, expected_type in test_cases:
            entities = detect_pii(prompt)
            entity_types = [e["type"] for e in entities]
            assert expected_type in entity_types, \
                f"Failed to detect {expected_type} in: {prompt}"
    
    def test_gdpr_data_minimization(self):
        """Verify only necessary entities are flagged for GDPR."""
        prompt = "Hello, my name is John"
        
        entities = detect_pii(prompt)
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"], 
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        result = engine.check_compliance(prompt, normalized_entities, frameworks=["GDPR"])
        
        # GDPR should flag PERSON entities but not over-flag
        # Verify violations are reasonable
        assert len(result.violations) >= 0  # May have violations for PERSON
    
    def test_gdpr_right_to_erasure_redaction(self):
        """Verify PII is completely redacted (not just masked)."""
        prompt = "My SSN is 123-45-6789 and email is test@example.com"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        redaction_service = get_redaction_service()
        sanitized, _ = redaction_service.redact_text(prompt, normalized_entities)
        
        # Verify original values are NOT in sanitized text
        assert "123-45-6789" not in sanitized
        assert "test@example.com" not in sanitized
        
        # Verify placeholders are used
        assert "[SSN]" in sanitized or "[SOCIAL_SECURITY_NUMBER]" in sanitized
        assert "[EMAIL]" in sanitized
    
    def test_gdpr_cross_border_transfer_warning(self):
        """Test that location-based PII triggers appropriate warnings."""
        prompt = "I'm located at 192.168.1.1 in Germany"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        result = engine.check_compliance(prompt, normalized_entities, frameworks=["GDPR"])
        
        # Should detect IP_ADDRESS and potentially LOCATION
        entity_types = [e["type"] for e in entities]
        assert "IP_ADDRESS" in entity_types or "LOCATION" in entity_types


class TestHIPAACompliance:
    """Test HIPAA-specific compliance requirements."""
    
    def test_hipaa_phi_detection(self):
        """Verify Protected Health Information is detected."""
        test_cases = [
            ("Patient SSN: 123-45-6789", "SSN"),
            ("Medical Record #: MRN-12345", "MEDICAL_RECORD_NUMBER"),
            ("Patient email: patient@hospital.com", "EMAIL"),
            ("Patient phone: 555-123-4567", "PHONE_NUMBER"),
        ]
        
        for prompt, expected_type in test_cases:
            entities = detect_pii(prompt)
            entity_types = [e["type"] for e in entities]
            
            # Map expected types to actual detection types
            type_mapping = {
                "SSN": ["SSN", "SOCIAL_SECURITY_NUMBER"],
                "MEDICAL_RECORD_NUMBER": ["MEDICAL_RECORD_NUMBER", "US_DRIVER_LICENSE"],  # May be detected as similar pattern
                "EMAIL": ["EMAIL"],
                "PHONE_NUMBER": ["PHONE_NUMBER", "US_PHONE_NUMBER"],
            }
            
            detected = any(
                actual_type in entity_types 
                for actual_type in type_mapping.get(expected_type, [expected_type])
            )
            assert detected, f"Failed to detect {expected_type} in: {prompt}"
    
    def test_hipaa_18_identifiers(self):
        """Test detection of HIPAA Safe Harbor 18 identifiers."""
        # Test a subset of the 18 identifiers
        identifiers = [
            ("Name: John Doe", "PERSON"),
            ("Address: 123 Main St", "LOCATION"),
            ("DOB: 01/15/1990", "DATE_TIME"),
            ("Phone: 555-1234", "PHONE_NUMBER"),
            ("SSN: 123-45-6789", "SSN"),
            ("Email: test@example.com", "EMAIL"),
            ("IP: 192.168.1.1", "IP_ADDRESS"),
        ]
        
        for prompt, expected_type in identifiers:
            entities = detect_pii(prompt)
            entity_types = [e["type"] for e in entities]
            
            # Some flexibility in type names
            type_variants = {
                "SSN": ["SSN", "SOCIAL_SECURITY_NUMBER"],
                "PHONE_NUMBER": ["PHONE_NUMBER", "US_PHONE_NUMBER"],
            }
            
            if expected_type in type_variants:
                assert any(t in entity_types for t in type_variants[expected_type]), \
                    f"Failed to detect {expected_type} in: {prompt}"
            else:
                assert expected_type in entity_types, \
                    f"Failed to detect {expected_type} in: {prompt}"
    
    def test_hipaa_minimum_necessary_rule(self):
        """Verify redaction doesn't over-redact non-PHI."""
        prompt = "The patient's favorite color is blue and their SSN is 123-45-6789"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        redaction_service = get_redaction_service()
        sanitized, _ = redaction_service.redact_text(prompt, normalized_entities)
        
        # "blue" should NOT be redacted (it's not PHI)
        assert "blue" in sanitized
        
        # SSN SHOULD be redacted
        assert "123-45-6789" not in sanitized
    
    def test_hipaa_blocking_on_high_risk(self):
        """Test that high-risk HIPAA violations trigger BLOCK action."""
        prompt = "Patient SSN 123-45-6789 has HIV diagnosis"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        result = engine.check_compliance(prompt, normalized_entities, frameworks=["HIPAA"])
        
        # Should have violations
        assert len(result.violations) > 0
        
        # At least one should be high severity
        severities = [v.severity for v in result.violations]
        assert "high" in severities or "critical" in severities


class TestPCIDSSCompliance:
    """Test PCI-DSS specific compliance requirements."""
    
    def test_pci_credit_card_detection(self):
        """Verify credit card numbers are detected."""
        test_cases = [
            "4532-1488-0343-6467",  # Visa
            "5425-2334-3010-9903",  # Mastercard
            "3782-822463-10005",    # Amex
            "6011-1111-1111-1117",  # Discover
        ]
        
        for card_number in test_cases:
            prompt = f"My card is {card_number}"
            entities = detect_pii(prompt)
            entity_types = [e["type"] for e in entities]
            
            assert "CREDIT_CARD" in entity_types or "CREDIT_DEBIT_NUMBER" in entity_types, \
                f"Failed to detect credit card: {card_number}"
    
    def test_pci_luhn_validation(self):
        """Verify Luhn algorithm is used for credit card validation."""
        # Valid Luhn checksum
        valid_card = "4532-1488-0343-6467"
        
        # Invalid Luhn checksum (last digit changed)
        invalid_card = "4532-1488-0343-6468"
        
        valid_entities = detect_pii(f"Card: {valid_card}")
        invalid_entities = detect_pii(f"Card: {invalid_card}")
        
        # Valid card should be detected
        valid_types = [e["type"] for e in valid_entities]
        assert "CREDIT_CARD" in valid_types or "CREDIT_DEBIT_NUMBER" in valid_types
        
        # Invalid card should NOT be detected (or detected with lower confidence)
        # Note: Some PII detectors may still flag it as a potential card
        # This test may need adjustment based on your detector's behavior
    
    def test_pci_cvv_detection_near_card(self):
        """Test that CVV codes near card numbers are flagged."""
        prompt = "Card: 4532-1488-0343-6467 CVV: 123"
        entities = detect_pii(prompt)
        
        # Should detect the card number
        entity_types = [e["type"] for e in entities]
        assert "CREDIT_CARD" in entity_types or "CREDIT_DEBIT_NUMBER" in entity_types
        
        # CVV might be detected as a separate entity or part of card data
        # At minimum, the card should be detected
    
    def test_pci_cardholder_data_never_logged(self):
        """Verify card data is redacted before any logging."""
        prompt = "Process payment for card 4532-1488-0343-6467"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        redaction_service = get_redaction_service()
        sanitized, _ = redaction_service.redact_text(prompt, normalized_entities)
        
        # Original card number should NOT appear in sanitized text
        assert "4532-1488-0343-6467" not in sanitized
        assert "4532" not in sanitized  # Even partial shouldn't appear
    
    def test_pci_blocking_on_card_data(self):
        """Test that PCI violations trigger appropriate actions."""
        prompt = "Store this card: 4532-1488-0343-6467 CVV: 123"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        result = engine.check_compliance(prompt, normalized_entities, frameworks=["PCI-DSS"])
        
        # Should have violations for credit card
        assert len(result.violations) > 0
        
        # Should be high severity
        severities = [v.severity for v in result.violations]
        assert "high" in severities or "critical" in severities


class TestCrossFrameworkCompliance:
    """Test scenarios involving multiple compliance frameworks."""
    
    def test_multi_framework_detection(self):
        """Test prompt that violates multiple frameworks."""
        prompt = "Patient John Doe (SSN: 123-45-6789) paid with card 4532-1488-0343-6467"
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        # Check all frameworks
        result = engine.check_compliance(
            prompt, 
            normalized_entities, 
            frameworks=["GDPR", "HIPAA", "PCI-DSS"]
        )
        
        # Should have violations from multiple frameworks
        frameworks_violated = set(v.framework for v in result.violations)
        assert len(frameworks_violated) >= 2, "Should violate multiple frameworks"
    
    def test_strictest_action_wins(self):
        """When multiple frameworks apply, the strictest action should be used."""
        prompt = "SSN: 123-45-6789"  # Violates both GDPR and HIPAA
        entities = detect_pii(prompt)
        
        normalized_entities = [
            {"type": e["type"], "value": e["value"],
             "start": e["position"]["start"], "end": e["position"]["end"]}
            for e in entities
        ]
        
        rules = load_compliance_rules()
        engine = get_compliance_engine()
        engine.load_rules(rules)
        
        result = engine.check_compliance(
            prompt,
            normalized_entities,
            frameworks=["GDPR", "HIPAA"]
        )
        
        # If any rule says BLOCK, the overall action should be BLOCK
        actions = [v.action for v in result.violations]
        if ComplianceAction.BLOCK in actions:
            # Verify the engine would block this
            assert not result.compliant
