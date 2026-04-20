"""0017 — campo nome_contato em clientes_b2b.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE clientes_b2b ADD COLUMN IF NOT EXISTS nome_contato TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE clientes_b2b DROP COLUMN IF EXISTS nome_contato")
