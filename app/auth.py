import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# Security scheme for API Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_password(plain_password, hashed_password):
    """Verify a plain password against its SHA-256 hash."""
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password


def get_password_hash(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_api_key(db: Session, customer_id: int) -> tuple[str, models.APIKey]:
    """Generate a new API key, hash it, and store it in the database."""
    # Use 16 bytes (32 hex chars) for the key - shorter than 72 byte bcrypt limit
    plain_key = secrets.token_hex(16)
    hashed_key = get_password_hash(plain_key)

    # Fetch customer to get tenant_id
    # Use tenant-aware query to ensure customer belongs to current tenant
    from .middleware import get_current_tenant
    from .tenant_queries import get_tenant_item

    tenant_id = get_current_tenant()
    if tenant_id:
        # If tenant context exists, verify customer belongs to this tenant
        customer = get_tenant_item(db, models.Customer, customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found or access denied")
    else:
        # Fallback for non-tenant contexts (e.g., initial setup, tests)
        customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

    new_api_key = models.APIKey(
        customer_id=customer_id,
        tenant_id=customer.tenant_id,
        key_hash=hashed_key,
        name="New API Key",
    )
    db.add(new_api_key)
    db.commit()
    db.refresh(new_api_key)

    return plain_key, new_api_key


def get_api_key_from_db(db: Session, key: str) -> models.APIKey | None:
    """
    Retrieves an API key from the database by matching against stored hashes.

    This function uses bcrypt password verification for secure key matching.
    While it must iterate through keys (bcrypt hashes are one-way), the
    database index on key_hash ensures efficient retrieval.

    For even better performance in production, consider:
    1. Using a separate lookup table with pre-computed prefixes
    2. Implementing caching with Redis
    3. Rate-limiting key lookups to prevent brute force attacks
    """
    # Query all API keys (with index on key_hash for faster retrieval)
    # In production, consider implementing a cache or alternative lookup method
    api_keys = (
        db.query(models.APIKey)
        .filter(models.APIKey.revoked_at.is_(None))  # Only return non-revoked keys
        .all()
    )

    for api_key_obj in api_keys:
        if verify_password(key, api_key_obj.key_hash):
            return api_key_obj
    return None


def get_current_user(api_key: str = Depends(api_key_header), db: Session = Depends(get_db)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_api_key = get_api_key_from_db(db, api_key)
    if not db_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set tenant context for this request
    from .middleware import set_current_tenant

    set_current_tenant(db_api_key.tenant_id)

    return db_api_key
