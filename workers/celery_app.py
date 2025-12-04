"""
Celery Configuration and Task Definitions

Async task processing for:
- PII detection
- Compliance checking
- Redaction
- Risk scoring

Uses Redis as broker and result backend.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

# Get configuration from environment or use defaults
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BROKER_URL = os.getenv("BROKER_URL", REDIS_URL)
RESULT_BACKEND = os.getenv("RESULT_BACKEND", REDIS_URL)

# Create Celery app
app = Celery("guardrails")

# Configure Celery
app.conf.update(
    # Broker and backend configuration
    broker_url=BROKER_URL,
    result_backend=RESULT_BACKEND,
    # Task configuration
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard time limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft time limit
    task_acks_late=True,  # Tasks acknowledged after execution
    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_max_tasks_per_child=1000,  # Recycle workers after 1000 tasks
    # Retry configuration
    task_autoretry_for=(Exception,),
    task_max_retries=3,
    task_default_retry_delay=60,  # 60 seconds between retries
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,
    # Queue configuration
    task_queues=(
        Queue("detection", Exchange("detection"), routing_key="detection"),
        Queue("compliance", Exchange("compliance"), routing_key="compliance"),
        Queue("redaction", Exchange("redaction"), routing_key="redaction"),
        Queue("scoring", Exchange("scoring"), routing_key="scoring"),
        Queue("default", Exchange("default"), routing_key="default"),
    ),
    # Task routing
    task_routes={
        "workers.tasks.detect_pii_async": {"queue": "detection"},
        "workers.tasks.check_compliance_async": {"queue": "compliance"},
        "workers.tasks.redact_async": {"queue": "redaction"},
        "workers.tasks.score_risk_async": {"queue": "scoring"},
        "workers.celery_app.sync_usage_to_stripe": {"queue": "default"},
    },
)

# Configure Periodic Tasks (Celery Beat)
app.conf.beat_schedule = {
    "sync-usage-every-hour": {
        "task": "workers.celery_app.sync_usage_to_stripe",
        "schedule": crontab(minute=0),  # Run every hour
    },
}


# ============================================================================
# TASK DEFINITIONS
# ============================================================================


@app.task(
    bind=True,
    name="workers.tasks.detect_pii_async",
    max_retries=3,
    autoretry_for=(Exception,),
)
def detect_pii_async(self, text: str) -> Dict[str, Any]:
    """
    Async task: Detect PII in text.

    Args:
        text: Text to analyze

    Returns:
        Dict with detected entities
    """
    try:
        from app.detection import detect_pii

        logger.info(f"[detect_pii_async] Processing {len(text)} chars")

        entities = detect_pii(text)

        result = {
            "status": "success",
            "entities": entities,
            "entity_count": len(entities),
            "text_length": len(text),
        }

        logger.info(f"[detect_pii_async] Detected {len(entities)} entities")
        return result

    except Exception as exc:
        logger.error(f"[detect_pii_async] Error: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@app.task(
    bind=True,
    name="workers.tasks.check_compliance_async",
    max_retries=3,
    autoretry_for=(Exception,),
)
def check_compliance_async(
    self,
    text: str,
    entities: List[Dict],
    frameworks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Async task: Check text against compliance rules.

    Args:
        text: Text to check
        entities: Detected PII entities
        frameworks: Frameworks to check (default: all)

    Returns:
        Dict with compliance results
    """
    try:
        from app.compliance import ComplianceEngine, load_compliance_rules

        logger.info(
            f"[check_compliance_async] Processing {len(text)} chars against "
            f"{frameworks or 'all'} frameworks"
        )

        # Load rules
        rules = load_compliance_rules()

        # Create engine
        engine = ComplianceEngine()
        engine.load_rules(rules)

        # Check compliance
        result_obj = engine.check_compliance(text, entities, frameworks=frameworks)

        result = {
            "status": "success",
            "compliant": result_obj.compliant,
            "violation_count": len(result_obj.violations),
            "frameworks_checked": result_obj.frameworks_checked,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "framework": v.framework,
                    "rule_name": v.rule_name,
                    "severity": v.severity.name,
                    "action": v.action.name,
                    "message": v.message,
                }
                for v in result_obj.violations[:10]  # Top 10 violations
            ],
        }

        logger.info(f"[check_compliance_async] Found {len(result_obj.violations)} violations")
        return result

    except Exception as exc:
        logger.error(f"[check_compliance_async] Error: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@app.task(
    bind=True,
    name="workers.tasks.redact_async",
    max_retries=3,
    autoretry_for=(Exception,),
)
def redact_async(
    self,
    text: str,
    entities: List[Dict],
    strategy: str = "token",
) -> Dict[str, Any]:
    """
    Async task: Redact sensitive data from text.

    Args:
        text: Original text
        entities: Entities to redact
        strategy: Redaction strategy (token, mask, partial, hash)

    Returns:
        Dict with redacted text and mapping
    """
    try:
        from app.compliance.redaction import RedactionService, RedactionStrategy

        logger.info(f"[redact_async] Redacting {len(entities)} entities using {strategy}")

        # Convert strategy string to enum
        strategy_map = {
            "mask": RedactionStrategy.FULL_MASK,
            "token": RedactionStrategy.TOKEN_REPLACEMENT,
            "partial": RedactionStrategy.PARTIAL_MASK,
            "hash": RedactionStrategy.HASH_REPLACEMENT,
        }

        redaction_strategy = strategy_map.get(strategy, RedactionStrategy.TOKEN_REPLACEMENT)

        # Redact
        service = RedactionService(redaction_strategy)
        redacted_text, records = service.redact_text(text, entities)

        result = {
            "status": "success",
            "redacted_text": redacted_text,
            "redaction_count": len(records),
            "strategy": strategy,
            "original_length": len(text),
            "redacted_length": len(redacted_text),
        }

        logger.info(f"[redact_async] Applied {len(records)} redactions")
        return result

    except Exception as exc:
        logger.error(f"[redact_async] Error: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@app.task(
    bind=True,
    name="workers.tasks.score_risk_async",
    max_retries=3,
    autoretry_for=(Exception,),
)
def score_risk_async(
    self,
    entities: List[Dict],
    injection_score: float = 0.0,
    violations: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Async task: Assess overall risk from all components.

    Args:
        entities: Detected PII entities
        injection_score: Injection threat confidence
        violations: Compliance violations (dicts)

    Returns:
        Dict with risk assessment
    """
    try:
        from app.compliance import RiskScorer
        from app.compliance.models import ComplianceAction, ComplianceViolation, Severity

        logger.info(f"[score_risk_async] Scoring {len(entities)} entities")

        # Convert violations back to objects
        violation_objects = []
        if violations:
            severity_map = {s.name: s for s in Severity}
            action_map = {a.name: a for a in ComplianceAction}

            for v in violations:
                violation_objects.append(
                    ComplianceViolation(
                        rule_id=v.get("rule_id"),
                        framework=v.get("framework"),
                        rule_name=v.get("rule_name"),
                        severity=severity_map.get(v.get("severity"), Severity.MEDIUM),
                        message=v.get("message"),
                        remediation=v.get("remediation"),
                        action=action_map.get(v.get("action"), ComplianceAction.FLAG),
                    )
                )

        # Score risk
        scorer = RiskScorer()
        assessment = scorer.assess_overall_risk(
            pii_entities=entities,
            injection_score=injection_score,
            compliance_violations=violation_objects,
        )

        result = {
            "status": "success",
            "overall_score": assessment.overall_score,
            "overall_level": assessment.overall_level.value,
            "pii_score": assessment.pii_score,
            "injection_score": assessment.injection_score,
            "compliance_score": assessment.compliance_score,
            "critical_count": assessment.critical_count,
            "total_entities": assessment.total_entities,
            "top_risks": [
                {
                    "component": r.component,
                    "value": r.value,
                    "level": r.level.value,
                    "details": r.details,
                }
                for r in assessment.top_risks[:5]
            ],
            "recommendations": assessment.recommendations,
        }

        logger.info(f"[score_risk_async] Risk level: {assessment.overall_level.value}")
        return result

    except Exception as exc:
        logger.error(f"[score_risk_async] Error: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)


# ============================================================================
# COMPOSITE TASKS
# ============================================================================


@app.task(
    bind=True,
    name="workers.tasks.analyze_complete_async",
)
def analyze_complete_async(
    self,
    text: str,
    frameworks: Optional[List[str]] = None,
    webhook_url: Optional[str] = None,
    sign_payload: bool = False,
) -> Dict[str, Any]:
    """
    Async task: Complete analysis (PII detection + compliance + risk scoring).

    This is a composite task that chains multiple sub-tasks.

    Args:
        text: Text to analyze
        frameworks: Frameworks to check

    Returns:
        Dict with complete analysis results
    """
    try:
        logger.info("[analyze_complete_async] Starting complete analysis")

        # Step 1: Detect PII
        pii_result = detect_pii_async.delay(text).get(timeout=60)
        if pii_result["status"] != "success":
            return {"status": "error", "error": "PII detection failed"}

        entities = pii_result["entities"]

        # Step 2: Check compliance
        compliance_result = check_compliance_async.delay(text, entities, frameworks).get(timeout=60)
        if compliance_result["status"] != "success":
            return {"status": "error", "error": "Compliance check failed"}

        # Step 3: Score risk
        # Convert violations to dicts for JSON serialization
        violations = [
            {
                "rule_id": v["rule_id"],
                "framework": v["framework"],
                "rule_name": v["rule_name"],
                "severity": v["severity"],
                "action": v["action"],
                "message": v["message"],
            }
            for v in compliance_result["violations"]
        ]

        risk_result = score_risk_async.delay(entities, 0.0, violations).get(timeout=60)
        if risk_result["status"] != "success":
            return {"status": "error", "error": "Risk scoring failed"}

        # Combine results
        result = {
            "status": "success",
            "pii": {
                "detected": pii_result["entity_count"],
                "entities": entities[:10],  # Top 10 entities
            },
            "compliance": {
                "compliant": compliance_result["compliant"],
                "violations": compliance_result["violation_count"],
                "frameworks": compliance_result["frameworks_checked"],
            },
            "risk": {
                "overall_score": risk_result["overall_score"],
                "overall_level": risk_result["overall_level"],
                "recommendations": risk_result["recommendations"][:3],
            },
        }

        logger.info("[analyze_complete_async] Analysis complete")

        # Notify webhook destination if provided
        if webhook_url:
            try:
                # Import here to avoid module cycles
                from app import webhook_security
                from app.webhooks import WebhookEventType, WebhookPayload, get_webhook_notifier

                notifier = get_webhook_notifier()
                payload = WebhookPayload.build_task_event(
                    event_type=WebhookEventType.TASK_COMPLETED,
                    task_id=(
                        self.request.id
                        if hasattr(self, "request") and getattr(self.request, "id", None)
                        else ""
                    ),
                    task_name="analyze_complete_async",
                    status="SUCCESS",
                    result=result,
                )

                extra_headers = None
                if sign_payload:
                    secret = webhook_security.get_signing_secret()
                    if secret:
                        try:
                            extra_headers = webhook_security.sign_payload(payload, secret)
                        except Exception:
                            logger.exception(
                                "Failed to sign webhook payload in worker; sending unsigned"
                            )

                notifier.send_webhook(
                    webhook_url,
                    payload,
                    WebhookEventType.TASK_COMPLETED,
                    extra_headers=extra_headers,
                )
            except Exception:
                logger.exception("Failed to send webhook from worker")

        return result

    except Exception as exc:
        logger.error(f"[analyze_complete_async] Error: {exc}")

        # Attempt to notify failure to webhook destination if provided
        if "webhook_url" in locals() and webhook_url:
            try:
                from app.webhooks import WebhookEventType, WebhookPayload, get_webhook_notifier

                notifier = get_webhook_notifier()
                payload = WebhookPayload.build_task_event(
                    event_type=WebhookEventType.TASK_FAILED,
                    task_id=(
                        self.request.id
                        if hasattr(self, "request") and getattr(self.request, "id", None)
                        else ""
                    ),
                    task_name="analyze_complete_async",
                    status="FAILURE",
                    error=str(exc),
                )
                notifier.send_webhook(webhook_url, payload, WebhookEventType.TASK_FAILED)
            except Exception:
                logger.exception("Failed to send failure webhook from worker")

        return {"status": "error", "error": str(exc)}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_task_result(task_id: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Get result of a completed task.

    Args:
        task_id: Task ID from Celery
        timeout: Timeout in seconds

    Returns:
        Task result or error dict
    """
    try:
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=app)

        if result.state == "PENDING":
            return {"status": "pending", "task_id": task_id}
        elif result.state == "STARTED":
            return {"status": "started", "task_id": task_id}
        elif result.state == "SUCCESS":
            return {"status": "success", "result": result.result}
        elif result.state == "FAILURE":
            return {
                "status": "error",
                "error": str(result.info),
                "task_id": task_id,
            }
        else:
            return {"status": result.state, "task_id": task_id}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_task_status(task_id: str) -> str:
    """Get status of a task"""
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=app)
    return result.state


