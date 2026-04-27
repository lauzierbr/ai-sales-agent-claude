"""Tipos do domínio Integrations — enums e dataclasses.

Camada Types: sem imports internos do projeto.
Não importa agents/, catalog/, orders/, tenants/, dashboard/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SyncStatus(StrEnum):
    """Status de uma execução de sync."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class ConnectorCapability(StrEnum):
    """Capacidade de dados que um conector pode fornecer."""

    CATALOG = "catalog"
    PRICING_B2B = "pricing_b2b"
    CUSTOMERS_B2B = "customers_b2b"
    ORDERS_B2B = "orders_b2b"
    INVENTORY = "inventory"
    SALES_HISTORY = "sales_history"


@dataclass
class SyncRun:
    """Registro de uma execução de sincronização."""

    id: UUID
    tenant_id: str
    connector_kind: str
    capabilities: list[ConnectorCapability]
    started_at: datetime
    finished_at: datetime | None
    status: SyncStatus
    rows_published: int
    error: str | None


@dataclass
class SyncArtifact:
    """Registro de um artefato (arquivo de backup) processado."""

    id: UUID
    tenant_id: str
    connector_kind: str
    artifact_path: str
    artifact_checksum: str
    created_at: datetime
