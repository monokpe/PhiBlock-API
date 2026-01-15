import logging
import sys
from pathlib import Path

# Ensure app is in path
sys.path.append(str(Path(__file__).parent.parent))

from app import auth, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

logger = logging.getLogger(__name__)


def setup_load_test_data():
    """Setup load testing data."""
    db = SessionLocal()

    try:
        # Create a test tenant
        tenant_name = "load-test-tenant"
        tenant = db.query(models.Tenant).filter(models.Tenant.name == tenant_name).first()

        if not tenant:
            logger.info(f"Creating tenant: {tenant_name}")
            tenant = models.Tenant(name=tenant_name, slug="load-test-tenant", plan="enterprise")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # Check if customer exists
        customer_email = "loadtester@example.com"
        customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()

        if not customer:
            logger.info(f"Creating customer: {customer_email}")
            customer = models.Customer(
                tenant_id=tenant.id, name="Load Tester", email=customer_email
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)

        # Create API Key
        key_value = "test-load-key"
        key_hash = auth.get_password_hash(key_value)

        existing_key = db.query(models.APIKey).filter(models.APIKey.key_hash == key_hash).first()

        if not existing_key:
            logger.info(f"Creating API Key: {key_value}")
            api_key = models.APIKey(
                tenant_id=tenant.id,
                customer_id=customer.id,
                key_hash=key_hash,
                name="Load Test Key",
                tier="platinum",
                rate_limit=10000,  # High limit for load testing
            )
            db.add(api_key)
            db.commit()
            logger.info("Load test data setup complete.")
        else:
            logger.info("API Key already exists.")

    except Exception as e:
        logger.error(f"Error setting up data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    setup_load_test_data()
