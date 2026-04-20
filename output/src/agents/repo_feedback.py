"""Repositório de feedbacks dos agentes.

Camada Repo: acessa banco via SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

log = structlog.get_logger(__name__)

_SP = ZoneInfo("America/Sao_Paulo")


class FeedbackRepo:
    async def criar(
        self,
        tenant_id: str,
        perfil: str,
        de: str,
        nome: str | None,
        mensagem: str,
        contexto: str,
        session: AsyncSession,
    ) -> str:
        feedback_id = str(uuid.uuid4())
        await session.execute(
            text(
                "INSERT INTO feedbacks (id, tenant_id, perfil, de, nome, mensagem, contexto) "
                "VALUES (:id, :tenant_id, :perfil, :de, :nome, :mensagem, :contexto)"
            ),
            {
                "id": feedback_id,
                "tenant_id": tenant_id,
                "perfil": perfil,
                "de": de,
                "nome": nome,
                "mensagem": mensagem,
                "contexto": contexto,
            },
        )
        await session.commit()
        log.info("feedback_registrado", tenant_id=tenant_id, perfil=perfil, feedback_id=feedback_id)
        return feedback_id

    async def listar(
        self,
        tenant_id: str,
        session: AsyncSession,
        perfil: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params: dict = {"tenant_id": tenant_id, "limit": limit}
        perfil_filter = ""
        if perfil:
            perfil_filter = "AND perfil = :perfil"
            params["perfil"] = perfil

        result = await session.execute(
            text(
                f"SELECT id, perfil, de, nome, mensagem, contexto, criado_em "
                f"FROM feedbacks "
                f"WHERE tenant_id = :tenant_id {perfil_filter} "
                f"ORDER BY criado_em DESC "
                f"LIMIT :limit"
            ),
            params,
        )
        rows = result.mappings().all()
        out = []
        for row in rows:
            d = dict(row)
            if d.get("criado_em") and d["criado_em"].tzinfo is not None:
                d["criado_em"] = d["criado_em"].astimezone(_SP)
            out.append(d)
        return out
