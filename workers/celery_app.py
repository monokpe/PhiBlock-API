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
from celery.signals import worker_process_init
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BROKER_URL = os.getenv("BROKER_URL", REDIS_URL)
RESULT_BACKEND = os.getenv("RESULT_BACKEND", REDIS_URL)

celery_app = Celery("phiblock")

celery_app.conf.update(
    broker_url=BROKER_URL,
    result_backend=RESULT_BACKEND,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_autoretry_for=(Exception,),
    task_max_retries=3,
    task_default_retry_delay=60,
    result_expires=3600,
    result_persistent=True,
    task_default_queue="default",
    task_queues=(
        Queue("detection", Exchange("detection"), routing_key="detection"),
        Queue("compliance", Exchange("compliance"), routing_key="compliance"),
        Queue("redaction", Exchange("redaction"), routing_key="redaction"),
        Queue("scoring", Exchange("scoring"), routing_key="scoring"),
        Queue("default", Exchange("default"), routing_key="default"),
    ),
    task_routes={
        "workers.tasks.detect_pii_async": {"queue": "detection"},
        "workers.tasks.check_compliance_async": {"queue": "compliance"},
        "workers.tasks.redact_async": {"queue": "redaction"},
        "workers.tasks.score_risk_async": {"queue": "scoring"},
        "workers.tasks.analyze_complete_async": {"queue": "default"},
        "workers.celery_app.sync_usage_to_stripe": {"queue": "default"},
    },
)

# Configure Periodic Tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "sync-usage-every-hour": {
        "task": "workers.celery_app.sync_usage_to_stripe",
        "schedule": crontab(minute=0),
    },
}


@worker_process_init.connect
def warm_up_models(**kwargs):
    """
    Warm up ML models at worker process initialization.
    This reduces cold-start latency for the first few analysis requests.
    """
    try:
        from app.detection import get_nlp
        from workers.detection import get_injection_score

        logger.info("[worker_process_init] Warming up ML models...")

        # Warm up spaCy
        get_nlp()

        # Warm up injection model with a dummy prompt
        try:
            get_injection_score("warmup")
        except Exception:
            # Injection model might fail in environments without GPU/Transformers
            logger.warning("[worker_process_init] Injection model warmup skipped or failed")

        logger.info("[worker_process_init] ML models warmed up successfully")
    except Exception as e:
        logger.error(f"[worker_process_init] Failed to warm up models: {e}")


