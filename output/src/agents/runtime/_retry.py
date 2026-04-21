"""Retry wrapper para chamadas à API Anthropic.

Camada Runtime: importa apenas stdlib e structlog.

Resolve TD-05 (retro Sprint 4): API Anthropic pode retornar 529
(overloaded_error) em picos de carga. Sem retry, o bot simplesmente não
responde. Este wrapper aplica exponential backoff (2s, 4s, 8s) em até
3 tentativas, apenas para erros 529/overloaded.

Outros erros (400 com tool_use_id, 401, 403, etc.) são re-raised
imediatamente para preservar o recovery path já existente em cada agente
(ex: limpeza de histórico Redis em 400 com tool_use_id orphan).
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Literal

import structlog

log = structlog.get_logger(__name__)

_OVERLOAD_DELAYS = (2.0, 4.0, 8.0)

AnthropicHealthState = Literal["ok", "degraded", "fail"]
_anthropic_health_state: AnthropicHealthState = "ok"


def get_anthropic_health() -> AnthropicHealthState:
    """Retorna o estado atual da integração Anthropic."""
    return _anthropic_health_state


def _set_anthropic_health(state: AnthropicHealthState) -> None:
    global _anthropic_health_state
    _anthropic_health_state = state


def _is_auth_or_quota(exc: BaseException) -> bool:
    """Identifica erros de auth/quota (401, 403, 402) — classificados como 'fail'."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403, 402):
        return True
    msg = str(exc).lower()
    return any(kw in msg for kw in ("authentication_error", "permission_error", "quota", "invalid api key"))


def _is_overload(exc: BaseException) -> bool:
    """Identifica erro 529 (overloaded_error) da API Anthropic.

    O SDK Anthropic pode levantar diferentes classes de exceção; cobrimos
    os três sinais possíveis:
      - atributo .status_code == 529
      - substring "overloaded_error" no str()
      - substring " 529 " no str()
    """
    if getattr(exc, "status_code", None) == 529:
        return True
    msg = str(exc).lower()
    if "overloaded_error" in msg or "overloaded" in msg:
        return True
    if " 529 " in f" {msg} ":
        return True
    return False


async def call_with_overload_retry(
    create_fn: Callable[..., Awaitable[Any]],
    *,
    agent_name: str,
    **kwargs: Any,
) -> Any:
    """Chama a API Anthropic com retry em overload (529).

    Args:
        create_fn: função assíncrona (tipicamente `client.messages.create`).
        agent_name: identificador para log ("cliente", "rep", "gestor").
        **kwargs: argumentos passados direto para create_fn.

    Returns:
        Resposta da API na primeira tentativa bem-sucedida.

    Raises:
        Propaga a exceção original se todas as tentativas falharem,
        ou se for erro diferente de overload (que é re-raise imediato).
    """
    last_exc: BaseException | None = None
    for attempt, delay in enumerate((0.0, *_OVERLOAD_DELAYS), start=1):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            result = await create_fn(**kwargs)
            _set_anthropic_health("ok")
            return result
        except Exception as exc:
            if _is_auth_or_quota(exc):
                _set_anthropic_health("fail")
                raise
            if not _is_overload(exc):
                raise
            last_exc = exc
            _set_anthropic_health("degraded")
            log.warning(
                "agent_anthropic_overload_retry",
                agent=agent_name,
                attempt=attempt,
                max_attempts=len(_OVERLOAD_DELAYS) + 1,
                next_delay=_OVERLOAD_DELAYS[attempt - 1] if attempt <= len(_OVERLOAD_DELAYS) else None,
                error=str(exc)[:120],
            )
    log.error(
        "agent_anthropic_overload_exhausted",
        agent=agent_name,
        attempts=len(_OVERLOAD_DELAYS) + 1,
    )
    assert last_exc is not None
    raise last_exc
