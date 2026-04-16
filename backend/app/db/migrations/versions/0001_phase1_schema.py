"""phase1 schema

Revision ID: 0001_phase1_schema
Revises:
Create Date: 2026-04-16 16:30:00
"""

from __future__ import annotations

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0001_phase1_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb";')
    # Models include `secret_token_hash` (unique) on webhook_sources and
    # `consecutive_health_failures` / `health_disabled_at` on accounts; both are
    # picked up by metadata.create_all() at first install.
    Base.metadata.create_all(bind)
    op.execute("SELECT create_hypertable('latency_samples', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');")
    op.execute("SELECT create_hypertable('ohlcv_candles', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');")
    op.execute("SELECT create_hypertable('order_events', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');")
    op.execute("SELECT create_hypertable('pnl_snapshots', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_no_update_delete() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'audit_events is append-only'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_no_update_delete();
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
