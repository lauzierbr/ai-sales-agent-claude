"""0019 — tabela sync_artifacts para rastreamento de arquivos de backup EFOS.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_artifacts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           TEXT NOT NULL,
            connector_kind      TEXT NOT NULL,
            artifact_path       TEXT NOT NULL,
            artifact_checksum   TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sync_artifacts_tenant_id ON sync_artifacts (tenant_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_artifacts_checksum ON sync_artifacts (tenant_id, artifact_checksum)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync_artifacts")
