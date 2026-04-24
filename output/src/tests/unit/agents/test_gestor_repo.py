"""Testes unitários de GestorRepo.listar_ativos_por_tenant (Sprint 7).

Todos os testes são @pytest.mark.unit — sem I/O externo.
PostgreSQL mockado via AsyncMock.

Casos cobertos:
  - test_listar_ativos_por_tenant_retorna_gestores_ativos: 2 rows ativos → lista com 2 gestores
  - test_listar_ativos_por_tenant_isolamento_tenant: query usa tenant_id = :tenant_id
  - test_listar_ativos_lista_vazia: 0 rows → [] sem exceção
  - test_listar_ativos_exclui_inativos: query contém ativo = true
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.repo import GestorRepo
from src.agents.types import Gestor


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_gestor_row(
    id: str,
    tenant_id: str,
    telefone: str,
    nome: str,
    ativo: bool = True,
) -> dict:
    return {
        "id": id,
        "tenant_id": tenant_id,
        "telefone": telefone,
        "nome": nome,
        "ativo": ativo,
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def _make_session_mock(rows: list[dict]) -> AsyncMock:
    """Cria AsyncMock de session que retorna as rows fornecidas."""
    mapping_result = MagicMock()
    mapping_result.all.return_value = [MagicMock(**row) for row in rows]
    # Faz cada row se comportar como Mapping via __getitem__
    for i, row in enumerate(rows):
        mapping_result.all.return_value[i].__getitem__ = lambda self, key, r=row: r[key]

    result_mock = MagicMock()
    result_mock.mappings.return_value = mapping_result

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ─────────────────────────────────────────────
# Testes
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_listar_ativos_por_tenant_retorna_gestores_ativos() -> None:
    """Mock session retorna 2 rows ativos → lista com 2 gestores."""
    rows = [
        _make_gestor_row("g-001", "jmb", "5519111111111", "Alice"),
        _make_gestor_row("g-002", "jmb", "5519222222222", "Bob"),
    ]
    session = _make_session_mock(rows)

    repo = GestorRepo()
    result = await repo.listar_ativos_por_tenant("jmb", session)

    assert len(result) == 2
    assert all(isinstance(g, Gestor) for g in result)
    assert {g.id for g in result} == {"g-001", "g-002"}
    assert {g.telefone for g in result} == {"5519111111111", "5519222222222"}
    assert all(g.tenant_id == "jmb" for g in result)


@pytest.mark.unit
async def test_listar_ativos_por_tenant_isolamento_tenant() -> None:
    """Query SQL inclui tenant_id = :tenant_id — verificado via call args do session.execute."""
    session = _make_session_mock([])

    repo = GestorRepo()
    await repo.listar_ativos_por_tenant("tenant-abc", session)

    # Verifica que session.execute foi chamado com params contendo tenant_id correto
    assert session.execute.called
    call_args = session.execute.call_args
    # Segundo argumento posicional são os params do bind
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert params.get("tenant_id") == "tenant-abc", (
        f"Esperado tenant_id='tenant-abc', obtido params={params!r}"
    )

    # Verificar que a query SQL contém o filtro de tenant_id
    sql_text = str(call_args[0][0])
    assert "tenant_id" in sql_text, "Query SQL deve filtrar por tenant_id"


@pytest.mark.unit
async def test_listar_ativos_lista_vazia() -> None:
    """Mock session retorna 0 rows → método devolve [] sem levantar exceção."""
    session = _make_session_mock([])

    repo = GestorRepo()
    result = await repo.listar_ativos_por_tenant("jmb", session)

    assert result == []
    assert isinstance(result, list)


@pytest.mark.unit
async def test_listar_ativos_exclui_inativos() -> None:
    """Query SQL inclui ativo = true — verificado inspecionando o SQL gerado."""
    session = _make_session_mock([])

    repo = GestorRepo()
    await repo.listar_ativos_por_tenant("jmb", session)

    # Inspeciona o SQL para confirmar filtro ativo = true
    assert session.execute.called
    call_args = session.execute.call_args
    sql_text = str(call_args[0][0])
    assert "ativo" in sql_text.lower(), "Query SQL deve filtrar por ativo"
    assert "true" in sql_text.lower(), "Query SQL deve filtrar por ativo = true"
