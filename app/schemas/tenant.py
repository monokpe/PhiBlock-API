"""
Pydantic schemas for Tenant Management API.

These schemas define the request and response models for tenant CRUD operations.
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    # Convert to lowercase and replace spaces with hyphens
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


class TenantBase(BaseModel):
    """Base tenant schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Tenant name")
    plan: Optional[str] = Field(
        default="basic", description="Subscription plan: basic, pro, enterprise"
    )

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v):
        """Validate plan is one of the allowed values."""
        allowed_plans = ["basic", "pro", "enterprise"]
        if v and v not in allowed_plans:
            raise ValueError(f"Plan must be one of: {', '.join(allowed_plans)}")
        return v


class TenantCreate(TenantBase):
    """Schema for creating a new tenant."""

    slug: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="URL-safe identifier (auto-generated from name if not provided)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v):
        """Validate slug format."""
        if v:
            if not re.match(r"^[a-z0-9-]+$", v):
                raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v

    def generate_slug(self) -> str:
        """Generate slug from name if not provided."""
        if self.slug:
            return self.slug
        return slugify(self.name)


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    plan: Optional[str] = Field(None, description="Subscription plan")

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v):
        """Validate plan is one of the allowed values."""
        if v:
            allowed_plans = ["basic", "pro", "enterprise"]
            if v not in allowed_plans:
                raise ValueError(f"Plan must be one of: {', '.join(allowed_plans)}")
        return v


class TenantResponse(TenantBase):
    """Schema for tenant API responses."""

    id: uuid.UUID
    slug: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    """Schema for paginated tenant list responses."""

    tenants: List[TenantResponse]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.page_size - 1) // self.page_size
