"""Testes unitários de providers/tenant_context.py — TenantProvider middleware.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(tenant_dict: dict[str, Any] | None = None) -> FastAPI:
    """Cria app de teste com TenantProvider e um endpoint simples."""
    from src.providers.tenant_context import TenantProvider

    app = FastAPI()
    app.add_middleware(TenantProvider)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/auth/login")
    async def fake_login() -> dict[str, Any]:
        return {"token": "fake"}

    @app.get("/catalog/produtos")
    async def produtos(request: MagicMock) -> dict[str, Any]:
        return {"tenant_id": request.state.tenant_id}

    return app


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def mock_get_tenant_success() -> dict[str, Any]:
    return {
        "id": "jmb",
        "nome": "JMB Distribuidora",
        "cnpj": "00.000.000/0001-00",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
    }


# ─────────────────────────────────────────────
# Testes do middleware
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_rota_excluida_sem_tenant(mock_get_tenant_success: dict[str, Any]) -> None:
    """Rotas em EXCLUDED_PATHS passam sem X-Tenant-ID — nunca retornam 401."""
    import httpx

    from src.providers.tenant_context import TenantProvider

    app = FastAPI()
    app.add_middleware(TenantProvider)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/auth/login")
    async def login() -> dict[str, Any]:
        return {"msg": "ok"}

    @app.post("/webhook/whatsapp")
    async def webhook() -> dict[str, Any]:
        return {"status": "received"}

    @app.get("/catalog/painel")
    async def painel() -> dict[str, Any]:
        return {"produtos": []}

    @app.post("/catalog/painel/{produto_id}/aprovar")
    async def aprovar(produto_id: str) -> dict[str, Any]:
        return {"ok": True}

    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=mock_get_tenant_success),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # /health — sem X-Tenant-ID
            resp = await client.get("/health")
            assert resp.status_code == 200

            # /auth/login — sem X-Tenant-ID
            resp = await client.get("/auth/login")
            assert resp.status_code == 200

            # /webhook/whatsapp — sem X-Tenant-ID
            resp = await client.post("/webhook/whatsapp")
            assert resp.status_code == 200

            # /catalog/painel — sem X-Tenant-ID (usa query param)
            resp = await client.get("/catalog/painel")
            assert resp.status_code == 200

            # /catalog/painel/{id}/aprovar — sem X-Tenant-ID
            resp = await client.post("/catalog/painel/abc123/aprovar")
            assert resp.status_code == 200


@pytest.mark.unit
async def test_tenant_invalido_retorna_401() -> None:
    """Request com tenant_id não encontrado no DB/cache retorna 401."""
    import httpx

    from src.providers.tenant_context import TenantProvider

    app = FastAPI()
    app.add_middleware(TenantProvider)

    @app.get("/catalog/produtos")
    async def produtos() -> dict[str, Any]:
        return {"data": []}

    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=None),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/catalog/produtos", headers={"X-Tenant-ID": "tenant_inexistente"}
            )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Tenant inválido ou inativo"


@pytest.mark.unit
async def test_tenant_inativo_retorna_401() -> None:
    """Tenant com ativo=False retorna 401."""
    import httpx

    from src.providers.tenant_context import TenantProvider

    app = FastAPI()
    app.add_middleware(TenantProvider)

    @app.get("/catalog/produtos")
    async def produtos() -> dict[str, Any]:
        return {"data": []}

    tenant_inativo = {
        "id": "jmb",
        "nome": "JMB",
        "cnpj": "00.000.000/0001-00",
        "ativo": False,  # inativo
        "whatsapp_number": None,
        "config_json": {},
    }

    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=tenant_inativo),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/catalog/produtos", headers={"X-Tenant-ID": "jmb"}
            )
            assert resp.status_code == 401


@pytest.mark.unit
async def test_tenant_valido_injeta_estado(mock_get_tenant_success: dict[str, Any]) -> None:
    """Tenant válido é injetado em request.state via dispatch direto do middleware."""
    from starlette.datastructures import Headers
    from starlette.testclient import TestClient
    from starlette.types import ASGIApp, Receive, Scope, Send

    from src.providers.tenant_context import TenantProvider

    state_capturado = {}

    async def fake_app(scope: Scope, receive: Receive, send: Send) -> None:
        """App mínimo que captura request.state.tenant_id."""
        from starlette.requests import Request as StarletteRequest
        req = StarletteRequest(scope, receive)
        state_capturado["tenant_id"] = getattr(req.state, "tenant_id", None)
        # Emite resposta HTTP 200 mínima
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    middleware = TenantProvider(fake_app)

    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=mock_get_tenant_success),
    ):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/protected",
            "query_string": b"",
            "headers": [(b"x-tenant-id", b"jmb")],
        }
        receive = AsyncMock(return_value={"type": "http.request", "body": b"", "more_body": False})
        send = AsyncMock()

        await middleware(scope, receive, send)

    assert state_capturado.get("tenant_id") == "jmb"


@pytest.mark.unit
async def test_get_tenant_cache_hit_retorna_sem_db() -> None:
    """_get_tenant retorna do cache Redis sem consultar o DB (cache hit)."""
    import json
    from src.providers.tenant_context import _get_tenant

    cached_tenant = {
        "id": "jmb",
        "nome": "JMB",
        "cnpj": "x",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
    }

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_tenant))

    with patch("src.providers.db.get_redis", return_value=mock_redis):
        result = await _get_tenant("jmb")

    assert result is not None
    assert result["id"] == "jmb"
    assert result["ativo"] is True


@pytest.mark.unit
async def test_get_tenant_cache_miss_consulta_db() -> None:
    """_get_tenant consulta o DB quando cache Redis retorna None."""
    from src.providers.tenant_context import _get_tenant

    db_tenant = {
        "id": "jmb",
        "nome": "JMB",
        "cnpj": "x",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
    }

    # Redis cache miss
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    with (
        patch("src.providers.db.get_redis", return_value=mock_redis),
        patch("src.providers.tenant_context._get_from_db", new=AsyncMock(return_value=db_tenant)),
    ):
        result = await _get_tenant("jmb")

    assert result is not None
    assert result["id"] == "jmb"


@pytest.mark.unit
async def test_get_tenant_redis_indisponivel_fallback_db() -> None:
    """_get_tenant faz fallback para DB quando Redis indisponível (falha silenciosa)."""
    from src.providers.tenant_context import _get_tenant

    db_tenant = {
        "id": "jmb",
        "nome": "JMB",
        "cnpj": "x",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
    }

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

    with (
        patch("src.providers.db.get_redis", return_value=mock_redis),
        patch("src.providers.tenant_context._get_from_db", new=AsyncMock(return_value=db_tenant)),
    ):
        result = await _get_tenant("jmb")

    assert result is not None


@pytest.mark.unit
async def test_get_from_db_nao_encontrado_retorna_none() -> None:
    """_get_from_db retorna None quando tenant não existe no DB."""
    from unittest.mock import MagicMock
    from src.providers.tenant_context import _get_from_db

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_ctx)

    with patch("src.providers.db.get_session_factory", return_value=mock_factory):
        result = await _get_from_db("inexistente")

    assert result is None


@pytest.mark.unit
async def test_sem_header_tenant_id_retorna_401() -> None:
    """Request sem X-Tenant-ID em rota protegida retorna 401."""
    import httpx

    from src.providers.tenant_context import TenantProvider

    app = FastAPI()
    app.add_middleware(TenantProvider)

    @app.get("/catalog/produtos")
    async def produtos() -> dict[str, Any]:
        return {"data": []}

    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=None),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/catalog/produtos")  # sem header
            assert resp.status_code == 401
