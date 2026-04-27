"""Tipos do domínio Commerce — dataclasses para dados EFOS normalizados.

Camada Types: sem imports internos do projeto.
Não importa agents/, catalog/, orders/, tenants/, dashboard/, integrations/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class CommerceProduct:
    """Produto normalizado a partir do EFOS (tb_produto).

    Campos obrigatórios: tenant_id, external_id, nome, snapshot_checksum.
    """

    tenant_id: str
    external_id: str
    codigo: str | None
    nome: str
    descricao: str | None
    unidade: str | None
    preco_padrao: Decimal | None
    ativo: bool
    snapshot_checksum: str


@dataclass
class CommerceAccountB2B:
    """Conta B2B normalizada a partir do EFOS (tb_cliente).

    situacao_cliente: 1=ativo, 2=inativo, conforme enum EFOS.
    """

    tenant_id: str
    external_id: str
    codigo: str | None
    nome: str
    cnpj: str | None
    cidade: str | None
    uf: str | None
    situacao_cliente: int | None
    vendedor_codigo: str | None
    snapshot_checksum: str


@dataclass
class CommerceOrder:
    """Pedido B2B normalizado a partir do EFOS (tb_pedido).

    mes e ano são extraídos de data_pedido para facilitar queries agregadas.
    """

    tenant_id: str
    external_id: str
    numero_pedido: str | None
    cliente_codigo: str | None
    cliente_nome: str | None
    vendedor_codigo: str | None
    data_pedido: date | None
    total: Decimal | None
    status: str | None
    mes: int | None
    ano: int | None
    snapshot_checksum: str


@dataclass
class CommerceOrderItem:
    """Item de pedido B2B normalizado a partir do EFOS (tb_itens)."""

    tenant_id: str
    external_id: str
    order_external_id: str
    produto_codigo: str | None
    produto_nome: str | None
    quantidade: Decimal | None
    preco_unitario: Decimal | None
    total: Decimal | None
    snapshot_checksum: str


@dataclass
class CommerceInventory:
    """Saldo de estoque normalizado a partir do EFOS (tb_saldo)."""

    tenant_id: str
    external_id: str
    produto_codigo: str | None
    produto_nome: str | None
    saldo: Decimal | None
    deposito: str | None
    snapshot_checksum: str


@dataclass
class CommerceSalesHistory:
    """Histórico de vendas normalizado a partir do EFOS (tb_venda).

    mes e ano facilitam queries de relatório sem EXTRACT().
    """

    tenant_id: str
    external_id: str
    cliente_codigo: str | None
    produto_codigo: str | None
    quantidade: Decimal | None
    total: Decimal | None
    data_venda: date | None
    mes: int | None
    ano: int | None
    snapshot_checksum: str


@dataclass
class CommerceVendedor:
    """Representante comercial normalizado a partir do EFOS (tb_vendedor).

    DISTINCT ON ve_codigo: uma linha por representante (sem duplicar por filial).
    """

    tenant_id: str
    external_id: str
    ve_codigo: str
    ve_nome: str
    snapshot_checksum: str
