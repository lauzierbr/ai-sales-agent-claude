"""Testes unitários dos tipos do domínio Catalog."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from src.catalog.types import (
    PrecoDiferenciado,
    Produto,
    ProdutoBruto,
    ResultadoBusca,
    StatusEnriquecimento,
)


@pytest.mark.unit
def test_status_enriquecimento_valores() -> None:
    """StatusEnriquecimento deve ter os 5 valores esperados."""
    assert StatusEnriquecimento.PENDENTE.value == "pendente"
    assert StatusEnriquecimento.ENRIQUECIDO.value == "enriquecido"
    assert StatusEnriquecimento.EM_REVISAO.value == "em_revisao"
    assert StatusEnriquecimento.ATIVO.value == "ativo"
    assert StatusEnriquecimento.INATIVO.value == "inativo"


@pytest.mark.unit
def test_produto_bruto_campos_obrigatorios() -> None:
    """ProdutoBruto deve exigir codigo_externo, nome_bruto e tenant_id."""
    p = ProdutoBruto(
        codigo_externo="SKU001",
        nome_bruto="Produto Teste",
        tenant_id="jmb",
    )
    assert p.codigo_externo == "SKU001"
    assert p.nome_bruto == "Produto Teste"
    assert p.tenant_id == "jmb"
    assert p.preco_padrao is None
    assert p.descricao_bruta is None


@pytest.mark.unit
def test_preco_diferenciado_normaliza_cnpj() -> None:
    """PrecoDiferenciado deve normalizar CNPJ para apenas dígitos."""
    preco = PrecoDiferenciado(
        tenant_id="jmb",
        codigo_produto="SKU001",
        cliente_cnpj="12.345.678/0001-90",
        preco_cliente=Decimal("29.90"),
    )
    assert preco.cliente_cnpj == "12345678000190"
    assert "." not in preco.cliente_cnpj
    assert "/" not in preco.cliente_cnpj
    assert "-" not in preco.cliente_cnpj


@pytest.mark.unit
def test_preco_diferenciado_cnpj_sem_pontuacao() -> None:
    """PrecoDiferenciado deve aceitar CNPJ já sem pontuação."""
    preco = PrecoDiferenciado(
        tenant_id="jmb",
        codigo_produto="SKU001",
        cliente_cnpj="12345678000190",
        preco_cliente=Decimal("29.90"),
    )
    assert preco.cliente_cnpj == "12345678000190"


@pytest.mark.unit
def test_resultado_busca_score(produto_fixture: Produto) -> None:
    """ResultadoBusca deve calcular score como 1 - distancia."""
    resultado = ResultadoBusca(produto=produto_fixture, distancia=0.15)
    assert resultado.score == pytest.approx(0.85, abs=1e-4)
    assert resultado.distancia == 0.15


@pytest.mark.unit
def test_resultado_busca_to_dict(produto_fixture: Produto) -> None:
    """ResultadoBusca.to_dict deve conter 'produto' e 'score'."""
    resultado = ResultadoBusca(produto=produto_fixture, distancia=0.20)
    d = resultado.to_dict()
    assert "produto" in d
    assert "score" in d
    assert "distancia" in d
    assert isinstance(d["produto"], dict)
    assert d["produto"]["codigo_externo"] == "SKU001"


@pytest.mark.unit
def test_produto_to_dict(produto_fixture: Produto) -> None:
    """Produto.to_dict deve serializar todos os campos principais."""
    d = produto_fixture.to_dict()
    assert d["codigo_externo"] == "SKU001"
    assert d["tenant_id"] == "jmb"
    assert d["status_enriquecimento"] == "enriquecido"
    assert isinstance(d["tags"], list)
    assert isinstance(d["meta_agente"], dict)
