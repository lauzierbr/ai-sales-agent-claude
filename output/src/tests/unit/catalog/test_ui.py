"""Testes unitários dos endpoints FastAPI do domínio Catalog.

Usa httpx.AsyncClient com ASGITransport e dependency_overrides para mock.
Todos os testes são @pytest.mark.unit — sem I/O real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
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
async def test_listar_produtos_sem_header_retorna_422(
    produto_fixture: Produto,
) -> None:
    """GET /catalog/produtos sem X-Tenant-ID deve retornar 422."""
    # FastAPI resolve dependencies mesmo para erros 422 — precisamos de override
    mock_service = make_mock_service(produto_fixture)
    app.dependency_overrides[get_catalog_service] = lambda: mock_service
    try:
        async with make_client() as client:
            response = await client.get("/catalog/produtos")
        assert response.status_code == 422
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
                response = await client.get("/catalog/painel?tenant_id=jmb")

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
