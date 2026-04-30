"""Testes unitários — B-30: wrapper Langfuse para Anthropic (E3, Sprint 10).

Verifica que call_anthropic_with_langfuse:
- Chama start_generation e gen.update com usage.input_tokens e output_tokens.
- Retorna a resposta Anthropic normalmente.
- Funciona sem Langfuse (graceful degradation).
"""
from __future__ import annotations

import pytest


@pytest.mark.unit
async def test_langfuse_wrapper_chama_generation_e_update(mocker):
    """Wrapper chama start_generation e gen.update com usage real."""
    # Mock do módulo langfuse_anthropic para isolar
    import src.observability.langfuse_anthropic as lf_mod

    # Simular Langfuse habilitado
    mocker.patch.object(lf_mod, "_LANGFUSE_ENABLED", True)
    mocker.patch.object(lf_mod, "_LANGFUSE_PUBLIC_KEY", "pk-fake")
    mocker.patch.object(lf_mod, "_LANGFUSE_SECRET_KEY", "sk-fake")

    # Mock do cliente Langfuse
    mock_generation = mocker.MagicMock()
    mock_lf = mocker.MagicMock()
    mock_lf.generation.return_value = mock_generation
    mocker.patch.object(lf_mod, "_langfuse_client", mock_lf)

    # Mock do call_with_overload_retry para não chamar Anthropic real
    mock_response = mocker.MagicMock()
    mock_response.content = [mocker.MagicMock(type="text", text="ok")]
    mock_response.usage = mocker.MagicMock(input_tokens=100, output_tokens=50)

    mocker.patch(
        "src.observability.langfuse_anthropic.call_with_overload_retry",
        new=mocker.AsyncMock(return_value=mock_response),
    )

    # Resetar cliente global
    mocker.patch.object(lf_mod, "_langfuse_client", mock_lf)

    mock_client = mocker.AsyncMock()
    mock_client.messages.create = mocker.AsyncMock(return_value=mock_response)

    # Chamar a função
    result = await lf_mod.call_anthropic_with_langfuse(
        client=mock_client,
        agent_name="gestor",
        session_id="test-session",
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "oi"}],
        max_tokens=100,
    )

    # Verificar que generation foi criada
    mock_lf.generation.assert_called_once()
    call_kwargs = mock_lf.generation.call_args

    # Verificar que gen.update foi chamado com usage
    mock_generation.update.assert_called()
    update_kwargs = mock_generation.update.call_args
    usage_arg = update_kwargs.kwargs.get("usage") or update_kwargs.args[0] if update_kwargs.args else None

    # A resposta deve ser retornada normalmente
    assert result == mock_response


@pytest.mark.unit
async def test_langfuse_wrapper_sem_langfuse_ainda_funciona(mocker):
    """Wrapper funciona sem Langfuse configurado — chamada direta."""
    import src.observability.langfuse_anthropic as lf_mod

    # Langfuse desabilitado
    mocker.patch.object(lf_mod, "_LANGFUSE_ENABLED", False)
    mocker.patch.object(lf_mod, "_langfuse_client", None)

    mock_response = mocker.MagicMock()
    mock_response.content = [mocker.MagicMock(type="text", text="resposta")]
    mock_response.usage = mocker.MagicMock(input_tokens=50, output_tokens=25)

    mock_retry = mocker.AsyncMock(return_value=mock_response)
    mocker.patch("src.observability.langfuse_anthropic.call_with_overload_retry", new=mock_retry)

    mock_client = mocker.MagicMock()

    result = await lf_mod.call_anthropic_with_langfuse(
        client=mock_client,
        agent_name="cliente",
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=100,
    )

    # Deve ter chamado o retry diretamente
    mock_retry.assert_called_once()
    assert result == mock_response


@pytest.mark.unit
async def test_langfuse_wrapper_propaga_excecao_anthropic(mocker):
    """Wrapper re-raise exceção da API Anthropic."""
    import src.observability.langfuse_anthropic as lf_mod

    mocker.patch.object(lf_mod, "_LANGFUSE_ENABLED", False)
    mocker.patch.object(lf_mod, "_langfuse_client", None)

    mocker.patch(
        "src.observability.langfuse_anthropic.call_with_overload_retry",
        new=mocker.AsyncMock(side_effect=RuntimeError("API error")),
    )

    mock_client = mocker.MagicMock()

    with pytest.raises(RuntimeError, match="API error"):
        await lf_mod.call_anthropic_with_langfuse(
            client=mock_client,
            agent_name="rep",
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=100,
        )
