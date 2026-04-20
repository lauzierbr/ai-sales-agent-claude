"""Testes unitários de agents/runtime/agent_cliente.py — AgentCliente (Sprint 2).

Todos os testes são @pytest.mark.unit — sem I/O externo.
Claude SDK, Redis, PostgreSQL — todos mockados.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.runtime.agent_cliente import AgentCliente
from src.agents.types import Conversa, Mensagem, Persona
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
def mensagem_cliente() -> Mensagem:
    return Mensagem(
        id="msg1",
        de="5519999999999@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Quero ver o catálogo de shampoo",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def conversa_fixture() -> Conversa:
    return Conversa(
        id="conv-001",
        tenant_id="jmb",
        telefone="5519999999999",
        persona=Persona.CLIENTE_B2B,
        iniciada_em=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
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
        criado_em=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
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


def _make_anthropic_end_turn(text: str = "Aqui estão os produtos encontrados!") -> MagicMock:
    """Cria mock de resposta anthropic com stop_reason=end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _make_anthropic_tool_use(tool_name: str, tool_input: dict[str, Any], tool_id: str = "tool_abc") -> MagicMock:
    """Cria mock de resposta anthropic com stop_reason=tool_use."""
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
    anthropic_client: MagicMock,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido | None = None,
) -> AgentCliente:
    """Cria AgentCliente com todas as dependências mockadas."""
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    mock_order_service = AsyncMock(spec=OrderService)
    if pedido_fixture:
        mock_order_service.criar_pedido_from_intent = AsyncMock(return_value=pedido_fixture)

    mock_pdf = MagicMock(spec=PDFGenerator)
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"PDF_BYTES_FAKE" * 100)

    config = AgentClienteConfig()

    return AgentCliente(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=config,
        catalog_service=None,
        anthropic_client=anthropic_client,
        redis_client=None,
    )


# ─────────────────────────────────────────────
# A8: confirmar_pedido executa cadeia completa
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_confirmar_pedido_cadeia_completa(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido,
) -> None:
    """A8: confirmar_pedido chama (1) OrderService, (2) PDFGenerator, (3) send_whatsapp_media."""
    from src.agents.runtime.agent_cliente import AgentCliente
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    mock_order_service = AsyncMock(spec=OrderService)
    mock_order_service.criar_pedido_from_intent = AsyncMock(return_value=pedido_fixture)

    mock_pdf = MagicMock(spec=PDFGenerator)
    fake_pdf_bytes = b"PDF_FAKE" * 200
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=fake_pdf_bytes)

    # Anthropic: primeira chamada tool_use confirmar_pedido, segunda end_turn
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
        "observacao": None,
    }
    tool_response = _make_anthropic_tool_use("confirmar_pedido", tool_input)
    end_response = _make_anthropic_end_turn("Pedido PED-PED-ABC123 confirmado com sucesso!")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    config = AgentClienteConfig()
    agent = AgentCliente(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=config,
        catalog_service=None,
        anthropic_client=mock_anthropic,
        redis_client=None,
    )

    media_calls: list[dict[str, Any]] = []

    async def mock_send_media(instancia_id: str, numero: str, pdf_bytes: bytes, caption: str, file_name: str) -> None:
        media_calls.append({
            "instancia_id": instancia_id,
            "numero": numero,
            "pdf_bytes": pdf_bytes,
            "caption": caption,
        })

    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_media", new=mock_send_media):
        with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(
                mensagem=mensagem_cliente,
                tenant=tenant_jmb,
                session=session,
                cliente_b2b_id="cli-001",
            )

    # (1) OrderService.criar_pedido_from_intent foi chamado
    assert mock_order_service.criar_pedido_from_intent.called, "OrderService não foi chamado"

    # (2) PDFGenerator.gerar_pdf_pedido foi chamado com o pedido retornado
    assert mock_pdf.gerar_pdf_pedido.called, "PDFGenerator não foi chamado"
    call_args = mock_pdf.gerar_pdf_pedido.call_args
    assert call_args[0][0].id == pedido_fixture.id, "PDFGenerator chamado com pedido errado"

    # (3) send_whatsapp_media chamado com pdf_bytes e tenant.whatsapp_number
    assert len(media_calls) >= 1, "send_whatsapp_media não foi chamado"
    assert media_calls[0]["numero"] == tenant_jmb.whatsapp_number
    assert media_calls[0]["pdf_bytes"] == fake_pdf_bytes


# ─────────────────────────────────────────────
# A9: max_iterations impede loop infinito
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_max_iterations_nao_loop_infinito(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
) -> None:
    """A9: AgentCliente encerra após max_iterations quando stop_reason sempre é tool_use."""
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.agents.runtime.agent_cliente import AgentCliente
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    # Mock que sempre retorna tool_use (potencialmente infinito)
    tool_response = _make_anthropic_tool_use(
        "buscar_produtos",
        {"query": "shampoo", "limit": 5},
    )
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=tool_response)

    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    config = AgentClienteConfig()
    config.max_iterations = 5  # Configura explicitamente

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
        await agent.responder(
            mensagem=mensagem_cliente,
            tenant=tenant_jmb,
            session=session,
        )

    # Deve ter chamado anthropic exatamente max_iterations vezes
    assert mock_anthropic.messages.create.call_count == config.max_iterations, (
        f"Esperado {config.max_iterations} chamadas, "
        f"obtido {mock_anthropic.messages.create.call_count}"
    )


