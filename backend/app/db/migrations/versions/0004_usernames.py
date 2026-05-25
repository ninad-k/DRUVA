"""add usernames to users

Revision ID: 0004_usernames
Revises: 0003_multibagger
Create Date: 2026-05-25 08:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_usernames"
down_revision = "0003_multibagger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
