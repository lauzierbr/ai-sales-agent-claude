"""TenantProvider — middleware FastAPI para resolução de tenant por request.

Cross-cutting provider.
Decisão D020: shared table + tenant_id para todos os domínios.
Decisão D022: X-Tenant-ID header como mecanismo de identificação de tenant.
"""

from __future__ import annotations

import json
import os
from typing import Any, cast

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

log = structlog.get_logger(__name__)

# Rotas que não exigem tenant identificado (match exato)
_EXCLUDED_PATHS = frozenset({
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/webhook/whatsapp",
})

# Prefixos excluídos — qualquer path que comece com estes passa sem header
_EXCLUDED_PREFIXES = (
    "/catalog/painel",  # painel de revisão usa tenant_id via query param
    "/dashboard",       # dashboard resolve tenant via cookie JWT (D023)
)

_CACHE_TTL = int(os.getenv("TENANT_CACHE_TTL", "60"))


class TenantProvider(BaseHTTPMiddleware):
    """Middleware que resolve e injeta tenant em cada request.

    Fluxo:
    1. Verifica se a rota está na lista de exclusão — passa adiante.
    2. Extrai X-Tenant-ID do header.
    3. Tenta Redis cache (TTL 60s) → fallback para DB.
    4. Valida que tenant existe e está ativo.
    5. Injeta request.state.tenant_id e request.state.tenant.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Intercepta request e injeta contexto de tenant."""
        # Rotas excluídas passam direto
        path = request.url.path
        if path in _EXCLUDED_PATHS or path.startswith(_EXCLUDED_PREFIXES):
            return await call_next(request)

        # Extrai header
        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if not tenant_id:
            return JSONResponse(
                {"detail": "Tenant inválido ou inativo"},
                status_code=401,
            )

        # Tenta cache Redis → DB
        tenant = await _get_tenant(tenant_id)

        if tenant is None or not tenant.get("ativo", False):
            return JSONResponse(
                {"detail": "Tenant inválido ou inativo"},
                status_code=401,
            )

        # Injeta no estado do request
        request.state.tenant_id = tenant_id
        request.state.tenant = tenant  # dict com dados do tenant

        return await call_next(request)


async def _get_tenant(tenant_id: str) -> dict[str, Any] | None:
    """Busca tenant no cache Redis ou DB.

    Returns:
        Dict com dados do tenant, ou None se não encontrado.
    """
    # Tenta Redis primeiro
    cached = await _get_from_redis(tenant_id)
    if cached is not None:
        return cached

    # Fallback: DB
    tenant_dict = await _get_from_db(tenant_id)
    if tenant_dict is not None:
        await _set_in_redis(tenant_id, tenant_dict)

    return tenant_dict


async def _get_from_redis(tenant_id: str) -> dict[str, Any] | None:
    """Tenta obter tenant do cache Redis.

    Returns:
        Dict do tenant ou None se cache miss ou Redis indisponível.
    """
    try:
        from src.providers.db import get_redis

        redis = get_redis()
        data = await redis.get(f"tenant:{tenant_id}")
        if data:
            return cast(dict[str, Any], json.loads(data))
    except Exception as exc:
        log.warning("redis_cache_erro", tenant_id=tenant_id, error=str(exc))
    return None


async def _set_in_redis(tenant_id: str, tenant_dict: dict[str, Any]) -> None:
    """Armazena tenant no cache Redis com TTL.

    Falha silenciosa se Redis indisponível.
    """
    try:
        from src.providers.db import get_redis

        redis = get_redis()
        await redis.setex(f"tenant:{tenant_id}", _CACHE_TTL, json.dumps(tenant_dict, default=str))
    except Exception as exc:
        log.warning("redis_set_erro", tenant_id=tenant_id, error=str(exc))


async def _get_from_db(tenant_id: str) -> dict[str, Any] | None:
    """Busca tenant diretamente no PostgreSQL.

    Returns:
        Dict do tenant ou None se não encontrado.
    """
    try:
        from sqlalchemy import text

        from src.providers.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, nome, cnpj, ativo, whatsapp_number, config_json "
                    "FROM tenants WHERE id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return {
                "id": row["id"],
                "nome": row["nome"],
                "cnpj": row["cnpj"],
                "ativo": row["ativo"],
                "whatsapp_number": row["whatsapp_number"],
                "config_json": row["config_json"] or {},
            }
    except Exception as exc:
        log.error("tenant_db_erro", tenant_id=tenant_id, error=str(exc))
        return None
