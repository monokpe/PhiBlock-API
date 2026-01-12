"""
Async API endpoints for Celery task processing.

These endpoints allow clients to:
- Submit async analysis tasks
- Check task status
- Retrieve task results

Endpoint pattern:
- POST /api/v1/analyze/async - Submit analysis task
- GET /api/v1/tasks/{task_id} - Check task status
- GET /api/v1/tasks/{task_id}/result - Get task result
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from workers.celery_app import (
    analyze_complete_async,
    celery_app as app,
    check_compliance_async,
    detect_pii_async,
    get_task_result,
    redact_async,
)

from . import webhook_security
from .token_tracking import get_token_tracker
from .webhooks import WebhookEventType, WebhookPayload, get_webhook_notifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["async"])


def _send_webhook_notification(
    webhook_url: Optional[str],
    task_id: str,
    task_name: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    sign_payload: bool = False,
) -> None:
    """
    Send webhook notification asynchronously.

    This is called as a background task to notify the client of task completion.

    Args:
        webhook_url: URL to send webhook to (if provided)
        task_id: Celery task ID
        task_name: Name of the task
        status: Task status (SUCCESS, FAILURE, etc.)
        result: Task result data
        error: Error message if task failed
    """
    if not webhook_url:
        logger.debug("[_send_webhook_notification] No webhook URL provided")
        return

    try:
        notifier = get_webhook_notifier()

        # Determine event type based on status
        if status == "SUCCESS":
            event_type = WebhookEventType.TASK_COMPLETED
        elif status == "FAILURE":
            event_type = WebhookEventType.TASK_FAILED
        else:
            event_type = WebhookEventType.TASK_SUBMITTED

        # Build payload
        payload = WebhookPayload.build_task_event(
            event_type=event_type,
            task_id=task_id,
            task_name=task_name,
            status=status,
            result=result,
            error=error,
        )

        # Optionally sign payload headers if requested and secret configured
        extra_headers = None
        if sign_payload:
            secret = webhook_security.get_signing_secret()
            if secret:
                try:
                    extra_headers = webhook_security.sign_payload(payload, secret)
                except Exception:
                    logger.exception("Failed to sign webhook payload; continuing without signature")

        # Send webhook (this handles retries internally)
        success, error_msg, attempt = notifier.send_webhook(
            webhook_url, payload, event_type, extra_headers=extra_headers
        )

        if success:
            logger.info(
                f"[_send_webhook_notification] Webhook sent successfully to {webhook_url} "
                f"(task: {task_id}, "
                f"attempt: {attempt})"
            )
        else:
            logger.warning(
                f"[_send_webhook_notification] Failed to send webhook to {webhook_url} "
                f"for task {task_id}: {error_msg}"
            )

    except Exception as e:
        logger.error(f"[_send_webhook_notification] Error sending webhook: {e}")


class AsyncAnalysisRequest(BaseModel):
    """Request model for async analysis"""

    text: str = Field(..., min_length=1, max_length=50000)
    frameworks: Optional[List[str]] = Field(
        default=None,
        description="Frameworks to check (HIPAA, GDPR, PCI_DSS). If null, checks all.",
    )
    include_redaction: bool = Field(
        default=True, description="Whether to include redacted text in response"
    )
    redaction_strategy: str = Field(
        default="token", description="Redaction strategy (mask, token, partial, hash)"
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Optional webhook URL for task completion notifications (HTTP/HTTPS)",
    )
    sign_payload: Optional[bool] = Field(
        default=False,
        description=(
            "If true, request that the server sign webhook payloads "
            "with server-wide HMAC secret (if configured)"
        ),
    )


class AsyncTaskResponse(BaseModel):
    """Response model for async tasks"""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status (PENDING, STARTED, SUCCESS, FAILURE)")
    submitted_at: datetime
    message: str = Field(default="Task submitted successfully")


class TaskStatusResponse(BaseModel):
    """Response model for task status"""

    task_id: str
    status: str
    submitted_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DetectionTaskResponse(BaseModel):
    """Response for PII detection task"""

    status: str
    entities: List[Dict[str, Any]]
    entity_count: int
    text_length: int


class ComplianceTaskResponse(BaseModel):
    """Response for compliance check task"""

    status: str
    compliant: bool
    violation_count: int
    frameworks_checked: List[str]
    violations: List[Dict[str, Any]]


class RedactionTaskResponse(BaseModel):
    """Response for redaction task"""

    status: str
    redacted_text: str
    redaction_count: int
    strategy: str
    original_length: int
    redacted_length: int


class RiskScoreResponse(BaseModel):
    """Response for risk scoring task"""

    status: str
    overall_score: float
    overall_level: str
    pii_score: float
    injection_score: float
    compliance_score: float
    critical_count: int
    total_entities: int
    top_risks: List[Dict[str, Any]]
    recommendations: List[str]


class CompleteAnalysisResponse(BaseModel):
    """Response for complete analysis task"""

    status: str
    pii: Dict[str, Any]
    compliance: Dict[str, Any]
    risk: Dict[str, Any]


from . import auth, models
from .database import get_db
from fastapi import Depends

@router.post(
    "/analyze/async",
    response_model=AsyncTaskResponse,
    summary="Submit async analysis task",
    description="Submit text for asynchronous analysis (PII + Compliance + Risk Scoring)",
)
async def submit_analysis_task(
    request: AsyncAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: models.APIKey = Depends(auth.get_current_user),
) -> AsyncTaskResponse:
    """
    Submit text for complete async analysis.

    Returns task ID that can be used to check status and retrieve results.

    Args:
        request: Analysis request with text and options
        background_tasks: FastAPI background tasks for webhook notifications
        current_user: Authenticated API key
    """
    try:
        logger.info(f"[submit_analysis_task] Submitting analysis for {len(request.text)} chars (tenant={current_user.tenant_id})")

        # Submit task to Celery
        task = analyze_complete_async.delay(
            text=request.text,
            frameworks=request.frameworks,
            webhook_url=request.webhook_url,
            sign_payload=getattr(request, "sign_payload", False),
            tenant_id=str(current_user.tenant_id),
            api_key_id=str(current_user.id),
        )

        # If webhook URL is provided, schedule notification check
        if request.webhook_url:
            background_tasks.add_task(
                _send_webhook_notification,
                webhook_url=request.webhook_url,
                task_id=task.id,
                task_name="analyze_complete_async",
                status="STARTED",
                sign_payload=getattr(request, "sign_payload", False),
            )
            logger.info(
                f"[submit_analysis_task] Webhook notification scheduled for {request.webhook_url}"
            )

        logger.info(f"[submit_analysis_task] Task ID: {task.id}")

        return AsyncTaskResponse(
            task_id=task.id,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
            message="Analysis task submitted successfully",
        )

    except Exception as e:
        logger.error(f"[submit_analysis_task] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/detect/pii/async",
    response_model=AsyncTaskResponse,
    summary="Async PII detection",
)
async def detect_pii_task(
    text: str = Query(..., min_length=1, max_length=50000)
) -> AsyncTaskResponse:
    """Submit text for async PII detection."""
    try:
        logger.info(f"[detect_pii_task] Submitting PII detection for {len(text)} chars")

        task = detect_pii_async.delay(text)

        return AsyncTaskResponse(
            task_id=task.id,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
            message="PII detection task submitted",
        )

    except Exception as e:
        logger.error(f"[detect_pii_task] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/compliance/check/async",
    response_model=AsyncTaskResponse,
    summary="Async compliance check",
)
async def check_compliance_task(
    text: str = Query(..., min_length=1, max_length=50000),
    frameworks: Optional[List[str]] = Query(default=None),
) -> AsyncTaskResponse:
    """Submit text for async compliance checking."""
    try:
        logger.info(f"[check_compliance_task] Submitting compliance check for {len(text)} chars")

        # For compliance, we need entities first (empty for demo)
        # In real usage, would call detect_pii first or use results from prior analysis
        task = check_compliance_async.delay(text, [], frameworks=frameworks)

        return AsyncTaskResponse(
            task_id=task.id,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
            message="Compliance check task submitted",
        )

    except Exception as e:
        logger.error(f"[check_compliance_task] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/redact/async",
    response_model=AsyncTaskResponse,
    summary="Async redaction",
)
async def redact_task(
    text: str = Query(..., min_length=1, max_length=50000),
    strategy: str = Query(default="token"),
) -> AsyncTaskResponse:
    """Submit text for async redaction."""
    try:
        logger.info(f"[redact_task] Submitting redaction for {len(text)} chars using {strategy}")

        # For redaction, we need entities (empty for demo)
        task = redact_async.delay(text, [], strategy=strategy)

        return AsyncTaskResponse(
            task_id=task.id,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
            message="Redaction task submitted",
        )

    except Exception as e:
        logger.error(f"[redact_task] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status",
    description="Check the status of an async task",
)
async def get_task_status_endpoint(task_id: str) -> TaskStatusResponse:
    """
    Get status of a submitted task.

    Args:
        task_id: Celery task ID

    Returns:
        Task status and result (if available)
    """
    try:
        logger.info(f"[get_task_status_endpoint] Checking status for {task_id}")

        result_dict = get_task_result(task_id)

        response = TaskStatusResponse(
            task_id=task_id,
            status=result_dict.get("status", "UNKNOWN"),
            submitted_at=datetime.now(timezone.utc),
            result=result_dict.get("result"),
            error=result_dict.get("error"),
        )

        return response

    except Exception as e:
        logger.error(f"[get_task_status_endpoint] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/tasks/{task_id}/result",
    summary="Get task result",
    description="Retrieve the result of a completed task",
)
async def get_task_result_endpoint(task_id: str) -> Dict[str, Any]:
    """
    Get result of a completed task.

    Args:
        task_id: Celery task ID

    Returns:
        Task result
    """
    try:
        logger.info(f"[get_task_result_endpoint] Getting result for {task_id}")

        result_dict = get_task_result(task_id)

        if result_dict["status"] == "pending":
            raise HTTPException(status_code=202, detail="Task is still processing")
        elif result_dict["status"] == "error":
            raise HTTPException(status_code=400, detail=result_dict.get("error", "Task failed"))

        result: Dict[str, Any] = result_dict.get("result", {})
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_task_result_endpoint] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/tasks/{task_id}",
    summary="Cancel task",
    description="Cancel a pending or running task",
)
async def cancel_task(task_id: str) -> Dict[str, str]:
    """
    Cancel a task.

    Args:
        task_id: Celery task ID

    Returns:
        Cancellation confirmation
    """
    try:
        logger.info(f"[cancel_task] Cancelling task {task_id}")

        task = AsyncResult(task_id, app=app)
        task.revoke(terminate=True)

        return {
            "status": "cancelled",
            "task_id": task_id,
            "message": "Task cancelled successfully",
        }

    except Exception as e:
        logger.error(f"[cancel_task] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/tasks/stats/pending",
    summary="Get pending tasks",
    description="List all pending tasks",
)
async def get_pending_tasks() -> Dict[str, Any]:
    """Get statistics on pending tasks."""
    try:
        from workers.celery_app import app

        active = app.control.inspect().active()

        pending_count = 0
        if active:
            for worker, tasks in active.items():
                pending_count += len(tasks)

        return {
            "pending_count": pending_count,
            "workers_active": len(active) if active else 0,
        }

    except Exception as e:
        logger.error(f"[get_pending_tasks] Error: {e}")
        return {"pending_count": 0, "workers_active": 0, "error": str(e)}


@router.get(
    "/tasks/workers",
    summary="Get worker stats",
    description="Get statistics about active Celery workers",
)
async def get_worker_stats() -> Dict[str, Any]:
    """Get worker statistics."""
    try:
        inspect = app.control.inspect()

        stats = inspect.stats()
        if not stats:
            return {"workers": [], "total_workers": 0}

        return {
            "workers": list(stats.keys()),
            "total_workers": len(stats),
            "stats": stats,
        }

    except Exception as e:
        logger.error(f"[get_worker_stats] Error: {e}")
        return {"workers": [], "total_workers": 0, "error": str(e)}


@router.get(
    "/tokens/stats",
    summary="Get token usage statistics",
    description="Get token counting and cost statistics",
)
async def get_token_stats() -> Dict[str, Any]:
    """Get token tracking statistics."""
    try:
        tracker = get_token_tracker()

        return {
            "tracker_status": "active",
            "thresholds": {
                "warning_threshold": tracker.TOKEN_WARNING_THRESHOLD,
                "critical_threshold": tracker.TOKEN_CRITICAL_THRESHOLD,
            },
            "daily_limit": tracker.DAILY_TOKEN_LIMIT,
            "pricing": {
                "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
                "gpt-4": {"input": 3.00, "output": 6.00},
                "gpt-4-turbo": {"input": 1.00, "output": 3.00},
            },
            "models_supported": [
                "gpt-3.5-turbo",
                "gpt-4",
                "gpt-4-turbo",
                "text-embedding-3",
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"[get_token_stats] Error: {e}")
        return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
