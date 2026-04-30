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

    async def count_produtos(
        self,
        tenant_id: str,
        session: AsyncSession,
    ) -> int:
        """Conta quantos produtos existem em commerce_products para o tenant.

        Usado por catalog/service.py para decidir se usa commerce_products
        como fonte primária de busca (fallback E1a do Sprint 9).

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Número de produtos em commerce_products para este tenant.
        """
        result = await session.execute(
            text("""
                SELECT COUNT(*) AS total
                FROM commerce_products
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        return int(row["total"]) if row else 0

    async def buscar_produtos_commerce(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        session: AsyncSession | None = None,
    ) -> list[dict]:
        """Busca produtos em commerce_products por código ou nome (ILIKE).

        Usado como fonte primária de busca por código/nome quando commerce_products
        tem dados (fallback E1a do Sprint 9). Busca semântica pgvector permanece
        em catalog.produtos.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            query: texto de busca — nome ou código externo.
            limit: número máximo de resultados.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts com {external_id, nome, preco_padrao, ativo}.
        """
        if session is None:
            return []
        result = await session.execute(
            text("""
                SELECT external_id, nome, preco_padrao, ativo, codigo
                FROM commerce_products
                WHERE tenant_id = :tenant_id
                  AND (
                    LOWER(nome) LIKE LOWER(:query_like)
                    OR external_id = :query_exact
                    OR codigo = :query_exact
                  )
                ORDER BY nome ASC
                LIMIT :limit
            """),
            {
                "tenant_id": tenant_id,
                "query_like": f"%{query}%",
                "query_exact": query,
                "limit": limit,
            },
        )
        rows = result.mappings().all()
        return [
            {
                "external_id": row["external_id"],
                "codigo": row["codigo"],
                "nome": row["nome"],
                "preco_padrao": str(row["preco_padrao"]) if row["preco_padrao"] else None,
                "ativo": bool(row["ativo"]),
            }
            for row in rows
        ]

    async def buscar_clientes_commerce(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        session: AsyncSession | None = None,
    ) -> list[dict]:
        """Busca clientes em commerce_accounts_b2b por nome (ILIKE).

        Fallback E1b: usado quando clientes_b2b retorna 0 resultados.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            query: texto de busca — nome do cliente.
            limit: número máximo de resultados.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts normalizados compatíveis com ClienteB2B.
        """
        if session is None:
            return []
        result = await session.execute(
            text("""
                SELECT external_id, codigo, nome, cnpj, cidade, situacao_cliente,
                       vendedor_codigo
                FROM commerce_accounts_b2b
                WHERE tenant_id = :tenant_id
                  AND LOWER(nome) LIKE LOWER(:query_like)
                ORDER BY nome ASC
                LIMIT :limit
            """),
            {
                "tenant_id": tenant_id,
                "query_like": f"%{query}%",
                "limit": limit,
            },
        )
        rows = result.mappings().all()
        return [
            {
                "id": row["external_id"],
                "tenant_id": tenant_id,
                "nome": row["nome"],
                "cnpj": row["cnpj"] or "",
                "telefone": None,
                "ativo": row["situacao_cliente"] == 1 if row["situacao_cliente"] is not None else True,
                "representante_id": None,
                "codigo": row["codigo"],
                "cidade": row["cidade"],
                "fonte": "commerce_accounts_b2b",
            }
            for row in rows
        ]

    async def listar_pedidos_efos(
        self,
        tenant_id: str,
        status: str | None,
        dias: int,
        limit: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Lista pedidos de commerce_orders com filtro opcional de status.

        B-14: tabela pedidos pode estar vazia (dados reais em commerce_orders).
        Esta query retorna pedidos importados do EFOS.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            status: filtro de status (pendente/confirmado/cancelado). None = todos.
            dias: janela de busca em dias.
            limit: máximo de registros.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de dicts compatível com listar_por_tenant_status.
        """
        from datetime import datetime, timedelta, timezone
        data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)

        if status is not None:
            result = await session.execute(
                text("""
                    SELECT
                        o.numero_pedido               AS id,
                        COALESCE(NULLIF(o.cliente_nome, ''), a.nome, o.cliente_codigo) AS cliente_nome,
                        v.ve_nome                     AS representante_nome,
                        o.total                       AS total_estimado,
                        :status_val                   AS status,
                        o.data_pedido                 AS criado_em
                    FROM commerce_orders o
                    LEFT JOIN commerce_vendedores v
                        ON v.tenant_id = o.tenant_id
                       AND v.ve_codigo = o.vendedor_codigo
                    LEFT JOIN commerce_accounts_b2b a
                        ON a.tenant_id = o.tenant_id
                       AND a.codigo = o.cliente_codigo
                    WHERE o.tenant_id = :tenant_id
                      AND o.data_pedido >= :data_inicio
                    ORDER BY o.data_pedido DESC
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "status_val": status,
                    "data_inicio": data_inicio,
                    "limit": limit,
                },
            )
        else:
            result = await session.execute(
                text("""
                    SELECT
                        o.numero_pedido               AS id,
                        COALESCE(NULLIF(o.cliente_nome, ''), a.nome, o.cliente_codigo) AS cliente_nome,
                        v.ve_nome                     AS representante_nome,
                        o.total                       AS total_estimado,
                        'confirmado'                  AS status,
                        o.data_pedido                 AS criado_em
                    FROM commerce_orders o
                    LEFT JOIN commerce_vendedores v
                        ON v.tenant_id = o.tenant_id
                       AND v.ve_codigo = o.vendedor_codigo
                    LEFT JOIN commerce_accounts_b2b a
                        ON a.tenant_id = o.tenant_id
                       AND a.codigo = o.cliente_codigo
                    WHERE o.tenant_id = :tenant_id
                      AND o.data_pedido >= :data_inicio
                    ORDER BY o.data_pedido DESC
                    LIMIT :limit
                """),
                {
                    "tenant_id": tenant_id,
                    "data_inicio": data_inicio,
                    "limit": limit,
                },
            )
        rows = result.mappings().all()
        return [
            {
                "id": row["id"],
                "cliente_nome": row["cliente_nome"] or "Cliente desconhecido",
                "representante_nome": row["representante_nome"] or "Sem representante",
                "total_estimado": Decimal(str(row["total_estimado"] or 0)),
                "status": row["status"],
                "criado_em": row["criado_em"],
                "fonte": "commerce_orders",
            }
            for row in rows
        ]

    async def ranking_vendedores(
        self,
        tenant_id: str,
        mes: int,
        ano: int,
        top_n: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Ranking de vendedores por GMV em um mês/ano via SQL agregada.

        E6 (B-25a): query única em vez de 24 chamadas seriais.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            mes: mês (1–12).
            ano: ano (ex: 2026).
            top_n: número de vendedores a retornar.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {vendedor_nome, ve_codigo, total_vendido, qtde_pedidos}
            ordenada por total_vendido DESC.
        """
        result = await session.execute(
            text("""
                SELECT
                    COALESCE(v.ve_nome, o.vendedor_codigo) AS vendedor_nome,
                    o.vendedor_codigo                       AS ve_codigo,
                    COALESCE(SUM(o.total), 0)               AS total_vendido,
                    COUNT(*)                                AS qtde_pedidos
                FROM commerce_orders o
                LEFT JOIN commerce_vendedores v
                    ON v.tenant_id = o.tenant_id
                   AND v.ve_codigo = o.vendedor_codigo
                WHERE o.tenant_id = :tenant_id
                  AND o.mes = :mes
                  AND o.ano = :ano
                  AND o.vendedor_codigo IS NOT NULL
                  AND o.vendedor_codigo != ''
                GROUP BY o.vendedor_codigo, v.ve_nome
                ORDER BY total_vendido DESC
                LIMIT :top_n
            """),
            {
                "tenant_id": tenant_id,
                "mes": mes,
                "ano": ano,
                "top_n": top_n,
            },
        )
        rows = result.mappings().all()
        return [
            {
                "vendedor_nome": row["vendedor_nome"] or "Desconhecido",
                "ve_codigo": row["ve_codigo"],
                "total_vendido": Decimal(str(row["total_vendido"] or 0)),
                "qtde_pedidos": int(row["qtde_pedidos"] or 0),
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
