import hashlib
import time
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from . import models


async def log_request(
    db: Session,
    api_key: models.APIKey,
    status_code: int,
    start_time: float,
    prompt: str,
    analysis_result: Optional[Dict[str, Any]],
    endpoint: str,
    http_method: str,
    injection_score: Optional[float] = None,
):
    """
    Logs a request and its analysis outcome to the audit_logs table.
    """
    latency_ms = int((time.time() - start_time) * 1000)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    analysis_result = analysis_result or {}
    detections = analysis_result.get("detections", {})
    entities_detected = detections.get("entities")

    audit_log = models.AuditLog(
        request_id=analysis_result.get("request_id", uuid.uuid4()),
        tenant_id=api_key.tenant_id,
        api_key_id=api_key.id,
        endpoint=endpoint,
        http_method=http_method,
        status_code=status_code,
        latency_ms=latency_ms,
        prompt_hash=prompt_hash,
        prompt_length=len(prompt),
        entities_detected=entities_detected,
        injection_score=injection_score,
        compliance_status=analysis_result.get("status", "completed"),
    )
    db.add(audit_log)
    db.commit()
