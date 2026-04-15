"""Repositório do domínio Catalog — acesso ao PostgreSQL com pgvector.

Camada Repo: importa apenas src.catalog.types, src.catalog.config e providers.db.
Toda função pública recebe tenant_id como parâmetro obrigatório.
Toda query filtra por tenant_id — isolamento de tenant garantido mecanicamente.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.catalog.types import (
    Produto,
    ProdutoBruto,
    ProdutoEnriquecido,
    PrecoDiferenciado,
    ResultadoBusca,
    StatusEnriquecimento,
)

log = structlog.get_logger(__name__)


class CatalogRepo:
    """Repositório de produtos e preços diferenciados.

    Todas as operações são isoladas por tenant_id.
    Usa SQL raw para operações com pgvector (<=> operator).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Inicializa com a session factory injetada.

        Args:
            session_factory: async_sessionmaker do SQLAlchemy.
        """
        self._session_factory = session_factory

    # ─────────────────────────────────────────────
    # Produtos — escrita
    # ─────────────────────────────────────────────

    async def upsert_produto_bruto(
        self, tenant_id: str, produto: ProdutoBruto
    ) -> Produto:
        """Insere ou atualiza um produto bruto (ON CONFLICT UPDATE).

        Args:
            tenant_id: identificador do tenant.
            produto: dados brutos extraídos pelo crawler.

        Returns:
            Produto persistido com id e timestamps.
        """
        sql = text("""
            INSERT INTO produtos (
                tenant_id, codigo_externo, nome_bruto, preco_padrao,
                url_imagem, imagem_local, categoria, status_enriquecimento
            )
            VALUES (
                :tenant_id, :codigo_externo, :nome_bruto, :preco_padrao,
                :url_imagem, :imagem_local, :categoria, 'pendente'
            )
            ON CONFLICT (tenant_id, codigo_externo) DO UPDATE SET
                nome_bruto        = EXCLUDED.nome_bruto,
                preco_padrao      = EXCLUDED.preco_padrao,
                url_imagem        = EXCLUDED.url_imagem,
                imagem_local      = COALESCE(EXCLUDED.imagem_local, produtos.imagem_local),
                categoria         = EXCLUDED.categoria,
                atualizado_em     = NOW()
            RETURNING
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "codigo_externo": produto.codigo_externo,
                    "nome_bruto": produto.nome_bruto,
                    "preco_padrao": str(produto.preco_padrao) if produto.preco_padrao else None,
                    "url_imagem": produto.url_imagem,
                    "imagem_local": produto.imagem_local,
                    "categoria": produto.categoria,
                },
            )
            await session.commit()
            row = result.fetchone()

        log.info(
            "produto_upserted",
            tenant_id=tenant_id,
            codigo_externo=produto.codigo_externo,
        )
        return self._row_to_produto(row)

    async def update_produto_enriquecido(
        self,
        tenant_id: str,
        codigo_externo: str,
        enriquecido: ProdutoEnriquecido,
    ) -> Produto:
        """Atualiza campos de enriquecimento de um produto.

        Args:
            tenant_id: identificador do tenant.
            codigo_externo: código do produto no sistema do tenant.
            enriquecido: dados enriquecidos pelo Haiku.

        Returns:
            Produto atualizado.

        Raises:
            ValueError: se produto não encontrado para este tenant.
        """
        sql = text("""
            UPDATE produtos SET
                nome                  = :nome,
                marca                 = :marca,
                categoria             = :categoria,
                tags                  = :tags,
                texto_rag             = :texto_rag,
                meta_agente           = CAST(:meta_agente AS jsonb),
                status_enriquecimento = 'enriquecido',
                atualizado_em         = NOW()
            WHERE tenant_id = :tenant_id
              AND codigo_externo = :codigo_externo
            RETURNING
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em
        """)

        import json

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "codigo_externo": codigo_externo,
                    "nome": enriquecido.nome,
                    "marca": enriquecido.marca,
                    "categoria": enriquecido.categoria,
                    "tags": enriquecido.tags,
                    "texto_rag": enriquecido.texto_rag,
                    "meta_agente": json.dumps(enriquecido.meta_agente, ensure_ascii=False),
                },
            )
            await session.commit()
            row = result.fetchone()

        if row is None:
            raise ValueError(
                f"Produto não encontrado: tenant={tenant_id}, codigo={codigo_externo}"
            )

        log.info(
            "produto_enriquecido",
            tenant_id=tenant_id,
            codigo_externo=codigo_externo,
        )
        return self._row_to_produto(row)

    async def update_embedding(
        self,
        tenant_id: str,
        produto_id: UUID,
        embedding: list[float],
    ) -> None:
        """Atualiza o embedding vetorial de um produto.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.
            embedding: lista de 1536 floats gerados pelo OpenAI.
        """
        # Formata como string de array PostgreSQL: '[0.1, 0.2, ...]'
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        sql = text("""
            UPDATE produtos
            SET embedding = CAST(:embedding AS vector),
                atualizado_em = NOW()
            WHERE tenant_id = :tenant_id
              AND id = :produto_id
        """)

        async with self._session_factory() as session:
            await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "produto_id": str(produto_id),
                    "embedding": vec_str,
                },
            )
            await session.commit()

        log.debug(
            "embedding_atualizado",
            tenant_id=tenant_id,
            produto_id=str(produto_id),
        )

    async def update_status(
        self,
        tenant_id: str,
        produto_id: UUID,
        status: StatusEnriquecimento,
    ) -> Produto:
        """Atualiza status de enriquecimento de um produto.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.
            status: novo status.

        Returns:
            Produto atualizado.

        Raises:
            ValueError: se produto não encontrado para este tenant.
        """
        sql = text("""
            UPDATE produtos
            SET status_enriquecimento = :status,
                atualizado_em = NOW()
            WHERE tenant_id = :tenant_id
              AND id = :produto_id
            RETURNING
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "produto_id": str(produto_id),
                    "status": status.value,
                },
            )
            await session.commit()
            row = result.fetchone()

        if row is None:
            raise ValueError(
                f"Produto não encontrado: tenant={tenant_id}, id={produto_id}"
            )

        return self._row_to_produto(row)

    # ─────────────────────────────────────────────
    # Produtos — leitura
    # ─────────────────────────────────────────────

    async def get_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> Produto | None:
        """Busca produto por ID dentro do tenant.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            Produto encontrado ou None.
        """
        sql = text("""
            SELECT
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em
            FROM produtos
            WHERE tenant_id = :tenant_id
              AND id = :produto_id
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {"tenant_id": tenant_id, "produto_id": str(produto_id)},
            )
            row = result.fetchone()

        return self._row_to_produto(row) if row else None

    async def listar_produtos(
        self,
        tenant_id: str,
        status: StatusEnriquecimento | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Produto]:
        """Lista produtos de um tenant com filtro opcional de status.

        Args:
            tenant_id: identificador do tenant.
            status: filtra por status de enriquecimento (opcional).
            limit: máximo de resultados (padrão 50).
            offset: paginação (padrão 0).

        Returns:
            Lista de produtos ordenados por atualizado_em desc.
        """
        if status is not None:
            sql = text("""
                SELECT
                    id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                    tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                    status_enriquecimento, criado_em, atualizado_em
                FROM produtos
                WHERE tenant_id = :tenant_id
                  AND status_enriquecimento = :status
                ORDER BY atualizado_em DESC
                LIMIT :limit OFFSET :offset
            """)
            params: dict[str, object] = {
                "tenant_id": tenant_id,
                "status": status.value,
                "limit": limit,
                "offset": offset,
            }
        else:
            sql = text("""
                SELECT
                    id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                    tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                    status_enriquecimento, criado_em, atualizado_em
                FROM produtos
                WHERE tenant_id = :tenant_id
                ORDER BY atualizado_em DESC
                LIMIT :limit OFFSET :offset
            """)
            params = {"tenant_id": tenant_id, "limit": limit, "offset": offset}

        async with self._session_factory() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        return [self._row_to_produto(row) for row in rows]

    async def listar_produtos_sem_embedding(
        self, tenant_id: str, limit: int = 100
    ) -> list[Produto]:
        """Lista produtos com status 'enriquecido' sem embedding gerado.

        Args:
            tenant_id: identificador do tenant.
            limit: máximo de resultados.

        Returns:
            Lista de produtos aguardando geração de embedding.
        """
        sql = text("""
            SELECT
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em
            FROM produtos
            WHERE tenant_id = :tenant_id
              AND status_enriquecimento = 'enriquecido'
              AND embedding IS NULL
              AND texto_rag IS NOT NULL
            ORDER BY atualizado_em ASC
            LIMIT :limit
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql, {"tenant_id": tenant_id, "limit": limit}
            )
            rows = result.fetchall()

        return [self._row_to_produto(row) for row in rows]

    async def buscar_por_embedding(
        self,
        tenant_id: str,
        embedding: list[float],
        limit: int = 10,
        distancia_maxima: float = 0.75,
    ) -> list[tuple[Produto, float]]:
        """Busca semântica por similaridade de embedding (cosine distance).

        Args:
            tenant_id: identificador do tenant — filtro obrigatório.
            embedding: vetor de query com 1536 dimensões.
            limit: número máximo de resultados.
            distancia_maxima: distância cosine máxima (0 = idêntico, 1 = oposto).

        Returns:
            Lista de (Produto, distancia) ordenada por similaridade crescente.
        """
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Notas de implementação:
        # 1. O vetor é interpolado diretamente no SQL (não como parâmetro bind)
        #    porque asyncpg não consegue inferir o tipo 'vector' do pgvector.
        #    A interpolação é segura: vec_str contém apenas floats gerados internamente.
        # 2. ORDER BY usa a expressão completa (não o alias 'distancia') porque
        #    asyncpg com prepared statements retorna 0 rows ao ordenar por alias
        #    de expressão vetorial — bug confirmado em testes de isolamento.
        sql = text(f"""
            SELECT
                id, tenant_id, codigo_externo, nome_bruto, nome, marca, categoria,
                tags, texto_rag, meta_agente, preco_padrao, url_imagem, imagem_local,
                status_enriquecimento, criado_em, atualizado_em,
                embedding <=> '{vec_str}'::vector AS distancia
            FROM produtos
            WHERE tenant_id = :tenant_id
              AND embedding IS NOT NULL
              AND status_enriquecimento IN ('enriquecido', 'ativo')
              AND embedding <=> '{vec_str}'::vector < :distancia_maxima
            ORDER BY embedding <=> '{vec_str}'::vector ASC
            LIMIT :limit
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql,
                {
                    "tenant_id": tenant_id,
                    "distancia_maxima": distancia_maxima,
                    "limit": limit,
                },
            )
            rows = result.fetchall()

        return [(self._row_to_produto(row), float(row.distancia)) for row in rows]

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
    def _row_to_produto(row: Any) -> Produto:
        """Converte row SQLAlchemy para objeto Produto."""
        import json as _json
        from decimal import Decimal as _D

        # row é um RowProxy — acesso por nome de coluna
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

        return Produto(
            id=UUID(str(row.id)),
            tenant_id=row.tenant_id,
            codigo_externo=row.codigo_externo,
            nome_bruto=row.nome_bruto,
            nome=row.nome,
            marca=row.marca,
            categoria=row.categoria,
            tags=list(tags),
            texto_rag=row.texto_rag,
            meta_agente=meta,
            preco_padrao=preco,
            url_imagem=row.url_imagem,
            imagem_local=imagem_local,
            status_enriquecimento=StatusEnriquecimento(row.status_enriquecimento),
            criado_em=row.criado_em,
            atualizado_em=row.atualizado_em,
        )
