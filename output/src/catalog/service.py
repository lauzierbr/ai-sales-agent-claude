"""Serviço do domínio Catalog — lógica de negócio.

Camada Service: importa apenas src.catalog.types, src.catalog.config e src.catalog.repo.
NÃO importa nada de src.catalog.runtime — injeção via EnricherProtocol.
Toda função pública tem OTel span e structlog.

E18/E19 (Sprint 10): métodos do pipeline de enriquecimento removidos (código morto
após remoção do enricher em E19). Fonte de dados: commerce_products exclusivamente.
"""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import pandas as pd
import structlog
from opentelemetry import trace

from src.catalog.repo import CatalogRepo
from src.catalog.types import (
    CommerceProduct,
    ExcelUploadResult,
    PrecoDiferenciado,
    ResultadoBusca,
    StatusEnriquecimento,
)
# commerce importado localmente para evitar dependência circular em runtime
# (import-linter: catalog/service pode importar commerce — ambos são camada Service/Repo)

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class CatalogService:
    """Serviço de catálogo de produtos.

    Orquestra: busca semântica, busca por código e preços diferenciados.
    Fonte de dados: commerce_products (E18 — produtos legado removido em E20).
    O cliente OpenAI é injetado para permitir mock nos testes unitários.
    """

    def __init__(
        self,
        repo: CatalogRepo,
        enricher: Any,  # aceita None — enricher removido em E19; mantido por compat de callers
        embedding_client: Any,  # AsyncOpenAI — tipado como Any para evitar import externo
        commerce_repo: Any | None = None,  # CommerceRepo — opcional, injetado em runtime
    ) -> None:
        """Inicializa o serviço com dependências injetadas.

        Args:
            repo: repositório de catálogo.
            enricher: obsoleto (removido em E19) — ignorado; aceito por compat de callers.
            embedding_client: cliente OpenAI assíncrono para geração de embeddings.
            commerce_repo: CommerceRepo para busca em commerce_products (E1a, opcional).
        """
        self._repo = repo
        self._embedding_client: Any = embedding_client
        self._embedding_model = "text-embedding-3-small"
        self._commerce_repo: Any | None = commerce_repo

    async def get_por_codigo(
        self, tenant_id: str, codigo_externo: str
    ) -> ResultadoBusca | None:
        """Busca produto por código externo (lookup exato).

        B-13: quando codigo_externo.isdigit() e len > 6 (ex: EAN de 13 dígitos),
        tenta primeiro o código completo; se não encontrar, tenta os últimos 6 dígitos
        (sufixo [-6:]) — padrão comum no EFOS onde o codigo_externo é o sufixo do EAN.

        Args:
            tenant_id: identificador do tenant.
            codigo_externo: código do produto no ERP (pode ser EAN completo de 13 dígitos).

        Returns:
            ResultadoBusca com distancia=0.0 ou None se não encontrado.
        """
        produto = await self._repo.get_produto_por_codigo(tenant_id, codigo_externo)
        if produto is None and codigo_externo.isdigit() and len(codigo_externo) > 6:
            # B-13: tenta sufixo dos últimos 6 dígitos (padrão EFOS)
            sufixo = codigo_externo[-6:]
            produto = await self._repo.get_produto_por_codigo(tenant_id, sufixo)
        if produto is None:
            return None
        return ResultadoBusca(produto, distancia=0.0)

    async def _usar_commerce_products(
        self, tenant_id: str, session: Any | None
    ) -> bool:
        """Retorna True se commerce_products tem >= 1 produto para o tenant.

        Decisão de fallback E1a: se True, busca por código/nome usa commerce_products;
        caso contrário, usa catalog.produtos (legado).

        Args:
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy assíncrona (necessária para a query).

        Returns:
            True se commerce_products tem dados para o tenant.
        """
        if self._commerce_repo is None or session is None:
            return False
        try:
            count = await self._commerce_repo.count_produtos(
                tenant_id=tenant_id,
                session=session,
            )
            return count >= 1
        except Exception as exc:
            log.warning(
                "catalog_service_commerce_count_erro",
                tenant_id=tenant_id,
                error=str(exc),
            )
            return False

    async def buscar_por_nome_commerce(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        session: Any | None = None,
    ) -> list[ResultadoBusca]:
        """Busca produtos em commerce_products por código ou nome.

        E1a: fonte primária quando commerce_products tem dados para o tenant.
        Retorna list[ResultadoBusca] normalizado com distancia=0.0 (busca exata/parcial).

        Args:
            tenant_id: identificador do tenant.
            query: texto de busca — código ou nome.
            limit: número máximo de resultados.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de ResultadoBusca com produtos de commerce_products.
        """
        if self._commerce_repo is None:
            return []
        rows = await self._commerce_repo.buscar_produtos_commerce(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
            session=session,
        )
        resultados = []
        import uuid as _uuid
        from decimal import Decimal as _Decimal
        from datetime import datetime as _dt, timezone as _tz

        for row in rows:
            # Gera UUID determinístico a partir do external_id (namespace DNS)
            produto_uuid = _uuid.uuid5(_uuid.NAMESPACE_DNS, f"{tenant_id}:{row['external_id']}")
            produto = CommerceProduct(
                id=produto_uuid,
                tenant_id=tenant_id,
                codigo_externo=row.get("codigo") or row["external_id"],
                nome_bruto=row["nome"],
                nome=row["nome"],
                preco_padrao=_Decimal(str(row["preco_padrao"])) if row.get("preco_padrao") else None,
                status_enriquecimento=StatusEnriquecimento.ATIVO,
                criado_em=_dt.now(_tz.utc),
                atualizado_em=_dt.now(_tz.utc),
            )
            resultados.append(ResultadoBusca(produto, distancia=0.0))
        return resultados

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
    # Listagem de produtos (compat com catalog/ui)
    # ─────────────────────────────────────────────

    async def listar_produtos(
        self,
        tenant_id: str,
        status: StatusEnriquecimento | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommerceProduct]:
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
    ) -> CommerceProduct | None:
        """Busca produto por ID.

        Args:
            tenant_id: identificador do tenant.
            produto_id: UUID do produto.

        Returns:
            CommerceProduct encontrado ou None.
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


