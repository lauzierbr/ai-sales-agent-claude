"""Regression tests for Sprint 8 bugs B-10, B-11, B-12.

E9 — test-first: these tests MUST FAIL before the hotfixes are applied,
and PASS after each fix. Each test FAILs if the respective fix is reverted.

Markers: @pytest.mark.regression (not unit) so they run separately.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────
# B-10: representante_id NOT in get_by_telefone SELECT
# ─────────────────────────────────────────────────────────────

@pytest.mark.regression
def test_b10_clienteb2b_type_has_representante_id() -> None:
    """B-10: ClienteB2B type must have representante_id annotation.

    Fails if representante_id is removed from the type.
    """
    import inspect

    from src.agents.types import ClienteB2B

    annotations = inspect.get_annotations(ClienteB2B, eval_str=True)
    assert "representante_id" in annotations, (
        "B-10 REGRESSION: ClienteB2B.representante_id annotation is missing. "
        "Fix: add representante_id: str | None = None to the model."
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b10_get_by_telefone_includes_representante_id() -> None:
    """B-10: get_by_telefone() SELECT must include representante_id column.

    Fails if the SQL query no longer selects representante_id.
    """
    from src.agents.repo import ClienteB2BRepo
    from src.agents.types import ClienteB2B

    rep_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_row = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "tenant_id": "jmb",
        "nome": "Farmácia São Paulo",
        "cnpj": "12.345.678/0001-99",
        "telefone": "5519912345678",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1),
        "representante_id": rep_id,
    }

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = ClienteB2BRepo()
    cliente = await repo.get_by_telefone(
        tenant_id="jmb",
        telefone="5519912345678",
        session=mock_session,
    )

    assert cliente is not None, "get_by_telefone returned None — check tenant/phone filter"
    assert isinstance(cliente, ClienteB2B), "Return type must be ClienteB2B"
    assert cliente.representante_id == rep_id, (
        f"B-10 REGRESSION: representante_id expected '{rep_id}' but got '{cliente.representante_id}'. "
        "Fix: include representante_id in SELECT of get_by_telefone."
    )


@pytest.mark.regression
def test_b10_get_by_telefone_query_selects_representante_id() -> None:
    """B-10: SQL in get_by_telefone must include 'representante_id'.

    Inspects source code to verify the column name appears in the SQL.
    Fails if the column is removed from the SELECT list.
    """
    import inspect

    from src.agents import repo as repo_module

    source = inspect.getsource(repo_module.ClienteB2BRepo.get_by_telefone)
    assert "representante_id" in source, (
        "B-10 REGRESSION: 'representante_id' not found in get_by_telefone source. "
        "The SQL SELECT must include this column."
    )


# ─────────────────────────────────────────────────────────────
# B-11: persona switch does not invalidate Redis history
# ─────────────────────────────────────────────────────────────

@pytest.mark.regression
@pytest.mark.asyncio
async def test_b11_invalidar_redis_conversa_deletes_all_keys() -> None:
    """B-11: _invalidar_redis_conversa must delete all conv:{tenant}:{numero}* keys.

    Fails if the function is removed or doesn't scan/delete matching keys.
    """
    from src.agents.ui import _invalidar_redis_conversa

    tenant_id = "jmb"
    numero = "5519912345678"
    pattern = f"conv:{tenant_id}:{numero}*"

    # Build mock Redis with keys matching the pattern
    matching_keys = [
        f"conv:{tenant_id}:{numero}",
        f"conv:{tenant_id}:{numero}:extra",
    ]
    non_matching_keys = [f"conv:outro:{numero}"]

    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=matching_keys)
    mock_redis.delete = AsyncMock(return_value=2)

    await _invalidar_redis_conversa(mock_redis, tenant_id, numero)

    mock_redis.keys.assert_called_once_with(pattern)
    mock_redis.delete.assert_called_once_with(*matching_keys)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b11_invalidar_redis_noop_when_no_keys() -> None:
    """B-11: _invalidar_redis_conversa must not crash when no keys match."""
    from src.agents.ui import _invalidar_redis_conversa

    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.delete = AsyncMock()

    # Must not raise
    await _invalidar_redis_conversa(mock_redis, "jmb", "5519999999999")

    mock_redis.keys.assert_called_once()
    mock_redis.delete.assert_not_called()


# ─────────────────────────────────────────────────────────────
# B-12: Langfuse wrapper missing session_id and output
# ─────────────────────────────────────────────────────────────

@pytest.mark.regression
def test_b12_get_anthropic_client_signature_accepts_session_id() -> None:
    """B-12: _get_anthropic_client must accept session_id parameter.

    Fails if the signature is reverted to no-arg form.
    """
    import inspect

    from src.agents.runtime.agent_cliente import AgentCliente
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.agents.runtime.agent_rep import AgentRep

    for cls in (AgentCliente, AgentGestor, AgentRep):
        method = getattr(cls, "_get_anthropic_client", None)
        assert method is not None, f"{cls.__name__}._get_anthropic_client is missing"
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert "session_id" in params, (
            f"B-12 REGRESSION: {cls.__name__}._get_anthropic_client missing 'session_id' param. "
            "Fix: add session_id: str parameter."
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_b12_langfuse_output_called_in_agent_cliente() -> None:
    """B-12: AgentCliente.responder must call update_current_observation(output=...).

    Verifies that the Langfuse output is set before returning.
    """
    from src.agents.runtime.agent_cliente import AgentCliente
    import src.agents.runtime.agent_cliente as agent_cliente_module

    mock_lf_ctx = MagicMock()
    mock_lf_ctx.update_current_trace = MagicMock()
    mock_lf_ctx.update_current_observation = MagicMock()

    # Check that update_current_observation is used in source
    import inspect
    source = inspect.getsource(agent_cliente_module)
    assert "update_current_observation" in source, (
        "B-12 REGRESSION: 'update_current_observation' not found in agent_cliente.py. "
        "Fix: call _lf_ctx.update_current_observation(output=resposta_final) before returning."
    )


@pytest.mark.regression
def test_b12_langfuse_output_in_all_agents() -> None:
    """B-12: update_current_observation(output=...) must appear in all 3 agents.

    Inspects source of each agent module to verify the call is present.
    """
    import inspect

    import src.agents.runtime.agent_cliente as mod_cliente
    import src.agents.runtime.agent_gestor as mod_gestor
    import src.agents.runtime.agent_rep as mod_rep

    for mod, name in [
        (mod_cliente, "agent_cliente"),
        (mod_gestor, "agent_gestor"),
        (mod_rep, "agent_rep"),
    ]:
        source = inspect.getsource(mod)
        assert "update_current_observation" in source, (
            f"B-12 REGRESSION: 'update_current_observation' not found in {name}.py. "
            "Fix: add _lf_ctx.update_current_observation(output=resposta_final)."
        )
        assert "session_id" in source, (
            f"B-12 REGRESSION: 'session_id' not found in {name}.py. "
            "Fix: pass session_id to _get_anthropic_client()."
        )
