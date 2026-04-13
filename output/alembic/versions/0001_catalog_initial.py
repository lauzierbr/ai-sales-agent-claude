"""Catálogo inicial: tabelas produtos e precos_diferenciados.

Revision ID: 0001
Revises:
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria extensão pgvector, tabela produtos e precos_diferenciados."""

    # Extensão pgvector — obrigatória para o tipo vector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # ─────────────────────────────────────────────
    # Tabela: produtos
    # ─────────────────────────────────────────────
    op.create_table(
        "produtos",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("codigo_externo", sa.Text(), nullable=False),
        sa.Column("nome_bruto", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=True),
        sa.Column("marca", sa.Text(), nullable=True),
        sa.Column("categoria", sa.Text(), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=True, server_default="{}"),
        sa.Column("texto_rag", sa.Text(), nullable=True),
        sa.Column("meta_agente", sa.JSON(), nullable=True, server_default="{}"),
        sa.Column("preco_padrao", sa.Numeric(12, 2), nullable=True),
        sa.Column("url_imagem", sa.Text(), nullable=True),
        # Tipo vector do pgvector — 1536 dimensões (text-embedding-3-small)
        sa.Column(
            "embedding",
            sa.Text(),  # Placeholder — será convertido para vector(1536) via raw DDL abaixo
            nullable=True,
        ),
        sa.Column(
            "status_enriquecimento",
            sa.Text(),
            nullable=False,
            server_default="pendente",
        ),
        sa.Column(
            "criado_em",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "codigo_externo", name="uq_produtos_tenant_codigo"),
    )

    # Altera coluna embedding para o tipo nativo vector(1536) do pgvector
    op.execute(
        "ALTER TABLE produtos ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )

    # Índices na tabela produtos
    op.create_index("idx_produtos_tenant_id", "produtos", ["tenant_id"])
    op.create_index(
        "idx_produtos_tenant_status",
        "produtos",
        ["tenant_id", "status_enriquecimento"],
    )
    # Índice IVFFlat para busca semântica aproximada (ANN)
    op.execute(
        "CREATE INDEX idx_produtos_embedding ON produtos "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # ─────────────────────────────────────────────
    # Tabela: precos_diferenciados
    # ─────────────────────────────────────────────
    op.create_table(
        "precos_diferenciados",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("codigo_produto", sa.Text(), nullable=False),
        sa.Column("ean", sa.Text(), nullable=True),
        sa.Column("cliente_cnpj", sa.Text(), nullable=False),
        sa.Column("preco_cliente", sa.Numeric(12, 2), nullable=False),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column(
            "criado_em",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "codigo_produto",
            "cliente_cnpj",
            name="uq_precos_tenant_produto_cnpj",
        ),
    )

    op.create_index("idx_precos_tenant_id", "precos_diferenciados", ["tenant_id"])
    op.create_index(
        "idx_precos_tenant_produto",
        "precos_diferenciados",
        ["tenant_id", "codigo_produto"],
    )


def downgrade() -> None:
    """Remove tabelas e extensões."""
    op.execute("DROP INDEX IF EXISTS idx_produtos_embedding")
    op.drop_table("precos_diferenciados")
    op.drop_table("produtos")
    # Não remove a extensão vector pois pode ser usada por outros schemas
