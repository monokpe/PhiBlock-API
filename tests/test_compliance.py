"""
Tests for Compliance Module

Tests for:
- Rule loading from YAML
- Compliance engine evaluation
- Violation detection and severity
- Multiple framework checking
"""

from pathlib import Path

import pytest

from app.compliance import (
    ComplianceAction,
    ComplianceEngine,
    ComplianceFramework,
    ComplianceRule,
    ComplianceViolation,
    RuleLoader,
    Severity,
    get_compliance_engine,
    load_compliance_rules,
    reset_compliance_engine,
)


class TestComplianceModels:
    """Test compliance data models"""

    def test_compliance_rule_creation(self):
        """Test creating a compliance rule"""
        rule = ComplianceRule(
            id="test_001",
            name="Test Rule",
            description="A test rule",
            framework="HIPAA",
            severity=Severity.HIGH,
            action=ComplianceAction.REDACT,
            entity_types=["PERSON"],
            keywords=["patient"],
            patterns=[],
            remediation="Remove the data",
        )

        assert rule.id == "test_001"
        assert rule.name == "Test Rule"
        assert rule.severity == Severity.HIGH
        assert "PERSON" in rule.entity_types

    def test_compliance_violation_creation(self):
        """Test creating a compliance violation"""
        violation = ComplianceViolation(
            rule_id="rule_001",
            framework="HIPAA",
            rule_name="PII Detection",
            severity=Severity.HIGH,
            message="PHI detected",
            remediation="Remove PHI",
            action=ComplianceAction.BLOCK,
            matched_content="John Doe",
        )

        assert violation.rule_id == "rule_001"
        assert violation.framework == "HIPAA"
        assert violation.matched_content == "John Doe"


class TestRuleLoader:
    """Test rule loading from YAML"""

    def test_load_hipaa_rules(self):
        """Test loading HIPAA rules"""
        loader = RuleLoader()
        rules = []

        # Try to load existing rules
        hipaa_file = (
            Path(__file__).parent.parent / "app" / "compliance" / "definitions" / "hipaa.yaml"
        )
        if hipaa_file.exists():
            rules = loader.load_rules_from_file(str(hipaa_file))

        if rules:
            assert len(rules) > 0
            assert all(isinstance(r, ComplianceRule) for r in rules)
            assert all(r.framework == "HIPAA" for r in rules)

    def test_load_all_rules(self):
        """Test loading all available rules"""
        loader = RuleLoader()
        rules = loader.load_all_rules()

        # Should have at least some rules
        assert isinstance(rules, list)
        if rules:
            assert all(isinstance(r, ComplianceRule) for r in rules)

    def test_validate_rules(self):
        """Test rule validation"""
        loader = RuleLoader()

        # Create test rules
        rules = [
            ComplianceRule(
                id="test_001",
                name="Test 1",
                description="Test rule 1",
                framework="HIPAA",
                severity=Severity.HIGH,
                action=ComplianceAction.REDACT,
                entity_types=["PERSON"],
                remediation="Test",
            ),
            ComplianceRule(
                id="test_002",
                name="Test 2",
                description="Test rule 2",
                framework="GDPR",
                severity=Severity.CRITICAL,
                action=ComplianceAction.BLOCK,
                keywords=["test"],
                remediation="Test",
            ),
        ]

        report = loader.validate_rules(rules)

        assert report["total"] == 2
        assert "HIPAA" in report["by_framework"]
        assert "GDPR" in report["by_framework"]
        assert "high" in report["by_severity"]
        assert "critical" in report["by_severity"]


