import os
import sys

import redis
from sqlalchemy import create_engine, text


def check_database():
    url = os.getenv("DATABASE_URL")
    if not url:
        return False

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            # Check if we can execute a simple query
            result = conn.execute(text("SELECT 1"))

            # Check for the tenants table
            result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'tenants'
                );
            """
                )
            )
            exists = result.scalar()
            if not exists:
                return False

    except Exception:
        return False
    return True


def check_redis():
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = redis.from_url(url)
        if not r.ping():
            return False
    except Exception:
        return False
    return True


if __name__ == "__main__":
    db_ok = check_database()
    redis_ok = check_redis()

    if db_ok and redis_ok:
        sys.exit(0)
    else:
        sys.exit(1)
