"""add_stripe_customer_id

Revision ID: 907236a277b9
Revises: ea3c4d930566
Create Date: 2025-11-19 23:39:15.725748

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "907236a277b9"
down_revision: Union[str, Sequence[str], None] = "ea3c4d930566"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("stripe_subscription_id", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
