"""Repositório do domínio Orders — acesso ao PostgreSQL.

Camada Repo: importa apenas src.orders.types e stdlib.
Toda função pública que acessa dados de tenant filtra por tenant_id.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.types import (
    CriarPedidoInput,
    ItemPedido,
    Pedido,
    StatusPedido,
)

log = structlog.get_logger(__name__)


class OrderRepo:
    """Repositório de pedidos e itens de pedido."""

    async def criar_pedido(
        self,
        tenant_id: str,
        pedido_input: CriarPedidoInput,
        total_estimado: Decimal,
        session: AsyncSession,
    ) -> Pedido:
        """Persiste novo pedido e seus itens no banco de dados.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_input: dados do pedido (itens, cliente, rep).
            total_estimado: total calculado em Python antes da persistência.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Pedido persistido com ID gerado pelo banco.

        Raises:
            RuntimeError: se o INSERT não retornar dados.
        """
        result = await session.execute(
            text("""
                INSERT INTO pedidos (tenant_id, cliente_b2b_id, representante_id, total_estimado)
                VALUES (:tenant_id, :cliente_b2b_id, :representante_id, :total_estimado)
                RETURNING id, tenant_id, cliente_b2b_id, representante_id,
                          status, total_estimado, pdf_path, criado_em
            """),
            {
                "tenant_id": tenant_id,
                "cliente_b2b_id": pedido_input.cliente_b2b_id,
                "representante_id": pedido_input.representante_id,
                "total_estimado": str(total_estimado),
            },
        )
        row = result.mappings().first()
        if row is None:
            raise RuntimeError("Falha ao criar pedido")

        pedido_id = row["id"]

        # Persiste itens individualmente
        itens: list[ItemPedido] = []
        for item in pedido_input.itens:
            subtotal = item.quantidade * item.preco_unitario
            item_result = await session.execute(
                text("""
                    INSERT INTO itens_pedido
                        (pedido_id, produto_id, codigo_externo, nome_produto,
                         quantidade, preco_unitario, subtotal)
                    VALUES
                        (:pedido_id, :produto_id, :codigo_externo, :nome_produto,
                         :quantidade, :preco_unitario, :subtotal)
                    RETURNING id, pedido_id, produto_id, codigo_externo, nome_produto,
                              quantidade, preco_unitario, subtotal
                """),
                {
                    "pedido_id": pedido_id,
                    "produto_id": item.produto_id,
                    "codigo_externo": item.codigo_externo,
                    "nome_produto": item.nome_produto,
                    "quantidade": item.quantidade,
                    "preco_unitario": str(item.preco_unitario),
                    "subtotal": str(subtotal),
                },
            )
            item_row = item_result.mappings().first()
            if item_row is None:
                raise RuntimeError(f"Falha ao criar item do pedido: {item.codigo_externo}")
            itens.append(
                ItemPedido(
                    id=item_row["id"],
                    pedido_id=item_row["pedido_id"],
                    produto_id=item_row["produto_id"],
                    codigo_externo=item_row["codigo_externo"],
                    nome_produto=item_row["nome_produto"],
                    quantidade=item_row["quantidade"],
                    preco_unitario=Decimal(str(item_row["preco_unitario"])),
                    subtotal=Decimal(str(item_row["subtotal"])),
                )
            )

        log.info(
            "pedido_criado",
            tenant_id=tenant_id,
            pedido_id=pedido_id,
            total=str(total_estimado),
            n_itens=len(itens),
        )
        return Pedido(
            id=row["id"],
            tenant_id=row["tenant_id"],
            cliente_b2b_id=row["cliente_b2b_id"],
            representante_id=row["representante_id"],
            status=StatusPedido(row["status"]),
            total_estimado=Decimal(str(row["total_estimado"])),
            pdf_path=row["pdf_path"],
            criado_em=row["criado_em"],
            itens=itens,
        )

    async def get_pedido(
        self,
        tenant_id: str,
        pedido_id: str,
        session: AsyncSession,
    ) -> Pedido | None:
        """Retorna pedido completo (com itens) pelo ID.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_id: ID do pedido.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Pedido com itens, ou None se não encontrado.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, cliente_b2b_id, representante_id,
                       status, total_estimado, pdf_path, criado_em
                FROM pedidos
                WHERE tenant_id = :tenant_id AND id = :pedido_id
            """),
            {"tenant_id": tenant_id, "pedido_id": pedido_id},
        )
        row = result.mappings().first()
        if row is None:
            return None

        itens = await self._get_itens(pedido_id, session)
        return Pedido(
            id=row["id"],
            tenant_id=row["tenant_id"],
            cliente_b2b_id=row["cliente_b2b_id"],
            representante_id=row["representante_id"],
            status=StatusPedido(row["status"]),
            total_estimado=Decimal(str(row["total_estimado"])),
            pdf_path=row["pdf_path"],
            criado_em=row["criado_em"],
            itens=itens,
        )

    async def get_pedidos_pendentes(
        self,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[Pedido]:
        """Retorna todos os pedidos com status PENDENTE do tenant.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de Pedido com status pendente, ordenada por criado_em DESC.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, cliente_b2b_id, representante_id,
                       status, total_estimado, pdf_path, criado_em
                FROM pedidos
                WHERE tenant_id = :tenant_id AND status = 'pendente'
                ORDER BY criado_em DESC
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.mappings().all()
        pedidos: list[Pedido] = []
        for row in rows:
            itens = await self._get_itens(row["id"], session)
            pedidos.append(
                Pedido(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    cliente_b2b_id=row["cliente_b2b_id"],
                    representante_id=row["representante_id"],
                    status=StatusPedido(row["status"]),
                    total_estimado=Decimal(str(row["total_estimado"])),
                    pdf_path=row["pdf_path"],
                    criado_em=row["criado_em"],
                    itens=itens,
                )
            )
        return pedidos

    async def update_pdf_path(
        self,
        tenant_id: str,
        pedido_id: str,
        pdf_path: str,
        session: AsyncSession,
    ) -> None:
        """Atualiza o caminho do PDF gerado para o pedido.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_id: ID do pedido.
            pdf_path: caminho relativo do PDF gerado.
            session: sessão SQLAlchemy assíncrona.
        """
        await session.execute(
            text("""
                UPDATE pedidos
                SET pdf_path = :pdf_path
                WHERE tenant_id = :tenant_id AND id = :pedido_id
            """),
            {"tenant_id": tenant_id, "pedido_id": pedido_id, "pdf_path": pdf_path},
        )
        log.info("pedido_pdf_atualizado", tenant_id=tenant_id, pedido_id=pedido_id)

    async def _get_itens(
        self,
        pedido_id: str,
        session: AsyncSession,
    ) -> list[ItemPedido]:
        """Retorna itens de um pedido.

        Args:
            pedido_id: ID do pedido.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de ItemPedido do pedido.
        """
        result = await session.execute(
            text("""
                SELECT id, pedido_id, produto_id, codigo_externo, nome_produto,
                       quantidade, preco_unitario, subtotal
                FROM itens_pedido
                WHERE pedido_id = :pedido_id
                ORDER BY id
            """),
            {"pedido_id": pedido_id},
        )
        return [
            ItemPedido(
                id=r["id"],
                pedido_id=r["pedido_id"],
                produto_id=r["produto_id"],
                codigo_externo=r["codigo_externo"],
                nome_produto=r["nome_produto"],
                quantidade=r["quantidade"],
                preco_unitario=Decimal(str(r["preco_unitario"])),
                subtotal=Decimal(str(r["subtotal"])),
            )
            for r in result.mappings().all()
        ]
