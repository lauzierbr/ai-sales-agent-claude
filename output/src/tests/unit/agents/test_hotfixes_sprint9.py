"""Testes unitários — Hotfix Sprint 9 (v0.9.1).

Bugs cobertos:
  B-14: listar_pedidos_por_status faz fallback para commerce_orders quando pedidos vazio
  B-15: listar_representantes tool existe em _TOOLS e retorna dados de commerce_vendedores
  B-18: home passa sync_info no contexto (não mostra "Nunca sincronizado")
  B-19: KPIs usam commerce_orders quando pedidos vazio
  B-20: top_produtos faz fallback para commerce_order_items
  B-21: "Representantes" está no menu de navegação (base.html)
  B-22: system prompts dos 3 agentes proibem emojis explicitamente

Todos @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ─────────────────────────────────────────────
# B-22 — system prompts proibem emojis
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_agentcliente_config_proibe_emojis() -> None:
    """B-22: system_prompt_template do AgentCliente deve proibir emojis."""
    from src.agents.config import AgentClienteConfig
    config = AgentClienteConfig()
    assert "NUNCA use emojis" in config.system_prompt_template, (
        "B-22: AgentClienteConfig não proíbe emojis no system_prompt_template"
    )


@pytest.mark.unit
def test_agentrep_config_proibe_emojis() -> None:
    """B-22: system_prompt_template do AgentRep deve proibir emojis."""
    from src.agents.config import AgentRepConfig
    config = AgentRepConfig()
    assert "NUNCA use emojis" in config.system_prompt_template, (
        "B-22: AgentRepConfig não proíbe emojis no system_prompt_template"
    )


@pytest.mark.unit
def test_agentgestor_config_proibe_emojis() -> None:
    """B-22: system_prompt_template do AgentGestor deve proibir emojis."""
    from src.agents.config import AgentGestorConfig
    config = AgentGestorConfig()
    assert "NUNCA use emojis" in config.system_prompt_template, (
        "B-22: AgentGestorConfig não proíbe emojis no system_prompt_template"
    )


# ─────────────────────────────────────────────
# B-15 — listar_representantes em _TOOLS
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_listar_representantes_em_tools() -> None:
    """B-15: _TOOLS do AgentGestor deve conter listar_representantes."""
    from src.agents.runtime.agent_gestor import _TOOLS
    nomes = [t["name"] for t in _TOOLS]
    assert "listar_representantes" in nomes, (
        "B-15: tool listar_representantes ausente em _TOOLS do AgentGestor"
    )


@pytest.mark.unit
def test_listar_representantes_no_system_prompt() -> None:
    """B-15: system_prompt_template do AgentGestor deve anunciar listar_representantes."""
    from src.agents.config import AgentGestorConfig
    config = AgentGestorConfig()
    assert "listar_representantes" in config.system_prompt_template, (
        "B-15: listar_representantes não anunciada no system_prompt do AgentGestor"
    )


@pytest.mark.unit
async def test_listar_representantes_retorna_dados(mocker: Any) -> None:
    """B-15: _listar_representantes retorna lista de representantes via commerce_vendedores."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    from src.agents.config import AgentGestorConfig
    from src.agents.repo import ClienteB2BRepo, ConversaRepo, RelatorioRepo
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.agents.types import Gestor
    from src.commerce.repo import CommerceRepo
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.tenants.types import Tenant

    mock_session = AsyncMock()

    # Simula resultado do execute()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"ve_codigo": "V01", "ve_nome": "Rondinele Ritter", "ve_situacaovendedor": 1},
        {"ve_codigo": "V02", "ve_nome": "Carlos Souza", "ve_situacaovendedor": 1},
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    tenant = Tenant(
        id="jmb", nome="JMB Distribuidora", cnpj="00.000.000/0001-00",
        ativo=True, whatsapp_number="5519999999999",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    gestor = Gestor(
        id="g-01", tenant_id="jmb", telefone="5519000000000",
        nome="Lauzier", ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    agent = AgentGestor(
        order_service=AsyncMock(spec=OrderService),
        conversa_repo=AsyncMock(spec=ConversaRepo),
        pdf_generator=MagicMock(spec=PDFGenerator),
        config=AgentGestorConfig(),
        gestor=gestor,
        anthropic_client=AsyncMock(),
        commerce_repo=AsyncMock(spec=CommerceRepo),
    )

    resultado = await agent._listar_representantes(
        nome=None, tenant_id="jmb", session=mock_session
    )

    assert "representantes" in resultado
    assert resultado["total"] == 2
    nomes = [r["nome"] for r in resultado["representantes"]]
    assert "Rondinele Ritter" in nomes


# ─────────────────────────────────────────────
# B-14 — listar_pedidos_por_status fallback commerce_orders
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_listar_pedidos_usa_commerce_quando_vazio(mocker: Any) -> None:
    """B-14: quando OrderRepo retorna vazio, usa CommerceRepo.listar_pedidos_efos."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from src.agents.config import AgentGestorConfig
    from src.agents.repo import ClienteB2BRepo, ConversaRepo, RelatorioRepo
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.agents.types import Gestor
    from src.commerce.repo import CommerceRepo
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.tenants.types import Tenant

    mock_order_repo = AsyncMock(spec=OrderRepo)
    mock_order_repo.listar_por_tenant_status.return_value = []  # B-14: retorna vazio

    mock_commerce_repo = AsyncMock(spec=CommerceRepo)
    mock_commerce_repo.listar_pedidos_efos.return_value = [
        {
            "id": "1234",
            "cliente_nome": "Distribuidora XYZ",
            "representante_nome": "Rondinele",
            "total_estimado": Decimal("1500.00"),
            "status": "confirmado",
            "criado_em": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "fonte": "commerce_orders",
        }
    ]

    tenant = Tenant(
        id="jmb", nome="JMB Distribuidora", cnpj="00.000.000/0001-00",
        ativo=True, whatsapp_number="5519999999999",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    gestor = Gestor(
        id="g-01", tenant_id="jmb", telefone="5519000000000",
        nome="Lauzier", ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    agent = AgentGestor(
        order_service=AsyncMock(spec=OrderService),
        conversa_repo=AsyncMock(spec=ConversaRepo),
        pdf_generator=MagicMock(spec=PDFGenerator),
        config=AgentGestorConfig(),
        gestor=gestor,
        anthropic_client=AsyncMock(),
        order_repo=mock_order_repo,
        commerce_repo=mock_commerce_repo,
    )

    mock_session = AsyncMock()
    resultado = await agent._listar_pedidos_por_status(
        status=None, dias=30, limit=20, tenant_id="jmb", session=mock_session
    )

    # Deve ter chamado commerce_repo.listar_pedidos_efos (fallback B-14)
    mock_commerce_repo.listar_pedidos_efos.assert_called_once()
    assert len(resultado) == 1
    assert resultado[0]["cliente_nome"] == "Distribuidora XYZ"
    assert resultado[0]["fonte"] == "commerce_orders"


# ─────────────────────────────────────────────
# B-20 — top_produtos_por_periodo fallback commerce_order_items
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_top_produtos_fallback_commerce(mocker: Any) -> None:
    """B-20: top_produtos_por_periodo usa commerce_order_items quando itens_pedido vazio."""
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock, call

    from src.agents.repo import RelatorioRepo

    repo = RelatorioRepo()
    mock_session = AsyncMock()

    # Primeira execute (itens_pedido) retorna vazio
    mock_result_empty = MagicMock()
    mock_result_empty.mappings.return_value.all.return_value = []

    # Segunda execute (commerce_order_items) retorna dados
    mock_result_commerce = MagicMock()
    mock_result_commerce.mappings.return_value.all.return_value = [
        {
            "produto_nome": "Escova Quadrada 571",
            "quantidade_total": 150,
            "valor_total": Decimal("2250.00"),
        },
        {
            "produto_nome": "Shampoo Natura 300ml",
            "quantidade_total": 80,
            "valor_total": Decimal("1200.00"),
        },
    ]

    # A primeira chamada retorna vazio, a segunda retorna dados
    mock_session.execute = AsyncMock(
        side_effect=[mock_result_empty, mock_result_commerce]
    )

    resultado = await repo.top_produtos_por_periodo(
        tenant_id="jmb", dias=30, limite=5, session=mock_session
    )

    # Deve ter feito 2 executes (uma para itens_pedido, outra fallback)
    assert mock_session.execute.call_count == 2
    assert len(resultado) == 2
    assert resultado[0]["produto_nome"] == "Escova Quadrada 571"


# ─────────────────────────────────────────────
# B-21 — menu de navegação contém Representantes
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_base_html_contem_link_representantes() -> None:
    """B-21: base.html deve conter link para /dashboard/representantes no menu."""
    base_html = Path(__file__).parents[3] / "dashboard" / "templates" / "base.html"
    assert base_html.exists(), f"base.html não encontrado em {base_html}"
    content = base_html.read_text(encoding="utf-8")
    assert "/dashboard/representantes" in content, (
        "B-21: link /dashboard/representantes ausente no menu de navegação (base.html)"
    )


# ─────────────────────────────────────────────
# B-18 — home endpoint passa sync_info
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_kpis_usa_janela_mensal() -> None:
    """v0.9.4: _get_kpis usa janela mensal (não diária) e timestamp do último
    sync EFOS bem-sucedido como 'atualizado em' (B-18 removido em v0.9.4)."""
    import inspect
    from src.dashboard.ui import _get_kpis
    source = inspect.getsource(_get_kpis)
    assert "mes_inicio" in source and "now.replace(day=1" in source, (
        "_get_kpis deve agregar pelo mês corrente (day=1)"
    )
    assert "sync_runs" in source and "status = 'success'" in source, (
        "_get_kpis deve usar último sync_runs success como timestamp 'atualizado em'"
    )


@pytest.mark.unit
def test_home_nao_passa_sync_info() -> None:
    """v0.9.4: bloco 'Última sincronização EFOS' removido — home() não deve mais
    calcular nem passar sync_info no contexto."""
    import inspect
    from src.dashboard.ui import home
    source = inspect.getsource(home)
    assert "sync_info" not in source, (
        "v0.9.4: home() não deve mais carregar sync_info "
        "(bloco removido — info migrou para o card 'Atualizado no sync EFOS')"
    )


# ─────────────────────────────────────────────
# Cobertura geral — ferramenta anunciada = ferramenta em _TOOLS
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_tool_coverage_listar_representantes_e_anunciada() -> None:
    """B-15: listar_representantes anunciada no system_prompt E existe em _TOOLS."""
    from src.agents.config import AgentGestorConfig
    from src.agents.runtime.agent_gestor import _TOOLS

    config = AgentGestorConfig()
    tool_names = {t["name"] for t in _TOOLS}

    assert "listar_representantes" in config.system_prompt_template
    assert "listar_representantes" in tool_names


from typing import Any  # noqa: E402 — importado ao final para não poluir escopo de fixtures
