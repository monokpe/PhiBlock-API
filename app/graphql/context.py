"""
GraphQL context and dependency injection.
"""

from typing import Any, Dict, Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db
from ..middleware import get_current_tenant


async def get_context(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create the GraphQL context.

    We attempt to get the current user from the request.
    If authentication fails, current_user will be None (if we handle it)
    or the request will be rejected (if we use strict dependency).

    For now, we'll extract the API key manually to allow for
    schema introspection without auth if needed, or strict auth.

    Actually, to keep it simple and secure, we'll check auth inside resolvers
    or use a dependency that doesn't raise if we want mixed public/private.

    But since our REST API is fully authenticated, let's try to get the user.
    """

    # We can't easily use Depends(get_current_user) here if we want to allow
    # some unauthenticated queries (like introspection).
    # But for this implementation, we'll rely on manual extraction or
    # let the resolvers handle "Authentication required".

    # However, to reuse get_current_user logic, we can try to call it.
    # But get_current_user depends on api_key_header.

    # Let's try to resolve the user if the header is present.
    current_user = None
    try:
        # We manually call the dependency logic or use a modified version.
        # Since get_current_user is a FastAPI dependency, calling it directly is tricky
        # without the dependency injection system.
        # But since get_context IS a dependency, we can inject get_current_user!
        pass
    except Exception:
        pass

    # For now, we will pass the db and let resolvers handle logic.
    # But wait, mutations need current_user.

    # Let's use a trick: we'll define a separate dependency for optional auth
    # or just use the request state if we had middleware.

    # Let's try to get the user from the header manually for now to avoid 401 on introspection.
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        # We would need to query the DB.
        # Since we have 'db', we can do it.
        import hashlib

        from ..models import APIKey

        key_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
        current_user = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()

        # Update last used
        if current_user:
            import datetime

            current_user.last_used_at = datetime.datetime.utcnow()
            db.commit()

    tenant_id = get_current_tenant()

    return {
        "db": db,
        "current_user": current_user,
        "tenant_id": tenant_id,
        "request": request,
    }
