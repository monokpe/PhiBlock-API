import re

import spacy

# Load the spaCy model
nlp = spacy.load("en_core_web_sm")

# Regex patterns for PII
REGEX_PATTERNS = {
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "PHONE": r"\b(?:\+?1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b",
}


def detect_pii(text: str) -> list[dict]:
    """Detect PII in a string using regex and spaCy."""
    entities = []

    # Regex-based detection
    for entity_type, pattern in REGEX_PATTERNS.items():
        for match in re.finditer(pattern, text):
            entities.append(
                {
                    "type": entity_type,
                    "value": match.group(0),
                    "position": {"start": match.start(), "end": match.end()},
                    "confidence": 1.0,  # Regex matches are considered high confidence
                }
            )

    # spaCy-based detection
    doc = nlp(text)
    for ent in doc.ents:
        # Avoid duplicating entities found by regex
        is_duplicate = False
        for existing_entity in entities:
            if (
                ent.start_char >= existing_entity["position"]["start"]
                and ent.end_char <= existing_entity["position"]["end"]
            ):
                is_duplicate = True
                break

        if not is_duplicate:
            entities.append(
                {
                    "type": ent.label_,
                    "value": ent.text,
                    "position": {"start": ent.start_char, "end": ent.end_char},
                    "confidence": 0.8,  # spaCy confidence is generally lower than regex
                }
            )

    return entities
