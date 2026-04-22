"""Regression: bugs encontrados na homologação do Sprint 6.

Fonte: homologacao_sprint-6.md — bugs reportados pós-aprovação do Evaluator.

Bug H6-B1: AgentGestor não suportava período "ontem" em relatorio_vendas —
  o bot respondia "não consigo filtrar por ontem" e listava apenas
  hoje/semana/mes/30d. Corrigido adicionando "ontem" ao enum e à lógica
  de data_inicio/data_fim em _relatorio_vendas.
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
def test_relatorio_vendas_enum_contem_ontem() -> None:
    """H6-B1: 'ontem' deve estar no enum de períodos da ferramenta relatorio_vendas.

    Antes da correção: enum era ["hoje", "semana", "mes", "30d"].
    Depois: ["hoje", "ontem", "semana", "mes", "30d"].
    """
    source = AGENT_GESTOR_PATH.read_text()
    # Localiza o bloco da ferramenta relatorio_vendas
    assert '"ontem"' in source, (
        "Bug H6-B1 regrediu: 'ontem' ausente no source de agent_gestor.py"
    )
    # Garante que está dentro do enum de periodo (não apenas em description)
    import ast
    tree = ast.parse(source)
    # Procura lista com "ontem" próxima a "hoje" (enum do campo periodo)
    found_enum = False
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if "ontem" in elts and "hoje" in elts and "semana" in elts:
                found_enum = True
                break
    assert found_enum, "Bug H6-B1 regrediu: 'ontem' não encontrado no enum do input_schema de relatorio_vendas"


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
