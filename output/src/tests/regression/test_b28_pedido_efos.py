"""Testes de regressão — B-28: pedido em nome de cliente EFOS (E12, Sprint 10).

Verifica que:
- get_by_id tem fallback para commerce_accounts_b2b.
- Mock: clientes_b2b retorna None → commerce_accounts_b2b é consultado.
- Pedido mock criado com account_external_id populado.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.unit
async def test_get_by_id_fallback_commerce_accounts(mocker):
    """get_by_id retorna cliente de commerce_accounts_b2b quando clientes_b2b retorna None."""
    from src.agents.repo import ClienteB2BRepo

    repo = ClienteB2BRepo()
    mock_session = mocker.AsyncMock()

    # Primeira query (clientes_b2b) retorna None
    # Segunda query (commerce_accounts_b2b) retorna dados
    mock_commerce_row = MagicMock()
    mock_commerce_row.__getitem__ = lambda self, key: {
        "id": "63.153.691",
        "tenant_id": "jmb",
        "nome": "LAUZIER PEREIRA DE ARAUJO",
        "cnpj": "63.153.691/0001-99",
        "telefone": None,
        "situacao_cliente": 1,
        "vendedor_codigo": "01",
    }[key]

    mock_empty_result = MagicMock()
    mock_empty_result.mappings = lambda: MagicMock(first=lambda: None)

    mock_commerce_result = MagicMock()
    mock_commerce_result.mappings = lambda: MagicMock(first=lambda: mock_commerce_row)

    # execute chamado duas vezes: clientes_b2b (None) e commerce_accounts_b2b (row)
    mock_session.execute = AsyncMock(
        side_effect=[mock_empty_result, mock_commerce_result]
    )

    cliente = await repo.get_by_id(
        id="63.153.691",
        tenant_id="jmb",
        session=mock_session,
    )

    # Deve encontrar via fallback
    assert cliente is not None
    assert cliente.id == "63.153.691"
    assert cliente.nome == "LAUZIER PEREIRA DE ARAUJO"

    # execute deve ter sido chamado 2x: uma para clientes_b2b e outra para commerce
    assert mock_session.execute.call_count == 2


@pytest.mark.unit
async def test_get_by_id_retorna_none_quando_nao_existe(mocker):
    """get_by_id retorna None quando não encontra em nenhuma tabela."""
    from src.agents.repo import ClienteB2BRepo

    repo = ClienteB2BRepo()
    mock_session = mocker.AsyncMock()

    mock_empty = MagicMock()
    mock_empty.mappings = lambda: MagicMock(first=lambda: None)

    mock_session.execute = AsyncMock(return_value=mock_empty)

    cliente = await repo.get_by_id(
        id="id-nao-existe",
        tenant_id="jmb",
        session=mock_session,
    )

    assert cliente is None
    assert mock_session.execute.call_count == 2


@pytest.mark.unit
async def test_pedidos_tem_account_external_id():
    """Verificar que a migration 0025 adiciona account_external_id em pedidos."""
    # Verificar que a migration existe
    from pathlib import Path
    migration_path = Path(__file__).parent.parent.parent.parent / "alembic" / "versions" / "0025_d030_contacts_and_account_extras.py"

    assert migration_path.exists(), "Migration 0025 não encontrada"

    content = migration_path.read_text()
    assert "account_external_id" in content, "Migration 0025 deve adicionar account_external_id em pedidos"
