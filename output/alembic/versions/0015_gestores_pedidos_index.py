"""0015 — tabela gestores + índice pedidos + fix CHECK CONSTRAINT conversas.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tabela de gestores (dono/admin do tenant)
    op.execute("""
        CREATE TABLE IF NOT EXISTS gestores (
            id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   TEXT NOT NULL,
            telefone    TEXT NOT NULL,
            nome        TEXT NOT NULL,
            ativo       BOOLEAN NOT NULL DEFAULT true,
            criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, telefone)
        )
    """)

    # Índice de pedidos por tenant + criado_em para queries de relatório
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pedidos_tenant_criado_em "
        "ON pedidos(tenant_id, criado_em)"
    )

    # Fix CHECK CONSTRAINT ck_conversas_persona — adiciona 'gestor'
    op.execute("ALTER TABLE conversas DROP CONSTRAINT IF EXISTS ck_conversas_persona")
    op.execute(
        "ALTER TABLE conversas ADD CONSTRAINT ck_conversas_persona "
        "CHECK (persona IN ('cliente_b2b', 'representante', 'desconhecido', 'gestor'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE conversas DROP CONSTRAINT IF EXISTS ck_conversas_persona")
    op.execute(
        "ALTER TABLE conversas ADD CONSTRAINT ck_conversas_persona "
        "CHECK (persona IN ('cliente_b2b', 'representante', 'desconhecido'))"
    )

    op.execute("DROP INDEX IF EXISTS ix_pedidos_tenant_criado_em")
    op.execute("DROP TABLE IF EXISTS gestores")
