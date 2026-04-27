"""Repositório do domínio Integrations — acesso ao PostgreSQL.

Camada Repo: importa apenas src.integrations.types e stdlib.
Toda função filtra por tenant_id para isolamento de tenant.
Não importa agents/, catalog/, orders/, tenants/, dashboard/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.types import ConnectorCapability, SyncArtifact, SyncRun, SyncStatus

log = structlog.get_logger(__name__)


class SyncRunRepo:
    """Repositório de execuções de sync — persiste e atualiza SyncRun."""

    async def create(self, run: SyncRun, session: AsyncSession) -> SyncRun:
        """Persiste nova execução de sync.

        Args:
            run: dados da execução a persistir.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            SyncRun persistido (com id gerado pelo banco se None).
        """
        capabilities_arr = [c.value for c in run.capabilities]
        await session.execute(
            text("""
                INSERT INTO sync_runs
                    (id, tenant_id, connector_kind, capabilities,
                     started_at, finished_at, status, rows_published, error)
                VALUES
                    (:id, :tenant_id, :connector_kind, :capabilities,
                     :started_at, :finished_at, :status, :rows_published, :error)
            """),
            {
                "id": str(run.id),
                "tenant_id": run.tenant_id,
                "connector_kind": run.connector_kind,
                "capabilities": capabilities_arr,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "status": run.status.value,
                "rows_published": run.rows_published,
                "error": run.error,
            },
        )
        await session.commit()
        log.info("sync_run_criado", tenant_id=run.tenant_id, run_id=str(run.id))
        return run

    async def update_status(
        self,
        run_id: UUID,
        status: SyncStatus,
        rows_published: int,
        error: str | None,
        session: AsyncSession,
    ) -> None:
        """Atualiza status de uma execução de sync.

        Args:
            run_id: ID da execução.
            status: novo status.
            rows_published: total de rows inseridas.
            error: mensagem de erro (ou None em sucesso).
            session: sessão SQLAlchemy assíncrona.
        """
        await session.execute(
            text("""
                UPDATE sync_runs
                SET status = :status,
                    rows_published = :rows_published,
                    error = :error,
                    finished_at = :finished_at
                WHERE id = :run_id
            """),
            {
                "run_id": str(run_id),
                "status": status.value,
                "rows_published": rows_published,
                "error": error,
                "finished_at": datetime.now(timezone.utc),
            },
        )
        await session.commit()
        log.info("sync_run_atualizado", run_id=str(run_id), status=status.value)


class SyncArtifactRepo:
    """Repositório de artefatos de sync — persiste e consulta SyncArtifact."""

    async def find_by_checksum(
        self,
        tenant_id: str,
        checksum: str,
        session: AsyncSession,
    ) -> SyncArtifact | None:
        """Busca artefato pelo checksum SHA-256.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            checksum: hash SHA-256 do arquivo de backup.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            SyncArtifact se já foi importado, None caso contrário.
        """
        result = await session.execute(
            text("""
                SELECT id, tenant_id, connector_kind, artifact_path,
                       artifact_checksum, created_at
                FROM sync_artifacts
                WHERE tenant_id = :tenant_id AND artifact_checksum = :checksum
                LIMIT 1
            """),
            {"tenant_id": tenant_id, "checksum": checksum},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return SyncArtifact(
            id=UUID(str(row["id"])),
            tenant_id=row["tenant_id"],
            connector_kind=row["connector_kind"],
            artifact_path=row["artifact_path"],
            artifact_checksum=row["artifact_checksum"],
            created_at=row["created_at"],
        )

    async def create(self, artifact: SyncArtifact, session: AsyncSession) -> SyncArtifact:
        """Persiste novo artefato de sync.

        Args:
            artifact: dados do artefato.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            SyncArtifact persistido.
        """
        await session.execute(
            text("""
                INSERT INTO sync_artifacts
                    (id, tenant_id, connector_kind, artifact_path, artifact_checksum, created_at)
                VALUES
                    (:id, :tenant_id, :connector_kind, :artifact_path, :artifact_checksum, :created_at)
                ON CONFLICT (tenant_id, artifact_checksum) DO NOTHING
            """),
            {
                "id": str(artifact.id),
                "tenant_id": artifact.tenant_id,
                "connector_kind": artifact.connector_kind,
                "artifact_path": artifact.artifact_path,
                "artifact_checksum": artifact.artifact_checksum,
                "created_at": artifact.created_at,
            },
        )
        await session.commit()
        log.info(
            "sync_artifact_criado",
            tenant_id=artifact.tenant_id,
            checksum=artifact.artifact_checksum[:12],
        )
        return artifact
