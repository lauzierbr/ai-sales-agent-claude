"""Testes unitários de tenants/ui.py — endpoints /auth/login e /tenants.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from src.tenants.types import Role, Tenant, Usuario


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_usuario(senha_plain: str = "senha123") -> Usuario:
    from src.providers.auth import hash_password

    return Usuario(
        id="u1",
        tenant_id="jmb",
        cnpj="11.222.333/0001-44",
        senha_hash=hash_password(senha_plain, rounds=4),
        role=Role.gestor,
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_tenant() -> Tenant:
    return Tenant(
        id="jmb",
        nome="JMB Distribuidora",
        cnpj="00.000.000/0001-00",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_app_with_overrides(mock_session: Any = None) -> FastAPI:
    """Cria app isolado com get_session como stub (noop AsyncGenerator)."""
    from src.providers.db import get_session
    from src.tenants.ui import auth_router, router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(router)

    # Override get_session para evitar conexão real ao banco
    async def fake_session() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session] = fake_session
    return app


# ─────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_login_credenciais_validas_retorna_token() -> None:
    """POST /auth/login com CNPJ+senha corretos retorna access_token JWT."""
    import os
    os.environ.setdefault("JWT_SECRET", "secret-de-teste-com-32-caracteres-ok")

    usuario = _make_usuario("senha123")
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.UsuarioRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_cnpj_global = AsyncMock(return_value=usuario)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/login",
                json={"cnpj": "11.222.333/0001-44", "senha": "senha123"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


@pytest.mark.unit
async def test_login_cnpj_nao_encontrado_retorna_401() -> None:
    """POST /auth/login com CNPJ inexistente retorna 401."""
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.UsuarioRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_cnpj_global = AsyncMock(return_value=None)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/login",
                json={"cnpj": "99.999.999/0001-99", "senha": "qualquer"},
            )

    assert resp.status_code == 401
    assert "inválidos" in resp.json()["detail"]


@pytest.mark.unit
async def test_login_senha_errada_retorna_401() -> None:
    """POST /auth/login com senha incorreta retorna 401."""
    usuario = _make_usuario("senha_correta")
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.UsuarioRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_cnpj_global = AsyncMock(return_value=usuario)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/login",
                json={"cnpj": "11.222.333/0001-44", "senha": "senha_errada"},
            )

    assert resp.status_code == 401


@pytest.mark.unit
async def test_login_token_contem_tenant_id_e_role() -> None:
    """JWT retornado pelo login contém tenant_id e role corretos."""
    import os
    from src.providers.auth import decode_token

    os.environ.setdefault("JWT_SECRET", "secret-de-teste-com-32-caracteres-ok")
    usuario = _make_usuario("senha123")
    app = _make_app_with_overrides()

    with (
        patch("src.tenants.ui.UsuarioRepo") as MockRepo,
        patch.dict("os.environ", {"JWT_SECRET": "secret-de-teste-com-32-caracteres-ok"}),
    ):
        mock_repo = AsyncMock()
        mock_repo.get_by_cnpj_global = AsyncMock(return_value=usuario)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/login",
                json={"cnpj": "11.222.333/0001-44", "senha": "senha123"},
            )

    token = resp.json()["access_token"]
    with patch.dict("os.environ", {"JWT_SECRET": "secret-de-teste-com-32-caracteres-ok"}):
        payload = decode_token(token)
    assert payload["tenant_id"] == "jmb"
    assert payload["role"] == "gestor"


# ─────────────────────────────────────────────
# GET /tenants
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_list_tenants_retorna_lista() -> None:
    """GET /tenants retorna lista de tenants ativos."""
    tenant = _make_tenant()
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.TenantRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_active_tenants = AsyncMock(return_value=[tenant])
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/tenants")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "jmb"


@pytest.mark.unit
async def test_get_tenant_por_id_encontrado() -> None:
    """GET /tenants/{id} retorna tenant quando encontrado."""
    tenant = _make_tenant()
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.TenantRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/tenants/jmb")

    assert resp.status_code == 200
    assert resp.json()["id"] == "jmb"


@pytest.mark.unit
async def test_get_tenant_por_id_nao_encontrado_retorna_404() -> None:
    """GET /tenants/{id} retorna 404 quando tenant não existe."""
    app = _make_app_with_overrides()

    with patch("src.tenants.ui.TenantRepo") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        MockRepo.return_value = mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/tenants/inexistente")

    assert resp.status_code == 404
