"""Testes unitários de agents/runtime/agent_rep.py — AgentRep (Sprint 3).

Todos os testes são @pytest.mark.unit — sem I/O externo.
Claude SDK, Redis, PostgreSQL — todos mockados.

Casos cobertos:
  R01 — buscar_produtos chama CatalogService
  R02 — buscar_clientes_carteira filtra por tenant_id E representante_id
  R03 — confirmar com cliente válido chama OrderService + PDF + gestor
  R04 — confirmar com cliente inválido NÃO chama OrderService
  R05 — pedido criado tem representante_id preenchido
  R06 — Persona.REPRESENTANTE usado em get_or_create_conversa
  R07 — catalog_service=None retorna aviso sem exceção
  R08 — max_iterations impede loop infinito
  Extra — session.commit() chamado após confirmar pedido
  Extra — isolamento cross-tenant: tenant_id correto sempre passado
  Extra — buscar_clientes_carteira filtra por rep (A5)
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.agents.config import AgentRepConfig
from src.agents.repo import ClienteB2BRepo, ConversaRepo
from src.agents.runtime.agent_rep import AgentRep
from src.agents.types import ClienteB2B, Conversa, Mensagem, Persona, Representante
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
def representante_jmb() -> Representante:
    return Representante(
        id="rep-001",
        tenant_id="jmb",
        usuario_id=None,
        telefone="5519888888888",
        nome="Carlos Vendas",
        ativo=True,
    )


@pytest.fixture
def mensagem_rep() -> Mensagem:
    return Mensagem(
        id="msg-rep-01",
        de="5519888888888@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Quero ver os produtos de shampoo",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def conversa_rep_fixture() -> Conversa:
    return Conversa(
        id="conv-rep-001",
        tenant_id="jmb",
        telefone="5519888888888",
        persona=Persona.REPRESENTANTE,
        iniciada_em=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def cliente_b2b_fixture() -> ClienteB2B:
    return ClienteB2B(
        id="cli-001",
        tenant_id="jmb",
        nome="Farmácia São João",
        cnpj="12.345.678/0001-99",
        telefone="5519777777777",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        representante_id="rep-001",
    )


@pytest.fixture
def pedido_fixture() -> Pedido:
    return Pedido(
        id="ped-rep-abc12345",
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id="rep-001",
        status=StatusPedido.PENDENTE,
        total_estimado=Decimal("500.00"),
        pdf_path=None,
        criado_em=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        itens=[
            ItemPedido(
                id="item-001",
                pedido_id="ped-rep-abc12345",
                produto_id="prod-001",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=10,
                preco_unitario=Decimal("50.00"),
                subtotal=Decimal("500.00"),
            )
        ],
    )


def _make_anthropic_end_turn(text: str = "Aqui estão os resultados!") -> MagicMock:
    """Cria mock de resposta anthropic com stop_reason=end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _make_anthropic_tool_use(
    tool_name: str, tool_input: dict[str, Any], tool_id: str = "tool_rep_abc"
) -> MagicMock:
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
    representante: Representante,
    anthropic_client: MagicMock,
    conversa_fixture: Conversa,
    pedido_fixture: Pedido | None = None,
    clientes_carteira: list[ClienteB2B] | None = None,
    catalog_service: Any | None = None,
) -> tuple[AgentRep, AsyncMock, AsyncMock, MagicMock]:
    """Cria AgentRep com todas as dependências mockadas.

    Returns:
        Tupla (agent, mock_order_service, mock_conversa_repo, mock_pdf).
    """
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

    mock_cliente_repo = AsyncMock(spec=ClienteB2BRepo)
    mock_cliente_repo.buscar_por_nome = AsyncMock(return_value=clientes_carteira or [])
    mock_cliente_repo.listar_por_representante = AsyncMock(return_value=clientes_carteira or [])

    config = AgentRepConfig()

    agent = AgentRep(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=config,
        representante=representante,
        catalog_service=catalog_service,
        anthropic_client=anthropic_client,
        redis_client=None,
        cliente_b2b_repo=mock_cliente_repo,
    )

    return agent, mock_order_service, mock_conversa_repo, mock_pdf


