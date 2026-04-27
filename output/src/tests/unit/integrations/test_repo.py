"""Testes unitários de integrations/repo.py — SyncRunRepo e SyncArtifactRepo.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest


def _make_sync_run(tenant_id: str = "jmb"):
    from src.integrations.types import ConnectorCapability, SyncRun, SyncStatus

    return SyncRun(
        id=uuid4(),
        tenant_id=tenant_id,
        connector_kind="efos_backup",
        capabilities=[ConnectorCapability.CATALOG],
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        status=SyncStatus.RUNNING,
        rows_published=0,
        error=None,
    )


def _make_sync_artifact(tenant_id: str = "jmb"):
    from src.integrations.types import SyncArtifact

    return SyncArtifact(
        id=uuid4(),
        tenant_id=tenant_id,
        connector_kind="efos_backup",
        artifact_path="/tmp/backup.dump",
        artifact_checksum="abc123def456",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
async def test_sync_run_repo_create_persiste_tenant_id() -> None:
    """A7: SyncRunRepo.create inclui tenant_id no INSERT."""
    from src.integrations.repo import SyncRunRepo

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()

    run = _make_sync_run(tenant_id="jmb")
    repo = SyncRunRepo()
    result = await repo.create(run, mock_session)

    assert result.tenant_id == "jmb"
    mock_session.execute.assert_called_once()
    call_kwargs = mock_session.execute.call_args
    # Verifica que tenant_id está nos parâmetros
    params = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1]
    assert "tenant_id" in params
    assert params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_sync_run_repo_update_status() -> None:
    """A7: SyncRunRepo.update_status atualiza status e rows_published."""
    from src.integrations.repo import SyncRunRepo
    from src.integrations.types import SyncStatus

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()

    run_id = uuid4()
    repo = SyncRunRepo()
    await repo.update_status(
        run_id=run_id,
        status=SyncStatus.SUCCESS,
        rows_published=150,
        error=None,
        session=mock_session,
    )

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    params = call_args[0][1]
    assert params["status"] == "success"
    assert params["rows_published"] == 150
    assert params["error"] is None


@pytest.mark.unit
async def test_sync_artifact_repo_find_by_checksum_encontrado() -> None:
    """A7: SyncArtifactRepo.find_by_checksum filtra por tenant_id e checksum."""
    from src.integrations.repo import SyncArtifactRepo

    artifact_id = uuid4()
    now = datetime.now(timezone.utc)
    row_data = {
        "id": str(artifact_id),
        "tenant_id": "jmb",
        "connector_kind": "efos_backup",
        "artifact_path": "/tmp/backup.dump",
        "artifact_checksum": "abc123",
        "created_at": now,
    }
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: row_data[key]

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = SyncArtifactRepo()
    artifact = await repo.find_by_checksum("jmb", "abc123", mock_session)

    assert artifact is not None
    assert artifact.tenant_id == "jmb"
    assert artifact.artifact_checksum == "abc123"

    # Verifica que tenant_id está nos params da query
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_sync_artifact_repo_find_by_checksum_nao_encontrado() -> None:
    """A7: SyncArtifactRepo.find_by_checksum retorna None se não encontrado."""
    from src.integrations.repo import SyncArtifactRepo

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = SyncArtifactRepo()
    artifact = await repo.find_by_checksum("jmb", "checksum_inexistente", mock_session)

    assert artifact is None


@pytest.mark.unit
async def test_sync_artifact_repo_create_persiste_tenant_id() -> None:
    """A7: SyncArtifactRepo.create inclui tenant_id no INSERT."""
    from src.integrations.repo import SyncArtifactRepo

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()

    artifact = _make_sync_artifact(tenant_id="jmb")
    repo = SyncArtifactRepo()
    result = await repo.create(artifact, mock_session)

    assert result.tenant_id == "jmb"
    mock_session.execute.assert_called_once()
    call_params = mock_session.execute.call_args[0][1]
    assert call_params["tenant_id"] == "jmb"
