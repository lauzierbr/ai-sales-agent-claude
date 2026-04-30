"""Wrapper Langfuse para chamadas Anthropic (B-30 / E3).

Implementa a Opção A do BUGS.md: context manager manual em torno de
`client.messages.create()` que registra um generation no Langfuse com
input_tokens e output_tokens reais.

Por que wrapper manual:
  - Não existe integração nativa Langfuse-Anthropic (existe para OpenAI).
  - `AsyncAnthropic()` puro é invisível ao Langfuse.
  - Este módulo é o único ponto de chamada — os 3 agentes importam daqui.

Camada: Service (observabilidade transversal — sem dependência de Repo/UI).
"""
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger()

# Importado sob demanda para evitar circularidade de módulos
# (observability não deve depender de agents.runtime na camada de módulo)
def _get_retry_fn():  # type: ignore[return]
    """Retorna call_with_overload_retry de forma lazy."""
    from src.agents.runtime._retry import call_with_overload_retry
    return call_with_overload_retry

# Exposto para mock nos testes
call_with_overload_retry = _get_retry_fn()

# Langfuse é opcional — se não configurado, chamadas passam direto.
_LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
_LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
_LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

_LANGFUSE_ENABLED = bool(_LANGFUSE_PUBLIC_KEY and _LANGFUSE_SECRET_KEY)

_langfuse_client: Any = None


def _get_langfuse() -> Any | None:
    """Retorna instância Langfuse (lazy singleton) ou None se não configurado."""
    global _langfuse_client
    if not _LANGFUSE_ENABLED:
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=_LANGFUSE_PUBLIC_KEY,
            secret_key=_LANGFUSE_SECRET_KEY,
            host=_LANGFUSE_HOST,
        )
        log.info("langfuse_inicializado", host=_LANGFUSE_HOST)
    except ImportError:
        log.warning("langfuse_nao_instalado")
        return None
    except Exception as exc:
        log.warning("langfuse_init_erro", error=str(exc))
        return None
    return _langfuse_client


async def call_anthropic_with_langfuse(
    client: Any,
    agent_name: str = "unknown",
    trace_id: str | None = None,
    session_id: str | None = None,
    **kwargs: Any,
) -> Any:
    """Chama `client.messages.create(**kwargs)` registrando generation no Langfuse.

    Sempre retorna a resposta Anthropic — Langfuse é melhor-esforço.
    Se Langfuse falhar, a chamada ao agente continua normalmente.
    Internamente usa `call_with_overload_retry` para retry em 529 overload.

    Args:
        client: instância de `anthropic.AsyncAnthropic`.
        agent_name: nome do agente para rastreabilidade (cliente/rep/gestor).
        trace_id: ID do trace Langfuse existente (opcional).
        session_id: ID de sessão para agrupar conversas (opcional).
        **kwargs: argumentos passados diretamente a `client.messages.create`.

    Returns:
        Resposta da Anthropic API.
    """
    lf = _get_langfuse()
    if not lf:
        # Langfuse não configurado — chamada com retry apenas
        return await call_with_overload_retry(
            client.messages.create,
            agent_name=agent_name,
            **kwargs,
        )

    generation = None
    _trace_obj = None
    # Última mensagem do usuário como resumo de input para o trace (evita payload gigante)
    _last_user_msg = ""
    try:
        msgs = kwargs.get("messages", [])
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content", "")
                _last_user_msg = c if isinstance(c, str) else str(c)[:300]
                break
    except Exception:
        pass

    try:
        # session_id precisa ir no TRACE, não na generation standalone.
        # input/output no trace aparece na UI de Sessions; generation filha tem detalhe.
        if session_id:
            _trace_obj = lf.trace(
                name=f"anthropic_{agent_name}",
                session_id=session_id,
                id=trace_id,
                input=_last_user_msg or None,
            )
            generation = _trace_obj.generation(
                name=f"anthropic_{agent_name}",
                model=kwargs.get("model", "unknown"),
                input=kwargs.get("messages", []),
            )
        else:
            generation = lf.generation(
                name=f"anthropic_{agent_name}",
                model=kwargs.get("model", "unknown"),
                input=kwargs.get("messages", []),
                trace_id=trace_id,
            )
    except Exception as exc:
        log.warning("langfuse_generation_create_erro", agent=agent_name, error=str(exc))

    try:
        response = await call_with_overload_retry(  # type: ignore[misc]
            client.messages.create,
            agent_name=agent_name,
            **kwargs,
        )
    except Exception:
        # Se a chamada Anthropic falhar, encerrar generation com erro e re-raise
        if generation is not None:
            try:
                generation.update(level="ERROR")
                generation.end()
            except Exception:
                pass
        raise

    # Atualizar generation com tokens reais
    if generation is not None:
        try:
            output_content = None
            output_text = None  # texto plano para o trace (mais legível na UI)
            if hasattr(response, "content"):
                try:
                    output_content = [b.model_dump() for b in response.content]
                    # Extrair texto das partes text para o trace
                    text_parts = [
                        b.get("text", "") for b in output_content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    output_text = " ".join(text_parts).strip() or None
                except Exception:
                    output_content = str(response.content)
                    output_text = output_content

            usage_data: dict[str, Any] = {}
            if hasattr(response, "usage") and response.usage is not None:
                usage_data = {
                    "input": getattr(response.usage, "input_tokens", 0),
                    "output": getattr(response.usage, "output_tokens", 0),
                }

            generation.update(
                output=output_content,
                usage=usage_data if usage_data else None,
            )
            generation.end()

            # Atualizar o trace com output legível — aparece na UI de Sessions
            if _trace_obj is not None and output_text:
                try:
                    _trace_obj.update(output=output_text)
                except Exception:
                    pass
        except Exception as exc:
            log.warning("langfuse_generation_update_erro", agent=agent_name, error=str(exc))

    return response
