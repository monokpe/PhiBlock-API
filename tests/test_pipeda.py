import pytest

from app.compliance.engine import get_compliance_engine, reset_compliance_engine
from app.compliance.models import ComplianceFramework
from app.compliance.rules import load_compliance_rules


@pytest.fixture
def engine():
    reset_compliance_engine()
    engine = get_compliance_engine()
    rules = load_compliance_rules()
    engine.load_rules(rules)
    return engine


def test_pipeda_framework_loaded(engine):
    """Test that PIPEDA rules are loaded"""
    pipeda_rules = engine.get_rules_by_framework("PIPEDA")
    assert len(pipeda_rules) > 0
    assert any(r.id == "pipeda_001" for r in pipeda_rules)


def test_sin_detection(engine):
    """Test detection of Social Insurance Numbers"""
    text = "My SIN is 123-456-789"
    # Mock entity detection since we haven't updated the NER model yet
    # But the rule also has a regex pattern

    # Test regex pattern matching
    result = engine.check_compliance(text, [], frameworks=["PIPEDA"])

    assert not result.compliant
    assert len(result.violations) > 0
    violation = result.violations[0]
    assert violation.rule_id == "pipeda_001"
    assert "123-456-789" in violation.matched_content


def test_postal_code_detection(engine):
    """Test detection of Canadian postal codes"""
    text = "I live at M5V 2T6 in Toronto"

    result = engine.check_compliance(text, [], frameworks=["PIPEDA"])

    # Medium severity does not cause non-compliance
    assert result.compliant
    violation = next(v for v in result.violations if v.rule_id == "pipeda_002")
    assert "M5V 2T6" in violation.matched_content


def test_data_residency_warning(engine):
    """Test detection of data residency issues"""
    text = "We will store user data on a US server for backup"

    result = engine.check_compliance(text, [], frameworks=["PIPEDA"])

    violation = next(v for v in result.violations if v.rule_id == "pipeda_004")
    assert violation.severity.value == "high"
    assert violation.action.value == "flag"


def test_consent_violation(engine):
    """Test detection of consent violations"""
    text = "We collect this data without consent"

    result = engine.check_compliance(text, [], frameworks=["PIPEDA"])

    assert not result.compliant
    violation = next(v for v in result.violations if v.rule_id == "pipeda_005")
    assert violation.action.value == "block"
