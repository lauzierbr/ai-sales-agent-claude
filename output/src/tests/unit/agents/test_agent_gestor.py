"""Testes unitários de agents/runtime/agent_gestor.py — AgentGestor (Sprint 4).

Todos os testes são @pytest.mark.unit — sem I/O externo.
Claude SDK, Redis, PostgreSQL — todos mockados.

Casos cobertos:
  G01 — buscar_clientes chama buscar_todos_por_nome (sem rep filter)
  G02 — buscar_produtos chama CatalogService
  G03 — confirmar_pedido_em_nome_de cria pedido sem validar carteira
  G04 — DP-03: representante_id do pedido = cliente.representante_id
  G05 — DP-03: representante_id = None quando cliente não tem rep
  G06 — relatorio_vendas(semana) usa timedelta(7), não DATE_TRUNC
  G07 — relatorio_vendas(tipo=por_rep) chama RelatorioRepo.totais_por_rep
  G08 — clientes_inativos(dias=30) chama RelatorioRepo.clientes_inativos
  G09 — catalog_service=None não levanta exceção
  G10 — ConversaRepo chamado com Persona.GESTOR
  G11 — session.commit() chamado após resposta
  G12 — tenant_id passado ao RelatorioRepo (isolamento)
  G13 — multi-turn: tool call seguida de follow-up não gera erro 400
         (verifica que response.content é serializado como dicts, não objetos SDK)
  G14 — listar_pedidos_por_status chama OrderRepo.listar_por_tenant_status
  A_TOOL_COVERAGE — todas capacidades anunciadas têm ferramenta correspondente
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.agents.config import AgentGestorConfig
from src.agents.repo import ClienteB2BRepo, ConversaRepo, RelatorioRepo
from src.agents.runtime.agent_gestor import AgentGestor, _TOOLS
from src.agents.types import ClienteB2B, Conversa, Gestor, Mensagem, Persona
from src.orders.repo import OrderRepo
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
def gestor_jmb() -> Gestor:
    return Gestor(
        id="gest-001",
        tenant_id="jmb",
        telefone="5519000000002",
        nome="Lauzier Gestor",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mensagem_gestor() -> Mensagem:
    return Mensagem(
        id="msg-gest-01",
        de="5519000000002@s.whatsapp.net",
        para="inst-jmb-01",
        texto="busca clientes muzel",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def conversa_gestor() -> Conversa:
    return Conversa(
        id="conv-gest-001",
        tenant_id="jmb",
        telefone="5519000000002",
        persona=Persona.GESTOR,
        iniciada_em=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def cliente_com_rep() -> ClienteB2B:
    return ClienteB2B(
        id="cli-001",
        tenant_id="jmb",
        nome="José LZ Muzel",
        cnpj="12.345.678/0001-90",
        telefone="5519991111111",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        representante_id="rep-001",
    )


@pytest.fixture
def cliente_sem_rep() -> ClienteB2B:
    return ClienteB2B(
        id="cli-002",
        tenant_id="jmb",
        nome="Farmácia Sem Rep",
        cnpj="99.888.777/0001-11",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        representante_id=None,
    )


@pytest.fixture
def pedido_criado() -> Pedido:
    return Pedido(
        id="ped-001",
        tenant_id="jmb",
        numero_pedido="PED-001",
        cliente_b2b_id="cli-001",
        representante_id="rep-001",
        status=StatusPedido.PENDENTE,
        total_estimado=Decimal("299.80"),
        pdf_path=None,
        itens=[],
        criado_em=datetime(2026, 4, 17, tzinfo=timezone.utc),
    )


def _make_agent(
    tenant: Tenant,
    gestor: Gestor,
    mock_session: AsyncMock,
    mock_conversa_repo: AsyncMock,
    mock_order_service: AsyncMock,
    mock_pdf: MagicMock,
    mock_anthropic: AsyncMock,
    mock_cliente_repo: AsyncMock | None = None,
    mock_relatorio_repo: AsyncMock | None = None,
    mock_order_repo: AsyncMock | None = None,
    catalog_service: Any | None = None,
) -> AgentGestor:
    return AgentGestor(
        order_service=mock_order_service,
        conversa_repo=mock_conversa_repo,
        pdf_generator=mock_pdf,
        config=AgentGestorConfig(),
        gestor=gestor,
        catalog_service=catalog_service,
        anthropic_client=mock_anthropic,
        redis_client=None,
        cliente_b2b_repo=mock_cliente_repo,
        relatorio_repo=mock_relatorio_repo,
        order_repo=mock_order_repo,
    )


def _mock_anthropic_end_turn(texto: str = "Resposta do gestor.") -> AsyncMock:
    """Mock do cliente Anthropic que retorna end_turn com texto."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = texto

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    return mock_client


