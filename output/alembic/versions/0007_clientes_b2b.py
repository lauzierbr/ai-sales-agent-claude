"""Cria tabela clientes_b2b — lookup de clientes B2B por telefone.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-15

Contexto: Sprint 2 implementa o IdentityRouter real. A tabela clientes_b2b
mapeia número de telefone (E.164 sem sufixo) ao tenant, permitindo que o
router identifique clientes B2B que enviam mensagens via WhatsApp.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela clientes_b2b com índices de lookup por tenant e telefone."""
    op.create_table(
        "clientes_b2b",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("cnpj", sa.Text(), nullable=False),
        sa.Column("telefone", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_clientes_b2b_tenant_id", ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "cnpj", name="uq_clientes_b2b_tenant_cnpj"),
        sa.UniqueConstraint("tenant_id", "telefone", name="uq_clientes_b2b_tenant_telefone"),
    )
    op.create_index("ix_clientes_b2b_tenant", "clientes_b2b", ["tenant_id"])
    op.create_index("ix_clientes_b2b_telefone", "clientes_b2b", ["tenant_id", "telefone"])


def downgrade() -> None:
    """Remove tabela clientes_b2b e seus índices."""
    op.drop_index("ix_clientes_b2b_telefone", table_name="clientes_b2b")
    op.drop_index("ix_clientes_b2b_tenant", table_name="clientes_b2b")
    op.drop_table("clientes_b2b")
