"""
GraphQL query resolvers.
"""

import uuid
from typing import List, Optional

import strawberry
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models
from .types import AuditLogType, CustomerType, TenantType


@strawberry.type
class Query:
    @strawberry.field
    def tenants(self, info, page: int = 1, page_size: int = 10) -> List[TenantType]:
        """List all tenants (paginated)."""
        db: Session = info.context["db"]
        skip = (page - 1) * page_size

        tenants = db.query(models.Tenant).offset(skip).limit(page_size).all()

        return tenants

    @strawberry.field
    def tenant(self, info, tenant_id: uuid.UUID) -> Optional[TenantType]:
        """Get a specific tenant by ID."""
        db: Session = info.context["db"]
        return db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()

    @strawberry.field
    def customers(
        self, info, tenant_id: uuid.UUID, page: int = 1, page_size: int = 10
    ) -> List[CustomerType]:
        """List customers for a specific tenant."""
        db: Session = info.context["db"]
        skip = (page - 1) * page_size

        customers = (
            db.query(models.Customer)
            .filter(models.Customer.tenant_id == tenant_id)
            .offset(skip)
            .limit(page_size)
            .all()
        )
        return customers

    @strawberry.field
    def audit_logs(
        self, info, tenant_id: uuid.UUID, page: int = 1, page_size: int = 10
    ) -> List[AuditLogType]:
        """List audit logs for a specific tenant."""
        db: Session = info.context["db"]
        skip = (page - 1) * page_size

        logs = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.tenant_id == tenant_id)
            .order_by(desc(models.AuditLog.timestamp))
            .offset(skip)
            .limit(page_size)
            .all()
        )
        return logs
