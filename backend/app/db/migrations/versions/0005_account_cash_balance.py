"""account cash_balance + last_synced_at

Revision ID: 0005_account_cash_balance
Revises: 0004_usernames
Create Date: 2026-05-25 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_account_cash_balance"
down_revision = "0004_usernames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("cash_balance", sa.Numeric(20, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Seed paper accounts so the dashboard isn't ₹0 the instant this lands; live
    # accounts stay at 0 until the next broker sync writes a real number.
    op.execute(
        "UPDATE accounts SET cash_balance = paper_starting_capital WHERE is_paper = true"
    )


def downgrade() -> None:
    op.drop_column("accounts", "last_synced_at")
    op.drop_column("accounts", "cash_balance")
