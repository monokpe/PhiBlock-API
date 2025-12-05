"""
GraphQL type definitions for Guardrails API.
"""

import datetime
import uuid
from typing import List, Optional

import strawberry
from strawberry.scalars import JSON


@strawberry.type
class TenantType:
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


@strawberry.type
class CustomerType:
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: str
    created_at: datetime.datetime


@strawberry.type
class APIKeyType:
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    key_hash: str
    name: Optional[str]
    tier: str
    rate_limit: int
    created_at: datetime.datetime
    last_used_at: Optional[datetime.datetime]
    revoked_at: Optional[datetime.datetime]


@strawberry.type
class AuditLogType:
    id: int
    tenant_id: uuid.UUID
    request_id: uuid.UUID
    api_key_id: uuid.UUID
    timestamp: datetime.datetime
    endpoint: str
    http_method: str
    status_code: int
    latency_ms: int
    prompt_hash: Optional[str]
    prompt_length: Optional[int]
    compliance_context: Optional[JSON]
    entities_detected: Optional[JSON]
    injection_score: Optional[float]
    compliance_status: Optional[str]
    violations: Optional[JSON]
    risk_score: Optional[float]
    tokens_analyzed: Optional[int]
    tokens_billable: Optional[int]


@strawberry.type
class EntityPositionType:
    start: int
    end: int


@strawberry.type
class EntityType:
    type: str
    text: str
    position: EntityPositionType
    score: float


@strawberry.type
class DetectionResultType:
    pii_found: bool
    entities: List[EntityType]
    injection_detected: bool
    injection_score: float


@strawberry.type
class AnalysisResultType:
    request_id: uuid.UUID
    status: str
    sanitized_prompt: str
    detections: DetectionResultType
    cached: bool
