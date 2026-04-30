"""Módulo de publicação: insere dados normalizados nas tabelas commerce_*.

B-36: Todas as tabelas usam UPSERT (ON CONFLICT DO UPDATE) em vez de
DELETE+INSERT para evitar UniqueViolationError em caso de re-sync ou
falha parcial. Commerce_products preserva embedding existente (DT-2).
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
        # B-36: removido DELETE+INSERT. Todas as tabelas usam UPSERT para idempotência.
        # commerce_products preserva embedding (DT-2).
        # As demais tabelas atualizam todos os campos ERP exceto campos não-ERP (embedding).

        total = 0

        # UPSERT para products — preserva embedding existente (DT-2)
        total += await _upsert_products(products, session)
        # UPSERT para as demais tabelas — idempotente, sem UniqueViolation
        total += await _upsert_accounts(accounts, session)
        total += await _upsert_orders(orders, session)
        total += await _upsert_order_items(order_items, session)
        total += await _upsert_inventory(inventory, session)
        total += await _upsert_sales_history(sales_history, session)
        total += await _upsert_vendedores(vendedores, session)

        await session.commit()
        log.info("publish_concluido", tenant_id=tenant_id, total_rows=total)
        return total

    except Exception as exc:
        await session.rollback()
        log.error("publish_rollback", tenant_id=tenant_id, error=str(exc))
        raise


async def _upsert_products(rows: list[CommerceProduct], session: AsyncSession) -> int:
    """UPSERT de CommerceProduct preservando embedding existente (DT-2, E8).

    ON CONFLICT (tenant_id, external_id) atualiza todos os campos EXCETO embedding.
    embedding só é sobrescrito se a linha existente não tiver (COALESCE).
    """
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_products
                    (tenant_id, source_system, external_id, codigo, nome, descricao,
                     unidade, preco_padrao, ativo, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :codigo, :nome, :descricao,
                     :unidade, :preco_padrao, :ativo, NOW(), :snapshot_checksum)
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    codigo            = EXCLUDED.codigo,
                    nome              = EXCLUDED.nome,
                    descricao         = EXCLUDED.descricao,
                    unidade           = EXCLUDED.unidade,
                    preco_padrao      = EXCLUDED.preco_padrao,
                    ativo             = EXCLUDED.ativo,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
                    -- embedding NÃO atualizado aqui: preservado de sincronizações anteriores
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


async def _upsert_accounts(rows: list[CommerceAccountB2B], session: AsyncSession) -> int:
    """UPSERT de CommerceAccountB2B — idempotente, sem UniqueViolationError (B-36).

    E8 (D030): inclui os 6 novos campos de contato do EFOS.
    ON CONFLICT (tenant_id, external_id) atualiza todos os campos ERP.
    """
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_accounts_b2b
                    (tenant_id, source_system, external_id, codigo, nome, cnpj,
                     cidade, uf, situacao_cliente, vendedor_codigo,
                     contato_padrao, telefone, telefone_celular, email, nome_fantasia, dataultimacompra,
                     synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :codigo, :nome, :cnpj,
                     :cidade, :uf, :situacao_cliente, :vendedor_codigo,
                     :contato_padrao, :telefone, :telefone_celular, :email, :nome_fantasia, :dataultimacompra,
                     NOW(), :snapshot_checksum)
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    codigo             = EXCLUDED.codigo,
                    nome               = EXCLUDED.nome,
                    cnpj               = EXCLUDED.cnpj,
                    cidade             = EXCLUDED.cidade,
                    uf                 = EXCLUDED.uf,
                    situacao_cliente   = EXCLUDED.situacao_cliente,
                    vendedor_codigo    = EXCLUDED.vendedor_codigo,
                    contato_padrao     = EXCLUDED.contato_padrao,
                    telefone           = EXCLUDED.telefone,
                    telefone_celular   = EXCLUDED.telefone_celular,
                    email              = EXCLUDED.email,
                    nome_fantasia      = EXCLUDED.nome_fantasia,
                    dataultimacompra   = EXCLUDED.dataultimacompra,
                    synced_at          = EXCLUDED.synced_at,
                    snapshot_checksum  = EXCLUDED.snapshot_checksum
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
                "contato_padrao": row.contato_padrao,
                "telefone": row.telefone,
                "telefone_celular": row.telefone_celular,
                "email": row.email,
                "nome_fantasia": row.nome_fantasia,
                "dataultimacompra": row.dataultimacompra,
                "snapshot_checksum": row.snapshot_checksum,
            },
        )
    return len(rows)


async def _upsert_orders(rows: list[CommerceOrder], session: AsyncSession) -> int:
    """UPSERT de CommerceOrder — idempotente (B-36)."""
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
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    numero_pedido     = EXCLUDED.numero_pedido,
                    cliente_codigo    = EXCLUDED.cliente_codigo,
                    cliente_nome      = EXCLUDED.cliente_nome,
                    vendedor_codigo   = EXCLUDED.vendedor_codigo,
                    data_pedido       = EXCLUDED.data_pedido,
                    total             = EXCLUDED.total,
                    status            = EXCLUDED.status,
                    mes               = EXCLUDED.mes,
                    ano               = EXCLUDED.ano,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
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


async def _upsert_order_items(rows: list[CommerceOrderItem], session: AsyncSession) -> int:
    """UPSERT de CommerceOrderItem — idempotente (B-36)."""
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
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    order_external_id = EXCLUDED.order_external_id,
                    produto_codigo    = EXCLUDED.produto_codigo,
                    produto_nome      = EXCLUDED.produto_nome,
                    quantidade        = EXCLUDED.quantidade,
                    preco_unitario    = EXCLUDED.preco_unitario,
                    total             = EXCLUDED.total,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
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


async def _upsert_inventory(rows: list[CommerceInventory], session: AsyncSession) -> int:
    """UPSERT de CommerceInventory — idempotente (B-36)."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_inventory
                    (tenant_id, source_system, external_id, produto_codigo,
                     produto_nome, saldo, deposito, synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :produto_codigo,
                     :produto_nome, :saldo, :deposito, NOW(), :snapshot_checksum)
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    produto_codigo    = EXCLUDED.produto_codigo,
                    produto_nome      = EXCLUDED.produto_nome,
                    saldo             = EXCLUDED.saldo,
                    deposito          = EXCLUDED.deposito,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
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


