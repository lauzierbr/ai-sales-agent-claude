"""Testes do SyncRunRepo (último sync EFOS bem-sucedido).

Sprint 9 (E2) introduziu o partial /dashboard/sync-status com bloco visual
"Última sincronização EFOS". Em v0.9.4 esse bloco foi REMOVIDO — a info
migrou para o card "Atualizado no sync EFOS" dentro dos KPIs.

Os testes aqui mantêm a cobertura do método `SyncRunRepo.get_last_sync_run`
(que continua sendo usado por _get_kpis para o timestamp). Os testes do
partial/endpoint removidos foram apagados junto com o código.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.unit
def test_sync_run_repo_get_last_sync_run_filtra_tenant() -> None:
    """SyncRunRepo.get_last_sync_run deve filtrar por tenant_id."""
    import inspect
    from src.integrations.repo import SyncRunRepo

    source = inspect.getsource(SyncRunRepo.get_last_sync_run)
    assert "tenant_id" in source, (
        "get_last_sync_run deve filtrar por tenant_id. "
        "Toda query em integrations/repo.py deve incluir tenant_id."
    )
    assert "WHERE" in source or "where" in source.lower(), (
        "get_last_sync_run deve ter cláusula WHERE com tenant_id."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_run_repo_retorna_none_sem_registros() -> None:
    """SyncRunRepo.get_last_sync_run retorna None quando sem registros."""
    from src.integrations.repo import SyncRunRepo

    repo = SyncRunRepo()
    mock_session = AsyncMock()

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await repo.get_last_sync_run(tenant_id="jmb", session=mock_session)
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_run_repo_retorna_dict_com_campos() -> None:
    """SyncRunRepo.get_last_sync_run retorna dict com campos obrigatórios."""
    from src.integrations.repo import SyncRunRepo

    repo = SyncRunRepo()
    mock_session = AsyncMock()

    finished_at = datetime(2026, 4, 27, 10, 30, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {
        "status": "success",
        "finished_at": finished_at,
        "rows_published": 4280,
        "error": None,
        "started_at": datetime(2026, 4, 27, 10, 0, 0, tzinfo=timezone.utc),
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await repo.get_last_sync_run(tenant_id="jmb", session=mock_session)

    assert result is not None
    assert result["status"] == "success"
    assert result["rows_published"] == 4280
    assert result["finished_at"] == finished_at


@pytest.mark.unit
def test_kpis_consome_sync_runs_para_timestamp() -> None:
    """v0.9.4: _get_kpis passa a usar sync_runs success como 'atualizado em'."""
    import inspect
    from src.dashboard.ui import _get_kpis
    source = inspect.getsource(_get_kpis)
    assert "sync_runs" in source, (
        "_get_kpis deve consultar sync_runs para timestamp 'atualizado em'"
    )
    assert "status = 'success'" in source, (
        "_get_kpis deve filtrar apenas syncs bem-sucedidos"
    )