# ─────────────────────────────────────────────
# G01 — buscar_clientes sem filtro representante_id
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g01_buscar_clientes_sem_filtro_rep(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
    cliente_com_rep: ClienteB2B,
) -> None:
    """G01: buscar_clientes chama buscar_todos_por_nome sem representante_id."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    # buscar_clientes agora usa buscar_todos_com_representante (retorna dicts com nome do rep)
    cliente_dict = {
        "id": cliente_com_rep.id,
        "nome": cliente_com_rep.nome,
        "cnpj": cliente_com_rep.cnpj,
        "telefone": cliente_com_rep.telefone,
        "representante_id": cliente_com_rep.representante_id,
        "representante_nome": "João Silva",
    }
    mock_cliente_repo = AsyncMock(spec=ClienteB2BRepo)
    mock_cliente_repo.buscar_todos_com_representante = AsyncMock(return_value=[cliente_dict])

    mock_order_service = AsyncMock()
    mock_pdf = MagicMock()
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"fake-pdf")

    # Anthropic: primeira chamada pede buscar_clientes, segunda retorna texto
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "buscar_clientes"
    tool_block.id = "tool-001"
    tool_block.input = {"query": "muzel"}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Encontrei o cliente Muzel."

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb,
        gestor=gestor_jmb,
        mock_session=mock_session,
        mock_conversa_repo=mock_conversa_repo,
        mock_order_service=mock_order_service,
        mock_pdf=mock_pdf,
        mock_anthropic=mock_anthropic,
        mock_cliente_repo=mock_cliente_repo,
    )

    with patch("src.agents.service.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    # Agora usa buscar_todos_com_representante (com JOIN para nome do rep)
    mock_cliente_repo.buscar_todos_com_representante.assert_called_once()
    call_kwargs = mock_cliente_repo.buscar_todos_com_representante.call_args
    all_kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    assert "representante_id" not in all_kwargs, "buscar_todos_com_representante não deve receber representante_id"


# ─────────────────────────────────────────────
# G02 — buscar_produtos chama CatalogService
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g02_buscar_produtos_chama_catalog(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G02: buscar_produtos delega ao CatalogService."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    # AgentGestor agora usa buscar_semantico (+ get_por_codigo para queries numéricas),
    # mesmo padrão do AgentCliente. Ver fix: _buscar_produtos no agent_gestor.py.
    mock_catalog = AsyncMock()
    mock_catalog.buscar_semantico = AsyncMock(return_value=[])
    mock_catalog.get_por_codigo = AsyncMock(return_value=None)

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "buscar_produtos"
    tool_block.id = "tool-002"
    tool_block.input = {"query": "shampoo", "limit": 5}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Nenhum produto encontrado."

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic, catalog_service=mock_catalog,
    )

    with patch("src.agents.service.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    # Query "shampoo" não é dígito → pula get_por_codigo, vai direto para busca semântica.
    mock_catalog.buscar_semantico.assert_called_once_with(
        tenant_id="jmb", query="shampoo", limit=5
    )


# ─────────────────────────────────────────────
# G03 — confirmar_pedido sem validação de carteira
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g03_pedido_sem_validacao_carteira(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
    cliente_com_rep: ClienteB2B,
    pedido_criado: Pedido,
) -> None:
    """G03: confirmar_pedido_em_nome_de cria pedido sem validar carteira."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_cliente_repo = AsyncMock(spec=ClienteB2BRepo)
    mock_cliente_repo.get_by_id = AsyncMock(return_value=cliente_com_rep)

    mock_order_service = AsyncMock()
    mock_order_service.criar_pedido_from_intent = AsyncMock(return_value=pedido_criado)

    mock_pdf = MagicMock()
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"pdf")

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "confirmar_pedido_em_nome_de"
    tool_block.id = "tool-003"
    tool_block.input = {
        "cliente_b2b_id": "cli-001",
        "itens": [{"produto_id": "p1", "codigo_externo": "SKU1", "nome_produto": "Prod", "quantidade": 2, "preco_unitario": "29.90"}],
    }

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Pedido criado!"

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=mock_order_service, mock_pdf=mock_pdf,
        mock_anthropic=mock_anthropic, mock_cliente_repo=mock_cliente_repo,
    )

    with (
        patch("src.agents.service.send_whatsapp_message", new=AsyncMock()),
        patch("src.agents.service.send_whatsapp_media", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
    ):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    mock_order_service.criar_pedido_from_intent.assert_called_once()


# ─────────────────────────────────────────────
# G04 — DP-03: representante_id herdado do cliente
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g04_dp03_herda_rep_do_cliente(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
    cliente_com_rep: ClienteB2B,
    pedido_criado: Pedido,
) -> None:
    """G04: CriarPedidoInput.representante_id = cliente.representante_id quando não None."""
    from src.orders.types import CriarPedidoInput

    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_cliente_repo = AsyncMock(spec=ClienteB2BRepo)
    mock_cliente_repo.get_by_id = AsyncMock(return_value=cliente_com_rep)

    pedido_inputs_recebidos: list[CriarPedidoInput] = []

    async def captura_pedido(pedido_input: CriarPedidoInput, session: Any) -> Pedido:
        pedido_inputs_recebidos.append(pedido_input)
        return pedido_criado

    mock_order_service = AsyncMock()
    mock_order_service.criar_pedido_from_intent = captura_pedido

    mock_pdf = MagicMock()
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"pdf")

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "confirmar_pedido_em_nome_de"
    tool_block.id = "tool-004"
    tool_block.input = {
        "cliente_b2b_id": "cli-001",
        "itens": [{"produto_id": "p1", "codigo_externo": "SKU1", "nome_produto": "P", "quantidade": 1, "preco_unitario": "10.00"}],
    }

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Pedido criado!"

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=mock_order_service, mock_pdf=mock_pdf,
        mock_anthropic=mock_anthropic, mock_cliente_repo=mock_cliente_repo,
    )

    with (
        patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
    ):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    assert len(pedido_inputs_recebidos) == 1
    assert pedido_inputs_recebidos[0].representante_id == "rep-001"


