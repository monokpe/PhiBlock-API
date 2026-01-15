"""
Analytics API endpoints.
"""

from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user
from .database import get_db
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

    logs_query = db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tenant_id, models.AuditLog.timestamp >= start_date
    )

    usage_query = db.query(models.TokenUsage).filter(
        models.TokenUsage.tenant_id == tenant_id, models.TokenUsage.timestamp >= start_date
    )

    total_requests = logs_query.count()

    token_stats = usage_query.with_entities(
        func.sum(models.TokenUsage.total_tokens).label("total_tokens"),
        func.sum(models.TokenUsage.estimated_cost_usd).label("total_cost"),
    ).first()

    total_tokens = getattr(token_stats, "total_tokens", 0) or 0
    estimated_cost = float(getattr(token_stats, "total_cost", 0.0) or 0.0)

    injection_count = logs_query.filter(models.AuditLog.injection_score > 0.5).count()

    pii_count = logs_query.filter(models.AuditLog.entities_detected.isnot(None)).all()
    # Filter non-empty lists in Python to avoid SQL JSON comparison issues across dialects
    pii_count = len(
        [log for log in pii_count if log.entities_detected and len(log.entities_detected) > 0]
    )

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

    data_map = {}

    for log in logs:
        date_key = log.timestamp.date()
        if date_key not in data_map:
            data_map[date_key] = {"requests": 0, "violations": 0, "total_latency": 0, "count": 0}

        data_map[date_key]["requests"] += 1
        data_map[date_key]["total_latency"] += log.latency_ms
        data_map[date_key]["count"] += 1

        is_violation = False
        if log.injection_score and log.injection_score > 0.5:
            is_violation = True
        elif log.entities_detected and log.entities_detected != []:
            is_violation = True

        if is_violation:
            data_map[date_key]["violations"] += 1

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

    pii_counts: Dict[str, int] = {}
    injection_counts = {"Prompt Injection": 0}

    for log in logs:
        if log.entities_detected:
            entities = log.entities_detected
            if isinstance(entities, list):
                for entity in entities:
                    etype = entity.get("type", "UNKNOWN")
                    pii_counts[etype] = pii_counts.get(etype, 0) + 1

        if log.injection_score and log.injection_score > 0.5:
            injection_counts["Prompt Injection"] += 1

    pii_types = [ViolationType(type=k, count=v) for k, v in pii_counts.items()]

    injection_types = [ViolationType(type=k, count=v) for k, v in injection_counts.items() if v > 0]

    return ViolationsBreakdownResponse(pii_types=pii_types, injection_types=injection_types)
