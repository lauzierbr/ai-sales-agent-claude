"""Testes unitários de integrations/connectors/efos_backup/publish.py.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call

import pytest


def _make_product(tenant_id: str = "jmb", n: int = 1):
    from src.commerce.types import CommerceProduct
    return CommerceProduct(
        tenant_id=tenant_id,
        external_id=f"P{n:03d}",
        codigo=f"P{n:03d}",
        nome=f"Produto {n}",
        descricao=None,
        unidade="UN",
        preco_padrao=Decimal("10.00"),
        ativo=True,
        snapshot_checksum="abc123",
    )


@pytest.mark.unit
async def test_publish_rollback_em_falha() -> None:
    """A10: publish faz rollback total quando um INSERT falha."""
    from src.integrations.connectors.efos_backup.publish import publish

    mock_session = AsyncMock()
    execute_count = 0

    async def mock_execute(query, params=None):
        nonlocal execute_count
        execute_count += 1
        # Falha na 4ª chamada (após 3 DELETEs + 1 INSERT)
        if execute_count == 4:
            raise RuntimeError("Erro simulado de INSERT")
        return MagicMock()

    mock_session.execute = mock_execute
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    products = [_make_product()]

    with pytest.raises(RuntimeError, match="Erro simulado de INSERT"):
        await publish(
            tenant_id="jmb",
            products=products,
            accounts=[],
            orders=[],
            order_items=[],
            inventory=[],
            sales_history=[],
            vendedores=[],
            session=mock_session,
        )

    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()


@pytest.mark.unit
async def test_publish_retorna_total_rows() -> None:
    """publish retorna total de rows inseridas."""
    from src.integrations.connectors.efos_backup.publish import publish
    from src.commerce.types import CommerceVendedor

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    products = [_make_product(n=1), _make_product(n=2)]
    vendedor = CommerceVendedor(
        tenant_id="jmb",
        external_id="001",
        ve_codigo="001",
        ve_nome="Rondinele",
        snapshot_checksum="abc123",
    )

    total = await publish(
        tenant_id="jmb",
        products=products,
        accounts=[],
        orders=[],
        order_items=[],
        inventory=[],
        sales_history=[],
        vendedores=[vendedor],
        session=mock_session,
    )

    assert total == 3  # 2 products + 1 vendedor


@pytest.mark.unit
async def test_publish_filtra_por_tenant_id() -> None:
    """publish executa DELETE WHERE tenant_id para cada tabela commerce_*."""
    from src.integrations.connectors.efos_backup.publish import publish

    mock_session = AsyncMock()
    executed_queries: list[str] = []

    async def mock_execute(query, params=None):
        executed_queries.append(str(query))
        return MagicMock()

    mock_session.execute = mock_execute
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    await publish(
        tenant_id="jmb",
        products=[],
        accounts=[],
        orders=[],
        order_items=[],
        inventory=[],
        sales_history=[],
        vendedores=[],
        session=mock_session,
    )

    # E8 DT-2: commerce_products usa UPSERT agora (não DELETE+INSERT)
    # Verifica que os DELETEs foram executados para as 6 tabelas restantes
    delete_queries = [q for q in executed_queries if "DELETE" in q.upper()]
    assert len(delete_queries) >= 6, (
        "Devem existir DELETEs para 6 tabelas commerce_* "
        "(commerce_products usa UPSERT — DT-2 E8)"
    )
    # Verifica que commerce_products NÃO é deletado
    products_delete = [q for q in delete_queries if "commerce_products" in q.lower()]
    assert len(products_delete) == 0, (
        "commerce_products não deve ter DELETE (preserva embedding via UPSERT — DT-2)"
    )
