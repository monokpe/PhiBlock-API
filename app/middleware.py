"""
Tenant Context Middleware for Multi-Tenancy Support.

This middleware extracts the tenant_id from the authenticated API key
and makes it available throughout the request lifecycle.
"""

import uuid
from contextvars import ContextVar
from typing import Callable, Optional, cast

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable to store the current tenant ID
_tenant_context: ContextVar[Optional[uuid.UUID]] = ContextVar("tenant_id", default=None)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and set tenant context for each request.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and extract tenant context.
        """
        _tenant_context.set(None)

        try:
            response = await call_next(request)
            return cast(Response, response)
        finally:
            _tenant_context.set(None)


def get_current_tenant() -> Optional[uuid.UUID]:
    """
    Get the current tenant ID from the request context.
    """
    return _tenant_context.get()


def set_current_tenant(tenant_id: uuid.UUID) -> None:
    """
    Set the current tenant ID in the request context.
    """
    _tenant_context.set(tenant_id)
