"""clientes_b2b: torna telefone nullable + unique parcial + índice cross-table.

Revisão: telefone de cliente B2B não é obrigatório — clientes acessados
exclusivamente via representante não precisam de WhatsApp próprio.

Também adiciona unique constraint parcial em (tenant_id, telefone)
WHERE telefone IS NOT NULL para evitar colisões silenciosas.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Remove NOT NULL de clientes_b2b.telefone
    op.alter_column(
        "clientes_b2b",
        "telefone",
        existing_type=sa.Text(),
        nullable=True,
    )

    # 2. Remove índice único antigo se existir (pode ser ix_clientes_b2b_telefone)
    op.execute("""
        DROP INDEX IF EXISTS ix_clientes_b2b_telefone;
    """)

    # 3. Cria unique constraint parcial: (tenant_id, telefone) WHERE telefone IS NOT NULL
    #    Impede dois clientes do mesmo tenant com o mesmo telefone (quando preenchido)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_clientes_b2b_tenant_telefone
        ON clientes_b2b (tenant_id, telefone)
        WHERE telefone IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_clientes_b2b_tenant_telefone;")

    # Antes de recolocar NOT NULL, garante que não há NULLs
    op.execute("UPDATE clientes_b2b SET telefone = '00000000000' WHERE telefone IS NULL;")

    op.alter_column(
        "clientes_b2b",
        "telefone",
        existing_type=sa.Text(),
        nullable=False,
    )
