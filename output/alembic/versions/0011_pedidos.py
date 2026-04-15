"""Cria tabela pedidos — captura de intenção de pedido via WhatsApp.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-15

Contexto: Sprint 2 — D023: pedidos capturados pelo agente ficam em status
PENDENTE até processamento manual pelo gestor no EFOS. O pdf_path armazena
o caminho relativo do PDF gerado e enviado ao gestor via WhatsApp.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela pedidos com check constraint de status."""
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("cliente_b2b_id", sa.Text(), nullable=True),
        sa.Column("representante_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pendente"),
        sa.Column("total_estimado", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_pedidos_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cliente_b2b_id"], ["clientes_b2b.id"], name="fk_pedidos_cliente_b2b_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["representante_id"], ["representantes.id"], name="fk_pedidos_representante_id", ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('pendente', 'confirmado', 'cancelado')",
            name="ck_pedidos_status",
        ),
    )
    op.create_index("ix_pedidos_tenant", "pedidos", ["tenant_id"])
    op.create_index("ix_pedidos_tenant_status", "pedidos", ["tenant_id", "status"])
    op.create_index("ix_pedidos_tenant_criado", "pedidos", ["tenant_id", "criado_em"])


def downgrade() -> None:
    """Remove tabela pedidos e seus índices."""
    op.drop_index("ix_pedidos_tenant_criado", table_name="pedidos")
    op.drop_index("ix_pedidos_tenant_status", table_name="pedidos")
    op.drop_index("ix_pedidos_tenant", table_name="pedidos")
    op.drop_table("pedidos")
