import hashlib
import logging
import os
import secrets
import sys
from typing import Optional

from app.database import SessionLocal
from app.models import APIKey, Customer, Tenant

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Check for database configuration
if not os.getenv("DATABASE_URL"):
    logger.warning(
        "DATABASE_URL not found. The script will use the default Postgres URL from app.database."
    )


def create_demo_data(
    tenant_name: str = "Demo Company",
    customer_name: str = "Demo User",
    customer_email: str = "demo@example.com",
    key_name: str = "Demo API Key",
) -> Optional[str]:
    """
    Creates a demo tenant, customer, and API key.
    Returns the plain-text API key if successful.
    """
    db = SessionLocal()
    try:
        # 1. Handle Tenant
        slug = "demo-company"
        tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
        if not tenant:
            logger.info(f"Creating tenant: {tenant_name}")
            tenant = Tenant(name=tenant_name, slug=slug, plan="pro")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        else:
            logger.info(f"Using existing tenant: {tenant.name}")

        # 2. Handle Customer
        customer = db.query(Customer).filter(Customer.email == customer_email).first()
        if not customer:
            logger.info(f"Creating customer: {customer_name} ({customer_email})")
            customer = Customer(name=customer_name, email=customer_email, tenant_id=tenant.id)
            db.add(customer)
            db.commit()
            db.refresh(customer)
        else:
            logger.info(f"Using existing customer: {customer_name}")

        # 3. Create API Key
        plain_key = secrets.token_hex(16)
        hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()

        logger.info(f"Generating new API key: {key_name}")
        api_key = APIKey(
            customer_id=customer.id,
            tenant_id=tenant.id,
            key_hash=hashed_key,
            name=key_name,
        )
        db.add(api_key)
        db.commit()

        return plain_key

    except Exception as e:
        logger.error(f"Error creating demo data: {e}")
        db.rollback()
        return None
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starting demo user setup...")
    api_key = create_demo_data()

    if not api_key:
        logger.error("❌ Failed to create demo user.")
        sys.exit(1)
