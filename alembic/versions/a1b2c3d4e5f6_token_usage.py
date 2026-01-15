"""Create token_usage table for token tracking

Revision ID: a1b2c3d4e5f6_token_usage
Revises: cdcdf2318ca5_initial_migration
Create Date: 2025-11-15 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6_token_usage"
down_revision = "cdcdf2318ca5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create token_usage table
    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("estimated_cost_usd", sa.DECIMAL(10, 6), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("audit_data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_token_usage_api_key_id"), "token_usage", ["api_key_id"], unique=False)
    op.create_index(op.f("ix_token_usage_endpoint"), "token_usage", ["endpoint"], unique=False)
    op.create_index(op.f("ix_token_usage_request_id"), "token_usage", ["request_id"], unique=False)
    op.create_index(op.f("ix_token_usage_timestamp"), "token_usage", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_token_usage_timestamp"), table_name="token_usage")
    op.drop_index(op.f("ix_token_usage_request_id"), table_name="token_usage")
    op.drop_index(op.f("ix_token_usage_endpoint"), table_name="token_usage")
    op.drop_index(op.f("ix_token_usage_api_key_id"), table_name="token_usage")
    op.drop_table("token_usage")
