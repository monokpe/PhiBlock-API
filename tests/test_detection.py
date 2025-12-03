import pytest

from app.detection import detect_pii


def test_detect_pii_with_ssn():
    text = "My social security number is 123-45-6789."
    entities = detect_pii(text)
    assert len(entities) == 1
    assert entities[0]["type"] == "SSN"
    assert entities[0]["value"] == "123-45-6789"


def test_detect_pii_with_credit_card():
    text = "My credit card is 1234-5678-9012-3456."
    entities = detect_pii(text)
    assert len(entities) == 1
    assert entities[0]["type"] == "CREDIT_CARD"


def test_detect_pii_with_phone():
    text = "Call me at (123) 456-7890."
    entities = detect_pii(text)
    assert len(entities) == 1
    assert entities[0]["type"] == "PHONE"


def test_detect_pii_with_spacy_person():
    text = "My name is John Doe."
    entities = detect_pii(text)
    assert len(entities) == 1
    assert entities[0]["type"] == "PERSON"
    assert entities[0]["value"] == "John Doe"


def test_detect_pii_no_pii():
    text = "This is a test sentence with no PII."
    entities = detect_pii(text)
    # Filter out ORG entities which can be false positives
    filtered_entities = [e for e in entities if e["type"] != "ORG"]
    assert len(filtered_entities) == 0


def test_detect_pii_mixed():
    text = "My name is Jane Doe and my number is 987-654-3210."
    entities = detect_pii(text)
    assert len(entities) == 2
    # Note: the order of entities is not guaranteed
    entity_types = {e["type"] for e in entities}
    assert "PERSON" in entity_types
    assert "PHONE" in entity_types


def test_detect_pii_false_positives():
    text = "My order number is 123456789012 and I live at 123 Main St."
    entities = detect_pii(text)
    # Filter out any potential false positives we are not concerned about for this test
    filtered_entities = [
        e for e in entities if e["type"] not in ["DATE", "CARDINAL", "ORG", "GPE", "LOC", "FAC"]
    ]
    assert len(filtered_entities) == 0


def test_detect_pii_unicode_obfuscation():
    # Use full-width characters to simulate obfuscation
    text = "My name is Jｏｈn Dｏe and my number is ９８７-６５４-３２１０."
    entities = detect_pii(text)
    assert len(entities) >= 2
    entity_types = {e["type"] for e in entities}
    assert "PERSON" in entity_types
    assert "PHONE" in entity_types
