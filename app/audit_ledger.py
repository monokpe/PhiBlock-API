"""Tamper-evident, append-only audit ledger.

This module implements a simple append-only audit ledger stored as
newline-delimited JSON. Each record is chained by including the
previous record's hash and a signature (HMAC-SHA256) produced using a
server-side ledger key. The ledger supports writing records and
verifying integrity of the whole file.

Usage:
    from app.audit_ledger import AuditLedger
    ledger = AuditLedger(path="/var/log/guardrails_audit.log")
    ledger.append({"event": "request", "user": "abc"})
    AuditLedger.verify_file(path)

The signing key is read from `AUDIT_LEDGER_KEY` env var or via
`app.secrets` (preferred). If not present, signing is disabled and a
warning is emitted — production MUST set a key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from .secrets import secrets


def _get_ledger_key() -> Optional[bytes]:
    key = secrets.get("AUDIT_LEDGER_KEY") or os.getenv("AUDIT_LEDGER_KEY")
    if not key:
        return None
    if isinstance(key, str):
        return key.encode("utf-8")
    return key


def _hmac_sign(key: bytes, message: bytes) -> str:
    mac = hmac.new(key, message, hashlib.sha256)
    return mac.hexdigest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class LedgerRecord:
    index: int
    timestamp: str
    payload: Dict[str, Any]
    prev_hash: Optional[str]
    hash: str
    signature: Optional[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
                "hash": self.hash,
                "signature": self.signature,
            },
            separators=(",", ":"),
        )


class AuditLedger:
    def __init__(self, path: str):
        self.path = path
        self.key = _get_ledger_key()

        dirname = os.path.dirname(self.path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        if not os.path.exists(self.path):
            open(self.path, "a", encoding="utf-8").close()

    def _iter_records(self) -> Iterator[LedgerRecord]:
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                yield LedgerRecord(
                    index=obj["index"],
                    timestamp=obj["timestamp"],
                    payload=obj["payload"],
                    prev_hash=obj.get("prev_hash"),
                    hash=obj.get("hash"),
                    signature=obj.get("signature"),
                )

    def append(self, payload: Dict[str, Any]) -> LedgerRecord:
        # Determine index and prev_hash from last record
        last = None
        for r in self._iter_records():
            last = r

        index = (last.index + 1) if last else 0
        prev_hash = last.hash if last else None

        timestamp = datetime.now(timezone.utc).isoformat()
        body = json.dumps(
            {
                "index": index,
                "timestamp": timestamp,
                "payload": payload,
                "prev_hash": prev_hash,
            },
            separators=(",", ":"),
        )
        body_bytes = body.encode("utf-8")
        record_hash = _sha256_hex(body_bytes)

        signature = None
        if self.key:
            signature = _hmac_sign(self.key, body_bytes)

        record = LedgerRecord(
            index=index,
            timestamp=timestamp,
            payload=payload,
            prev_hash=prev_hash,
            hash=record_hash,
            signature=signature,
        )

        # Append to file atomically
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")

        return record

    def verify(self) -> bool:
        """Verify ledger integrity and signatures.

        Returns True if ledger is valid, False otherwise.
        """
        expected_prev = None
        for rec in self._iter_records():
            # Reconstruct body used for hash/signature
            body = json.dumps(
                {
                    "index": rec.index,
                    "timestamp": rec.timestamp,
                    "payload": rec.payload,
                    "prev_hash": rec.prev_hash,
                },
                separators=(",", ":"),
            )
            body_bytes = body.encode("utf-8")
            computed_hash = _sha256_hex(body_bytes)
            if computed_hash != rec.hash:
                return False

            if rec.prev_hash != expected_prev:
                return False

            if self.key:
                if not rec.signature:
                    return False
                if _hmac_sign(self.key, body_bytes) != rec.signature:
                    return False

            expected_prev = rec.hash

        return True

    @staticmethod
    def verify_file(path: str, key: Optional[bytes] = None) -> bool:
        ledger = AuditLedger(path)
        if key is not None:
            ledger.key = key
        return ledger.verify()


__all__ = ["AuditLedger", "LedgerRecord"]
