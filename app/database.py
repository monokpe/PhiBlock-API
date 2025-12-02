import os
from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import sessionmaker
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# Database URL from environment or default
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://user:password@db/guardrails_db"
)

# Connection pooling configuration for production performance
# Uses QueuePool for high-concurrency scenarios
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=pool.QueuePool,
    pool_size=20,  # Number of connections to keep in pool
    max_overflow=40,  # Additional connections beyond pool_size
    pool_pre_ping=True,  # Test connections before use
    pool_recycle=3600,  # Recycle connections every hour
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL if enabled
    connect_args={
        "connect_timeout": 5,
        "application_name": "guardrails_api",
    },
)


# Connection pool event listeners for optimization
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set PostgreSQL connection parameters for performance."""
    if "postgresql" in SQLALCHEMY_DATABASE_URL.lower():
        cursor = dbapi_conn.cursor()
        # Enable query optimization
        cursor.execute("SET statement_timeout = 30000")  # 30 second query timeout
        cursor.execute(
            "SET work_mem = '256MB'"
        )  # Increase working memory for complex queries
        cursor.close()


@event.listens_for(engine, "connect")
def log_pool_connect(dbapi_conn, connection_record):
    """Log pool connections for monitoring."""
    logger.debug("Database connection acquired from pool")


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Avoid unnecessary re-queries after commit
)


def get_db() -> Generator:
    """
    Dependency for FastAPI endpoints to get database session.
    Automatically returns after request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_sync() -> SessionLocal:
    """Synchronous database session for non-async contexts."""
    return SessionLocal()


def close_db_session(db) -> None:
    """Explicitly close database session."""
    if db:
        db.close()


def get_engine_info() -> dict:
    """Get connection pool statistics for monitoring."""
    pool_obj = engine.pool
    return {
        "pool_size": pool_obj.size() if hasattr(pool_obj, "size") else "N/A",
        "checked_out": (
            pool_obj.checkedout() if hasattr(pool_obj, "checkedout") else "N/A"
        ),
        "overflow": pool_obj.overflow() if hasattr(pool_obj, "overflow") else "N/A",
        "total": (
            pool_obj.size() + pool_obj.overflow()
            if hasattr(pool_obj, "size")
            else "N/A"
        ),
    }
