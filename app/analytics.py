"""
Analytics API endpoints.
"""

from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
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
    """Get time-series data for charts using efficient SQL aggregation."""
    start_date = get_date_range(range)
    tenant_id = current_user.tenant_id

    # Group by date and calculate aggregates in SQL
    aggregated_data = (
        db.query(
            func.date(models.AuditLog.timestamp).label("date"),
            func.count(models.AuditLog.id).label("requests"),
            func.avg(models.AuditLog.latency_ms).label("avg_latency"),
            # Count violations: injection > 0.5 or entities_detected is not null/empty
            # Note: JSON logic can be tricky across dialects, so we use a simplified count
            func.sum(
                case(
                    (models.AuditLog.injection_score > 0.5, 1),
                    (models.AuditLog.entities_detected.isnot(None), 1),
                    else_=0,
                )
            ).label("violations"),
        )
        .filter(models.AuditLog.tenant_id == tenant_id, models.AuditLog.timestamp >= start_date)
        .group_by(func.date(models.AuditLog.timestamp))
        .order_by("date")
        .all()
    )

    result_data = [
        TimeSeriesPoint(
            date=row.date
            if isinstance(row.date, datetime)
            else datetime.strptime(row.date, "%Y-%m-%d").date(),
            requests=row.requests,
            violations=int(row.violations or 0),
            latency_ms=float(row.avg_latency or 0.0),
        )
        for row in aggregated_data
    ]

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
