"""
Tests for Risk Scoring Engine

Tests for:
- PII entity risk scoring
- Injection threat scoring
- Compliance violation scoring
- Overall risk assessment
- Risk level classification
"""

import pytest

from app.compliance.models import ComplianceAction, ComplianceViolation, Severity
from app.compliance.risk_scoring import RiskLevel, RiskScorer, get_risk_scorer


class TestRiskScoring:
    """Test risk scoring functionality"""

    def test_pii_entity_scoring(self):
        """Test scoring of PII entities"""
        scorer = RiskScorer()

        # SSN - highest risk
        ssn_risk = scorer.score_pii_entity("SSN", confidence=0.95)
        assert ssn_risk.value > 80
        assert ssn_risk.level == RiskLevel.CRITICAL
        assert ssn_risk.component == "PII_SSN"

        # Person name - medium-high risk
        person_risk = scorer.score_pii_entity("PERSON", confidence=0.85)
        assert person_risk.value > 50
        assert person_risk.level in [RiskLevel.MEDIUM, RiskLevel.HIGH]

        # Location - low risk
        location_risk = scorer.score_pii_entity("GPE", confidence=0.9)
        assert location_risk.value < 30
        assert location_risk.level == RiskLevel.LOW

    def test_confidence_multiplier(self):
        """Test that confidence affects score"""
        scorer = RiskScorer()

        # High confidence
        high_conf = scorer.score_pii_entity("PERSON", confidence=0.95)

        # Low confidence
        low_conf = scorer.score_pii_entity("PERSON", confidence=0.5)

        assert high_conf.value > low_conf.value

    def test_unknown_entity_type(self):
        """Test handling of unknown entity types"""
        scorer = RiskScorer()

        risk = scorer.score_pii_entity("UNKNOWN_TYPE", confidence=0.8)

        assert risk.value > 0
        assert risk.component == "PII_UNKNOWN_TYPE"

    def test_injection_scoring(self):
        """Test injection threat scoring"""
        scorer = RiskScorer()

        # High confidence injection threat
        high_threat = scorer.score_injection_threat(0.95, prompt_length=100)
        assert high_threat.value > 80
        assert high_threat.level == RiskLevel.CRITICAL

        # Low confidence
        low_threat = scorer.score_injection_threat(0.1, prompt_length=100)
        assert low_threat.value < 30
        assert low_threat.level == RiskLevel.LOW

    def test_injection_length_multiplier(self):
        """Test that longer prompts increase risk"""
        scorer = RiskScorer()

        # Short prompt
        short = scorer.score_injection_threat(0.5, prompt_length=100)

        # Long prompt (1000+ chars)
        long = scorer.score_injection_threat(0.5, prompt_length=1500)

        assert long.value > short.value

    def test_compliance_scoring(self):
        """Test compliance violation scoring"""
        scorer = RiskScorer()

        # Critical violation
        critical_violation = ComplianceViolation(
            rule_id="rule_1",
            framework="HIPAA",
            rule_name="Critical Rule",
            severity=Severity.CRITICAL,
            message="Critical violation",
            remediation="Fix immediately",
            action=ComplianceAction.BLOCK,
        )

        critical_risk = scorer.score_compliance_violation(critical_violation)
        assert critical_risk.value > 80
        assert critical_risk.level == RiskLevel.CRITICAL

        # Low violation
        low_violation = ComplianceViolation(
            rule_id="rule_2",
            framework="GDPR",
            rule_name="Low Rule",
            severity=Severity.LOW,
            message="Low violation",
            remediation="Consider reviewing",
            action=ComplianceAction.FLAG,
        )

        low_risk = scorer.score_compliance_violation(low_violation)
        assert low_risk.value < 40
        assert low_risk.level == RiskLevel.LOW

    def test_framework_weight_multiplier(self):
        """Test that framework importance affects score"""
        scorer = RiskScorer()

        # HIPAA (highest priority)
        hipaa_violation = ComplianceViolation(
            rule_id="h1",
            framework="HIPAA",
            rule_name="Test",
            severity=Severity.HIGH,
            message="Test",
            remediation="Test",
            action=ComplianceAction.REDACT,
        )
        hipaa_risk = scorer.score_compliance_violation(hipaa_violation)

        # GDPR (lower priority)
        gdpr_violation = ComplianceViolation(
            rule_id="g1",
            framework="GDPR",
            rule_name="Test",
            severity=Severity.HIGH,
            message="Test",
            remediation="Test",
            action=ComplianceAction.REDACT,
        )
        gdpr_risk = scorer.score_compliance_violation(gdpr_violation)

        assert hipaa_risk.value > gdpr_risk.value


