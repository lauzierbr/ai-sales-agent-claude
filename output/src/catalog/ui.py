"""UI do domínio Catalog — FastAPI router com JSON API e painel Jinja2.

Camada UI: importa src.catalog.types e src.catalog.service.
NÃO importa repo ou runtime diretamente — injeção via Depends.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.catalog.repo import CatalogRepo
from src.catalog.service import CatalogService
from src.catalog.types import (
    CrawlStatus,
    ExcelUploadResult,
    Produto,
    ResultadoBusca,
    StatusEnriquecimento,
)
from src.providers.auth import require_role
from src.providers.db import get_session

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


# ─────────────────────────────────────────────
# Factory — pode importar Runtime (UI é a última camada)
# ─────────────────────────────────────────────


def create_catalog_service(repo: CatalogRepo) -> CatalogService:
    """Cria CatalogService com dependências reais para uso em produção.

    A UI é a única camada que pode importar Runtime.
    Service recebe EnricherAgent via EnricherProtocol (duck typing).
    """
    import os

    from openai import AsyncOpenAI

    from src.catalog.runtime.enricher import EnricherAgent

    enricher = EnricherAgent()

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise ValueError("Variável Infisical não configurada: OPENAI_API_KEY")

    embedding_client = AsyncOpenAI(api_key=openai_key)

    return CatalogService(
        repo=repo,
        enricher=enricher,
        embedding_client=embedding_client,
    )

# Templates Jinja2 — caminho relativo ao diretório do módulo
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


# ─────────────────────────────────────────────
# Dependency injection
# ─────────────────────────────────────────────


async def get_catalog_service() -> CatalogService:
    """FastAPI dependency: cria CatalogService com dependências reais.

    Em produção usa o session factory do providers.db.
    Em testes unitários é sobrescrita via app.dependency_overrides.
    """
    from src.providers.db import get_session_factory

    repo = CatalogRepo(get_session_factory())
    return create_catalog_service(repo)


def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extrai e valida o tenant_id do header X-Tenant-ID.

    Raises:
        HTTPException 422: se header não presente (FastAPI valida automaticamente).
    """
    if not x_tenant_id.strip():
        raise HTTPException(status_code=422, detail="Header X-Tenant-ID não pode ser vazio")
    return x_tenant_id.strip().lower()


# ─────────────────────────────────────────────
# JSON API — Crawler
# ─────────────────────────────────────────────


