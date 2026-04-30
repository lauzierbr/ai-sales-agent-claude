"""0026 — F-07: tabela sync_schedule + gestores.role ENUM.

E13 — Sprint 10. Foundations do F-07 (controle de frequência sync EFOS via UI):
- Tabela `sync_schedule` com UNIQUE (tenant_id, connector_kind).
- Seed default: (jmb, efos_backup, diario, '0 13 * * *', true).
- `gestores.role ENUM('admin','gestor') DEFAULT 'gestor'`.

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-29
"""
from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ENUM para preset do schedule
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sync_preset_enum') THEN
                CREATE TYPE sync_preset_enum AS ENUM ('manual', 'diario', '2x_dia', '4x_dia', 'horario');
            END IF;
        END$$;
    """)

    # 2. ENUM para role de gestor
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role_enum') THEN
                CREATE TYPE role_enum AS ENUM ('admin', 'gestor');
            END IF;
        END$$;
    """)

    # 3. Tabela sync_schedule
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_schedule (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         VARCHAR NOT NULL,
            connector_kind    VARCHAR NOT NULL,
            preset            sync_preset_enum NOT NULL DEFAULT 'diario',
            cron_expression   VARCHAR,
            enabled           BOOLEAN NOT NULL DEFAULT TRUE,
            last_triggered_at TIMESTAMPTZ,
            next_run_at       TIMESTAMPTZ,
            atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, connector_kind)
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_schedule_tenant
            ON sync_schedule (tenant_id);
    """)

    # 4. Seed default para JMB (diário às 13:00 BRT = 16:00 UTC)
    op.execute("""
        INSERT INTO sync_schedule (tenant_id, connector_kind, preset, cron_expression, enabled)
        VALUES ('jmb', 'efos_backup', 'diario', '0 13 * * *', true)
        ON CONFLICT (tenant_id, connector_kind) DO NOTHING;
    """)

    # 5. Adicionar coluna role em gestores
    op.execute("""
        ALTER TABLE gestores
            ADD COLUMN IF NOT EXISTS role role_enum NOT NULL DEFAULT 'gestor';
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE gestores DROP COLUMN IF EXISTS role;")
    op.execute("DROP TABLE IF EXISTS sync_schedule;")
    op.execute("DROP TYPE IF EXISTS sync_preset_enum;")
    op.execute("DROP TYPE IF EXISTS role_enum;")