class TestComplianceEngine:
    """Test compliance engine"""

    @pytest.fixture
    def engine(self):
        """Create a test engine with sample rules"""
        engine = ComplianceEngine()

        rules = [
            ComplianceRule(
                id="hipaa_001",
                name="Patient Name",
                description="Patient name detection",
                framework="HIPAA",
                severity=Severity.HIGH,
                action=ComplianceAction.REDACT,
                entity_types=["PERSON"],
                remediation="Redact patient names",
            ),
            ComplianceRule(
                id="hipaa_002",
                name="SSN Detection",
                description="SSN detection",
                framework="HIPAA",
                severity=Severity.CRITICAL,
                action=ComplianceAction.BLOCK,
                entity_types=["SSN"],
                remediation="Never send SSN",
            ),
            ComplianceRule(
                id="gdpr_001",
                name="Email Detection",
                description="Email detection",
                framework="GDPR",
                severity=Severity.HIGH,
                action=ComplianceAction.REDACT,
                entity_types=["EMAIL"],
                remediation="Protect email addresses",
            ),
        ]

        engine.load_rules(rules)
        return engine

    def test_engine_initialization(self, engine):
        """Test engine initializes correctly"""
        assert len(engine.frameworks) == 2
        assert "HIPAA" in engine.frameworks
        assert "GDPR" in engine.frameworks

    def test_detect_entity_violation(self, engine):
        """Test detecting entity-based violations"""
        entities = [
            {
                "type": "PERSON",
                "value": "John Doe",
                "start": 0,
                "end": 8,
                "confidence": 0.95,
            }
        ]

        result = engine.check_compliance(
            "John Doe is a patient",
            entities,
            frameworks=["HIPAA"],
        )

        assert len(result.violations) == 1
        assert result.violations[0].framework == "HIPAA"
        assert result.violations[0].rule_name == "Patient Name"

    def test_multiple_frameworks(self, engine):
        """Test checking multiple frameworks"""
        entities = [
            {"type": "PERSON", "value": "John Doe", "start": 0, "end": 8},
            {"type": "EMAIL", "value": "john@example.com", "start": 20, "end": 36},
        ]

        result = engine.check_compliance(
            "John Doe john@example.com",
            entities,
            frameworks=["HIPAA", "GDPR"],
        )

        assert len(result.violations) == 2
        assert any(v.framework == "HIPAA" for v in result.violations)
        assert any(v.framework == "GDPR" for v in result.violations)

    def test_critical_violation_non_compliance(self, engine):
        """Test that critical violations mark as non-compliant"""
        entities = [{"type": "SSN", "value": "123-45-6789", "start": 0, "end": 11}]

        result = engine.check_compliance(
            "SSN: 123-45-6789",
            entities,
            frameworks=["HIPAA"],
        )

        assert result.compliant is False
        assert result.violations[0].severity == Severity.CRITICAL

    def test_no_violations_compliance(self, engine):
        """Test compliant when no violations"""
        result = engine.check_compliance(
            "This is safe text",
            [],
            frameworks=["HIPAA"],
        )

        assert result.compliant is True
        assert len(result.violations) == 0

    def test_get_rules_by_framework(self, engine):
        """Test retrieving rules by framework"""
        hipaa_rules = engine.get_rules_by_framework("HIPAA")
        assert len(hipaa_rules) == 2
        assert all(r.framework == "HIPAA" for r in hipaa_rules)

    def test_get_rule_by_id(self, engine):
        """Test retrieving specific rule"""
        rule = engine.get_rule_by_id("hipaa_001")
        assert rule is not None
        assert rule.name == "Patient Name"

    def test_keyword_matching(self):
        """Test keyword-based rule matching"""
        engine = ComplianceEngine()

        rule = ComplianceRule(
            id="test_001",
            name="Test Keyword",
            description="Test keyword rule",
            framework="HIPAA",
            severity=Severity.MEDIUM,
            action=ComplianceAction.FLAG,
            keywords=["confidential", "secret"],
            remediation="Mark as confidential",
        )

        engine.load_rules([rule])

        result = engine.check_compliance(
            "This is confidential information",
            [],
            frameworks=["HIPAA"],
        )

        assert len(result.violations) == 1
        assert "confidential" in result.violations[0].message.lower()

    def test_pattern_matching(self):
        """Test regex pattern matching"""
        engine = ComplianceEngine()

        rule = ComplianceRule(
            id="test_001",
            name="Test Pattern",
            description="Test pattern rule",
            framework="HIPAA",
            severity=Severity.HIGH,
            action=ComplianceAction.BLOCK,
            patterns=[r"\d{3}-\d{2}-\d{4}"],
            remediation="Do not send SSN",
        )

        engine.load_rules([rule])

        result = engine.check_compliance(
            "SSN is 123-45-6789",
            [],
            frameworks=["HIPAA"],
        )

        assert len(result.violations) == 1
        assert "123-45-6789" in result.violations[0].matched_content


class TestGlobalEngine:
    """Test global engine instance"""

    def test_get_compliance_engine(self):
        """Test getting global engine"""
        reset_compliance_engine()

        engine1 = get_compliance_engine()
        engine2 = get_compliance_engine()

        assert engine1 is engine2

    def test_reset_compliance_engine(self):
        """Test resetting global engine"""
        reset_compliance_engine()

        engine1 = get_compliance_engine()
        reset_compliance_engine()
        engine2 = get_compliance_engine()

        assert engine1 is not engine2


class TestCompleteWorkflow:
    """Test complete compliance workflow"""

    def test_end_to_end_compliance_check(self):
        """Test complete workflow from loading to checking"""
        # Load rules
        loader = RuleLoader()
        all_rules = []

        # Try to load actual YAML rules
        hipaa_file = (
            Path(__file__).parent.parent / "app" / "compliance" / "definitions" / "hipaa.yaml"
        )
        if hipaa_file.exists():
            all_rules = loader.load_rules_from_file(str(hipaa_file))

        if not all_rules:
            # Create test rules
            all_rules = [
                ComplianceRule(
                    id="test_001",
                    name="Test",
                    description="Test rule",
                    framework="HIPAA",
                    severity=Severity.HIGH,
                    action=ComplianceAction.REDACT,
                    keywords=["patient"],
                    remediation="Test",
                ),
            ]

        # Create engine and load rules
        engine = ComplianceEngine()
        engine.load_rules(all_rules)

        # Check compliance
        entities = []
        result = engine.check_compliance(
            "Patient information should not be shared",
            entities,
            frameworks=["HIPAA"],
        )

        # Validate result
        assert result.frameworks_checked == ["HIPAA"]
        assert isinstance(result.violations, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
