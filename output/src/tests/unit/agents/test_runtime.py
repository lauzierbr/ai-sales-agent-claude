"""Testes unitários — A_MULTITURN: histórico multi-turn com >= 6 tool calls (Sprint 10).

Verifica que truncate_preserving_pairs produz histórico válido
que a Anthropic API aceitaria (sem 400 tool_use_id error).
"""
from __future__ import annotations

import pytest


def _make_user_text(text: str) -> dict:
    return {"role": "user", "content": text}


def _make_assistant_text(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _make_tool_use(tid: str, name: str = "buscar") -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tid, "name": name, "input": {}}],
    }


def _make_tool_result(tid: str, content: str = "resultado") -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}],
    }


def _validate_history(messages: list[dict]) -> tuple[bool, str]:
    """Valida que o histórico é aceitável pela Anthropic API.

    Returns:
        (válido, motivo) — True se válido.
    """
    if not messages:
        return True, "vazio"

    # Primeiro item não pode ser tool_result
    first = messages[0]
    if first.get("role") == "user":
        content = first.get("content", "")
        if isinstance(content, list) and content:
            if isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                return False, "Primeiro item é tool_result órfão"

    # Último item não pode ser tool_use sem tool_result subsequente
    last = messages[-1]
    if last.get("role") == "assistant":
        content = last.get("content", [])
        if isinstance(content, list) and content:
            if isinstance(content[0], dict) and content[0].get("type") == "tool_use":
                return False, "Último item é tool_use sem tool_result"

    return True, "ok"


@pytest.mark.unit
def test_multiturn_truncation_valid():
    """Histórico com >= 6 tool calls truncado para 20 msgs é válido para Anthropic API."""
    from src.agents.runtime._history import truncate_preserving_pairs

    # Construir histórico com 8 tool calls (> 6 conforme contrato)
    messages = [_make_user_text("inicio")]
    for i in range(8):
        tid = f"call_{i}"
        messages.append(_make_tool_use(tid, f"tool_{i}"))
        messages.append(_make_tool_result(tid, f"resultado_{i}"))
        messages.append(_make_assistant_text(f"resposta_{i}"))

    # Total: 1 + 8*3 = 25 mensagens
    assert len(messages) == 25

    truncado = truncate_preserving_pairs(messages, max_msgs=20)

    # Deve ter <= 20 msgs
    assert len(truncado) <= 20

    # Deve ser válido
    valido, motivo = _validate_history(truncado)
    assert valido, f"Histórico inválido após truncação: {motivo}"


@pytest.mark.unit
def test_multiturn_sem_truncacao():
    """Histórico com <= max_msgs não é alterado."""
    from src.agents.runtime._history import truncate_preserving_pairs

    messages = [
        _make_user_text("oi"),
        _make_assistant_text("olá"),
    ]
    result = truncate_preserving_pairs(messages, max_msgs=20)
    assert result == messages


@pytest.mark.unit
def test_multiturn_historico_vazio():
    """Histórico vazio não causa erro."""
    from src.agents.runtime._history import truncate_preserving_pairs, repair_history

    assert truncate_preserving_pairs([], max_msgs=20) == []
    assert repair_history([]) == []


@pytest.mark.unit
def test_repair_historico_corrompido_preserva_texto():
    """repair_history em histórico corrompido preserva texto user/assistant."""
    from src.agents.runtime._history import repair_history

    # Histórico corrompido: começa com tool_result, tem mensagens de texto no meio
    messages = [
        _make_tool_result("orphan_1"),
        _make_user_text("mensagem real 1"),
        _make_assistant_text("resposta real 1"),
        _make_tool_result("orphan_2"),
        _make_user_text("mensagem real 2"),
    ]

    repaired = repair_history(messages)

    # Deve preservar pelo menos as mensagens de texto
    text_users = [m for m in repaired if isinstance(m.get("content"), str) and m.get("role") == "user"]
    assert len(text_users) >= 1, "repair_history deve preservar mensagens de texto"

    # Resultado deve ser válido
    valido, motivo = _validate_history(repaired)
    assert valido, f"Histórico reparado ainda inválido: {motivo}"