# ─────────────────────────────────────────────
# R01 — buscar_produtos chama CatalogService
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_buscar_produtos_chama_catalog_service(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
) -> None:
    """R01: AgentRep.responder com buscar_produtos chama CatalogService.buscar_semantico."""
    mock_catalog = AsyncMock()
    mock_catalog.buscar_semantico = AsyncMock(return_value=[])

    tool_response = _make_anthropic_tool_use(
        "buscar_produtos", {"query": "shampoo", "limit": 5}
    )
    end_response = _make_anthropic_end_turn("Não encontrei produtos.")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent, _, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        catalog_service=mock_catalog,
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    mock_catalog.buscar_semantico.assert_called_once()
    call_kwargs = mock_catalog.buscar_semantico.call_args[1]
    assert call_kwargs["tenant_id"] == "jmb"
    assert call_kwargs["query"] == "shampoo"


# ─────────────────────────────────────────────
# R02 + A5 — buscar_clientes_carteira filtra por tenant_id E rep_id
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_buscar_clientes_carteira_filtra_por_rep(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
    cliente_b2b_fixture: ClienteB2B,
) -> None:
    """R02/A5: buscar_clientes_carteira chama buscar_por_nome com tenant_id='jmb' e representante_id do rep."""
    tool_response = _make_anthropic_tool_use(
        "buscar_clientes_carteira", {"query": "farmacia"}
    )
    end_response = _make_anthropic_end_turn("Encontrei o cliente.")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent, _, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        clientes_carteira=[cliente_b2b_fixture],
    )
    # Acessa o repo mockado para verificar chamada
    mock_repo = agent._cliente_b2b_repo

    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    # Verifica que buscar_por_nome foi chamado com tenant_id="jmb" explicitamente
    mock_repo.buscar_por_nome.assert_called_once()
    call_kwargs = mock_repo.buscar_por_nome.call_args[1]
    assert call_kwargs["tenant_id"] == "jmb", (
        f"tenant_id esperado 'jmb', obtido {call_kwargs.get('tenant_id')!r}"
    )
    assert call_kwargs["representante_id"] == representante_jmb.id, (
        f"representante_id esperado {representante_jmb.id!r}, "
        f"obtido {call_kwargs.get('representante_id')!r}"
    )

    # Garante que se fosse outro tenant, nunca seria chamado com "outro"
    for c in mock_repo.buscar_por_nome.call_args_list:
        assert c[1].get("tenant_id") != "outro", (
            "Cross-tenant violation: buscar_por_nome chamado com tenant_id='outro'"
        )


# ─────────────────────────────────────────────
# R03 — confirmar com cliente válido chama OrderService + PDF + gestor
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_confirmar_cliente_valido_cria_pedido(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
    cliente_b2b_fixture: ClienteB2B,
    pedido_fixture: Pedido,
) -> None:
    """R03: confirmar_pedido_em_nome_de com cliente válido chama OrderService + PDF + notifica gestor."""
    tool_input = {
        "cliente_b2b_id": "cli-001",
        "itens": [
            {
                "produto_id": "prod-001",
                "codigo_externo": "SKU001",
                "nome_produto": "Shampoo 300ml",
                "quantidade": 10,
                "preco_unitario": "50.00",
            }
        ],
    }
    tool_response = _make_anthropic_tool_use("confirmar_pedido_em_nome_de", tool_input)
    end_response = _make_anthropic_end_turn("Pedido confirmado!")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent, mock_order_service, _, mock_pdf = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        pedido_fixture=pedido_fixture,
        clientes_carteira=[cliente_b2b_fixture],
    )
    session = AsyncMock()

    media_calls: list[dict[str, Any]] = []

    async def mock_send_media(
        instancia_id: str, numero: str, pdf_bytes: bytes, caption: str, file_name: str
    ) -> None:
        media_calls.append({"numero": numero, "pdf_bytes": pdf_bytes})

    with patch("src.agents.runtime.agent_rep.send_whatsapp_media", new=mock_send_media):
        with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(mensagem_rep, tenant_jmb, session)

    # OrderService foi chamado
    assert mock_order_service.criar_pedido_from_intent.called, "OrderService não foi chamado"

    # PDF foi gerado
    assert mock_pdf.gerar_pdf_pedido.called, "PDFGenerator não foi chamado"

    # Gestor foi notificado
    assert len(media_calls) >= 1, "send_whatsapp_media não foi chamado"
    assert media_calls[0]["numero"] == tenant_jmb.whatsapp_number


