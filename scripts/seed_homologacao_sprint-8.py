#!/usr/bin/env python3
"""seed_homologacao_sprint-8.py — Seed de dados para homologação Sprint 8.

Garante as pré-condições mínimas para testar os cenários do Sprint 8:
  - H1/B-10: cliente B2B com representante_id não-nulo
  - H2/B-11: representante ativo (para troca de persona)
  - H3/B-12: gestor ativo com acesso ao Langfuse
  - H11: fluxo normal de pedido (seed básico existente)

O seed é idempotente: usa SELECT + INSERT ON CONFLICT DO NOTHING.
Não modifica dados existentes.

Uso:
    infisical run --env=staging -- python scripts/seed_homologacao_sprint-8.py

Pré-condição: banco staging na migração 0023 (alembic upgrade head aplicado).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

TENANT_ID = os.getenv("DASHBOARD_TENANT_ID", "jmb")


async def _get_conn():
    """Retorna conexão asyncpg usando POSTGRES_URL do ambiente."""
    import asyncpg
    url = os.getenv("POSTGRES_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise RuntimeError("POSTGRES_URL não definida — injete via infisical run")
    return await asyncpg.connect(url)


async def seed_tenant(conn) -> None:
    """Garante que tenant JMB existe e está ativo."""
    row = await conn.fetchrow(
        "SELECT id FROM tenants WHERE id = $1",
        TENANT_ID,
    )
    if row:
        log.info("tenant_ja_existe", tenant_id=TENANT_ID)
        return

    await conn.execute(
        """
        INSERT INTO tenants (id, nome, cnpj, ativo, criado_em)
        VALUES ($1, $2, $3, true, $4)
        ON CONFLICT DO NOTHING
        """,
        TENANT_ID,
        "JMB Distribuidora",
        "00000000000100",
        datetime.now(timezone.utc),
    )
    log.info("tenant_criado", tenant_id=TENANT_ID)


async def seed_representante(conn) -> str:
    """Garante que existe pelo menos 1 representante ativo (usado em H1 e H2)."""
    row = await conn.fetchrow(
        "SELECT id FROM representantes WHERE tenant_id = $1 AND ativo = true LIMIT 1",
        TENANT_ID,
    )
    if row:
        rep_id = str(row["id"])
        log.info("representante_ja_existe", id=rep_id)
        return rep_id

    rep_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO representantes (id, tenant_id, telefone, nome, ativo, criado_em)
        VALUES ($1, $2, $3, $4, true, $5)
        ON CONFLICT DO NOTHING
        """,
        rep_id,
        TENANT_ID,
        "5519900000001",
        "Representante Seed Sprint 8",
        datetime.now(timezone.utc),
    )
    log.info("representante_criado", id=rep_id)
    return rep_id


async def seed_gestor(conn) -> str:
    """Garante que existe pelo menos 1 gestor ativo (necessário para H3 — traces Langfuse)."""
    row = await conn.fetchrow(
        "SELECT id FROM gestores WHERE tenant_id = $1 AND ativo = true LIMIT 1",
        TENANT_ID,
    )
    if row:
        gestor_id = str(row["id"])
        log.info("gestor_ja_existe", id=gestor_id)
        return gestor_id

    gestor_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO gestores (id, tenant_id, telefone, nome, ativo, criado_em)
        VALUES ($1, $2, $3, $4, true, $5)
        ON CONFLICT DO NOTHING
        """,
        gestor_id,
        TENANT_ID,
        "5519900000099",
        "Gestor Seed Sprint 8",
        datetime.now(timezone.utc),
    )
    log.info("gestor_criado", id=gestor_id)
    return gestor_id


async def seed_cliente_b2b_com_representante(conn, representante_id: str) -> str:
    """Garante cliente B2B com representante_id não-nulo — pré-condição crítica para H1/B-10."""
    row = await conn.fetchrow(
        """
        SELECT id FROM clientes_b2b
        WHERE tenant_id = $1
          AND ativo = true
          AND representante_id IS NOT NULL
        LIMIT 1
        """,
        TENANT_ID,
    )
    if row:
        cliente_id = str(row["id"])
        log.info("cliente_b2b_com_rep_ja_existe", id=cliente_id)
        return cliente_id

    cliente_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO clientes_b2b
            (id, tenant_id, nome, cnpj, telefone, representante_id, ativo, criado_em)
        VALUES ($1, $2, $3, $4, $5, $6, true, $7)
        ON CONFLICT DO NOTHING
        """,
        cliente_id,
        TENANT_ID,
        "Empresa Seed Sprint 8",
        "11222333000182",
        "5511900000003",
        representante_id,
        datetime.now(timezone.utc),
    )
    log.info("cliente_b2b_criado_com_rep", id=cliente_id, representante_id=representante_id)
    return cliente_id


async def verify_state(conn) -> bool:
    """Verifica pré-condições do ambiente após seed. Retorna True se tudo OK."""
    checks: dict[str, int | None] = {
        "tenant_ativo": await conn.fetchval(
            "SELECT COUNT(*) FROM tenants WHERE id = $1 AND ativo = true", TENANT_ID
        ),
        "representantes_ativos": await conn.fetchval(
            "SELECT COUNT(*) FROM representantes WHERE tenant_id = $1 AND ativo = true", TENANT_ID
        ),
        "gestores_ativos": await conn.fetchval(
            "SELECT COUNT(*) FROM gestores WHERE tenant_id = $1 AND ativo = true", TENANT_ID
        ),
        "clientes_b2b_com_representante": await conn.fetchval(
            """
            SELECT COUNT(*) FROM clientes_b2b
            WHERE tenant_id = $1
              AND ativo = true
              AND representante_id IS NOT NULL
            """,
            TENANT_ID,
        ),
        "migrations_0023_aplicadas": await conn.fetchval(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN (
                'commerce_products', 'commerce_accounts_b2b',
                'commerce_orders', 'sync_runs', 'sync_artifacts',
                'commerce_vendedores'
            )
            """
        ),
    }

    all_ok = True
    for check_name, value in checks.items():
        ok = value is not None and value > 0
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {check_name}: {value}")
        if not ok:
            all_ok = False

    return all_ok


async def main() -> None:
    print(f"\nSeed Sprint 8 — tenant: {TENANT_ID}")
    print("=" * 55)
    conn = await _get_conn()
    try:
        await seed_tenant(conn)
        rep_id = await seed_representante(conn)
        await seed_gestor(conn)
        await seed_cliente_b2b_com_representante(conn, rep_id)

        print("\nVerificação de estado:")
        ok = await verify_state(conn)

        if ok:
            print("\nSeed concluído com sucesso.")
            print("\nPróximos passos:")
            print("  1. ./scripts/deploy.sh staging")
            print("  2. alembic upgrade head  (se necessário)")
            print("  3. python -m integrations.jobs.sync_efos --tenant jmb")
            print("  4. python scripts/smoke_sprint_8.py")
        else:
            log.error("precondições_nao_satisfeitas", tenant=TENANT_ID)
            sys.exit(1)
    except Exception as exc:
        log.error("seed_falhou", error=str(exc))
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
