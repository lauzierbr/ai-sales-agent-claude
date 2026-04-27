"""0018 — tabela sync_runs para rastreamento de execuções de sync EFOS.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_runs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       TEXT NOT NULL,
            connector_kind  TEXT NOT NULL,
            capabilities    TEXT[] NOT NULL DEFAULT '{}',
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at     TIMESTAMPTZ,
            status          TEXT NOT NULL DEFAULT 'running',
            rows_published  INTEGER NOT NULL DEFAULT 0,
            error           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sync_runs_tenant_id ON sync_runs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sync_runs_status ON sync_runs (tenant_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync_runs")