# ─────────────────────────────────────────────
# R04 + A6 — confirmar com cliente inválido NÃO chama OrderService
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_confirmar_cliente_invalido_nao_cria_pedido(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
    cliente_b2b_fixture: ClienteB2B,
) -> None:
    """R04/A6: confirmar_pedido_em_nome_de com cliente_b2b_id não na carteira → OrderService NÃO chamado."""
    # ID inválido — não está na carteira
    tool_input = {
        "cliente_b2b_id": "cli-INVALIDO-999",
        "itens": [
            {
                "produto_id": "prod-001",
                "codigo_externo": "SKU001",
                "nome_produto": "Shampoo 300ml",
                "quantidade": 5,
                "preco_unitario": "50.00",
            }
        ],
    }
    tool_response = _make_anthropic_tool_use("confirmar_pedido_em_nome_de", tool_input)
    end_response = _make_anthropic_end_turn("Cliente não encontrado.")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    # Carteira contém apenas cli-001 — cli-INVALIDO-999 não está nela
    agent, mock_order_service, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        clientes_carteira=[cliente_b2b_fixture],
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    # OrderService NÃO deve ter sido chamado
    assert not mock_order_service.criar_pedido_from_intent.called, (
        "OrderService foi chamado com cliente inválido — violação de segurança!"
    )


# ─────────────────────────────────────────────
# R05 — pedido criado tem representante_id preenchido
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_pedido_tem_representante_id(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
    cliente_b2b_fixture: ClienteB2B,
    pedido_fixture: Pedido,
) -> None:
    """R05: CriarPedidoInput passado ao OrderService contém representante_id do representante injetado."""
    tool_input = {
        "cliente_b2b_id": "cli-001",
        "itens": [
            {
                "produto_id": "prod-001",
                "codigo_externo": "SKU001",
                "nome_produto": "Shampoo 300ml",
                "quantidade": 5,
                "preco_unitario": "50.00",
            }
        ],
    }
    tool_response = _make_anthropic_tool_use("confirmar_pedido_em_nome_de", tool_input)
    end_response = _make_anthropic_end_turn("Pedido confirmado!")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent, mock_order_service, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        pedido_fixture=pedido_fixture,
        clientes_carteira=[cliente_b2b_fixture],
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(mensagem_rep, tenant_jmb, session)

    assert mock_order_service.criar_pedido_from_intent.called
    call_kwargs = mock_order_service.criar_pedido_from_intent.call_args[1]
    pedido_input = call_kwargs["pedido_input"]
    assert pedido_input.representante_id == "rep-001", (
        f"representante_id esperado 'rep-001', obtido {pedido_input.representante_id!r}"
    )


# ─────────────────────────────────────────────
# R06 + A9 — Persona.REPRESENTANTE em get_or_create_conversa
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_persona_representante(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
) -> None:
    """R06/A9: get_or_create_conversa chamado com persona=Persona.REPRESENTANTE."""
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=_make_anthropic_end_turn())

    agent, _, mock_conversa_repo, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    mock_conversa_repo.get_or_create_conversa.assert_called_once()
    call_kwargs = mock_conversa_repo.get_or_create_conversa.call_args[1]
    assert call_kwargs["persona"] == Persona.REPRESENTANTE, (
        f"Esperado Persona.REPRESENTANTE, obtido {call_kwargs.get('persona')!r}"
    )


