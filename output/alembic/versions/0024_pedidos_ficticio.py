"""0024 — coluna ficticio em pedidos para identificar pedidos de teste.

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-27

Pedidos criados em staging têm ficticio=True automaticamente.
Pedidos fictícios recebem marca d'água no PDF e prefixo ⚠️ TESTE no caption.
Relatórios EFOS devem filtrar ficticio=False.
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE pedidos
        ADD COLUMN IF NOT EXISTS ficticio BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pedidos_ficticio
        ON pedidos (tenant_id, ficticio)
        WHERE ficticio = FALSE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pedidos_ficticio")
    op.execute("ALTER TABLE pedidos DROP COLUMN IF EXISTS ficticio")
