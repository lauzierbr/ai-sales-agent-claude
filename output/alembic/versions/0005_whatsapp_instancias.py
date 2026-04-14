"""Instâncias WhatsApp — associação entre Evolution API e tenant.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela whatsapp_instancias."""

    op.create_table(
        "whatsapp_instancias",
        sa.Column("instancia_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("numero_whatsapp", sa.Text(), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.PrimaryKeyConstraint("instancia_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_whatsapp_instancias_tenant",
        "whatsapp_instancias",
        ["tenant_id"],
    )


def downgrade() -> None:
    """Remove tabela whatsapp_instancias."""
    op.drop_index("ix_whatsapp_instancias_tenant", table_name="whatsapp_instancias")
    op.drop_table("whatsapp_instancias")
