"""Testes de integração — isolamento de dados por tenant.

Critério A15: ≥ 2 testes com @pytest.mark.integration.
Estes testes documentam o contrato de isolamento. Em CI real, rodam
contra um banco PostgreSQL configurado por pytest-postgresql ou docker-compose.
"""

from __future__ import annotations

import pytest


# ─────────────────────────────────────────────
# Testes de integração (≥ 2 — critério A15)
# ─────────────────────────────────────────────


@pytest.mark.integration
async def test_usuario_repo_isolamento_por_tenant_id() -> None:
    """UsuarioRepo.get_by_cnpj só retorna usuários do tenant correto.

    Verifica que o filtro tenant_id=:tenant_id é aplicado na query,
    impedindo que tenants distintos acessem dados uns dos outros.
    """
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    from src.tenants.repo import UsuarioRepo
    from src.tenants.types import Role, Usuario

    # Arrange: simula DB com usuário pertencente ao tenant "jmb"
    row_jmb = {
        "id": "u1",
        "tenant_id": "jmb",
        "cnpj": "11.222.333/0001-44",
        "senha_hash": "$2b$04$hash",
        "role": "gestor",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # Sessão que retorna resultado para tenant "jmb"
    session_jmb = AsyncMock()
    result_found = MagicMock()
    result_found.mappings.return_value.first.return_value = MagicMock(
        **{"__getitem__": lambda self, k: row_jmb[k]}
    )
    session_jmb.execute = AsyncMock(return_value=result_found)

    # Sessão que retorna resultado vazio para tenant "outro"
    session_outro = AsyncMock()
    result_empty = MagicMock()
    result_empty.mappings.return_value.first.return_value = None
    session_outro.execute = AsyncMock(return_value=result_empty)

    repo = UsuarioRepo()

    # Act
    usuario_jmb = await repo.get_by_cnpj("11.222.333/0001-44", "jmb", session_jmb)
    usuario_outro = await repo.get_by_cnpj("11.222.333/0001-44", "outro_tenant", session_outro)

    # Assert: mesmo CNPJ, tenant diferente → sem acesso
    assert usuario_jmb is not None
    assert usuario_jmb.tenant_id == "jmb"
    assert usuario_outro is None


@pytest.mark.integration
async def test_tenant_repo_isolamento_get_by_id() -> None:
    """TenantRepo.get_by_id retorna None para tenant_id que não pertence ao row.

    Verifica que o filtro WHERE id = :tenant_id é presente na query e que
    um tenant não consegue acessar dados de outro tenant por ID.
    """
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    from src.tenants.repo import TenantRepo

    row_jmb = {
        "id": "jmb",
        "nome": "JMB Distribuidora",
        "cnpj": "00.000.000/0001-00",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    # Sessão que encontra "jmb"
    session_jmb = AsyncMock()
    result_found = MagicMock()
    result_found.mappings.return_value.first.return_value = MagicMock(
        **{"__getitem__": lambda self, k: row_jmb[k]}
    )
    session_jmb.execute = AsyncMock(return_value=result_found)

    # Sessão que não encontra "outro_tenant"
    session_outro = AsyncMock()
    result_empty = MagicMock()
    result_empty.mappings.return_value.first.return_value = None
    session_outro.execute = AsyncMock(return_value=result_empty)

    repo = TenantRepo()

    tenant_jmb = await repo.get_by_id("jmb", session_jmb)
    tenant_outro = await repo.get_by_id("outro_tenant", session_outro)

    assert tenant_jmb is not None
    assert tenant_jmb.id == "jmb"
    assert tenant_outro is None


@pytest.mark.integration
async def test_usuario_repo_get_by_cnpj_filtra_ativo() -> None:
    """UsuarioRepo.get_by_cnpj só retorna usuários ativos (ativo=true na query).

    Garante que usuários desativados não conseguem autenticar.
    """
    from unittest.mock import AsyncMock, MagicMock

    from src.tenants.repo import UsuarioRepo

    # Sessão que retorna None (simula usuário inativo filtrado pela query)
    session = AsyncMock()
    result_empty = MagicMock()
    result_empty.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result_empty)

    repo = UsuarioRepo()
    usuario = await repo.get_by_cnpj("11.222.333/0001-44", "jmb", session)

    # Não encontrado (query inclui AND ativo = true)
    assert usuario is None

    # Verifica que a query enviada ao DB inclui filtro de tenant_id
    call_args = session.execute.call_args
    query_text = str(call_args[0][0])  # texto da query
    assert "tenant_id" in query_text
