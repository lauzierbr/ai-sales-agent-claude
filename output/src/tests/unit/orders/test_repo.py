"""Testes unitários de orders/repo.py — OrderRepo.

Todos os testes são @pytest.mark.unit — sem I/O externo.
PostgreSQL mockado via AsyncMock.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orders.types import CriarPedidoInput, ItemPedidoInput, StatusPedido


# ─────────────────────────────────────────────
# A3: tenant_id obrigatório em todos os métodos públicos
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_todo_metodo_repo_tem_tenant_id() -> None:
    """A3: todos os métodos públicos de ClienteB2BRepo, RepresentanteRepo,
    ConversaRepo e OrderRepo que executam queries recebem tenant_id: str."""
    import inspect

    from src.agents.repo import ClienteB2BRepo, ConversaRepo, RepresentanteRepo
    from src.orders.repo import OrderRepo

    repos_e_metodos = [
        (ClienteB2BRepo, ["get_by_telefone", "create"]),
        (RepresentanteRepo, ["get_by_telefone"]),
        (ConversaRepo, ["get_or_create_conversa"]),
        (OrderRepo, ["criar_pedido", "get_pedido", "get_pedidos_pendentes", "update_pdf_path"]),
    ]

    for repo_cls, metodos in repos_e_metodos:
        for nome in metodos:
            metodo = getattr(repo_cls, nome)
            sig = inspect.signature(metodo)
            assert "tenant_id" in sig.parameters, (
                f"{repo_cls.__name__}.{nome} não tem parâmetro tenant_id"
            )
            param = sig.parameters["tenant_id"]
            annotation = param.annotation
            assert annotation is str or annotation == "str", (
                f"{repo_cls.__name__}.{nome}.tenant_id não é anotado como str"
            )


# ─────────────────────────────────────────────
# OrderRepo.criar_pedido
# ─────────────────────────────────────────────


@pytest.fixture
def pedido_input() -> CriarPedidoInput:
    return CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id=None,
        itens=[
            ItemPedidoInput(
                produto_id="prod-001",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=10,
                preco_unitario=Decimal("29.90"),
            ),
        ],
    )


def _make_mock_row(data: dict[str, Any]) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _make_session_with_returning(pedido_row: dict[str, Any], item_row: dict[str, Any]) -> AsyncMock:
    """Cria mock de sessão que simula RETURNING para pedido e itens."""
    session = AsyncMock()

    pedido_result = MagicMock()
    pedido_result.mappings.return_value.first.return_value = pedido_row

    item_result = MagicMock()
    item_result.mappings.return_value.first.return_value = item_row

    # Primeira chamada = INSERT pedido, segunda = INSERT item
    session.execute = AsyncMock(side_effect=[pedido_result, item_result])
    return session


@pytest.mark.unit
async def test_criar_pedido_retorna_pedido_com_id() -> None:
    """OrderRepo.criar_pedido retorna Pedido com ID gerado via RETURNING."""
    from src.orders.repo import OrderRepo

    pedido_row = {
        "id": "ped-abc123",
        "tenant_id": "jmb",
        "cliente_b2b_id": "cli-001",
        "representante_id": None,
        "status": "pendente",
        "total_estimado": "299.00",
        "pdf_path": None,
        "criado_em": datetime(2026, 4, 15, tzinfo=timezone.utc),
    }
    item_row = {
        "id": "item-001",
        "pedido_id": "ped-abc123",
        "produto_id": "prod-001",
        "codigo_externo": "SKU001",
        "nome_produto": "Shampoo 300ml",
        "quantidade": 10,
        "preco_unitario": "29.90",
        "subtotal": "299.00",
    }

    session = _make_session_with_returning(pedido_row, item_row)
    repo = OrderRepo()

    pedido_input = CriarPedidoInput(
        tenant_id="jmb",
        cliente_b2b_id="cli-001",
        representante_id=None,
        itens=[
            ItemPedidoInput(
                produto_id="prod-001",
                codigo_externo="SKU001",
                nome_produto="Shampoo 300ml",
                quantidade=10,
                preco_unitario=Decimal("29.90"),
            ),
        ],
    )

    pedido = await repo.criar_pedido(
        tenant_id="jmb",
        pedido_input=pedido_input,
        total_estimado=Decimal("299.00"),
        session=session,
    )

    assert pedido.id == "ped-abc123"
    assert pedido.tenant_id == "jmb"
    assert len(pedido.itens) == 1
    assert pedido.itens[0].codigo_externo == "SKU001"


@pytest.mark.unit
async def test_get_pedidos_pendentes_filtra_tenant_id() -> None:
    """OrderRepo.get_pedidos_pendentes filtra por tenant_id."""
    from src.orders.repo import OrderRepo

    session = AsyncMock()

    # Sem pedidos
    pendentes_result = MagicMock()
    pendentes_result.mappings.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=pendentes_result)

    repo = OrderRepo()
    pedidos = await repo.get_pedidos_pendentes(tenant_id="jmb", session=session)

    assert pedidos == []
    call_args = session.execute.call_args
    # Verifica que o SQL referencia tenant_id
    sql_text = str(call_args[0][0])
    assert "tenant_id" in sql_text


@pytest.mark.unit
async def test_update_pdf_path_chama_execute() -> None:
    """OrderRepo.update_pdf_path executa UPDATE com tenant_id e pedido_id."""
    from src.orders.repo import OrderRepo

    session = AsyncMock()
    result = MagicMock()
    session.execute = AsyncMock(return_value=result)

    repo = OrderRepo()
    await repo.update_pdf_path(
        tenant_id="jmb",
        pedido_id="ped-123",
        pdf_path="/pdfs/jmb/ped-123.pdf",
        session=session,
    )

    session.execute.assert_called_once()
    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["tenant_id"] == "jmb"
    assert params["pedido_id"] == "ped-123"
    assert params["pdf_path"] == "/pdfs/jmb/ped-123.pdf"


@pytest.mark.unit
async def test_get_pedido_retorna_none_se_nao_encontrado() -> None:
    """OrderRepo.get_pedido retorna None para pedido inexistente."""
    from src.orders.repo import OrderRepo

    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)

    repo = OrderRepo()
    pedido = await repo.get_pedido(tenant_id="jmb", pedido_id="nao-existe", session=session)

    assert pedido is None
