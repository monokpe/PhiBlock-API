"""
Tenant Management API Endpoints.

Provides CRUD operations for managing tenants in the system.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import Tenant
from .schemas.tenant import TenantCreate, TenantListResponse, TenantResponse, TenantUpdate

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new tenant.

    - **name**: Tenant name (required)
    - **slug**: URL-safe identifier (auto-generated from name if not provided)
    - **plan**: Subscription plan (basic, pro, enterprise)
    """
    # Generate slug if not provided
    slug = tenant_data.generate_slug()

    # Check if slug already exists
    existing = db.query(Tenant).filter(Tenant.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Tenant with slug '{slug}' already exists"
        )

    # Create tenant
    tenant = Tenant(
        name=tenant_data.name,
        slug=slug,
        plan=tenant_data.plan or "basic",
    )

    # Create Stripe Customer
    from .billing import billing_service

    stripe_id = billing_service.create_customer(
        email=f"admin@{slug}.com", name=tenant_data.name  # Placeholder email
    )
    if stripe_id:
        tenant.stripe_customer_id = stripe_id

    try:
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tenant with this slug already exists"
        )


@router.get("", response_model=TenantListResponse)
def list_tenants(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    List all tenants with pagination.

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 10, max: 100)
    """
    # Get total count
    total = db.query(Tenant).count()

    # Get paginated results
    offset = (page - 1) * page_size
    tenants = (
        db.query(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(page_size).all()
    )

    return TenantListResponse(
        tenants=tenants,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific tenant by ID.

    - **tenant_id**: UUID of the tenant
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a tenant.

    - **tenant_id**: UUID of the tenant
    - **name**: New tenant name (optional)
    - **plan**: New subscription plan (optional)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Update fields if provided
    if tenant_data.name is not None:
        tenant.name = tenant_data.name

    if tenant_data.plan is not None:
        tenant.plan = tenant_data.plan

    try:
        db.commit()
        db.refresh(tenant)
        return tenant
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Update failed due to constraint violation"
        )


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete a tenant.

    **Warning**: This will delete the tenant and may affect related data.

    - **tenant_id**: UUID of the tenant
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        db.delete(tenant)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete tenant with existing related data. Delete related records first.",
        )
