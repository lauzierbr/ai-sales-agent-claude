"""Configurações do domínio Tenants.

Camada Config: importa apenas stdlib.
Secrets lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations


class TenantConfig:
    """Configurações operacionais do domínio Tenants."""

    tenant_cache_ttl: int = 60  # segundos no Redis
    max_tenants_per_page: int = 100
