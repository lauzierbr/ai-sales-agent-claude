"""Tenants e usuários — tabelas base da plataforma multi-tenant.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14

Seed JMB: cria tenant JMB + usuário gestor se GESTOR_PASSWORD_JMB estiver
configurado no Infisical. Se ausente, seed é pulado com warning.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabelas tenants e usuarios + seed do tenant JMB."""

    # ─────────────────────────────────────────────
    # Tabela: tenants
    # ─────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("cnpj", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("whatsapp_number", sa.Text(), nullable=True),
        sa.Column(
            "config_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "criado_em",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cnpj"),
    )

    # ─────────────────────────────────────────────
    # Tabela: usuarios
    # ─────────────────────────────────────────────
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("cnpj", sa.Text(), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "criado_em",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('gestor', 'rep', 'cliente')", name="usuarios_role_check"),
    )

    op.create_index(
        "ix_usuarios_cnpj_tenant",
        "usuarios",
        ["cnpj", "tenant_id"],
        unique=True,
    )

    # ─────────────────────────────────────────────
    # Seed: tenant JMB + gestor
    # ─────────────────────────────────────────────
    _seed_jmb()


def _seed_jmb() -> None:
    """Cria tenant JMB e usuário gestor se GESTOR_PASSWORD_JMB disponível."""
    import structlog

    log = structlog.get_logger()

    gestor_senha = os.getenv("GESTOR_PASSWORD_JMB", "")
    if not gestor_senha:
        log.warning(
            "seed_jmb_pulado",
            motivo="GESTOR_PASSWORD_JMB não configurada no Infisical",
        )
        return

    import bcrypt

    now = datetime.now(timezone.utc)
    tenant_id = "jmb"
    gestor_id = str(uuid.uuid4())
    senha_hash = bcrypt.hashpw(gestor_senha.encode(), bcrypt.gensalt(12)).decode()

    conn = op.get_bind()

    # Idempotente — ignora se já existir
    conn.execute(
        sa.text("""
            INSERT INTO tenants (id, nome, cnpj, ativo, whatsapp_number, config_json, criado_em)
            VALUES (:id, :nome, :cnpj, :ativo, :whatsapp_number, :config_json, :criado_em)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": tenant_id,
            "nome": "JMB Distribuidora",
            "cnpj": "00.000.000/0001-00",  # placeholder — substituir pelo CNPJ real
            "ativo": True,
            "whatsapp_number": None,
            "config_json": "{}",
            "criado_em": now,
        },
    )

    conn.execute(
        sa.text("""
            INSERT INTO usuarios (id, tenant_id, cnpj, senha_hash, role, ativo, criado_em)
            VALUES (:id, :tenant_id, :cnpj, :senha_hash, :role, :ativo, :criado_em)
            ON CONFLICT (cnpj, tenant_id) DO NOTHING
        """),
        {
            "id": gestor_id,
            "tenant_id": tenant_id,
            "cnpj": "00.000.000/0001-00",  # CNPJ do gestor JMB
            "senha_hash": senha_hash,
            "role": "gestor",
            "ativo": True,
            "criado_em": now,
        },
    )

    log.info("seed_jmb_concluido", tenant_id=tenant_id, gestor_id=gestor_id)


def downgrade() -> None:
    """Remove tabelas usuarios e tenants (ordem reversa de FK)."""
    op.drop_index("ix_usuarios_cnpj_tenant", table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_table("tenants")
