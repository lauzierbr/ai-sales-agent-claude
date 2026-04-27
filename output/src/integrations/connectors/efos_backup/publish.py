"""Módulo de publicação: insere dados normalizados nas tabelas commerce_*.

Executa em transação única: DELETE WHERE tenant_id + INSERT.
Rollback total se qualquer INSERT falhar.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


async def publish(
    tenant_id: str,
    products: list[CommerceProduct],
    accounts: list[CommerceAccountB2B],
    orders: list[CommerceOrder],
    order_items: list[CommerceOrderItem],
    inventory: list[CommerceInventory],
    sales_history: list[CommerceSalesHistory],
    vendedores: list[CommerceVendedor],
    session: AsyncSession,
) -> int:
    """Publica dados normalizados nas tabelas commerce_*.

    Transação única: DELETE WHERE tenant_id (trunca snapshot anterior)
    + INSERT de todos os dados normalizados. Rollback total em falha.

    Args:
        tenant_id: ID do tenant — filtra DELETEs e INSERTs.
        products: lista de CommerceProduct normalizada.
        accounts: lista de CommerceAccountB2B normalizada.
        orders: lista de CommerceOrder normalizada.
        order_items: lista de CommerceOrderItem normalizada.
        inventory: lista de CommerceInventory normalizada.
        sales_history: lista de CommerceSalesHistory normalizada.
        vendedores: lista de CommerceVendedor normalizada.
        session: sessão SQLAlchemy assíncrona.

    Returns:
        Total de rows inseridas (soma de todas as tabelas).

    Raises:
        Exception: qualquer erro causa rollback total da transação.
    """
    try:
        # Limpa snapshot anterior para o tenant
        for table in [
            "commerce_products",
            "commerce_accounts_b2b",
            "commerce_order_items",
            "commerce_orders",
            "commerce_inventory",
            "commerce_sales_history",
            "commerce_vendedores",
        ]:
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),  # noqa: S608
                {"tenant_id": tenant_id},
            )

        total = 0

        total += await _insert_products(products, session)
        total += await _insert_accounts(accounts, session)
        total += await _insert_orders(orders, session)
        total += await _insert_order_items(order_items, session)
        total += await _insert_inventory(inventory, session)
        total += await _insert_sales_history(sales_history, session)
        total += await _insert_vendedores(vendedores, session)

        await session.commit()
        log.info("publish_concluido", tenant_id=tenant_id, total_rows=total)
        return total

    except Exception as exc:
        await session.rollback()
        log.error("publish_rollback", tenant_id=tenant_id, error=str(exc))
        raise


async def _insert_products(rows: list[CommerceProduct], session: AsyncSession) -> int:
    """Insere lista de CommerceProduct na tabela commerce_products."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_products
                    (tenant_id, source_system, external_id, codigo, nome, descricao,
                     unidade, preco_padrao, ativo, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :codigo, :nome, :descricao,
                     :unidade, :preco_padrao, :ativo, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "codigo": row.codigo,
                "nome": row.nome,
                "descricao": row.descricao,
                "unidade": row.unidade,
                "preco_padrao": row.preco_padrao,
                "ativo": row.ativo,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_accounts(rows: list[CommerceAccountB2B], session: AsyncSession) -> int:
    """Insere lista de CommerceAccountB2B na tabela commerce_accounts_b2b."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_accounts_b2b
                    (tenant_id, source_system, external_id, codigo, nome, cnpj,
                     cidade, uf, situacao_cliente, vendedor_codigo, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :codigo, :nome, :cnpj,
                     :cidade, :uf, :situacao_cliente, :vendedor_codigo, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "codigo": row.codigo,
                "nome": row.nome,
                "cnpj": row.cnpj,
                "cidade": row.cidade,
                "uf": row.uf,
                "situacao_cliente": row.situacao_cliente,
                "vendedor_codigo": row.vendedor_codigo,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_orders(rows: list[CommerceOrder], session: AsyncSession) -> int:
    """Insere lista de CommerceOrder na tabela commerce_orders."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_orders
                    (tenant_id, source_system, external_id, numero_pedido, cliente_codigo,
                     cliente_nome, vendedor_codigo, data_pedido, total, status,
                     mes, ano, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :numero_pedido, :cliente_codigo,
                     :cliente_nome, :vendedor_codigo, :data_pedido, :total, :status,
                     :mes, :ano, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "numero_pedido": row.numero_pedido,
                "cliente_codigo": row.cliente_codigo,
                "cliente_nome": row.cliente_nome,
                "vendedor_codigo": row.vendedor_codigo,
                "data_pedido": row.data_pedido,
                "total": row.total,
                "status": row.status,
                "mes": row.mes,
                "ano": row.ano,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_order_items(rows: list[CommerceOrderItem], session: AsyncSession) -> int:
    """Insere lista de CommerceOrderItem na tabela commerce_order_items."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_order_items
                    (tenant_id, source_system, external_id, order_external_id,
                     produto_codigo, produto_nome, quantidade, preco_unitario,
                     total, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :order_external_id,
                     :produto_codigo, :produto_nome, :quantidade, :preco_unitario,
                     :total, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "order_external_id": row.order_external_id,
                "produto_codigo": row.produto_codigo,
                "produto_nome": row.produto_nome,
                "quantidade": row.quantidade,
                "preco_unitario": row.preco_unitario,
                "total": row.total,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_inventory(rows: list[CommerceInventory], session: AsyncSession) -> int:
    """Insere lista de CommerceInventory na tabela commerce_inventory."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_inventory
                    (tenant_id, source_system, external_id, produto_codigo,
                     produto_nome, saldo, deposito, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :produto_codigo,
                     :produto_nome, :saldo, :deposito, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "produto_codigo": row.produto_codigo,
                "produto_nome": row.produto_nome,
                "saldo": row.saldo,
                "deposito": row.deposito,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_sales_history(rows: list[CommerceSalesHistory], session: AsyncSession) -> int:
    """Insere lista de CommerceSalesHistory na tabela commerce_sales_history."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_sales_history
                    (tenant_id, source_system, external_id, cliente_codigo,
                     produto_codigo, quantidade, total, data_venda,
                     mes, ano, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :cliente_codigo,
                     :produto_codigo, :quantidade, :total, :data_venda,
                     :mes, :ano, NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "cliente_codigo": row.cliente_codigo,
                "produto_codigo": row.produto_codigo,
                "quantidade": row.quantidade,
                "total": row.total,
                "data_venda": row.data_venda,
                "mes": row.mes,
                "ano": row.ano,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _insert_vendedores(rows: list[CommerceVendedor], session: AsyncSession) -> int:
    """Insere lista de CommerceVendedor na tabela commerce_vendedores."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_vendedores
                    (tenant_id, source_system, external_id, ve_codigo, ve_nome,
                     synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :ve_codigo, :ve_nome,
                     NOW(), :snapshot_checksum)
            """),
            {
                "tenant_id": row.tenant_id,
                "external_id": row.external_id,
                "ve_codigo": row.ve_codigo,
                "ve_nome": row.ve_nome,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)
