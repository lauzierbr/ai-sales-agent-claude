"""UI do domínio Catalog — FastAPI router (simplificado, E19 Sprint 10).

Catalog legado removido em Sprint 10:
- Crawler (efos.py, efos_http.py, base.py) removido.
- Enricher removido.
- Painel de revisão removido.
- Rotas /crawl, /enriquecer-lote, /painel, /produtos/{id}/aprovar|rejeitar removidas.
- Scheduler de crawl removido (substituído por APScheduler EFOS em integrations/).

Rotas mantidas:
  - POST /catalog/busca — busca semântica (via commerce_products, E18).
  - POST /catalog/precos/upload — upload de preços diferenciados.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.catalog.repo import CatalogRepo
from src.catalog.service import CatalogService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


# ─────────────────────────────────────────────
# Factory — pode importar Runtime (UI é a última camada)
# ─────────────────────────────────────────────


def create_catalog_service(repo: CatalogRepo) -> CatalogService:
    """Cria CatalogService com dependências reais.

    Sem EnricherAgent (removido em E19). Apenas embedding para busca.
    """
    from openai import AsyncOpenAI

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise ValueError("Variável Infisical não configurada: OPENAI_API_KEY")

    embedding_client = AsyncOpenAI(api_key=openai_key)

    return CatalogService(
        repo=repo,
        enricher=None,
        embedding_client=embedding_client,
    )


async def get_catalog_service() -> CatalogService:
    """FastAPI dependency: cria CatalogService com dependências reais."""
    from src.providers.db import get_session_factory

    repo = CatalogRepo(get_session_factory())
    return create_catalog_service(repo)


def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extrai e valida o tenant_id do header X-Tenant-ID."""
    if not x_tenant_id.strip():
        raise HTTPException(status_code=422, detail="Header X-Tenant-ID não pode ser vazio")
    return x_tenant_id.strip().lower()


# ─────────────────────────────────────────────
# Busca semântica (E18: usa commerce_products)
# ─────────────────────────────────────────────


@router.post("/busca", response_class=JSONResponse)
async def busca_semantica(
    request: Request,
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Busca semântica por produtos usando embedding (commerce_products).

    Body JSON esperado:
        {"query": "shampoo hidratante", "limit": 10}

    Returns:
        Lista de ResultadoBusca com produto e score de similaridade.
    """
    body = await request.json()
    query: str = body.get("query", "")
    limit: int = int(body.get("limit", 10))

    if not query.strip():
        raise HTTPException(status_code=422, detail="Campo 'query' é obrigatório")

    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="'limit' deve estar entre 1 e 50")

    resultados = await service.buscar_semantico(
        tenant_id=tenant_id,
        query=query,
        limit=limit,
    )

    return JSONResponse(content=[r.to_dict() for r in resultados])


# ─────────────────────────────────────────────
# Preços diferenciados
# ─────────────────────────────────────────────


@router.post("/precos/upload", response_class=JSONResponse)
async def upload_precos(
    file: UploadFile = File(...),
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Faz upload de planilha Excel de preços diferenciados.

    Colunas esperadas: codigo_produto, cliente_cnpj, preco_cliente, ean (opcional).

    Returns:
        ExcelUploadResult com contadores e lista de erros por linha.
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=422,
            detail="Arquivo deve ser .xlsx ou .xls",
        )

    conteudo = await file.read()
    if len(conteudo) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=422, detail="Arquivo muito grande (máximo 10MB)")

    try:
        resultado = await service.processar_excel_precos(tenant_id, conteudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return JSONResponse(content=resultado.to_dict())
