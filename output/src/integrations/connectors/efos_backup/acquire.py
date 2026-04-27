"""Módulo de aquisição de backup EFOS via SSH/SFTP.

Baixa o dump mais recente do servidor Windows via paramiko.
Usa PKey.from_private_key_file() para suportar RSA e Ed25519 automaticamente.
"""

from __future__ import annotations

import hashlib
import ntpath
import os
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# Hora mínima (UTC) em que o backup do dia está disponível
# EFOS gera backup às 16:30 BRT = 19:30 UTC; 12:30 BRT = 15:30 UTC
_BACKUP_AVAILABLE_AFTER_UTC_HOUR = 16  # 13:00 BRT = 16:00 UTC


def _compute_sha256(path: Path) -> str:
    """Computa SHA-256 de um arquivo local.

    Args:
        path: caminho do arquivo.

    Returns:
        Hash SHA-256 em hex lowercase.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def acquire(config: object) -> tuple[Path, str]:
    """Baixa o dump EFOS mais recente via SSH/SFTP.

    Identifica o dump mais recente disponível:
    - Se hora atual UTC >= 16:00, usa o dump de hoje.
    - Caso contrário, usa o dump de ontem (D-1).

    Args:
        config: EFOSBackupConfig com credenciais SSH e paths.

    Returns:
        Tuple (caminho_local, sha256_hex).

    Raises:
        FileNotFoundError: se nenhum dump for encontrado no servidor.
        Exception: erros de conexão SSH/SFTP.
    """
    import paramiko  # type: ignore[import-untyped]

    from src.integrations.config import EFOSBackupConfig

    cfg: EFOSBackupConfig = config  # type: ignore[assignment]

    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= _BACKUP_AVAILABLE_AFTER_UTC_HOUR:
        target_date = now_utc.date()
    else:
        from datetime import timedelta
        target_date = (now_utc - timedelta(days=1)).date()

    date_str = target_date.strftime("%Y%m%d")

    # Conecta via SSH usando chave privada genérica (RSA ou Ed25519)
    pkey = paramiko.PKey.from_private_key_file(cfg.ssh_key_path)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=cfg.ssh_host,
        username=cfg.ssh_user,
        pkey=pkey,
        timeout=30,
    )

    try:
        sftp = ssh.open_sftp()
        try:
            # Converte path remoto Windows: usa ntpath para separador \\
            remote_dir = cfg.backup_remote_path.replace("/", "\\")
            # Lista arquivos no diretório remoto
            try:
                files = sftp.listdir(cfg.backup_remote_path)
            except Exception:
                # Tenta com separador Windows
                files = sftp.listdir(remote_dir)

            # Filtra arquivos do dia alvo (formato esperado: backup_YYYYMMDD*.dump)
            candidates = [
                f for f in files
                if date_str in f and f.endswith(".dump")
            ]

            if not candidates:
                raise FileNotFoundError(
                    f"Nenhum dump EFOS encontrado para {date_str} em {cfg.backup_remote_path}"
                )

            # Pega o mais recente (sort lexicográfico funciona com timestamp no nome)
            candidates.sort(reverse=True)
            remote_filename = candidates[0]

            # Monta path remoto compatível com Windows
            remote_path = ntpath.join(cfg.backup_remote_path, remote_filename)

            # Garante diretório local de artifacts
            artifact_dir = Path(cfg.artifact_dir)
            artifact_dir.mkdir(parents=True, exist_ok=True)

            local_path = artifact_dir / remote_filename

            log.info(
                "efos_acquire_baixando",
                remote_path=remote_path,
                local_path=str(local_path),
            )
            sftp.get(remote_path, str(local_path))

        finally:
            sftp.close()
    finally:
        ssh.close()

    checksum = _compute_sha256(local_path)
    log.info(
        "efos_acquire_concluido",
        local_path=str(local_path),
        checksum=checksum[:12],
        size_bytes=local_path.stat().st_size,
    )
    return local_path, checksum
