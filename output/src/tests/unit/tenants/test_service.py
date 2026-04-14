"""Testes unitários de tenants/service.py — TenantService.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from typing import Any

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


def _mock_session_factory(tenant: Tenant | None = None) -> MagicMock:
    """Cria session factory mock que retorna sessão com contexto begin."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    begin_ctx = AsyncMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=begin_ctx)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=begin_ctx)

    factory = MagicMock()
    factory.return_value = session
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    return factory


# ─────────────────────────────────────────────
# TenantService.provision_tenant
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_provision_tenant_retorna_tenant() -> None:
    """TenantService.provision_tenant retorna Tenant criado."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()

    with (
        patch("src.tenants.service.TenantRepo") as MockTenantRepo,
        patch("src.tenants.service.UsuarioRepo") as MockUsuarioRepo,
    ):
        mock_tenant_repo = AsyncMock()
        mock_usuario_repo = AsyncMock()
        MockTenantRepo.return_value = mock_tenant_repo
        MockUsuarioRepo.return_value = mock_usuario_repo

        service = TenantService(factory)
        tenant = await service.provision_tenant(
            nome="JMB Distribuidora",
            cnpj="00.000.000/0001-00",
            gestor_cnpj="11.222.333/0001-44",
            gestor_senha="senha_segura",
            bcrypt_rounds=4,
        )

    assert tenant.nome == "JMB Distribuidora"
    assert tenant.cnpj == "00.000.000/0001-00"
    assert tenant.ativo is True


@pytest.mark.unit
async def test_provision_tenant_chama_ambos_repos() -> None:
    """TenantService.provision_tenant cria tenant e usuário em transação única."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()

    with (
        patch("src.tenants.service.TenantRepo") as MockTenantRepo,
        patch("src.tenants.service.UsuarioRepo") as MockUsuarioRepo,
    ):
        mock_tenant_repo = AsyncMock()
        mock_usuario_repo = AsyncMock()
        MockTenantRepo.return_value = mock_tenant_repo
        MockUsuarioRepo.return_value = mock_usuario_repo

        service = TenantService(factory)
        await service.provision_tenant(
            nome="JMB",
            cnpj="00.000.000/0001-00",
            gestor_cnpj="11.222.333/0001-44",
            gestor_senha="pass",
            bcrypt_rounds=4,
        )

    mock_tenant_repo.create.assert_called_once()
    mock_usuario_repo.create.assert_called_once()


@pytest.mark.unit
async def test_provision_tenant_hasheia_senha() -> None:
    """TenantService.provision_tenant nunca armazena senha em plaintext."""
    from src.tenants.service import TenantService
    from src.providers.auth import verify_password

    factory = _mock_session_factory()
    senha_plain = "minha_senha_secreta"
    usuario_criado = None

    async def captura_usuario(usuario: Usuario, session: Any) -> None:
        nonlocal usuario_criado
        usuario_criado = usuario

    with (
        patch("src.tenants.service.TenantRepo") as MockTenantRepo,
        patch("src.tenants.service.UsuarioRepo") as MockUsuarioRepo,
    ):
        mock_tenant_repo = AsyncMock()
        mock_usuario_repo = AsyncMock()
        mock_usuario_repo.create = captura_usuario
        MockTenantRepo.return_value = mock_tenant_repo
        MockUsuarioRepo.return_value = mock_usuario_repo

        service = TenantService(factory)
        await service.provision_tenant(
            nome="JMB",
            cnpj="00.000.000/0001-00",
            gestor_cnpj="11.222.333/0001-44",
            gestor_senha=senha_plain,
            bcrypt_rounds=4,
        )

    assert usuario_criado is not None
    assert usuario_criado.senha_hash != senha_plain
    assert verify_password(senha_plain, usuario_criado.senha_hash)


@pytest.mark.unit
async def test_provision_tenant_role_e_gestor() -> None:
    """TenantService.provision_tenant cria usuário com role=gestor."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()
    usuario_criado = None

    async def captura_usuario(usuario: Usuario, session: Any) -> None:
        nonlocal usuario_criado
        usuario_criado = usuario

    with (
        patch("src.tenants.service.TenantRepo") as MockTenantRepo,
        patch("src.tenants.service.UsuarioRepo") as MockUsuarioRepo,
    ):
        mock_tenant_repo = AsyncMock()
        mock_usuario_repo = AsyncMock()
        mock_usuario_repo.create = captura_usuario
        MockTenantRepo.return_value = mock_tenant_repo
        MockUsuarioRepo.return_value = mock_usuario_repo

        service = TenantService(factory)
        await service.provision_tenant(
            nome="JMB",
            cnpj="00.000.000/0001-00",
            gestor_cnpj="11.222.333/0001-44",
            gestor_senha="pass",
            bcrypt_rounds=4,
        )

    assert usuario_criado is not None
    assert usuario_criado.role == Role.gestor


# ─────────────────────────────────────────────
# TenantService.get_active_tenants / get_tenant
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_get_active_tenants_delega_para_repo() -> None:
    """TenantService.get_active_tenants delega para TenantRepo."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()
    tenants_esperados = [_make_tenant("jmb"), _make_tenant("outro")]

    with patch("src.tenants.service.TenantRepo") as MockTenantRepo:
        mock_repo = AsyncMock()
        mock_repo.get_active_tenants = AsyncMock(return_value=tenants_esperados)
        MockTenantRepo.return_value = mock_repo

        service = TenantService(factory)
        result = await service.get_active_tenants()

    assert result == tenants_esperados


@pytest.mark.unit
async def test_get_tenant_existente() -> None:
    """TenantService.get_tenant retorna Tenant quando existe."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()
    tenant_esperado = _make_tenant("jmb")

    with patch("src.tenants.service.TenantRepo") as MockTenantRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant_esperado)
        MockTenantRepo.return_value = mock_repo

        service = TenantService(factory)
        result = await service.get_tenant("jmb")

    assert result is not None
    assert result.id == "jmb"


@pytest.mark.unit
async def test_get_tenant_inexistente_retorna_none() -> None:
    """TenantService.get_tenant retorna None quando tenant não encontrado."""
    from src.tenants.service import TenantService

    factory = _mock_session_factory()

    with patch("src.tenants.service.TenantRepo") as MockTenantRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        MockTenantRepo.return_value = mock_repo

        service = TenantService(factory)
        result = await service.get_tenant("inexistente")

    assert result is None
