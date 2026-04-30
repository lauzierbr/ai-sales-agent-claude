"""0025 — D030: tabela contacts + pedidos.account_external_id + campos extras commerce_accounts_b2b.

E7 — Sprint 10. Foundations do ADR D030:
- Tabela `contacts` com todos os campos de identidade de canal.
- `pedidos.account_external_id VARCHAR NULL` (transição; não remove cliente_b2b_id).
- `commerce_accounts_b2b`: 6 novos campos de contato do EFOS.
- Data migration: 5 contatos existentes em `clientes_b2b` → `contacts` com origin='manual'.

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ENUMs necessários
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'contact_papel_enum') THEN
                CREATE TYPE contact_papel_enum AS ENUM ('comprador', 'dono', 'gerente', 'outro');
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'contact_origin_enum') THEN
                CREATE TYPE contact_origin_enum AS ENUM ('erp_suggested', 'manual', 'self_registered');
            END IF;
        END$$;
    """)

    # 2. Tabela contacts
    op.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               VARCHAR NOT NULL,
            account_external_id     VARCHAR,
            nome                    VARCHAR,
            papel                   contact_papel_enum DEFAULT 'comprador',
            authorized              BOOLEAN NOT NULL DEFAULT FALSE,
            channels                JSONB NOT NULL DEFAULT '[]'::jsonb,
            origin                  contact_origin_enum NOT NULL DEFAULT 'manual',
            last_active_at          TIMESTAMPTZ,
            criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            authorized_by_gestor_id VARCHAR
        );
    """)

    # Índices de contacts
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_tenant_account
            ON contacts (tenant_id, account_external_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_tenant_authorized
            ON contacts (tenant_id, authorized);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_channels
            ON contacts USING GIN (channels);
    """)
    # Índice para busca por número WhatsApp dentro de channels JSONB
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_tenant_origin
            ON contacts (tenant_id, origin);
    """)

    # 3. Adicionar pedidos.account_external_id (sem remover cliente_b2b_id)
    op.execute("""
        ALTER TABLE pedidos
            ADD COLUMN IF NOT EXISTS account_external_id VARCHAR;
    """)

    # 4. Adicionar 6 novos campos em commerce_accounts_b2b
    op.execute("""
        ALTER TABLE commerce_accounts_b2b
            ADD COLUMN IF NOT EXISTS contato_padrao    VARCHAR,
            ADD COLUMN IF NOT EXISTS telefone          VARCHAR,
            ADD COLUMN IF NOT EXISTS telefone_celular  VARCHAR,
            ADD COLUMN IF NOT EXISTS email             VARCHAR,
            ADD COLUMN IF NOT EXISTS nome_fantasia     VARCHAR,
            ADD COLUMN IF NOT EXISTS dataultimacompra  DATE;
    """)

    # 5. Data migration: clientes_b2b existentes → contacts com origin='manual'
    # Apenas os que têm telefone ou nome_contato preenchidos
    op.execute("""
        INSERT INTO contacts (
            tenant_id,
            account_external_id,
            nome,
            papel,
            authorized,
            channels,
            origin,
            criado_em,
            atualizado_em
        )
        SELECT
            c.tenant_id,
            NULL AS account_external_id,
            COALESCE(c.nome_contato, c.nome) AS nome,
            'comprador'::contact_papel_enum AS papel,
            TRUE AS authorized,
            CASE
                WHEN c.telefone IS NOT NULL AND c.telefone != ''
                THEN jsonb_build_array(
                    jsonb_build_object(
                        'kind', 'whatsapp',
                        'identifier', c.telefone,
                        'verified', FALSE
                    )
                )
                ELSE '[]'::jsonb
            END AS channels,
            'manual'::contact_origin_enum AS origin,
            COALESCE(c.criado_em, NOW()) AS criado_em,
            NOW() AS atualizado_em
        FROM clientes_b2b c
        WHERE NOT EXISTS (
            SELECT 1 FROM contacts ct
            WHERE ct.tenant_id = c.tenant_id
              AND ct.nome = COALESCE(c.nome_contato, c.nome)
        )
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Remover na ordem inversa
    op.execute("DELETE FROM contacts WHERE origin = 'manual';")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS dataultimacompra;")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS nome_fantasia;")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS email;")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS telefone_celular;")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS telefone;")
    op.execute("ALTER TABLE commerce_accounts_b2b DROP COLUMN IF EXISTS contato_padrao;")
    op.execute("ALTER TABLE pedidos DROP COLUMN IF EXISTS account_external_id;")
    op.execute("DROP TABLE IF EXISTS contacts;")
    op.execute("DROP TYPE IF EXISTS contact_origin_enum;")
    op.execute("DROP TYPE IF EXISTS contact_papel_enum;")
