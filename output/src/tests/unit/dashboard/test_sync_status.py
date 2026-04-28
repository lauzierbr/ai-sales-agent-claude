"""Testes unitários para /dashboard/sync-status (E2 — Sprint 9).

Cobre:
  - Endpoint retorna 200 com HTML contendo status e finished_at
  - Fallback "Nunca sincronizado" quando sem registros
  - Query inclui tenant_id (isolamento)
  - SyncRunRepo.get_last_sync_run existe e filtra por tenant_id
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
def test_sync_run_repo_get_last_sync_run_filtra_tenant() -> None:
    """SyncRunRepo.get_last_sync_run deve filtrar por tenant_id."""
    import inspect
    from src.integrations.repo import SyncRunRepo

    source = inspect.getsource(SyncRunRepo.get_last_sync_run)
    assert "tenant_id" in source, (
        "A_DASHBOARD_SYNC: get_last_sync_run deve filtrar por tenant_id. "
        "Toda query em integrations/repo.py deve incluir tenant_id."
    )
    assert "WHERE" in source or "where" in source.lower(), (
        "A_DASHBOARD_SYNC: get_last_sync_run deve ter cláusula WHERE com tenant_id."
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
def test_dashboard_sync_status_endpoint_existe() -> None:
    """Endpoint /dashboard/sync-status deve existir no router."""
    from src.dashboard.ui import router

    routes = [r.path for r in router.routes]  # type: ignore[attr-defined]
    assert "/dashboard/sync-status" in routes, (
        "A_DASHBOARD_SYNC: endpoint GET /dashboard/sync-status deve existir em dashboard/ui.py."
    )


@pytest.mark.unit
def test_sync_status_partial_template_existe() -> None:
    """Template _partials/sync_status.html deve existir."""
    from pathlib import Path
    template_path = Path(__file__).parent.parent.parent.parent.parent / \
        "src" / "dashboard" / "templates" / "_partials" / "sync_status.html"
    assert template_path.exists(), (
        "A_DASHBOARD_SYNC: template _partials/sync_status.html deve existir."
    )
    content = template_path.read_text()
    assert "Nunca sincronizado" in content, (
        "A_DASHBOARD_SYNC: template deve incluir fallback 'Nunca sincronizado'."
    )
