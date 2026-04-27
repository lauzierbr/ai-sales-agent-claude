"""Módulo de aquisição de backup EFOS via SSH/SFTP.

Baixa o dump mais recente do servidor Windows via paramiko.
Suporta autenticação por senha (preferencial) ou chave privada.
Formato de arquivo EFOS: backup_em_DD_MM_YYYY_HH.MM.SS.backup
"""

from __future__ import annotations

import hashlib
import ntpath
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# Fuso BRT = UTC-3
_BRT = timezone(timedelta(hours=-3))

# Hora mínima BRT em que o backup do dia está disponível (13:00 BRT)
_BACKUP_AVAILABLE_AFTER_BRT_HOUR = 13

# Padrão do nome do arquivo: backup_em_24_04_2026_12.30.00.backup
_FILENAME_RE = re.compile(
    r"backup_em_(\d{2})_(\d{2})_(\d{4})_(\d{2})\.(\d{2})\.(\d{2})\.backup",
    re.IGNORECASE,
)


def _parse_file_datetime(filename: str) -> datetime | None:
    """Extrai datetime do nome do arquivo EFOS."""
    m = _FILENAME_RE.search(filename)
    if not m:
        return None
    day, month, year, hour, minute, second = (int(x) for x in m.groups())
    return datetime(year, month, day, hour, minute, second)


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def acquire(config: object) -> tuple[Path, str]:
    """Baixa o dump EFOS mais recente via SSH/SFTP.

    Lógica de seleção:
    - Se hora BRT atual >= 13:00 → procura dumps de hoje
    - Caso contrário → procura dumps de D-1
    - Entre os candidatos do dia, pega o mais recente

    Args:
        config: EFOSBackupConfig com credenciais SSH e paths.

    Returns:
        Tuple (caminho_local, sha256_hex).

    Raises:
        FileNotFoundError: se nenhum dump for encontrado para a data alvo.
    """
    import paramiko  # type: ignore[import-untyped]

    from src.integrations.config import EFOSBackupConfig

    cfg: EFOSBackupConfig = config  # type: ignore[assignment]

    now_brt = datetime.now(_BRT)
    if now_brt.hour >= _BACKUP_AVAILABLE_AFTER_BRT_HOUR:
        target_date = now_brt.date()
    else:
        target_date = (now_brt - timedelta(days=1)).date()

    log.info("efos_acquire_conectando", host=cfg.ssh_host, target_date=str(target_date))

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Preferência: senha; fallback: chave privada
    connect_kwargs: dict = {
        "hostname": cfg.ssh_host,
        "username": cfg.ssh_user,
        "timeout": 30,
    }
    if cfg.ssh_password:
        connect_kwargs["password"] = cfg.ssh_password
    elif cfg.ssh_key_path:
        connect_kwargs["pkey"] = paramiko.PKey.from_private_key_file(cfg.ssh_key_path)

    ssh.connect(**connect_kwargs)

    try:
        sftp = ssh.open_sftp()
        try:
            # Lista arquivos no diretório remoto (tenta separador Windows e Unix)
            remote_dir = cfg.backup_remote_path
            try:
                files = sftp.listdir(remote_dir)
            except Exception:
                remote_dir = cfg.backup_remote_path.replace("/", "\\")
                files = sftp.listdir(remote_dir)

            # Filtra arquivos .backup e extrai datetime do nome
            candidates: list[tuple[datetime, str]] = []
            for fname in files:
                if not fname.lower().endswith(".backup"):
                    continue
                file_dt = _parse_file_datetime(fname)
                if file_dt is None:
                    continue
                if file_dt.date() == target_date:
                    candidates.append((file_dt, fname))

            # Fallback: D-1 se não houver dumps do dia
            if not candidates:
                fallback_date = target_date - timedelta(days=1)
                for fname in files:
                    if not fname.lower().endswith(".backup"):
                        continue
                    file_dt = _parse_file_datetime(fname)
                    if file_dt and file_dt.date() == fallback_date:
                        candidates.append((file_dt, fname))

            if not candidates:
                raise FileNotFoundError(
                    f"Nenhum dump EFOS encontrado para {target_date} em {cfg.backup_remote_path}. "
                    f"Arquivos disponíveis: {[f for f in files if f.endswith('.backup')][:5]}"
                )

            # Mais recente primeiro
            candidates.sort(reverse=True)
            remote_filename = candidates[0][1]
            remote_path = ntpath.join(remote_dir, remote_filename)

            artifact_dir = Path(cfg.artifact_dir)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            local_path = artifact_dir / remote_filename

            log.info("efos_acquire_baixando", remote=remote_path, local=str(local_path))
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
