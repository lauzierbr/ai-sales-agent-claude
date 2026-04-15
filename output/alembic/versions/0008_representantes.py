"""Cria tabela representantes — lookup de representantes por telefone.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-15

Contexto: Sprint 2 — IdentityRouter real precisa identificar representantes
comerciais pelo número de telefone WhatsApp. A coluna usuario_id é opcional
(representantes podem ser cadastrados sem conta no sistema).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela representantes com índice de lookup por tenant e telefone."""
    op.create_table(
        "representantes",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=True),
        sa.Column("telefone", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_representantes_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], name="fk_representantes_usuario_id", ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "telefone", name="uq_representantes_tenant_telefone"),
    )
    op.create_index("ix_representantes_tenant", "representantes", ["tenant_id"])
    op.create_index("ix_representantes_telefone", "representantes", ["tenant_id", "telefone"])


def downgrade() -> None:
    """Remove tabela representantes e seus índices."""
    op.drop_index("ix_representantes_telefone", table_name="representantes")
    op.drop_index("ix_representantes_tenant", table_name="representantes")
    op.drop_table("representantes")
