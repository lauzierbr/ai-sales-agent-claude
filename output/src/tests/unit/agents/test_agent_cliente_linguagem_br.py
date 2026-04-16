"""Suite de testes de linguagem coloquial brasileira — AgentCliente (Sprint 3).

Todos os testes são @pytest.mark.unit — sem I/O externo.

Grupos:
  A01–A06: Consultas informais → buscar_produtos chamado
  B01–B04: Saudações → sem ferramenta chamada (end_turn)
  C01–C04: Pedidos diretos → buscar_produtos + confirmar_pedido em sequência
  D01–D07: Confirmações coloquiais → confirmar_pedido acionado
  E01–E05: Cancelamentos → confirmar_pedido NÃO chamado
  F01–F02: Multi-produto em uma mensagem
  G01–G02: Quantidade ausente → agente pede esclarecimento
  H01–H04: Regressão Sprint 2

Estratégia: cada teste injeta mock do Anthropic que simula a resposta
que Claude daria com o system_prompt expandido. O teste verifica o
COMPORTAMENTO DO AGENTE (ferramentas chamadas, whatsapp enviado),
não o texto gerado pelo Claude.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import AgentClienteConfig
from src.agents.repo import ConversaRepo
from src.agents.runtime.agent_cliente import AgentCliente
from src.agents.types import Conversa, Mensagem, Persona
from src.orders.runtime.pdf_generator import PDFGenerator
from src.orders.service import OrderService
from src.orders.types import ItemPedido, Pedido, StatusPedido
from src.tenants.types import Tenant


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def tenant_jmb() -> Tenant:
    return Tenant(
        id="jmb",
        nome="JMB Distribuidora",
        cnpj="00.000.000/0001-00",
        ativo=True,
        whatsapp_number="5519999990000",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def conversa_fixture() -> Conversa:
    return Conversa(
        id="conv-001",
        tenant_id="jmb",
        telefone="5519999999999",
        persona=Persona.CLIENTE_B2B,
        iniciada_em=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def pedido_fixture() -> Pedido:
    return Pedido(
        id="ped-abc12345",
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id=None,
        status=StatusPedido.PENDENTE,
        total_estimado=Decimal("299.00"),
        pdf_path=None,
        criado_em=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        itens=[
            ItemPedido(
                id="item-001",
                pedido_id="ped-abc12345",
                produto_id="prod-001",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=10,
                preco_unitario=Decimal("29.90"),
                subtotal=Decimal("299.00"),
            )
        ],
    )


# ─────────────────────────────────────────────
# Helpers de construção de mocks
# ─────────────────────────────────────────────


def _make_end_turn(text: str = "Posso ajudar você!") -> MagicMock:
    """Mock de resposta anthropic com stop_reason=end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _make_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_id: str = "tool_abc",
) -> MagicMock:
    """Mock de resposta anthropic com stop_reason=tool_use."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.id = tool_id
    block.input = tool_input

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


def _make_agent(
    anthropic_responses: list[MagicMock],
    conversa_fixture: Conversa,
    pedido_fixture: Pedido | None = None,
    redis_history: list[dict[str, Any]] | None = None,
) -> tuple[AgentCliente, AsyncMock, MagicMock, AsyncMock]:
    """Cria AgentCliente com dependências mockadas.

    Args:
        anthropic_responses: sequência de respostas do mock Anthropic.
        conversa_fixture: conversa mockada.
        pedido_fixture: pedido mockado (para testes de confirmação).
        redis_history: histórico pré-populado no Redis (simula contexto anterior).

    Returns:
        Tupla (agent, mock_order_service, mock_anthropic, mock_redis).
    """
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    mock_order_service = AsyncMock(spec=OrderService)
    if pedido_fixture:
        mock_order_service.criar_pedido_from_intent = AsyncMock(return_value=pedido_fixture)

    mock_pdf = MagicMock(spec=PDFGenerator)
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"PDF_BYTES_FAKE" * 100)

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=anthropic_responses)

    # Redis mockado com histórico opcional
    mock_redis = AsyncMock()
    if redis_history is not None:
        mock_redis.get = AsyncMock(
            return_value=json.dumps(redis_history, ensure_ascii=False).encode()
        )
    else:
        mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    config = AgentClienteConfig()

    agent = AgentCliente(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=config,
        catalog_service=None,  # não testado aqui
        anthropic_client=mock_anthropic,
        redis_client=mock_redis,
    )

    return agent, mock_order_service, mock_anthropic, mock_redis


def _make_mensagem(texto: str, numero: str = "5519999999999") -> Mensagem:
    """Cria mensagem de cliente com texto fornecido."""
    return Mensagem(
        id="msg-test",
        de=f"{numero}@s.whatsapp.net",
        para="inst-jmb-01",
        texto=texto,
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


def _make_historico_com_produto() -> list[dict[str, Any]]:
    """Simula histórico Redis com produtos apresentados (contexto para confirmações)."""
    return [
        {"role": "user", "content": "quero ver shampoo"},
        {
            "role": "assistant",
            "content": (
                "Encontrei: Shampoo 300ml (SKU001) R$ 29,90 — produto_id: prod-001. "
                "Quantas unidades deseja?"
            ),
        },
        {"role": "user", "content": "10 unidades"},
        {
            "role": "assistant",
            "content": (
                "Perfeito! 10x Shampoo 300ml = R$ 299,00. Confirma o pedido?"
            ),
        },
    ]


def _make_confirmar_pedido_tool_use() -> MagicMock:
    """Mock de tool_use para confirmar_pedido com itens pré-definidos."""
    return _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-001",
                    "codigo_externo": "SKU001",
                    "nome_produto": "Shampoo 300ml",
                    "quantidade": 10,
                    "preco_unitario": "29.90",
                }
            ],
        },
        tool_id="tool_confirmar",
    )


# ─────────────────────────────────────────────
# Grupo A: Consultas informais → buscar_produtos chamado
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_a_a01_consulta_shampoo(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A01: 'oi, tem shampoo?' → buscar_produtos(query='shampoo') chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "shampoo", "limit": 5}, "tool_a01")
    end = _make_end_turn("Aqui estão os shampoos disponíveis!")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("oi, tem shampoo?"), tenant_jmb, session)

    # Verifica que anthropic foi chamado com tool buscar_produtos
    assert mock_anthropic.messages.create.call_count == 2
    # OrderService não chamado
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_a_a02_preco_heineken(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A02: 'manda o preço da heineken' → buscar_produtos(query='heineken') chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "heineken", "limit": 5}, "tool_a02")
    end = _make_end_turn("Heineken Long Neck R$ 4,50 cada.")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("manda o preço da heineken"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 2
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_a_a03_valor_nescau(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A03: 'qual o valor do nescau?' → buscar_produtos(query='nescau') chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "nescau", "limit": 5}, "tool_a03")
    end = _make_end_turn("Nescau 400g R$ 8,90.")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("qual o valor do nescau?"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 2
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_a_a04_higiene(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A04: 'tem alguma coisa de higiene?' → buscar_produtos(query='higiene') chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "higiene", "limit": 5}, "tool_a04")
    end = _make_end_turn("Produtos de higiene disponíveis:")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("tem alguma coisa de higiene?"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 2
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_a_a05_typo_condicionadro(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A05: 'me mostra condicionadro' (typo) → buscar_produtos chamado (query não vazia)."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "condicionadro", "limit": 5}, "tool_a05"
    )
    end = _make_end_turn("Condicionador disponível:")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(
            _make_mensagem("me mostra condicionadro"), tenant_jmb, session
        )

    assert mock_anthropic.messages.create.call_count == 2
    # Query não vazia
    first_tool_call = mock_anthropic.messages.create.call_args_list[0]
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_a_a06_catalogo_bebe(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """A06: 'quero ver o catálogo de bebê' → buscar_produtos(query contém 'bebê')."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "bebê", "limit": 5}, "tool_a06"
    )
    end = _make_end_turn("Produtos para bebê:")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(
            _make_mensagem("quero ver o catálogo de bebê"), tenant_jmb, session
        )

    assert mock_anthropic.messages.create.call_count == 2
    assert not mock_order.criar_pedido_from_intent.called


