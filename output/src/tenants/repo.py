"""Repositório do domínio Tenants — acesso ao PostgreSQL.

Camada Repo: importa apenas src.tenants.types e stdlib.
Toda função pública recebe tenant_id (onde aplicável) como parâmetro obrigatório.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.tenants.types import Role, Tenant, Usuario

log = structlog.get_logger(__name__)


class TenantRepo:
    """Repositório de tenants — operações CRUD sobre a tabela `tenants`."""

    async def get_by_id(self, tenant_id: str, session: AsyncSession) -> Tenant | None:
        """Busca tenant pelo ID.

        Args:
            tenant_id: identificador do tenant.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Tenant se encontrado, None caso contrário.
        """
        result = await session.execute(
            text("SELECT id, nome, cnpj, ativo, whatsapp_number, config_json, criado_em "
                 "FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return Tenant(
            id=row["id"],
            nome=row["nome"],
            cnpj=row["cnpj"],
            ativo=row["ativo"],
            whatsapp_number=row["whatsapp_number"],
            config_json=json.loads(row["config_json"] or "{}"),
            criado_em=row["criado_em"],
        )

    async def get_active_tenants(self, session: AsyncSession) -> list[Tenant]:
        """Retorna todos os tenants ativos.

        Args:
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de Tenant ativos ordenados por nome.
        """
        result = await session.execute(
            text("SELECT id, nome, cnpj, ativo, whatsapp_number, config_json, criado_em "
                 "FROM tenants WHERE ativo = true ORDER BY nome"),
        )
        rows = result.mappings().all()
        return [
            Tenant(
                id=r["id"],
                nome=r["nome"],
                cnpj=r["cnpj"],
                ativo=r["ativo"],
                whatsapp_number=r["whatsapp_number"],
                config_json=json.loads(r["config_json"] or "{}"),
                criado_em=r["criado_em"],
            )
            for r in rows
        ]

    async def create(self, tenant: Tenant, session: AsyncSession) -> Tenant:
        """Persiste um novo tenant.

        Args:
            tenant: dados do tenant a criar.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Tenant persistido.
        """
        await session.execute(
            text("""
                INSERT INTO tenants (id, nome, cnpj, ativo, whatsapp_number, config_json, criado_em)
                VALUES (:id, :nome, :cnpj, :ativo, :whatsapp_number, :config_json::jsonb, :criado_em)
            """),
            {
                "id": tenant.id,
                "nome": tenant.nome,
                "cnpj": tenant.cnpj,
                "ativo": tenant.ativo,
                "whatsapp_number": tenant.whatsapp_number,
                "config_json": "{}",
                "criado_em": tenant.criado_em,
            },
        )
        log.info("tenant_criado", tenant_id=tenant.id, nome=tenant.nome)
        return tenant


class UsuarioRepo:
    """Repositório de usuários — operações CRUD sobre a tabela `usuarios`."""

    async def get_by_cnpj(
        self, cnpj: str, tenant_id: str, session: AsyncSession
    ) -> Usuario | None:
        """Busca usuário por CNPJ dentro de um tenant específico.

        Args:
            cnpj: CNPJ do usuário.
            tenant_id: identificador do tenant — isolamento obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Usuario se encontrado, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, cnpj, senha_hash, role, ativo, criado_em
                FROM usuarios
                WHERE cnpj = :cnpj AND tenant_id = :tenant_id AND ativo = true
            """),
            {"cnpj": cnpj, "tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return Usuario(
            id=row["id"],
            tenant_id=row["tenant_id"],
            cnpj=row["cnpj"],
            senha_hash=row["senha_hash"],
            role=Role(row["role"]),
            ativo=row["ativo"],
            criado_em=row["criado_em"],
        )

    async def get_by_cnpj_global(
        self, cnpj: str, session: AsyncSession
    ) -> Usuario | None:
        """Busca usuário por CNPJ sem filtro de tenant — EXCLUSIVO para login.

        Uso restrito: apenas POST /auth/login, onde o tenant_id é desconhecido.
        CNPJs de gestores são únicos no Brasil (CNPJ empresarial). Em Sprint 2+,
        adicionar seletor de tenant para representantes com CPF repetido.

        Args:
            cnpj: CNPJ do usuário.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Primeiro Usuario ativo com este CNPJ, ou None.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, cnpj, senha_hash, role, ativo, criado_em
                FROM usuarios
                WHERE cnpj = :cnpj AND ativo = true
                LIMIT 1
            """),
            {"cnpj": cnpj},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return Usuario(
            id=row["id"],
            tenant_id=row["tenant_id"],
            cnpj=row["cnpj"],
            senha_hash=row["senha_hash"],
            role=Role(row["role"]),
            ativo=row["ativo"],
            criado_em=row["criado_em"],
        )

    async def create(self, usuario: Usuario, session: AsyncSession) -> Usuario:
        """Persiste um novo usuário.

        Args:
            usuario: dados do usuário a criar.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Usuario persistido.
        """
        await session.execute(
            text("""
                INSERT INTO usuarios (id, tenant_id, cnpj, senha_hash, role, ativo, criado_em)
                VALUES (:id, :tenant_id, :cnpj, :senha_hash, :role, :ativo, :criado_em)
            """),
            {
                "id": usuario.id,
                "tenant_id": usuario.tenant_id,
                "cnpj": usuario.cnpj,
                "senha_hash": usuario.senha_hash,
                "role": usuario.role.value,
                "ativo": usuario.ativo,
                "criado_em": usuario.criado_em,
            },
        )
        log.info("usuario_criado", usuario_id=usuario.id, tenant_id=usuario.tenant_id)
        return usuario
