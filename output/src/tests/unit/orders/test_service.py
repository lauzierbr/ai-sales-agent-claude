"""Testes unitários de orders/service.py — OrderService.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orders.types import CriarPedidoInput, ItemPedido, ItemPedidoInput, Pedido, StatusPedido


def _pedido_fake(total: Decimal) -> Pedido:
    return Pedido(
        id="ped-001",
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id=None,
        status=StatusPedido.PENDENTE,
        total_estimado=total,
        pdf_path=None,
        criado_em=datetime(2026, 4, 15, tzinfo=timezone.utc),
        itens=[],
    )


@pytest.mark.unit
async def test_criar_pedido_from_intent_calcula_total() -> None:
    """A12: OrderService.criar_pedido_from_intent calcula total_estimado em Python.

    3 itens com preços conhecidos → total_estimado correto sem acesso ao DB.
    """
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService

    # Itens: 10 x R$29,90 + 5 x R$19,90 + 2 x R$99,50 = 299,00 + 99,50 + 199,00 = 597,50
    pedido_input = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id=None,
        itens=[
            ItemPedidoInput(
                produto_id="p1",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=10,
                preco_unitario=Decimal("29.90"),
            ),
            ItemPedidoInput(
                produto_id="p2",
                codigo_externo="SKU002",
                nome_produto="Condicionador 300ml",
                quantidade=5,
                preco_unitario=Decimal("19.90"),
            ),
            ItemPedidoInput(
                produto_id="p3",
                codigo_externo="SKU003",
                nome_produto="Creme Hidratante 200ml",
                quantidade=2,
                preco_unitario=Decimal("99.50"),
            ),
        ],
    )

    expected_total = Decimal("10") * Decimal("29.90") + Decimal("5") * Decimal("19.90") + Decimal("2") * Decimal("99.50")
    # = 299.00 + 99.50 + 199.00 = 597.50

    # Mock do repo que captura o total_estimado passado
    mock_repo = AsyncMock(spec=OrderRepo)
    captured_total: list[Decimal] = []

    async def mock_criar(tenant_id: str, pedido_input: CriarPedidoInput, total_estimado: Decimal, session: AsyncMock) -> Pedido:
        captured_total.append(total_estimado)
        return _pedido_fake(total_estimado)

    mock_repo.criar_pedido = mock_criar

    service = OrderService(repo=mock_repo, config=OrderConfig())
    session = AsyncMock()

    pedido = await service.criar_pedido_from_intent(pedido_input=pedido_input, session=session)

    assert len(captured_total) == 1
    assert captured_total[0] == expected_total
    assert pedido.total_estimado == expected_total


@pytest.mark.unit
async def test_criar_pedido_from_intent_delega_ao_repo() -> None:
    """OrderService.criar_pedido_from_intent delega persistência ao OrderRepo."""
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService

    mock_repo = AsyncMock(spec=OrderRepo)
    pedido_retornado = _pedido_fake(Decimal("29.90"))
    mock_repo.criar_pedido = AsyncMock(return_value=pedido_retornado)

    pedido_input = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id=None,
        representante_id=None,
        itens=[
            ItemPedidoInput(
                produto_id="p1",
                codigo_externo="SKU001",
                nome_produto="Produto Teste",
                quantidade=1,
                preco_unitario=Decimal("29.90"),
            ),
        ],
    )

    service = OrderService(repo=mock_repo, config=OrderConfig())
    session = AsyncMock()

    pedido = await service.criar_pedido_from_intent(pedido_input=pedido_input, session=session)

    assert mock_repo.criar_pedido.called
    assert pedido.id == "ped-001"


@pytest.mark.unit
async def test_get_pedidos_pendentes_delega_ao_repo() -> None:
    """OrderService.get_pedidos_pendentes delega ao OrderRepo com tenant_id."""
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.service import OrderService

    mock_repo = AsyncMock(spec=OrderRepo)
    mock_repo.get_pedidos_pendentes = AsyncMock(return_value=[])

    service = OrderService(repo=mock_repo, config=OrderConfig())
    session = AsyncMock()

    result = await service.get_pedidos_pendentes(tenant_id="jmb", session=session)

    assert result == []
    mock_repo.get_pedidos_pendentes.assert_called_once_with(
        tenant_id="jmb", session=session
    )