# ─────────────────────────────────────────────
# Grupo B: Saudações → sem ferramenta chamada
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_b_b01_oi(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """B01: 'oi' → end_turn (nenhuma tool chamada)."""
    end = _make_end_turn("Olá! Como posso ajudar?")

    agent, mock_order, mock_anthropic, _ = _make_agent([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("oi"), tenant_jmb, session)

    # Apenas 1 chamada ao anthropic (end_turn direto)
    assert mock_anthropic.messages.create.call_count == 1
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_b_b02_bom_dia(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """B02: 'bom dia' → end_turn, nenhuma tool chamada."""
    end = _make_end_turn("Bom dia! Em que posso ajudar?")

    agent, mock_order, mock_anthropic, _ = _make_agent([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("bom dia"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 1
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_b_b03_boa_tarde(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """B03: 'boa tarde, tudo bem?' → end_turn, nenhuma tool chamada."""
    end = _make_end_turn("Boa tarde! Tudo bem sim, obrigado!")

    agent, mock_order, mock_anthropic, _ = _make_agent([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("boa tarde, tudo bem?"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 1
    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_b_b04_ola_posso_fazer_pedido(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """B04: 'olá posso fazer um pedido?' → end_turn orientando sem buscar_produtos."""
    end = _make_end_turn(
        "Olá! Claro, pode fazer um pedido. Qual produto você precisa?"
    )

    agent, mock_order, mock_anthropic, _ = _make_agent([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(
            _make_mensagem("olá posso fazer um pedido?"), tenant_jmb, session
        )

    assert mock_anthropic.messages.create.call_count == 1
    assert not mock_order.criar_pedido_from_intent.called


# ─────────────────────────────────────────────
# Grupo C: Pedidos diretos → buscar + confirmar em sequência
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_c_c01_pedido_direto_shampoo(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """C01: 'manda 10 shampoo 300ml' → buscar_produtos + confirmar_pedido → OrderService chamado 1x."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "shampoo 300ml", "limit": 5}, "tool_c01_busca"
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-001",
                    "codigo_externo": "SKU001",
                    "nome_produto": "Shampoo 300ml",
                    "quantidade": 10,
                    "preco_unitario": "29.90",
                }
            ]
        },
        "tool_c01_confirma",
    )
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order, mock_anthropic, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("manda 10 shampoo 300ml"), tenant_jmb, session
            )

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_c_c02_pedido_heineken_caixa(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """C02: 'quero 2 cx de heineken long neck' → buscar_produtos chamado, depois confirmar_pedido."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "heineken long neck", "limit": 5}, "tool_c02_busca"
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-hein",
                    "codigo_externo": "HEIN600",
                    "nome_produto": "Heineken Long Neck",
                    "quantidade": 2,
                    "preco_unitario": "4.50",
                }
            ]
        },
        "tool_c02_confirma",
    )
    end = _make_end_turn("Pedido de 2 cx Heineken confirmado!")

    agent, mock_order, mock_anthropic, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("quero 2 cx de heineken long neck"), tenant_jmb, session
            )

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_c_c03_fecha_multiitem(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """C03: 'fecha aí, 3 de shampoo e 2 de condicionador' → confirmar_pedido com 2 itens."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "shampoo condicionador", "limit": 5}, "tool_c03_busca"
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-001",
                    "codigo_externo": "SKU001",
                    "nome_produto": "Shampoo 300ml",
                    "quantidade": 3,
                    "preco_unitario": "29.90",
                },
                {
                    "produto_id": "prod-002",
                    "codigo_externo": "SKU002",
                    "nome_produto": "Condicionador 300ml",
                    "quantidade": 2,
                    "preco_unitario": "29.90",
                },
            ]
        },
        "tool_c03_confirma",
    )
    end = _make_end_turn("Pedido com 2 itens confirmado!")

    agent, mock_order, mock_anthropic, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("fecha aí, 3 de shampoo e 2 de condicionador"),
                tenant_jmb,
                session,
            )

    mock_order.criar_pedido_from_intent.assert_called_once()
    # Verifica que pelo menos 2 itens foram enviados ao OrderService
    call_kwargs = mock_order.criar_pedido_from_intent.call_args[1]
    assert len(call_kwargs["pedido_input"].itens) >= 2


@pytest.mark.unit
async def test_grupo_c_c04_me_manda_multiitem(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """C04: 'me manda: 10 heineken 600ml e 5 skol' → confirmar_pedido com >= 2 itens."""
    busca = _make_tool_use(
        "buscar_produtos",
        {"query": "heineken 600ml skol", "limit": 5},
        "tool_c04_busca",
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-hein",
                    "codigo_externo": "HEIN600",
                    "nome_produto": "Heineken 600ml",
                    "quantidade": 10,
                    "preco_unitario": "7.00",
                },
                {
                    "produto_id": "prod-skol",
                    "codigo_externo": "SKOL350",
                    "nome_produto": "Skol 350ml",
                    "quantidade": 5,
                    "preco_unitario": "3.00",
                },
            ]
        },
        "tool_c04_confirma",
    )
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order, mock_anthropic, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("me manda: 10 heineken 600ml e 5 skol"),
                tenant_jmb,
                session,
            )

    mock_order.criar_pedido_from_intent.assert_called_once()
    call_kwargs = mock_order.criar_pedido_from_intent.call_args[1]
    assert len(call_kwargs["pedido_input"].itens) >= 2


# ─────────────────────────────────────────────
# Helpers para grupos D e E
# ─────────────────────────────────────────────


def _make_agent_with_redis_history(
    anthropic_responses: list[MagicMock],
    conversa_fixture: Conversa,
    pedido_fixture: Pedido | None = None,
) -> tuple[AgentCliente, AsyncMock]:
    """Cria AgentCliente com histórico Redis pré-populado (produtos já apresentados).

    Args:
        anthropic_responses: sequência de respostas mock do Anthropic.
        conversa_fixture: conversa mockada.
        pedido_fixture: pedido para testes de confirmação.

    Returns:
        Tupla (agent, mock_order_service).
    """
    agent, mock_order, _, _ = _make_agent(
        anthropic_responses,
        conversa_fixture,
        pedido_fixture=pedido_fixture,
        redis_history=_make_historico_com_produto(),
    )
    return agent, mock_order


# ─────────────────────────────────────────────
# Grupo D: Confirmações coloquiais → confirmar_pedido acionado (D01–D07)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_d_d01_pode_mandar(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D01: 'pode mandar' → Claude retorna confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("pode mandar"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d02_vai_la(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D02: 'vai lá' → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("vai lá"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d03_fecha(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D03: 'fecha!' → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("fecha!"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d04_beleza_pode_ir(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D04: 'beleza, pode ir' → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("beleza, pode ir"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d05_FECHA_maiusculas(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D05: 'FECHA' (maiúsculas) → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("FECHA"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d06_sim_confirmo(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D06: 'sim confirmo' → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(_make_mensagem("sim confirmo"), tenant_jmb, session)

    mock_order.criar_pedido_from_intent.assert_called_once()


@pytest.mark.unit
async def test_grupo_d_d07_to_dentro_manda_tudo(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """D07: 'tô dentro, manda tudo' → confirmar_pedido → OrderService chamado 1x."""
    confirma = _make_confirmar_pedido_tool_use()
    end = _make_end_turn("Pedido confirmado!")

    agent, mock_order = _make_agent_with_redis_history(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("tô dentro, manda tudo"), tenant_jmb, session
            )

    mock_order.criar_pedido_from_intent.assert_called_once()


# ─────────────────────────────────────────────
# Grupo E: Cancelamentos → confirmar_pedido NÃO chamado (E01–E05)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_e_e01_nao_deixa(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """E01: 'não, deixa' → end_turn sem confirmar_pedido; OrderService não chamado."""
    end = _make_end_turn("Tudo bem! Posso ajudar com mais alguma coisa?")

    agent, mock_order = _make_agent_with_redis_history([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("não, deixa"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called, (
        "OrderService foi chamado após cancelamento 'não, deixa'"
    )


@pytest.mark.unit
async def test_grupo_e_e02_cancela(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """E02: 'cancela' → end_turn; OrderService não chamado."""
    end = _make_end_turn("Pedido cancelado. Posso ajudar com mais alguma coisa?")

    agent, mock_order = _make_agent_with_redis_history([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("cancela"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_e_e03_esquece(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """E03: 'esquece' → end_turn; OrderService não chamado."""
    end = _make_end_turn("Ok, esquecido. Em que mais posso ajudar?")

    agent, mock_order = _make_agent_with_redis_history([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("esquece"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_e_e04_perai_ver_chefe(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """E04: 'peraí vou ver com o chefe' → end_turn; OrderService não chamado."""
    end = _make_end_turn("Claro, pode consultar! Estarei aqui quando quiser confirmar.")

    agent, mock_order = _make_agent_with_redis_history([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(
            _make_mensagem("peraí vou ver com o chefe"), tenant_jmb, session
        )

    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_e_e05_nao_quero_mais(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """E05: 'não quero mais' → end_turn; OrderService não chamado."""
    end = _make_end_turn("Entendido! Quando quiser, é só falar.")

    agent, mock_order = _make_agent_with_redis_history([end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("não quero mais"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called


# ─────────────────────────────────────────────
# Grupo F: Multi-produto em uma mensagem
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_f_f01_multi_produto_dois_itens(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """F01: 'quero 3 shampoo e 2 condicionador' → confirmar_pedido com 2 itens distintos."""
    busca = _make_tool_use(
        "buscar_produtos", {"query": "shampoo condicionador", "limit": 5}, "tool_f01"
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-001",
                    "codigo_externo": "SKU001",
                    "nome_produto": "Shampoo 300ml",
                    "quantidade": 3,
                    "preco_unitario": "29.90",
                },
                {
                    "produto_id": "prod-002",
                    "codigo_externo": "SKU002",
                    "nome_produto": "Condicionador 300ml",
                    "quantidade": 2,
                    "preco_unitario": "29.90",
                },
            ]
        },
        "tool_f01_confirma",
    )
    end = _make_end_turn("Pedido com 2 itens confirmado!")

    agent, mock_order, _, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("quero 3 shampoo e 2 condicionador"), tenant_jmb, session
            )

    mock_order.criar_pedido_from_intent.assert_called_once()
    call_kwargs = mock_order.criar_pedido_from_intent.call_args[1]
    assert len(call_kwargs["pedido_input"].itens) >= 2


@pytest.mark.unit
async def test_grupo_f_f02_tres_bebidas(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """F02: 'me manda: 10 heineken, 5 skol, 3 brahma' → confirmar_pedido com 3 itens."""
    busca = _make_tool_use(
        "buscar_produtos",
        {"query": "heineken skol brahma", "limit": 10},
        "tool_f02_busca",
    )
    confirma = _make_tool_use(
        "confirmar_pedido",
        {
            "itens": [
                {
                    "produto_id": "prod-hein",
                    "codigo_externo": "HEIN",
                    "nome_produto": "Heineken",
                    "quantidade": 10,
                    "preco_unitario": "4.50",
                },
                {
                    "produto_id": "prod-skol",
                    "codigo_externo": "SKOL",
                    "nome_produto": "Skol",
                    "quantidade": 5,
                    "preco_unitario": "3.00",
                },
                {
                    "produto_id": "prod-brah",
                    "codigo_externo": "BRAH",
                    "nome_produto": "Brahma",
                    "quantidade": 3,
                    "preco_unitario": "3.20",
                },
            ]
        },
        "tool_f02_confirma",
    )
    end = _make_end_turn("Pedido com 3 itens confirmado!")

    agent, mock_order, _, _ = _make_agent(
        [busca, confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("me manda: 10 heineken, 5 skol, 3 brahma"),
                tenant_jmb,
                session,
            )

    mock_order.criar_pedido_from_intent.assert_called_once()
    call_kwargs = mock_order.criar_pedido_from_intent.call_args[1]
    assert len(call_kwargs["pedido_input"].itens) >= 3


# ─────────────────────────────────────────────
# Grupo G: Quantidade ausente → agente pede esclarecimento
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_g_g01_sem_quantidade(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """G01: 'quero shampoo' (sem quantidade) → end_turn perguntando quantidade; OrderService NÃO chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "shampoo", "limit": 5}, "tool_g01")
    end = _make_end_turn("Encontrei o Shampoo 300ml. Quantas unidades deseja?")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("quero shampoo"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called


@pytest.mark.unit
async def test_grupo_g_g02_tem_nescau_quero(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """G02: 'tem nescau? quero' (sem quantidade) → end_turn perguntando quantidade; OrderService NÃO chamado."""
    busca = _make_tool_use("buscar_produtos", {"query": "nescau", "limit": 5}, "tool_g02")
    end = _make_end_turn("Temos Nescau 400g! Quantas unidades deseja?")

    agent, mock_order, mock_anthropic, _ = _make_agent([busca, end], conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("tem nescau? quero"), tenant_jmb, session)

    assert not mock_order.criar_pedido_from_intent.called


# ─────────────────────────────────────────────
# Grupo H: Regressão Sprint 2
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_grupo_h_h01_confirmar_pedido_cadeia_completa(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """H01: regressão — confirmar_pedido chama OrderService + PDFGenerator + send_whatsapp_media."""
    tool_input = {
        "itens": [
            {
                "produto_id": "prod-001",
                "codigo_externo": "SKU001",
                "nome_produto": "Shampoo 300ml",
                "quantidade": 10,
                "preco_unitario": "29.90",
            }
        ],
    }
    confirma = _make_tool_use("confirmar_pedido", tool_input, "tool_h01")
    end = _make_end_turn("Pedido PED-PED-ABC123 confirmado!")

    agent, mock_order, _, _ = _make_agent(
        [confirma, end], conversa_fixture, pedido_fixture=pedido_fixture
    )
    # Acessa pdf diretamente
    mock_pdf = agent._pdf_generator

    media_calls: list[dict[str, Any]] = []

    async def mock_send_media(
        instancia_id: str, numero: str, pdf_bytes: bytes, caption: str, file_name: str
    ) -> None:
        media_calls.append({"numero": numero, "pdf_bytes": pdf_bytes})

    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=mock_send_media):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                _make_mensagem("Quero ver o catálogo de shampoo"),
                tenant_jmb,
                session,
                cliente_b2b_id="cli-001",
            )

    assert mock_order.criar_pedido_from_intent.called
    assert mock_pdf.gerar_pdf_pedido.called
    assert len(media_calls) >= 1
    assert media_calls[0]["numero"] == tenant_jmb.whatsapp_number


@pytest.mark.unit
async def test_grupo_h_h02_max_iterations_nao_loop_infinito(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """H02: regressão — max_iterations ainda funciona com system_prompt expandido."""
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    tool_response = _make_tool_use("buscar_produtos", {"query": "teste", "limit": 5})
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=tool_response)

    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    config = AgentClienteConfig()
    config.max_iterations = 5

    agent = AgentCliente(
        order_service=AsyncMock(spec=OrderService),
        conversa_repo=mock_conversa_repo,
        pdf_generator=MagicMock(spec=PDFGenerator),
        config=config,
        anthropic_client=mock_anthropic,
        redis_client=None,
    )

    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("teste"), tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 5


@pytest.mark.unit
async def test_grupo_h_h03_persiste_mensagens_db(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """H03: regressão — add_mensagem chamado pelo menos 2x (user + assistant)."""
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(
        return_value=_make_end_turn("Resposta do agente")
    )

    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_add_mensagem = AsyncMock(return_value=MagicMock())
    mock_conversa_repo.add_mensagem = mock_add_mensagem

    config = AgentClienteConfig()
    agent = AgentCliente(
        order_service=AsyncMock(spec=OrderService),
        conversa_repo=mock_conversa_repo,
        pdf_generator=MagicMock(spec=PDFGenerator),
        config=config,
        anthropic_client=mock_anthropic,
        redis_client=None,
    )

    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("oi"), tenant_jmb, session)

    assert mock_add_mensagem.call_count >= 2
    roles = [c.kwargs["role"] for c in mock_add_mensagem.call_args_list]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.unit
async def test_grupo_h_h04_buscar_produtos_sem_catalog_service(
    tenant_jmb: Tenant,
    conversa_fixture: Conversa,
) -> None:
    """H04: regressão — catalog_service=None retorna aviso sem lançar exceção."""
    tool_response = _make_tool_use("buscar_produtos", {"query": "shampoo", "limit": 5})
    end = _make_end_turn("Não encontrei produtos no momento.")

    agent, mock_order, mock_anthropic, _ = _make_agent(
        [tool_response, end], conversa_fixture
    )
    # catalog_service já é None no _make_agent padrão

    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(_make_mensagem("quero shampoo"), tenant_jmb, session)

    # 2 chamadas ao anthropic sem exceção
    assert mock_anthropic.messages.create.call_count == 2
    assert not mock_order.criar_pedido_from_intent.called
