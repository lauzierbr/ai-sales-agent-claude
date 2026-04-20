"""P5 — Channel format lint: bloqueia tabelas markdown em saídas WhatsApp.

Sprint 4 descobriu em homologação que o bot gerava `| col | col |` no
WhatsApp, que renderiza como texto bruto e quebra o layout. O fix foi
adicionar `_WHATSAPP_FORMATTING` aos system prompts dos 3 agentes, com
a instrução explícita "NUNCA use tabelas markdown".

Esses testes garantem que a instrução não é acidentalmente removida e
expõem um helper reutilizável para testes VCR/staging futuros.
"""

from __future__ import annotations

import re

import pytest

from src.agents.config import (
    AgentClienteConfig,
    AgentGestorConfig,
    AgentRepConfig,
    _WHATSAPP_FORMATTING,
)

# Regex: 3+ pipes na mesma linha indica tabela markdown
# (duas células + bordas = mínimo 3 pipes).
_PIPE_TABLE_RE = re.compile(r"^[^\n]*\|[^|\n]*\|[^|\n]*\|", re.MULTILINE)


def contains_markdown_pipe_table(text: str) -> bool:
    """Detecta tabela markdown com 3+ pipes numa mesma linha.

    Helper exportado para uso em testes staging/VCR que verifiquem saídas
    reais do modelo.
    """
    return bool(_PIPE_TABLE_RE.search(text))


@pytest.mark.unit
def test_whatsapp_formatting_block_forbids_pipe_tables() -> None:
    """O bloco canônico de formatação WhatsApp proíbe tabelas explicitamente."""
    assert "NUNCA" in _WHATSAPP_FORMATTING
    assert "tabelas markdown" in _WHATSAPP_FORMATTING
    assert "|" in _WHATSAPP_FORMATTING  # cita o caractere


@pytest.mark.unit
@pytest.mark.parametrize(
    "config_cls,nome",
    [
        (AgentClienteConfig, "cliente"),
        (AgentRepConfig, "rep"),
        (AgentGestorConfig, "gestor"),
    ],
)
def test_system_prompt_includes_whatsapp_formatting_block(
    config_cls: type, nome: str
) -> None:
    """Cada agente tem o bloco _WHATSAPP_FORMATTING no system_prompt_template.

    Se alguém remover o bloco por engano, este teste falha e o PR fica
    barulhento.
    """
    cfg = config_cls()
    prompt = cfg.system_prompt_template
    assert _WHATSAPP_FORMATTING in prompt, (
        f"AgentCfg {nome}: system_prompt_template não inclui bloco "
        "_WHATSAPP_FORMATTING — tabelas markdown podem reaparecer"
    )


@pytest.mark.unit
def test_pipe_table_detector_positive() -> None:
    """Helper flagra um exemplo típico de tabela markdown."""
    tabela = (
        "Veja os pedidos:\n"
        "| Cliente | Total | Status |\n"
        "|---------|-------|--------|\n"
        "| Muzel   | R$100 | pend   |\n"
    )
    assert contains_markdown_pipe_table(tabela)


@pytest.mark.unit
def test_pipe_table_detector_negative_single_pipe() -> None:
    """Helper NÃO flagra uso legítimo de pipe (ex: 'GMV | R$')."""
    ok = (
        "*Cliente Muzel*\n"
        "• Pedidos: 5  |  GMV: R$ 1.078,64\n"
        "• Status: ativo\n"
    )
    assert not contains_markdown_pipe_table(ok)


@pytest.mark.unit
def test_pipe_table_detector_negative_no_pipes() -> None:
    """Helper devolve False em texto WhatsApp bem formatado."""
    ok = (
        "*Pedido #ABC123*\n"
        "• Cliente: LZ Muzel\n"
        "• Total: R$ 1.078,64\n"
        "• Status: pendente\n"
    )
    assert not contains_markdown_pipe_table(ok)
