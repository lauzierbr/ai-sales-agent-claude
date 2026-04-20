"""P2 — Multi-turn Conversation Smoke.

Testa o fluxo completo de uma conversa com múltiplos turnos, onde pelo menos
um turno envolve uma tool call seguida de follow-up. Este é o cenário que
revelou o bug B1 do Sprint 4: `response.content` serializado como string
no Redis → erro 400 na 2ª mensagem.

**Dependências reais:** API Anthropic (para capturar bugs de serialização
que são invisíveis com mocks). Redis e BD são substituídos por implementações
in-memory para isolar o teste.

**Dependências mockadas:** whatsapp (send_message/send_media), ConversaRepo
(BD), PDF, todas as ferramentas de repo (retornam dados de seed).

Uso:
    # Requer ANTHROPIC_API_KEY no ambiente
    infisical run --env=staging -- pytest -m staging -k "multiturn" -v

Ou localmente (sem Infisical):
    ANTHROPIC_API_KEY=sk-ant-... pytest -m staging -k "multiturn" -v
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import AgentClienteConfig, AgentGestorConfig, AgentRepConfig
from src.agents.types import (
    Conversa,
    Gestor,
    Mensagem,
    Persona,
    Representante,
)
from src.tenants.types import Tenant

TENANT_JMB = Tenant(
    id="jmb",
    nome="JMB Distribuidora",
    cnpj="00.000.000/0001-00",
    ativo=True,
    whatsapp_number="5519999990000",
    criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

GESTOR_JMB = Gestor(
    id="gest-01",
    tenant_id="jmb",
    telefone="5519000000002",
    nome="Lauzier",
    ativo=True,
    criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

REP_JMB = Representante(
    id="rep-01",
    tenant_id="jmb",
    usuario_id=None,
    telefone="5519000000099",
    nome="Carlos Rep",
    ativo=True,
)

CONVERSA_MOCK = Conversa(
    id="conv-multiturn-01",
    tenant_id="jmb",
    telefone="5519000000002@s.whatsapp.net",
    persona=Persona.GESTOR,
    iniciada_em=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc),
)


class FakeRedis:
    """Redis em memória: suporta get/set/delete async com TTL ignorado."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def history_for(self, key: str) -> list[dict]:
        """Helper de assert: devolve o histórico parseado do Redis."""
        raw = self._store.get(key)
        if raw is None:
            return []
        return json.loads(raw)


def _make_session_mock() -> MagicMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_conversa_repo_mock() -> AsyncMock:
    from src.agents.repo import ConversaRepo

    repo = AsyncMock(spec=ConversaRepo)
    repo.get_or_create_conversa = AsyncMock(return_value=CONVERSA_MOCK)
    repo.add_mensagem = AsyncMock(return_value=None)
    return repo


def _make_order_repo_mock() -> AsyncMock:
    from src.orders.repo import OrderRepo

    repo = AsyncMock(spec=OrderRepo)
    repo.listar_por_tenant_status = AsyncMock(return_value=[])
    repo.listar_por_representante_status = AsyncMock(return_value=[])
    repo.aprovar_pedido = AsyncMock(return_value=True)
    return repo


def _make_relatorio_repo_mock() -> AsyncMock:
    from src.agents.repo import RelatorioRepo

    repo = AsyncMock(spec=RelatorioRepo)
    repo.totais_periodo = AsyncMock(return_value={"gmv": 0, "n_pedidos": 0})
    repo.totais_por_rep = AsyncMock(return_value=[])
    repo.totais_por_cliente = AsyncMock(return_value=[])
    repo.clientes_inativos = AsyncMock(return_value=[])
    return repo


def _make_cliente_b2b_repo_mock() -> AsyncMock:
    from src.agents.repo import ClienteB2BRepo

    repo = AsyncMock(spec=ClienteB2BRepo)
    repo.buscar_todos_por_nome = AsyncMock(return_value=[])
    repo.buscar_por_nome = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_telefone = AsyncMock(return_value=None)
    return repo


