"""Cria tabela mensagens_conversa — histórico de mensagens por sessão.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-15

Contexto: Sprint 2 — persistência do histórico de conversa para o
AgentCliente. Redis armazena as últimas 20 mensagens em memória;
PostgreSQL mantém o histórico completo para auditoria e recarregamento.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela mensagens_conversa com check constraint de role."""
    op.create_table(
        "mensagens_conversa",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("conversa_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["conversa_id"], ["conversas.id"], name="fk_mensagens_conversa_id", ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_mensagens_role"),
    )
    op.create_index("ix_mensagens_conversa_id", "mensagens_conversa", ["conversa_id"])
    op.create_index("ix_mensagens_criado", "mensagens_conversa", ["conversa_id", "criado_em"])


def downgrade() -> None:
    """Remove tabela mensagens_conversa e seus índices."""
    op.drop_index("ix_mensagens_criado", table_name="mensagens_conversa")
    op.drop_index("ix_mensagens_conversa_id", table_name="mensagens_conversa")
    op.drop_table("mensagens_conversa")
