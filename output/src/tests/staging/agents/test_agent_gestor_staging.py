"""Staging smoke tests para AgentGestor — Postgres + Redis reais, sem WhatsApp real.

@pytest.mark.staging — requer banco real, não executa no loop automático do Evaluator.

Seed esperado antes de executar:
  - Tenant: id="jmb"
  - Gestor: telefone="5519000000002", tenant_id="jmb"
  - Pedidos antigos (>=31 dias) para clientes_inativos funcionar

Para rodar:
    pytest -m staging -k "test_agent_gestor" -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.types import Mensagem


TELEFONE_GESTOR_TESTE = "5519000000002"
TENANT_ID_TESTE = "jmb"


@pytest.fixture
def mensagem_gestor_staging() -> Mensagem:
    """Mensagem do gestor de teste para staging."""
    return Mensagem(
        id="msg-staging-gest-01",
        de=f"{TELEFONE_GESTOR_TESTE}@s.whatsapp.net",
        para="inst-jmb-staging",
        texto="quanto vendeu essa semana?",
        tipo="conversation",
        instancia_id="inst-jmb-staging",
        timestamp=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


# ─────────────────────────────────────────────
# S_GESTOR_1 — IdentityRouter identifica gestor com banco real
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_identity_router_gestor_banco_real() -> None:
    """Staging: IdentityRouter identifica Persona.GESTOR para telefone seed com banco real."""
    from src.agents.service import IdentityRouter
    from src.agents.types import Persona
    from src.providers.db import get_session_factory

    mensagem = Mensagem(
        id="msg-staging-ir-gest",
        de=f"{TELEFONE_GESTOR_TESTE}@s.whatsapp.net",
        para="inst-jmb-staging",
        texto="oi",
        tipo="conversation",
        instancia_id="inst-jmb-staging",
        timestamp=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
    )

    factory = get_session_factory()
    router = IdentityRouter()

    async with factory() as session:
        persona = await router.resolve(mensagem, TENANT_ID_TESTE, session)

    assert persona == Persona.GESTOR, (
        f"Esperado Persona.GESTOR para {TELEFONE_GESTOR_TESTE}, "
        f"mas obteve {persona}. Verifique se o seed foi executado."
    )


# ─────────────────────────────────────────────
# S_GESTOR_2 — AgentGestor.responder não crasha com banco real
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_agent_gestor_responde_sem_crash(
    mensagem_gestor_staging: Mensagem,
) -> None:
    """Staging: AgentGestor.responder não levanta exceção com banco real (Claude mockado)."""
    from src.agents.config import AgentGestorConfig
    from src.agents.repo import ClienteB2BRepo, ConversaRepo, GestorRepo, RelatorioRepo
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService
    from src.providers.db import get_session_factory
    from src.tenants.repo import TenantRepo

    factory = get_session_factory()

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Vendas da semana: processando..."

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [mock_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(return_value=mock_response)

    async with factory() as session:
        gestor_repo = GestorRepo()
        gestor = await gestor_repo.get_by_telefone(
            tenant_id=TENANT_ID_TESTE,
            telefone=TELEFONE_GESTOR_TESTE,
            session=session,
        )

        if gestor is None:
            pytest.skip(f"Gestor {TELEFONE_GESTOR_TESTE} não encontrado. Execute o seed primeiro.")

        tenant_repo = TenantRepo()
        tenant = await tenant_repo.get_by_id(TENANT_ID_TESTE, session)

        if tenant is None:
            pytest.skip("Tenant jmb não encontrado no banco.")

        agent = AgentGestor(
            order_service=OrderService(repo=OrderRepo(), config=OrderConfig()),
            conversa_repo=ConversaRepo(),
            pdf_generator=PDFGenerator(),
            config=AgentGestorConfig(),
            gestor=gestor,
            catalog_service=None,
            anthropic_client=mock_anthropic,
            redis_client=None,
            relatorio_repo=RelatorioRepo(),
        )

        with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                mensagem=mensagem_gestor_staging,
                tenant=tenant,
                session=session,
            )
