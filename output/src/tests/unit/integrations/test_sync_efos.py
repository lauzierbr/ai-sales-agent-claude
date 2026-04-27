"""Testes unitários de integrations/jobs/sync_efos.py.

Todos os testes são @pytest.mark.unit — sem I/O externo.
Staging DB e acquire são mockados.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
async def test_staging_db_destruido_em_erro() -> None:
    """A15: staging DB é destruído em bloco finally mesmo quando stage() lança exceção."""
    from src.integrations.jobs.sync_efos import run_sync

    with (
        patch("src.integrations.config.EFOSBackupConfig.for_tenant") as mock_for_tenant,
        patch("src.integrations.connectors.efos_backup.acquire.acquire") as mock_acquire,
        patch("src.integrations.connectors.efos_backup.stage.stage") as mock_stage,
        patch("src.integrations.jobs.sync_efos._destruir_staging_db") as mock_destruir,
        patch("src.integrations.jobs.sync_efos._limpar_artifacts_antigos"),
        patch("src.providers.db.get_session_factory") as mock_factory,
    ):
        mock_cfg = MagicMock()
        mock_cfg.staging_db_url = "postgresql://localhost/test"
        mock_cfg.artifact_dir = "/tmp/artifacts"
        mock_for_tenant.return_value = mock_cfg

        mock_acquire.return_value = (MagicMock(), "abc123checksum")

        # stage() lança exceção
        mock_stage.side_effect = RuntimeError("Erro simulado no stage")

        # Session factory
        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value = MagicMock(return_value=mock_ctx)

        # SyncArtifactRepo — não encontra artifact existente
        with (
            patch("src.integrations.repo.SyncArtifactRepo.find_by_checksum", new_callable=AsyncMock, return_value=None),
            patch("src.integrations.repo.SyncRunRepo.create", new_callable=AsyncMock, return_value=MagicMock(id=MagicMock())),
            patch("src.integrations.repo.SyncRunRepo.update_status", new_callable=AsyncMock),
        ):
            exit_code = await run_sync("jmb")

        # stage() falhou → deve retornar exit code 1
        assert exit_code == 1
        # _destruir_staging_db DEVE ter sido chamado (bloco finally)
        mock_destruir.assert_called_once()


@pytest.mark.unit
async def test_dry_run_nao_modifica_banco() -> None:
    """A13: run_sync --dry-run não persiste SyncRun nem publica dados."""
    from src.integrations.jobs.sync_efos import run_sync

    with (
        patch("src.integrations.config.EFOSBackupConfig.for_tenant") as mock_for_tenant,
        patch("src.integrations.connectors.efos_backup.acquire.acquire") as mock_acquire,
        patch("src.integrations.jobs.sync_efos._destruir_staging_db"),
        patch("src.integrations.jobs.sync_efos._limpar_artifacts_antigos"),
    ):
        mock_cfg = MagicMock()
        mock_cfg.staging_db_url = "postgresql://localhost/test"
        mock_cfg.artifact_dir = "/tmp/artifacts"
        mock_for_tenant.return_value = mock_cfg

        mock_acquire.return_value = (MagicMock(), "abc123checksum")

        with patch("src.providers.db.get_session_factory") as mock_factory:
            mock_factory.return_value = MagicMock()

            exit_code = await run_sync("jmb", dry_run=True)

        assert exit_code == 0
        # get_session_factory não deve ter sido chamada (sem writes em dry_run)
        mock_factory.return_value.assert_not_called()


@pytest.mark.unit
def test_destruir_staging_db_nao_lanca_excecao_em_erro() -> None:
    """_destruir_staging_db não lança exceção mesmo quando psql falha."""
    from src.integrations.jobs.sync_efos import _destruir_staging_db

    with patch("src.integrations.jobs.sync_efos.subprocess.run") as mock_run:
        mock_run.side_effect = Exception("psql não encontrado")
        # Não deve lançar exceção
        _destruir_staging_db("postgresql://localhost/efos_staging")
