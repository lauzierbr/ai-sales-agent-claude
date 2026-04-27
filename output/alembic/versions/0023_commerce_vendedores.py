"""0023 — tabela commerce_vendedores (representantes comerciais EFOS).

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_vendedores (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            ve_codigo           TEXT NOT NULL,
            ve_nome             TEXT NOT NULL,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_vendedores_tenant ON commerce_vendedores (tenant_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_vendedores_ext_id ON commerce_vendedores (tenant_id, source_system, external_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_vendedores_codigo ON commerce_vendedores (tenant_id, ve_codigo)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commerce_vendedores")
