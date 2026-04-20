"""0016 — tabela feedbacks dos agentes.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   TEXT NOT NULL,
            perfil      TEXT NOT NULL CHECK (perfil IN ('gestor', 'rep', 'cliente')),
            de          TEXT NOT NULL,
            nome        TEXT,
            mensagem    TEXT NOT NULL,
            contexto    TEXT,
            criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feedbacks_tenant_criado_em "
        "ON feedbacks(tenant_id, criado_em DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_feedbacks_tenant_criado_em")
    op.execute("DROP TABLE IF EXISTS feedbacks")
