"""
Tenant Context Middleware for Multi-Tenancy Support.

This middleware extracts the tenant_id from the authenticated API key
and makes it available throughout the request lifecycle.
"""

import uuid
from contextvars import ContextVar
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable to store the current tenant ID
_tenant_context: ContextVar[Optional[uuid.UUID]] = ContextVar("tenant_id", default=None)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and set tenant context for each request.

    The tenant_id is extracted from the authenticated API key and stored
    in a context variable that can be accessed throughout the request.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and extract tenant context.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler

        Returns:
            The response from the next handler
        """
        # Reset tenant context at the start of each request
        _tenant_context.set(None)

        # The tenant_id will be set by the authentication dependency
        # after the API key is validated. This middleware just ensures
        # the context is properly initialized and cleaned up.

        try:
            response = await call_next(request)
            return response
        finally:
            # Clean up context after request
            _tenant_context.set(None)


def get_current_tenant() -> Optional[uuid.UUID]:
    """
    Get the current tenant ID from the request context.

    Returns:
        The current tenant UUID, or None if not set
    """
    return _tenant_context.get()


def set_current_tenant(tenant_id: uuid.UUID) -> None:
    """
    Set the current tenant ID in the request context.

    This should be called by the authentication layer after validating
    the API key.

    Args:
        tenant_id: The tenant UUID to set
    """
    _tenant_context.set(tenant_id)
