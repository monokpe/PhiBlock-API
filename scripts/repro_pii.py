import os
import sys

# Ensure app is in path
sys.path.append(os.getcwd())

from app.detection import detect_pii  # noqa: E402


def test_pii():
    test_cases = [
        "My email is john.doe@example.com",
        'My email is "john.doe@example.com"',
        "My SSN is 123-45-6789",
    ]

    for text in test_cases:
        _ = detect_pii(text)
        # Process entities


if __name__ == "__main__":
    test_pii()
