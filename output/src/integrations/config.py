"""Configuração do domínio Integrations — EFOSBackupConfig.

Camada Config: importa apenas Types do domínio.
Secrets lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class EFOSBackupConfig:
    """Configuração do conector de backup EFOS via SSH/SFTP.

    Todos os valores são lidos de variáveis de ambiente prefixadas por
    {TENANT_UPPER}_EFOS_* para suporte multi-tenant.
    """

    ssh_host: str
    ssh_user: str
    backup_remote_path: str
    artifact_dir: str
    staging_db_url: str
    ssh_password: str | None = field(default=None)
    ssh_key_path: str | None = field(default=None)

    @classmethod
    def for_tenant(cls, tenant_id: str) -> "EFOSBackupConfig":
        """Cria configuração a partir de variáveis de ambiente do tenant.

        Args:
            tenant_id: ID do tenant (ex: "jmb"). Usado como prefixo das env vars.

        Returns:
            EFOSBackupConfig populado com valores das env vars.

        Raises:
            ValueError: se alguma variável obrigatória não estiver definida.
        """
        prefix = tenant_id.upper()

        def _require(name: str) -> str:
            val = os.getenv(name)
            if not val:
                raise ValueError(f"Variável de ambiente obrigatória não definida: {name}")
            return val

        def _optional(name: str) -> str | None:
            return os.getenv(name) or None

        return cls(
            ssh_host=_require(f"{prefix}_EFOS_SSH_HOST"),
            ssh_user=_require(f"{prefix}_EFOS_SSH_USER"),
            ssh_password=_optional(f"{prefix}_EFOS_SSH_PASSWORD"),
            ssh_key_path=_optional(f"{prefix}_EFOS_SSH_KEY_PATH"),
            backup_remote_path=_require(f"{prefix}_EFOS_BACKUP_REMOTE_PATH"),
            artifact_dir=_require(f"{prefix}_EFOS_ARTIFACT_DIR"),
            staging_db_url=_require(f"{prefix}_EFOS_STAGING_DB_URL"),
        )
