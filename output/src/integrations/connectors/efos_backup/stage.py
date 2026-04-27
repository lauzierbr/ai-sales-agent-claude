"""Módulo de staging: restaura dump EFOS em banco temporário.

Usa pg_restore --format=c para restaurar dump no formato custom do PostgreSQL.
Valida presença das 6 tabelas mínimas após restore.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_REQUIRED_TABLES = {
    "tb_produto",
    "tb_cliente",
    "tb_pedido",
    "tb_itens",
    "tb_vendedor",
    "tb_saldo",
}

_STAGING_DB_NAME = "efos_staging"


class StagingValidationError(Exception):
    """Levantada quando tabelas obrigatórias estão ausentes após o restore."""
    pass


async def stage(artifact_path: Path, staging_db_url: str) -> None:
    """Restaura dump EFOS em banco de staging e valida estrutura.

    Fluxo:
    1. Extrai DSN do staging_db_url para obter host, port, user, password.
    2. DROP DATABASE efos_staging (se existir) + CREATE DATABASE efos_staging.
    3. pg_restore --format=c --no-owner --no-privileges -d efos_staging.
    4. Valida presença das 6 tabelas mínimas.

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
    # Banco alvo fixo para staging
    db_name = _STAGING_DB_NAME

    env_extra: dict[str, str] = {}
    if password:
        env_extra["PGPASSWORD"] = password

    import os
    env = {**os.environ, **env_extra}

    # URL de conexão para manutenção (usa banco postgres)
    maintenance_url = staging_db_url.replace(f"/{db_name}", "/postgres")

    log.info("efos_stage_drop_create", db=db_name)

    # DROP + CREATE via psql
    _run_psql(
        [f"DROP DATABASE IF EXISTS {db_name}; CREATE DATABASE {db_name};"],
        host=host, port=port, user=user, dbname="postgres", env=env,
    )

    log.info("efos_stage_restore_iniciando", artifact=str(artifact_path))

    # pg_restore --format=c obrigatório (gotcha: sem --format=c falha silenciosamente)
    cmd = [
        "pg_restore",
        "--format=c",
        "--no-owner",
        "--no-privileges",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={db_name}",
        str(artifact_path),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,  # pg_restore retorna exit != 0 em warnings; verificamos manualmente
    )

    if proc.returncode not in (0, 1):  # 1 = warnings apenas
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

    # Valida tabelas mínimas
    await _validar_tabelas(host=host, port=port, user=user, db_name=db_name, env=env)


def _run_psql(
    commands: list[str],
    host: str,
    port: str,
    user: str,
    dbname: str,
    env: dict[str, str],
) -> None:
    """Executa comandos SQL via psql.

    Args:
        commands: lista de comandos SQL a executar.
        host, port, user, dbname: parâmetros de conexão.
        env: variáveis de ambiente (inclui PGPASSWORD se necessário).
    """
    for sql in commands:
        cmd = [
            "psql",
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            f"--dbname={dbname}",
            "-c", sql,
        ]
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)


async def _validar_tabelas(
    host: str,
    port: str,
    user: str,
    db_name: str,
    env: dict[str, str],
) -> None:
    """Valida presença das tabelas mínimas no banco de staging.

    Args:
        host, port, user, db_name: parâmetros de conexão.
        env: variáveis de ambiente.

    Raises:
        StagingValidationError: se alguma tabela obrigatória estiver ausente.
    """
    sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"
    )
    cmd = [
        "psql",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={db_name}",
        "--no-align",
        "--tuples-only",
        "-c", sql,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    tabelas_encontradas = {
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip()
    }

    faltando = _REQUIRED_TABLES - tabelas_encontradas
    if faltando:
        raise StagingValidationError(
            f"Tabelas obrigatórias ausentes após restore: {sorted(faltando)}. "
            f"Tabelas encontradas: {sorted(tabelas_encontradas)}"
        )

    log.info("efos_stage_validacao_ok", tabelas=sorted(tabelas_encontradas))
