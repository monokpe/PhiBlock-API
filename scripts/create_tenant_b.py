import hashlib
import secrets

from app.database import SessionLocal
from app.models import APIKey, Customer, Tenant


def create_tenant_b():
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == "tenant-b").first()
    if not tenant:
        return

    customer = db.query(Customer).filter(Customer.tenant_id == tenant.id).first()
    if not customer:
        customer = Customer(name="User B", email="userb@tenant-b.com", tenant_id=tenant.id)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    plain_key = secrets.token_hex(16)
    hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
    api_key = APIKey(
        customer_id=customer.id, tenant_id=tenant.id, key_hash=hashed_key, name="Key B"
    )
    db.add(api_key)
    db.commit()

    db.close()


if __name__ == "__main__":
    create_tenant_b()
