"""Testes unitários para fallback de clientes_b2b → commerce_accounts_b2b (E1b — Sprint 9).

Cobre:
  - Mock clientes_b2b retornando lista vazia → CommerceRepo.buscar_clientes_commerce chamado
  - Mock clientes_b2b retornando resultado → CommerceRepo NÃO chamado
  - Resultado normalizado para estrutura compatível com AgentGestor
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_commerce_chamado_quando_clientes_b2b_vazio() -> None:
    """E1b: quando clientes_b2b retorna vazio, CommerceRepo.buscar_clientes_commerce é chamado."""
    from src.agents.repo import ClienteB2BRepo

    repo = ClienteB2BRepo()
    mock_session = AsyncMock()

    # clientes_b2b retorna vazio
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    # commerce_repo retorna um cliente
    mock_commerce = AsyncMock()
    mock_commerce.buscar_clientes_commerce = AsyncMock(
        return_value=[
            {
                "id": "ext-cli-001",
                "nome": "Farmácia Central EFOS",
                "cnpj": "12.345.678/0001-99",
                "telefone": None,
                "representante_id": None,
                "codigo": "CLI001",
                "cidade": "VINHEDO",
                "ativo": True,
                "fonte": "commerce_accounts_b2b",
            }
        ]
    )

    resultados = await repo.buscar_todos_com_representante(
        tenant_id="jmb",
        query="farmacia",
        session=mock_session,
        commerce_repo=mock_commerce,
    )

    # CommerceRepo DEVE ter sido chamado (clientes_b2b estava vazio)
    mock_commerce.buscar_clientes_commerce.assert_called_once()
    assert len(resultados) == 1
    assert resultados[0]["nome"] == "Farmácia Central EFOS"
    assert resultados[0].get("fonte") == "commerce_accounts_b2b"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_commerce_nao_chamado_quando_clientes_b2b_tem_resultado() -> None:
    """E1b: quando clientes_b2b retorna resultado, CommerceRepo NÃO é chamado."""
    from src.agents.repo import ClienteB2BRepo

    repo = ClienteB2BRepo()
    mock_session = AsyncMock()

    # clientes_b2b retorna um cliente
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": "cli-001",
            "nome": "Farmácia São Paulo",
            "cnpj": "12.345.678/0001-99",
            "telefone": "5519991111111",
            "representante_id": "rep-001",
            "representante_nome": "João Rep",
        }
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_commerce = AsyncMock()
    mock_commerce.buscar_clientes_commerce = AsyncMock(return_value=[])

    resultados = await repo.buscar_todos_com_representante(
        tenant_id="jmb",
        query="farmacia",
        session=mock_session,
        commerce_repo=mock_commerce,
    )

    # CommerceRepo NÃO deve ter sido chamado
    mock_commerce.buscar_clientes_commerce.assert_not_called()
    assert len(resultados) == 1
    assert resultados[0]["nome"] == "Farmácia São Paulo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_commerce_sem_commerce_repo() -> None:
    """E1b: sem commerce_repo, retorna lista vazia quando clientes_b2b é vazio."""
    from src.agents.repo import ClienteB2BRepo

    repo = ClienteB2BRepo()
    mock_session = AsyncMock()

    # clientes_b2b retorna vazio
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    resultados = await repo.buscar_todos_com_representante(
        tenant_id="jmb",
        query="farmacia",
        session=mock_session,
        commerce_repo=None,  # sem fallback
    )

    assert resultados == []