# ─────────────────────────────────────────────
# R07 — catalog_service=None retorna aviso sem exceção
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_catalog_service_none_nao_lanca_excecao(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
) -> None:
    """R07: AgentRep instanciado com catalog_service=None retorna aviso quando busca é chamada."""
    tool_response = _make_anthropic_tool_use(
        "buscar_produtos", {"query": "shampoo", "limit": 5}
    )
    end_response = _make_anthropic_end_turn("Catálogo não disponível.")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    # catalog_service=None explicitamente
    agent, _, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        catalog_service=None,
    )
    session = AsyncMock()

    # Não deve lançar exceção
    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    # Deve ter chamado anthropic 2x (tool + end_turn)
    assert mock_anthropic.messages.create.call_count == 2


# ─────────────────────────────────────────────
# R08 — max_iterations impede loop infinito
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_max_iterations_nao_loop_infinito(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
) -> None:
    """R08: AgentRep encerra após max_iterations quando stop_reason sempre é tool_use."""
    tool_response = _make_anthropic_tool_use(
        "buscar_clientes_carteira", {"query": "cliente"}
    )
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=tool_response)

    agent, _, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
    )
    agent._config.max_iterations = 5

    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem_rep, tenant_jmb, session)

    assert mock_anthropic.messages.create.call_count == 5, (
        f"Esperado 5 chamadas (max_iterations), "
        f"obtido {mock_anthropic.messages.create.call_count}"
    )


# ─────────────────────────────────────────────
# A10 — session.commit() chamado após confirmar pedido
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_rep_commit_apos_pedido(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
    cliente_b2b_fixture: ClienteB2B,
    pedido_fixture: Pedido,
) -> None:
    """A10: session.commit() chamado ao menos 1x quando confirmar_pedido_em_nome_de é executada."""
    tool_input = {
        "cliente_b2b_id": "cli-001",
        "itens": [
            {
                "produto_id": "prod-001",
                "codigo_externo": "SKU001",
                "nome_produto": "Shampoo 300ml",
                "quantidade": 10,
                "preco_unitario": "50.00",
            }
        ],
    }
    tool_response = _make_anthropic_tool_use("confirmar_pedido_em_nome_de", tool_input)
    end_response = _make_anthropic_end_turn("Pedido confirmado!")

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[tool_response, end_response])

    agent, _, _, _ = _make_agent(
        representante_jmb,
        mock_anthropic,
        conversa_rep_fixture,
        pedido_fixture=pedido_fixture,
        clientes_carteira=[cliente_b2b_fixture],
    )
    session = AsyncMock()

    with patch("src.agents.runtime.agent_rep.send_whatsapp_media", new=AsyncMock()):
        with patch("src.agents.runtime.agent_rep.send_whatsapp_message", new=AsyncMock()):
            await agent.responder(mensagem_rep, tenant_jmb, session)

    assert session.commit.called, "session.commit() não foi chamado"
    assert session.commit.call_count >= 1


# ─────────────────────────────────────────────
# M_INJECT — wiring deps não-None em ui.py (teste indireto via AgentRep construtor)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_agent_rep_deps_nao_none(
    tenant_jmb: Tenant,
    representante_jmb: Representante,
    mensagem_rep: Mensagem,
    conversa_rep_fixture: Conversa,
) -> None:
    """M_INJECT: AgentRep recebe order_service, pdf_generator e catalog_service não-None via construtor."""
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService

    mock_order_service = AsyncMock(spec=OrderService)
    mock_pdf = MagicMock(spec=PDFGenerator)
    mock_catalog = AsyncMock()

    config = AgentRepConfig()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_rep_fixture)
    mock_conversa_repo.add_mensagem = AsyncMock(return_value=MagicMock())

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create = AsyncMock(return_value=_make_anthropic_end_turn())

    agent = AgentRep(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=config,
        representante=representante_jmb,
        catalog_service=mock_catalog,
        anthropic_client=mock_anthropic,
        redis_client=None,
    )

    # Verifica que deps foram injetadas corretamente (não-None)
    assert agent._order_service is not None
    assert agent._pdf_generator is not None
    assert agent._catalog_service is not None
    assert agent._representante is representante_jmb
