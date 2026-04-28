"""Regression tests for Sprint 9 bugs B-13 and E0-B tool cleanup.

E0-B test-first: these tests FAIL before the fixes are applied, and PASS after.
B-13: EAN search with query[-6:] suffix match.
E0-B: tools clientes_inativos (antiga) and relatorio_representantes removed.

Markers: @pytest.mark.regression — runs with unit tests in the container.
"""

from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────
# B-13: EAN busca com query[-6:] — catalog/repo.py + agentes
# ─────────────────────────────────────────────────────────────


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b13_ean_completo_retorna_produto() -> None:
    """B-13: busca por EAN completo (13 dígitos) retorna produto via query[-6:].

    Simula: produto com codigo_externo='148571', query='7898923148571'.
    O repo/service deve tentar query[-6:] = '148571' e encontrar o produto.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from decimal import Decimal
    from datetime import datetime, timezone
    from uuid import UUID

    from src.catalog.types import Produto, ResultadoBusca, StatusEnriquecimento

    produto_mock = Produto(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id="jmb",
        codigo_externo="148571",
        nome_bruto="SHAMPOO HIDRATANTE 300ML",
        nome="Shampoo Hidratante 300ml",
        status_enriquecimento=StatusEnriquecimento.ATIVO,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    mock_repo = AsyncMock()
    # Primeiro lookup com codigo completo retorna None
    # Segundo lookup com query[-6:] retorna produto
    mock_repo.get_produto_por_codigo = AsyncMock(
        side_effect=[None, produto_mock]
    )

    from src.catalog.service import CatalogService
    from unittest.mock import MagicMock

    mock_embedding_client = MagicMock()
    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding_client,
    )

    query = "7898923148571"  # EAN completo de 13 dígitos
    resultado = await service.get_por_codigo(tenant_id="jmb", codigo_externo=query)

    # Deve ter tentado com o sufixo [-6:] = '148571' e encontrado
    assert resultado is not None, (
        "B-13 REGRESSION: busca por EAN completo '7898923148571' deve retornar produto "
        "com codigo_externo='148571'. Fix: adicionar fallback query[-6:] em "
        "catalog/service.py quando query.isdigit() e len(query) > 6."
    )
    assert resultado.produto.codigo_externo == "148571"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b13_ean_curto_retorna_produto() -> None:
    """B-13: busca por código curto (<=6 dígitos) usa lookup direto sem truncar.

    Produto com codigo_externo='148571', query='148571'.
    Não deve aplicar query[-6:] — o código já é curto.
    """
    from unittest.mock import AsyncMock, MagicMock
    from decimal import Decimal
    from datetime import datetime, timezone
    from uuid import UUID

    from src.catalog.types import Produto, ResultadoBusca, StatusEnriquecimento

    produto_mock = Produto(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        tenant_id="jmb",
        codigo_externo="148571",
        nome_bruto="SHAMPOO HIDRATANTE 300ML",
        nome="Shampoo Hidratante 300ml",
        status_enriquecimento=StatusEnriquecimento.ATIVO,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    mock_repo = AsyncMock()
    mock_repo.get_produto_por_codigo = AsyncMock(return_value=produto_mock)

    from src.catalog.service import CatalogService

    mock_embedding_client = MagicMock()
    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding_client,
    )

    query = "148571"  # código curto — 6 dígitos
    resultado = await service.get_por_codigo(tenant_id="jmb", codigo_externo=query)

    assert resultado is not None, (
        "B-13: busca por código curto '148571' deve retornar produto diretamente."
    )
    assert resultado.produto.codigo_externo == "148571"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b13_busca_textual_nao_afetada() -> None:
    """B-13: busca textual ('shampoo hidratante') NÃO passa pelo branch EAN.

    Garante que a lógica de query[-6:] só é ativada quando query.isdigit() == True.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from datetime import datetime, timezone
    from uuid import UUID

    from src.catalog.types import Produto, ResultadoBusca, StatusEnriquecimento

    produto_mock = Produto(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        tenant_id="jmb",
        codigo_externo="SKU001",
        nome_bruto="SHAMPOO HID 300ML",
        nome="Shampoo Hidratante 300ml",
        status_enriquecimento=StatusEnriquecimento.ATIVO,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        atualizado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    mock_repo = AsyncMock()
    mock_repo.get_produto_por_codigo = AsyncMock(return_value=None)
    mock_repo.buscar_por_embedding = AsyncMock(return_value=[(produto_mock, 0.1)])

    mock_embedding_client = MagicMock()
    embedding_resp = MagicMock()
    embedding_resp.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_embedding_client.embeddings.create = AsyncMock(return_value=embedding_resp)

    from src.catalog.service import CatalogService

    service = CatalogService(
        repo=mock_repo,
        enricher=None,  # type: ignore[arg-type]
        embedding_client=mock_embedding_client,
    )

    # busca textual — NÃO é só dígitos, portanto NÃO deve truncar
    query = "shampoo hidratante"
    resultados = await service.buscar_semantico(tenant_id="jmb", query=query, limit=5)

    # get_produto_por_codigo NÃO deve ter sido chamado (não é query de código)
    mock_repo.get_produto_por_codigo.assert_not_called(), (
        "B-13: busca textual NÃO deve chamar get_produto_por_codigo. "
        "O branch EAN só deve ser ativado quando query.isdigit() == True."
    )
    assert len(resultados) == 1


# ─────────────────────────────────────────────────────────────
# E0-B: tools antigas removidas do AgentGestor
# ─────────────────────────────────────────────────────────────


@pytest.mark.regression
def test_e0b_tool_clientes_inativos_antiga_removida() -> None:
    """E0-B: tool 'clientes_inativos' baseada em clientes_b2b/pedidos foi removida.

    Após a remoção, só deve existir a versão renomeada de 'clientes_inativos_efos'
    para 'clientes_inativos' (baseada em commerce_accounts_b2b).

    Verifica que a implementação de _clientes_inativos NÃO chama
    RelatorioRepo.clientes_inativos (que usa tabela pedidos).
    """
    import inspect
    from src.agents.runtime.agent_gestor import AgentGestor, _TOOLS

    # A tool 'clientes_inativos' deve existir (renomeada de efos)
    tool_names = [t["name"] for t in _TOOLS]
    assert "clientes_inativos" in tool_names, (
        "E0-B: tool 'clientes_inativos' deve existir no AgentGestor "
        "(renomeada de clientes_inativos_efos)."
    )

    # A tool 'clientes_inativos_efos' (com sufixo) NÃO deve existir mais
    assert "clientes_inativos_efos" not in tool_names, (
        "E0-B REGRESSION: tool 'clientes_inativos_efos' ainda existe em _TOOLS. "
        "Fix: remover clientes_inativos_efos e renomear para clientes_inativos."
    )

    # Verificar que o método _clientes_inativos chama CommerceRepo, não RelatorioRepo
    source = inspect.getsource(AgentGestor._clientes_inativos)
    assert "commerce_repo" in source or "CommerceRepo" in source or "listar_clientes_inativos" in source, (
        "E0-B: _clientes_inativos deve usar CommerceRepo (dados EFOS), "
        "não RelatorioRepo (tabela pedidos)."
    )


@pytest.mark.regression
def test_e0b_tool_relatorio_representantes_removida() -> None:
    """E0-B: tool 'relatorio_representantes' (baseada em tabela pedidos) foi removida.

    A tool EFOS 'relatorio_vendas_representante_efos' deve ser mantida.
    """
    from src.agents.runtime.agent_gestor import _TOOLS

    tool_names = [t["name"] for t in _TOOLS]

    assert "relatorio_representantes" not in tool_names, (
        "E0-B REGRESSION: tool 'relatorio_representantes' ainda existe em _TOOLS. "
        "Fix: remover esta tool da lista _TOOLS do AgentGestor."
    )

    # A tool EFOS deve permanecer
    assert "relatorio_vendas_representante_efos" in tool_names, (
        "E0-B: tool 'relatorio_vendas_representante_efos' deve continuar existindo."
    )