def _make_catalog_service_mock() -> AsyncMock:
    svc = AsyncMock()
    svc.buscar_produtos = AsyncMock(return_value=[])
    return svc


def _make_order_service_mock() -> AsyncMock:
    from src.orders.service import OrderService

    svc = AsyncMock(spec=OrderService)
    return svc


def _assert_redis_history_is_list_of_dicts(
    fake_redis: FakeRedis, redis_key: str
) -> None:
    """Regra B1: histórico Redis deve ser list[dict], nunca list[str].

    Se qualquer content block foi serializado com `json.dumps(..., default=str)`
    ao invés de `[b.model_dump() for b in response.content]`, o content vira
    string. Isso causa erro 400 na próxima chamada à API.
    """
    history = fake_redis.history_for(redis_key)
    assert history, "Histórico Redis está vazio — agente não salvou nada"

    for msg in history:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                assert isinstance(block, dict), (
                    f"Bug B1 regressão: content block deveria ser dict, "
                    f"mas é {type(block).__name__!r}. "
                    f"Bloco: {str(block)[:200]}"
                )


@pytest.mark.staging
async def test_gestor_multiturn_tool_call_then_followup() -> None:
    """Gestor: listar pedidos (tool call) → follow-up → sem erro 400.

    Verifica:
    1. Resposta 1: bot processa e retorna texto.
    2. Resposta 2: follow-up usando o histórico — sem exception, sem erro 400.
    3. Redis: content blocks são list[dict], não list[str] (regressão B1).
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY não disponível — skip em CI")

    import anthropic

    fake_redis = FakeRedis()
    session = _make_session_mock()
    conversa_repo = _make_conversa_repo_mock()
    order_repo = _make_order_repo_mock()
    relatorio_repo = _make_relatorio_repo_mock()
    cliente_b2b_repo = _make_cliente_b2b_repo_mock()
    catalog_svc = _make_catalog_service_mock()
    order_svc = _make_order_service_mock()
    pdf_gen = MagicMock()

    from src.agents.runtime.agent_gestor import AgentGestor

    agent = AgentGestor(
        order_service=order_svc,
        conversa_repo=conversa_repo,
        pdf_generator=pdf_gen,
        config=AgentGestorConfig(),
        gestor=GESTOR_JMB,
        catalog_service=catalog_svc,
        anthropic_client=anthropic.AsyncAnthropic(),
        redis_client=fake_redis,
        cliente_b2b_repo=cliente_b2b_repo,
        relatorio_repo=relatorio_repo,
        order_repo=order_repo,
    )

    redis_key = f"hist:gestor:{TENANT_JMB.id}:5519000000002"

    with (
        patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
    ):
        # Turno 1: pergunta que aciona tool (listar_pedidos_por_status)
        msg1 = Mensagem(
            id="mt-g-01",
            de="5519000000002@s.whatsapp.net",
            para="inst-jmb-01",
            texto="quais pedidos estão pendentes?",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg1, TENANT_JMB, session)

        history_after_t1 = fake_redis.history_for(redis_key)
        assert history_after_t1, "Histórico vazio após turno 1"

        # Turno 2: follow-up — usa histórico salvo no Redis
        msg2 = Mensagem(
            id="mt-g-02",
            de="5519000000002@s.whatsapp.net",
            para="inst-jmb-01",
            texto="e os confirmados nos últimos 60 dias?",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 1, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg2, TENANT_JMB, session)

        history_after_t2 = fake_redis.history_for(redis_key)
        assert len(history_after_t2) > len(history_after_t1), (
            "Turno 2 não adicionou ao histórico Redis"
        )

        # Verificação B1: conteúdo deve ser list[dict], nunca list[str]
        _assert_redis_history_is_list_of_dicts(fake_redis, redis_key)


@pytest.mark.staging
async def test_rep_multiturn_lista_pedidos_then_aprova() -> None:
    """Rep: listar pedidos carteira → aprovar → sem erro 400.

    Verifica que o histórico multi-turn do Rep também serializa
    content blocks como list[dict] (regressão B1).
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY não disponível — skip em CI")

    import anthropic

    from src.agents.runtime.agent_rep import AgentRep

    fake_redis = FakeRedis()
    session = _make_session_mock()
    conversa_repo = _make_conversa_repo_mock()
    order_repo = _make_order_repo_mock()
    cliente_b2b_repo = _make_cliente_b2b_repo_mock()
    catalog_svc = _make_catalog_service_mock()
    order_svc = _make_order_service_mock()
    pdf_gen = MagicMock()

    agent = AgentRep(
        order_service=order_svc,
        conversa_repo=conversa_repo,
        pdf_generator=pdf_gen,
        config=AgentRepConfig(),
        representante=REP_JMB,
        catalog_service=catalog_svc,
        anthropic_client=anthropic.AsyncAnthropic(),
        redis_client=fake_redis,
        cliente_b2b_repo=cliente_b2b_repo,
        order_repo=order_repo,
    )

    redis_key = f"hist:rep:{TENANT_JMB.id}:5519000000099"

    with (
        patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()),
        patch("src.agents.runtime.agent_rep.send_whatsapp_media", new=AsyncMock()),
    ):
        msg1 = Mensagem(
            id="mt-r-01",
            de="5519000000099@s.whatsapp.net",
            para="inst-jmb-01",
            texto="quais pedidos da minha carteira estão pendentes?",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg1, TENANT_JMB, session)

        msg2 = Mensagem(
            id="mt-r-02",
            de="5519000000099@s.whatsapp.net",
            para="inst-jmb-01",
            texto="me mostra também os confirmados essa semana",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 2, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg2, TENANT_JMB, session)

        _assert_redis_history_is_list_of_dicts(fake_redis, redis_key)


