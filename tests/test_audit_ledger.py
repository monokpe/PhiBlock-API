import os
import tempfile

from cryptography.hazmat.primitives import hashes

from app.audit_ledger import AuditLedger


def test_append_and_verify(monkeypatch):
    # Provide a ledger key via env
    monkeypatch.setenv("AUDIT_LEDGER_KEY", "ledger-test-key")

    with tempfile.TemporaryDirectory() as td:
        path = f"{td}/ledger.log"
        ledger = AuditLedger(path)
        r1 = ledger.append({"event": "one"})
        r2 = ledger.append({"event": "two"})

        assert r2.index == r1.index + 1
        assert AuditLedger.verify_file(path) is True


def test_tamper_detection(monkeypatch):
    monkeypatch.setenv("AUDIT_LEDGER_KEY", "ledger-test-key")
    with tempfile.TemporaryDirectory() as td:
        path = f"{td}/ledger.log"
        ledger = AuditLedger(path)
        ledger.append({"event": "one"})
        ledger.append({"event": "two"})

        # Tamper with file: change payload of second line
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        assert len(lines) >= 2
        # Modify second line's payload naively
        import json

        obj = json.loads(lines[1])
        obj["payload"]["event"] = "tampered"
        lines[1] = json.dumps(obj, separators=(",", ":")) + "\n"

        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)

        assert AuditLedger.verify_file(path) is False
