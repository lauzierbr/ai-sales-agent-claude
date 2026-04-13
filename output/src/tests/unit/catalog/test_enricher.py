"""Testes unitários do EnricherAgent (Claude Haiku).

Anthropic SDK é mockado — sem chamadas reais à API.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock

from src.catalog.types import ProdutoBruto, ProdutoEnriquecido


RESPOSTA_HAIKU_VALIDA = json.dumps({
    "nome": "Shampoo Hidratante 300ml",
    "marca": "Natura",
    "categoria": "Cuidados com Cabelos",
    "tags": ["shampoo", "hidratante", "natura", "cabelos", "300ml"],
    "texto_rag": "Shampoo hidratante 300ml da marca Natura. Ideal para hidratação.",
    "meta_agente": {
        "unidade": "ml",
        "quantidade": 300,
        "variante": None,
        "grupo_produto": "shampoo",
    },
}, ensure_ascii=False)


@pytest.mark.unit
async def test_enriquecer_retorna_produto_enriquecido(
    produto_bruto_fixture: ProdutoBruto,
) -> None:
    """enriquecer deve retornar ProdutoEnriquecido quando Haiku retorna JSON válido."""
    with patch("src.catalog.runtime.enricher.AsyncAnthropic") as mock_anthropic_cls:
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [TextBlock(type="text", text=RESPOSTA_HAIKU_VALIDA)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            from src.catalog.runtime.enricher import EnricherAgent
            enricher = EnricherAgent()
            resultado = await enricher.enriquecer(produto_bruto_fixture)

    assert isinstance(resultado, ProdutoEnriquecido)
    assert resultado.nome == "Shampoo Hidratante 300ml"
    assert resultado.marca == "Natura"
    assert len(resultado.tags) == 5
    assert resultado.texto_rag != ""
    assert resultado.codigo_externo == produto_bruto_fixture.codigo_externo
    assert resultado.tenant_id == produto_bruto_fixture.tenant_id


@pytest.mark.unit
async def test_enriquecer_remove_markdown_do_json(
    produto_bruto_fixture: ProdutoBruto,
) -> None:
    """enriquecer deve remover bloco ```json se o Haiku incluir markdown."""
    resposta_com_markdown = f"```json\n{RESPOSTA_HAIKU_VALIDA}\n```"

    with patch("src.catalog.runtime.enricher.AsyncAnthropic") as mock_anthropic_cls:
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [TextBlock(type="text", text=resposta_com_markdown)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            from src.catalog.runtime.enricher import EnricherAgent
            enricher = EnricherAgent()
            # Substituímos o _client pelo mock criado acima
            enricher._client = mock_client  # type: ignore[assignment]
            resultado = await enricher.enriquecer(produto_bruto_fixture)

    assert resultado.nome == "Shampoo Hidratante 300ml"


@pytest.mark.unit
async def test_enriquecer_json_invalido_levanta_value_error(
    produto_bruto_fixture: ProdutoBruto,
) -> None:
    """enriquecer deve levantar ValueError se Haiku retornar JSON inválido."""
    with patch("src.catalog.runtime.enricher.AsyncAnthropic") as mock_anthropic_cls:
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [TextBlock(type="text", text="isso nao e json")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            from src.catalog.runtime.enricher import EnricherAgent
            enricher = EnricherAgent()

            with pytest.raises(ValueError, match="JSON inválido"):
                await enricher.enriquecer(produto_bruto_fixture)


@pytest.mark.unit
async def test_enricher_sem_api_key_levanta_value_error() -> None:
    """EnricherAgent sem ANTHROPIC_API_KEY deve levantar ValueError na inicialização."""
    with patch.dict("os.environ", {}, clear=True):
        # Remove ANTHROPIC_API_KEY do ambiente
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            from src.catalog.runtime.enricher import EnricherAgent
            EnricherAgent()
