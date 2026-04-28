"""Testes unitários dos novos tools EFOS do AgentGestor.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_gestor_agent(**kwargs):
    """Cria AgentGestor com dependências mockadas."""
    from src.agents.runtime.agent_gestor import AgentGestor

    defaults = {
        "order_service": MagicMock(),
        "conversa_repo": MagicMock(),
        "pdf_generator": MagicMock(),
        "config": MagicMock(),
        "gestor": MagicMock(),
        "anthropic_client": MagicMock(),
        "redis_client": None,
    }
    defaults.update(kwargs)
    return AgentGestor(**defaults)


# ─────────────────────────────────────────────────────────────
# A18 — Fuzzy match representante
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_fuzzy_match_representante() -> None:
    """A18: fuzzy match retorna mesmo ve_codigo para variações de nome."""
    agent = _make_gestor_agent()

    # Mock de sessão com um vendedor
    mock_row = MagicMock()
    row_data = {"ve_codigo": "001", "ve_nome": "Rondinele Ritter"}
    mock_row.__getitem__ = lambda self, key: row_data[key]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Variações de nome que devem all match para ve_codigo "001"
    variaciones = ["RONDINELE", "Rondinele Ritter", "rondinele"]

    for nome in variaciones:
        result = await agent._fuzzy_match_vendedor(nome, "jmb", mock_session)
        assert result == "001", f"'{nome}' deve retornar '001', obteve '{result}'"


@pytest.mark.unit
async def test_fuzzy_match_nenhum_resultado() -> None:
    """fuzzy_match_vendedor retorna None quando similaridade < 80%."""
    agent = _make_gestor_agent()

    mock_row = MagicMock()
    row_data = {"ve_codigo": "001", "ve_nome": "Rondinele Ritter"}
    mock_row.__getitem__ = lambda self, key: row_data[key]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await agent._fuzzy_match_vendedor("Zézinho Completamente Diferente", "jmb", mock_session)
    assert result is None


# ─────────────────────────────────────────────────────────────
# A19 — Normalização cidade → UPPERCASE
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_normalizacao_cidade() -> None:
    """A19: _relatorio_vendas_cidade_efos normaliza cidade para UPPERCASE."""
    from src.commerce.repo import CommerceRepo

    mock_commerce_repo = AsyncMock(spec=CommerceRepo)
    mock_commerce_repo.relatorio_vendas_cidade = AsyncMock(return_value=[
        {"cliente": "Farmácia", "total": Decimal("1000.00")}
    ])

    agent = _make_gestor_agent(commerce_repo=mock_commerce_repo)
    mock_session = AsyncMock()

    await agent._relatorio_vendas_cidade_efos(
        cidade="Vinhedo",
        mes=4,
        ano=2026,
        tenant_id="jmb",
        session=mock_session,
    )

    call_kwargs = mock_commerce_repo.relatorio_vendas_cidade.call_args[1]
    assert call_kwargs["cidade"] == "VINHEDO"

    await agent._relatorio_vendas_cidade_efos(
        cidade="campinas",
        mes=4,
        ano=2026,
        tenant_id="jmb",
        session=mock_session,
    )

    call_kwargs = mock_commerce_repo.relatorio_vendas_cidade.call_args[1]
    assert call_kwargs["cidade"] == "CAMPINAS"


# ─────────────────────────────────────────────────────────────
# A20 — Normalização de mês
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_normalizacao_mes_abril_string() -> None:
    """A20: _normalizar_mes("abril") → 4."""
    from src.agents.runtime.agent_gestor import AgentGestor

    assert AgentGestor._normalizar_mes("abril") == 4


@pytest.mark.unit
def test_normalizacao_mes_mes_4() -> None:
    """A20: _normalizar_mes("mes 4") → 4."""
    from src.agents.runtime.agent_gestor import AgentGestor

    assert AgentGestor._normalizar_mes("mes 4") == 4


@pytest.mark.unit
def test_normalizacao_mes_string_numero() -> None:
    """A20: _normalizar_mes("4") → 4."""
    from src.agents.runtime.agent_gestor import AgentGestor

    assert AgentGestor._normalizar_mes("4") == 4


@pytest.mark.unit
def test_normalizacao_mes_int() -> None:
    """A20: _normalizar_mes(4) → 4."""
    from src.agents.runtime.agent_gestor import AgentGestor

    assert AgentGestor._normalizar_mes(4) == 4


@pytest.mark.unit
def test_normalizacao_mes_todos_nomes() -> None:
    """_normalizar_mes reconhece todos os nomes de mês em português."""
    from src.agents.runtime.agent_gestor import AgentGestor

    meses = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    for nome, numero in meses.items():
        assert AgentGestor._normalizar_mes(nome) == numero, f"Falhou para '{nome}'"


@pytest.mark.unit
def test_normalizacao_mes_invalido_lanca_erro() -> None:
    """_normalizar_mes lança ValueError para entrada inválida."""
    from src.agents.runtime.agent_gestor import AgentGestor

    with pytest.raises(ValueError):
        AgentGestor._normalizar_mes("mês_invalido_xpto")


# ─────────────────────────────────────────────────────────────
# A_TOOL_COVERAGE — tools EFOS em _TOOLS
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_tools_efos_em_tools_list() -> None:
    """A_TOOL_COVERAGE: as 3 tools EFOS existem em _TOOLS do AgentGestor."""
    from src.agents.runtime.agent_gestor import _TOOLS

    tool_names = {t["name"] for t in _TOOLS}

    assert "relatorio_vendas_representante_efos" in tool_names, (
        "Tool 'relatorio_vendas_representante_efos' ausente em _TOOLS"
    )
    assert "relatorio_vendas_cidade_efos" in tool_names, (
        "Tool 'relatorio_vendas_cidade_efos' ausente em _TOOLS"
    )
    # E0-B Sprint 9: clientes_inativos_efos foi renomeada para clientes_inativos (sem sufixo)
    assert "clientes_inativos" in tool_names, (
        "Tool 'clientes_inativos' (renomeada de clientes_inativos_efos) ausente em _TOOLS"
    )
    # clientes_inativos_efos com sufixo NÃO deve mais existir
    assert "clientes_inativos_efos" not in tool_names, (
        "E0-B: tool 'clientes_inativos_efos' foi renomeada — não deve mais existir em _TOOLS."
    )


@pytest.mark.unit
async def test_clientes_inativos_efos_sem_cidade() -> None:
    """clientes_inativos_efos sem cidade passa cidade=None para CommerceRepo."""
    from src.commerce.repo import CommerceRepo

    mock_commerce_repo = AsyncMock(spec=CommerceRepo)
    mock_commerce_repo.listar_clientes_inativos = AsyncMock(return_value=[])

    agent = _make_gestor_agent(commerce_repo=mock_commerce_repo)
    mock_session = AsyncMock()

    await agent._clientes_inativos_efos(
        cidade=None,
        tenant_id="jmb",
        session=mock_session,
    )

    mock_commerce_repo.listar_clientes_inativos.assert_called_once_with(
        tenant_id="jmb",
        cidade=None,
        session=mock_session,
    )


@pytest.mark.unit
async def test_clientes_inativos_efos_com_cidade_uppercase() -> None:
    """clientes_inativos_efos com cidade converte para UPPERCASE."""
    from src.commerce.repo import CommerceRepo

    mock_commerce_repo = AsyncMock(spec=CommerceRepo)
    mock_commerce_repo.listar_clientes_inativos = AsyncMock(return_value=[])

    agent = _make_gestor_agent(commerce_repo=mock_commerce_repo)
    mock_session = AsyncMock()

    await agent._clientes_inativos_efos(
        cidade="vinhedo",
        tenant_id="jmb",
        session=mock_session,
    )

    call_kwargs = mock_commerce_repo.listar_clientes_inativos.call_args[1]
    assert call_kwargs["cidade"] == "VINHEDO"
