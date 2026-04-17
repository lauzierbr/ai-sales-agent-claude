"""Adiciona representante_id em clientes_b2b — FK para representantes.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-16

Contexto: Sprint 3 — cada cliente B2B pode ser vinculado a um representante.
Coluna NULLABLE para não quebrar clientes existentes sem representante.
Ativa extensão unaccent para busca insensível a acentos.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona representante_id NULLABLE em clientes_b2b + FK + índice + unaccent.

    Operação segura em produção: ALTER TABLE ADD COLUMN NULLABLE não bloqueia leitura.
    """
    # Ativa extensão unaccent para busca insensível a acentos (buscar_por_nome)
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")

    # Adiciona coluna representante_id — NULLABLE para compatibilidade com dados existentes
    op.add_column(
        "clientes_b2b",
        sa.Column("representante_id", sa.Text(), nullable=True),
    )

    # FK para representantes.id — SET NULL ao deletar representante
    op.create_foreign_key(
        "fk_clientes_b2b_representante_id",
        "clientes_b2b",
        "representantes",
        ["representante_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Índice composto para queries filtradas por tenant + representante
    op.create_index(
        "ix_clientes_b2b_rep",
        "clientes_b2b",
        ["tenant_id", "representante_id"],
    )


def downgrade() -> None:
    """Remove índice, FK e coluna representante_id de clientes_b2b.

    Não remove extensão unaccent — pode estar em uso por outros objetos.
    """
    op.drop_index("ix_clientes_b2b_rep", table_name="clientes_b2b")
    op.drop_constraint(
        "fk_clientes_b2b_representante_id",
        "clientes_b2b",
        type_="foreignkey",
    )
    op.drop_column("clientes_b2b", "representante_id")
