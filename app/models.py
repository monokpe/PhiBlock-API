import datetime
import uuid

from sqlalchemy import (
    DECIMAL,
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent GUID type."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            else:
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value


Base = declarative_base()


class Tenant(Base):
    """
    Tenant model for multi-tenancy support.
    """

    __tablename__ = "tenants"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    plan = Column(String(50), default="basic")
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    customers = relationship("Customer", back_populates="tenant")
    api_keys = relationship("APIKey", back_populates="tenant")
    audit_logs = relationship("AuditLog", back_populates="tenant")
    token_usage = relationship("TokenUsage", back_populates="tenant")

    __table_args__ = (
        Index("ix_tenant_slug", "slug"),
        Index("ix_tenant_created", "created_at"),
    )


class Customer(Base):
    __tablename__ = "customers"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    tenant = relationship("Tenant", back_populates="customers")
    api_keys = relationship("APIKey", back_populates="customer")

    @classmethod
    def for_tenant(cls, db):
        """Get a query filtered by current tenant."""
        from .tenant_queries import get_tenant_query

        return get_tenant_query(db, cls)

    @classmethod
    def get_for_tenant(cls, db, item_id):
        """Get a single customer by ID for current tenant."""
        from .tenant_queries import get_tenant_item

        return get_tenant_item(db, cls, item_id)

    @classmethod
    def verify_ownership(cls, db, item_id):
        """Verify customer exists and belongs to current tenant."""
        from .tenant_queries import verify_tenant_ownership

        return verify_tenant_ownership(db, cls, item_id)


class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(GUID, ForeignKey("customers.id"), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255))
    tier = Column(String(50), default="standard")
    rate_limit = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_used_at = Column(DateTime)
    revoked_at = Column(DateTime)

    tenant = relationship("Tenant", back_populates="api_keys")
    customer = relationship("Customer", back_populates="api_keys")
    audit_logs = relationship("AuditLog", back_populates="api_key")

    @classmethod
    def for_tenant(cls, db):
        """Get a query filtered by current tenant."""
        from .tenant_queries import get_tenant_query

        return get_tenant_query(db, cls)

    @classmethod
    def get_for_tenant(cls, db, item_id):
        """Get a single API key by ID for current tenant."""
        from .tenant_queries import get_tenant_item

        return get_tenant_item(db, cls, item_id)

    @classmethod
    def verify_ownership(cls, db, item_id):
        """Verify API key exists and belongs to current tenant."""
        from .tenant_queries import verify_tenant_ownership

        return verify_tenant_ownership(db, cls, item_id)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(GUID, ForeignKey("tenants.id"), nullable=False, index=True)
    request_id = Column(GUID, nullable=False, unique=True, index=True, default=uuid.uuid4)
    api_key_id = Column(GUID, ForeignKey("api_keys.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    endpoint = Column(String(255), nullable=False)
    http_method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)

    prompt_hash = Column(String(64), index=True)
    prompt_length = Column(Integer)
    compliance_context = Column(JSON)

    entities_detected = Column(JSON)
    injection_score = Column(DECIMAL(5, 4))

    compliance_status = Column(String(20))
    violations = Column(JSON)
    risk_score = Column(DECIMAL(5, 4))

    tokens_analyzed = Column(Integer)
    tokens_billable = Column(Integer)

    redacted_prompt_encrypted = Column(LargeBinary)

    tenant = relationship("Tenant", back_populates="audit_logs")
    api_key = relationship("APIKey", back_populates="audit_logs")

    __table_args__ = (Index("ix_audit_logs_tenant_timestamp", "tenant_id", "timestamp"),)

    @classmethod
    def for_tenant(cls, db):
        """Get a query filtered by current tenant."""
        from .tenant_queries import get_tenant_query

        return get_tenant_query(db, cls)

    @classmethod
    def get_for_tenant(cls, db, item_id):
        """Get a single audit log by ID for current tenant."""
        from .tenant_queries import get_tenant_item

        return get_tenant_item(db, cls, item_id)

    @classmethod
    def verify_ownership(cls, db, item_id):
        """Verify audit log exists and belongs to current tenant."""
        from .tenant_queries import verify_tenant_ownership

        return verify_tenant_ownership(db, cls, item_id)


class TokenUsage(Base):
    __tablename__ = "token_usage"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(GUID, ForeignKey("tenants.id"), nullable=False, index=True)
    request_id = Column(GUID, nullable=False, unique=True, index=True, default=uuid.uuid4)
    api_key_id = Column(GUID, ForeignKey("api_keys.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    endpoint = Column(String(255), nullable=False, index=True)

    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False)

    model = Column(String(50), nullable=False, default="gpt-3.5-turbo")
    estimated_cost_usd = Column(DECIMAL(10, 6), nullable=False)

    risk_level = Column(String(20), nullable=False, default="safe")

    audit_data = Column(JSON)

    reported_to_stripe = Column(Boolean, default=False, index=True)

    tenant = relationship("Tenant", back_populates="token_usage")
    api_key = relationship("APIKey")

    __table_args__ = (
        Index("ix_token_usage_tenant_timestamp", "tenant_id", "timestamp"),
        Index("ix_token_usage_tenant_reported", "tenant_id", "reported_to_stripe"),
    )

    @classmethod
    def for_tenant(cls, db):
        """Get a query filtered by current tenant."""
        from .tenant_queries import get_tenant_query

        return get_tenant_query(db, cls)

    @classmethod
    def get_for_tenant(cls, db, item_id):
        """Get a single token usage record by ID for current tenant."""
        from .tenant_queries import get_tenant_item

        return get_tenant_item(db, cls, item_id)

    @classmethod
    def verify_ownership(cls, db, item_id):
        """Verify token usage record exists and belongs to current tenant."""
        from .tenant_queries import verify_tenant_ownership

        return verify_tenant_ownership(db, cls, item_id)
