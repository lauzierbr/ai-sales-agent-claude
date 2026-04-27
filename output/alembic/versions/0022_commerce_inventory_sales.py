"""0022 — tabelas commerce_inventory e commerce_sales_history.

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_inventory (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            produto_codigo      TEXT,
            produto_nome        TEXT,
            saldo               NUMERIC(14,3),
            deposito            TEXT,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_inventory_tenant ON commerce_inventory (tenant_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_inventory_ext_id ON commerce_inventory (tenant_id, source_system, external_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_sales_history (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            cliente_codigo      TEXT,
            produto_codigo      TEXT,
            quantidade          NUMERIC(14,3),
            total               NUMERIC(14,2),
            data_venda          DATE,
            mes                 INTEGER,
            ano                 INTEGER,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_sales_tenant ON commerce_sales_history (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_sales_mes_ano ON commerce_sales_history (tenant_id, ano, mes)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commerce_sales_history")
    op.execute("DROP TABLE IF EXISTS commerce_inventory")
