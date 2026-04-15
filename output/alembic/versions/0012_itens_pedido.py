"""Cria tabela itens_pedido — itens de cada pedido capturado.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-15

Contexto: Sprint 2 — cada pedido tem N itens com produto, quantidade e
preço. O subtotal é calculado em Python (quantidade * preco_unitario)
e armazenado como coluna regular para evitar gotchas de SQLAlchemy
Computed com asyncpg.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela itens_pedido com FK para pedidos.

    Nota: produto_id é TEXT (referência lógica ao código externo do produto).
    Não há FK para produtos.id pois produtos.id é UUID — tipos incompatíveis.
    A integridade é gerenciada em Python pela camada de serviço.
    """
    op.create_table(
        "itens_pedido",
        sa.Column("id", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("pedido_id", sa.Text(), nullable=False),
        sa.Column("produto_id", sa.Text(), nullable=False),
        sa.Column("codigo_externo", sa.Text(), nullable=False),
        sa.Column("nome_produto", sa.Text(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(12, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"], name="fk_itens_pedido_id", ondelete="CASCADE"),
        sa.CheckConstraint("quantidade > 0", name="ck_itens_quantidade_positiva"),
        sa.CheckConstraint("preco_unitario >= 0", name="ck_itens_preco_nao_negativo"),
    )
    op.create_index("ix_itens_pedido_pedido_id", "itens_pedido", ["pedido_id"])


def downgrade() -> None:
    """Remove tabela itens_pedido e seus índices."""
    op.drop_index("ix_itens_pedido_pedido_id", table_name="itens_pedido")
    op.drop_table("itens_pedido")
