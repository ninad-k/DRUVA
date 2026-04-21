"""ai advisor tables

Revision ID: 0002_ai_advisor
Revises: 0001_phase1_schema
Create Date: 2026-04-19 12:00:00
"""

from __future__ import annotations

from alembic import op

from app.db import models  # noqa: F401 — ensures tables are registered on Base
from app.db.base import Base

revision = "0002_ai_advisor"
down_revision = "0001_phase1_schema"
branch_labels = None
depends_on = None


ADVISOR_TABLES = (
    "advisor_llm_configs",
    "advisor_watchlist",
    "advisor_runs",
    "advisor_scores",
)


def upgrade() -> None:
    bind = op.get_bind()
    # Create only the advisor tables (others already exist from 0001).
    tables = [Base.metadata.tables[t] for t in ADVISOR_TABLES]
    Base.metadata.create_all(bind, tables=tables)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in reversed(ADVISOR_TABLES)]
    Base.metadata.drop_all(bind, tables=tables)
