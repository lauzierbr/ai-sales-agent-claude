"""Módulo de normalização: converte rows EFOS em types commerce/.

Mapeamento das tabelas EFOS para os types do domínio commerce/:
  tb_produto  → CommerceProduct
  tb_cliente  → CommerceAccountB2B
  tb_pedido   → CommerceOrder
  tb_itens    → CommerceOrderItem
  tb_saldo    → CommerceInventory
  tb_venda    → CommerceSalesHistory
  tb_vendedor → CommerceVendedor (DISTINCT ON ve_codigo)

Gotchas aplicados:
  - tb_vendedor: DISTINCT ON ve_codigo — de-duplica por filial
  - cidades: .upper() no valor original (EFOS armazena em UPPERCASE)
  - Decimal() para todos os campos monetários e quantitativos
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from src.commerce.types import (
    CommerceAccountB2B,
    CommerceInventory,
    CommerceOrder,
    CommerceOrderItem,
    CommerceProduct,
    CommerceSalesHistory,
    CommerceVendedor,
)

log = structlog.get_logger(__name__)


def _to_decimal(val: object) -> Decimal | None:
    """Converte valor para Decimal, retornando None se inválido."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _to_date(val: object) -> date | None:
    """Converte valor para date, retornando None se inválido."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        from datetime import datetime
        if isinstance(val, str):
            # Formatos comuns: YYYY-MM-DD, DD/MM/YYYY
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
                try:
                    return datetime.strptime(val, fmt).date()
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def _mes_ano(d: date | None) -> tuple[int | None, int | None]:
    """Extrai (mes, ano) de uma date, ou (None, None) se None."""
    if d is None:
        return None, None
    return d.month, d.year


def normalize_products(rows: list[dict], *, tenant_id: str, checksum: str) -> list[CommerceProduct]:
    """Normaliza rows de tb_produto para CommerceProduct.

    Args:
        rows: rows brutas do banco EFOS (tb_produto).
        tenant_id: ID do tenant para isolamento.
        checksum: checksum do arquivo de backup (snapshot_checksum).

    Returns:
        Lista de CommerceProduct normalizada.
    """
    result = []
    for row in rows:
        external_id = str(row.get("pr_codigo") or row.get("id") or "")
        if not external_id:
            continue
        result.append(CommerceProduct(
            tenant_id=tenant_id,
            external_id=external_id,
            codigo=str(row.get("pr_codigo") or "") or None,
            nome=str(row.get("pr_nome") or row.get("nome") or "").strip() or "Sem nome",
            descricao=str(row.get("pr_descricao") or "") or None,
            unidade=str(row.get("pr_unidade") or row.get("unidade") or "") or None,
            preco_padrao=_to_decimal(row.get("pr_preco") or row.get("preco_padrao")),
            ativo=bool(row.get("pr_ativo", True)),
            snapshot_checksum=checksum,
        ))
    log.info("normalize_products_ok", tenant_id=tenant_id, count=len(result))
    return result


def normalize_accounts_b2b(rows: list[dict], *, tenant_id: str, checksum: str) -> list[CommerceAccountB2B]:
    """Normaliza rows de tb_cliente para CommerceAccountB2B.

    Cidades são convertidas para UPPERCASE (gotcha: EFOS armazena em UPPERCASE).

    Args:
        rows: rows brutas do banco EFOS (tb_cliente).
        tenant_id: ID do tenant.
        checksum: checksum do snapshot.

    Returns:
        Lista de CommerceAccountB2B normalizada.
    """
    result = []
    for row in rows:
        external_id = str(row.get("cl_codigo") or row.get("id") or "")
        if not external_id:
            continue
        cidade_raw = row.get("cl_cidade") or row.get("cidade") or ""
        result.append(CommerceAccountB2B(
            tenant_id=tenant_id,
            external_id=external_id,
            codigo=str(row.get("cl_codigo") or "") or None,
            nome=str(row.get("cl_nome") or row.get("nome") or "").strip() or "Sem nome",
            cnpj=str(row.get("cl_cgc") or row.get("cnpj") or "") or None,
            cidade=str(cidade_raw).upper() if cidade_raw else None,
            uf=str(row.get("cl_uf") or row.get("uf") or "") or None,
            situacao_cliente=int(row.get("cl_situacao") or row.get("situacao_cliente") or 0) or None,
            vendedor_codigo=str(row.get("cl_vendedor") or row.get("vendedor_codigo") or "") or None,
            snapshot_checksum=checksum,
        ))
    log.info("normalize_accounts_b2b_ok", tenant_id=tenant_id, count=len(result))
    return result


def normalize_orders(
    pedido_rows: list[dict],
    itens_rows: list[dict],
    vendedor_rows: list[dict],
    *,
    tenant_id: str,
    checksum: str,
) -> tuple[list[CommerceOrder], list[CommerceOrderItem]]:
    """Normaliza rows de tb_pedido + tb_itens para CommerceOrder + CommerceOrderItem.

    Enriquece pedidos com nome do vendedor via lookup em vendedor_rows.

    Args:
        pedido_rows: rows brutas de tb_pedido.
        itens_rows: rows brutas de tb_itens.
        vendedor_rows: rows brutas de tb_vendedor (para lookup de nome).
        tenant_id: ID do tenant.
        checksum: checksum do snapshot.

    Returns:
        Tupla (pedidos, itens) normalizada.
    """
    # Lookup rápido de vendedor: codigo → nome
    vendedor_map: dict[str, str] = {}
    for v in vendedor_rows:
        ve_codigo = str(v.get("ve_codigo") or "")
        ve_nome = str(v.get("ve_nome") or "")
        if ve_codigo:
            vendedor_map[ve_codigo] = ve_nome

    orders: list[CommerceOrder] = []
    for row in pedido_rows:
        external_id = str(row.get("pe_numero") or row.get("id") or "")
        if not external_id:
            continue
        data_ped = _to_date(row.get("pe_data") or row.get("data_pedido"))
        mes, ano = _mes_ano(data_ped)
        vend_cod = str(row.get("pe_vendedor") or row.get("vendedor_codigo") or "") or None
        orders.append(CommerceOrder(
            tenant_id=tenant_id,
            external_id=external_id,
            numero_pedido=str(row.get("pe_numero") or "") or None,
            cliente_codigo=str(row.get("pe_cliente") or row.get("cliente_codigo") or "") or None,
            cliente_nome=str(row.get("pe_cli_nome") or row.get("cliente_nome") or "") or None,
            vendedor_codigo=vend_cod,
            data_pedido=data_ped,
            total=_to_decimal(row.get("pe_total") or row.get("total")),
            status=str(row.get("pe_status") or row.get("status") or "") or None,
            mes=mes,
            ano=ano,
            snapshot_checksum=checksum,
        ))

    items: list[CommerceOrderItem] = []
    for row in itens_rows:
        external_id = str(row.get("it_id") or row.get("id") or "")
        if not external_id:
            continue
        items.append(CommerceOrderItem(
            tenant_id=tenant_id,
            external_id=external_id,
            order_external_id=str(row.get("it_pedido") or row.get("order_external_id") or ""),
            produto_codigo=str(row.get("it_produto") or row.get("produto_codigo") or "") or None,
            produto_nome=str(row.get("it_nome") or row.get("produto_nome") or "") or None,
            quantidade=_to_decimal(row.get("it_qtde") or row.get("quantidade")),
            preco_unitario=_to_decimal(row.get("it_preco") or row.get("preco_unitario")),
            total=_to_decimal(row.get("it_total") or row.get("total")),
            snapshot_checksum=checksum,
        ))

    log.info(
        "normalize_orders_ok",
        tenant_id=tenant_id,
        n_orders=len(orders),
        n_items=len(items),
    )
    return orders, items


def normalize_inventory(rows: list[dict], *, tenant_id: str, checksum: str) -> list[CommerceInventory]:
    """Normaliza rows de tb_saldo para CommerceInventory.

    Args:
        rows: rows brutas de tb_saldo.
        tenant_id: ID do tenant.
        checksum: checksum do snapshot.

    Returns:
        Lista de CommerceInventory normalizada.
    """
    result = []
    for row in rows:
        external_id = str(row.get("sa_id") or row.get("id") or "")
        if not external_id:
            continue
        result.append(CommerceInventory(
            tenant_id=tenant_id,
            external_id=external_id,
            produto_codigo=str(row.get("sa_produto") or row.get("produto_codigo") or "") or None,
            produto_nome=str(row.get("sa_nome") or row.get("produto_nome") or "") or None,
            saldo=_to_decimal(row.get("sa_saldo") or row.get("saldo")),
            deposito=str(row.get("sa_deposito") or row.get("deposito") or "") or None,
            snapshot_checksum=checksum,
        ))
    log.info("normalize_inventory_ok", tenant_id=tenant_id, count=len(result))
    return result


def normalize_sales_history(rows: list[dict], *, tenant_id: str, checksum: str) -> list[CommerceSalesHistory]:
    """Normaliza rows de tb_venda para CommerceSalesHistory.

    Args:
        rows: rows brutas de tb_venda.
        tenant_id: ID do tenant.
        checksum: checksum do snapshot.

    Returns:
        Lista de CommerceSalesHistory normalizada.
    """
    result = []
    for row in rows:
        external_id = str(row.get("vd_id") or row.get("id") or "")
        if not external_id:
            continue
        data_venda = _to_date(row.get("vd_data") or row.get("data_venda"))
        mes, ano = _mes_ano(data_venda)
        result.append(CommerceSalesHistory(
            tenant_id=tenant_id,
            external_id=external_id,
            cliente_codigo=str(row.get("vd_cliente") or row.get("cliente_codigo") or "") or None,
            produto_codigo=str(row.get("vd_produto") or row.get("produto_codigo") or "") or None,
            quantidade=_to_decimal(row.get("vd_qtde") or row.get("quantidade")),
            total=_to_decimal(row.get("vd_total") or row.get("total")),
            data_venda=data_venda,
            mes=mes,
            ano=ano,
            snapshot_checksum=checksum,
        ))
    log.info("normalize_sales_history_ok", tenant_id=tenant_id, count=len(result))
    return result


def normalize_vendedores(rows: list[dict], *, tenant_id: str, checksum: str) -> list[CommerceVendedor]:
    """Normaliza rows de tb_vendedor para CommerceVendedor.

    Aplica DISTINCT ON ve_codigo: de-duplica por código, mantendo a primeira
    ocorrência quando o mesmo vendedor aparece em múltiplas filiais.

    Args:
        rows: rows brutas de tb_vendedor (pode conter duplicatas por filial).
        tenant_id: ID do tenant.
        checksum: checksum do snapshot.

    Returns:
        Lista de CommerceVendedor sem duplicatas (uma por ve_codigo).
    """
    seen_codigos: set[str] = set()
    result = []
    for row in rows:
        ve_codigo = str(row.get("ve_codigo") or "")
        if not ve_codigo:
            continue
        # DISTINCT ON ve_codigo: ignora duplicatas
        if ve_codigo in seen_codigos:
            continue
        seen_codigos.add(ve_codigo)
        result.append(CommerceVendedor(
            tenant_id=tenant_id,
            external_id=ve_codigo,
            ve_codigo=ve_codigo,
            ve_nome=str(row.get("ve_nome") or "").strip() or "Sem nome",
            snapshot_checksum=checksum,
        ))
    log.info(
        "normalize_vendedores_ok",
        tenant_id=tenant_id,
        count=len(result),
        raw_count=len(rows),
    )
    return result
