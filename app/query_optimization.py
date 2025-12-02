"""
Query Optimization Utilities

Provides helpers for efficient database queries:
- Eager loading to prevent N+1 queries
- Query result caching
- Batch operations
- Index hints and optimization strategies
"""

import logging
from typing import List, Type, Optional, Any, Dict
from datetime import datetime, timedelta
from functools import wraps
import time

from sqlalchemy import and_, or_, desc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.sql import text

from . import models

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Centralized query optimization helper."""

    @staticmethod
    def get_audit_logs_optimized(
        db: Session,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[models.AuditLog]:
        """
        Fetch audit logs with eager loading to prevent N+1 queries.

        Uses:
        - joinedload for api_key relationship
        - date range filtering for performance
        - Limit and offset for pagination
        """
        query = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.tenant_id == tenant_id)
            .options(
                joinedload(models.AuditLog.api_key),
                joinedload(models.AuditLog.tenant),
            )
        )

        # Optional date range filtering
        if start_date:
            query = query.filter(models.AuditLog.timestamp >= start_date)
        if end_date:
            query = query.filter(models.AuditLog.timestamp <= end_date)

        return (
            query.order_by(desc(models.AuditLog.timestamp))
            .limit(limit)
            .offset(offset)
            .all()
        )

    @staticmethod
    def get_customers_with_keys(
        db: Session,
        tenant_id: str,
    ) -> List[models.Customer]:
        """
        Fetch customers and their API keys with eager loading.
        Prevents N+1 queries when accessing customer.api_keys.
        """
        return (
            db.query(models.Customer)
            .filter(models.Customer.tenant_id == tenant_id)
            .options(selectinload(models.Customer.api_keys))
            .all()
        )

    @staticmethod
    def get_api_keys_optimized(
        db: Session,
        tenant_id: str,
        customer_id: Optional[str] = None,
    ) -> List[models.APIKey]:
        """
        Fetch API keys with relationships eager-loaded.
        """
        query = db.query(models.APIKey).filter(models.APIKey.tenant_id == tenant_id)

        if customer_id:
            query = query.filter(models.APIKey.customer_id == customer_id)

        return query.options(
            joinedload(models.APIKey.customer),
            joinedload(models.APIKey.tenant),
        ).all()

    @staticmethod
    def get_token_usage_stats(
        db: Session,
        tenant_id: str,
        api_key_id: Optional[str] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Get aggregated token usage statistics using SQL aggregation.
        More efficient than fetching all rows and aggregating in Python.
        """
        from sqlalchemy import func

        query = (
            db.query(
                func.sum(models.TokenUsage.input_tokens).label("total_input"),
                func.sum(models.TokenUsage.output_tokens).label("total_output"),
                func.count(models.TokenUsage.id).label("request_count"),
                func.avg(
                    models.TokenUsage.input_tokens + models.TokenUsage.output_tokens
                ).label("avg_tokens"),
            )
            .filter(models.TokenUsage.tenant_id == tenant_id)
            .filter(
                models.TokenUsage.timestamp >= datetime.utcnow() - timedelta(days=days)
            )
        )

        if api_key_id:
            query = query.filter(models.TokenUsage.api_key_id == api_key_id)

        result = query.first()

        return {
            "total_input_tokens": result[0] or 0,
            "total_output_tokens": result[1] or 0,
            "request_count": result[2] or 0,
            "avg_tokens_per_request": result[3] or 0,
            "period_days": days,
        }

    @staticmethod
    def batch_insert(
        db: Session, models_list: List[Any], batch_size: int = 1000
    ) -> None:
        """
        Insert multiple records efficiently using batch operations.
        """
        for i in range(0, len(models_list), batch_size):
            batch = models_list[i : i + batch_size]
            db.add_all(batch)
            db.commit()
        logger.info(f"Batch inserted {len(models_list)} records")

    @staticmethod
    def batch_delete(
        db: Session,
        model_class: Type[Any],
        filter_criteria: Dict[str, Any],
        batch_size: int = 1000,
    ) -> int:
        """
        Delete records matching criteria using batch operations.
        """
        total_deleted = 0
        while True:
            batch = (
                db.query(model_class)
                .filter_by(**filter_criteria)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            for record in batch:
                db.delete(record)
            db.commit()
            total_deleted += len(batch)
        logger.info(f"Batch deleted {total_deleted} records")
        return total_deleted


def query_performance_monitor(func):
    """
    Decorator to monitor query performance and log slow queries.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time

            if elapsed > 1.0:  # Log if query takes >1 second
                logger.warning(
                    f"Slow query: {func.__name__} took {elapsed:.2f}s",
                )
            else:
                logger.debug(f"Query {func.__name__} took {elapsed:.3f}s")

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Query failed: {func.__name__} after {elapsed:.2f}s: {e}")
            raise

    return wrapper


class IndexingStrategy:
    """
    Documentation and recommendations for database indexing.
    """

    # Recommended indexes for performance
    RECOMMENDED_INDEXES = [
        # Tenant isolation and filtering
        "CREATE INDEX idx_customer_tenant_id ON customers(tenant_id);",
        "CREATE INDEX idx_api_key_tenant_id ON api_keys(tenant_id);",
        "CREATE INDEX idx_audit_log_tenant_id ON audit_logs(tenant_id);",
        "CREATE INDEX idx_token_usage_tenant_id ON token_usage(tenant_id);",
        # Lookup by ID
        "CREATE INDEX idx_audit_log_api_key_id ON audit_logs(api_key_id);",
        "CREATE INDEX idx_token_usage_api_key_id ON token_usage(api_key_id);",
        # Time-series queries
        "CREATE INDEX idx_audit_log_timestamp ON audit_logs(timestamp DESC);",
        "CREATE INDEX idx_token_usage_timestamp ON token_usage(timestamp DESC);",
        # Composite indexes for common queries
        "CREATE INDEX idx_audit_log_tenant_timestamp ON audit_logs(tenant_id, timestamp DESC);",
        "CREATE INDEX idx_token_usage_tenant_timestamp ON token_usage(tenant_id, timestamp DESC);",
        # Unique constraints for lookups
        "CREATE UNIQUE INDEX idx_api_key_hash ON api_keys(key_hash);",
        "CREATE UNIQUE INDEX idx_tenant_slug ON tenants(slug);",
    ]

    @staticmethod
    def get_index_creation_script() -> str:
        """Get SQL script to create recommended indexes."""
        return "\n".join(IndexingStrategy.RECOMMENDED_INDEXES)

    @staticmethod
    def check_missing_indexes(db: Session) -> List[str]:
        """
        Check which recommended indexes are missing.
        Run this periodically to ensure optimal performance.
        """
        missing = []
        for index_sql in IndexingStrategy.RECOMMENDED_INDEXES:
            index_name = index_sql.split(" ")[2]  # Extract index name
            try:
                result = db.execute(
                    text(
                        f"""
                    SELECT 1 FROM information_schema.statistics
                    WHERE table_schema = 'public' AND index_name = '{index_name}'
                    """
                    )
                ).first()
                if not result:
                    missing.append(index_sql)
            except Exception as e:
                logger.warning(f"Could not check index {index_name}: {e}")

        return missing


# Example: Query performance monitoring endpoint helper
def get_slow_queries_report(
    db: Session, threshold_seconds: float = 1.0
) -> Dict[str, Any]:
    """
    Get a report of slow queries from pg_stat_statements (PostgreSQL).
    Requires pg_stat_statements extension enabled.
    """
    try:
        result = db.execute(
            text(
                f"""
            SELECT
                query,
                calls,
                total_time,
                mean_time,
                max_time
            FROM pg_stat_statements
            WHERE mean_time > {threshold_seconds * 1000}
            ORDER BY mean_time DESC
            LIMIT 20
            """
            )
        ).fetchall()

        return {
            "slow_queries": [
                {
                    "query": row[0],
                    "calls": row[1],
                    "total_time_ms": row[2],
                    "mean_time_ms": row[3],
                    "max_time_ms": row[4],
                }
                for row in result
            ]
        }
    except Exception as e:
        logger.error(f"Could not fetch slow queries report: {e}")
        return {"error": str(e)}