# ─────────────────────────────────────────────
# G05 — DP-03: representante_id = None quando cliente sem rep
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g05_dp03_sem_rep_none(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
    cliente_sem_rep: ClienteB2B,
    pedido_criado: Pedido,
) -> None:
    """G05: CriarPedidoInput.representante_id = None quando cliente não tem rep."""
    from src.orders.types import CriarPedidoInput

    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_cliente_repo = AsyncMock(spec=ClienteB2BRepo)
    mock_cliente_repo.get_by_id = AsyncMock(return_value=cliente_sem_rep)

    pedido_inputs_recebidos: list[CriarPedidoInput] = []

    async def captura_pedido(pedido_input: CriarPedidoInput, session: Any) -> Pedido:
        pedido_inputs_recebidos.append(pedido_input)
        return pedido_criado

    mock_order_service = AsyncMock()
    mock_order_service.criar_pedido_from_intent = captura_pedido

    mock_pdf = MagicMock()
    mock_pdf.gerar_pdf_pedido = MagicMock(return_value=b"pdf")

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "confirmar_pedido_em_nome_de"
    tool_block.id = "tool-005"
    tool_block.input = {
        "cliente_b2b_id": "cli-002",
        "itens": [{"produto_id": "p1", "codigo_externo": "SKU1", "nome_produto": "P", "quantidade": 1, "preco_unitario": "10.00"}],
    }

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Pedido criado!"

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=mock_order_service, mock_pdf=mock_pdf,
        mock_anthropic=mock_anthropic, mock_cliente_repo=mock_cliente_repo,
    )

    with (
        patch("src.agents.runtime.agent_gestor.send_whatsapp_media", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()),
    ):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    assert len(pedido_inputs_recebidos) == 1
    assert pedido_inputs_recebidos[0].representante_id is None


