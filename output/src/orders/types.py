"""Tipos do domínio Orders — Pydantic models e enums.

Camada Types: sem imports internos do projeto.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StatusPedido(StrEnum):
    """Status de ciclo de vida de um pedido."""

    PENDENTE = "pendente"
    CONFIRMADO = "confirmado"
    CANCELADO = "cancelado"


class ItemPedidoInput(BaseModel):
    """Input para criação de um item de pedido."""

    produto_id: str
    codigo_externo: str
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal


class ItemPedido(BaseModel):
    """Item de pedido persistido no banco de dados."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    pedido_id: str
    produto_id: str
    codigo_externo: str
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal


class CriarPedidoInput(BaseModel):
    """Input DTO para OrderService.criar_pedido_from_intent().

    Quando o cliente existe apenas em commerce_accounts_b2b (EFOS-only),
    passar cliente_b2b_id=None e account_external_id=<external_id>.
    Quando o cliente existe em clientes_b2b (UUID), passar cliente_b2b_id=<uuid>
    e account_external_id=None.
    """

    tenant_id: str
    cliente_b2b_id: str | None
    account_external_id: str | None = None
    representante_id: str | None
    itens: list[ItemPedidoInput]
    observacao: str | None = None


class Pedido(BaseModel):
    """Pedido capturado pelo agente, aguardando processamento manual pelo gestor."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    cliente_b2b_id: str | None
    account_external_id: str | None = None
    representante_id: str | None
    status: StatusPedido
    total_estimado: Decimal
    pdf_path: str | None
    criado_em: datetime
    ficticio: bool = False
    observacao: str | None = None
    itens: list[ItemPedido] = []
