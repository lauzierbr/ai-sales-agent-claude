"""Repositório do domínio Agents — acesso ao PostgreSQL.

Camada Repo: importa apenas src.agents.types e stdlib.
Toda função pública que acessa dados de tenant filtra por tenant_id.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.types import WhatsappInstancia

log = structlog.get_logger(__name__)


class WhatsappInstanciaRepo:
    """Repositório de instâncias WhatsApp — associa instância ao tenant."""

    async def get_by_instancia_id(
        self, instancia_id: str, session: AsyncSession
    ) -> WhatsappInstancia | None:
        """Busca instância pelo ID da Evolution API.

        Args:
            instancia_id: nome/ID da instância Evolution API.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            WhatsappInstancia se encontrada e ativa, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT instancia_id, tenant_id, numero_whatsapp, ativo
                FROM whatsapp_instancias
                WHERE instancia_id = :instancia_id AND ativo = true
            """),
            {"instancia_id": instancia_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return WhatsappInstancia(
            instancia_id=row["instancia_id"],
            tenant_id=row["tenant_id"],
            numero_whatsapp=row["numero_whatsapp"],
            ativo=row["ativo"],
        )

    async def create(
        self, instancia: WhatsappInstancia, session: AsyncSession
    ) -> WhatsappInstancia:
        """Persiste uma nova instância WhatsApp.

        Args:
            instancia: dados da instância.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            WhatsappInstancia persistida.
        """
        await session.execute(
            text("""
                INSERT INTO whatsapp_instancias (instancia_id, tenant_id, numero_whatsapp, ativo)
                VALUES (:instancia_id, :tenant_id, :numero_whatsapp, :ativo)
                ON CONFLICT (instancia_id) DO UPDATE SET
                    tenant_id       = EXCLUDED.tenant_id,
                    numero_whatsapp = EXCLUDED.numero_whatsapp,
                    ativo           = EXCLUDED.ativo
            """),
            {
                "instancia_id": instancia.instancia_id,
                "tenant_id": instancia.tenant_id,
                "numero_whatsapp": instancia.numero_whatsapp,
                "ativo": instancia.ativo,
            },
        )
        log.info("instancia_criada", instancia_id=instancia.instancia_id, tenant_id=instancia.tenant_id)
        return instancia
