"""Fixtures globais para os testes do AI Sales Agent.

Todas as fixtures aqui são de escopo unitário — sem I/O externo.
Testes de integração ficam em tests/integration/ e usam @pytest.mark.integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.catalog.types import (
    EnricherProtocol,
    Produto,
    ProdutoBruto,
    ProdutoEnriquecido,
    ResultadoBusca,
    StatusEnriquecimento,
)


# ─────────────────────────────────────────────
# Fixtures de tenant
# ─────────────────────────────────────────────


@pytest.fixture
def tenant_id() -> str:
    """Tenant ID do projeto piloto JMB."""
    return "jmb"


@pytest.fixture
def outro_tenant_id() -> str:
    """Segundo tenant para testes de isolamento."""
    return "outro_tenant"


# ─────────────────────────────────────────────
# Fixtures de modelos de dados
# ─────────────────────────────────────────────


@pytest.fixture
def produto_id() -> UUID:
    """UUID fixo para uso nos testes."""
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def produto_bruto_fixture(tenant_id: str) -> ProdutoBruto:
    """Produto bruto simples para testes."""
    return ProdutoBruto(
        codigo_externo="SKU001",
        nome_bruto="SHAM HID NAT 300ML CX12",
        tenant_id=tenant_id,
        preco_padrao=Decimal("29.90"),
        categoria="Cabelos",
        descricao_bruta="Shampoo hidratante Natura 300ml caixa com 12 unidades",
        url_imagem="https://exemplo.com/img/sku001.jpg",
    )


@pytest.fixture
def produto_enriquecido_fixture(tenant_id: str) -> ProdutoEnriquecido:
    """Produto enriquecido (saída do EnricherAgent) para testes."""
    return ProdutoEnriquecido(
        codigo_externo="SKU001",
        tenant_id=tenant_id,
        nome="Shampoo Hidratante 300ml",
        marca="Natura",
        categoria="Cuidados com Cabelos",
        tags=["shampoo", "hidratante", "natura", "cabelos", "300ml"],
        texto_rag=(
            "Shampoo hidratante 300ml da marca Natura. Produto para cuidados com cabelos. "
            "Ideal para hidratação intensa. Fórmula com ativos naturais. "
            "Embalagem de 300ml. Vendido em caixa com 12 unidades. "
            "Sinônimos: xampu, xampoo, shampoo, hidratante capilar."
        ),
        meta_agente={
            "unidade": "ml",
            "quantidade": 300,
            "variante": None,
            "grupo_produto": "shampoo",
        },
    )


@pytest.fixture
def produto_fixture(tenant_id: str, produto_id: UUID) -> Produto:
    """Produto completo (registro do BD) para testes."""
    return Produto(
        id=produto_id,
        tenant_id=tenant_id,
        codigo_externo="SKU001",
        nome_bruto="SHAM HID NAT 300ML CX12",
        nome="Shampoo Hidratante 300ml",
        marca="Natura",
        categoria="Cuidados com Cabelos",
        tags=["shampoo", "hidratante", "natura"],
        texto_rag="Shampoo hidratante 300ml da marca Natura para cuidados com cabelos.",
        meta_agente={"unidade": "ml", "quantidade": 300},
        preco_padrao=Decimal("29.90"),
        url_imagem="https://exemplo.com/img/sku001.jpg",
        status_enriquecimento=StatusEnriquecimento.ENRIQUECIDO,
        criado_em=datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def produto_pendente_fixture(tenant_id: str, produto_id: UUID) -> Produto:
    """Produto com status PENDENTE (sem enriquecimento) para testes."""
    return Produto(
        id=produto_id,
        tenant_id=tenant_id,
        codigo_externo="SKU001",
        nome_bruto="SHAM HID NAT 300ML CX12",
        status_enriquecimento=StatusEnriquecimento.PENDENTE,
        criado_em=datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc),
    )


# ─────────────────────────────────────────────
# Fixtures de mocks
# ─────────────────────────────────────────────


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Mock do CatalogRepo para testes unitários de Service."""
    from src.catalog.repo import CatalogRepo

    mock = AsyncMock(spec=CatalogRepo)
    return mock


@pytest.fixture
def mock_enricher() -> AsyncMock:
    """Mock do EnricherProtocol para testes unitários de Service."""
    mock = AsyncMock(spec=EnricherProtocol)
    return mock


@pytest.fixture
def mock_openai_client(produto_enriquecido_fixture: ProdutoEnriquecido) -> MagicMock:
    """Mock do AsyncOpenAI client para testes unitários.

    Retorna embedding sintético de 1536 dimensões.
    """
    client = MagicMock()
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.1] * 1536)]
    client.embeddings.create = AsyncMock(return_value=embedding_response)
    return client
