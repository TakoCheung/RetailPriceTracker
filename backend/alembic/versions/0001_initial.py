"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add SKU column to products table
    op.add_column("products", sa.Column("sku", sa.String(length=100), nullable=True))
    # Create unique index on SKU
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)


def downgrade():
    # Remove unique index and column
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_column("products", "sku")
