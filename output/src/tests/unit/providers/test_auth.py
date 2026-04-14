"""Testes unitários de providers/auth.py — JWT + bcrypt.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.auth import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante JWT_SECRET configurada em todos os testes."""
    monkeypatch.setenv("JWT_SECRET", "secret-de-teste-com-32-caracteres-ok")


# ─────────────────────────────────────────────
# hash_password / verify_password
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_hash_password_gera_hash_valido() -> None:
    hashed = hash_password("senha123", rounds=4)
    assert hashed.startswith("$2b$")
    assert verify_password("senha123", hashed) is True


@pytest.mark.unit
def test_verify_password_senha_errada_retorna_false() -> None:
    hashed = hash_password("correta", rounds=4)
    assert verify_password("errada", hashed) is False


# ─────────────────────────────────────────────
# create_access_token / decode_token
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_create_access_token_retorna_string() -> None:
    token = create_access_token("user1", "jmb", "gestor")
    assert isinstance(token, str)
    assert len(token) > 10


@pytest.mark.unit
def test_decode_token_retorna_claims_corretos() -> None:
    token = create_access_token("user1", "jmb", "gestor")
    payload = decode_token(token)
    assert payload["sub"] == "user1"
    assert payload["tenant_id"] == "jmb"
    assert payload["role"] == "gestor"


@pytest.mark.unit
def test_token_expirado_retorna_401() -> None:
    from fastapi import HTTPException

    token = create_access_token("user1", "jmb", "gestor", expire_hours=-1)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.unit
def test_token_invalido_retorna_401() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_token("token.invalido.aqui")
    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────
# get_current_user
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_get_current_user_token_valido() -> None:
    token = create_access_token("user1", "jmb", "gestor")
    request = MagicMock()
    request.headers.get.return_value = f"Bearer {token}"

    user = await get_current_user(request)
    assert user["sub"] == "user1"
    assert user["tenant_id"] == "jmb"


@pytest.mark.unit
async def test_get_current_user_sem_header_retorna_401() -> None:
    from fastapi import HTTPException

    request = MagicMock()
    request.headers.get.return_value = ""

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request)
    assert exc_info.value.status_code == 401


@pytest.mark.unit
async def test_get_current_user_token_expirado_retorna_401() -> None:
    from fastapi import HTTPException

    token = create_access_token("user1", "jmb", "gestor", expire_hours=-1)
    request = MagicMock()
    request.headers.get.return_value = f"Bearer {token}"

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request)
    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────
# require_role
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_require_role_role_correto_retorna_user() -> None:
    token = create_access_token("user1", "jmb", "gestor")
    request = MagicMock()
    request.headers.get.return_value = f"Bearer {token}"

    dependency = require_role(["gestor"])
    user = await dependency(user={"sub": "user1", "role": "gestor", "tenant_id": "jmb"})
    assert user["role"] == "gestor"


@pytest.mark.unit
async def test_role_insuficiente_retorna_403() -> None:
    from fastapi import HTTPException

    dependency = require_role(["gestor"])
    with pytest.raises(HTTPException) as exc_info:
        await dependency(user={"sub": "user1", "role": "cliente", "tenant_id": "jmb"})
    assert exc_info.value.status_code == 403


@pytest.mark.unit
async def test_require_role_multiplos_roles_aceita_qualquer() -> None:
    dependency = require_role(["gestor", "rep"])
    user = await dependency(user={"sub": "u", "role": "rep", "tenant_id": "jmb"})
    assert user["role"] == "rep"
