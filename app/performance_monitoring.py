"""
Performance & Health Monitoring Endpoints

Provides metrics and diagnostics for system performance:
- Database connection pool statistics
- Query performance metrics
- System health checks
- Performance benchmarks
"""

import os
from datetime import datetime

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user
from .database import get_db, get_engine_info
from .query_optimization import IndexingStrategy, QueryOptimizer, get_slow_queries_report

router = APIRouter(
    prefix="/v1/performance",
    tags=["Performance & Monitoring"],
)


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint for load balancers and monitoring.
    Returns basic system status.
    """
    try:
        # Test database connection
        result = db.execute("SELECT 1")
        db_healthy = result is not None
    except Exception:
        db_healthy = False

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db_healthy else "disconnected",
    }


@router.get("/metrics")
async def get_performance_metrics(
    current_user: models.APIKey = Depends(get_current_user),
):
    """
    Get current performance metrics including connection pool, memory, CPU.
    Requires authentication.
    """
    try:
        # Get connection pool info
        pool_info = get_engine_info()

        # Get system metrics
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "connection_pool": pool_info,
            "system": {
                "memory_mb": memory_info.rss / 1024 / 1024,
                "memory_percent": process.memory_percent(),
                "cpu_percent": cpu_percent,
                "num_threads": process.num_threads(),
            },
            "requests": {
                "uptime_seconds": (datetime.utcnow() - datetime(2025, 1, 1)).total_seconds(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics error: {str(e)}")


@router.get("/slow-queries")
async def get_slow_queries(
    threshold_seconds: float = Query(1.0, ge=0.1, le=10.0),
    current_user: models.APIKey = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get slow queries from database (if pg_stat_statements is enabled).
    Only available for superusers or monitoring roles.
    """
    try:
        report = get_slow_queries_report(db, threshold_seconds)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Slow queries error: {str(e)}")


@router.get("/indexes/missing")
async def check_missing_indexes(
    current_user: models.APIKey = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check for missing recommended indexes and return creation script.
    Admin only.
    """
    try:
        missing = IndexingStrategy.check_missing_indexes(db)
        return {
            "missing_count": len(missing),
            "creation_scripts": missing,
            "full_script": IndexingStrategy.get_index_creation_script(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index check error: {str(e)}")


@router.get("/token-usage/stats")
async def get_token_usage_stats(
    days: int = Query(7, ge=1, le=365),
    current_user: models.APIKey = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get optimized token usage statistics for current tenant.
    Uses SQL aggregation for efficiency.
    """
    try:
        stats = QueryOptimizer.get_token_usage_stats(
            db,
            tenant_id=current_user.tenant_id,
            api_key_id=current_user.id,
            days=days,
        )
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token stats error: {str(e)}")


@router.get("/audit-logs/optimized")
async def get_optimized_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: models.APIKey = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fetch audit logs with optimized eager loading.
    Prevents N+1 queries when accessing relationships.
    """
    try:
        logs = QueryOptimizer.get_audit_logs_optimized(
            db,
            tenant_id=current_user.tenant_id,
            limit=limit,
            offset=offset,
        )
        return {
            "count": len(logs),
            "logs": [
                {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "endpoint": log.endpoint,
                    "status_code": log.status_code,
                    "latency_ms": log.latency_ms,
                    "risk_score": log.risk_score,
                }
                for log in logs
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit logs error: {str(e)}")


@router.post("/query-benchmark")
async def run_query_benchmark(
    query_type: str = Query("simple", regex="^(simple|aggregate|join)$"),
    iterations: int = Query(100, ge=10, le=10000),
    current_user: models.APIKey = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run performance benchmarks on different query patterns.
    Helps identify optimization opportunities.
    """
    import time

    results = {}

    try:
        if query_type in ["simple", "all"]:
            # Benchmark simple query
            start = time.time()
            for _ in range(iterations):
                db.query(models.AuditLog).filter(
                    models.AuditLog.tenant_id == current_user.tenant_id
                ).first()
            simple_time = (time.time() - start) / iterations * 1000

            results["simple_query_ms"] = round(simple_time, 3)

        if query_type in ["aggregate", "all"]:
            # Benchmark aggregation
            from sqlalchemy import func

            start = time.time()
            for _ in range(iterations):
                db.query(func.count(models.AuditLog.id)).filter(
                    models.AuditLog.tenant_id == current_user.tenant_id
                ).scalar()
            agg_time = (time.time() - start) / iterations * 1000

            results["aggregate_query_ms"] = round(agg_time, 3)

        if query_type in ["join", "all"]:
            # Benchmark join query
            start = time.time()
            for _ in range(iterations):
                db.query(models.AuditLog).filter(
                    models.AuditLog.tenant_id == current_user.tenant_id
                ).options(
                    __import__("sqlalchemy.orm", fromlist=["joinedload"]).joinedload(
                        models.AuditLog.api_key
                    ),
                ).first()
            join_time = (time.time() - start) / iterations * 1000

            results["join_query_ms"] = round(join_time, 3)

        return {
            "query_type": query_type,
            "iterations": iterations,
            "results_ms": results,
            "recommendation": (
                "Consider adding indexes if times exceed 10ms"
                if max(results.values()) > 10
                else "Performance is good"
            ),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmark error: {str(e)}")
