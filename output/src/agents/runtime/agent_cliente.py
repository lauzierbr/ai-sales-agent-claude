"""Agente Cliente B2B — resposta básica via WhatsApp.

Camada Runtime: pode importar Types, Config, Repo e Service.
Sprint 1: resposta fixa por template. Sprint 2: Claude SDK completo.
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
    "Olá! Sou o assistente da {tenant_nome}. "
    "Como posso ajudar? Consulte produtos, verifique pedidos "
    "ou fale com um atendente."
)


class AgentCliente:
    """Agente de atendimento ao cliente B2B via WhatsApp."""

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde mensagem do cliente com template fixo.

        Args:
            mensagem: mensagem recebida do cliente.
            tenant: dados do tenant para personalização.
            session: sessão SQLAlchemy (reservado para Sprint 2).
        """
        with tracer.start_as_current_span("agent_response") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("persona", "cliente_b2b")
            span.set_attribute("mensagem_len", len(mensagem.texto))

            texto = _TEMPLATE.format(tenant_nome=tenant.nome)
            numero = mensagem.de.split("@")[0]  # strip WhatsApp suffix

            log.info(
                "agent_cliente_respondendo",
                tenant_id=tenant.id,
                instancia_id=mensagem.instancia_id,
            )

            await send_whatsapp_message(mensagem.instancia_id, numero, texto)