@celery_app.task(
    bind=True,
    name="workers.tasks.detect_pii_async",
    max_retries=3,
    autoretry_for=(Exception,),
)
def detect_pii_async(self, text: str) -> Dict[str, Any]:
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
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@celery_app.task(
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
    try:
        from app.compliance import ComplianceEngine, load_compliance_rules

        logger.info(
            f"[check_compliance_async] Processing {len(text)} chars against "
            f"{frameworks or 'all'} frameworks"
        )

        rules = load_compliance_rules()

        engine = ComplianceEngine()
        engine.load_rules(rules)

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
                for v in result_obj.violations[:10]
            ],
        }

        logger.info(f"[check_compliance_async] Found {len(result_obj.violations)} violations")
        return result

    except Exception as exc:
        logger.error(f"[check_compliance_async] Error: {exc}")
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@celery_app.task(
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
    try:
        from app.compliance.redaction import RedactionService, RedactionStrategy

        logger.info(f"[redact_async] Redacting {len(entities)} entities using {strategy}")

        strategy_map = {
            "mask": RedactionStrategy.FULL_MASK,
            "token": RedactionStrategy.TOKEN_REPLACEMENT,
            "partial": RedactionStrategy.PARTIAL_MASK,
            "hash": RedactionStrategy.HASH_REPLACEMENT,
        }

        redaction_strategy = strategy_map.get(strategy, RedactionStrategy.TOKEN_REPLACEMENT)

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


@celery_app.task(
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
    try:
        from app.compliance import RiskScorer
        from app.compliance.models import ComplianceAction, ComplianceViolation, Severity

        logger.info(f"[score_risk_async] Scoring {len(entities)} entities")

        violation_objects = []
        if violations:
            severity_map = {s.name: s for s in Severity}
            action_map = {a.name: a for a in ComplianceAction}

            for v in violations:
                violation_objects.append(
                    ComplianceViolation(
                        rule_id=str(v.get("rule_id", "")),
                        framework=str(v.get("framework", "")),
                        rule_name=str(v.get("rule_name", "")),
                        severity=severity_map.get(str(v.get("severity")), Severity.MEDIUM),
                        message=str(v.get("message", "")),
                        remediation=str(v.get("remediation", "")),
                        action=action_map.get(str(v.get("action")), ComplianceAction.FLAG),
                    )
                )

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


@celery_app.task(
    bind=True,
    name="workers.tasks.analyze_complete_async",
)
def analyze_complete_async(
    self,
    text: str,
    frameworks: Optional[List[str]] = None,
    webhook_url: Optional[str] = None,
    sign_payload: bool = False,
    tenant_id: Optional[str] = None,
    api_key_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        logger.info(f"[analyze_complete_async] Starting complete analysis (tenant={tenant_id})")

        # 1. Detect PII
        from app.detection import detect_pii

        entities = detect_pii(text)

        # 2. Check Compliance
        from app.compliance import ComplianceEngine, load_compliance_rules

        rules = load_compliance_rules()
        engine = ComplianceEngine()
        engine.load_rules(rules)
        comp_obj = engine.check_compliance(text, entities, frameworks=frameworks)

        violations = [
            {
                "rule_id": v.rule_id,
                "framework": v.framework,
                "rule_name": v.rule_name,
                "severity": v.severity.name,
                "action": v.action.name,
                "message": v.message,
            }
            for v in comp_obj.violations
        ]

        # 3. Score Risk
        from app.compliance import RiskScorer
        from app.compliance.models import ComplianceAction, ComplianceViolation, Severity

        severity_map = {s.name: s for s in Severity}
        action_map = {a.name: a for a in ComplianceAction}

        violation_objects = [
            ComplianceViolation(
                rule_id=str(v["rule_id"]),
                framework=str(v["framework"]),
                rule_name=str(v["rule_name"]),
                severity=severity_map.get(str(v["severity"]), Severity.MEDIUM),
                message=str(v["message"]),
                remediation="",
                action=action_map.get(str(v["action"]), ComplianceAction.FLAG),
            )
            for v in violations
        ]

        scorer = RiskScorer()
        assessment = scorer.assess_overall_risk(
            pii_entities=entities,
            injection_score=0.0,
            compliance_violations=violation_objects,
        )

        result = {
            "status": "success",
            "pii": {
                "detected": len(entities),
                "entities": entities[:10],
            },
            "compliance": {
                "compliant": comp_obj.compliant,
                "violations": len(comp_obj.violations),
                "frameworks": comp_obj.frameworks_checked,
            },
            "risk": {
                "overall_score": assessment.overall_score,
                "overall_level": assessment.overall_level.value,
                "recommendations": assessment.recommendations[:3],
            },
        }

        logger.info("[analyze_complete_async] Analysis complete")

        # 4. Log token usage
        if tenant_id and api_key_id:
            try:
                from app.database import SessionLocal
                from app.token_tracking import get_token_logger

                with SessionLocal() as db:
                    token_logger = get_token_logger(db)
                    token_logger.log_token_usage(
                        api_key_id=api_key_id,
                        tenant_id=tenant_id,
                        endpoint="/v1/analyze/async",
                        input_text=text,
                        output_text=None,  # In async we don't necessarily have output
                        request_id=self.request.id if hasattr(self, "request") else None,
                        metadata={"type": "async_complete"},
                    )
                    db.commit()
            except Exception as e:
                logger.error(f"[analyze_complete_async] Failed to log usage: {e}")

        if webhook_url:
            try:
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


def get_task_result(task_id: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=celery_app)

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
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    return str(result.state)


@celery_app.task(name="workers.celery_app.sync_usage_to_stripe")
def sync_usage_to_stripe():
    from sqlalchemy import func

    from app.billing import billing_service
    from app.database import SessionLocal
    from app.models import Tenant, TokenUsage

    logger.info("[sync_usage_to_stripe] Starting usage sync")

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.stripe_subscription_id.isnot(None)).all()

        for tenant in tenants:
            try:
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

                if usage_stats and usage_stats.total_tokens:
                    total_tokens = usage_stats.total_tokens
                else:
                    total_tokens = 0

                if total_tokens > 0:
                    logger.info(f"Reporting {total_tokens} tokens for tenant {tenant.slug}")

                    import stripe

                    if billing_service.api_key:
                        if tenant.stripe_subscription_id:
                            subscription = stripe.Subscription.retrieve(
                                str(tenant.stripe_subscription_id)
                            )
                            if subscription and subscription["items"]["data"]:
                                subscription_item_id = subscription["items"]["data"][0].id

                                success = billing_service.report_usage(
                                    subscription_item_id, int(total_tokens)
                                )

                                if success:
                                    db.query(TokenUsage).filter(
                                        TokenUsage.tenant_id == tenant.id,
                                        TokenUsage.reported_to_stripe.is_(False),
                                    ).update({TokenUsage.reported_to_stripe: True})
                                    db.commit()

                                    logger.info(
                                        f"Successfully synced {total_tokens} tokens for "
                                        f"{tenant.slug}"
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
    # Start worker: celery -A workers.celery_app worker -l info
    celery_app.worker_main()