async def _upsert_sales_history(rows: list[CommerceSalesHistory], session: AsyncSession) -> int:
    """UPSERT de CommerceSalesHistory — idempotente (B-36)."""
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
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    cliente_codigo    = EXCLUDED.cliente_codigo,
                    produto_codigo    = EXCLUDED.produto_codigo,
                    quantidade        = EXCLUDED.quantidade,
                    total             = EXCLUDED.total,
                    data_venda        = EXCLUDED.data_venda,
                    mes               = EXCLUDED.mes,
                    ano               = EXCLUDED.ano,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
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


async def _upsert_vendedores(rows: list[CommerceVendedor], session: AsyncSession) -> int:
    """UPSERT de CommerceVendedor — idempotente (B-36)."""
    for row in rows:
        await session.execute(
            text("""
                INSERT INTO commerce_vendedores
                    (tenant_id, source_system, external_id, ve_codigo, ve_nome,
                     synced_at, snapshot_checksum)
                VALUES
                    (:tenant_id, 'efos', :external_id, :ve_codigo, :ve_nome,
                     NOW(), :snapshot_checksum)
                ON CONFLICT (tenant_id, external_id) DO UPDATE SET
                    ve_codigo         = EXCLUDED.ve_codigo,
                    ve_nome           = EXCLUDED.ve_nome,
                    synced_at         = EXCLUDED.synced_at,
                    snapshot_checksum = EXCLUDED.snapshot_checksum
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