@router.post("/crawl", response_class=JSONResponse)
async def trigger_crawl(
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
    _user: dict[str, Any] = Depends(require_role(["gestor"])),
) -> JSONResponse:
    """Dispara crawl completo do catálogo para o tenant informado.

    O crawl é síncrono e retorna o status ao final.
    Scheduler automático pertence ao Sprint 1 (D018).

    Returns:
        CrawlStatus com contadores de produtos crawleados.
    """
    from src.catalog.config import CrawlerConfig
    from src.catalog.runtime.crawler.efos_http import EfosHttpCrawler

    log.info("crawl_iniciado", tenant_id=tenant_id)
    iniciado_em = datetime.now(timezone.utc)

    try:
        config = CrawlerConfig.for_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    novos = 0
    atualizados = 0
    erros = 0
    total_categorias = 0
    total_produtos = 0

    try:
        async with EfosHttpCrawler(config) as crawler:
            categorias = await crawler.get_categorias()
            total_categorias = len(categorias)

            for categoria in categorias:
                try:
                    produtos = await crawler.get_produtos(categoria)
                    total_produtos += len(produtos)
                    for produto_bruto in produtos:
                        try:
                            await service.salvar_produto_bruto(tenant_id, produto_bruto)
                            novos += 1
                        except Exception as exc:
                            erros += 1
                            log.warning(
                                "crawl_produto_erro",
                                tenant_id=tenant_id,
                                codigo=produto_bruto.codigo_externo,
                                error=str(exc),
                            )
                except Exception as exc:
                    erros += 1
                    log.warning(
                        "crawl_categoria_erro",
                        tenant_id=tenant_id,
                        categoria=categoria.nome,
                        error=str(exc),
                    )
    except Exception as exc:
        log.error("crawl_falhou", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Crawl falhou: {exc}") from exc

    status = CrawlStatus(
        tenant_id=tenant_id,
        total_categorias=total_categorias,
        total_produtos=total_produtos,
        novos=novos,
        atualizados=atualizados,
        erros=erros,
        iniciado_em=iniciado_em,
        finalizado_em=datetime.now(timezone.utc),
    )

    log.info(
        "crawl_concluido",
        tenant_id=tenant_id,
        total_produtos=total_produtos,
        erros=erros,
    )

    return JSONResponse(content=status.to_dict())


# ─────────────────────────────────────────────
# JSON API — Enriquecimento em lote
# ─────────────────────────────────────────────


@router.post("/enriquecer-lote", response_class=JSONResponse)
async def enriquecer_lote(
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
    concorrencia: int = Query(5, ge=1, le=20, description="Chamadas simultâneas ao Haiku"),
) -> JSONResponse:
    """Enriquece todos os produtos PENDENTE do tenant via Claude Haiku + embedding OpenAI.

    Busca todos os produtos com status PENDENTE e roda o pipeline de enriquecimento
    em paralelo (controlado por semáforo). Idempotente: produtos já enriquecidos
    são ignorados.

    Returns:
        JSON com total, enriquecidos e erros.
    """
    log.info("enriquecer_lote_iniciado", tenant_id=tenant_id)

    pendentes = await service.listar_produtos(
        tenant_id=tenant_id,
        status=StatusEnriquecimento.PENDENTE,
        limit=2000,
    )

    if not pendentes:
        return JSONResponse(content={"total": 0, "enriquecidos": 0, "erros": 0})

    semaforo = asyncio.Semaphore(concorrencia)
    enriquecidos = 0
    erros = 0

    async def _enriquecer_um(produto: Produto) -> None:
        nonlocal enriquecidos, erros
        async with semaforo:
            try:
                await service.enriquecer_produto(tenant_id, produto.id)
                enriquecidos += 1
                log.debug(
                    "produto_enriquecido",
                    tenant_id=tenant_id,
                    codigo=produto.codigo_externo,
                )
            except Exception as exc:
                erros += 1
                log.warning(
                    "enriquecimento_falhou",
                    tenant_id=tenant_id,
                    codigo=produto.codigo_externo,
                    error=str(exc),
                )

    await asyncio.gather(*[_enriquecer_um(p) for p in pendentes])

    log.info(
        "enriquecer_lote_concluido",
        tenant_id=tenant_id,
        total=len(pendentes),
        enriquecidos=enriquecidos,
        erros=erros,
    )

    return JSONResponse(content={
        "total": len(pendentes),
        "enriquecidos": enriquecidos,
        "erros": erros,
    })


# ─────────────────────────────────────────────
# JSON API — Produtos
# ─────────────────────────────────────────────


@router.get("/produtos", response_class=JSONResponse)
async def listar_produtos(
    tenant_id: str = Depends(_get_tenant_id),
    status: StatusEnriquecimento | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Lista produtos do tenant com filtro opcional de status e paginação.

    Args:
        status: filtra por status de enriquecimento.
        limit: máximo de resultados (1-200).
        offset: offset de paginação.

    Returns:
        Lista de produtos serializada como JSON.
    """
    produtos = await service.listar_produtos(
        tenant_id=tenant_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=[p.to_dict() for p in produtos])


@router.get("/produtos/{produto_id}", response_class=JSONResponse)
async def get_produto(
    produto_id: UUID,
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Retorna detalhes de um produto por ID.

    Raises:
        HTTPException 404: se produto não encontrado para este tenant.
    """
    produto = await service.get_produto(tenant_id, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return JSONResponse(content=produto.to_dict())


@router.post("/produtos/{produto_id}/aprovar", response_class=JSONResponse)
async def aprovar_produto(
    produto_id: UUID,
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Aprova um produto — status → ATIVO.

    Raises:
        HTTPException 404: se produto não encontrado.
    """
    try:
        produto = await service.aprovar_produto(tenant_id, produto_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=produto.to_dict())


@router.post("/produtos/{produto_id}/rejeitar", response_class=JSONResponse)
async def rejeitar_produto(
    produto_id: UUID,
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Rejeita um produto — status → INATIVO.

    Raises:
        HTTPException 404: se produto não encontrado.
    """
    try:
        produto = await service.rejeitar_produto(tenant_id, produto_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=produto.to_dict())


# ─────────────────────────────────────────────
# JSON API — Busca semântica
# ─────────────────────────────────────────────


@router.post("/busca", response_class=JSONResponse)
async def busca_semantica(
    request: Request,
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Busca semântica por produtos usando embedding.

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
# JSON API — Preços diferenciados
# ─────────────────────────────────────────────


@router.post("/precos/upload", response_class=JSONResponse)
async def upload_precos(
    file: UploadFile = File(...),
    tenant_id: str = Depends(_get_tenant_id),
    service: CatalogService = Depends(get_catalog_service),
) -> JSONResponse:
    """Faz upload de planilha Excel de preços diferenciados.

    Colunas esperadas: codigo_produto, cliente_cnpj, preco_cliente, ean (opcional).
    CNPJ aceita com ou sem pontuação: '12.345.678/0001-90' ou '12345678000190'.

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


# ─────────────────────────────────────────────
# HTML — Painel de revisão de produtos
# ─────────────────────────────────────────────


@router.get("/painel", response_class=HTMLResponse)
async def painel_revisao(
    request: Request,
    tenant_id: str = Query("jmb", description="Tenant ID para visualizar"),
    limit: int = Query(100, ge=1, le=500, description="Máximo de produtos por página"),
    status: str = Query("todos", description="Filtro de status: todos, enriquecido, pendente, ativo, inativo"),
    service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Renderiza painel de revisão de produtos para o tenant.

    Tenant ID via query param para uso direto no browser (sem header).
    status=todos mostra todos os produtos independente do status de enriquecimento.
    """
    status_filtro: StatusEnriquecimento | None = None
    if status != "todos":
        try:
            status_filtro = StatusEnriquecimento(status)
        except ValueError:
            pass

    produtos = await service.listar_produtos(
        tenant_id=tenant_id,
        status=status_filtro,
        limit=limit,
    )

    return templates.TemplateResponse(
        request=request,
        name="produtos.html",
        context={
            "produtos": [p.to_dict() for p in produtos],
            "tenant_id": tenant_id,
            "total": len(produtos),
            "status_filtro": status,
        },
    )


@router.post("/painel/{produto_id}/aprovar")
async def painel_aprovar(
    produto_id: UUID,
    tenant_id: str = Query("jmb"),
    service: CatalogService = Depends(get_catalog_service),
) -> RedirectResponse:
    """Aprova produto via submit HTML e redireciona para o painel."""
    try:
        await service.aprovar_produto(tenant_id, produto_id)
    except ValueError:
        pass  # produto não encontrado — redireciona de volta mesmo assim
    return RedirectResponse(url=f"/catalog/painel?tenant_id={tenant_id}", status_code=303)


@router.post("/painel/{produto_id}/rejeitar")
async def painel_rejeitar(
    produto_id: UUID,
    tenant_id: str = Query("jmb"),
    service: CatalogService = Depends(get_catalog_service),
) -> RedirectResponse:
    """Rejeita produto via submit HTML e redireciona para o painel."""
    try:
        await service.rejeitar_produto(tenant_id, produto_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/catalog/painel?tenant_id={tenant_id}", status_code=303)


# ─────────────────────────────────────────────
# JSON API — Scheduler de crawl
# ─────────────────────────────────────────────


@router.get("/schedule", response_class=JSONResponse)
async def get_schedule(
    request: Request,
    _user: dict[str, Any] = Depends(require_role(["gestor"])),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Retorna configuração de schedule de crawl do tenant.

    Requer JWT de gestor. Tenant extraído de request.state (TenantProvider).

    Returns:
        Schedule atual ou default se não configurado.
    """
    from sqlalchemy import text

    tenant_id: str = getattr(request.state, "tenant_id", "")

    result = await session.execute(
        text(
            "SELECT tenant_id, cron_expression, enabled, last_run_at, next_run_at "
            "FROM crawl_schedule WHERE tenant_id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    )
    row = result.mappings().first()

    if row is None:
        return JSONResponse(
            {
                "tenant_id": tenant_id,
                "cron_expression": "0 2 1 * *",
                "enabled": True,
                "last_run_at": None,
                "next_run_at": None,
            }
        )

    return JSONResponse(
        {
            "tenant_id": row["tenant_id"],
            "cron_expression": row["cron_expression"],
            "enabled": row["enabled"],
            "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
            "next_run_at": row["next_run_at"].isoformat() if row["next_run_at"] else None,
        }
    )


@router.put("/schedule", response_class=JSONResponse)
async def update_schedule(
    request: Request,
    _user: dict[str, Any] = Depends(require_role(["gestor"])),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Atualiza configuração de schedule de crawl do tenant.

    Requer JWT de gestor. Valida expressão cron antes de salvar.

    Body: {"cron_expression": "0 2 1 * *", "enabled": true}

    Returns:
        Schedule atualizado.

    Raises:
        HTTPException 422: se cron_expression inválida.
    """
    from sqlalchemy import text

    from src.providers.scheduler import validate_cron

    body = await request.json()
    cron_expression: str = body.get("cron_expression", "0 2 1 * *")
    enabled: bool = bool(body.get("enabled", True))
    tenant_id: str = getattr(request.state, "tenant_id", "")

    if not validate_cron(cron_expression):
        raise HTTPException(status_code=422, detail="Expressão cron inválida")

    await session.execute(
        text("""
            INSERT INTO crawl_schedule (id, tenant_id, cron_expression, enabled, created_at)
            VALUES (gen_random_uuid()::text, :tenant_id, :cron_expression, :enabled, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET
                cron_expression = EXCLUDED.cron_expression,
                enabled         = EXCLUDED.enabled
        """),
        {"tenant_id": tenant_id, "cron_expression": cron_expression, "enabled": enabled},
    )
    await session.commit()

    log.info(
        "crawl_schedule_atualizado",
        tenant_id=tenant_id,
        cron_expression=cron_expression,
        enabled=enabled,
    )

    return JSONResponse(
        {"tenant_id": tenant_id, "cron_expression": cron_expression, "enabled": enabled}
    )
