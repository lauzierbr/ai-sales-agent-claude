#!/usr/bin/env python3
"""seed_homologacao_sprint-6.py — Seed de dados para homologação Sprint 6.

Insere dados mínimos necessários para testar todos os fluxos do Sprint 6.
Uso: infisical run --env=staging -- python scripts/seed_homologacao_sprint-6.py

Pré-condição: banco staging na migração 0017.
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
    import asyncpg
    url = os.getenv("POSTGRES_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url)


async def seed_representante(conn) -> str:
    """Garante que existe pelo menos um representante ativo no tenant."""
    row = await conn.fetchrow(
        "SELECT id FROM representantes WHERE tenant_id = $1 AND ativo = true LIMIT 1",
        TENANT_ID,
    )
    if row:
        log.info("representante_ja_existe", id=str(row["id"]))
        return str(row["id"])

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
        "Representante Seed Sprint 6",
        datetime.now(timezone.utc),
    )
    log.info("representante_criado", id=rep_id)
    return rep_id


async def seed_cliente_b2b(conn, representante_id: str) -> str:
    """Garante que existe pelo menos um cliente B2B ativo no tenant."""
    row = await conn.fetchrow(
        "SELECT id FROM clientes_b2b WHERE tenant_id = $1 AND ativo = true LIMIT 1",
        TENANT_ID,
    )
    if row:
        log.info("cliente_b2b_ja_existe", id=str(row["id"]))
        return str(row["id"])

    cliente_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO clientes_b2b (id, tenant_id, nome, cnpj, telefone, representante_id, ativo, criado_em)
        VALUES ($1, $2, $3, $4, $5, $6, true, $7)
        ON CONFLICT DO NOTHING
        """,
        cliente_id,
        TENANT_ID,
        "Empresa Seed Sprint 6",
        "11222333000181",
        "5511900000002",
        representante_id,
        datetime.now(timezone.utc),
    )
    log.info("cliente_b2b_criado", id=cliente_id)
    return cliente_id


async def seed_pedido(conn, cliente_id: str) -> str:
    """Garante que existe pelo menos um pedido no tenant para o dashboard."""
    row = await conn.fetchrow(
        "SELECT id FROM pedidos WHERE tenant_id = $1 LIMIT 1",
        TENANT_ID,
    )
    if row:
        log.info("pedido_ja_existe", id=str(row["id"]))
        return str(row["id"])

    pedido_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO pedidos (id, tenant_id, cliente_b2b_id, status, total_estimado, criado_em)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT DO NOTHING
        """,
        pedido_id,
        TENANT_ID,
        cliente_id,
        "confirmado",
        1500.00,
        datetime.now(timezone.utc),
    )
    log.info("pedido_criado", id=pedido_id)
    return pedido_id


async def verify_state(conn) -> None:
    """Verifica precondições do ambiente após seed."""
    checks = {
        "tenant_ativo": await conn.fetchval(
            "SELECT COUNT(*) FROM tenants WHERE id = $1 AND ativo = true", TENANT_ID
        ),
        "representantes_ativos": await conn.fetchval(
            "SELECT COUNT(*) FROM representantes WHERE tenant_id = $1 AND ativo = true", TENANT_ID
        ),
        "clientes_b2b_ativos": await conn.fetchval(
            "SELECT COUNT(*) FROM clientes_b2b WHERE tenant_id = $1 AND ativo = true", TENANT_ID
        ),
        "pedidos": await conn.fetchval(
            "SELECT COUNT(*) FROM pedidos WHERE tenant_id = $1", TENANT_ID
        ),
    }
    all_ok = True
    for check, value in checks.items():
        status = "OK" if value and value > 0 else "FAIL"
        print(f"  [{status}] {check}: {value}")
        if not (value and value > 0):
            all_ok = False
    if not all_ok:
        raise RuntimeError("Precondições de homologação não satisfeitas")


async def main() -> None:
    print(f"\nSeed Sprint 6 — tenant: {TENANT_ID}")
    print("=" * 50)
    conn = await _get_conn()
    try:
        rep_id = await seed_representante(conn)
        cliente_id = await seed_cliente_b2b(conn, rep_id)
        await seed_pedido(conn, cliente_id)
        print("\nVerificação de estado:")
        await verify_state(conn)
        print("\nSeed concluído com sucesso.")
    except Exception as e:
        log.error("seed_falhou", error=str(e))
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
