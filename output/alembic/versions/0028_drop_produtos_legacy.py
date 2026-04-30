"""0028 — W4: drop tabela produtos legada.

E20 — Sprint 10. Pré-condições obrigatórias antes de executar:
  1. Migration 0027 aplicada (commerce_products.embedding EXISTS).
  2. scripts/migrate_embeddings.py executado com >= 95% cobertura.
  3. grep "FROM produtos" em output/src/ retorna 0 hits em código de produção.
  4. Smoke comportamental: cliente busca "shampoo" → >= 1 produto retornado.
  5. pytest -m unit passa.

Tabelas removidas:
  - produtos (catálogo legado)
  - crawl_runs (execuções do crawler legado)

ATENÇÃO: Este downgrade é destrutivo. Não há rollback funcional após o drop.

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-29
"""
from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remover tabelas legadas do catalog crawler
    # crawl_runs: execuções do crawler EFOS (substituído pelo sync EFOS + APScheduler)
    op.execute("DROP TABLE IF EXISTS crawl_runs CASCADE;")
    # produtos: catálogo enriquecido manualmente (substituído por commerce_products)
    op.execute("DROP TABLE IF EXISTS produtos CASCADE;")
    # crawl_schedule: schedule do crawler (substituído por sync_schedule)
    op.execute("DROP TABLE IF EXISTS crawl_schedule CASCADE;")


def downgrade() -> None:
    # Downgrade não restaura dados — apenas recria estrutura vazia para compatibilidade
    op.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR NOT NULL,
            codigo_externo VARCHAR,
            nome_bruto VARCHAR,
            nome VARCHAR,
            marca VARCHAR,
            categoria VARCHAR,
            tags TEXT[],
            texto_rag TEXT,
            meta_agente JSONB,
            preco_padrao NUMERIC(10,2),
            url_imagem TEXT,
            imagem_local TEXT,
            status_enriquecimento VARCHAR DEFAULT 'pendente',
            embedding vector(1536),
            criado_em TIMESTAMPTZ DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS crawl_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR NOT NULL,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            status VARCHAR DEFAULT 'running',
            products_found INTEGER DEFAULT 0,
            error TEXT
        );
    """)
