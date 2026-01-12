import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis

def check_database():
    print("--- Database Diagnostics ---")
    url = os.getenv("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL not set in environment!")
        return False
    
    print(f"Connecting to: {url.split('@')[-1] if '@' in url else url}")
    
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            # Check if we can execute a simple query
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
            
            # Check for the tenants table
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'tenants'
                );
            """))
            exists = result.scalar()
            if exists:
                print("✅ Table 'tenants' exists")
            else:
                print("❌ Table 'tenants' DOES NOT exist. Migrations might have failed.")
                return False
                
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False
    return True

def check_redis():
    print("\n--- Redis Diagnostics ---")
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"Connecting to Redis at: {url}")
    try:
        r = redis.from_url(url)
        if r.ping():
            print("✅ Redis connection successful")
        else:
            print("❌ Redis ping failed")
            return False
    except Exception as e:
        print(f"❌ Redis error: {e}")
        return False
    return True

if __name__ == "__main__":
    db_ok = check_database()
    redis_ok = check_redis()
    
    if db_ok and redis_ok:
        print("\n✨ All systems nominal.")
        sys.exit(0)
    else:
        print("\n⚠️ Diagnostics found issues.")
        sys.exit(1)
