"""Adiciona FK de produtos.tenant_id → tenants(id).

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-14

Contexto: produtos.tenant_id foi criado como TEXT livre no Sprint 0 antes
da tabela tenants existir no schema formal. Esta migration formaliza a
integridade referencial. Usa RESTRICT (não CASCADE) para evitar que a
desativação de um tenant destrua o catálogo silenciosamente.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona FK produtos.tenant_id → tenants(id) ON DELETE RESTRICT."""
    op.create_foreign_key(
        "fk_produtos_tenant_id",
        "produtos",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove FK de produtos para tenants."""
    op.drop_constraint("fk_produtos_tenant_id", "produtos", type_="foreignkey")
