"""
Celery Workers Module

Async task processing for Guardrails compliance engine.

Tasks:
- PII Detection (async)
- Compliance Checking (async)
- Redaction (async)
- Risk Scoring (async)
- Complete Analysis (composite)

Usage:
    # Import Celery app
    from workers.celery_app import app

    # Schedule a task
    from workers.celery_app import detect_pii_async
    task = detect_pii_async.delay("John Doe lives in NYC")

    # Get result
    result = task.get()
"""

from workers.celery_app import (
    analyze_complete_async,
    app,
    check_compliance_async,
    detect_pii_async,
    get_task_result,
    get_task_status,
    redact_async,
    score_risk_async,
)

__all__ = [
    "app",
    "detect_pii_async",
    "check_compliance_async",
    "redact_async",
    "score_risk_async",
    "analyze_complete_async",
    "get_task_result",
    "get_task_status",
]
