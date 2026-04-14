"""Agente Representante — resposta básica via WhatsApp.

Camada Runtime: pode importar Types, Config, Repo e Service.
Sprint 1: resposta fixa por template. Sprint 3: funcionalidades completas.
"""

from __future__ import annotations

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.service import send_whatsapp_message
from src.agents.types import Mensagem
from src.tenants.types import Tenant

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_TEMPLATE = (
    "Olá! Use este canal para consultar catálogo, "
    "registrar pedidos da sua carteira ou verificar metas."
)

_TEMPLATE_DESCONHECIDO = (
    "Olá! Para atendimento, entre em contato pelo WhatsApp {whatsapp_number}."
)


class AgentRep:
    """Agente de atendimento ao representante via WhatsApp."""

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde mensagem do representante com template fixo.

        Args:
            mensagem: mensagem recebida do representante.
            tenant: dados do tenant.
            session: sessão SQLAlchemy (reservado para Sprint 3).
        """
        with tracer.start_as_current_span("agent_response") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("persona", "representante")
            span.set_attribute("mensagem_len", len(mensagem.texto))

            numero = mensagem.de.split("@")[0]

            log.info(
                "agent_rep_respondendo",
                tenant_id=tenant.id,
                instancia_id=mensagem.instancia_id,
            )

            await send_whatsapp_message(mensagem.instancia_id, numero, _TEMPLATE)


class AgentDesconhecido:
    """Agente de resposta para remetentes não identificados."""

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde remetente desconhecido com mensagem de boas-vindas.

        Args:
            mensagem: mensagem recebida.
            tenant: dados do tenant para personalização.
            session: sessão SQLAlchemy.
        """
        with tracer.start_as_current_span("agent_response") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("persona", "desconhecido")
            span.set_attribute("mensagem_len", len(mensagem.texto))

            whatsapp = tenant.whatsapp_number or "da distribuidora"
            texto = _TEMPLATE_DESCONHECIDO.format(whatsapp_number=whatsapp)
            numero = mensagem.de.split("@")[0]

            log.info(
                "agent_desconhecido_respondendo",
                tenant_id=tenant.id,
                instancia_id=mensagem.instancia_id,
            )

            await send_whatsapp_message(mensagem.instancia_id, numero, texto)
