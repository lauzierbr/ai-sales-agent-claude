"""CLI de sincronização EFOS via backup diário SSH/SFTP.

Uso:
    python -m integrations.jobs.sync_efos --tenant jmb
    python -m integrations.jobs.sync_efos --tenant jmb --dry-run
    python -m integrations.jobs.sync_efos --tenant jmb --force

Flags:
    --tenant   ID do tenant (obrigatório).
    --dry-run  Não modifica banco; apenas loga o que faria.
    --force    Ignora verificação de checksum (re-importa mesmo arquivo).

Garantias:
    - Staging DB destruído em bloco finally (mesmo em caso de erro).
    - Artifacts com mais de 7 dias são removidos.
    - Idempotente: skip se checksum já importado (a menos que --force).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)

_ARTIFACT_RETENTION_DAYS = 7
_STAGING_DB_NAME = "efos_staging"


async def run_sync(
    tenant_id: str,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Executa o pipeline de sync EFOS para um tenant.

    Args:
        tenant_id: ID do tenant (ex: "jmb").
        dry_run: se True, não modifica banco.
        force: se True, re-importa mesmo se checksum já importado.

    Returns:
        Exit code: 0 (OK) ou 1 (erro).
    """
    from src.integrations.config import EFOSBackupConfig
    from src.integrations.connectors.efos_backup.acquire import acquire
    from src.integrations.connectors.efos_backup.normalize import (
        normalize_accounts_b2b,
        normalize_inventory,
        normalize_orders,
        normalize_products,
        normalize_sales_history,
        normalize_vendedores,
    )
    from src.integrations.connectors.efos_backup.publish import publish
    from src.integrations.connectors.efos_backup.stage import stage
    from src.integrations.repo import SyncArtifactRepo, SyncRunRepo
    from src.integrations.types import ConnectorCapability, SyncArtifact, SyncRun, SyncStatus
    from src.providers.db import get_session_factory

    try:
        cfg = EFOSBackupConfig.for_tenant(tenant_id)
    except ValueError as exc:
        log.error("sync_efos_config_erro", tenant_id=tenant_id, error=str(exc))
        return 1

    factory = get_session_factory()
    artifact_path: Path | None = None

    run = SyncRun(
        id=uuid4(),
        tenant_id=tenant_id,
        connector_kind="efos_backup",
        capabilities=[
            ConnectorCapability.CATALOG,
            ConnectorCapability.CUSTOMERS_B2B,
            ConnectorCapability.ORDERS_B2B,
            ConnectorCapability.INVENTORY,
            ConnectorCapability.SALES_HISTORY,
        ],
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        status=SyncStatus.RUNNING,
        rows_published=0,
        error=None,
    )

    try:
        # 1. Acquire — baixa dump via SSH
        log.info("sync_efos_acquire_iniciando", tenant_id=tenant_id, dry_run=dry_run)
        artifact_path, checksum = await acquire(cfg)

        if dry_run:
            log.info(
                "sync_efos_dry_run_skip",
                tenant_id=tenant_id,
                checksum=checksum[:12],
                artifact=str(artifact_path),
            )
            return 0

        # 2. Verifica idempotência (skip se já importado)
        async with factory() as session:
            artifact_repo = SyncArtifactRepo()
            existente = await artifact_repo.find_by_checksum(
                tenant_id=tenant_id,
                checksum=checksum,
                session=session,
            )
            if existente is not None and not force:
                log.info(
                    "sync_efos_checksum_ja_importado",
                    tenant_id=tenant_id,
                    checksum=checksum[:12],
                )
                return 0

            # 3. Persiste SyncRun
            run_repo = SyncRunRepo()
            run = await run_repo.create(run, session)

        # 4. Stage — restaura dump em banco temporário
        log.info("sync_efos_stage_iniciando", tenant_id=tenant_id)
        await stage(artifact_path, cfg.staging_db_url)

        # 5. Lê dados do banco de staging
        rows_dict = await _ler_staging(cfg.staging_db_url)

        # 6. Normaliza
        log.info("sync_efos_normalizando", tenant_id=tenant_id)
        products = normalize_products(
            rows_dict["tb_itens"], tenant_id=tenant_id, checksum=checksum
        )
        accounts = normalize_accounts_b2b(
            rows_dict["tb_clientes"], tenant_id=tenant_id, checksum=checksum
        )
        orders, order_items = normalize_orders(
            rows_dict["tb_pedido"],
            rows_dict["tb_itenspedido"],
            rows_dict["tb_vendedor"],
            tenant_id=tenant_id,
            checksum=checksum,
        )
        inv = normalize_inventory(
            rows_dict["tb_estoque"], tenant_id=tenant_id, checksum=checksum
        )
        sales = normalize_sales_history(
            rows_dict.get("tb_vendas", []), tenant_id=tenant_id, checksum=checksum
        )
        vendedores = normalize_vendedores(
            rows_dict["tb_vendedor"], tenant_id=tenant_id, checksum=checksum
        )

        # 7. Publica — transação única
        async with factory() as session:
            total_rows = await publish(
                tenant_id=tenant_id,
                products=products,
                accounts=accounts,
                orders=orders,
                order_items=order_items,
                inventory=inv,
                sales_history=sales,
                vendedores=vendedores,
                session=session,
            )

        # 8. Registra artifact + atualiza SyncRun
        async with factory() as session:
            artifact = SyncArtifact(
                id=uuid4(),
                tenant_id=tenant_id,
                connector_kind="efos_backup",
                artifact_path=str(artifact_path),
                artifact_checksum=checksum,
                created_at=datetime.now(timezone.utc),
            )
            await artifact_repo.create(artifact, session)
            await run_repo.update_status(
                run_id=run.id,
                status=SyncStatus.SUCCESS,
                rows_published=total_rows,
                error=None,
                session=session,
            )

        log.info(
            "sync_efos_concluido",
            tenant_id=tenant_id,
            total_rows=total_rows,
            run_id=str(run.id),
        )
        return 0

    except Exception as exc:
        log.error("sync_efos_erro", tenant_id=tenant_id, error=str(exc))
        # Atualiza SyncRun com status de erro
        try:
            async with factory() as session:
                run_repo = SyncRunRepo()
                await run_repo.update_status(
                    run_id=run.id,
                    status=SyncStatus.ERROR,
                    rows_published=0,
                    error=str(exc),
                    session=session,
                )
        except Exception as inner_exc:
            log.warning("sync_efos_update_run_erro", error=str(inner_exc))
        return 1

    finally:
        # Staging DB destruído em bloco finally (mesmo em caso de erro)
        _destruir_staging_db(cfg.staging_db_url)
        # Remove artifacts com mais de 7 dias
        _limpar_artifacts_antigos(cfg.artifact_dir)


