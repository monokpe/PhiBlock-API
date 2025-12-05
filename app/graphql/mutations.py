"""
GraphQL mutation resolvers.
"""

import logging
import time
import uuid
from typing import Optional

import strawberry
from sqlalchemy.orm import Session

from workers.detection import get_injection_score

from .. import cache_service, models
from ..detection import detect_pii
from .types import AnalysisResultType, DetectionResultType, TenantType

logger = logging.getLogger(__name__)


@strawberry.input
class TenantInput:
    name: str
    slug: Optional[str] = None
    plan: str = "basic"


@strawberry.input
class TenantUpdateInput:
    name: Optional[str] = None
    plan: Optional[str] = None


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_tenant(self, info, input: TenantInput) -> TenantType:
        """Create a new tenant."""
        db: Session = info.context["db"]

        slug = input.slug or input.name.lower().replace(" ", "-")

        existing = db.query(models.Tenant).filter(models.Tenant.slug == slug).first()
        if existing:
            raise Exception(f"Tenant with slug '{slug}' already exists.")

        tenant = models.Tenant(name=input.name, slug=slug, plan=input.plan)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    @strawberry.mutation
    def update_tenant(
        self, info, tenant_id: uuid.UUID, input: TenantUpdateInput
    ) -> Optional[TenantType]:
        """Update an existing tenant."""
        db: Session = info.context["db"]
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()

        if not tenant:
            return None

        if input.name:
            tenant.name = input.name
        if input.plan:
            tenant.plan = input.plan

        db.commit()
        db.refresh(tenant)
        return tenant

    @strawberry.mutation
    def delete_tenant(self, info, tenant_id: uuid.UUID) -> bool:
        """Delete a tenant."""
        db: Session = info.context["db"]
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()

        if not tenant:
            return False

        db.delete(tenant)
        db.commit()
        return True

    @strawberry.mutation
    async def analyze_prompt(self, info, prompt: str) -> AnalysisResultType:
        """Analyze a prompt for PII and injection."""
        db: Session = info.context["db"]
        current_user = info.context.get("current_user")
        tenant_id = info.context.get("tenant_id")

        if not current_user:
            raise Exception("Authentication required")

        start_time = time.time()
        request_id = uuid.uuid4()

        if tenant_id:
            cached_result = cache_service.get_cached_result(prompt, str(tenant_id))
            if cached_result:
                detections_data = cached_result["detections"]
                detections = DetectionResultType(
                    pii_found=detections_data["pii_found"],
                    entities=detections_data["entities"],
                    injection_detected=detections_data["injection_detected"],
                    injection_score=detections_data["injection_score"],
                )
                return AnalysisResultType(
                    request_id=request_id,
                    status="completed",
                    sanitized_prompt=cached_result["sanitized_prompt"],
                    detections=detections,
                    cached=True,
                )

        entities = detect_pii(prompt)
        pii_found = len(entities) > 0

        try:
            injection_score = get_injection_score(prompt)
        except Exception as e:
            logger.warning(f"Injection detection failed, falling back to score 0.0. Error: {e}")
            injection_score = 0.0

        injection_detected = injection_score > 0.5

        sanitized_prompt = prompt
        for entity in sorted(entities, key=lambda e: e["position"]["start"], reverse=True):
            start = entity["position"]["start"]
            end = entity["position"]["end"]
            sanitized_prompt = (
                sanitized_prompt[:start] + f"[{entity['type']}]" + sanitized_prompt[end:]
            )

        detections = DetectionResultType(
            pii_found=pii_found,
            entities=entities,
            injection_detected=injection_detected,
            injection_score=round(injection_score, 4),
        )

        result = AnalysisResultType(
            request_id=request_id,
            status="completed",
            sanitized_prompt=sanitized_prompt,
            detections=detections,
            cached=False,
        )

        if tenant_id:
            cache_data = {
                "request_id": str(request_id),
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
            cache_service.cache_result(prompt, str(tenant_id), cache_data)

        analysis_result_dict = {
            "request_id": request_id,
            "status": "completed",
            "sanitized_prompt": sanitized_prompt,
            "detections": {
                "pii_found": pii_found,
                "entities": entities,
                "injection_detected": injection_detected,
                "injection_score": round(injection_score, 4),
            },
        }

        await logging.log_request(
            db=db,
            api_key=current_user,
            status_code=200,
            start_time=start_time,
            prompt=prompt,
            analysis_result=analysis_result_dict,
            injection_score=injection_score,
            endpoint="/graphql",
            http_method="POST",
        )

        return result
