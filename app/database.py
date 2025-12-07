import logging
import os
from typing import Any, Generator, cast

from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db/guardrails_db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=pool.QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    connect_args={
        "connect_timeout": 5,
        "application_name": "guardrails_api",
    },
)


# Connection pool event listeners for optimization
@event.listens_for(engine, "connect")
def set_postgresql_connection_parameters(dbapi_conn, connection_record):
    if "postgresql" in SQLALCHEMY_DATABASE_URL.lower():
        cursor = dbapi_conn.cursor()
        cursor.execute("SET statement_timeout = 30000")
        cursor.execute("SET work_mem = '256MB'")
        cursor.close()


@event.listens_for(engine, "connect")
def log_pool_connect(dbapi_conn, connection_record):
    logger.debug("Database connection acquired from pool")


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
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


def get_db_sync() -> Session:
    return SessionLocal()


def close_db_session(db) -> None:
    if db:
        db.close()


def get_engine_info() -> dict:
    pool_obj = engine.pool
    # Cast to Any to avoid mypy error about missing 'overflow' method on base Pool class
    # We use hasattr checks at runtime for safety
    pool_any = cast(Any, pool_obj)
    return {
        "pool_size": pool_obj.size() if hasattr(pool_obj, "size") else "N/A",
        "checked_out": (pool_obj.checkedout() if hasattr(pool_obj, "checkedout") else "N/A"),
        "overflow": pool_any.overflow() if hasattr(pool_obj, "overflow") else "N/A",
        "total": (pool_obj.size() + pool_any.overflow() if hasattr(pool_obj, "size") else "N/A"),
    }
