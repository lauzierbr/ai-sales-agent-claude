"""0020 — tabelas commerce_products e commerce_accounts_b2b.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_products (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            codigo              TEXT,
            nome                TEXT NOT NULL,
            descricao           TEXT,
            unidade             TEXT,
            preco_padrao        NUMERIC(14,2),
            ativo               BOOLEAN NOT NULL DEFAULT TRUE,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_products_tenant ON commerce_products (tenant_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_products_ext_id ON commerce_products (tenant_id, source_system, external_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS commerce_accounts_b2b (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            source_system       TEXT NOT NULL DEFAULT 'efos',
            external_id         TEXT NOT NULL,
            codigo              TEXT,
            nome                TEXT NOT NULL,
            cnpj                TEXT,
            cidade              TEXT,
            uf                  TEXT,
            situacao_cliente    INTEGER,
            vendedor_codigo     TEXT,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            snapshot_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_accounts_tenant ON commerce_accounts_b2b (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_commerce_accounts_cidade ON commerce_accounts_b2b (tenant_id, cidade)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_accounts_ext_id ON commerce_accounts_b2b (tenant_id, source_system, external_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commerce_accounts_b2b")
    op.execute("DROP TABLE IF EXISTS commerce_products")
