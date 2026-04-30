"""0030 — unique indexes para UPSERT em commerce_order_items e commerce_sales_history.

Hotfix v0.10.10 — B-36 fix de publish.py incompleto.

publish.py usa ON CONFLICT (tenant_id, source_system, external_id) em todas
as tabelas commerce_*. As tabelas commerce_order_items e commerce_sales_history
não tinham esse unique index, causando:
  InvalidColumnReferenceError: there is no unique or exclusion constraint
  matching the ON CONFLICT specification

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-30
"""
from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_order_items_ext_id
            ON commerce_order_items (tenant_id, source_system, external_id)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_sales_history_ext_id
            ON commerce_sales_history (tenant_id, source_system, external_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_commerce_order_items_ext_id")
    op.execute("DROP INDEX IF EXISTS idx_commerce_sales_history_ext_id")
