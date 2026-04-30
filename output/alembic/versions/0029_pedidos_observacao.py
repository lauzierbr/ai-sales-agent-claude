"""0029 — coluna observacao em pedidos.

Hotfix v0.10.2 — H4 homologacao Sprint 10.

A coluna `pedidos.observacao` era referenciada em orders/repo.py e
agent_gestor.py mas nunca foi criada por nenhuma migration anterior.
O INSERT falhava com UndefinedColumnError, abortando a transacao
e impedindo que mesmo a mensagem de erro do bot fosse persistida.

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-30
"""
from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE pedidos
            ADD COLUMN IF NOT EXISTS observacao TEXT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE pedidos DROP COLUMN IF EXISTS observacao")
