"""
Rule Loader - Load compliance rules from YAML files

Handles parsing YAML rule definitions and converting them to ComplianceRule objects.
Supports validation and rule merging from multiple sources.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.compliance.models import (
    ComplianceAction,
    ComplianceFramework,
    ComplianceRule,
    Severity,
)


class RuleLoader:
    """Load compliance rules from YAML files"""

    def __init__(self, rules_dir: Optional[str] = None):
        """
        Initialize the rule loader.

        Args:
            rules_dir: Directory containing rule YAML files.
                      Defaults to app/compliance/definitions/
        """
        if rules_dir is None:
            # Default to definitions directory in same package
            current_dir = Path(__file__).parent
            rules_dir = str(current_dir / "definitions")

        self.rules_dir = Path(rules_dir)

    def load_all_rules(self) -> List[ComplianceRule]:
        """
        Load all rules from YAML files in the rules directory.

        Returns:
            List of ComplianceRule objects
        """
        rules = []

        if not self.rules_dir.exists():
            print(f"Warning: Rules directory not found: {self.rules_dir}")
            return rules

        # Find all YAML files
        yaml_files = list(self.rules_dir.glob("*.yaml")) + list(self.rules_dir.glob("*.yml"))

        for yaml_file in sorted(yaml_files):
            try:
                file_rules = self.load_rules_from_file(str(yaml_file))
                rules.extend(file_rules)
            except Exception as e:
                print(f"Error loading rules from {yaml_file.name}: {e}")

        return rules

    def load_rules_from_file(self, filepath: str) -> List[ComplianceRule]:
        """
        Load rules from a single YAML file.

        Args:
            filepath: Path to the YAML file

        Returns:
            List of ComplianceRule objects
        """
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if not data or "rules" not in data:
            return []

        rules = []
        for rule_data in data["rules"]:
            try:
                rule = self._parse_rule(rule_data, data.get("framework"))
                if rule:
                    rules.append(rule)
            except Exception as e:
                print(f"Error parsing rule: {e}")
                continue

        return rules

    def _parse_rule(
        self, rule_data: Dict[str, Any], default_framework: Optional[str] = None
    ) -> Optional[ComplianceRule]:
        """
        Parse a single rule from YAML data.

        Args:
            rule_data: Rule configuration dict
            default_framework: Framework to use if not specified in rule

        Returns:
            ComplianceRule object or None if invalid
        """
        # Get framework
        framework_str = rule_data.get("framework", default_framework)
        if not framework_str:
            raise ValueError("Framework not specified")

        try:
            framework = ComplianceFramework[framework_str.upper()]
        except KeyError:
            raise ValueError(f"Unknown framework: {framework_str}")

        # Get ID and name
        rule_id = rule_data.get("id", f"rule_{hash(str(rule_data))}")
        name = rule_data.get("name", "Unnamed Rule")

        # Get severity
        severity_str = rule_data.get("severity", "medium").lower()
        try:
            severity = Severity[severity_str.upper()]
        except KeyError:
            severity = Severity.MEDIUM

        # Get action
        action_str = rule_data.get("action", "flag").lower()
        try:
            action = ComplianceAction[action_str.upper()]
        except KeyError:
            action = ComplianceAction.FLAG

        # Get description and remediation
        description = rule_data.get("description", "")
        remediation = rule_data.get("remediation", f"Review and remediate {name}")

        # Get matching criteria
        entity_types = rule_data.get("entity_types", [])
        keywords = rule_data.get("keywords", [])
        patterns = rule_data.get("patterns", [])

        # Validate at least one matching criterion
        if not (entity_types or keywords or patterns):
            raise ValueError(f"Rule {rule_id} has no matching criteria")

        return ComplianceRule(
            id=rule_id,
            name=name,
            description=description,
            framework=framework.value,
            severity=severity,
            action=action,
            entity_types=entity_types,
            keywords=keywords,
            patterns=patterns,
            remediation=remediation,
        )

    def validate_rules(self, rules: List[ComplianceRule]) -> Dict[str, Any]:
        """
        Validate a set of rules.

        Args:
            rules: Rules to validate

        Returns:
            Validation report with counts and any issues
        """
        report = {
            "total": len(rules),
            "by_framework": {},
            "by_severity": {},
            "by_action": {},
            "issues": [],
        }

        for rule in rules:
            # Count by framework
            framework = rule.framework
            report["by_framework"][framework] = report["by_framework"].get(framework, 0) + 1

            # Count by severity
            severity = rule.severity.name.lower()
            report["by_severity"][severity] = report["by_severity"].get(severity, 0) + 1

            # Count by action
            action = rule.action.name.lower()
            report["by_action"][action] = report["by_action"].get(action, 0) + 1

            # Validate patterns (regex)
            import re

            for pattern in rule.patterns:
                try:
                    re.compile(pattern)
                except re.error as e:
                    report["issues"].append(f"Invalid regex in rule {rule.id}: {pattern} - {e}")

        return report


def load_compliance_rules(rules_dir: Optional[str] = None) -> List[ComplianceRule]:
    """
    Convenience function to load all compliance rules.

    Args:
        rules_dir: Optional directory to load from

    Returns:
        List of loaded ComplianceRule objects
    """
    loader = RuleLoader(rules_dir)
    return loader.load_all_rules()
