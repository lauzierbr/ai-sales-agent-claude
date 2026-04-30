"""Testes de integração do EfosCrawler — removido em Sprint 10 E19.

O crawler EFOS foi removido em Sprint 10 (E19). Este arquivo é mantido apenas
como registro histórico e está marcado como skip para não quebrar a coleta
global do pytest.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="catalog crawler removido em Sprint 10 E19")


@pytest.mark.integration
@pytest.mark.slow
async def test_login_efos_autenticado() -> None:
    """Verifica que o login no EFOS retorna True com credenciais válidas."""
    config = CrawlerConfig.for_tenant("jmb")
    async with EfosCrawler(config) as crawler:
        assert crawler._authenticated is True


@pytest.mark.integration
@pytest.mark.slow
async def test_get_categorias_retorna_lista_nao_vazia() -> None:
    """Verifica que get_categorias retorna ao menos 1 categoria."""
    config = CrawlerConfig.for_tenant("jmb")
    async with EfosCrawler(config) as crawler:
        categorias = await crawler.get_categorias()
    assert len(categorias) > 0
    assert all(isinstance(c, Categoria) for c in categorias)
    assert all(c.nome for c in categorias)


@pytest.mark.integration
@pytest.mark.slow
async def test_get_produtos_primeira_categoria_nao_vazia() -> None:
    """Verifica que get_produtos retorna produtos para a primeira categoria."""
    config = CrawlerConfig.for_tenant("jmb")
    async with EfosCrawler(config) as crawler:
        categorias = await crawler.get_categorias()
        assert len(categorias) > 0

        primeira = categorias[0]
        produtos = await crawler.get_produtos(primeira)

    assert len(produtos) > 0
    assert all(isinstance(p, ProdutoBruto) for p in produtos)
    assert all(p.codigo_externo for p in produtos)
    assert all(p.nome_bruto for p in produtos)
    assert all(p.tenant_id == "jmb" for p in produtos)
