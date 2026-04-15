"""Cria tabela conversas — rastreamento de sessões de conversa WhatsApp.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-15

Contexto: Sprint 2 — AgentCliente mantém histórico de conversa para
contexto do Claude SDK. Cada sessão de conversa é registrada aqui,
com referência ao número do cliente e persona identificada.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela conversas com check constraint de persona."""
    op.create_table(
        "conversas",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("telefone", sa.Text(), nullable=False),
        sa.Column("persona", sa.Text(), nullable=False),
        sa.Column("iniciada_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("encerrada_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_conversas_tenant_id", ondelete="CASCADE"),
        sa.CheckConstraint(
            "persona IN ('cliente_b2b', 'representante', 'desconhecido')",
            name="ck_conversas_persona",
        ),
    )
    op.create_index("ix_conversas_tenant_telefone", "conversas", ["tenant_id", "telefone"])
    op.create_index("ix_conversas_tenant_iniciada", "conversas", ["tenant_id", "iniciada_em"])


def downgrade() -> None:
    """Remove tabela conversas e seus índices."""
    op.drop_index("ix_conversas_tenant_iniciada", table_name="conversas")
    op.drop_index("ix_conversas_tenant_telefone", table_name="conversas")
    op.drop_table("conversas")
