"""Testes unitários do CatalogService.

Todos os testes são @pytest.mark.unit — sem I/O externo.
Todos os externos (repo, enricher, openai) são mockados via AsyncMock.
"""

from __future__ import annotations

import io
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

import pandas as pd
import pytest

from src.catalog.service import CatalogService
from src.catalog.types import (
    ExcelUploadResult,
    Produto,
    ProdutoBruto,
    ProdutoEnriquecido,
    ResultadoBusca,
    StatusEnriquecimento,
)


# ─────────────────────────────────────────────
# Fixtures de CatalogService
# ─────────────────────────────────────────────


@pytest.fixture
def service(
    mock_repo: AsyncMock,
    mock_enricher: AsyncMock,
    mock_openai_client: MagicMock,
) -> CatalogService:
    """CatalogService com todas as dependências mockadas."""
    return CatalogService(
        repo=mock_repo,
        enricher=mock_enricher,
        embedding_client=mock_openai_client,
    )


# ─────────────────────────────────────────────
# salvar_produto_bruto
# ─────────────────────────────────────────────


@pytest.mark.skip(reason="salvar_produto_bruto removido em Sprint 10 E19 — pipeline enricher depreciado")
@pytest.mark.unit
async def test_salvar_produto_bruto_chama_repo(
    service: CatalogService,
    mock_repo: AsyncMock,
    produto_bruto_fixture: ProdutoBruto,
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """salvar_produto_bruto deve delegar ao repo e retornar produto."""
    mock_repo.upsert_produto_bruto.return_value = produto_fixture

    result = await service.salvar_produto_bruto(tenant_id, produto_bruto_fixture)

    mock_repo.upsert_produto_bruto.assert_called_once_with(tenant_id, produto_bruto_fixture)
    assert result.codigo_externo == "SKU001"


# ─────────────────────────────────────────────
# enriquecer_produto
# ─────────────────────────────────────────────


@pytest.mark.skip(reason="enriquecer_produto removido em Sprint 10 E19")
@pytest.mark.unit
async def test_enriquecer_produto_fluxo_completo(
    service: CatalogService,
    mock_repo: AsyncMock,
    mock_enricher: AsyncMock,
    produto_fixture: Produto,
    produto_enriquecido_fixture: ProdutoEnriquecido,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """enriquecer_produto deve: buscar produto, chamar enricher, salvar e gerar embedding."""
    mock_repo.get_produto.return_value = produto_fixture
    mock_enricher.enriquecer.return_value = produto_enriquecido_fixture
    mock_repo.update_produto_enriquecido.return_value = produto_fixture
    # gerar_e_salvar_embedding fará outro get_produto
    mock_repo.get_produto.side_effect = [produto_fixture, produto_fixture]

    result = await service.enriquecer_produto(tenant_id, produto_id)

    mock_enricher.enriquecer.assert_called_once()
    mock_repo.update_produto_enriquecido.assert_called_once()
    mock_repo.update_embedding.assert_called_once()
    assert result is not None


@pytest.mark.skip(reason="enriquecer_produto removido em Sprint 10 E19")
@pytest.mark.unit
async def test_enriquecer_produto_nao_encontrado_levanta_valor_erro(
    service: CatalogService,
    mock_repo: AsyncMock,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """enriquecer_produto deve levantar ValueError se produto não existir."""
    mock_repo.get_produto.return_value = None

    with pytest.raises(ValueError, match="não encontrado"):
        await service.enriquecer_produto(tenant_id, produto_id)


# ─────────────────────────────────────────────
# buscar_semantico — inclui teste de isolamento de tenant (A3/A6)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_buscar_semantico_retorna_resultados(
    service: CatalogService,
    mock_repo: AsyncMock,
    produto_fixture: Produto,
    tenant_id: str,
) -> None:
    """buscar_semantico deve gerar embedding, chamar repo e retornar ResultadoBusca."""
    mock_repo.buscar_por_embedding.return_value = [(produto_fixture, 0.15)]

    resultados = await service.buscar_semantico(tenant_id, "shampoo hidratante")

    assert len(resultados) == 1
    assert isinstance(resultados[0], ResultadoBusca)
    assert resultados[0].score == pytest.approx(0.85, abs=1e-4)
    assert resultados[0].produto.codigo_externo == "SKU001"


@pytest.mark.unit
async def test_buscar_semantico_tenant_isolation(
    service: CatalogService,
    mock_repo: AsyncMock,
    produto_fixture: Produto,
    tenant_id: str,
    outro_tenant_id: str,
) -> None:
    """tenant_id nunca vaza entre chamadas consecutivas de tenants diferentes.

    Este teste é o critério A3 do sprint contract.
    """
    mock_repo.buscar_por_embedding.return_value = [(produto_fixture, 0.15)]

    await service.buscar_semantico(tenant_id, "shampoo")
    await service.buscar_semantico(outro_tenant_id, "creme")

    chamadas = mock_repo.buscar_por_embedding.call_args_list
    assert len(chamadas) == 2
    assert chamadas[0].kwargs["tenant_id"] == tenant_id
    assert chamadas[1].kwargs["tenant_id"] == outro_tenant_id
    assert chamadas[0].kwargs["tenant_id"] != chamadas[1].kwargs["tenant_id"]


@pytest.mark.unit
async def test_buscar_semantico_usa_embedding_correto(
    service: CatalogService,
    mock_repo: AsyncMock,
    mock_openai_client: MagicMock,
    tenant_id: str,
) -> None:
    """buscar_semantico deve passar o embedding gerado pelo OpenAI para o repo."""
    mock_repo.buscar_por_embedding.return_value = []

    await service.buscar_semantico(tenant_id, "qualquer query")

    mock_openai_client.embeddings.create.assert_called_once()
    chamada_repo = mock_repo.buscar_por_embedding.call_args
    assert chamada_repo.kwargs["embedding"] == [0.1] * 1536
    assert len(chamada_repo.kwargs["embedding"]) == 1536


# ─────────────────────────────────────────────
# gerar_e_salvar_embedding
# ─────────────────────────────────────────────


@pytest.mark.skip(reason="gerar_e_salvar_embedding removido em Sprint 10 E19")
@pytest.mark.unit
async def test_gerar_embedding_sem_texto_rag_nao_chama_openai(
    service: CatalogService,
    mock_repo: AsyncMock,
    mock_openai_client: MagicMock,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """Se produto não tem texto_rag, não deve chamar a API OpenAI."""
    from src.catalog.types import StatusEnriquecimento
    from datetime import datetime, timezone

    produto_sem_rag = Produto(
        id=produto_id,
        tenant_id=tenant_id,
        codigo_externo="SKU001",
        nome_bruto="Produto",
        texto_rag=None,
        status_enriquecimento=StatusEnriquecimento.PENDENTE,
        criado_em=datetime.now(timezone.utc),
        atualizado_em=datetime.now(timezone.utc),
    )
    mock_repo.get_produto.return_value = produto_sem_rag

    await service.gerar_e_salvar_embedding(tenant_id, produto_id)

    mock_openai_client.embeddings.create.assert_not_called()
    mock_repo.update_embedding.assert_not_called()


# ─────────────────────────────────────────────
# processar_excel_precos
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_processar_excel_precos_sucesso(
    service: CatalogService,
    mock_repo: AsyncMock,
    tenant_id: str,
) -> None:
    """processar_excel_precos deve processar fixture com 3 válidas + 1 inválida."""
    from pathlib import Path

    fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "precos_teste.xlsx"
    if not fixture_path.exists():
        pytest.skip("Fixture precos_teste.xlsx não encontrada")

    conteudo = fixture_path.read_bytes()
    resultado = await service.processar_excel_precos(tenant_id, conteudo)

    assert isinstance(resultado, ExcelUploadResult)
    assert resultado.linhas_processadas == 4  # 3 válidas + 1 inválida
    assert resultado.inseridos == 3
    assert len(resultado.erros) == 1


@pytest.mark.unit
async def test_processar_excel_precos_arquivo_invalido(
    service: CatalogService,
    tenant_id: str,
) -> None:
    """processar_excel_precos deve levantar ValueError para bytes inválidos."""
    with pytest.raises(ValueError, match="Excel inválido"):
        await service.processar_excel_precos(tenant_id, b"nao e excel")


@pytest.mark.unit
async def test_processar_excel_precos_commit_chamado(tenant_id: str) -> None:
    """M5: processar_excel_precos delega ao repo que chama session.commit()."""
    from src.catalog.repo import CatalogRepo

    # Cria Excel mínimo em memória com uma linha válida
    df = pd.DataFrame([{"codigo": "SKU001", "cnpj": "12345678000195", "preco": "10.50"}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    excel_bytes = buf.getvalue()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    catalog_repo = CatalogRepo(session_factory=mock_factory)
    catalog_service = CatalogService(repo=catalog_repo, enricher=None, embedding_client=None)  # type: ignore[arg-type]

    await catalog_service.processar_excel_precos(tenant_id, excel_bytes)

    mock_session.commit.assert_called()


# ─────────────────────────────────────────────
# aprovar_produto / rejeitar_produto
# ─────────────────────────────────────────────


@pytest.mark.skip(reason="aprovar_produto removido em Sprint 10 E19 — painel de revisão depreciado")
@pytest.mark.unit
async def test_aprovar_produto_muda_status_ativo(
    service: CatalogService,
    mock_repo: AsyncMock,
    produto_fixture: Produto,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """aprovar_produto deve chamar repo.update_status com ATIVO."""
    mock_repo.update_status.return_value = produto_fixture

    await service.aprovar_produto(tenant_id, produto_id)  # type: ignore[attr-defined]

    mock_repo.update_status.assert_called_once_with(
        tenant_id, produto_id, StatusEnriquecimento.ATIVO
    )


@pytest.mark.skip(reason="rejeitar_produto removido em Sprint 10 E19 — painel de revisão depreciado")
@pytest.mark.unit
async def test_rejeitar_produto_muda_status_inativo(
    service: CatalogService,
    mock_repo: AsyncMock,
    produto_fixture: Produto,
    tenant_id: str,
    produto_id: UUID,
) -> None:
    """rejeitar_produto deve chamar repo.update_status com INATIVO."""
    mock_repo.update_status.return_value = produto_fixture

    await service.rejeitar_produto(tenant_id, produto_id)  # type: ignore[attr-defined]

    mock_repo.update_status.assert_called_once_with(
        tenant_id, produto_id, StatusEnriquecimento.INATIVO
    )
