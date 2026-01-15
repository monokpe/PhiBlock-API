"""
Compliance Module

Handles compliance rule evaluation against multiple frameworks:
- HIPAA: Health Insurance Portability and Accountability Act
- GDPR: General Data Protection Regulation
- PCI-DSS: Payment Card Industry Data Security Standard

Components:
- models: Data structures for rules and violations
- engine: Core compliance evaluation engine
- rules: YAML rule loading and parsing
- redaction: Text redaction with multiple strategies
- risk_scoring: Risk assessment and scoring engine
"""

from app.compliance.engine import ComplianceEngine, get_compliance_engine, reset_compliance_engine
from app.compliance.models import (
    ComplianceAction,
    ComplianceFramework,
    ComplianceResult,
    ComplianceRule,
    ComplianceViolation,
    Severity,
)
from app.compliance.redaction import (
    RedactionPipeline,
    RedactionService,
    RedactionStrategy,
    get_redaction_service,
    reset_redaction_service,
)
from app.compliance.risk_scoring import (
    OverallRiskAssessment,
    RiskLevel,
    RiskScore,
    RiskScorer,
    get_risk_scorer,
)
from app.compliance.rules import RuleLoader, load_compliance_rules

__all__ = [
    "ComplianceRule",
    "ComplianceViolation",
    "ComplianceResult",
    "ComplianceFramework",
    "Severity",
    "ComplianceAction",
    "ComplianceEngine",
    "get_compliance_engine",
    "reset_compliance_engine",
    "RuleLoader",
    "load_compliance_rules",
    "RedactionService",
    "RedactionStrategy",
    "RedactionPipeline",
    "get_redaction_service",
    "reset_redaction_service",
    "RiskScorer",
    "RiskLevel",
    "RiskScore",
    "OverallRiskAssessment",
    "get_risk_scorer",
]
