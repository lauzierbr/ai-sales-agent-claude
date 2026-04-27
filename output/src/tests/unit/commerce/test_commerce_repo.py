"""Testes unitários de commerce/repo.py — CommerceRepo.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    return row


@pytest.mark.unit
async def test_relatorio_vendas_representante_filtra_tenant() -> None:
    """A17: relatorio_vendas_representante filtra por tenant_id."""
    from src.commerce.repo import CommerceRepo

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = _make_row(
        qtde_pedidos=5,
        total_vendido=Decimal("10000.00"),
        clientes_raw=["Farmácia A", "Drogaria B"],
    )
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CommerceRepo()
    result = await repo.relatorio_vendas_representante(
        tenant_id="jmb",
        vendedor_id="001",
        mes=4,
        ano=2026,
        session=mock_session,
    )

    assert result["qtde_pedidos"] == 5
    assert result["total_vendido"] == Decimal("10000.00")
    assert "Farmácia A" in result["clientes"]

    # Verifica filtro tenant_id
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_relatorio_vendas_representante_sem_dados() -> None:
    """relatorio_vendas_representante retorna zeros quando sem dados."""
    from src.commerce.repo import CommerceRepo

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CommerceRepo()
    result = await repo.relatorio_vendas_representante(
        tenant_id="jmb",
        vendedor_id="999",
        mes=1,
        ano=2026,
        session=mock_session,
    )

    assert result["total_vendido"] == Decimal("0")
    assert result["qtde_pedidos"] == 0
    assert result["clientes"] == []


@pytest.mark.unit
async def test_relatorio_vendas_cidade_filtra_tenant() -> None:
    """A17: relatorio_vendas_cidade filtra por tenant_id."""
    from src.commerce.repo import CommerceRepo

    mock_row = _make_row(cliente="Farmácia Central", total=Decimal("5000.00"))
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CommerceRepo()
    result = await repo.relatorio_vendas_cidade(
        tenant_id="jmb",
        cidade="VINHEDO",
        mes=4,
        ano=2026,
        session=mock_session,
    )

    assert len(result) == 1
    assert result[0]["cliente"] == "Farmácia Central"
    assert result[0]["total"] == Decimal("5000.00")

    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"
    assert call_params["cidade"] == "VINHEDO"


@pytest.mark.unit
async def test_listar_clientes_inativos_filtra_tenant() -> None:
    """A17: listar_clientes_inativos filtra por tenant_id."""
    from src.commerce.repo import CommerceRepo

    mock_row = _make_row(
        nome="Cliente Inativo",
        cnpj="12.345.678/0001-90",
        cidade="CAMPINAS",
    )
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CommerceRepo()
    result = await repo.listar_clientes_inativos(
        tenant_id="jmb",
        cidade=None,
        session=mock_session,
    )

    assert len(result) == 1
    assert result[0]["nome"] == "Cliente Inativo"
    assert result[0]["cidade"] == "CAMPINAS"

    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_listar_clientes_inativos_com_cidade_filtra() -> None:
    """listar_clientes_inativos com cidade filtra por cidade UPPERCASE."""
    from src.commerce.repo import CommerceRepo

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CommerceRepo()
    await repo.listar_clientes_inativos(
        tenant_id="jmb",
        cidade="VINHEDO",
        session=mock_session,
    )

    call_params = mock_session.execute.call_args[0][1]
    assert call_params["cidade"] == "VINHEDO"
