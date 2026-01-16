"""
Redaction Service - Redact sensitive data from text

Supports multiple redaction strategies:
- Full masking: Replace with ****
- Token replacement: Replace with [TYPE] tag
- Pattern-based: Use custom replacement patterns
- Hash replacement: Replace with hash for consistency
"""

import hashlib
import hmac
import logging
import os
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.compliance.models import ComplianceAction
from app.secrets import secrets

logger = logging.getLogger(__name__)


class RedactionStrategy(Enum):
    """Available redaction strategies"""

    FULL_MASK = "full_mask"  # Replace with ****
    TOKEN_REPLACEMENT = "token"  # Replace with [TYPE]
    PATTERN_BASED = "pattern"  # Custom pattern replacement
    HASH_REPLACEMENT = "hash"  # Replace with hash
    PARTIAL_MASK = "partial"  # Mask but show start/end


class RedactionService:
    """
    Redacts sensitive data from text while maintaining readability.
    """

    def __init__(self, strategy: RedactionStrategy = RedactionStrategy.TOKEN_REPLACEMENT):
        """
        Initialize the redaction service.
        """
        self.strategy = strategy
        self.redaction_map: Dict[str, str] = {}

    def _merge_entities(self, entities: List[Dict], text: str) -> List[Dict]:
        """
        Merge overlapping or adjacent entities.
        """
        if not entities:
            return []

        # Filter out invalid entities
        valid_entities = [
            e for e in entities 
            if e.get("start", -1) >= 0 and e.get("end", -1) > e.get("start", -1)
        ]
        
        if not valid_entities:
            return []

        # Sort by start position
        sorted_ents = sorted(valid_entities, key=lambda e: e.get("start", 0))
        
        merged = []
        current = sorted_ents[0].copy()
        
        for next_ent in sorted_ents[1:]:
            # If overlapping or adjacent
            if next_ent["start"] <= current["end"]:
                # Extend end if needed
                current["end"] = max(current["end"], next_ent["end"])
                
                # Combine types
                c_type = current.get("type", "UNKNOWN")
                n_type = next_ent.get("type", "UNKNOWN")
                if n_type != c_type:
                    types = set(t.strip() for t in c_type.split("|"))
                    types.add(n_type)
                    current["type"] = "|".join(sorted(list(types)))
                
                # Update merged value based on new start/end
                current["value"] = text[current["start"]:current["end"]]
            else:
                merged.append(current)
                current = next_ent.copy()
        
        merged.append(current)
        return merged

    def redact_text(
        self,
        text: str,
        entities: List[Dict],
        strategy: Optional[RedactionStrategy] = None,
        keep_mapping: bool = True,
    ) -> Tuple[str, List[Dict]]:
        """
        Redact sensitive entities from text.

        Args:
            text: Original text
            entities: List of detected entities to redact
            strategy: Redaction strategy (uses default if None)
            keep_mapping: Whether to store mapping for audit trail

        Returns:
            Tuple of (redacted_text, redaction_records)
        """
        if strategy is None:
            strategy = self.strategy

        redacted_text = text
        redaction_records = []

        # Merge overlapping entities first
        merged_entities = self._merge_entities(entities, text)

        sorted_entities = sorted(
            merged_entities,
            key=lambda e: e.get("start", 0),
            reverse=True,
        )

        for entity in sorted_entities:
            original = entity.get("value", "")
            start = entity.get("start", 0)
            end = entity.get("end", 0)
            entity_type = entity.get("type", "UNKNOWN")

            if not original or start < 0 or end <= start:
                continue

            redacted = self._generate_redacted_value(original, entity_type, strategy)

            redacted_text = redacted_text[:start] + redacted + redacted_text[end:]

            if keep_mapping:
                self.redaction_map[original] = redacted

            redaction_records.append(
                {
                    "original": original,
                    "redacted": redacted,
                    "type": entity_type,
                    "strategy": strategy.value,
                    "start": start,
                    "end": end,
                }
            )

        return redacted_text, redaction_records

    def redact_by_pattern(
        self,
        text: str,
        patterns: Dict[str, str],
        strategy: Optional[RedactionStrategy] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        Redact text matching patterns.
        """
        if strategy is None:
            strategy = self.strategy

        redacted_text = text
        redaction_records = []

        for pattern_name, pattern in patterns.items():
            try:
                matches = list(re.finditer(pattern, text, re.IGNORECASE))

                for match in reversed(matches):
                    original = match.group(0)
                    start = match.start()
                    end = match.end()

                    redacted = self._generate_redacted_value(original, pattern_name, strategy)

                    redacted_text = redacted_text[:start] + redacted + redacted_text[end:]

                    redaction_records.append(
                        {
                            "original": original,
                            "redacted": redacted,
                            "type": pattern_name,
                            "strategy": strategy.value,
                            "start": start,
                            "end": end,
                        }
                    )
            except re.error as e:
                logger.warning(f"Invalid pattern {pattern_name}: {e}")

        return redacted_text, redaction_records

    def redact_action(
        self,
        text: str,
        entities: List[Dict],
        action: ComplianceAction,
    ) -> Tuple[str, List[Dict]]:
        """
        Redact based on compliance action.
        """
        if action == ComplianceAction.BLOCK:
            return "", []
        elif action == ComplianceAction.REDACT:
            return self.redact_text(text, entities)
        elif action == ComplianceAction.FLAG:
            return text, []

        return text, []

    def _generate_redacted_value(
        self,
        original: str,
        entity_type: str,
        strategy: RedactionStrategy,
    ) -> str:
        """
        Generate redacted value based on strategy.
        """
        if strategy == RedactionStrategy.FULL_MASK:
            return "****"

        elif strategy == RedactionStrategy.TOKEN_REPLACEMENT:
            return f"[{entity_type}]"

        elif strategy == RedactionStrategy.PARTIAL_MASK:
            if len(original) <= 4:
                return "*" * len(original)
            return original[0] + "*" * (len(original) - 2) + original[-1]

        elif strategy == RedactionStrategy.HASH_REPLACEMENT:
            key = secrets.get("PII_REDACTION_KEY") or os.getenv("PII_REDACTION_KEY")
            if key:
                if isinstance(key, str):
                    key_bytes = key.encode("utf-8")
                else:
                    key_bytes = key
                mac = hmac.new(key_bytes, original.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
                hash_val = mac
            else:
                hash_val = hashlib.sha256(original.encode()).hexdigest()[:8]
            return f"[{entity_type}:{hash_val}]"

        return "****"

    def clear_mapping(self) -> None:
        """Clear the redaction mapping"""
        self.redaction_map.clear()

    def get_mapping(self) -> Dict[str, str]:
        """Get the current redaction mapping"""
        return self.redaction_map.copy()


class RedactionPipeline:
    """
    Chain multiple redaction operations together.
    """

    def __init__(self, service: Optional[RedactionService] = None):
        """
        Initialize redaction pipeline.
        """
        self.service = service or RedactionService()
        self.operations: List[Tuple] = []

    def add_entity_redaction(
        self,
        strategy: RedactionStrategy = RedactionStrategy.TOKEN_REPLACEMENT,
    ) -> "RedactionPipeline":
        """Add entity-based redaction step"""
        self.operations.append(("entity", strategy))
        return self

    def add_pattern_redaction(
        self,
        patterns: Dict[str, str],
        strategy: RedactionStrategy = RedactionStrategy.TOKEN_REPLACEMENT,
    ) -> "RedactionPipeline":
        """Add pattern-based redaction step"""
        self.operations.append(("pattern", patterns, strategy))
        return self

    def execute(
        self,
        text: str,
        entities: Optional[List[Dict]] = None,
    ) -> Tuple[str, List[List[Dict]]]:
        """
        Execute all redaction steps.

        Args:
            text: Text to redact
            entities: Entities to redact

        Returns:
            Tuple of (redacted_text, list_of_redaction_records)
        """
        redacted_text = text
        all_records = []

        for operation in self.operations:
            if operation[0] == "entity":
                strategy = operation[1]
                redacted_text, records = self.service.redact_text(
                    redacted_text,
                    entities or [],
                    strategy=strategy,
                )

            elif operation[0] == "pattern":
                patterns = operation[1]
                strategy = operation[2]
                redacted_text, records = self.service.redact_by_pattern(
                    redacted_text,
                    patterns,
                    strategy=strategy,
                )

            all_records.append(records)

        return redacted_text, all_records


# Global redaction service instance
_redaction_service: Optional[RedactionService] = None


def get_redaction_service(
    strategy: RedactionStrategy = RedactionStrategy.TOKEN_REPLACEMENT,
) -> RedactionService:
    """Get or create global redaction service"""
    global _redaction_service
    if _redaction_service is None:
        _redaction_service = RedactionService(strategy)
    return _redaction_service


def reset_redaction_service() -> None:
    """Reset the redaction service"""
    global _redaction_service
    _redaction_service = None
