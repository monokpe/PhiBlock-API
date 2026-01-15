import logging  # Standard library logging
import os
import time
import uuid

import sentry_sdk
from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from strawberry.fastapi import GraphQLRouter

from workers.detection import get_injection_score

from . import auth
from . import logging as local_logging  # Renaming local logging to avoid conflict
from . import models
from .analytics import router as analytics_router
from .async_endpoints import router as async_router
from .cache_service import cache_result, get_cached_result
from .compliance import get_compliance_engine, get_redaction_service, load_compliance_rules
from .compliance.models import ComplianceAction
from .database import get_db
from .detection import detect_pii
from .graphql.context import get_context
from .graphql.schema import schema
from .middleware import TenantContextMiddleware
from .performance_monitoring import router as performance_router
from .rate_limiting import RateLimiter
from .security import register_security
from .tenant_api import router as tenant_router

logger = logging.getLogger(__name__)  # Use standard logging for general purpose logging


class AnalyzeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class HealthCheckResponse(BaseModel):
    status: str
    version: str


rate_limiter = RateLimiter(requests_per_minute=100)

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title="PhiBlock API",
    description="API for real-time content filtering and compliance.",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for validation errors to provide better feedback for malformed JSON.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Invalid Request Format",
            "message": "The JSON payload is malformed. Use escaped quotes or single quotes.",
            "errors": exc.errors(),
        },
    )


app.add_middleware(TenantContextMiddleware)

register_security(app)

app.include_router(async_router)
app.include_router(tenant_router)

graphql_app = GraphQLRouter(schema, context_getter=get_context)  # type: ignore
app.include_router(graphql_app, prefix="/graphql")

app.include_router(analytics_router)

app.include_router(performance_router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")


@app.get("/v1/health", response_model=HealthCheckResponse, tags=["Monitoring"])
def health_check():
    """
    System health check.

    Returns the operational status of the API.
    """
    return {
        "status": "healthy",
        "version": app.version,
    }


@app.post("/v1/analyze", tags=["Analysis"], status_code=200)
async def analyze_prompt(
    req: Request,
    body: AnalyzeRequest,
    current_user: models.APIKey = Depends(auth.get_current_user),
    db=Depends(get_db),
    _rate_limit=Depends(rate_limiter),
):
    """
    Analyzes a prompt for PII, injection, and compliance violations.

    Results are cached for 5 minutes to avoid re-processing identical prompts.
    """
    start_time = time.time()
    request_id = uuid.uuid4()

    tenant_id = current_user.tenant_id
    if tenant_id:
        cached_result = get_cached_result(body.prompt, str(tenant_id))
        if cached_result:
            cached_result["request_id"] = request_id
            cached_result["cached"] = True
            return cached_result

    raw_entities = detect_pii(body.prompt)

    try:
        injection_score = get_injection_score(body.prompt)
    except Exception as e:
        logger.warning(f"Injection detection failed: {e}")
        injection_score = 0.0

    injection_detected = injection_score > 0.5

    # 1. Normalize and Aggregate Entities
    # detect_pii returns {"type": ..., "value": ..., "position": {"start": ..., "end": ...}}
    # compliance engine expects {"type": ..., "value": ..., "start": ..., "end": ...}
    normalized_entities = []
    for e in raw_entities:
        normalized_entities.append(
            {
                "type": e["type"],
                "value": e["value"],
                "start": e["position"]["start"],
                "end": e["position"]["end"],
            }
        )

    if injection_detected:
        normalized_entities.append(
            {
                "type": "PROMPT_INJECTION",
                "value": body.prompt,
                "start": 0,
                "end": len(body.prompt),
                "confidence": injection_score,
            }
        )

    # 2. Evaluate Compliance Rules
    rules = load_compliance_rules()
    engine = get_compliance_engine()
    engine.load_rules(rules)

    # We include our new "Security" framework by default here
    frameworks = ["Security", "GDPR", "HIPAA", "PCI-DSS"]
    compliance_result = engine.check_compliance(
        body.prompt, normalized_entities, frameworks=frameworks
    )

    # 3. Apply Redaction/Blocking based on Compliance Engine results
    redaction_service = get_redaction_service()

    # Identify if we have a BLOCK action
    should_block = any(v.action == ComplianceAction.BLOCK for v in compliance_result.violations)

    if should_block:
        # If blocked, we mask the entire prompt or return a specific message
        # The design for BLOCK usually means the request is rejected,
        # but for sanitized_prompt we can provide the filtered message
        blocking_violation = next(
            v for v in compliance_result.violations if v.action == ComplianceAction.BLOCK
        )
        sanitized_prompt = f"[FILTERED DUE TO {blocking_violation.rule_name.upper()}]"
    else:
        # Otherwise, redact specific entities marked for REDACT
        sanitized_prompt, _ = redaction_service.redact_text(body.prompt, normalized_entities)

    analysis_result = {
        "request_id": str(request_id),
        "status": "completed",
        "sanitized_prompt": sanitized_prompt,
        "detections": {
            "pii_found": len(raw_entities) > 0,
            "entities": raw_entities,
            "injection_detected": injection_detected,
            "injection_score": round(injection_score, 4),
        },
        "compliance": {
            "compliant": compliance_result.compliant,
            "violations": [
                {
                    "rule_name": v.rule_name,
                    "framework": v.framework,
                    "severity": v.severity,
                    "message": v.message,
                }
                for v in compliance_result.violations
            ],
        },
        "cached": False,
    }

    if tenant_id:
        cache_result(body.prompt, str(tenant_id), analysis_result)

    await local_logging.log_request(
        db=db,
        api_key=current_user,
        status_code=200,
        start_time=start_time,
        prompt=body.prompt,
        analysis_result=analysis_result,
        injection_score=injection_score,
        endpoint=req.url.path,
        http_method=req.method,
    )

    return analysis_result
