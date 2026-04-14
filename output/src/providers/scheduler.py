"""Provider do scheduler de crawl — APScheduler AsyncIOScheduler.

Cross-cutting provider.
Decisão D019: APScheduler 3.x embedded (sem broker).
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_CRON = "0 2 1 * *"  # 02h00 do dia 1 de cada mês


def create_scheduler() -> AsyncIOScheduler:
    """Cria instância do AsyncIOScheduler.

    Returns:
        Scheduler pronto para receber jobs (não iniciado).
    """
    return AsyncIOScheduler(timezone="America/Sao_Paulo")


async def start_scheduler_from_db(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Lê schedules ativos do DB e inicia o scheduler.

    Se ENVIRONMENT == "test", não inicia (evita side effects em testes).

    Args:
        scheduler: instância do AsyncIOScheduler.
        session_factory: session factory para leitura do DB.
    """
    if os.getenv("ENVIRONMENT", "development") == "test":
        log.info("scheduler_skipped_test_env")
        return

    schedules = await _load_schedules(session_factory)

    for schedule in schedules:
        _add_job(scheduler, schedule["tenant_id"], schedule["cron_expression"])
        log.info(
            "scheduler_job_registrado",
            tenant_id=schedule["tenant_id"],
            cron=schedule["cron_expression"],
        )

    scheduler.start()
    log.info("scheduler_iniciado", total_jobs=len(schedules))


async def _load_schedules(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[dict[str, Any]]:
    """Carrega schedules ativos do banco de dados.

    Returns:
        Lista de dicts com tenant_id e cron_expression.
    """
    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT tenant_id, cron_expression FROM crawl_schedule "
                    "WHERE enabled = true"
                )
            )
            return [
                {"tenant_id": r["tenant_id"], "cron_expression": r["cron_expression"]}
                for r in result.mappings().all()
            ]
    except Exception as exc:
        log.warning("scheduler_load_erro", error=str(exc))
        return []


def _add_job(
    scheduler: AsyncIOScheduler, tenant_id: str, cron_expression: str
) -> None:
    """Adiciona job de crawl ao scheduler para um tenant.

    Args:
        scheduler: instância do AsyncIOScheduler.
        tenant_id: ID do tenant.
        cron_expression: expressão cron (5 campos).
    """
    from apscheduler.triggers.cron import CronTrigger

    from src.catalog.runtime.scheduler_job import run_crawl_for_tenant
    from src.providers.db import get_session_factory

    trigger = CronTrigger.from_crontab(cron_expression)
    scheduler.add_job(
        run_crawl_for_tenant,
        trigger=trigger,
        args=[tenant_id, get_session_factory()],
        id=f"crawl_{tenant_id}",
        replace_existing=True,
    )


def validate_cron(cron_expression: str) -> bool:
    """Valida sintaxe de expressão cron.

    Args:
        cron_expression: expressão cron com 5 campos.

    Returns:
        True se válida, False caso contrário.
    """
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(cron_expression)
        return True
    except (ValueError, KeyError):
        return False
