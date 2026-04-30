"""Repositório do domínio Catalog — acesso ao PostgreSQL com pgvector.

Camada Repo: importa apenas src.catalog.types, src.catalog.config e providers.db.
Toda função pública recebe tenant_id como parâmetro obrigatório.
Toda query filtra por tenant_id — isolamento de tenant garantido mecanicamente.

E18 (Sprint 10): todos os métodos de leitura migrados de `produtos` legado
para `commerce_products`. Métodos exclusivos do enricher (upsert_produto_bruto,
update_produto_enriquecido, update_embedding, update_status,
listar_produtos_sem_embedding) removidos — código morto após E19.
Tipo renomeado de `Produto` para `CommerceProduct` (Sprint 10 B-33 fix).
"""

from __future__ import annotations

import structlog
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.catalog.types import (
    CommerceProduct,
    PrecoDiferenciado,
    ResultadoBusca,
    StatusEnriquecimento,
)

log = structlog.get_logger(__name__)

# Fragmento SQL reutilizável para SELECT de commerce_products mapeado para
# as colunas esperadas por _row_to_produto.
# Mapeamento de colunas commerce_products → alias Produto:
#   external_id         → codigo_externo
#   descricao           → texto_rag
#   synced_at           → criado_em e atualizado_em
#   NULL                → campos legados (nome_bruto, marca, categoria, tags,
#                         meta_agente, url_imagem, imagem_local)
#   'ativo'             → status_enriquecimento (fixo — todos os produtos
#                         em commerce_products são considerados ativos)
_COMMERCE_PRODUCTS_SELECT = """
    SELECT
        id::text                    AS id,
        tenant_id,
        COALESCE(codigo, external_id) AS codigo_externo,
        nome                        AS nome_bruto,
        nome,
        NULL::text                  AS marca,
        NULL::text                  AS categoria,
        NULL::text[]                AS tags,
        descricao                   AS texto_rag,
        NULL::jsonb                 AS meta_agente,
        preco_padrao,
        NULL::text                  AS url_imagem,
        NULL::text                  AS imagem_local,
        'ativo'::text               AS status_enriquecimento,
        synced_at                   AS criado_em,
        synced_at                   AS atualizado_em
    FROM commerce_products
"""


