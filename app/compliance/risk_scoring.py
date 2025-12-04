"""
Risk Scoring Engine - Evaluate and quantify security risks

Provides weighted scoring for:
- PII entities (types, sensitivity levels)
- Injection threats (confidence scores)
- Compliance violations (severity + framework)
- Overall risk assessment

Risk levels: LOW (0-30), MEDIUM (30-60), HIGH (60-85), CRITICAL (85-100)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from app.compliance.models import ComplianceViolation, Severity


class RiskLevel(Enum):
    """Risk severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskScore:
    """Individual risk score for an entity or component"""

    component: str  # pii, injection, compliance
    value: float  # 0-100
    level: RiskLevel
    details: str
    remediation: Optional[str] = None


@dataclass
class OverallRiskAssessment:
    """Complete risk assessment result"""

    overall_score: float  # 0-100
    overall_level: RiskLevel
    pii_score: float
    injection_score: float
    compliance_score: float
    individual_risks: List[RiskScore]
    top_risks: List[RiskScore]  # Top 5 risks
    recommendations: List[str]
    total_entities: int
    critical_count: int


class RiskScorer:
    """
    Calculates risk scores for security threats.

    Scoring Model:
    - PII Risk: Entity type * sensitivity * confidence
    - Injection Risk: Model confidence * exposure
    - Compliance Risk: Violation severity * framework importance
    """

    # PII Entity Type Risk Weights (0-100)
    PII_WEIGHTS = {
        "SSN": 95,  # Critical: unique identifier
        "CREDIT_CARD": 90,  # Critical: financial
        "PERSON": 70,  # High: personal name
        "EMAIL": 60,  # Medium-High: contact info
        "PHONE_NUMBER": 55,  # Medium: contact info
        "DATE": 30,  # Low-Medium: partial identifier
        "GPE": 20,  # Low: location (public)
        "ORG": 15,  # Very Low: organization name
        "UNKNOWN": 50,  # Medium: unknown type
    }

    # Compliance Framework Risk Weights (importance multiplier)
    FRAMEWORK_WEIGHTS = {
        "HIPAA": 1.5,  # Healthcare - highest priority
        "PCI_DSS": 1.4,  # Financial - high priority
        "GDPR": 1.3,  # Privacy - high priority
    }

    # Violation Severity Risk Scores
    SEVERITY_SCORES = {
        Severity.LOW: 20,
        Severity.MEDIUM: 40,
        Severity.HIGH: 70,
        Severity.CRITICAL: 95,
    }

    def __init__(self):
        """Initialize risk scorer"""
        self.component_scores: Dict[str, float] = {}

    def score_pii_entity(
        self,
        entity_type: str,
        confidence: float = 1.0,
        context_sensitive: bool = True,
    ) -> RiskScore:
        """
        Calculate risk score for a PII entity.

        Args:
            entity_type: Type of PII (SSN, PERSON, EMAIL, etc.)
            confidence: Detection confidence (0-1)
            context_sensitive: Whether context makes it more sensitive

        Returns:
            RiskScore for this entity
        """
        base_weight = self.PII_WEIGHTS.get(entity_type, self.PII_WEIGHTS["UNKNOWN"])

        # Apply confidence multiplier
        score = base_weight * confidence

        # Increase score if highly sensitive and high confidence
        if context_sensitive and confidence > 0.85:
            score = min(100, score * 1.1)

        level = self._score_to_level(score)

        return RiskScore(
            component=f"PII_{entity_type}",
            value=score,
            level=level,
            details=f"{entity_type} entity (confidence: {confidence:.2%})",
            remediation=f"Redact {entity_type} using appropriate strategy",
        )

    def score_injection_threat(
        self,
        injection_confidence: float,
        prompt_length: int = 0,
    ) -> RiskScore:
        """
        Calculate risk score for prompt injection threat.

        Args:
            injection_confidence: Model confidence of injection (0-1)
            prompt_length: Length of prompt (longer = higher exposure)

        Returns:
            RiskScore for injection threat
        """
        base_score = injection_confidence * 100

        # Increase risk based on prompt length (exposure)
        if prompt_length > 500:
            length_multiplier = 1.2
        elif prompt_length > 1000:
            length_multiplier = 1.4
        else:
            length_multiplier = 1.0

        score = min(100, base_score * length_multiplier)
        level = self._score_to_level(score)

        return RiskScore(
            component="INJECTION",
            value=score,
            level=level,
            details=f"Prompt injection risk (confidence: {injection_confidence:.2%}, length: {prompt_length})",
            remediation="Review and sanitize prompt; implement instruction following guardrails",
        )

    def score_compliance_violation(
        self,
        violation: ComplianceViolation,
    ) -> RiskScore:
        """
        Calculate risk score for a compliance violation.

        Args:
            violation: ComplianceViolation object

        Returns:
            RiskScore for this violation
        """
        severity_score = self.SEVERITY_SCORES.get(violation.severity, 50)
        framework_weight = self.FRAMEWORK_WEIGHTS.get(violation.framework, 1.0)

        # Combined score with framework importance
        score = min(100, severity_score * framework_weight)
        level = self._score_to_level(score)

        return RiskScore(
            component=f"COMPLIANCE_{violation.framework}",
            value=score,
            level=level,
            details=f"{violation.rule_name} ({violation.framework}): {violation.message}",
            remediation=violation.remediation,
        )

    def assess_overall_risk(
        self,
        pii_entities: Optional[List[Dict]] = None,
        injection_score: float = 0.0,
        compliance_violations: Optional[List[ComplianceViolation]] = None,
    ) -> OverallRiskAssessment:
        """
        Perform comprehensive risk assessment.

        Args:
            pii_entities: List of detected PII entities
            injection_score: Injection threat confidence (0-1)
            compliance_violations: List of compliance violations

        Returns:
            OverallRiskAssessment with complete analysis
        """
        individual_risks = []

        # Score PII entities
        pii_score = 0.0
        if pii_entities:
            pii_scores = []
            for entity in pii_entities:
                entity_type = entity.get("type", "UNKNOWN")
                confidence = entity.get("confidence", 0.8)
                risk = self.score_pii_entity(entity_type, confidence)
                individual_risks.append(risk)
                pii_scores.append(risk.value)

            pii_score = sum(pii_scores) / len(pii_scores) if pii_scores else 0.0

        # Score injection threat
        injection_risk = None
        if injection_score > 0.1:
            injection_risk = self.score_injection_threat(
                injection_score,
                prompt_length=100,  # Simplified for now
            )
            individual_risks.append(injection_risk)

        injection_score_normalized = injection_risk.value if injection_risk else 0.0

        # Score compliance violations
        compliance_score = 0.0
        if compliance_violations:
            compliance_scores = []
            for violation in compliance_violations:
                risk = self.score_compliance_violation(violation)
                individual_risks.append(risk)
                compliance_scores.append(risk.value)

            compliance_score = (
                sum(compliance_scores) / len(compliance_scores) if compliance_scores else 0.0
            )

        # Calculate overall score (weighted average)
        weights = [0.4, 0.3, 0.3]  # PII, Injection, Compliance
        scores = [pii_score, injection_score_normalized, compliance_score]

        overall_score = sum(s * w for s, w in zip(scores, weights))
        overall_level = self._score_to_level(overall_score)

        # Get top 5 risks
        top_risks = sorted(individual_risks, key=lambda r: r.value, reverse=True)[:5]

        # Generate recommendations
        recommendations = self._generate_recommendations(
            individual_risks,
            overall_level,
            len(pii_entities) if pii_entities else 0,
        )

        # Count critical items
        critical_count = len([r for r in individual_risks if r.level == RiskLevel.CRITICAL])

        return OverallRiskAssessment(
            overall_score=overall_score,
            overall_level=overall_level,
            pii_score=pii_score,
            injection_score=injection_score_normalized,
            compliance_score=compliance_score,
            individual_risks=individual_risks,
            top_risks=top_risks,
            recommendations=recommendations,
            total_entities=len(pii_entities) if pii_entities else 0,
            critical_count=critical_count,
        )

    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert numerical score (0-100) to RiskLevel"""
        if score >= 85:
            return RiskLevel.CRITICAL
        elif score >= 60:
            return RiskLevel.HIGH
        elif score >= 30:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_recommendations(
        self,
        risks: List[RiskScore],
        overall_level: RiskLevel,
        entity_count: int,
    ) -> List[str]:
        """Generate actionable recommendations based on risks"""
        recommendations = []

        # Critical level recommendations
        if overall_level == RiskLevel.CRITICAL:
            recommendations.append("🚨 CRITICAL: Block or quarantine content immediately")
            recommendations.append("Contact security team for incident response")

        # High level recommendations
        elif overall_level == RiskLevel.HIGH:
            recommendations.append("⚠️ Apply strict redaction to all sensitive data")
            recommendations.append("Review and validate all detected entities")

        # Medium level recommendations
        elif overall_level == RiskLevel.MEDIUM:
            recommendations.append("Apply selective redaction to high-risk entities")
            recommendations.append("Monitor for patterns and compliance trends")

        # Specific recommendations based on risk types
        has_pii = any("PII" in r.component for r in risks)
        has_injection = any("INJECTION" in r.component for r in risks)
        has_compliance = any("COMPLIANCE" in r.component for r in risks)

        if has_pii and entity_count > 5:
            recommendations.append("High volume of PII detected - consider bulk redaction")

        if has_injection:
            recommendations.append("Implement prompt input validation and sanitization")

        if has_compliance:
            critical_violations = [
                r for r in risks if "COMPLIANCE" in r.component and r.level == RiskLevel.CRITICAL
            ]
            if critical_violations:
                frameworks = set(r.component.split("_")[1] for r in critical_violations)
                recommendations.append(
                    f"Address {len(frameworks)} framework violations: {', '.join(frameworks)}"
                )

        return recommendations[:5]  # Return top 5 recommendations


def get_risk_scorer() -> RiskScorer:
    """Get or create risk scorer instance"""
    return RiskScorer()
