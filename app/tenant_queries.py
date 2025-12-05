"""
Tenant-Aware Query Helpers for Multi-Tenancy Support.

This module provides helper functions and decorators to ensure all database
queries are automatically filtered by the current tenant context.
"""

import uuid
from functools import wraps
from typing import Optional, Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from .middleware import get_current_tenant

T = TypeVar("T")


def require_tenant():
    """
    Decorator to ensure tenant context exists for an endpoint.
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tenant_id = get_current_tenant()
            if tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Tenant context not set. Authentication required.",
                )
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tenant_id = get_current_tenant()
            if tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Tenant context not set. Authentication required.",
                )
            return func(*args, **kwargs)

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_tenant_query(db: Session, model: Type[T]) -> Query:
    """
    Create a query pre-filtered by the current tenant.
    """
    tenant_id = get_current_tenant()

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context not set. Authentication required.",
        )

    if not hasattr(model, "tenant_id"):
        raise AttributeError(
            f"Model {model.__name__} does not have a tenant_id column. "
            f"Cannot apply tenant filtering."
        )

    return db.query(model).filter(model.tenant_id == tenant_id)


def get_tenant_item(
    db: Session,
    model: Type[T],
    item_id: uuid.UUID,
) -> Optional[T]:
    """
    Get a single item by ID, ensuring it belongs to the current tenant.
    """
    return get_tenant_query(db, model).filter(model.id == item_id).first()


def verify_tenant_ownership(
    db: Session,
    model: Type[T],
    item_id: uuid.UUID,
) -> T:
    """
    Verify an item exists and belongs to the current tenant.
    """
    item = get_tenant_item(db, model, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} not found or access denied",
        )
    return item


class TenantQueryMixin:
    """
    SQLAlchemy mixin for models that support tenant filtering.
    """

    @classmethod
    def for_tenant(cls, db: Session) -> Query:
        """Get a query filtered by current tenant."""
        return get_tenant_query(db, cls)

    @classmethod
    def get_for_tenant(cls, db: Session, item_id: uuid.UUID):
        """Get a single item by ID for current tenant."""
        return get_tenant_item(db, cls, item_id)

    @classmethod
    def verify_ownership(cls, db: Session, item_id: uuid.UUID):
        """Verify item exists and belongs to current tenant."""
        return verify_tenant_ownership(db, cls, item_id)
