"""Testes unitários dos hotfixes do Sprint 8 (B-10, B-11, B-12).

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────
# A1/A2 — B-10: representante_id em get_by_telefone
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_get_by_telefone_retorna_representante_id() -> None:
    """A1: get_by_telefone retorna ClienteB2B com representante_id não-nulo."""
    from src.agents.repo import ClienteB2BRepo
    from src.agents.types import ClienteB2B

    rep_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_row = MagicMock()
    row_data = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "tenant_id": "jmb",
        "nome": "Farmácia São Paulo",
        "cnpj": "12.345.678/0001-99",
        "telefone": "5519912345678",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1),
        "representante_id": rep_id,
    }
    mock_row.__getitem__ = lambda self, key: row_data[key]

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = ClienteB2BRepo()
    cliente = await repo.get_by_telefone("jmb", "5519912345678", mock_session)

    assert cliente is not None
    assert isinstance(cliente, ClienteB2B)
    assert cliente.representante_id == rep_id


@pytest.mark.unit
def test_clienteb2b_representante_id_annotation() -> None:
    """A2: ClienteB2B type tem anotação representante_id."""
    import inspect
    from src.agents.types import ClienteB2B

    annotations = inspect.get_annotations(ClienteB2B, eval_str=True)
    assert "representante_id" in annotations


# ─────────────────────────────────────────────────────────────
# A3 — B-11: troca de persona invalida Redis
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_troca_persona_invalida_redis() -> None:
    """A3: _invalidar_redis_conversa deleta chaves conv:{tenant}:{numero}*."""
    from src.agents.ui import _invalidar_redis_conversa

    tenant_id = "jmb"
    numero = "5519912345678"
    pattern = f"conv:{tenant_id}:{numero}*"

    matching_keys = [
        f"conv:{tenant_id}:{numero}",
        f"conv:{tenant_id}:{numero}:extra",
    ]

    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=matching_keys)
    mock_redis.delete = AsyncMock(return_value=2)

    await _invalidar_redis_conversa(mock_redis, tenant_id, numero)

    mock_redis.keys.assert_called_once_with(pattern)
    mock_redis.delete.assert_called_once_with(*matching_keys)


@pytest.mark.unit
async def test_invalidar_redis_nao_chama_delete_se_sem_chaves() -> None:
    """A3: _invalidar_redis_conversa não chama delete quando não há chaves."""
    from src.agents.ui import _invalidar_redis_conversa

    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.delete = AsyncMock()

    await _invalidar_redis_conversa(mock_redis, "jmb", "5519999999999")

    mock_redis.delete.assert_not_called()


# ─────────────────────────────────────────────────────────────
# A4/A5 — B-12: Langfuse session_id e output
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_langfuse_get_anthropic_client_aceita_session_id_gestor() -> None:
    """A4: AgentGestor._get_anthropic_client aceita session_id."""
    import inspect
    from src.agents.runtime.agent_gestor import AgentGestor

    sig = inspect.signature(AgentGestor._get_anthropic_client)
    assert "session_id" in sig.parameters


@pytest.mark.unit
def test_langfuse_get_anthropic_client_aceita_session_id_cliente() -> None:
    """A4: AgentCliente._get_anthropic_client aceita session_id."""
    import inspect
    from src.agents.runtime.agent_cliente import AgentCliente

    sig = inspect.signature(AgentCliente._get_anthropic_client)
    assert "session_id" in sig.parameters


@pytest.mark.unit
def test_langfuse_get_anthropic_client_aceita_session_id_rep() -> None:
    """A4: AgentRep._get_anthropic_client aceita session_id."""
    import inspect
    from src.agents.runtime.agent_rep import AgentRep

    sig = inspect.signature(AgentRep._get_anthropic_client)
    assert "session_id" in sig.parameters


@pytest.mark.unit
def test_langfuse_update_current_observation_em_gestor() -> None:
    """A4: update_current_observation aparece no código do AgentGestor."""
    import inspect
    import src.agents.runtime.agent_gestor as mod

    source = inspect.getsource(mod)
    assert "update_current_observation" in source


@pytest.mark.unit
def test_langfuse_update_current_observation_em_cliente() -> None:
    """A4: update_current_observation aparece no código do AgentCliente."""
    import inspect
    import src.agents.runtime.agent_cliente as mod

    source = inspect.getsource(mod)
    assert "update_current_observation" in source


@pytest.mark.unit
def test_langfuse_update_current_observation_em_rep() -> None:
    """A4: update_current_observation aparece no código do AgentRep."""
    import inspect
    import src.agents.runtime.agent_rep as mod

    source = inspect.getsource(mod)
    assert "update_current_observation" in source


@pytest.mark.unit
def test_dummy_lf_ctx_tem_update_current_observation() -> None:
    """A5: _DummyLfCtx tem update_current_observation sem lançar erro."""
    import os
    os.environ["LANGFUSE_ENABLED"] = "false"

    # Importa módulo com LANGFUSE_ENABLED=false para usar o dummy
    import importlib
    import src.agents.runtime.agent_gestor as mod_gestor

    # Testa que a classe dummy tem o método
    dummy = mod_gestor._DummyLfCtx()
    dummy.update_current_observation(output="teste")  # não deve lançar


@pytest.mark.unit
async def test_agent_gestor_commerce_repo_injetado() -> None:
    """M_INJECT: AgentGestor.__init__ aceita commerce_repo e o armazena."""
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.commerce.repo import CommerceRepo

    mock_repo = MagicMock(spec=CommerceRepo)

    agent = AgentGestor(
        order_service=MagicMock(),
        conversa_repo=MagicMock(),
        pdf_generator=MagicMock(),
        config=MagicMock(),
        gestor=MagicMock(),
        commerce_repo=mock_repo,
    )

    assert agent._commerce_repo is mock_repo


@pytest.mark.unit
async def test_agent_gestor_commerce_repo_default_nao_none() -> None:
    """M_INJECT: AgentGestor instanciado sem commerce_repo usa CommerceRepo()."""
    from src.agents.runtime.agent_gestor import AgentGestor
    from src.commerce.repo import CommerceRepo

    agent = AgentGestor(
        order_service=MagicMock(),
        conversa_repo=MagicMock(),
        pdf_generator=MagicMock(),
        config=MagicMock(),
        gestor=MagicMock(),
    )

    assert agent._commerce_repo is not None
    assert isinstance(agent._commerce_repo, CommerceRepo)
