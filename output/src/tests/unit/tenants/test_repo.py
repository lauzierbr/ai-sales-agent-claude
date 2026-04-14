"""Testes unitários de tenants/repo.py — TenantRepo e UsuarioRepo.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tenants.types import Role, Tenant, Usuario


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


def _make_tenant(tenant_id: str = "jmb") -> Tenant:
    return Tenant(
        id=tenant_id,
        nome="JMB Distribuidora",
        cnpj="00.000.000/0001-00",
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_usuario(tenant_id: str = "jmb") -> Usuario:
    return Usuario(
        id="u1",
        tenant_id=tenant_id,
        cnpj="11.222.333/0001-44",
        senha_hash="$2b$04$hash",
        role=Role.gestor,
        ativo=True,
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_row(data: dict[str, Any]) -> MagicMock:
    """Cria mock de row de resultado SQLAlchemy."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _make_session(row: MagicMock | None, *, many: bool = False) -> AsyncMock:
    """Cria mock de AsyncSession com resultado configurável."""
    session = AsyncMock()
    result = MagicMock()

    if many:
        result.mappings.return_value.all.return_value = [row] if row else []
    else:
        result.mappings.return_value.first.return_value = row

    session.execute = AsyncMock(return_value=result)
    return session


# ─────────────────────────────────────────────
# A3 — inspect.signature: todo método de query tem tenant_id
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_todo_metodo_repo_tem_tenant_id() -> None:
    """A3: métodos de query por entidade têm tenant_id na assinatura (inspect.signature).

    Garante que o padrão de isolamento por tenant é estruturalmente aplicado
    nos métodos de lookup do repositório.
    """
    from src.tenants.repo import TenantRepo, UsuarioRepo

    # TenantRepo.get_by_id deve ter tenant_id como parâmetro obrigatório
    sig_get_by_id = inspect.signature(TenantRepo.get_by_id)
    assert "tenant_id" in sig_get_by_id.parameters, (
        "TenantRepo.get_by_id precisa de tenant_id para isolamento de dados"
    )

    # UsuarioRepo.get_by_cnpj deve ter tenant_id para filtrar no tenant correto
    sig_get_by_cnpj = inspect.signature(UsuarioRepo.get_by_cnpj)
    assert "tenant_id" in sig_get_by_cnpj.parameters, (
        "UsuarioRepo.get_by_cnpj precisa de tenant_id para isolamento de dados"
    )

    # get_by_cnpj_global é exceção documentada — somente para POST /auth/login
    # Deve existir com nome explicitamente marcado como "global" (sem filtro de tenant)
    assert hasattr(UsuarioRepo, "get_by_cnpj_global"), (
        "UsuarioRepo.get_by_cnpj_global deve existir como método explicitamente global"
    )
    sig_global = inspect.signature(UsuarioRepo.get_by_cnpj_global)
    assert "tenant_id" not in sig_global.parameters, (
        "get_by_cnpj_global não deve ter tenant_id — é lookup cross-tenant intencional"
    )


# ─────────────────────────────────────────────
# TenantRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_tenant_repo_get_by_id_encontrado() -> None:
    """TenantRepo.get_by_id retorna Tenant quando encontrado."""
    from src.tenants.repo import TenantRepo

    row_data = {
        "id": "jmb",
        "nome": "JMB Distribuidora",
        "cnpj": "00.000.000/0001-00",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    session = _make_session(_make_row(row_data))

    repo = TenantRepo()
    tenant = await repo.get_by_id("jmb", session)

    assert tenant is not None
    assert tenant.id == "jmb"
    assert tenant.nome == "JMB Distribuidora"
    assert tenant.ativo is True


@pytest.mark.unit
async def test_tenant_repo_get_by_id_nao_encontrado() -> None:
    """TenantRepo.get_by_id retorna None quando tenant não existe."""
    from src.tenants.repo import TenantRepo

    session = _make_session(None)

    repo = TenantRepo()
    result = await repo.get_by_id("inexistente", session)

    assert result is None


@pytest.mark.unit
async def test_tenant_repo_get_active_tenants_retorna_lista() -> None:
    """TenantRepo.get_active_tenants retorna lista de tenants ativos."""
    from src.tenants.repo import TenantRepo

    row_data = {
        "id": "jmb",
        "nome": "JMB Distribuidora",
        "cnpj": "00.000.000/0001-00",
        "ativo": True,
        "whatsapp_number": None,
        "config_json": {},
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    session = _make_session(_make_row(row_data), many=True)

    repo = TenantRepo()
    tenants = await repo.get_active_tenants(session)

    assert len(tenants) == 1
    assert tenants[0].id == "jmb"


@pytest.mark.unit
async def test_tenant_repo_create_executa_insert() -> None:
    """TenantRepo.create executa INSERT e retorna o tenant."""
    from src.tenants.repo import TenantRepo

    session = AsyncMock()
    session.execute = AsyncMock()

    repo = TenantRepo()
    tenant = _make_tenant()
    result = await repo.create(tenant, session)

    assert result.id == tenant.id
    session.execute.assert_called_once()


# ─────────────────────────────────────────────
# UsuarioRepo
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_usuario_repo_get_by_cnpj_encontrado() -> None:
    """UsuarioRepo.get_by_cnpj retorna Usuario filtrando por tenant_id."""
    from src.tenants.repo import UsuarioRepo

    row_data = {
        "id": "u1",
        "tenant_id": "jmb",
        "cnpj": "11.222.333/0001-44",
        "senha_hash": "$2b$04$hash",
        "role": "gestor",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    session = _make_session(_make_row(row_data))

    repo = UsuarioRepo()
    usuario = await repo.get_by_cnpj("11.222.333/0001-44", "jmb", session)

    assert usuario is not None
    assert usuario.tenant_id == "jmb"
    assert usuario.role == Role.gestor


@pytest.mark.unit
async def test_usuario_repo_get_by_cnpj_nao_encontrado() -> None:
    """UsuarioRepo.get_by_cnpj retorna None quando não encontrado no tenant."""
    from src.tenants.repo import UsuarioRepo

    session = _make_session(None)

    repo = UsuarioRepo()
    result = await repo.get_by_cnpj("99.999.999/0001-99", "jmb", session)

    assert result is None


@pytest.mark.unit
async def test_usuario_repo_get_by_cnpj_global_sem_filtro_tenant() -> None:
    """UsuarioRepo.get_by_cnpj_global busca sem filtro de tenant (login cross-tenant)."""
    from src.tenants.repo import UsuarioRepo

    row_data = {
        "id": "u1",
        "tenant_id": "jmb",
        "cnpj": "11.222.333/0001-44",
        "senha_hash": "$2b$04$hash",
        "role": "gestor",
        "ativo": True,
        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    session = _make_session(_make_row(row_data))

    repo = UsuarioRepo()
    usuario = await repo.get_by_cnpj_global("11.222.333/0001-44", session)

    assert usuario is not None
    assert usuario.tenant_id == "jmb"


@pytest.mark.unit
async def test_usuario_repo_create_executa_insert() -> None:
    """UsuarioRepo.create executa INSERT e retorna o usuário."""
    from src.tenants.repo import UsuarioRepo

    session = AsyncMock()
    session.execute = AsyncMock()

    repo = UsuarioRepo()
    usuario = _make_usuario()
    result = await repo.create(usuario, session)

    assert result.id == usuario.id
    session.execute.assert_called_once()
