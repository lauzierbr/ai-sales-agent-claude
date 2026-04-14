"""UI do domínio Tenants — FastAPI router.

Camada UI: importa tudo. Endpoints de tenants e autenticação.
POST /auth/login excluído do TenantProvider (sem X-Tenant-ID necessário).
GET|POST /tenants — endpoints internos sem auth em Sprint 1.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.providers.auth import create_access_token, verify_password
from src.providers.db import get_session, get_session_factory
from src.tenants.repo import TenantRepo, UsuarioRepo
from src.tenants.service import TenantService

log = structlog.get_logger(__name__)

router = APIRouter(tags=["tenants"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Payload do endpoint de login."""

    cnpj: str
    senha: str


@auth_router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Autentica gestor/rep e retorna JWT de 8h.

    Lookup de usuário por CNPJ global (sem tenant — ver UsuarioRepo.get_by_cnpj_global).

    Returns:
        {"access_token": "...", "token_type": "bearer"}

    Raises:
        HTTPException 401: se CNPJ não encontrado ou senha incorreta.
    """
    repo = UsuarioRepo()
    usuario = await repo.get_by_cnpj_global(data.cnpj, session)

    if usuario is None:
        raise HTTPException(status_code=401, detail="CNPJ ou senha inválidos")

    if not verify_password(data.senha, usuario.senha_hash):
        log.warning("login_senha_incorreta", cnpj_hash=data.cnpj[:4] + "****")
        raise HTTPException(status_code=401, detail="CNPJ ou senha inválidos")

    token = create_access_token(
        user_id=usuario.id,
        tenant_id=usuario.tenant_id,
        role=usuario.role.value,
    )

    log.info("login_sucesso", usuario_id=usuario.id, tenant_id=usuario.tenant_id)
    return JSONResponse({"access_token": token, "token_type": "bearer"})


# ─────────────────────────────────────────────
# Tenant endpoints (internos — sem auth em Sprint 1)
# ─────────────────────────────────────────────


class ProvisionRequest(BaseModel):
    """Payload para provisionamento de novo tenant."""

    nome: str
    cnpj: str
    gestor_cnpj: str
    gestor_senha: str


@router.get("/tenants")
async def list_tenants(
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Lista todos os tenants ativos — endpoint interno.

    Returns:
        Lista de tenants serializados.
    """
    repo = TenantRepo()
    tenants = await repo.get_active_tenants(session)
    return JSONResponse([t.to_dict() for t in tenants])


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Retorna tenant por ID — endpoint interno.

    Raises:
        HTTPException 404: se tenant não encontrado.
    """
    repo = TenantRepo()
    tenant = await repo.get_by_id(tenant_id, session)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")
    return JSONResponse(tenant.to_dict())


@router.post("/tenants")
async def create_tenant(data: ProvisionRequest) -> JSONResponse:
    """Provisiona novo tenant com gestor — endpoint interno.

    Returns:
        Tenant criado.
    """
    service = TenantService(get_session_factory())
    try:
        tenant = await service.provision_tenant(
            nome=data.nome,
            cnpj=data.cnpj,
            gestor_cnpj=data.gestor_cnpj,
            gestor_senha=data.gestor_senha,
        )
    except Exception as exc:
        log.error("provision_tenant_erro", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Erro ao provisionar tenant: {exc}") from exc

    return JSONResponse(tenant.to_dict(), status_code=201)
