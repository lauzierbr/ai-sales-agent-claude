"""Testes unitários de catalog/runtime/scheduler_job.py e providers/scheduler.py.

NOTE (Sprint 10 E19): scheduler_job.py removido — todos os testes marcados como skip.

Todos os testes são @pytest.mark.unit — sem I/O externo.
Critério A13: scheduler não inicia quando ENVIRONMENT=test.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
pytestmark = pytest.mark.skip(reason="E19 Sprint 10: catalog/runtime/scheduler_job.py removido")

import pytest


# ─────────────────────────────────────────────
# A13 — scheduler não inicia em ENVIRONMENT=test
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_scheduler_nao_inicia_em_test_env() -> None:
    """A13: start_scheduler_from_db não chama scheduler.start() quando ENVIRONMENT=test."""
    from src.providers.scheduler import start_scheduler_from_db

    scheduler = MagicMock()
    scheduler.running = False
    factory = AsyncMock()

    with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
        await start_scheduler_from_db(scheduler, factory)

    # scheduler.start() nunca deve ser chamado em ambiente de teste
    scheduler.start.assert_not_called()


@pytest.mark.unit
async def test_scheduler_inicia_fora_de_test_env() -> None:
    """start_scheduler_from_db chama scheduler.start() quando ENVIRONMENT != test."""
    from src.providers.scheduler import start_scheduler_from_db

    scheduler = MagicMock()
    factory = AsyncMock()

    # Simula DB sem schedules (retorna lista vazia)
    with (
        patch.dict("os.environ", {"ENVIRONMENT": "development"}),
        patch("src.providers.scheduler._load_schedules", new=AsyncMock(return_value=[])),
    ):
        await start_scheduler_from_db(scheduler, factory)

    scheduler.start.assert_called_once()


@pytest.mark.unit
def test_validate_cron_expressao_valida() -> None:
    """validate_cron retorna True para expressão cron válida."""
    from src.providers.scheduler import validate_cron

    assert validate_cron("0 2 1 * *") is True   # 02h do dia 1 de cada mês
    assert validate_cron("*/30 * * * *") is True  # a cada 30 min
    assert validate_cron("0 0 * * 1") is True     # toda segunda-feira


@pytest.mark.unit
def test_validate_cron_expressao_invalida() -> None:
    """validate_cron retorna False para expressão cron inválida."""
    from src.providers.scheduler import validate_cron

    assert validate_cron("nao e cron") is False
    assert validate_cron("99 99 99 99 99") is False
    assert validate_cron("") is False


@pytest.mark.unit
def test_create_scheduler_retorna_instancia() -> None:
    """create_scheduler retorna AsyncIOScheduler configurado."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from src.providers.scheduler import create_scheduler

    scheduler = create_scheduler()
    assert isinstance(scheduler, AsyncIOScheduler)
    assert not scheduler.running


# ─────────────────────────────────────────────
# run_crawl_for_tenant — lock Redis
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_crawl_pula_se_lock_ja_adquirido() -> None:
    """run_crawl_for_tenant não executa crawl se lock Redis já existe."""
    from src.catalog.runtime.scheduler_job import run_crawl_for_tenant

    factory = AsyncMock()
    execute_calls = []

    async def mock_acquire(lock_key: str) -> bool:
        return False  # lock já existe

    async def mock_execute(tenant_id: str, sf: Any) -> None:
        execute_calls.append(tenant_id)

    with (
        patch("src.catalog.runtime.scheduler_job._acquire_lock", new=mock_acquire),
        patch("src.catalog.runtime.scheduler_job._execute_crawl", new=mock_execute),
        patch("src.catalog.runtime.scheduler_job._release_lock", new=AsyncMock()),
    ):
        await run_crawl_for_tenant("jmb", factory)

    assert execute_calls == []


@pytest.mark.unit
async def test_crawl_executa_se_lock_disponivel() -> None:
    """run_crawl_for_tenant executa crawl quando adquire lock com sucesso."""
    from src.catalog.runtime.scheduler_job import run_crawl_for_tenant

    factory = AsyncMock()
    execute_calls = []

    async def mock_acquire(lock_key: str) -> bool:
        return True  # lock adquirido

    async def mock_execute(tenant_id: str, sf: Any) -> None:
        execute_calls.append(tenant_id)

    with (
        patch("src.catalog.runtime.scheduler_job._acquire_lock", new=mock_acquire),
        patch("src.catalog.runtime.scheduler_job._execute_crawl", new=mock_execute),
        patch("src.catalog.runtime.scheduler_job._release_lock", new=AsyncMock()),
    ):
        await run_crawl_for_tenant("jmb", factory)

    assert execute_calls == ["jmb"]


@pytest.mark.unit
async def test_crawl_libera_lock_mesmo_com_erro() -> None:
    """run_crawl_for_tenant libera lock (finally) mesmo se crawl falhar."""
    from src.catalog.runtime.scheduler_job import run_crawl_for_tenant

    factory = AsyncMock()
    locks_liberados = []

    async def mock_acquire(lock_key: str) -> bool:
        return True

    async def mock_execute(tenant_id: str, sf: Any) -> None:
        raise RuntimeError("falha simulada do crawler")

    async def mock_release(lock_key: str) -> None:
        locks_liberados.append(lock_key)

    with (
        patch("src.catalog.runtime.scheduler_job._acquire_lock", new=mock_acquire),
        patch("src.catalog.runtime.scheduler_job._execute_crawl", new=mock_execute),
        patch("src.catalog.runtime.scheduler_job._release_lock", new=mock_release),
    ):
        await run_crawl_for_tenant("jmb", factory)  # não deve propagar exceção

    assert "crawl_lock:jmb" in locks_liberados


@pytest.mark.unit
async def test_acquire_lock_retorna_true_se_redis_indisponivel() -> None:
    """_acquire_lock retorna True (permite execução) se Redis indisponível."""
    from src.catalog.runtime.scheduler_job import _acquire_lock

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch("src.providers.db.get_redis", return_value=mock_redis):
        result = await _acquire_lock("crawl_lock:jmb")

    assert result is True  # fail-open: sem Redis, permite execução
