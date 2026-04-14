"""Schedule de crawl por tenant.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela crawl_schedule com schedule padrão para JMB."""

    op.create_table(
        "crawl_schedule",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column(
            "cron_expression",
            sa.Text(),
            nullable=False,
            server_default="0 2 1 * *",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id"),
    )

    # Seed: schedule default para JMB
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO crawl_schedule (id, tenant_id, cron_expression, enabled, created_at)
            VALUES (gen_random_uuid()::text, 'jmb', '0 2 1 * *', true, NOW())
            ON CONFLICT (tenant_id) DO NOTHING
        """)
    )


def downgrade() -> None:
    """Remove tabela crawl_schedule."""
    op.drop_table("crawl_schedule")
