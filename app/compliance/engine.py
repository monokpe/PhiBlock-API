"""
Compliance Engine - Core Implementation

Loads compliance rules and evaluates text against them.
Supports multiple compliance frameworks (HIPAA, GDPR, PCI-DSS).
"""

import logging
import re
from typing import Dict, List, Optional

from app.compliance.models import ComplianceResult, ComplianceRule, ComplianceViolation, Severity

logger = logging.getLogger(__name__)


class ComplianceEngine:
    def __init__(self):
        self.rules: Dict[str, List[ComplianceRule]] = {}
        self.frameworks: List[str] = []

    def load_rules(self, rules: List[ComplianceRule]) -> None:
        """
        Load a list of compliance rules.
        Existing rules are cleared to prevent duplication.
        """
        # Clear existing rules to prevent duplicates
        self.rules = {}
        self.frameworks = []

        for rule in rules:
            if rule.framework not in self.rules:
                self.rules[rule.framework] = []
            
            # Check for duplicates by ID within the framework
            existing_ids = {r.id for r in self.rules[rule.framework]}
            if rule.id not in existing_ids:
                self.rules[rule.framework].append(rule)
            else:
                logger.warning(f"Duplicate rule ignored: {rule.id} in framework {rule.framework}")

        self.frameworks = list(self.rules.keys())

    def check_compliance(
        self,
        text: str,
        detected_entities: List[Dict],
        frameworks: Optional[List[str]] = None,
    ) -> ComplianceResult:
        """
        Check text against compliance rules.

        Args:
            text: The text to check
            detected_entities: List of detected PII entities
            frameworks: Specific frameworks to check (None = all)

        Returns:
            ComplianceResult with all violations found
        """
        if frameworks is None:
            frameworks = self.frameworks

        violations: List[ComplianceViolation] = []

        for framework in frameworks:
            if framework not in self.rules:
                continue

            for rule in self.rules[framework]:
                rule_violations = self._check_rule(text, detected_entities, rule)
                violations.extend(rule_violations)

        critical_violations = [
            v for v in violations if v.severity in [Severity.CRITICAL, Severity.HIGH]
        ]
        compliant = len(critical_violations) == 0

        return ComplianceResult(
            frameworks_checked=frameworks,
            violations=violations,
            compliant=compliant,
        )

    def _check_rule(
        self,
        text: str,
        detected_entities: List[Dict],
        rule: ComplianceRule,
    ) -> List[ComplianceViolation]:
        violations = []

        if rule.entity_types:
            for entity in detected_entities:
                if entity.get("type") in rule.entity_types:
                    violations.append(
                        ComplianceViolation(
                            rule_id=rule.id,
                            framework=rule.framework,
                            rule_name=rule.name,
                            severity=rule.severity,
                            message=f"{rule.name} detected: {entity.get('type')}",
                            remediation=rule.remediation,
                            action=rule.action,
                            matched_content=entity.get("value"),
                            entity_types=[str(entity.get("type", "UNKNOWN"))],
                        )
                    )

        if rule.keywords:
            text_lower = text.lower()
            for keyword in rule.keywords:
                if keyword.lower() in text_lower:
                    violations.append(
                        ComplianceViolation(
                            rule_id=rule.id,
                            framework=rule.framework,
                            rule_name=rule.name,
                            severity=rule.severity,
                            message=f"{rule.name}: keyword '{keyword}' found",
                            remediation=rule.remediation,
                            action=rule.action,
                            matched_content=keyword,
                            start=text_lower.find(keyword.lower()),
                            end=text_lower.find(keyword.lower()) + len(keyword),
                        )
                    )
                    break

        if rule.patterns:
            for pattern in rule.patterns:
                try:
                    matches = re.finditer(pattern, text, re.IGNORECASE)
                    for match in matches:
                        violations.append(
                            ComplianceViolation(
                                rule_id=rule.id,
                                framework=rule.framework,
                                rule_name=rule.name,
                                severity=rule.severity,
                                message=f"{rule.name}: pattern matched",
                                remediation=rule.remediation,
                                action=rule.action,
                                matched_content=match.group(0),
                                start=match.start(),
                                end=match.end(),
                            )
                        )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern in rule {rule.id}: {e}")

        return violations

    def get_rules_by_framework(self, framework: str) -> List[ComplianceRule]:
        """Get all rules for a specific framework"""
        return self.rules.get(framework, [])

    def get_rule_by_id(self, rule_id: str) -> Optional[ComplianceRule]:
        """Get a specific rule by ID"""
        for rules in self.rules.values():
            for rule in rules:
                if rule.id == rule_id:
                    return rule
        return None


# Global engine instance
_compliance_engine: Optional[ComplianceEngine] = None


def get_compliance_engine() -> ComplianceEngine:
    """Get or create the global compliance engine"""
    global _compliance_engine
    if _compliance_engine is None:
        _compliance_engine = ComplianceEngine()
    return _compliance_engine


def reset_compliance_engine() -> None:
    """Reset the compliance engine (useful for testing)"""
    global _compliance_engine
    _compliance_engine = None