def _destruir_staging_db(staging_db_url: str) -> None:
    """Destrói banco de staging após o sync (sucesso ou erro).

    Executado em bloco finally — nunca levanta exceção.
    """
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(staging_db_url)
        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        user = parsed.username or "postgres"
        password = parsed.password or ""

        import os
        env = {**os.environ}
        if password:
            env["PGPASSWORD"] = password

        cmd = [
            "psql",
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            "--dbname=postgres",
            "-c", f"DROP DATABASE IF EXISTS {_STAGING_DB_NAME}",
        ]
        subprocess.run(cmd, env=env, capture_output=True, check=False, timeout=30)
        log.info("sync_efos_staging_destruido")
    except Exception as exc:
        log.warning("sync_efos_staging_destruir_erro", error=str(exc))


def _limpar_artifacts_antigos(artifact_dir: str) -> None:
    """Remove arquivos de backup com mais de 7 dias.

    Executado em bloco finally — nunca levanta exceção.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_ARTIFACT_RETENTION_DAYS)
        dir_path = Path(artifact_dir)
        if not dir_path.exists():
            return
        removidos = 0
        for f in dir_path.glob("*.backup"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                removidos += 1
        if removidos:
            log.info("sync_efos_artifacts_removidos", count=removidos, dias=_ARTIFACT_RETENTION_DAYS)
    except Exception as exc:
        log.warning("sync_efos_limpar_artifacts_erro", error=str(exc))


async def _ler_staging(staging_db_url: str) -> dict[str, list[dict]]:
    """Lê todas as tabelas do banco de staging via asyncpg.

    Args:
        staging_db_url: URL do banco de staging.

    Returns:
        Dict table_name → list[dict] com todas as rows.
    """
    import asyncpg  # type: ignore[import-untyped]

    conn = await asyncpg.connect(staging_db_url)
    try:
        result: dict[str, list[dict]] = {}
        tabelas = [
            "tb_itens", "tb_clientes", "tb_pedido",
            "tb_itenspedido", "tb_vendedor", "tb_estoque",
        ]
        # tb_vendas é opcional (pode não existir em todos os dumps)
        for tabela in tabelas:
            rows = await conn.fetch(f"SELECT * FROM {tabela}")  # noqa: S608
            result[tabela] = [dict(r) for r in rows]
        try:
            rows = await conn.fetch("SELECT * FROM tb_vendas")  # noqa: S608
            result["tb_vendas"] = [dict(r) for r in rows]
        except Exception:
            result["tb_vendas"] = []
        return result
    finally:
        await conn.close()


def main() -> None:
    """Entry point da CLI."""
    parser = argparse.ArgumentParser(
        description="Sincroniza dados EFOS via backup diário SSH/SFTP."
    )
    parser.add_argument("--tenant", required=True, help="ID do tenant (ex: jmb)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Não modifica banco; apenas loga o que faria.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-importa mesmo se checksum já importado.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(
        run_sync(
            tenant_id=args.tenant,
            dry_run=args.dry_run,
            force=args.force,
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
