"""Helper compartilhado para gerenciamento de histórico de conversa.

Camada Runtime — usado pelos 3 agentes (AgentCliente, AgentRep, AgentGestor).
Zero duplicação: E1 (B-26) — truncação preservando pares tool_use/tool_result.

Regras de integridade da Anthropic API:
- Nenhum `tool_result` órfão como primeiro item da lista.
- Nenhum `tool_use` no último item sem `tool_result` imediato na mensagem seguinte.
- Pares tool_use/tool_result devem estar completos.
"""
from __future__ import annotations

import structlog
from typing import Any

log = structlog.get_logger()


def _is_tool_result_msg(msg: dict[str, Any]) -> bool:
    """Retorna True se a mensagem começa com um tool_result (role=user, content=[{type:tool_result}])."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content", "")
    if not isinstance(content, list):
        return False
    if len(content) > 0 and isinstance(content[0], dict):
        return content[0].get("type") == "tool_result"
    return False


def _is_tool_use_msg(msg: dict[str, Any]) -> bool:
    """Retorna True se a mensagem contém tool_use sem tool_result seguinte."""
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content", [])
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        for b in content
    )


def truncate_preserving_pairs(
    messages: list[dict[str, Any]],
    max_msgs: int,
) -> list[dict[str, Any]]:
    """Trunca o histórico preservando a integridade de pares tool_use/tool_result.

    Nunca retorna:
    - `tool_result` órfão como primeiro item.
    - `tool_use` no último item sem `tool_result` imediato após.

    Args:
        messages: lista completa de mensagens da conversa.
        max_msgs: número máximo de mensagens a manter.

    Returns:
        Sub-lista válida para envio à Anthropic API.
    """
    if len(messages) <= max_msgs:
        return messages

    # Slice candidato inicial
    trimmed = messages[-max_msgs:]

    # Corrigir início: remover tool_result órfão no começo
    while trimmed and _is_tool_result_msg(trimmed[0]):
        trimmed = trimmed[1:]

    # Corrigir final: remover tool_use sem tool_result
    while trimmed and _is_tool_use_msg(trimmed[-1]):
        trimmed = trimmed[:-1]
        # Remover também o tool_result que viria após (se o tool_use foi removido,
        # os tool_results correspondentes no próximo item também ficam órfãos)

    # Verificação final: se o último item for role=user com tool_result,
    # mas o item anterior não tiver tool_use correspondente, remover
    if len(trimmed) >= 2:
        last = trimmed[-1]
        prev = trimmed[-2]
        if _is_tool_result_msg(last) and not _is_tool_use_msg(prev):
            trimmed = trimmed[:-1]

    return trimmed


def repair_history(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tenta reparar histórico corrompido de forma não-destrutiva.

    Estratégia (em ordem de preferência):
    1. Remover pares tool_use/tool_result órfãos do início.
    2. Se ainda inválido, manter apenas mensagens de texto (user/assistant text-only).
    3. Se ainda inválido, retornar lista vazia como último recurso (loga ERROR).

    Args:
        messages: histórico possivelmente corrompido.

    Returns:
        Histórico reparado, mantendo o máximo de contexto possível.
    """
    # Passo 1: remover tool_result órfão no início
    repaired = list(messages)
    iterations = 0
    while repaired and _is_tool_result_msg(repaired[0]) and iterations < 20:
        repaired = repaired[1:]
        iterations += 1

    # Passo 2: remover tool_use sem tool_result no final
    while repaired and _is_tool_use_msg(repaired[-1]):
        repaired = repaired[:-1]

    # Verificar se ainda parece corrompido — tentar manter apenas text-only
    has_orphan = any(
        i == 0 and _is_tool_result_msg(msg)
        for i, msg in enumerate(repaired)
    )
    if has_orphan or (repaired and _is_tool_use_msg(repaired[-1])):
        # Passo 3: filtrar apenas mensagens de texto simples
        text_only = [
            m for m in repaired
            if (
                isinstance(m.get("content"), str)
                or (
                    isinstance(m.get("content"), list)
                    and all(
                        isinstance(b, dict) and b.get("type") == "text"
                        for b in m.get("content", [])
                        if isinstance(b, dict)
                    )
                )
            )
        ]
        if text_only:
            log.warning(
                "history_repair_fallback_text_only",
                original_len=len(messages),
                repaired_len=len(text_only),
            )
            return text_only
        else:
            log.error(
                "history_repair_fallback_empty",
                original_len=len(messages),
                reason="nenhuma mensagem de texto preservável",
            )
            return []

    preserved_texts = sum(
        1 for m in repaired
        if isinstance(m.get("content"), str)
        or (isinstance(m.get("content"), list) and any(
            isinstance(b, dict) and b.get("type") == "text"
            for b in m.get("content", [])
        ))
    )
    log.info(
        "history_repair_ok",
        original_len=len(messages),
        repaired_len=len(repaired),
        text_messages_preserved=preserved_texts,
    )
    return repaired