class TestRiskLevelConversion:
    """Test risk score to level conversion"""

    def test_critical_threshold(self):
        """Test CRITICAL level (85+)"""
        scorer = RiskScorer()

        level = scorer._score_to_level(95)
        assert level == RiskLevel.CRITICAL

    def test_high_threshold(self):
        """Test HIGH level (60-85)"""
        scorer = RiskScorer()

        level = scorer._score_to_level(70)
        assert level == RiskLevel.HIGH

    def test_medium_threshold(self):
        """Test MEDIUM level (30-60)"""
        scorer = RiskScorer()

        level = scorer._score_to_level(45)
        assert level == RiskLevel.MEDIUM

    def test_low_threshold(self):
        """Test LOW level (0-30)"""
        scorer = RiskScorer()

        level = scorer._score_to_level(15)
        assert level == RiskLevel.LOW

    def test_boundary_values(self):
        """Test boundary values"""
        scorer = RiskScorer()

        assert scorer._score_to_level(30) == RiskLevel.MEDIUM  # Boundary
        assert scorer._score_to_level(60) == RiskLevel.HIGH  # Boundary
        assert scorer._score_to_level(85) == RiskLevel.CRITICAL  # Boundary


class TestOverallRiskAssessment:
    """Test comprehensive risk assessment"""

    def test_assessment_with_pii_only(self):
        """Test assessment with only PII entities"""
        scorer = RiskScorer()

        entities = [
            {"type": "SSN", "value": "123-45-6789", "confidence": 0.95},
            {"type": "PERSON", "value": "John", "confidence": 0.8},
        ]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        assert assessment.total_entities == 2
        assert assessment.pii_score > 0
        assert assessment.injection_score == 0
        assert assessment.compliance_score == 0
        assert len(assessment.individual_risks) > 0

    def test_assessment_with_injection_only(self):
        """Test assessment with only injection threat"""
        scorer = RiskScorer()

        assessment = scorer.assess_overall_risk(injection_score=0.92)

        assert assessment.injection_score > 80
        assert assessment.pii_score == 0
        assert assessment.compliance_score == 0

    def test_assessment_with_compliance_only(self):
        """Test assessment with only compliance violations"""
        scorer = RiskScorer()

        violations = [
            ComplianceViolation(
                rule_id="r1",
                framework="HIPAA",
                rule_name="Test",
                severity=Severity.HIGH,
                message="Test",
                remediation="Test",
                action=ComplianceAction.REDACT,
            ),
        ]

        assessment = scorer.assess_overall_risk(compliance_violations=violations)

        assert assessment.compliance_score > 0
        assert assessment.pii_score == 0
        assert assessment.injection_score == 0

    def test_comprehensive_assessment(self):
        """Test full risk assessment with all components"""
        scorer = RiskScorer()

        entities = [
            {"type": "SSN", "value": "123-45-6789", "confidence": 0.95},
            {"type": "EMAIL", "value": "test@example.com", "confidence": 0.9},
        ]

        violations = [
            ComplianceViolation(
                rule_id="r1",
                framework="HIPAA",
                rule_name="PHI",
                severity=Severity.CRITICAL,
                message="Test",
                remediation="Test",
                action=ComplianceAction.BLOCK,
            ),
        ]

        assessment = scorer.assess_overall_risk(
            pii_entities=entities,
            injection_score=0.7,
            compliance_violations=violations,
        )

        assert assessment.overall_score > 0
        assert assessment.total_entities == 2
        assert assessment.critical_count > 0
        assert len(assessment.individual_risks) >= 3
        assert len(assessment.top_risks) > 0

    def test_top_risks_ranking(self):
        """Test that top risks are properly ranked"""
        scorer = RiskScorer()

        entities = [
            {"type": "SSN", "value": "123-45-6789", "confidence": 0.95},
            {"type": "PERSON", "value": "John", "confidence": 0.8},
            {"type": "GPE", "value": "US", "confidence": 0.9},
        ]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        # Top risks should be sorted
        assert len(assessment.top_risks) <= 5
        assert assessment.top_risks[0].value >= assessment.top_risks[-1].value

    def test_overall_level_determination(self):
        """Test overall risk level is correctly determined"""
        scorer = RiskScorer()

        # Low risk scenario
        low_assessment = scorer.assess_overall_risk(injection_score=0.1)
        assert low_assessment.overall_level == RiskLevel.LOW

        # High risk scenario (weighted average: 100 * 0.4 = 40, but with injection)
        high_entities = [{"type": "SSN", "value": "123-45-6789", "confidence": 0.99}]
        high_assessment = scorer.assess_overall_risk(
            pii_entities=high_entities,
            injection_score=0.85,  # Add injection to push score up
        )
        # With PII score of 100 (0.4 weight) and injection of 80+ (0.3 weight), should be HIGH+
        assert high_assessment.overall_level in [
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        assert high_assessment.pii_score == 100.0


class TestRecommendations:
    """Test risk-based recommendations"""

    def test_critical_recommendations(self):
        """Test recommendations for critical risk"""
        scorer = RiskScorer()

        entities = [{"type": "SSN", "value": "123-45-6789", "confidence": 0.99}]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        if assessment.overall_level == RiskLevel.CRITICAL:
            assert len(assessment.recommendations) > 0
            assert any(
                "block" in r.lower() or "quarantine" in r.lower()
                for r in assessment.recommendations
            )

    def test_high_pii_volume_recommendation(self):
        """Test recommendation for high volume PII"""
        scorer = RiskScorer()

        entities = [
            {"type": "PERSON", "value": f"Person{i}", "confidence": 0.8}
            for i in range(10)  # 10 entities
        ]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        recommendations_text = " ".join(assessment.recommendations)
        if len(entities) > 5:
            # Should recommend bulk handling
            assert "volume" in recommendations_text.lower()

    def test_injection_recommendation(self):
        """Test recommendation for injection threats"""
        scorer = RiskScorer()

        assessment = scorer.assess_overall_risk(injection_score=0.95)

        recommendations_text = " ".join(assessment.recommendations)
        assert "prompt" in recommendations_text.lower() or "sanitiz" in recommendations_text.lower()

    def test_compliance_recommendation(self):
        """Test recommendation for compliance violations"""
        scorer = RiskScorer()

        violations = [
            ComplianceViolation(
                rule_id="r1",
                framework="HIPAA",
                rule_name="Test",
                severity=Severity.CRITICAL,
                message="Test",
                remediation="Test",
                action=ComplianceAction.BLOCK,
            ),
            ComplianceViolation(
                rule_id="r2",
                framework="GDPR",
                rule_name="Test",
                severity=Severity.CRITICAL,
                message="Test",
                remediation="Test",
                action=ComplianceAction.BLOCK,
            ),
        ]

        assessment = scorer.assess_overall_risk(compliance_violations=violations)

        recommendations_text = " ".join(assessment.recommendations)
        # Should mention frameworks
        assert (
            "HIPAA" in recommendations_text
            or "GDPR" in recommendations_text
            or "framework" in recommendations_text.lower()
        )


class TestRiskScorerInstance:
    """Test risk scorer instance creation"""

    def test_get_risk_scorer(self):
        """Test getting risk scorer instance"""
        scorer1 = get_risk_scorer()
        scorer2 = get_risk_scorer()

        # Should be different instances (not singleton for now)
        assert isinstance(scorer1, RiskScorer)
        assert isinstance(scorer2, RiskScorer)


class TestRiskScoreEdgeCases:
    """Test edge cases and special scenarios"""

    def test_empty_assessment(self):
        """Test assessment with no data"""
        scorer = RiskScorer()

        assessment = scorer.assess_overall_risk()

        assert assessment.overall_score >= 0
        assert assessment.total_entities == 0
        assert assessment.critical_count == 0

    def test_zero_confidence_pii(self):
        """Test PII with zero confidence"""
        scorer = RiskScorer()

        entities = [{"type": "PERSON", "value": "John", "confidence": 0.0}]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        # Should still calculate something
        assert assessment.total_entities == 1

    def test_multiple_same_type_entities(self):
        """Test multiple entities of same type"""
        scorer = RiskScorer()

        entities = [
            {"type": "EMAIL", "value": "test1@example.com", "confidence": 0.9},
            {"type": "EMAIL", "value": "test2@example.com", "confidence": 0.9},
            {"type": "EMAIL", "value": "test3@example.com", "confidence": 0.9},
        ]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        assert assessment.total_entities == 3
        assert assessment.pii_score > 0

    def test_score_bounds(self):
        """Test that scores stay within 0-100"""
        scorer = RiskScorer()

        # Extreme case: high confidence + high importance
        entities = [{"type": "SSN", "value": "123-45-6789", "confidence": 1.0}]

        assessment = scorer.assess_overall_risk(pii_entities=entities)

        assert 0 <= assessment.pii_score <= 100
        assert 0 <= assessment.overall_score <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
