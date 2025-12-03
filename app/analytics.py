"""
Analytics API endpoints.
"""

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user
from .database import get_db
from .middleware import get_current_tenant
from .schemas.analytics import (
    AnalyticsStatsResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
    ViolationsBreakdownResponse,
    ViolationType,
)

router = APIRouter(
    prefix="/v1/analytics", tags=["Analytics"], dependencies=[Depends(get_current_user)]
)


def get_date_range(range_str: str):
    """Calculate start date based on range string."""
    now = datetime.utcnow()
    if range_str == "24h":
        return now - timedelta(days=1)
    elif range_str == "7d":
        return now - timedelta(days=7)
    elif range_str == "30d":
        return now - timedelta(days=30)
    else:
        return now - timedelta(days=7)  # Default


@router.get("/stats", response_model=AnalyticsStatsResponse)
def get_analytics_stats(
    range: str = Query("7d", regex="^(24h|7d|30d)$"),
    db: Session = Depends(get_db),
    current_user: models.APIKey = Depends(get_current_user),
):
    """Get summary statistics for the selected time range."""
    start_date = get_date_range(range)
    tenant_id = current_user.tenant_id

    # Base query for audit logs
    logs_query = db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tenant_id, models.AuditLog.timestamp >= start_date
    )

    # Base query for token usage
    usage_query = db.query(models.TokenUsage).filter(
        models.TokenUsage.tenant_id == tenant_id, models.TokenUsage.timestamp >= start_date
    )

    # Aggregations
    total_requests = logs_query.count()

    token_stats = usage_query.with_entities(
        func.sum(models.TokenUsage.total_tokens).label("total_tokens"),
        func.sum(models.TokenUsage.estimated_cost_usd).label("total_cost"),
    ).first()

    total_tokens = token_stats.total_tokens or 0
    estimated_cost = float(token_stats.total_cost or 0.0)

    # Security stats
    # Injection > 0.5
    injection_count = logs_query.filter(models.AuditLog.injection_score > 0.5).count()

    # PII detected
    pii_count = logs_query.filter(
        models.AuditLog.entities_detected.isnot(None), models.AuditLog.entities_detected != "[]"
    ).count()

    # Avg latency
    avg_latency = logs_query.with_entities(func.avg(models.AuditLog.latency_ms)).scalar() or 0.0

    return AnalyticsStatsResponse(
        total_requests=total_requests,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        injection_attacks_blocked=injection_count,
        pii_detected_count=pii_count,
        avg_latency_ms=avg_latency,
    )


@router.get("/timeseries", response_model=TimeSeriesResponse)
def get_analytics_timeseries(
    range: str = Query("7d", regex="^(24h|7d|30d)$"),
    db: Session = Depends(get_db),
    current_user: models.APIKey = Depends(get_current_user),
):
    """Get time-series data for charts."""
    start_date = get_date_range(range)
    tenant_id = current_user.tenant_id

    logs = (
        db.query(
            models.AuditLog.timestamp,
            models.AuditLog.latency_ms,
            models.AuditLog.injection_score,
            models.AuditLog.entities_detected,
        )
        .filter(models.AuditLog.tenant_id == tenant_id, models.AuditLog.timestamp >= start_date)
        .order_by(models.AuditLog.timestamp)
        .all()
    )

    # Aggregate in Python
    data_map = {}

    for log in logs:
        date_key = log.timestamp.date()
        if date_key not in data_map:
            data_map[date_key] = {"requests": 0, "violations": 0, "total_latency": 0, "count": 0}

        data_map[date_key]["requests"] += 1
        data_map[date_key]["total_latency"] += log.latency_ms
        data_map[date_key]["count"] += 1

        # Check violations
        is_violation = False
        if log.injection_score and log.injection_score > 0.5:
            is_violation = True
        elif log.entities_detected and log.entities_detected != []:
            is_violation = True

        if is_violation:
            data_map[date_key]["violations"] += 1

    # Convert to list
    result_data = []
    sorted_dates = sorted(data_map.keys())

    for d in sorted_dates:
        stats = data_map[d]
        result_data.append(
            TimeSeriesPoint(
                date=d,
                requests=stats["requests"],
                violations=stats["violations"],
                latency_ms=stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0,
            )
        )

    return TimeSeriesResponse(data=result_data)


@router.get("/violations", response_model=ViolationsBreakdownResponse)
def get_violations_breakdown(
    range: str = Query("7d", regex="^(24h|7d|30d)$"),
    db: Session = Depends(get_db),
    current_user: models.APIKey = Depends(get_current_user),
):
    """Get breakdown of violations."""
    start_date = get_date_range(range)
    tenant_id = current_user.tenant_id

    logs = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.tenant_id == tenant_id, models.AuditLog.timestamp >= start_date)
        .all()
    )

    pii_counts = {}
    injection_counts = {"Prompt Injection": 0}

    for log in logs:
        # PII
        if log.entities_detected:
            # entities_detected is a list of dicts: [{'type': 'EMAIL', ...}]
            # If it's stored as JSON/dict in model, SQLAlchemy handles it
            entities = log.entities_detected
            if isinstance(entities, str):
                try:
                    entities = json.loads(entities)
                except:
                    entities = []

            if isinstance(entities, list):
                for entity in entities:
                    etype = entity.get("type", "UNKNOWN")
                    pii_counts[etype] = pii_counts.get(etype, 0) + 1

        # Injection
        if log.injection_score and log.injection_score > 0.5:
            injection_counts["Prompt Injection"] += 1

    pii_types = [ViolationType(type=k, count=v) for k, v in pii_counts.items()]

    injection_types = [ViolationType(type=k, count=v) for k, v in injection_counts.items() if v > 0]

    return ViolationsBreakdownResponse(pii_types=pii_types, injection_types=injection_types)