# ─────────────────────────────────────────────
# Anthropic chamado com parâmetros corretos
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_chama_anthropic(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
) -> None:
    """AgentCliente.responder chama anthropic.messages.create com model e tools."""
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=_make_anthropic_end_turn())

    agent = _make_agent(mock_anthropic, conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(
            mensagem=mensagem_cliente,
            tenant=tenant_jmb,
            session=session,
        )

    assert mock_anthropic.messages.create.called
    call_kwargs = mock_anthropic.messages.create.call_args[1]
    assert "tools" in call_kwargs
    assert "messages" in call_kwargs
    assert call_kwargs["model"] is not None


# ─────────────────────────────────────────────
# Resposta final enviada via WhatsApp
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_envia_resposta_whatsapp(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
) -> None:
    """AgentCliente.responder envia resposta final via send_whatsapp_message."""
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(
        return_value=_make_anthropic_end_turn("Temos Shampoo Hidratante disponível!")
    )

    agent = _make_agent(mock_anthropic, conversa_fixture)
    session = AsyncMock()
    envios: list[tuple[str, str, str]] = []

    async def mock_send(instancia_id: str, numero: str, texto: str) -> None:
        envios.append((instancia_id, numero, texto))

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=mock_send):
        await agent.responder(
            mensagem=mensagem_cliente,
            tenant=tenant_jmb,
            session=session,
        )

    assert len(envios) == 1
    instancia_usada, numero_usado, texto_enviado = envios[0]
    assert instancia_usada == "inst-jmb-01"
    assert numero_usado == "5519999999999"
    assert "Shampoo" in texto_enviado


# ─────────────────────────────────────────────
# Histórico persistido no banco
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_persiste_mensagens_db(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
) -> None:
    """AgentCliente persiste mensagem do usuário e resposta do assistente via ConversaRepo."""
    from src.agents.config import AgentClienteConfig
    from src.agents.repo import ConversaRepo
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(
        return_value=_make_anthropic_end_turn("Resposta do agente")
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
        await agent.responder(
            mensagem=mensagem_cliente,
            tenant=tenant_jmb,
            session=session,
        )

    # Deve ter chamado add_mensagem pelo menos 2 vezes: user + assistant
    add_mensagem_calls = mock_add_mensagem.call_count
    assert add_mensagem_calls >= 2, (
        f"add_mensagem deve ser chamado pelo menos 2x, chamado {add_mensagem_calls}x"
    )

    # Verifica roles das chamadas
    roles = [
        call.kwargs["role"]
        for call in mock_add_mensagem.call_args_list
    ]
    assert "user" in roles
    assert "assistant" in roles


# ─────────────────────────────────────────────
# buscar_produtos é invocado corretamente
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_cliente_buscar_produtos_sem_catalog_service(
    tenant_jmb: Tenant,
    mensagem_cliente: Mensagem,
    conversa_fixture: Conversa,
) -> None:
    """AgentCliente retorna aviso quando catalog_service=None e buscar_produtos é chamado."""
    # Primeira chamada: tool_use buscar_produtos; segunda: end_turn
    tool_response = _make_anthropic_tool_use(
        "buscar_produtos",
        {"query": "shampoo", "limit": 5},
    )
    end_response = _make_anthropic_end_turn("Não encontrei produtos no momento.")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent = _make_agent(mock_anthropic, conversa_fixture)
    session = AsyncMock()

    with patch("src.agents.runtime.agent_cliente.send_whatsapp_message", new=AsyncMock()):
        # Não deve lançar exceção mesmo sem catalog_service
        await agent.responder(
            mensagem=mensagem_cliente,
            tenant=tenant_jmb,
            session=session,
        )

    # Chamou anthropic 2x (1 tool_use + 1 end_turn)
    assert mock_anthropic.messages.create.call_count == 2


# ─────────────────────────────────────────────
# A_TOOL_COVERAGE — AgentCliente
# ─────────────────────────────────────────────

def test_a_tool_coverage_cliente_capacidades_anunciadas_tem_ferramenta() -> None:
    """A_TOOL_COVERAGE: cada capacidade que o AgentCliente anuncia tem ferramenta em _TOOLS."""
    from src.agents.runtime.agent_cliente import _TOOLS

    tool_names = {t["name"] for t in _TOOLS}
    assert "buscar_produtos" in tool_names
    assert "confirmar_pedido" in tool_names
    assert "listar_meus_pedidos" in tool_names, (
        "Cliente deve poder consultar seus próprios pedidos"
    )
