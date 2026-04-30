"""Testes de regressão — B-26: truncação cega do histórico (Sprint 10, E1).

Verifica que truncate_preserving_pairs e repair_history:
- Nunca retornam tool_result órfão como primeiro item.
- Nunca terminam com tool_use sem tool_result subsequente.
- Preservam mensagens de texto na reparação.
"""
from __future__ import annotations

import pytest

from src.agents.runtime._history import repair_history, truncate_preserving_pairs


def _make_user_text(content: str) -> dict:
    return {"role": "user", "content": content}


def _make_assistant_text(content: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": content}]}


def _make_tool_use(tool_id: str, name: str) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": {}}],
    }


def _make_tool_result(tool_id: str, content: str = "ok") -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": content}],
    }


def _build_conversation_with_tools(n_tool_calls: int = 5) -> list[dict]:
    """Constrói histórico válido com N pares tool_use/tool_result + texto."""
    msgs = [_make_user_text("oi")]
    for i in range(n_tool_calls):
        tid = f"tool_{i}"
        msgs.append(_make_tool_use(tid, f"ferramenta_{i}"))
        msgs.append(_make_tool_result(tid, f"resultado_{i}"))
        msgs.append(_make_assistant_text(f"resposta_{i}"))
    return msgs


@pytest.mark.unit
def test_truncate_sem_orphan_no_inicio():
    """Histórico de 25 msgs truncado para 20 nunca começa com tool_result órfão."""
    msgs = _build_conversation_with_tools(n_tool_calls=6)  # 1 + 6*3 = 19 msgs
    # Adicionar mais para forçar truncação
    for i in range(6, 10):
        tid = f"tool_{i}"
        msgs.append(_make_tool_use(tid, f"ferramenta_{i}"))
        msgs.append(_make_tool_result(tid, f"resultado_{i}"))
        msgs.append(_make_assistant_text(f"resposta_{i}"))

    assert len(msgs) > 20

    truncado = truncate_preserving_pairs(msgs, max_msgs=20)

    # Nunca começa com tool_result
    if truncado:
        primeiro = truncado[0]
        if isinstance(primeiro.get("content"), list) and primeiro.get("role") == "user":
            items = primeiro["content"]
            if items and isinstance(items[0], dict):
                assert items[0].get("type") != "tool_result", (
                    "Histórico truncado começa com tool_result órfão"
                )


@pytest.mark.unit
def test_truncate_sem_tool_use_no_fim():
    """Histórico truncado não termina com tool_use sem tool_result subsequente."""
    msgs = _build_conversation_with_tools(n_tool_calls=7)

    truncado = truncate_preserving_pairs(msgs, max_msgs=10)

    if truncado:
        ultimo = truncado[-1]
        if isinstance(ultimo.get("content"), list) and ultimo.get("role") == "assistant":
            items = ultimo["content"]
            if items and isinstance(items[0], dict):
                assert items[0].get("type") != "tool_use", (
                    "Histórico truncado termina com tool_use sem tool_result"
                )


@pytest.mark.unit
def test_truncate_sem_alteracao_quando_menor_que_max():
    """Histórico menor que max_msgs retorna sem modificação."""
    msgs = _build_conversation_with_tools(n_tool_calls=2)
    original_len = len(msgs)
    truncado = truncate_preserving_pairs(msgs, max_msgs=50)
    assert truncado == msgs
    assert len(truncado) == original_len


@pytest.mark.unit
def test_repair_history_remove_orphan_tool_result():
    """repair_history remove tool_result órfão do início."""
    # Histórico corrompido: começa com tool_result sem tool_use anterior
    msgs = [
        _make_tool_result("orphan_tool", "resultado órfão"),
        _make_user_text("segunda mensagem"),
        _make_assistant_text("resposta"),
    ]

    repaired = repair_history(msgs)

    # Não deve começar com tool_result
    if repaired:
        primeiro = repaired[0]
        if isinstance(primeiro.get("content"), list) and primeiro.get("role") == "user":
            items = primeiro["content"]
            if items and isinstance(items[0], dict):
                assert items[0].get("type") != "tool_result"


@pytest.mark.unit
def test_repair_history_preserva_texto():
    """repair_history preserva mensagens de texto mesmo com pares inválidos."""
    msgs = [
        _make_tool_result("orphan", "resultado"),  # órfão
        _make_user_text("mensagem válida 1"),
        _make_assistant_text("resposta válida 1"),
        _make_user_text("mensagem válida 2"),
    ]

    repaired = repair_history(msgs)

    # Pelo menos as mensagens de texto devem ser preservadas
    text_msgs = [m for m in repaired if isinstance(m.get("content"), str)]
    assert len(text_msgs) >= 2


@pytest.mark.unit
def test_repair_history_retorna_vazio_em_caso_extremo():
    """repair_history retorna lista vazia como último recurso se nada é preservável."""
    # Histórico completamente inválido (só tool_results e tool_uses sem texto)
    msgs = [
        _make_tool_result("t1", "r1"),
        _make_tool_result("t2", "r2"),
        _make_tool_use("t3", "f3"),
    ]

    repaired = repair_history(msgs)
    # Pode ser vazio ou filtrado — só verifica que não levanta exceção
    assert isinstance(repaired, list)


@pytest.mark.unit
def test_truncate_preserva_pares_intactos():
    """Conversação com N=25 mensagens, truncada para 20, mantém histórico válido."""
    msgs = _build_conversation_with_tools(n_tool_calls=8)  # 1 + 8*3 = 25 msgs
    assert len(msgs) == 25

    truncado = truncate_preserving_pairs(msgs, max_msgs=20)

    # Resultado deve ter <= 20 msgs
    assert len(truncado) <= 20

    # Validar integridade: nenhum tool_result como primeiro item
    if truncado:
        first = truncado[0]
        content = first.get("content", "")
        if isinstance(content, list) and content:
            assert content[0].get("type") != "tool_result"

    # Validar que não termina com tool_use
    if truncado:
        last = truncado[-1]
        content = last.get("content", [])
        if isinstance(content, list) and content:
            assert content[0].get("type") != "tool_use"
