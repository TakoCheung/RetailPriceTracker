"""Add authentication fields to users table

Revision ID: 0002_add_auth_fields
Revises: 0001_initial
Create Date: 2024-01-01 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_add_auth_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Add authentication fields to users table
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.add_column("users", sa.Column("github_id", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "role", sa.String(length=20), nullable=False, server_default="viewer"
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Add unique constraint for github_id
    op.create_unique_constraint("uq_users_github_id", "users", ["github_id"])


def downgrade():
    # Remove unique constraint
    op.drop_constraint("uq_users_github_id", "users", type_="unique")

    # Remove authentication fields
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
    op.drop_column("users", "github_id")
    op.drop_column("users", "password_hash")
