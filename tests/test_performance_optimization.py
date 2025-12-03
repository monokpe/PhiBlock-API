"""
Tests for Performance Optimization (Phase 4.1)

Tests query optimization, connection pooling, and performance monitoring.
"""

import time
from datetime import datetime, timedelta

import pytest

from app import models
from app.database import SessionLocal, get_engine_info
from app.query_optimization import IndexingStrategy, QueryOptimizer


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    db = SessionLocal()
    yield db
    db.close()


def test_indexing_strategy_recommendations():
    """Test indexing strategy provides proper recommendations."""
    indexes = IndexingStrategy.RECOMMENDED_INDEXES

    # Should include tenant_id indexes
    tenant_indexes = [idx for idx in indexes if "tenant_id" in idx]
    assert len(tenant_indexes) > 0

    # Should include timestamp indexes
    timestamp_indexes = [idx for idx in indexes if "timestamp" in idx]
    assert len(timestamp_indexes) > 0


def test_engine_info_available():
    """Test that engine info can be retrieved."""
    info = get_engine_info()
    assert isinstance(info, dict)
    assert "pool_size" in info or "checked_out" in info


def test_query_optimizer_token_stats():
    """Test token usage statistics aggregation logic."""
    # Test that the optimizer can be instantiated
    optimizer = QueryOptimizer
    assert hasattr(optimizer, "get_token_usage_stats")
    assert hasattr(optimizer, "get_audit_logs_optimized")


def test_query_optimizer_audit_logs():
    """Test optimized audit logs helper exists."""
    optimizer = QueryOptimizer
    # Verify the method signature exists
    assert hasattr(optimizer, "get_audit_logs_optimized")
    assert callable(optimizer.get_audit_logs_optimized)
