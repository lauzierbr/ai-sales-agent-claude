"""Testes unitários de orders/types.py — enums e modelos Pydantic.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.orders.types import (
    CriarPedidoInput,
    ItemPedido,
    ItemPedidoInput,
    Pedido,
    StatusPedido,
)


@pytest.mark.unit
def test_status_pedido_valores() -> None:
    """StatusPedido tem os 3 valores esperados."""
    assert StatusPedido.PENDENTE.value == "pendente"
    assert StatusPedido.CONFIRMADO.value == "confirmado"
    assert StatusPedido.CANCELADO.value == "cancelado"


@pytest.mark.unit
def test_item_pedido_input_parsing() -> None:
    """ItemPedidoInput aceita Decimal para preco_unitario."""
    item = ItemPedidoInput(
        produto_id="prod-1",
        codigo_externo="SKU001",
        nome_produto="Shampoo 300ml",
        quantidade=10,
        preco_unitario=Decimal("29.90"),
    )
    assert item.preco_unitario == Decimal("29.90")
    assert item.quantidade == 10


@pytest.mark.unit
def test_criar_pedido_input_parsing() -> None:
    """CriarPedidoInput aceita lista de ItemPedidoInput."""
    pedido_input = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id="cli-1",
        representante_id=None,
        itens=[
            ItemPedidoInput(
                produto_id="prod-1",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=5,
                preco_unitario=Decimal("29.90"),
            ),
            ItemPedidoInput(
                produto_id="prod-2",
                codigo_externo="SKU002",
                nome_produto="Condicionador 300ml",
                quantidade=3,
                preco_unitario=Decimal("19.90"),
            ),
        ],
    )
    assert len(pedido_input.itens) == 2
    assert pedido_input.tenant_id == "jmb"
    assert pedido_input.representante_id is None
