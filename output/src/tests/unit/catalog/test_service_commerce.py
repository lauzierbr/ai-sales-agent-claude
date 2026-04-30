"""Testes unitários para fallback catalog→commerce_products (E1a — Sprint 9).

Cobre:
  - Se commerce_products tem >= 1 registro: busca retorna de commerce
  - Se commerce_products está vazio: busca retorna de produtos (legado)
  - Decisão de fallback está em catalog/service.py, NÃO em catalog/repo.py
  - B-13: get_por_codigo com EAN completo tenta sufixo [-6:]
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.catalog.types import Produto, ResultadoBusca, StatusEnriquecimento


def _make_produto(codigo: str = "SKU001") -> Produto:
    return Produto(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id="jmb",
        codigo_externo=codigo,
        nome_bruto="Shampoo Hidratante 300ml",
        nome="Shampoo Hidratante 300ml",
        status_enriquecimento=StatusEnriquecimento.ATIVO,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_service_usa_commerce_quando_disponivel() -> None:
    """Quando commerce_products tem >= 1 produto, buscar_por_nome usa commerce."""
    from src.catalog.service import CatalogService

    mock_repo = AsyncMock()
    mock_embedding = MagicMock()
    mock_commerce = AsyncMock()

    # commerce_products tem 1 produto
    mock_commerce.count_produtos = AsyncMock(return_value=5)
    mock_commerce.buscar_produtos_commerce = AsyncMock(
        return_value=[
            {
                "external_id": "ext-001",
                "codigo": "SKU001",
                "nome": "Shampoo Hidratante 300ml",
                "preco_padrao": "29.90",
                "ativo": True,
            }
        ]
    )

    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding,
        commerce_repo=mock_commerce,
    )

    mock_session = AsyncMock()
    resultados = await service.buscar_por_nome_commerce(
        tenant_id="jmb",
        query="shampoo",
        limit=5,
        session=mock_session,
    )

    assert len(resultados) == 1
    assert resultados[0].produto.nome == "Shampoo Hidratante 300ml"
    mock_commerce.buscar_produtos_commerce.assert_called_once()
    # repo.buscar_por_embedding NÃO deve ter sido chamado
    mock_repo.buscar_por_embedding.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_service_fallback_legado_quando_commerce_vazio() -> None:
    """Quando commerce_products está vazio, _usar_commerce_products retorna False."""
    from src.catalog.service import CatalogService

    mock_repo = AsyncMock()
    mock_embedding = MagicMock()
    mock_commerce = AsyncMock()
    mock_commerce.count_produtos = AsyncMock(return_value=0)

    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding,
        commerce_repo=mock_commerce,
    )

    mock_session = AsyncMock()
    usar = await service._usar_commerce_products(tenant_id="jmb", session=mock_session)
    assert usar is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_service_fallback_sem_commerce_repo() -> None:
    """Sem commerce_repo injetado, _usar_commerce_products retorna False."""
    from src.catalog.service import CatalogService

    mock_repo = AsyncMock()
    mock_embedding = MagicMock()

    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding,
        commerce_repo=None,
    )

    mock_session = AsyncMock()
    usar = await service._usar_commerce_products(tenant_id="jmb", session=mock_session)
    assert usar is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_get_por_codigo_ean_completo_fallback_sufixo() -> None:
    """B-13: get_por_codigo tenta query[-6:] quando EAN completo não encontrado."""
    from src.catalog.service import CatalogService

    produto_mock = _make_produto("148571")
    mock_repo = AsyncMock()
    # Primeiro call com EAN completo → None
    # Segundo call com sufixo → produto
    mock_repo.get_produto_por_codigo = AsyncMock(side_effect=[None, produto_mock])

    mock_embedding = MagicMock()
    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding,
    )

    query = "7898923148571"  # EAN completo de 13 dígitos
    resultado = await service.get_por_codigo(tenant_id="jmb", codigo_externo=query)

    assert resultado is not None, "B-13: EAN completo deve retornar produto via sufixo [-6:]"
    assert resultado.produto.codigo_externo == "148571"
    # Verificar que foi chamado duas vezes: com EAN completo e depois com sufixo
    assert mock_repo.get_produto_por_codigo.call_count == 2
    calls = mock_repo.get_produto_por_codigo.call_args_list
    assert calls[0][0][1] == "7898923148571"  # primeiro: EAN completo
    assert calls[1][0][1] == "148571"  # segundo: sufixo [-6:]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b13_get_por_codigo_curto_sem_fallback() -> None:
    """B-13: código curto (<= 6 dígitos) NÃO aplica lógica de sufixo."""
    from src.catalog.service import CatalogService

    produto_mock = _make_produto("148571")
    mock_repo = AsyncMock()
    mock_repo.get_produto_por_codigo = AsyncMock(return_value=produto_mock)

    mock_embedding = MagicMock()
    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding,
    )

    resultado = await service.get_por_codigo(tenant_id="jmb", codigo_externo="148571")

    assert resultado is not None
    # Deve ter sido chamado apenas UMA vez (sem fallback)
    assert mock_repo.get_produto_por_codigo.call_count == 1


@pytest.mark.unit
def test_catalog_repo_nao_tem_logica_commerce() -> None:
    """E18 Sprint 10: buscar_por_embedding agora usa commerce_products como fonte PRINCIPAL.

    Sprint 9: decisão de fallback no service.
    Sprint 10 (E18): migração completa — catalog/repo.py lê commerce_products diretamente.
    Verificação atualizada: repo pode referenciar commerce_products (E18), mas não
    deve importar CommerceRepo (evita acoplamento entre repos).
    """
    import src.catalog.repo as repo_module

    source = open(repo_module.__file__).read()  # noqa: WPS515
    # E18: commerce_products é permitido no repo (busca semântica migrada)
    # Verificar apenas que CommerceRepo não é importado (manter camadas limpas)
    assert "CommerceRepo" not in source, (
        "catalog/repo.py NÃO deve importar CommerceRepo — use SQL direto."
    )
    assert "buscar_produtos_commerce" not in source, (
        "catalog/repo.py NÃO deve chamar buscar_produtos_commerce — use SQL direto."
    )
