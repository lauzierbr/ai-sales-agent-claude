"""0021 — tabelas commerce_orders e commerce_order_items.

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_orders (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            numero_pedido       TEXT,
            cliente_codigo      TEXT,
            cliente_nome        TEXT,
            vendedor_codigo     TEXT,
            data_pedido         DATE,
            total               NUMERIC(14,2),
            status              TEXT,
            mes                 INTEGER,
            ano                 INTEGER,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_orders_tenant ON commerce_orders (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_orders_mes_ano ON commerce_orders (tenant_id, ano, mes)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_orders_ext_id ON commerce_orders (tenant_id, source_system, external_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_order_items (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            order_external_id   TEXT NOT NULL,
            produto_codigo      TEXT,
            produto_nome        TEXT,
            quantidade          NUMERIC(14,3),
            preco_unitario      NUMERIC(14,2),
            total               NUMERIC(14,2),
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_order_items_tenant ON commerce_order_items (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_order_items_order ON commerce_order_items (tenant_id, order_external_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commerce_order_items")
    op.execute("DROP TABLE IF EXISTS commerce_orders")
