"""Repositório do domínio Commerce — queries sobre tabelas commerce_*.

Camada Repo: importa apenas src.commerce.types e stdlib.
Não importa agents/, catalog/, orders/, tenants/, dashboard/, integrations/.
Toda query filtra por tenant_id para isolamento de tenant.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class CommerceRepo:
    """Repositório de dados de commerce — relatórios EFOS via commerce_*.

    Queries agregadas sobre pedidos, clientes e vendedores importados do EFOS.
    """

    async def relatorio_vendas_representante(
        self,
        tenant_id: str,
        vendedor_id: str,
        mes: int,
        ano: int,
        session: AsyncSession,
    ) -> dict:
        """Relatório de vendas por representante em um mês/ano.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            vendedor_id: ve_codigo do representante.
            mes: mês (1–12).
            ano: ano (ex: 2026).
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Dict com {total_vendido: Decimal, qtde_pedidos: int, clientes: list}.
        """
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)                          AS qtde_pedidos,
                    COALESCE(SUM(o.total), 0)         AS total_vendido,
                    array_agg(DISTINCT o.cliente_nome) AS clientes_raw
                FROM commerce_orders o
                WHERE o.tenant_id = :tenant_id
                  AND o.vendedor_codigo = :vendedor_id
                  AND o.mes = :mes
                  AND o.ano = :ano
            """),
            {
                "tenant_id": tenant_id,
                "vendedor_id": vendedor_id,
                "mes": mes,
                "ano": ano,
            },
        )
        row = result.mappings().first()
        if row is None:
            return {"total_vendido": Decimal("0"), "qtde_pedidos": 0, "clientes": []}

        clientes_raw = row["clientes_raw"] or []
        clientes = [c for c in clientes_raw if c]

        return {
            "total_vendido": Decimal(str(row["total_vendido"] or 0)),
            "qtde_pedidos": int(row["qtde_pedidos"] or 0),
            "clientes": clientes,
        }

    async def relatorio_vendas_cidade(
        self,
        tenant_id: str,
        cidade: str,
        mes: int,
        ano: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Relatório de vendas por cidade em um mês/ano.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            cidade: cidade em UPPERCASE (gotcha: EFOS armazena em UPPERCASE).
            mes: mês (1–12).
            ano: ano (ex: 2026).
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {cliente: str, total: Decimal} ordenada por total DESC.
        """
        result = await session.execute(
            text("""
                SELECT
                    o.cliente_nome                AS cliente,
                    COALESCE(SUM(o.total), 0)     AS total
                FROM commerce_orders o
                JOIN commerce_accounts_b2b a
                    ON a.tenant_id = o.tenant_id
                   AND a.codigo = o.cliente_codigo
                WHERE o.tenant_id = :tenant_id
                  AND a.cidade = :cidade
                  AND o.mes = :mes
                  AND o.ano = :ano
                GROUP BY o.cliente_nome
                ORDER BY total DESC
            """),
            {
                "tenant_id": tenant_id,
                "cidade": cidade,
                "mes": mes,
                "ano": ano,
            },
        )
        rows = result.mappings().all()
        return [
            {
                "cliente": row["cliente"] or "Desconhecido",
                "total": Decimal(str(row["total"] or 0)),
            }
            for row in rows
        ]

    async def listar_clientes_inativos(
        self,
        tenant_id: str,
        cidade: str | None,
        session: AsyncSession,
    ) -> list[dict]:
        """Lista clientes com situacao_cliente=2 (inativos no EFOS).

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            cidade: filtrar por cidade (UPPERCASE); None = todas as cidades.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {nome: str, cnpj: str, telefone: str, cidade: str}
            ordenada por nome ASC.
        """
        if cidade is not None:
            result = await session.execute(
                text("""
                    SELECT nome, cnpj, cidade
                    FROM commerce_accounts_b2b
                    WHERE tenant_id = :tenant_id
                      AND situacao_cliente = 2
                      AND cidade = :cidade
                    ORDER BY nome ASC
                """),
                {"tenant_id": tenant_id, "cidade": cidade},
            )
        else:
            result = await session.execute(
                text("""
                    SELECT nome, cnpj, cidade
                    FROM commerce_accounts_b2b
                    WHERE tenant_id = :tenant_id
                      AND situacao_cliente = 2
                    ORDER BY nome ASC
                """),
                {"tenant_id": tenant_id},
            )

        rows = result.mappings().all()
        return [
            {
                "nome": row["nome"] or "Desconhecido",
                "cnpj": row["cnpj"] or "",
                "telefone": "",  # campo não disponível no EFOS
                "cidade": row["cidade"] or "",
            }
            for row in rows
        ]
