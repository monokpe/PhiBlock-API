import os
import time
import uuid

import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from strawberry.fastapi import GraphQLRouter

from . import auth, logging, models
from .analytics import router as analytics_router
from .async_endpoints import router as async_router
from .database import get_db
from .graphql.context import get_context
from .graphql.schema import schema
from .middleware import TenantContextMiddleware
from .performance_monitoring import router as performance_router
from .rate_limiting import RateLimiter
from .security import register_security
from .tenant_api import router as tenant_router


# A simple model for the request body of the analyze endpoint
class AnalyzeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


# A simple model for the health check response
class HealthCheckResponse(BaseModel):
    status: str
    version: str


# Initialize Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title="Guardrails API",
    description="API for real-time content filtering and compliance.",
    version="0.1.0",
)

# Add tenant context middleware
app.add_middleware(TenantContextMiddleware)

# Register security middleware (CORS + request signing)
register_security(app)

# Include routers
app.include_router(async_router)
app.include_router(tenant_router)

# GraphQL API
graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")

# Analytics API
app.include_router(analytics_router)

# Performance Monitoring API
app.include_router(performance_router)

# Static Files (Dashboard)
# Ensure static directory exists
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

    # Check cache first
    from .cache_service import cache_result, get_cached_result
    from .middleware import get_current_tenant

    tenant_id = get_current_tenant()
    if tenant_id:
        cached_result = get_cached_result(body.prompt, str(tenant_id))
        if cached_result:
            # Return cached result with new request_id
            cached_result["request_id"] = request_id
            cached_result["cached"] = True
            return cached_result

    from workers.detection import get_injection_score

    from .detection import detect_pii

    # Detect PII
    entities = detect_pii(body.prompt)
    pii_found = len(entities) > 0

    # Detect prompt injection
    try:
        injection_score = get_injection_score(body.prompt)
    except Exception as e:
        # Fallback to 0 if injection detection fails
        print(f"Warning: Injection detection failed: {e}")
        injection_score = 0.0

    injection_detected = injection_score > 0.5

    # Basic sanitization: replace detected PII with placeholders
    sanitized_prompt = body.prompt
    for entity in sorted(entities, key=lambda e: e["position"]["start"], reverse=True):
        start = entity["position"]["start"]
        end = entity["position"]["end"]
        sanitized_prompt = sanitized_prompt[:start] + f"[{entity['type']}]" + sanitized_prompt[end:]

    analysis_result = {
        "request_id": request_id,
        "status": "completed",
        "sanitized_prompt": sanitized_prompt,
        "detections": {
            "pii_found": pii_found,
            "entities": entities,
            "injection_detected": injection_detected,
            "injection_score": round(injection_score, 4),
        },
        "cached": False,
    }

    # Cache the result for future requests
    if tenant_id:
        cache_result(body.prompt, str(tenant_id), analysis_result)

    await logging.log_request(
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
