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
        import os as _os
        # ficticio=True em qualquer ambiente que não seja production
        _is_ficticio = _os.getenv("ENVIRONMENT", "development") != "production"

        result = await session.execute(
            text("""
                INSERT INTO pedidos
                    (tenant_id, cliente_b2b_id, account_external_id,
                     representante_id, total_estimado, ficticio, observacao)
                VALUES
                    (:tenant_id, :cliente_b2b_id, :account_external_id,
                     :representante_id, :total_estimado, :ficticio, :observacao)
                RETURNING id, tenant_id, cliente_b2b_id, account_external_id,
                          representante_id, status, total_estimado, pdf_path,
                          criado_em, ficticio, observacao
            """),
            {
                "tenant_id": tenant_id,
                "cliente_b2b_id": pedido_input.cliente_b2b_id,
                "account_external_id": pedido_input.account_external_id,
                "representante_id": pedido_input.representante_id,
                "total_estimado": str(total_estimado),
                "ficticio": _is_ficticio,
                "observacao": pedido_input.observacao,
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
            account_external_id=row.get("account_external_id"),
            representante_id=row["representante_id"],
            status=StatusPedido(row["status"]),
            total_estimado=Decimal(str(row["total_estimado"])),
            pdf_path=row["pdf_path"],
            criado_em=row["criado_em"],
            ficticio=bool(row["ficticio"]) if row["ficticio"] is not None else False,
            observacao=row["observacao"],
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
                       status, total_estimado, pdf_path, criado_em,
                       ficticio, observacao
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
            ficticio=bool(row["ficticio"]) if row.get("ficticio") is not None else False,
            observacao=row.get("observacao"),
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
                       status, total_estimado, pdf_path, criado_em,
                       ficticio, observacao
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
                    ficticio=bool(row["ficticio"]) if row.get("ficticio") is not None else False,
                    observacao=row.get("observacao"),
                    itens=itens,
                )
            )
        return pedidos

    async def listar_por_tenant_status(
        self,
        tenant_id: str,
        status: str | None,
        limit: int,
        session: AsyncSession,
        dias: int = 30,
    ) -> list[dict]:
        """Lista pedidos do tenant com JOIN em clientes_b2b para nome do cliente.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            status: filtro por status (pendente/confirmado/cancelado). None = todos.
            limit: máximo de registros retornados.
            session: sessão SQLAlchemy assíncrona.
            dias: janela de dias para busca sem filtro de status (padrão 30).

        Returns:
            Lista de dicts com id, cliente_nome, total_estimado, status, criado_em.
            Ordenada por criado_em DESC em Python (padrão do projeto).
        """
        from datetime import datetime, timedelta, timezone
        data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)

        # B-28: quando cliente_b2b_id for NULL (cliente EFOS-only), o nome vem de
        # commerce_accounts_b2b via account_external_id (fallback).
        base_select = """
            SELECT p.id, p.total_estimado, p.status, p.criado_em,
                   COALESCE(c.nome, ca.nome, 'Cliente desconhecido') AS cliente_nome,
                   r.nome AS representante_nome
            FROM pedidos p
            LEFT JOIN clientes_b2b c ON c.id = p.cliente_b2b_id
            LEFT JOIN commerce_accounts_b2b ca
                ON ca.external_id = p.account_external_id
               AND ca.tenant_id = p.tenant_id
            LEFT JOIN representantes r
                ON r.id = p.representante_id AND r.tenant_id = p.tenant_id
        """
        if status is not None:
            result = await session.execute(
                text(base_select + """
                    WHERE p.tenant_id = :tenant_id AND p.status = :status
                      AND p.ficticio = FALSE
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "status": status, "limit": limit, "data_inicio": data_inicio},
            )
        else:
            result = await session.execute(
                text(base_select + """
                    WHERE p.tenant_id = :tenant_id
                      AND p.ficticio = FALSE
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit, "data_inicio": data_inicio},
            )
        rows = result.mappings().all()
        pedidos = [
            {
                "id": row["id"],
                "cliente_nome": row["cliente_nome"],
                "representante_nome": row["representante_nome"],
                "total_estimado": Decimal(str(row["total_estimado"])),
                "status": row["status"],
                "criado_em": row["criado_em"],
            }
            for row in rows
        ]
        return sorted(pedidos, key=lambda p: p["criado_em"] or "", reverse=True)

    async def listar_por_representante(
        self,
        tenant_id: str,
        representante_id: str,
        status: str | None,
        limit: int,
        session: AsyncSession,
        dias: int = 30,
    ) -> list[dict]:
        """Lista pedidos da carteira do representante com JOIN em clientes_b2b.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            representante_id: ID do representante — restringe à carteira do rep.
            status: filtro por status. None = últimos 30 dias.
            limit: máximo de registros retornados.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts com id, cliente_nome, total_estimado, status, criado_em.
            Ordenada por criado_em DESC em Python.
        """
        from datetime import datetime, timedelta, timezone
        data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)

        if status is not None:
            result = await session.execute(
                text("""
                    SELECT p.id, p.total_estimado, p.status, p.criado_em,
                           COALESCE(c.nome, 'Cliente desconhecido') AS cliente_nome
                    FROM pedidos p
                    LEFT JOIN clientes_b2b c ON c.id = p.cliente_b2b_id
                    WHERE p.tenant_id = :tenant_id
                      AND p.representante_id = :representante_id
                      AND p.status = :status
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "representante_id": representante_id,
                    "status": status,
                    "limit": limit,
                    "data_inicio": data_inicio,
                },
            )
        else:
            result = await session.execute(
                text("""
                    SELECT p.id, p.total_estimado, p.status, p.criado_em,
                           COALESCE(c.nome, 'Cliente desconhecido') AS cliente_nome
                    FROM pedidos p
                    LEFT JOIN clientes_b2b c ON c.id = p.cliente_b2b_id
                    WHERE p.tenant_id = :tenant_id
                      AND p.representante_id = :representante_id
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "representante_id": representante_id,
                    "limit": limit,
                    "data_inicio": data_inicio,
                },
            )
        rows = result.mappings().all()
        pedidos = [
            {
                "id": row["id"],
                "cliente_nome": row["cliente_nome"],
                "total_estimado": Decimal(str(row["total_estimado"])),
                "status": row["status"],
                "criado_em": row["criado_em"],
            }
            for row in rows
        ]
        return sorted(pedidos, key=lambda p: p["criado_em"] or "", reverse=True)

    async def listar_por_cliente(
        self,
        tenant_id: str,
        cliente_b2b_id: str,
        status: str | None,
        limit: int,
        session: AsyncSession,
        dias: int = 30,
    ) -> list[dict]:
        """Lista pedidos de um cliente B2B específico.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            cliente_b2b_id: ID do cliente — restringe aos pedidos desse cliente.
            status: filtro por status. None = últimos 30 dias.
            limit: máximo de registros retornados.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts com id, total_estimado, status, criado_em.
            Ordenada por criado_em DESC em Python.
        """
        from datetime import datetime, timedelta, timezone
        data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)

        if status is not None:
            result = await session.execute(
                text("""
                    SELECT p.id, p.total_estimado, p.status, p.criado_em
                    FROM pedidos p
                    WHERE p.tenant_id = :tenant_id
                      AND p.cliente_b2b_id = :cliente_b2b_id
                      AND p.status = :status
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "cliente_b2b_id": cliente_b2b_id,
                    "status": status,
                    "limit": limit,
                    "data_inicio": data_inicio,
                },
            )
        else:
            result = await session.execute(
                text("""
                    SELECT p.id, p.total_estimado, p.status, p.criado_em
                    FROM pedidos p
                    WHERE p.tenant_id = :tenant_id
                      AND p.cliente_b2b_id = :cliente_b2b_id
                      AND p.criado_em >= :data_inicio
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "cliente_b2b_id": cliente_b2b_id,
                    "limit": limit,
                    "data_inicio": data_inicio,
                },
            )
        rows = result.mappings().all()
        pedidos = [
            {
                "id": row["id"],
                "total_estimado": Decimal(str(row["total_estimado"])),
                "status": row["status"],
                "criado_em": row["criado_em"],
            }
            for row in rows
        ]
        return sorted(pedidos, key=lambda p: p["criado_em"] or "", reverse=True)

    async def aprovar_pedido(
        self,
        tenant_id: str,
        pedido_id: str,
        session: AsyncSession,
    ) -> dict | None:
        """Altera status do pedido de pendente para confirmado.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_id: ID do pedido a aprovar.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Dict com id, status, cliente_b2b_id do pedido atualizado.
            None se pedido não encontrado ou não estava pendente.
        """
        result = await session.execute(
            text("""
                UPDATE pedidos
                SET status = 'confirmado'
                WHERE tenant_id = :tenant_id
                  AND id = :pedido_id
                  AND status = 'pendente'
                RETURNING id, status, cliente_b2b_id, total_estimado
            """),
            {"tenant_id": tenant_id, "pedido_id": pedido_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        log.info(
            "pedido_aprovado",
            tenant_id=tenant_id,
            pedido_id=pedido_id,
        )
        return {
            "id": row["id"],
            "status": row["status"],
            "cliente_b2b_id": row["cliente_b2b_id"],
            "total_estimado": str(row["total_estimado"]),
        }

    async def get_pedido_cliente_b2b_id(
        self,
        tenant_id: str,
        pedido_id: str,
        session: AsyncSession,
    ) -> str | None:
        """Retorna o cliente_b2b_id de um pedido (para validação de carteira).

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_id: ID do pedido.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            cliente_b2b_id do pedido, ou None se não encontrado.
        """
        result = await session.execute(
            text("""
                SELECT cliente_b2b_id FROM pedidos
                WHERE tenant_id = :tenant_id AND id = :pedido_id
            """),
            {"tenant_id": tenant_id, "pedido_id": pedido_id},
        )
        row = result.mappings().first()
        return row["cliente_b2b_id"] if row else None

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
