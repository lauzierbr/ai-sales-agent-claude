"""Provider de autenticação JWT — PyJWT + HS256 + bcrypt.

Cross-cutting provider: pode ser importado por qualquer camada.
Decisão: D021 — PyJWT + HS256, access token 8h, sem refresh em Sprint 1.
Decisão: D022 — JWT apenas para ações privilegiadas.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import structlog
from fastapi import Depends, HTTPException, Request

log = structlog.get_logger(__name__)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8


def _get_jwt_secret() -> str:
    """Lê JWT_SECRET do Infisical (injetado via env).

    Raises:
        ValueError: se JWT_SECRET não estiver configurada.
    """
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise ValueError("Variável Infisical não configurada: JWT_SECRET")
    return secret


def hash_password(password: str, rounds: int = 12) -> str:
    """Gera hash bcrypt da senha.

    Args:
        password: senha em plaintext.
        rounds: custo do bcrypt (12 em produção, 4 em testes).

    Returns:
        Hash bcrypt como string.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verifica senha contra hash bcrypt.

    Args:
        password: senha em plaintext.
        hashed: hash bcrypt armazenado.

    Returns:
        True se senha correta, False caso contrário.
    """
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expire_hours: int = ACCESS_TOKEN_EXPIRE_HOURS,
) -> str:
    """Cria JWT assinado com HS256.

    Args:
        user_id: ID do usuário (sub do token).
        tenant_id: ID do tenant do usuário.
        role: papel do usuário (gestor|rep|cliente).
        expire_hours: duração do token em horas (default 8h).

    Returns:
        JWT assinado como string.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica e valida JWT.

    Args:
        token: JWT como string.

    Returns:
        Payload decodificado.

    Raises:
        HTTPException 401: se token inválido, expirado ou malformado.
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return dict(payload)
    except jwt.ExpiredSignatureError:
        log.warning("jwt_expirado")
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError as exc:
        log.warning("jwt_invalido", error=str(exc))
        raise HTTPException(status_code=401, detail="Token inválido")


async def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: extrai e valida JWT do header Authorization.

    Uso:
        async def endpoint(user: dict = Depends(get_current_user)): ...

    Returns:
        Payload do token: {sub, tenant_id, role, iat, exp}.

    Raises:
        HTTPException 401: se header ausente ou token inválido/expirado.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação ausente")
    token = auth_header.removeprefix("Bearer ")
    return decode_token(token)


def require_role(roles: list[str]) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Dependency factory: valida que usuário tem um dos roles permitidos.

    Uso:
        @router.post("/crawl")
        async def crawl(_: dict = Depends(require_role(["gestor"]))): ...

    Args:
        roles: lista de roles aceitos (ex: ["gestor", "rep"]).

    Returns:
        FastAPI dependency que retorna o payload do usuário ou levanta 403.
    """
    async def _dependency(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if user.get("role") not in roles:
            log.warning(
                "acesso_negado",
                user_id=user.get("sub"),
                role=user.get("role"),
                roles_necessarios=roles,
            )
            raise HTTPException(status_code=403, detail="Permissão insuficiente")
        return user

    return _dependency
