"""0027 — W4: coluna embedding em commerce_products.

E17 — Sprint 10. Pré-condição para deprecar tabela produtos legada:
- CREATE EXTENSION IF NOT EXISTS vector (antes do ADD COLUMN).
- ADD COLUMN embedding vector(1536) em commerce_products.
- Índice HNSW para busca semântica eficiente.

ATENÇÃO: Executar scripts/migrate_embeddings.py ANTES da migration 0028 (drop).
DT-1: modelo confirmado como text-embedding-3-small (vector_dims=1536).

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-29
"""
from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Garantir que a extensão pgvector existe (gotcha: CREATE EXTENSION pode falhar se
    #    executar sem IF NOT EXISTS em upgrades repetidos)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Adicionar coluna embedding vector(1536)
    # Usa raw SQL para compatibilidade com pgvector (Alembic não tem suporte nativo)
    op.execute("""
        ALTER TABLE commerce_products
            ADD COLUMN IF NOT EXISTS embedding vector(1536);
    """)

    # 3. Índice HNSW para busca semântica por cosseno
    # IF NOT EXISTS garante idempotência
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_commerce_products_embedding_hnsw
            ON commerce_products USING hnsw (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_commerce_products_embedding_hnsw;")
    op.execute("ALTER TABLE commerce_products DROP COLUMN IF EXISTS embedding;")
