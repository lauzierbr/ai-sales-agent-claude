"""Serviço do domínio Catalog — lógica de negócio.

Camada Service: importa apenas src.catalog.types, src.catalog.config e src.catalog.repo.
NÃO importa nada de src.catalog.runtime — injeção via EnricherProtocol.
Toda função pública tem OTel span e structlog.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import pandas as pd
import structlog
from opentelemetry import trace

from src.catalog.config import EnrichmentConfig
from src.catalog.repo import CatalogRepo
from src.catalog.types import (
    CrawlStatus,
    EnricherProtocol,
    ExcelUploadResult,
    Produto,
    PrecoDiferenciado,
    ProdutoBruto,
    ResultadoBusca,
    StatusEnriquecimento,
)

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class CatalogService:
    """Serviço de catálogo de produtos.

    Orquestra: enriquecimento, embeddings, busca semântica e preços diferenciados.
    O EnricherAgent é injetado como EnricherProtocol para preservar a camada de arquitetura.
    O cliente OpenAI é injetado para permitir mock nos testes unitários.
    """

    def __init__(
        self,
        repo: CatalogRepo,
        enricher: EnricherProtocol,
        embedding_client: Any,  # AsyncOpenAI — tipado como Any para evitar import externo
    ) -> None:
        """Inicializa o serviço com dependências injetadas.

        Args:
            repo: repositório de catálogo.
            enricher: agente de enriquecimento (implementa EnricherProtocol).
            embedding_client: cliente OpenAI assíncrono para geração de embeddings.
        """
        self._repo = repo
        self._enricher = enricher
        self._embedding_client: Any = embedding_client
        self._embedding_model = "text-embedding-3-small"

    # ─────────────────────────────────────────────
    # Persistência de produto bruto
    # ─────────────────────────────────────────────

    async def salvar_produto_bruto(
        self,
        tenant_id: str,
        produto: ProdutoBruto,
    ) -> Produto:
        """Persiste produto bruto extraído pelo crawler.

        Args:
            tenant_id: identificador do tenant.
            produto: produto bruto do crawler.

        Returns:
            Produto persistido no banco de dados.
        """
        with tracer.start_as_current_span("catalog.salvar_produto_bruto") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("codigo_externo", produto.codigo_externo)

            result = await self._repo.upsert_produto_bruto(tenant_id, produto)
            log.info(
                "produto_bruto_salvo",
                tenant_id=tenant_id,
                codigo_externo=produto.codigo_externo,
                produto_id=str(result.id),
            )
            return result

    # ─────────────────────────────────────────────
    # Pipeline de enriquecimento
    # ─────────────────────────────────────────────

    async def enriquecer_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> Produto:
        """Enriquece um produto existente via Claude Haiku e gera embedding.

        Fluxo:
        1. Busca produto no banco
        2. Chama enricher (Claude Haiku)
        3. Persiste resultado de enriquecimento
        4. Gera e salva embedding (OpenAI)

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto a enriquecer.

        Returns:
            Produto enriquecido e com embedding gerado.

        Raises:
            ValueError: se produto não encontrado.
        """
        with tracer.start_as_current_span("catalog.enriquecer_produto") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("produto_id", str(produto_id))

            produto = await self._repo.get_produto(tenant_id, produto_id)
            if produto is None:
                raise ValueError(
                    f"Produto não encontrado: tenant={tenant_id}, id={produto_id}"
                )

            produto_bruto = ProdutoBruto(
                codigo_externo=produto.codigo_externo,
                nome_bruto=produto.nome_bruto,
                tenant_id=tenant_id,
                descricao_bruta=produto.texto_rag,
                categoria=produto.categoria,
            )

            log.info(
                "enriquecimento_iniciado",
                tenant_id=tenant_id,
                produto_id=str(produto_id),
                codigo_externo=produto.codigo_externo,
            )

            enriquecido = await self._enricher.enriquecer(produto_bruto)
            produto_atualizado = await self._repo.update_produto_enriquecido(
                tenant_id, produto.codigo_externo, enriquecido
            )

            # Gera embedding após enriquecimento (texto_rag agora disponível)
            await self.gerar_e_salvar_embedding(tenant_id, produto_id)

            log.info(
                "enriquecimento_concluido",
                tenant_id=tenant_id,
                produto_id=str(produto_id),
                nome=enriquecido.nome,
            )

            return produto_atualizado

    async def gerar_e_salvar_embedding(
        self, tenant_id: str, produto_id: UUID
    ) -> None:
        """Gera embedding OpenAI para o texto_rag do produto e persiste.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Raises:
            ValueError: se produto não encontrado ou sem texto_rag.
        """
        with tracer.start_as_current_span("catalog.gerar_e_salvar_embedding") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("produto_id", str(produto_id))

            produto = await self._repo.get_produto(tenant_id, produto_id)
            if produto is None:
                raise ValueError(
                    f"Produto não encontrado: tenant={tenant_id}, id={produto_id}"
                )

            if not produto.texto_rag:
                log.warning(
                    "embedding_sem_texto_rag",
                    tenant_id=tenant_id,
                    produto_id=str(produto_id),
                )
                return

            response = await self._embedding_client.embeddings.create(                model=self._embedding_model,
                input=produto.texto_rag,
            )
            embedding: list[float] = response.data[0].embedding

            await self._repo.update_embedding(tenant_id, produto_id, embedding)

            log.debug(
                "embedding_gerado",
                tenant_id=tenant_id,
                produto_id=str(produto_id),
                dimensoes=len(embedding),
            )

    # ─────────────────────────────────────────────
    # Busca semântica
    # ─────────────────────────────────────────────

    async def buscar_semantico(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[ResultadoBusca]:
        """Realiza busca semântica por similaridade de embedding.

        Args:
            tenant_id: identificador do tenant.
            query: texto de busca em linguagem natural.
            limit: número máximo de resultados.

        Returns:
            Lista de ResultadoBusca ordenada por score decrescente.
        """
        with tracer.start_as_current_span("catalog.buscar_semantico") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("query", query[:100])
            span.set_attribute("limit", limit)

            # Gera embedding da query
            response = await self._embedding_client.embeddings.create(                model=self._embedding_model,
                input=query,
            )
            query_embedding: list[float] = response.data[0].embedding

            # Busca no repo — tenant_id obrigatório para isolamento
            pares = await self._repo.buscar_por_embedding(
                tenant_id=tenant_id,
                embedding=query_embedding,
                limit=limit,
            )

            resultados = [ResultadoBusca(produto, distancia) for produto, distancia in pares]

            log.info(
                "busca_semantica_executada",
                tenant_id=tenant_id,
                query=query[:50],
                resultados=len(resultados),
            )

            return resultados

    # ─────────────────────────────────────────────
    # Preços diferenciados via Excel
    # ─────────────────────────────────────────────

    async def processar_excel_precos(
        self, tenant_id: str, file_bytes: bytes
    ) -> ExcelUploadResult:
        """Processa arquivo Excel de preços diferenciados.

        Colunas esperadas (case-insensitive):
            - codigo_produto / codigo / sku
            - cliente_cnpj / cnpj
            - preco_cliente / preco / valor
            - ean (opcional)

        Args:
            tenant_id: identificador do tenant.
            file_bytes: bytes do arquivo .xlsx.

        Returns:
            ExcelUploadResult com contadores e lista de erros.
        """
        with tracer.start_as_current_span("catalog.processar_excel_precos") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("file_size_bytes", len(file_bytes))

            try:
                df = pd.read_excel(io.BytesIO(file_bytes))
            except Exception as exc:
                log.error(
                    "excel_leitura_falhou",
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                raise ValueError(f"Arquivo Excel inválido: {exc}") from exc

            # Normaliza nomes de colunas
            df.columns = [str(c).lower().strip() for c in df.columns]

            col_codigo = self._find_col(df.columns.tolist(), ["codigo_produto", "codigo", "sku", "cod"])
            col_cnpj = self._find_col(df.columns.tolist(), ["cliente_cnpj", "cnpj", "cliente"])
            col_preco = self._find_col(df.columns.tolist(), ["preco_cliente", "preco", "valor", "price"])
            col_ean = self._find_col(df.columns.tolist(), ["ean", "codigo_barras", "barcode"])

            if not col_codigo or not col_cnpj or not col_preco:
                raise ValueError(
                    "Colunas obrigatórias não encontradas. Esperado: codigo_produto, cliente_cnpj, preco_cliente"
                )

            inseridos = 0
            atualizados = 0
            erros: list[str] = []

            for idx, row in df.iterrows():
                linha_num = int(idx) + 2  # +2 para numero da linha no Excel (1-indexed + header)
                try:
                    codigo = str(row[col_codigo]).strip()
                    cnpj_raw = str(row[col_cnpj]).strip()
                    preco_raw = row[col_preco]

                    if not codigo or codigo == "nan":
                        erros.append(f"Linha {linha_num}: código do produto vazio")
                        continue

                    if not cnpj_raw or cnpj_raw == "nan":
                        erros.append(f"Linha {linha_num}: CNPJ do cliente vazio")
                        continue

                    # Normaliza CNPJ para apenas dígitos
                    cnpj_digits = "".join(c for c in cnpj_raw if c.isdigit())
                    if len(cnpj_digits) not in (11, 14):
                        erros.append(
                            f"Linha {linha_num}: CNPJ inválido '{cnpj_raw}' "
                            f"(esperado 14 dígitos para CNPJ ou 11 para CPF)"
                        )
                        continue

                    try:
                        preco = Decimal(str(preco_raw).replace(",", ".").strip())
                        if preco <= 0:
                            raise InvalidOperation("preço deve ser positivo")
                    except (InvalidOperation, ValueError):
                        erros.append(
                            f"Linha {linha_num}: preço inválido '{preco_raw}'"
                        )
                        continue

                    ean: str | None = None
                    if col_ean and col_ean in df.columns:
                        ean_raw = str(row[col_ean]).strip()
                        if ean_raw and ean_raw != "nan":
                            ean = ean_raw

                    preco_obj = PrecoDiferenciado(
                        tenant_id=tenant_id,
                        codigo_produto=codigo,
                        cliente_cnpj=cnpj_digits,
                        preco_cliente=preco,
                        ean=ean,
                    )

                    await self._repo.upsert_preco_diferenciado(tenant_id, preco_obj)
                    inseridos += 1  # upsert — não distingue insert/update aqui

                except Exception as exc:
                    erros.append(f"Linha {linha_num}: erro inesperado — {exc}")

            result = ExcelUploadResult(
                linhas_processadas=len(df),
                inseridos=inseridos,
                atualizados=atualizados,
                erros=erros,
            )

            log.info(
                "excel_processado",
                tenant_id=tenant_id,
                linhas=len(df),
                inseridos=inseridos,
                erros=len(erros),
            )

            return result

    # ─────────────────────────────────────────────
    # Revisão de produtos (painel)
    # ─────────────────────────────────────────────

    async def aprovar_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> Produto:
        """Aprova um produto enriquecido — status → ATIVO.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            Produto com status ATIVO.
        """
        with tracer.start_as_current_span("catalog.aprovar_produto") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("produto_id", str(produto_id))

            result = await self._repo.update_status(
                tenant_id, produto_id, StatusEnriquecimento.ATIVO
            )
            log.info(
                "produto_aprovado",
                tenant_id=tenant_id,
                produto_id=str(produto_id),
            )
            return result

    async def rejeitar_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> Produto:
        """Rejeita um produto enriquecido — status → INATIVO.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            Produto com status INATIVO.
        """
        with tracer.start_as_current_span("catalog.rejeitar_produto") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("produto_id", str(produto_id))

            result = await self._repo.update_status(
                tenant_id, produto_id, StatusEnriquecimento.INATIVO
            )
            log.info(
                "produto_rejeitado",
                tenant_id=tenant_id,
                produto_id=str(produto_id),
            )
            return result

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
            status: filtra por status de enriquecimento.
            limit: máximo de resultados.
            offset: offset de paginação.

        Returns:
            Lista de produtos.
        """
        with tracer.start_as_current_span("catalog.listar_produtos") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("limit", limit)

            return await self._repo.listar_produtos(
                tenant_id=tenant_id,
                status=status,
                limit=limit,
                offset=offset,
            )

    async def get_produto(
        self, tenant_id: str, produto_id: UUID
    ) -> Produto | None:
        """Busca produto por ID.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            Produto encontrado ou None.
        """
        with tracer.start_as_current_span("catalog.get_produto") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("produto_id", str(produto_id))

            return await self._repo.get_produto(tenant_id, produto_id)

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def _find_col(columns: list[str], candidates: list[str]) -> str | None:
        """Encontra coluna do DataFrame por lista de nomes candidatos."""
        for col in columns:
            if col in candidates:
                return col
        return None


