"""Módulo de staging: restaura dump EFOS em banco temporário.

Usa pg_restore --format=c para restaurar dump no formato custom do PostgreSQL.
Valida presença das 6 tabelas mínimas após restore.

Adaptação para ambiente Docker: psql e pg_restore são executados via
`docker exec <container>` quando EFOS_DOCKER_CONTAINER está definido,
caso contrário usa os binários do host.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_REQUIRED_TABLES = {
    "tb_itens",
    "tb_clientes",
    "tb_pedido",
    "tb_itenspedido",
    "tb_estoque",
    "tb_vendas",
}

_STAGING_DB_NAME = "efos_staging"

# Nome do container Docker onde psql/pg_restore estão disponíveis.
# Se vazio, usa binários do host diretamente.
_DOCKER_CONTAINER = os.getenv("EFOS_DOCKER_CONTAINER", "ai-sales-postgres")


def _cmd(binary: str) -> list[str]:
    """Retorna prefixo de comando: docker exec se container configurado."""
    if _DOCKER_CONTAINER:
        return ["docker", "exec", _DOCKER_CONTAINER, binary]
    return [binary]


class StagingValidationError(Exception):
    """Levantada quando tabelas obrigatórias estão ausentes após o restore."""
    pass


async def stage(artifact_path: Path, staging_db_url: str) -> None:
    """Restaura dump EFOS em banco de staging e valida estrutura.

    Fluxo:
    1. Extrai DSN do staging_db_url para obter host, port, user, password.
    2. DROP DATABASE efos_staging (se existir) + CREATE DATABASE efos_staging.
    3. Copia o arquivo .backup para dentro do container (se modo Docker).
    4. pg_restore --format=c --no-owner --no-privileges -d efos_staging.
    5. Valida presença das 6 tabelas mínimas.

    Args:
        artifact_path: caminho do dump no formato custom do pg_dump.
        staging_db_url: URL PostgreSQL para o banco de staging.

    Raises:
        StagingValidationError: se alguma tabela obrigatória estiver ausente.
        subprocess.CalledProcessError: se pg_restore falhar.
    """
    import urllib.parse
    parsed = urllib.parse.urlparse(staging_db_url)
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    user = parsed.username or "postgres"
    password = parsed.password or ""
    db_name = _STAGING_DB_NAME

    env_extra: dict[str, str] = {}
    if password:
        env_extra["PGPASSWORD"] = password
    env = {**os.environ, **env_extra}

    log.info("efos_stage_drop_create", db=db_name, docker=bool(_DOCKER_CONTAINER))

    # DROP + CREATE via psql
    _run_psql(
        [f"DROP DATABASE IF EXISTS {db_name};", f"CREATE DATABASE {db_name};"],
        host=host, port=port, user=user, dbname="postgres", env=env,
    )

    # Em modo Docker: copia o arquivo para dentro do container
    container_path = str(artifact_path)
    if _DOCKER_CONTAINER:
        container_path = f"/tmp/{artifact_path.name}"
        subprocess.run(
            ["docker", "cp", str(artifact_path), f"{_DOCKER_CONTAINER}:{container_path}"],
            check=True, capture_output=True,
        )
        log.info("efos_stage_docker_cp_ok", container_path=container_path)

    log.info("efos_stage_restore_iniciando", artifact=container_path)

    # pg_restore --format=c obrigatório (gotcha: sem --format=c falha silenciosamente)
    cmd = _cmd("pg_restore") + [
        "--format=c",
        "--no-owner",
        "--no-privileges",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={db_name}",
        container_path,
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,  # pg_restore retorna exit != 0 em warnings; verificamos manualmente
    )

    # Limpa arquivo temporário dentro do container
    if _DOCKER_CONTAINER:
        subprocess.run(
            ["docker", "exec", _DOCKER_CONTAINER, "rm", "-f", container_path],
            capture_output=True, check=False,
        )

    if proc.returncode not in (0, 1):  # 1 = apenas warnings
        log.error(
            "efos_stage_restore_erro",
            returncode=proc.returncode,
            stderr=proc.stderr[:500],
        )
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)

    log.info(
        "efos_stage_restore_concluido",
        returncode=proc.returncode,
        warnings=bool(proc.stderr),
    )

    # Valida tabelas mínimas via asyncpg
    await _validar_tabelas(staging_db_url=staging_db_url, db_name=db_name)


def _run_psql(
    commands: list[str],
    host: str,
    port: str,
    user: str,
    dbname: str,
    env: dict[str, str],
) -> None:
    """Executa comandos SQL via psql (direto ou via docker exec)."""
    for sql in commands:
        cmd = _cmd("psql") + [
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            f"--dbname={dbname}",
            "-c", sql,
        ]
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)


async def _validar_tabelas(staging_db_url: str, db_name: str) -> None:
    """Valida presença das tabelas mínimas via asyncpg.

    Raises:
        StagingValidationError: se alguma tabela obrigatória estiver ausente.
    """
    import asyncpg  # type: ignore[import-untyped]

    # Substitui nome do banco na URL pelo banco de staging
    import urllib.parse
    parsed = urllib.parse.urlparse(staging_db_url)
    staging_url = parsed._replace(path=f"/{db_name}").geturl()
    # asyncpg não aceita postgresql+asyncpg:// — normaliza para postgresql://
    staging_url = staging_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(staging_url)
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tabelas_encontradas = {r["table_name"] for r in rows}
    finally:
        await conn.close()

    faltando = _REQUIRED_TABLES - tabelas_encontradas
    if faltando:
        raise StagingValidationError(
            f"Tabelas obrigatórias ausentes após restore: {sorted(faltando)}. "
            f"Encontradas: {sorted(tabelas_encontradas)[:10]}"
        )

    log.info("efos_stage_validacao_ok", tabelas=sorted(tabelas_encontradas))
