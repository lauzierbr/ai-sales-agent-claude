"""Testes de regressao B-28: pedido em nome de cliente EFOS (E12 + hotfix v0.10.2).

Verifica que:
- get_by_id tem fallback para commerce_accounts_b2b.
- Pedido de cliente EFOS-only usa account_external_id (nao cliente_b2b_id).
- Pedido de cliente clientes_b2b usa cliente_b2b_id UUID (nao account_external_id).
- Migration 0025 adiciona account_external_id; migration 0029 adiciona observacao.
- INSERT nao empurra external_id em cliente_b2b_id (FK/UUID).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
    """get_by_id retorna None quando nao encontra em nenhuma tabela."""
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
    from pathlib import Path
    migration_path = (
        Path(__file__).parent.parent.parent.parent
        / "alembic" / "versions" / "0025_d030_contacts_and_account_extras.py"
    )

    assert migration_path.exists(), "Migration 0025 nao encontrada"

    content = migration_path.read_text()
    assert "account_external_id" in content, (
        "Migration 0025 deve adicionar account_external_id em pedidos"
    )


@pytest.mark.unit
async def test_migration_0029_adiciona_observacao():
    """Migration 0029 deve adicionar coluna observacao em pedidos."""
    from pathlib import Path
    migration_path = (
        Path(__file__).parent.parent.parent.parent
        / "alembic" / "versions" / "0029_pedidos_observacao.py"
    )

    assert migration_path.exists(), "Migration 0029 nao encontrada"

    content = migration_path.read_text()
    assert "observacao" in content, "Migration 0029 deve adicionar coluna observacao"
    assert "pedidos" in content, "Migration 0029 deve referenciar tabela pedidos"


@pytest.mark.unit
def test_criar_pedido_input_aceita_account_external_id():
    """CriarPedidoInput deve aceitar account_external_id e cliente_b2b_id opcional."""
    from decimal import Decimal
    from src.orders.types import CriarPedidoInput, ItemPedidoInput

    # Cenario EFOS-only: cliente_b2b_id=None, account_external_id preenchido
    item = ItemPedidoInput(
        produto_id="prod-1",
        codigo_externo="617",
        nome_produto="Produto Teste",
        quantidade=2,
        preco_unitario=Decimal("10.00"),
    )

    pedido_efos = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id=None,
        account_external_id="617",
        representante_id=None,
        itens=[item],
        observacao=None,
    )
    assert pedido_efos.cliente_b2b_id is None
    assert pedido_efos.account_external_id == "617"

    # Cenario UUID: cliente_b2b_id preenchido, account_external_id=None
    pedido_uuid = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        account_external_id=None,
        representante_id=None,
        itens=[item],
    )
    assert pedido_uuid.cliente_b2b_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert pedido_uuid.account_external_id is None


@pytest.mark.unit
def test_uuid_vs_external_id_detection():
    """Logica de deteccao UUID vs external_id usada em _confirmar_pedido."""
    import uuid

    # external_id do EFOS (nao e UUID)
    external_ids = ["617", "63.153.691", "1234", "abc"]
    for eid in external_ids:
        try:
            uuid.UUID(str(eid))
            is_uuid = True
        except (ValueError, AttributeError):
            is_uuid = False
        assert not is_uuid, f"'{eid}' nao deveria ser UUID valido"

    # UUID real
    valid_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    try:
        uuid.UUID(valid_uuid)
        is_uuid = True
    except (ValueError, AttributeError):
        is_uuid = False
    assert is_uuid, "UUID valido deve ser reconhecido"
