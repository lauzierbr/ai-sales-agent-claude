"""Service do domínio Tenants — lógica de negócio de provisionamento.

Camada Service: importa apenas Types, Config e Repo do domínio.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.providers.auth import hash_password
from src.tenants.repo import TenantRepo, UsuarioRepo
from src.tenants.types import Role, Tenant, Usuario

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TenantService:
    """Serviço de operações de tenant — criação, onboarding e consulta."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Inicializa com session factory para operações transacionais.

        Args:
            session_factory: async_sessionmaker do SQLAlchemy.
        """
        self._sf = session_factory
        self._tenant_repo = TenantRepo()
        self._usuario_repo = UsuarioRepo()

    async def provision_tenant(
        self,
        nome: str,
        cnpj: str,
        gestor_cnpj: str,
        gestor_senha: str,
        bcrypt_rounds: int = 12,
    ) -> Tenant:
        """Provisiona novo tenant com usuário gestor em transação única.

        Cria registro em `tenants` + registro em `usuarios` (gestor) atomicamente.

        Args:
            nome: nome da distribuidora/fabricante.
            cnpj: CNPJ da empresa.
            gestor_cnpj: CNPJ do gestor (usuário admin).
            gestor_senha: senha plaintext do gestor (será hasheada).
            bcrypt_rounds: rounds bcrypt (12 produção, 4 testes).

        Returns:
            Tenant recém criado.

        Raises:
            Exception: se falhar a persistência (rolled back automaticamente).
        """
        with tracer.start_as_current_span("provision_tenant") as span:
            span.set_attribute("tenant_nome", nome)
            span.set_attribute("tenant_cnpj", cnpj)

            tenant_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            tenant = Tenant(
                id=tenant_id,
                nome=nome,
                cnpj=cnpj,
                ativo=True,
                criado_em=now,
            )

            usuario = Usuario(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                cnpj=gestor_cnpj,
                senha_hash=hash_password(gestor_senha, rounds=bcrypt_rounds),
                role=Role.gestor,
                ativo=True,
                criado_em=now,
            )

            async with self._sf() as session:
                async with session.begin():
                    await self._tenant_repo.create(tenant, session)
                    await self._usuario_repo.create(usuario, session)

            log.info(
                "tenant_provisionado",
                tenant_id=tenant_id,
                nome=nome,
                gestor_cnpj=gestor_cnpj,
            )
            return tenant

    async def get_active_tenants(self) -> list[Tenant]:
        """Retorna lista de tenants ativos.

        Returns:
            Lista de Tenant ordenada por nome.
        """
        with tracer.start_as_current_span("get_active_tenants"):
            async with self._sf() as session:
                return await self._tenant_repo.get_active_tenants(session)

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Retorna tenant por ID.

        Args:
            tenant_id: ID do tenant.

        Returns:
            Tenant ou None se não encontrado.
        """
        with tracer.start_as_current_span("get_tenant") as span:
            span.set_attribute("tenant_id", tenant_id)
            async with self._sf() as session:
                return await self._tenant_repo.get_by_id(tenant_id, session)
