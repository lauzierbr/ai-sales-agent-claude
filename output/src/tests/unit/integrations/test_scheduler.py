"""Testes unitários — E14 (F-07): APScheduler EFOS + Redis lock (Sprint 10).

Verifica:
- create_efos_scheduler retorna instância configurada.
- run_now retorna False se lock Redis ativo (409).
- _run_sync_job captura exceção sem derrubar app.
- replace_existing=True evita ConflictingIdError.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
async def test_create_efos_scheduler():
    """create_efos_scheduler retorna AsyncIOScheduler configurado."""
    from src.integrations.runtime.scheduler import create_efos_scheduler
    scheduler = create_efos_scheduler()
    assert scheduler is not None
    assert hasattr(scheduler, "add_job")


@pytest.mark.unit
async def test_run_now_bloqueado_por_lock(mocker):
    """run_now retorna False quando lock Redis já está ativo."""
    from src.integrations.runtime.scheduler import run_now

    mock_redis = mocker.AsyncMock()
    mock_redis.get = AsyncMock(return_value="1")  # lock ativo

    mock_scheduler = MagicMock()

    result = await run_now(
        scheduler=mock_scheduler,
        tenant_id="jmb",
        connector_kind="efos_backup",
        session_factory=MagicMock(),
        redis_client=mock_redis,
    )

    assert result is False
    # add_job não deve ter sido chamado
    mock_scheduler.add_job.assert_not_called()


@pytest.mark.unit
async def test_run_now_dispara_sem_lock(mocker):
    """run_now retorna True e adiciona job quando sem lock."""
    from src.integrations.runtime.scheduler import run_now

    mock_redis = mocker.AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # sem lock

    mock_scheduler = MagicMock()
    mock_scheduler.add_job = MagicMock()

    result = await run_now(
        scheduler=mock_scheduler,
        tenant_id="jmb",
        connector_kind="efos_backup",
        session_factory=MagicMock(),
        redis_client=mock_redis,
    )

    assert result is True
    mock_scheduler.add_job.assert_called_once()


@pytest.mark.unit
async def test_sync_job_captura_excecao(mocker):
    """_run_sync_job não propaga exceção — protege o scheduler."""
    from src.integrations.runtime.scheduler import _run_sync_job

    mock_redis = mocker.AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()

    # Simular que run_sync levanta exceção (importado dinamicamente dentro do job)
    mocker.patch(
        "src.integrations.jobs.sync_efos.run_sync",
        side_effect=RuntimeError("sync falhou"),
    )

    mock_factory = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session_ctx)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    # Não deve levantar exceção
    await _run_sync_job(
        tenant_id="jmb",
        connector_kind="efos_backup",
        session_factory=mock_factory,
        redis_client=mock_redis,
    )
    # Se chegou aqui sem exceção, o teste passou


@pytest.mark.unit
def test_register_job_usa_replace_existing(mocker):
    """_register_job usa replace_existing=True para evitar ConflictingIdError."""
    from src.integrations.runtime.scheduler import _register_job

    mock_scheduler = MagicMock()
    mock_scheduler.add_job = MagicMock()

    _register_job(
        scheduler=mock_scheduler,
        tenant_id="jmb",
        connector_kind="efos_backup",
        cron_expression="0 13 * * *",
        session_factory=MagicMock(),
        redis_client=None,
    )

    mock_scheduler.add_job.assert_called_once()
    call_kwargs = mock_scheduler.add_job.call_args.kwargs
    assert call_kwargs.get("replace_existing") is True