class CatalogRepo:
    """Repositório de produtos e preços diferenciados.

    Todas as operações são isoladas por tenant_id.
    Usa SQL raw para operações com pgvector (<=> operator).
    Fonte de dados: commerce_products (E18 — produtos legado removido em E20).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Inicializa com a session factory injetada.

        Args:
            session_factory: async_sessionmaker do SQLAlchemy.
        """
        self._session_factory = session_factory

    # ─────────────────────────────────────────────
    # Produtos — leitura (commerce_products)
    # ─────────────────────────────────────────────

    async def get_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> CommerceProduct | None:
        """Busca produto por ID dentro do tenant.

        E18: lê de commerce_products (não mais de produtos legado).

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            CommerceProduct encontrado ou None.
        """
        sql = text(
            _COMMERCE_PRODUCTS_SELECT + """
            WHERE tenant_id = :tenant_id
              AND id = :produto_id::uuid
        """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {"tenant_id": tenant_id, "produto_id": str(produto_id)},
            )
            row = result.fetchone()

        return self._row_to_produto(row) if row else None

    async def get_produto_por_codigo(
        self, tenant_id: str, codigo_externo: str
    ) -> CommerceProduct | None:
        """Busca produto por código externo (lookup exato).

        E18: lê de commerce_products. Verifica as colunas `codigo` e `external_id`
        (COALESCE na seleção; filtro nos dois campos para compatibilidade).

        Args:
            tenant_id: identificador do tenant.
            codigo_externo: código do produto no ERP.

        Returns:
            CommerceProduct encontrado ou None.
        """
        sql = text(
            _COMMERCE_PRODUCTS_SELECT + """
            WHERE tenant_id = :tenant_id
              AND (codigo = :codigo_externo OR external_id = :codigo_externo)
            LIMIT 1
        """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {"tenant_id": tenant_id, "codigo_externo": codigo_externo},
            )
            row = result.fetchone()

        return self._row_to_produto(row) if row else None

    async def listar_produtos(
        self,
        tenant_id: str,
        status: StatusEnriquecimento | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommerceProduct]:
        """Lista produtos de um tenant com filtro opcional de status.

        E18: lê de commerce_products. O parâmetro `status` não afeta o resultado
        (todos os produtos em commerce_products são considerados ativos); mantido
        na assinatura para compatibilidade com callers existentes.

        Args:
            tenant_id: identificador do tenant.
            status: ignorado (compat); todos os produtos são 'ativo'.
            limit: máximo de resultados (padrão 50).
            offset: paginação (padrão 0).

        Returns:
            Lista de produtos ordenados por synced_at desc.
        """
        sql = text(
            _COMMERCE_PRODUCTS_SELECT + """
            WHERE tenant_id = :tenant_id
              AND ativo = true
            ORDER BY synced_at DESC
            LIMIT :limit OFFSET :offset
        """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {"tenant_id": tenant_id, "limit": limit, "offset": offset},
            )
            rows = result.fetchall()

        return [self._row_to_produto(row) for row in rows]

    async def buscar_por_embedding(
        self,
        tenant_id: str,
        embedding: list[float],
        limit: int = 10,
        distancia_maxima: float = 0.75,
    ) -> list[tuple[CommerceProduct, float]]:
        """Busca semântica por similaridade de embedding (cosine distance).

        E18: fonte confirmada commerce_products (não mais produtos legado).

        Args:
            tenant_id: identificador do tenant — filtro obrigatório.
            embedding: vetor de query com 1536 dimensões.
            limit: número máximo de resultados.
            distancia_maxima: distância cosine máxima (0 = idêntico, 1 = oposto).

        Returns:
            Lista de (CommerceProduct, distancia) ordenada por similaridade crescente.
        """
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Notas de implementação (asyncpg + pgvector):
        # 1. O vetor é interpolado no SQL (não como parâmetro bind) porque asyncpg
        #    não infere o tipo 'vector' automaticamente em prepared statements.
        # 2. ORDER BY com expressão vetorial em prepared statements asyncpg retorna
        #    silenciosamente 0 rows (bug confirmado por testes de isolamento).
        # 3. LIMIT é aplicado em Python após sort — mesmo padrão do Sprint 9.
        sql = text(f"""
            SELECT
                id::text                    AS id,
                tenant_id,
                COALESCE(codigo, external_id) AS codigo_externo,
                nome                        AS nome_bruto,
                nome,
                NULL::text                  AS marca,
                NULL::text                  AS categoria,
                NULL::text[]                AS tags,
                descricao                   AS texto_rag,
                NULL::jsonb                 AS meta_agente,
                preco_padrao,
                NULL::text                  AS url_imagem,
                NULL::text                  AS imagem_local,
                'ativo'::text               AS status_enriquecimento,
                synced_at                   AS criado_em,
                synced_at                   AS atualizado_em,
                embedding <=> '{vec_str}'::vector AS distancia
            FROM commerce_products
            WHERE tenant_id = :tenant_id
              AND embedding IS NOT NULL
              AND ativo = true
              AND embedding <=> '{vec_str}'::vector < :distancia_maxima
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "distancia_maxima": distancia_maxima,
                },
            )
            rows = result.fetchall()

        # Sort por distância crescente em Python, depois slice para o limit
        sorted_rows = sorted(rows, key=lambda r: float(r.distancia))[:limit]
        return [(self._row_to_produto(row), float(row.distancia)) for row in sorted_rows]

    # ─────────────────────────────────────────────
    # Preços diferenciados
    # ─────────────────────────────────────────────

    async def upsert_preco_diferenciado(
        self, tenant_id: str, preco: PrecoDiferenciado
    ) -> None:
        """Insere ou atualiza preço diferenciado para um cliente.

        Args:
            tenant_id: identificador do tenant.
            preco: dados do preço diferenciado.
        """
        sql = text("""
            INSERT INTO precos_diferenciados (
                tenant_id, codigo_produto, ean, cliente_cnpj, preco_cliente
            )
            VALUES (
                :tenant_id, :codigo_produto, :ean, :cliente_cnpj, :preco_cliente
            )
            ON CONFLICT (tenant_id, codigo_produto, cliente_cnpj) DO UPDATE SET
                ean           = EXCLUDED.ean,
                preco_cliente = EXCLUDED.preco_cliente
        """)

        async with self._session_factory() as session:
            await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "codigo_produto": preco.codigo_produto,
                    "ean": preco.ean,
                    "cliente_cnpj": preco.cliente_cnpj,
                    "preco_cliente": str(preco.preco_cliente),
                },
            )
            await session.commit()

    async def get_preco_diferenciado(
        self,
        tenant_id: str,
        codigo_produto: str,
        cliente_cnpj: str,
    ) -> Decimal | None:
        """Busca preço diferenciado de um produto para um cliente.

        Args:
            tenant_id: identificador do tenant.
            codigo_produto: código do produto.
            cliente_cnpj: CNPJ do cliente (somente dígitos).

        Returns:
            Preço diferenciado ou None se não existir.
        """
        # Normaliza CNPJ para dígitos
        cnpj_digits = "".join(c for c in cliente_cnpj if c.isdigit())

        sql = text("""
            SELECT preco_cliente
            FROM precos_diferenciados
            WHERE tenant_id = :tenant_id
              AND codigo_produto = :codigo_produto
              AND cliente_cnpj = :cliente_cnpj
            LIMIT 1
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "codigo_produto": codigo_produto,
                    "cliente_cnpj": cnpj_digits,
                },
            )
            row = result.fetchone()

        return Decimal(str(row.preco_cliente)) if row else None

    # ─────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────

    @staticmethod
    def _row_to_produto(row: Any) -> CommerceProduct:
        """Converte row SQLAlchemy (commerce_products) para objeto CommerceProduct.

        Campos ausentes em commerce_products (nome_bruto, marca, categoria,
        tags, meta_agente, url_imagem, imagem_local) recebem valor padrão
        compatível com o tipo CommerceProduct para não quebrar callers existentes.
        status_enriquecimento fixado em StatusEnriquecimento.ATIVO.
        """
        import json as _json
        from decimal import Decimal as _D

        meta = row.meta_agente
        if isinstance(meta, str):
            meta = _json.loads(meta)
        elif meta is None:
            meta = {}

        preco = row.preco_padrao
        if preco is not None:
            preco = _D(str(preco))

        tags = row.tags or []

        imagem_local: str | None = getattr(row, "imagem_local", None)

        # nome_bruto: commerce_products não tem campo dedicado; usa nome como fallback
        nome_bruto: str = row.nome_bruto or row.nome or ""

        return CommerceProduct(
            id=UUID(str(row.id)),
            tenant_id=row.tenant_id,
            codigo_externo=row.codigo_externo,
            nome_bruto=nome_bruto,
            nome=row.nome,
            marca=getattr(row, "marca", None),
            categoria=getattr(row, "categoria", None),
            tags=list(tags),
            texto_rag=getattr(row, "texto_rag", None),
            meta_agente=meta,
            preco_padrao=preco,
            url_imagem=getattr(row, "url_imagem", None),
            imagem_local=imagem_local,
            status_enriquecimento=StatusEnriquecimento.ATIVO,
            criado_em=row.criado_em,
            atualizado_em=row.atualizado_em,
        )