@pytest.mark.staging
async def test_cliente_multiturn_lista_then_followup() -> None:
    """Cliente: listar pedidos → follow-up → sem erro 400.

    Verifica o agente cliente (persona com tool listar_meus_pedidos).
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY não disponível — skip em CI")

    import anthropic

    from src.agents.runtime.agent_cliente import AgentCliente

    fake_redis = FakeRedis()
    session = _make_session_mock()
    conversa_repo = _make_conversa_repo_mock()
    order_repo = _make_order_repo_mock()
    catalog_svc = _make_catalog_service_mock()
    order_svc = _make_order_service_mock()
    pdf_gen = MagicMock()

    agent = AgentCliente(
        order_service=order_svc,
        conversa_repo=conversa_repo,
        pdf_generator=pdf_gen,
        config=AgentClienteConfig(),
        catalog_service=catalog_svc,
        anthropic_client=anthropic.AsyncAnthropic(),
        redis_client=fake_redis,
        order_repo=order_repo,
    )

    redis_key = f"hist:cliente:{TENANT_JMB.id}:5519000000111"

    with (
        patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()),
        patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()),
    ):
        msg1 = Mensagem(
            id="mt-c-01",
            de="5519000000111@s.whatsapp.net",
            para="inst-jmb-01",
            texto="quais são meus pedidos?",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg1, TENANT_JMB, session,
                              cliente_b2b_id="cli-mt-01", representante_id="rep-01")

        msg2 = Mensagem(
            id="mt-c-02",
            de="5519000000111@s.whatsapp.net",
            para="inst-jmb-01",
            texto="e os pedidos cancelados?",
            tipo="conversation",
            instancia_id="inst-jmb-01",
            timestamp=datetime(2026, 4, 20, 10, 3, 0, tzinfo=timezone.utc),
        )
        await agent.responder(msg2, TENANT_JMB, session,
                              cliente_b2b_id="cli-mt-01", representante_id="rep-01")

        _assert_redis_history_is_list_of_dicts(fake_redis, redis_key)
