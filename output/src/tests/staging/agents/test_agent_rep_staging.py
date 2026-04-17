"""Staging smoke tests para AgentRep — Postgres + Redis reais, sem WhatsApp real.

@pytest.mark.staging — requer banco real, não executa no loop automático do Evaluator.

Seed esperado antes de executar:
  - Tenant: id="jmb"
  - Representante: telefone="5519000000001", tenant_id="jmb"
  - Cliente B2B com representante_id vinculado ao rep de teste

Para rodar:
    pytest -m staging -k "test_agent_rep" -v
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from src.agents.types import Mensagem


# ─────────────────────────────────────────────
# Fixtures de staging
# ─────────────────────────────────────────────


TELEFONE_REP_TESTE = "5519000000001"
TENANT_ID_TESTE = "jmb"


@pytest.fixture
def mensagem_rep_staging() -> Mensagem:
    """Mensagem do representante de teste para staging."""
    return Mensagem(
        id="msg-staging-rep-01",
        de=f"{TELEFONE_REP_TESTE}@s.whatsapp.net",
        para="inst-jmb-staging",
        texto="Olá, quero ver os produtos disponíveis",
        tipo="conversation",
        instancia_id="inst-jmb-staging",
        timestamp=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


# ─────────────────────────────────────────────
# A_SMOKE — AgentRep responde sem crash com banco real
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_agent_rep_smoke(mensagem_rep_staging: Mensagem) -> None:
    """A_SMOKE: AgentRep.responder executa com Claude real + banco real sem exceção.

    Verifica:
    - conversa e mensagem persistidas no banco para o rep de teste
    - Nenhuma exceção não tratada
    """
    from src.agents.config import AgentRepConfig
    from src.agents.repo import ClienteB2BRepo, ConversaRepo, RepresentanteRepo
    from src.agents.runtime.agent_rep import AgentRep
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService
    from src.providers.db import get_redis, get_session_factory
    from src.tenants.repo import TenantRepo
    from unittest.mock import AsyncMock, patch

    factory = get_session_factory()
    redis_client = get_redis()

    async with factory() as session:
        # Resolve tenant
        tenant_repo = TenantRepo()
        tenant = await tenant_repo.get_by_id(TENANT_ID_TESTE, session)
        assert tenant is not None, f"Tenant '{TENANT_ID_TESTE}' não encontrado no banco"

        # Resolve representante de teste
        rep_repo = RepresentanteRepo()
        representante = await rep_repo.get_by_telefone(
            TENANT_ID_TESTE, TELEFONE_REP_TESTE, session
        )
        assert representante is not None, (
            f"Representante de teste ({TELEFONE_REP_TESTE}) não encontrado. "
            "Execute scripts/seed_homologacao_sprint-3.py antes."
        )

        # Constrói AgentRep — Evolution API mockada para não enviar WhatsApp real
        agent = AgentRep(
            order_service=OrderService(repo=OrderRepo(), config=OrderConfig()),
            conversa_repo=ConversaRepo(),
            pdf_generator=PDFGenerator(),
            config=AgentRepConfig(),
            representante=representante,
            redis_client=redis_client,
            cliente_b2b_repo=ClienteB2BRepo(),
        )

        # Executa com Claude real — Evolution API mockada
        with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
            with patch("src.agents.runtime.agent_rep.send_whatsapp_media", new=AsyncMock()):
                await agent.responder(mensagem_rep_staging, tenant, session)

        # Verifica persistência no banco
        conversa_repo = ConversaRepo()
        conversa = await conversa_repo.get_or_create_conversa(
            tenant_id=TENANT_ID_TESTE,
            telefone=mensagem_rep_staging.de,
            persona=__import__("src.agents.types", fromlist=["Persona"]).Persona.REPRESENTANTE,
            session=session,
        )
        assert conversa is not None, "Conversa não foi persistida no banco"
        assert conversa.id is not None

        # Busca mensagens persistidas
        historico = await conversa_repo.get_historico(
            conversa_id=conversa.id,
            limit=10,
            session=session,
        )
        assert len(historico) >= 2, (
            f"Esperado ao menos 2 mensagens (user + assistant), encontrado {len(historico)}"
        )
        roles = [m.role for m in historico]
        assert "user" in roles, "Mensagem do usuário não persistida"
        assert "assistant" in roles, "Resposta do assistente não persistida"


# ─────────────────────────────────────────────
# Isolamento de carteira por tenant
# ─────────────────────────────────────────────


@pytest.mark.staging
async def test_agent_rep_isolamento_carteira_por_tenant() -> None:
    """Isolamento: buscar_clientes_carteira retorna apenas clientes do tenant jmb.

    Verifica que um representante do tenant 'jmb' nunca vê clientes de outro tenant.
    """
    from src.agents.repo import ClienteB2BRepo, RepresentanteRepo
    from src.providers.db import get_session_factory

    factory = get_session_factory()

    async with factory() as session:
        rep_repo = RepresentanteRepo()
        representante = await rep_repo.get_by_telefone(
            TENANT_ID_TESTE, TELEFONE_REP_TESTE, session
        )
        assert representante is not None, (
            "Representante de teste não encontrado. "
            "Execute scripts/seed_homologacao_sprint-3.py antes."
        )

        cliente_repo = ClienteB2BRepo()

        # Busca clientes da carteira do rep jmb
        clientes_jmb = await cliente_repo.buscar_por_nome(
            tenant_id=TENANT_ID_TESTE,
            representante_id=representante.id,
            query="",
            session=session,
        )

        # Todos os clientes retornados devem ser do tenant jmb
        for cliente in clientes_jmb:
            assert cliente.tenant_id == TENANT_ID_TESTE, (
                f"Cliente {cliente.id} tem tenant_id={cliente.tenant_id!r}, "
                f"esperado {TENANT_ID_TESTE!r} — violação de isolamento!"
            )
            assert cliente.representante_id == representante.id, (
                f"Cliente {cliente.id} tem representante_id={cliente.representante_id!r}, "
                f"esperado {representante.id!r}"
            )

        # Verifica que busca com tenant errado retorna lista vazia
        clientes_outro_tenant = await cliente_repo.buscar_por_nome(
            tenant_id="outro-tenant-inexistente",
            representante_id=representante.id,
            query="",
            session=session,
        )
        assert len(clientes_outro_tenant) == 0, (
            "buscar_por_nome retornou clientes para tenant inválido — "
            "violação de isolamento cross-tenant!"
        )
