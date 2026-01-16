"""
Compliance Engine - Data Models

Defines the ComplianceRule and ComplianceViolation data structures
used throughout the compliance evaluation pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Severity(str, Enum):
    """Violation severity levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComplianceAction(str, Enum):
    """Actions to take when a rule is violated"""

    BLOCK = "block"  # Reject the request entirely
    REDACT = "redact"  # Redact the matching content
    FLAG = "flag"  # Log the violation but allow request


@dataclass
class ComplianceRule:
    """
    A compliance rule that checks for specific violations.
    """

    id: str
    framework: str
    name: str
    description: str
    severity: Severity

    entity_types: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)

    action: ComplianceAction = ComplianceAction.FLAG
    remediation: str = ""

    def __post_init__(self):
        if self.entity_types is None:
            self.entity_types = []
        if self.keywords is None:
            self.keywords = []
        if self.patterns is None:
            self.patterns = []

        if isinstance(self.severity, str):
            self.severity = Severity(self.severity)
        if isinstance(self.action, str):
            self.action = ComplianceAction(self.action)


@dataclass
class ComplianceViolation:
    """A single compliance violation detected in the content"""

    rule_id: str
    framework: str
    rule_name: str
    severity: Severity
    message: str
    remediation: str
    action: ComplianceAction
    matched_content: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    entity_types: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.entity_types is None:
            self.entity_types = []
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity)
        if isinstance(self.action, str):
            self.action = ComplianceAction(self.action)


@dataclass
class ComplianceResult:
    """Overall compliance check result"""

    frameworks_checked: List[str]
    violations: List[ComplianceViolation]
    compliant: bool

    @property
    def critical_violations(self) -> List[ComplianceViolation]:
        """Get all critical violations"""
        return [v for v in self.violations if v.severity == Severity.CRITICAL]

    @property
    def high_violations(self) -> List[ComplianceViolation]:
        """Get all high severity violations"""
        return [v for v in self.violations if v.severity == Severity.HIGH]

    @property
    def summary(self) -> Dict:
        """Return summary of violations by severity"""
        return {
            "total": len(self.violations),
            "critical": len(self.critical_violations),
            "high": len(self.high_violations),
            "medium": len([v for v in self.violations if v.severity == Severity.MEDIUM]),
            "low": len([v for v in self.violations if v.severity == Severity.LOW]),
        }


class ComplianceFramework(str, Enum):
    """Supported compliance frameworks"""

    HIPAA = "HIPAA"
    GDPR = "GDPR"
    PCI_DSS = "PCI-DSS"
    SOC2 = "SOC2"
    CCPA = "CCPA"
    PIPEDA = "PIPEDA"
    SECURITY = "Security"
