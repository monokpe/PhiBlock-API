"""
GraphQL context and dependency injection.
"""

from typing import Any, Dict

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import get_current_tenant


async def get_context(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create the GraphQL context.
    """

    current_user = None
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        import hashlib

        from ..models import APIKey

        key_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
        current_user = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()

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
