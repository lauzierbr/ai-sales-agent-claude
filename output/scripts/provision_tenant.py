#!/usr/bin/env python3
"""Script de provisionamento de novo tenant.

Uso:
    infisical run --env=dev -- python scripts/provision_tenant.py \\
        --nome "Distribuidora Teste" \\
        --cnpj "00.000.000/0001-00" \\
        --gestor-cnpj "00.000.000/0001-00" \\
        --gestor-senha "senha123"

Requer:
    - POSTGRES_URL configurada via Infisical
    - Migrations já aplicadas (alembic upgrade head)
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def main(nome: str, cnpj: str, gestor_cnpj: str, gestor_senha: str) -> None:
    """Provisiona tenant + gestor no banco de dados."""
    import structlog

    log = structlog.get_logger()

    from src.providers.db import get_session_factory
    from src.tenants.service import TenantService

    session_factory = get_session_factory()
    service = TenantService(session_factory)

    try:
        tenant = await service.provision_tenant(
            nome=nome,
            cnpj=cnpj,
            gestor_cnpj=gestor_cnpj,
            gestor_senha=gestor_senha,
        )
        log.info(
            "tenant_provisionado_com_sucesso",
            tenant_id=tenant.id,
            nome=tenant.nome,
            cnpj=tenant.cnpj,
        )
    except Exception as exc:
        log.error("provision_falhou", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provisiona novo tenant na plataforma")
    parser.add_argument("--nome", required=True, help="Nome da distribuidora/fabricante")
    parser.add_argument("--cnpj", required=True, help="CNPJ da empresa")
    parser.add_argument("--gestor-cnpj", required=True, help="CNPJ do usuário gestor")
    parser.add_argument("--gestor-senha", required=True, help="Senha do gestor (será hasheada)")

    args = parser.parse_args()

    asyncio.run(
        main(
            nome=args.nome,
            cnpj=args.cnpj,
            gestor_cnpj=args.gestor_cnpj,
            gestor_senha=args.gestor_senha,
        )
    )
