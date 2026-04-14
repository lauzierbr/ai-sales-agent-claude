"""Job de crawl agendado — executado pelo APScheduler.

Camada Runtime: importa Types, Config, Repo e Service do domínio catalog.
"""

from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)
meter = get_meter(__name__)

_job_started = meter.create_counter(
    "crawler_job_started_total",
    description="Total de jobs de crawl iniciados pelo scheduler",
)
_job_completed = meter.create_counter(
    "crawler_job_completed_total",
    description="Total de jobs de crawl concluídos com sucesso",
)
_job_failed = meter.create_counter(
    "crawler_job_failed_total",
    description="Total de jobs de crawl que falharam",
)

_LOCK_TTL_SECONDS = 3600  # 1 hora


async def run_crawl_for_tenant(
    tenant_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Executa crawl completo para um tenant, com Redis lock para evitar overlap.

    Fluxo:
    1. Tenta obter Redis SETNX lock (chave crawl_lock:{tenant_id}, TTL 1h).
    2. Se lock já existe (crawl em andamento) — loga skip e retorna.
    3. Se obteve lock — executa crawl via CatalogService.
    4. Libera lock ao final (sucesso ou erro).

    Args:
        tenant_id: ID do tenant a crawlear.
        session_factory: factory de sessão para CatalogService.
    """
    lock_key = f"crawl_lock:{tenant_id}"

    with tracer.start_as_current_span("crawler_scheduled_run") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("triggered_by", "scheduler")

        # Tenta adquirir lock Redis
        acquired = await _acquire_lock(lock_key)
        if not acquired:
            log.info("crawler_job_lock_skip", tenant_id=tenant_id, lock_key=lock_key)
            return

        _job_started.add(1, {"tenant_id": tenant_id})
        log.info("crawler_job_iniciado", tenant_id=tenant_id)

        try:
            await _execute_crawl(tenant_id, session_factory)
            _job_completed.add(1, {"tenant_id": tenant_id})
            log.info("crawler_job_concluido", tenant_id=tenant_id)
        except Exception as exc:
            _job_failed.add(1, {"tenant_id": tenant_id})
            log.error("crawler_job_falhou", tenant_id=tenant_id, error=str(exc))
        finally:
            await _release_lock(lock_key)


async def _acquire_lock(lock_key: str) -> bool:
    """Tenta adquirir Redis SETNX lock.

    Returns:
        True se lock adquirido, False se já existia.
    """
    try:
        from src.providers.db import get_redis

        redis = get_redis()
        acquired = await redis.set(lock_key, "1", ex=_LOCK_TTL_SECONDS, nx=True)
        return bool(acquired)
    except Exception as exc:
        log.warning("redis_lock_erro", lock_key=lock_key, error=str(exc))
        # Se Redis indisponível, permite execução (sem lock)
        return True


async def _release_lock(lock_key: str) -> None:
    """Libera Redis lock.

    Falha silenciosa se Redis indisponível.
    """
    try:
        from src.providers.db import get_redis

        redis = get_redis()
        await redis.delete(lock_key)
    except Exception as exc:
        log.warning("redis_lock_release_erro", lock_key=lock_key, error=str(exc))


async def _execute_crawl(
    tenant_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Executa o crawl via CatalogService.

    Reutiliza o mesmo pipeline do endpoint POST /catalog/crawl.

    Args:
        tenant_id: ID do tenant.
        session_factory: factory de sessão.
    """
    from src.catalog.config import CrawlerConfig
    from src.catalog.repo import CatalogRepo
    from src.catalog.runtime.crawler.efos_http import EfosHttpCrawler
    from src.catalog.service import CatalogService

    config = CrawlerConfig.for_tenant(tenant_id)

    from openai import AsyncOpenAI

    import os
    openai_key = os.getenv("OPENAI_API_KEY", "")
    embedding_client = AsyncOpenAI(api_key=openai_key) if openai_key else None

    from src.catalog.runtime.enricher import EnricherAgent

    enricher = EnricherAgent()
    repo = CatalogRepo(session_factory)
    service = CatalogService(repo=repo, enricher=enricher, embedding_client=embedding_client)

    async with EfosHttpCrawler(config) as crawler:
        categorias = await crawler.get_categorias()
        for categoria in categorias:
            try:
                produtos = await crawler.get_produtos(categoria)
                for produto_bruto in produtos:
                    try:
                        produto = await service.salvar_produto_bruto(tenant_id, produto_bruto)
                        await service.enriquecer_produto(tenant_id, produto.id)
                    except Exception as exc:
                        log.warning(
                            "crawler_produto_erro",
                            tenant_id=tenant_id,
                            codigo=produto_bruto.codigo_externo,
                            error=str(exc),
                        )
            except Exception as exc:
                log.warning(
                    "crawler_categoria_erro",
                    tenant_id=tenant_id,
                    categoria=categoria.nome,
                    error=str(exc),
                )
