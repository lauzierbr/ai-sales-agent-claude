"""Regression: bugs encontrados na homologação do Sprint 6.

Fonte: homologacao_sprint-6.md — bugs reportados pós-aprovação do Evaluator.

Bug H6-B1: AgentGestor não suportava período "ontem" em relatorio_vendas —
  o bot respondia "não consigo filtrar por ontem" e listava apenas
  hoje/semana/mes/30d. Corrigido adicionando "ontem" à lógica de data_inicio/data_fim.

Bug H6-B2: relatorio_vendas recusava períodos arbitrários como "3 dias" —
  o enum restritivo impedia o gestor de perguntar "últimos 3 dias", "últimos 10 dias" etc.
  Corrigido removendo o enum e aceitando "Nd" (ex: "3d", "10d", "90d") na tool e na lógica.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
AGENT_GESTOR_PATH = REPO_ROOT / "output" / "src" / "agents" / "runtime" / "agent_gestor.py"


# ─────────────────────────────────────────────
# H6-B1: período "ontem" em relatorio_vendas
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_relatorio_vendas_suporta_periodo_ontem() -> None:
    """H6-B1: _relatorio_vendas deve ter branch explícita para período 'ontem'.

    Antes da correção: período 'ontem' não era tratado (caia no else do 30d).
    Depois: branch elif periodo == "ontem" presente, com cálculo correto de data_fim.
    """
    source = AGENT_GESTOR_PATH.read_text()
    assert '"ontem"' in source, (
        "Bug H6-B1 regrediu: 'ontem' ausente no source de agent_gestor.py"
    )
    # Garante que existe um branch elif para "ontem" na lógica (não apenas na description)
    assert 'periodo == "ontem"' in source, (
        "Bug H6-B1 regrediu: branch 'elif periodo == \"ontem\"' ausente em _relatorio_vendas"
    )


@pytest.mark.unit
async def test_relatorio_vendas_ontem_calcula_intervalo_correto() -> None:
    """H6-B1: _relatorio_vendas com periodo='ontem' deve calcular data_inicio/data_fim
    como ontem 00:00–23:59:59.999999, não vazar para hoje."""
    from src.agents.config import AgentGestorConfig
    from src.agents.types import Gestor
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService
    from src.orders.runtime.pdf_generator import PDFGenerator

    from datetime import datetime, timezone as _tz
    gestor = Gestor(
        id="g1",
        tenant_id="jmb",
        telefone="5519999999999",
        nome="Gestor Teste",
        ativo=True,
        usuario_id=None,
        criado_em=datetime.now(_tz.utc),
    )

    mock_relatorio_repo = AsyncMock()
    mock_relatorio_repo.totais_periodo = AsyncMock(
        return_value={"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0}
    )

    from src.agents.runtime.agent_gestor import AgentGestor

    agent = AgentGestor(
        order_service=AsyncMock(),
        conversa_repo=AsyncMock(),
        pdf_generator=MagicMock(),
        config=AgentGestorConfig(),
        gestor=gestor,
        catalog_service=AsyncMock(),
        redis_client=AsyncMock(),
        cliente_b2b_repo=AsyncMock(),
        relatorio_repo=mock_relatorio_repo,
    )

    mock_session = AsyncMock()
    await agent._relatorio_vendas("ontem", "totais", "jmb", mock_session)

    assert mock_relatorio_repo.totais_periodo.called, "totais_periodo não foi chamado"
    call_kwargs = mock_relatorio_repo.totais_periodo.call_args.kwargs
    data_inicio: datetime = call_kwargs["data_inicio"]
    data_fim: datetime = call_kwargs["data_fim"]

    now = datetime.now(timezone.utc)
    hoje_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_inicio = hoje_inicio - timedelta(days=1)

    # data_inicio deve ser ontem às 00:00:00
    assert data_inicio.date() == ontem_inicio.date(), (
        f"data_inicio esperado ontem ({ontem_inicio.date()}), got {data_inicio.date()}"
    )
    assert data_inicio.hour == 0 and data_inicio.minute == 0, (
        f"data_inicio deve ser início do dia: {data_inicio}"
    )

    # data_fim deve ser antes de hoje 00:00:00 (ontem 23:59:59.999999)
    assert data_fim < hoje_inicio, (
        f"data_fim ({data_fim}) não deve ultrapassar início de hoje ({hoje_inicio})"
    )
    assert data_fim.date() == ontem_inicio.date(), (
        f"data_fim deve ser ontem ({ontem_inicio.date()}), got {data_fim.date()}"
    )


# ─────────────────────────────────────────────
# H6-B2: períodos arbitrários "Nd" em relatorio_vendas
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_relatorio_vendas_tool_sem_enum_restritivo() -> None:
    """H6-B2: tool relatorio_vendas não deve ter 'enum' restritivo no campo periodo.

    Antes da correção: enum era ["hoje", "ontem", "semana", "mes", "30d"].
    Depois: campo periodo é string livre com description explicativa.
    """
    source = AGENT_GESTOR_PATH.read_text()
    import ast
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "name" in keys and "input_schema" in keys:
                # Procura dict da tool relatorio_vendas
                for i, k in enumerate(node.keys):
                    if isinstance(k, ast.Constant) and k.value == "name":
                        val = node.values[i]
                        if isinstance(val, ast.Constant) and val.value == "relatorio_vendas":
                            # Garante que não há lista enum com apenas os 5 períodos fixos
                            tool_source = ast.unparse(node)
                            assert '"hoje", "ontem", "semana", "mes", "30d"' not in tool_source, (
                                "Bug H6-B2 regrediu: enum restritivo ainda presente em relatorio_vendas"
                            )
                            return

    pytest.fail("Tool relatorio_vendas não encontrada no source de agent_gestor.py")


@pytest.mark.unit
async def test_relatorio_vendas_periodo_3d_calcula_intervalo_correto() -> None:
    """H6-B2: _relatorio_vendas com periodo='3d' deve cobrir os últimos 3 dias."""
    from src.agents.config import AgentGestorConfig
    from src.agents.types import Gestor

    gestor = Gestor(
        id="g1",
        tenant_id="jmb",
        telefone="5519999999999",
        nome="Gestor Teste",
        ativo=True,
        usuario_id=None,
        criado_em=datetime.now(timezone.utc),
    )

    mock_relatorio_repo = AsyncMock()
    mock_relatorio_repo.totais_periodo = AsyncMock(
        return_value={"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0}
    )

    from src.agents.runtime.agent_gestor import AgentGestor

    agent = AgentGestor(
        order_service=AsyncMock(),
        conversa_repo=AsyncMock(),
        pdf_generator=MagicMock(),
        config=AgentGestorConfig(),
        gestor=gestor,
        catalog_service=AsyncMock(),
        redis_client=AsyncMock(),
        cliente_b2b_repo=AsyncMock(),
        relatorio_repo=mock_relatorio_repo,
    )

    mock_session = AsyncMock()
    await agent._relatorio_vendas("3d", "totais", "jmb", mock_session)

    assert mock_relatorio_repo.totais_periodo.called
    call_kwargs = mock_relatorio_repo.totais_periodo.call_args.kwargs
    data_inicio: datetime = call_kwargs["data_inicio"]
    data_fim: datetime = call_kwargs["data_fim"]

    now = datetime.now(timezone.utc)
    esperado_inicio = now - timedelta(days=3)

    # Tolerância de 5s para execução do teste
    diff = abs((data_inicio - esperado_inicio).total_seconds())
    assert diff < 5, f"data_inicio esperado ~3 dias atrás, got {data_inicio} (diff {diff:.1f}s)"
    assert data_fim >= data_inicio, "data_fim deve ser >= data_inicio"


@pytest.mark.unit
async def test_relatorio_vendas_periodo_arbitrario_nao_trava() -> None:
    """H6-B2: período desconhecido faz fallback para 30d sem exceção."""
    from src.agents.config import AgentGestorConfig
    from src.agents.types import Gestor

    gestor = Gestor(
        id="g1",
        tenant_id="jmb",
        telefone="5519999999999",
        nome="Gestor Teste",
        ativo=True,
        usuario_id=None,
        criado_em=datetime.now(timezone.utc),
    )

    mock_relatorio_repo = AsyncMock()
    mock_relatorio_repo.totais_periodo = AsyncMock(
        return_value={"total_gmv": 0, "n_pedidos": 0, "ticket_medio": 0}
    )

    from src.agents.runtime.agent_gestor import AgentGestor

    agent = AgentGestor(
        order_service=AsyncMock(),
        conversa_repo=AsyncMock(),
        pdf_generator=MagicMock(),
        config=AgentGestorConfig(),
        gestor=gestor,
        catalog_service=AsyncMock(),
        redis_client=AsyncMock(),
        cliente_b2b_repo=AsyncMock(),
        relatorio_repo=mock_relatorio_repo,
    )

    mock_session = AsyncMock()
    # Período inválido/desconhecido — não deve lançar exceção
    await agent._relatorio_vendas("quinzena", "totais", "jmb", mock_session)

    assert mock_relatorio_repo.totais_periodo.called, "totais_periodo deve ser chamado mesmo com período inválido"