@app.task(name="workers.celery_app.sync_usage_to_stripe")
def sync_usage_to_stripe():
    """
    Periodic task: Sync token usage to Stripe.

    Aggregates usage from TokenUsage table and reports to Stripe.
    """
    from sqlalchemy import func

    from app.billing import billing_service
    from app.database import SessionLocal
    from app.models import Tenant, TokenUsage

    logger.info("[sync_usage_to_stripe] Starting usage sync")

    db = SessionLocal()
    try:
        # 1. Get all tenants with active Stripe subscriptions
        tenants = db.query(Tenant).filter(Tenant.stripe_subscription_id.isnot(None)).all()

        for tenant in tenants:
            try:
                # 2. Aggregate unreported usage for this tenant
                # We sum up total_tokens for all records where reported_to_stripe is False
                usage_stats = (
                    db.query(
                        func.sum(TokenUsage.total_tokens).label("total_tokens"),
                        func.count(TokenUsage.id).label("request_count"),
                    )
                    .filter(
                        TokenUsage.tenant_id == tenant.id,
                        TokenUsage.reported_to_stripe.is_(False),
                    )
                    .first()
                )

                total_tokens = usage_stats.total_tokens or 0

                if total_tokens > 0:
                    logger.info(f"Reporting {total_tokens} tokens for tenant {tenant.slug}")

                    import stripe

                    if billing_service.api_key:
                        subscription = stripe.Subscription.retrieve(tenant.stripe_subscription_id)
                        if subscription and subscription["items"]["data"]:
                            subscription_item_id = subscription["items"]["data"][0].id

                            success = billing_service.report_usage(
                                subscription_item_id, int(total_tokens)
                            )

                            if success:
                                # 4. Mark records as reported
                                db.query(TokenUsage).filter(
                                    TokenUsage.tenant_id == tenant.id,
                                    TokenUsage.reported_to_stripe.is_(False),
                                ).update({TokenUsage.reported_to_stripe: True})

                                db.commit()
                                logger.info(
                                    f"Successfully synced {total_tokens} tokens for {tenant.slug}"
                                )
                            else:
                                logger.error(f"Failed to report usage for {tenant.slug}")
                        else:
                            logger.error(f"No subscription items found for {tenant.slug}")
                    else:
                        logger.warning("Stripe API key not set, skipping report")

            except Exception as e:
                logger.error(f"Error processing tenant {tenant.slug}: {e}")
                db.rollback()

    except Exception as e:
        logger.error(f"[sync_usage_to_stripe] Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # Start worker: celery -A workers.celery worker -l info
    app.worker_main()
