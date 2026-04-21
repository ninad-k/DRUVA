"""multibagger scanner + fundamentals + goals

Revision ID: 0003_multibagger
Revises: 0002_ai_advisor
Create Date: 2026-04-21 10:00:00
"""

from __future__ import annotations

from alembic import op

from app.db import models  # noqa: F401 — register all tables on Base
from app.db.base import Base

revision = "0003_multibagger"
down_revision = "0002_ai_advisor"
branch_labels = None
depends_on = None


MULTIBAGGER_TABLES = (
    "scanner_configs",
    "scan_results",
    "fundamental_snapshots",
    "market_cycle_state",
    "watchlists",
    "watchlist_items",
    "investment_goals",
    "sip_schedules",
    "sip_executions",
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in MULTIBAGGER_TABLES]
    Base.metadata.create_all(bind, tables=tables)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in reversed(MULTIBAGGER_TABLES)]
    Base.metadata.drop_all(bind, tables=tables)
