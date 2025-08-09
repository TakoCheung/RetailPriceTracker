"""Add brand, is_active, and deleted_at fields to products

Revision ID: 0003_add_product_fields
Revises: 0002_add_auth_fields
Create Date: 2024-01-01 13:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_product_fields"
down_revision = "0002_add_auth_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Add new fields to products table
    op.add_column("products", sa.Column("brand", sa.String(length=100), nullable=True))
    op.add_column(
        "products",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("products", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade():
    # Remove the added fields
    op.drop_column("products", "deleted_at")
    op.drop_column("products", "is_active")
    op.drop_column("products", "brand")
