"""APScheduler para sync EFOS — E14, F-07, Sprint 10.

Camada Runtime: gerencia o ciclo de vida do APScheduler para o sync EFOS.
Substituí o launchd externo por scheduling interno ao processo FastAPI.

Responsabilidades:
- Registrar jobs no startup a partir de sync_schedule.enabled=true.
- Expor reschedule_job() para a UI de admin atualizar sem restart.
- Redis lock sync:efos:{tenant}:running (TTL 30min) impede sobreposição.
- 2º "Rodar agora" dentro de 30min retorna 409.
- Exceção dentro do job não derruba o app (try/except interno).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

log = structlog.get_logger(__name__)

_LOCK_TTL_SECONDS = 30 * 60  # 30 minutos


def create_efos_scheduler() -> AsyncIOScheduler:
    """Cria instância do AsyncIOScheduler para sync EFOS.

    Returns:
        AsyncIOScheduler configurado com timezone São Paulo.
    """
    return AsyncIOScheduler(timezone="America/Sao_Paulo")


async def start_efos_scheduler(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any | None = None,
) -> None:
    """Inicializa o APScheduler com jobs do banco de dados.

    Lê sync_schedule.enabled=true e registra 1 job por (tenant, connector).
    Se ENVIRONMENT=test, não inicia.

    Args:
        scheduler: instância do AsyncIOScheduler.
        session_factory: factory de sessões SQLAlchemy.
        redis_client: cliente Redis para lock (opcional).
    """
    if os.getenv("ENVIRONMENT", "development") == "test":
        log.info("efos_scheduler_skipped_test_env")
        return

    from src.integrations.repo import SyncScheduleRepo

    async with session_factory() as session:
        schedules = await SyncScheduleRepo().listar_enabled(session)

    for s in schedules:
        _register_job(
            scheduler=scheduler,
            tenant_id=s["tenant_id"],
            connector_kind=s["connector_kind"],
            cron_expression=s["cron_expression"] or "0 13 * * *",
            session_factory=session_factory,
            redis_client=redis_client,
        )

    if not scheduler.running:
        scheduler.start()
        log.info("efos_scheduler_iniciado", total_jobs=len(schedules))


def _register_job(
    scheduler: AsyncIOScheduler,
    tenant_id: str,
    connector_kind: str,
    cron_expression: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any | None = None,
) -> None:
    """Registra (ou substitui) um job no scheduler.

    Args:
        scheduler: instância do AsyncIOScheduler.
        tenant_id: ID do tenant.
        connector_kind: tipo do connector (ex: 'efos_backup').
        cron_expression: expressão cron de 5 campos.
        session_factory: factory de sessões.
        redis_client: cliente Redis para lock (opcional).
    """
    job_id = f"sync_{connector_kind}_{tenant_id}"
    trigger = CronTrigger.from_crontab(cron_expression, timezone="America/Sao_Paulo")
    scheduler.add_job(
        _run_sync_job,
        trigger=trigger,
        args=[tenant_id, connector_kind, session_factory, redis_client],
        id=job_id,
        replace_existing=True,  # APScheduler gotcha: sem isso levanta ConflictingIdError
        misfire_grace_time=3600,  # 1h grace period para execuções atrasadas
    )
    log.info(
        "efos_scheduler_job_registrado",
        tenant_id=tenant_id,
        connector_kind=connector_kind,
        job_id=job_id,
        cron=cron_expression,
    )


def reschedule_job(
    scheduler: AsyncIOScheduler,
    tenant_id: str,
    connector_kind: str,
    new_cron: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any | None = None,
) -> None:
    """Re-agenda um job existente com novo cron — sem restart da app.

    Args:
        scheduler: instância do AsyncIOScheduler.
        tenant_id: ID do tenant.
        connector_kind: tipo do connector.
        new_cron: nova expressão cron.
        session_factory: factory de sessões.
        redis_client: cliente Redis para lock (opcional).
    """
    _register_job(
        scheduler=scheduler,
        tenant_id=tenant_id,
        connector_kind=connector_kind,
        cron_expression=new_cron,
        session_factory=session_factory,
        redis_client=redis_client,
    )
    log.info(
        "efos_scheduler_job_reagendado",
        tenant_id=tenant_id,
        connector_kind=connector_kind,
        new_cron=new_cron,
    )


async def run_now(
    scheduler: AsyncIOScheduler,
    tenant_id: str,
    connector_kind: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any | None = None,
) -> bool:
    """Dispara sync imediato respeitando lock Redis (E14).

    Args:
        scheduler: instância do AsyncIOScheduler (não utilizado diretamente).
        tenant_id: ID do tenant.
        connector_kind: tipo do connector.
        session_factory: factory de sessões.
        redis_client: cliente Redis para lock (obrigatório para lock).

    Returns:
        True se disparou, False se lock ativo (sync já em andamento).
    """
    lock_key = f"sync:{connector_kind}:{tenant_id}:running"

    if redis_client is not None:
        try:
            locked = await redis_client.get(lock_key)  # type: ignore[attr-defined]
            if locked:
                log.info(
                    "efos_scheduler_lock_ativo",
                    tenant_id=tenant_id,
                    connector_kind=connector_kind,
                )
                return False
        except Exception as exc:
            log.warning("efos_scheduler_redis_check_erro", error=str(exc))

    # Disparar como job one-shot
    job_id_now = f"sync_{connector_kind}_{tenant_id}_now"
    scheduler.add_job(
        _run_sync_job,
        args=[tenant_id, connector_kind, session_factory, redis_client],
        id=job_id_now,
        replace_existing=True,
        max_instances=1,
    )
    log.info(
        "efos_scheduler_run_now",
        tenant_id=tenant_id,
        connector_kind=connector_kind,
    )
    return True


async def _run_sync_job(
    tenant_id: str,
    connector_kind: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any | None = None,
) -> None:
    """Executa o sync EFOS com lock Redis e try/except interno (E14).

    Não propaga exceção — falha apenas loga como erro (evita derrubar o scheduler).

    Args:
        tenant_id: ID do tenant.
        connector_kind: tipo do connector.
        session_factory: factory de sessões SQLAlchemy.
        redis_client: cliente Redis para lock (opcional).
    """
    lock_key = f"sync:{connector_kind}:{tenant_id}:running"

    # Adquirir lock
    if redis_client is not None:
        try:
            acquired = await redis_client.set(  # type: ignore[attr-defined]
                lock_key, "1", ex=_LOCK_TTL_SECONDS, nx=True
            )
            if not acquired:
                log.info(
                    "efos_sync_lock_nao_adquirido",
                    tenant_id=tenant_id,
                    connector_kind=connector_kind,
                )
                return
        except Exception as exc:
            log.warning("efos_sync_redis_lock_erro", error=str(exc))

    try:
        log.info("efos_sync_iniciado", tenant_id=tenant_id, connector_kind=connector_kind)
        from src.integrations.jobs.sync_efos import run_sync
        await run_sync(tenant_id=tenant_id, session_factory=session_factory)

        # Atualizar last_triggered_at no banco
        async with session_factory() as session:
            from src.integrations.repo import SyncScheduleRepo
            await SyncScheduleRepo().update_last_triggered(
                tenant_id=tenant_id,
                connector_kind=connector_kind,
                session=session,
            )
            await session.commit()

        log.info("efos_sync_concluido", tenant_id=tenant_id, connector_kind=connector_kind)
    except Exception as exc:
        # try/except interno: não derruba o scheduler
        log.error(
            "efos_sync_erro",
            tenant_id=tenant_id,
            connector_kind=connector_kind,
            error=str(exc),
        )
    finally:
        # Liberar lock
        if redis_client is not None:
            try:
                await redis_client.delete(lock_key)  # type: ignore[attr-defined]
            except Exception as exc_unlock:
                log.warning("efos_sync_redis_unlock_erro", error=str(exc_unlock))