# ─────────────────────────────────────────────
# G06 — relatorio_vendas("semana") usa timedelta(7)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g06_semana_usa_timedelta(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G06: relatorio_vendas(periodo=semana) usa timedelta(7), não DATE_TRUNC."""
    from unittest.mock import patch as mpatch

    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    data_inicio_capturada: list[datetime] = []
    args_capturados: list[Any] = []

    mock_relatorio_repo = AsyncMock(spec=RelatorioRepo)

    async def captura_totais(tenant_id: str, data_inicio: Any, data_fim: Any, session: Any) -> dict:
        data_inicio_capturada.append(data_inicio)
        return {"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0}

    mock_relatorio_repo.totais_periodo = captura_totais

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "relatorio_vendas"
    tool_block.id = "tool-006"
    tool_block.input = {"periodo": "semana", "tipo": "totais"}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Vendas da semana: R$ 0"

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
        mock_relatorio_repo=mock_relatorio_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    assert len(data_inicio_capturada) == 1
    data_inicio = data_inicio_capturada[0]
    now = datetime.now(timezone.utc)

    diff = abs((now - data_inicio).total_seconds())
    esperado = (now - timedelta(days=7))
    diff_esperado = abs((esperado - data_inicio).total_seconds())
    assert diff_esperado < 5, f"data_inicio deve ser ~now-7d, got diff={diff_esperado:.1f}s"

    # Garante que não passou string com DATE_TRUNC
    assert not isinstance(data_inicio, str), "data_inicio não deve ser string (DATE_TRUNC)"


# ─────────────────────────────────────────────
# G07 — relatorio_vendas(tipo=por_rep)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g07_relatorio_por_rep(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G07: relatorio_vendas(tipo=por_rep) chama RelatorioRepo.totais_por_rep."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_relatorio_repo = AsyncMock(spec=RelatorioRepo)
    mock_relatorio_repo.totais_por_rep = AsyncMock(return_value=[])

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "relatorio_vendas"
    tool_block.id = "tool-007"
    tool_block.input = {"periodo": "mes", "tipo": "por_rep"}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Ranking por rep."

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic, mock_relatorio_repo=mock_relatorio_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    mock_relatorio_repo.totais_por_rep.assert_called_once()


# ─────────────────────────────────────────────
# G08 — clientes_inativos(dias=30)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g08_clientes_inativos(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G08 (E0-B): clientes_inativos usa CommerceRepo.listar_clientes_inativos (dados EFOS).

    Sprint 9: clientes_inativos agora usa CommerceRepo (situacao=2 no EFOS),
    não mais RelatorioRepo (que consultava tabela pedidos).
    """
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    from src.commerce.repo import CommerceRepo
    mock_commerce_repo = AsyncMock(spec=CommerceRepo)
    mock_commerce_repo.listar_clientes_inativos = AsyncMock(return_value=[])

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "clientes_inativos"
    tool_block.id = "tool-008"
    tool_block.input = {}  # E0-B: sem campo "dias" — filtra por cidade (opcional)

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Clientes inativos listados."

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
    )
    # Injeta commerce_repo no agente
    agent._commerce_repo = mock_commerce_repo

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    # E0-B: deve chamar CommerceRepo.listar_clientes_inativos
    mock_commerce_repo.listar_clientes_inativos.assert_called_once_with(
        tenant_id="jmb", cidade=None, session=mock_session
    )


# ─────────────────────────────────────────────
# G09 — catalog_service=None não levanta exceção
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g09_catalog_none_sem_excecao(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G09: catalog_service=None não levanta exceção."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "buscar_produtos"
    tool_block.id = "tool-009"
    tool_block.input = {"query": "shampoo"}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Catálogo indisponível."

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
        catalog_service=None,  # explicitamente None
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        # Não deve levantar exceção
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)


# ─────────────────────────────────────────────
# G10 — Persona.GESTOR em ConversaRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g10_persona_gestor_em_conversa(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G10: ConversaRepo.get_or_create_conversa chamado com persona=Persona.GESTOR."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_anthropic = _mock_anthropic_end_turn("Ok.")

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    mock_conversa_repo.get_or_create_conversa.assert_called_once()
    call_kwargs = mock_conversa_repo.get_or_create_conversa.call_args
    persona_passada = call_kwargs.kwargs.get("persona") or call_kwargs.args[2]
    assert persona_passada == Persona.GESTOR


# ─────────────────────────────────────────────
# G11 — session.commit() chamado após resposta
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g11_commit_chamado(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G11: session.commit() chamado ao menos 1x durante AgentGestor.responder."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_anthropic = _mock_anthropic_end_turn("Confirmado.")

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    mock_session.commit.assert_called()


# ─────────────────────────────────────────────
# G12 — tenant_id passado ao RelatorioRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g12_tenant_id_em_relatorio(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G12: tenant_id sempre passado ao RelatorioRepo (isolamento multi-tenant)."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    tenant_ids_recebidos: list[str] = []

    mock_relatorio_repo = AsyncMock(spec=RelatorioRepo)

    async def captura(tenant_id: str, data_inicio: Any, data_fim: Any, session: Any) -> dict:
        tenant_ids_recebidos.append(tenant_id)
        return {"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0}

    mock_relatorio_repo.totais_periodo = captura

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "relatorio_vendas"
    tool_block.id = "tool-012"
    tool_block.input = {"periodo": "hoje", "tipo": "totais"}

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "GMV hoje: R$ 0"

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic, mock_relatorio_repo=mock_relatorio_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    assert len(tenant_ids_recebidos) == 1
    assert tenant_ids_recebidos[0] == "jmb"


# ─────────────────────────────────────────────
# G13 — multi-turn: blocks do SDK serializado como dicts, não objetos
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g13_multiturn_blocks_sao_dicts(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G13/A_MULTITURN: após uma tool call, response.content é armazenado como
    lista de dicts (model_dump), nunca como objetos SDK. Uma segunda chamada
    à API com esse histórico não deve gerar erro 400."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_relatorio_repo = AsyncMock(spec=RelatorioRepo)
    mock_relatorio_repo.totais_periodo = AsyncMock(
        return_value={"total_gmv": 100, "n_pedidos": 2, "ticket_medio": 50}
    )

    # tool_block com model_dump() — simula objeto SDK real
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "relatorio_vendas"
    tool_block.id = "tool-013"
    tool_block.input = {"periodo": "hoje", "tipo": "totais"}
    tool_block.model_dump = MagicMock(return_value={
        "type": "tool_use",
        "id": "tool-013",
        "name": "relatorio_vendas",
        "input": {"periodo": "hoje", "tipo": "totais"},
    })

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "Vendas de hoje: R$ 100"
    final_block.model_dump = MagicMock(return_value={"type": "text", "text": "Vendas de hoje: R$ 100"})

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    messages_enviadas: list[list[dict]] = []

    async def capture_create(**kwargs: Any) -> Any:
        messages_enviadas.append(kwargs.get("messages", []))
        if len(messages_enviadas) == 1:
            return resp_tool
        return resp_final

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = capture_create

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic, mock_relatorio_repo=mock_relatorio_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    # Verifica que a segunda chamada à API recebeu o histórico com dicts, não objetos SDK
    assert len(messages_enviadas) == 2, "Deve ter feito 2 chamadas à API (tool_use + follow-up)"
    segunda_chamada = messages_enviadas[1]
    assistant_msgs = [m for m in segunda_chamada if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 1, "Deve ter ao menos uma mensagem assistant no histórico"
    for msg in assistant_msgs:
        # Content pode ser string (end_turn) ou lista (tool_use).
        # Só verificamos o caso lista — é onde o bug de serialização ocorria.
        if not isinstance(msg["content"], list):
            continue
        for block in msg["content"]:
            assert isinstance(block, dict), (
                f"Bloco tool_use no histórico deve ser dict, não {type(block).__name__}. "
                "Use [b.model_dump() for b in response.content] antes de appender ao histórico."
            )


# ─────────────────────────────────────────────
# G14 — listar_pedidos_por_status chama OrderRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_agent_gestor_g14_listar_pedidos_por_status(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G14: listar_pedidos_por_status delega ao OrderRepo com tenant_id e status corretos."""
    from datetime import datetime, timezone

    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    pedidos_mock = [
        {
            "id": "ped-001",
            "cliente_nome": "LZ Muzel",
            "representante_nome": "João Silva",   # agora incluso via JOIN
            "total_estimado": Decimal("299.80"),
            "status": "pendente",
            "criado_em": datetime(2026, 4, 20, tzinfo=timezone.utc),
        }
    ]
    mock_order_repo = AsyncMock(spec=OrderRepo)
    mock_order_repo.listar_por_tenant_status = AsyncMock(return_value=pedidos_mock)

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "listar_pedidos_por_status"
    tool_block.id = "tool-014"
    tool_block.input = {"status": "pendente"}
    tool_block.model_dump = MagicMock(return_value={
        "type": "tool_use", "id": "tool-014",
        "name": "listar_pedidos_por_status", "input": {"status": "pendente"},
    })

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "1 pedido pendente encontrado."
    final_block.model_dump = MagicMock(return_value={"type": "text", "text": "1 pedido pendente encontrado."})

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = AgentGestor(
        order_service=AsyncMock(),
        conversa_repo=mock_conversa_repo,
        pdf_generator=MagicMock(),
        config=AgentGestorConfig(),
        gestor=gestor_jmb,
        anthropic_client=mock_anthropic,
        redis_client=None,
        order_repo=mock_order_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    mock_order_repo.listar_por_tenant_status.assert_called_once_with(
        tenant_id="jmb",
        status="pendente",
        dias=30,
        limit=20,
        session=mock_session,
    )


# ─────────────────────────────────────────────
# A_TOOL_COVERAGE — todas capacidades anunciadas têm ferramenta correspondente
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_a_tool_coverage_capacidades_anunciadas_tem_ferramenta() -> None:
    """A_TOOL_COVERAGE: cada capacidade que o AgentGestor anuncia ao usuário
    tem uma ferramenta correspondente em _TOOLS. Previne divergência entre
    o que o bot promete e o que consegue fazer."""
    tool_names = {t["name"] for t in _TOOLS}

    # Capacidades anunciadas na saudação e system prompt
    assert "buscar_clientes" in tool_names, "Ferramenta de busca de clientes ausente"
    assert "buscar_produtos" in tool_names, "Ferramenta de busca de produtos ausente"
    assert "confirmar_pedido_em_nome_de" in tool_names, "Ferramenta de fechar pedidos ausente"
    assert "relatorio_vendas" in tool_names, "Ferramenta de relatório de vendas ausente"
    assert "clientes_inativos" in tool_names, "Ferramenta de clientes inativos ausente"
    assert "listar_pedidos_por_status" in tool_names, (
        "Ferramenta de listar pedidos ausente — bot anuncia visibilidade de pedidos "
        "mas não conseguia responder 'quais os pedidos pendentes' sem esta ferramenta"
    )


# ─────────────────────────────────────────────
# G15 — aprovar_pedidos aprova e faz commit
# ─────────────────────────────────────────────

@pytest.mark.unit
async def test_agent_gestor_g15_aprovar_pedidos(
    tenant_jmb: Tenant,
    gestor_jmb: Gestor,
    mensagem_gestor: Mensagem,
    conversa_gestor: Conversa,
) -> None:
    """G15: aprovar_pedidos chama OrderRepo.aprovar_pedido para cada ID e faz commit."""
    mock_session = AsyncMock()
    mock_conversa_repo = AsyncMock(spec=ConversaRepo)
    mock_conversa_repo.get_or_create_conversa = AsyncMock(return_value=conversa_gestor)
    mock_conversa_repo.add_mensagem = AsyncMock()

    mock_order_repo = AsyncMock(spec=OrderRepo)
    mock_order_repo.aprovar_pedido = AsyncMock(
        side_effect=[
            {"id": "ped-1", "status": "confirmado", "cliente_b2b_id": "cli-1", "total_estimado": "100.00"},
            {"id": "ped-2", "status": "confirmado", "cliente_b2b_id": "cli-1", "total_estimado": "200.00"},
        ]
    )

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "aprovar_pedidos"
    tool_block.id = "tool-015"
    tool_block.input = {"pedido_ids": ["ped-1", "ped-2"]}
    tool_block.model_dump = MagicMock(return_value={
        "type": "tool_use", "id": "tool-015",
        "name": "aprovar_pedidos", "input": {"pedido_ids": ["ped-1", "ped-2"]},
    })

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = "2 pedidos aprovados."
    final_block.model_dump = MagicMock(return_value={"type": "text", "text": "2 pedidos aprovados."})

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [final_block]

    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=[resp_tool, resp_final])

    agent = _make_agent(
        tenant=tenant_jmb, gestor=gestor_jmb,
        mock_session=mock_session, mock_conversa_repo=mock_conversa_repo,
        mock_order_service=AsyncMock(), mock_pdf=MagicMock(),
        mock_anthropic=mock_anthropic,
        mock_order_repo=mock_order_repo,
    )

    with patch("src.agents.runtime.agent_gestor.send_whatsapp_message", new=AsyncMock()):
        await agent.responder(mensagem=mensagem_gestor, tenant=tenant_jmb, session=mock_session)

    assert mock_order_repo.aprovar_pedido.call_count == 2
    mock_session.commit.assert_called()


# ─────────────────────────────────────────────
# A_TOOL_COVERAGE — atualizado com aprovar_pedidos
# ─────────────────────────────────────────────

def test_a_tool_coverage_inclui_aprovar_pedidos() -> None:
    """A_TOOL_COVERAGE: aprovar_pedidos deve estar em _TOOLS do AgentGestor."""
    tool_names = {t["name"] for t in _TOOLS}
    assert "aprovar_pedidos" in tool_names, (
        "Gestor precisa poder aprovar pedidos — ausência causou incoerência de UX: "
        "bot pedia confirmação e depois dizia não ter a ferramenta"
    )


@pytest.mark.unit
def test_e0b_tools_antigas_removidas() -> None:
    """E0-B: tools antigas baseadas em pedidos foram removidas do AgentGestor.

    relatorio_representantes: usava RelatorioRepo (tabela pedidos) — removida.
    clientes_inativos_efos: renomeada para clientes_inativos (sem sufixo).
    """
    tool_names = {t["name"] for t in _TOOLS}

    assert "relatorio_representantes" not in tool_names, (
        "E0-B: tool 'relatorio_representantes' deve ter sido removida de _TOOLS. "
        "Use relatorio_vendas_representante_efos para dados EFOS."
    )
    assert "clientes_inativos_efos" not in tool_names, (
        "E0-B: tool 'clientes_inativos_efos' deve ter sido renomeada para 'clientes_inativos'."
    )
    assert "clientes_inativos" in tool_names, (
        "E0-B: tool 'clientes_inativos' deve existir (renomeada de clientes_inativos_efos)."
    )
