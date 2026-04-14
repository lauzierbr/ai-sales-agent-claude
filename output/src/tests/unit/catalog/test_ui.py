"""Testes unitários dos endpoints FastAPI do domínio Catalog.

Usa httpx.AsyncClient com ASGITransport e dependency_overrides para mock.
Todos os testes são @pytest.mark.unit — sem I/O real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.catalog.service import CatalogService
from src.catalog.types import (
    ExcelUploadResult,
    Produto,
    ResultadoBusca,
    StatusEnriquecimento,
)
from src.main import app
from src.catalog.ui import get_catalog_service

# ─────────────────────────────────────────────
# Fixture de middleware de tenant — Sprint 1
# Patch _get_tenant para evitar hit em Redis/DB nos testes unitários.
# ─────────────────────────────────────────────

_TENANT_JMB = {
    "id": "jmb",
    "nome": "JMB Distribuidora",
    "cnpj": "00.000.000/0001-00",
    "ativo": True,
    "whatsapp_number": None,
    "config_json": {},
}


@pytest.fixture(autouse=True)
def patch_tenant_middleware():
    """Substitui _get_tenant por AsyncMock retornando tenant JMB em todos os testes deste módulo."""
    with patch(
        "src.providers.tenant_context._get_tenant",
        new=AsyncMock(return_value=_TENANT_JMB),
    ):
        yield


def make_mock_service(produto_fixture: Produto) -> AsyncMock:
    """Cria mock de CatalogService para uso nos testes de UI."""
    mock = AsyncMock(spec=CatalogService)
    mock.listar_produtos.return_value = [produto_fixture]
    mock.get_produto.return_value = produto_fixture
    mock.buscar_semantico.return_value = [
        ResultadoBusca(produto=produto_fixture, distancia=0.15)
    ]
    mock.aprovar_produto.return_value = produto_fixture
    mock.rejeitar_produto.return_value = produto_fixture
    mock.processar_excel_precos.return_value = ExcelUploadResult(
        linhas_processadas=4,
        inseridos=3,
        atualizados=0,
        erros=["Linha 4: CNPJ do cliente vazio"],
    )
    return mock


def make_client() -> AsyncClient:
    """Cria AsyncClient com ASGITransport (httpx >= 0.20)."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ─────────────────────────────────────────────
# GET /catalog/produtos — critério A5
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_listar_produtos_retorna_200(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """GET /catalog/produtos com X-Tenant-ID válido deve retornar 200."""
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.get(
                "/catalog/produtos",
                headers={"X-Tenant-ID": tenant_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["codigo_externo"] == "SKU001"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_listar_produtos_sem_header_retorna_401(
    produto_fixture: Produto,
) -> None:
    """GET /catalog/produtos sem X-Tenant-ID retorna 401 (TenantProvider — Sprint 1).

    Sprint 0 esperava 422 (FastAPI validation). Sprint 1 adiciona TenantProvider
    que intercepta antes e retorna 401 (D022: middleware de tenant obrigatório).
    """
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service
    try:
        with patch(
            "src.providers.tenant_context._get_tenant",
            new=AsyncMock(return_value=None),
        ):
            async with make_client() as client:
                response = await client.get("/catalog/produtos")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# POST /catalog/busca — critério A6
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_busca_semantica_retorna_resultado(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """POST /catalog/busca deve retornar lista com campos 'produto' e 'score'."""
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.post(
                "/catalog/busca",
                json={"query": "shampoo hidratante", "limit": 5},
                headers={"X-Tenant-ID": tenant_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert "produto" in data[0]
        assert "score" in data[0]
        assert isinstance(data[0]["score"], float)
        assert 0.0 <= data[0]["score"] <= 1.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_busca_semantica_query_vazia_retorna_422(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """POST /catalog/busca com query vazia deve retornar 422."""
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service
    try:
        async with make_client() as client:
            response = await client.post(
                "/catalog/busca",
                json={"query": "", "limit": 5},
                headers={"X-Tenant-ID": tenant_id},
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# POST /catalog/precos/upload — critério A7
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_upload_precos_excel_retorna_resultado(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """POST /catalog/precos/upload com fixture Excel deve retornar ExcelUploadResult."""
    from pathlib import Path

    fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "precos_teste.xlsx"
    if not fixture_path.exists():
        pytest.skip("Fixture precos_teste.xlsx não encontrada")

    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.post(
                "/catalog/precos/upload",
                files={
                    "file": (
                        "precos.xlsx",
                        fixture_path.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                headers={"X-Tenant-ID": tenant_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert "linhas_processadas" in data
        assert "inseridos" in data
        assert "erros" in data
        assert isinstance(data["erros"], list)
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# GET /catalog/painel — HTML
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_painel_retorna_html(
    produto_fixture: Produto,
) -> None:
    """GET /catalog/painel deve retornar content-type text/html.

    O Jinja2 TemplateResponse é mockado porque Jinja2 3.x + Python 3.14
    tem incompatibilidade na serialização do cache_key — registrado como tech debt.
    """
    from unittest.mock import patch, MagicMock
    from fastapi.responses import HTMLResponse

    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    html_fake = "<html><body>Painel OK</body></html>"
    mock_response = HTMLResponse(content=html_fake)

    try:
        with patch("src.catalog.ui.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = mock_response
            async with make_client() as client:
                response = await client.get(
                    "/catalog/painel?tenant_id=jmb",
                    headers={"X-Tenant-ID": "jmb"},
                )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        mock_templates.TemplateResponse.assert_called_once()
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# POST /catalog/produtos/{id}/aprovar
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_aprovar_produto_retorna_produto(
    produto_fixture: Produto,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """POST /catalog/produtos/{id}/aprovar deve retornar produto atualizado."""
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.post(
                f"/catalog/produtos/{produto_id}/aprovar",
                headers={"X-Tenant-ID": tenant_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["codigo_externo"] == "SKU001"
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# POST /catalog/crawl — A9: exige JWT de gestor
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_crawl_sem_jwt_retorna_401(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """A9: POST /catalog/crawl sem Authorization header retorna 401."""
    import os
    os.environ.setdefault("JWT_SECRET", "secret-de-teste-com-32-caracteres-ok")

    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.post(
                "/catalog/crawl",
                params={"tenant_id": tenant_id},
                headers={
                    "X-Tenant-ID": tenant_id,
                    # sem Authorization header
                },
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_crawl_role_cliente_retorna_403(
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """A9: POST /catalog/crawl com JWT de role=cliente retorna 403."""
    import os
    os.environ.setdefault("JWT_SECRET", "secret-de-teste-com-32-caracteres-ok")

    from src.providers.auth import create_access_token

    token = create_access_token("u1", tenant_id, "cliente", expire_hours=1)
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service

    try:
        async with make_client() as client:
            response = await client.post(
                "/catalog/crawl",
                params={"tenant_id": tenant_id},
                headers={
                    "X-Tenant-ID": tenant_id,
                    "Authorization": f"Bearer {token}",
                },
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
