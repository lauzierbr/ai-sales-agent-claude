"""Seed de homologação Sprint 4 — AgentGestor + Dashboard.

Cria gestor de teste e pedidos antigos para clientes_inativos funcionar.
Garante que o número do gestor não colide com rep (5519000000001) nem cliente (5519992066177).

Uso:
    infisical run --env=staging -- python scripts/seed_homologacao_sprint4.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog

log = structlog.get_logger(__name__)

GESTOR_TELEFONE = "5519000000002"
GESTOR_NOME = "Lauzier Gestor Teste"
TENANT_ID = "jmb"
CLIENTE_TELEFONE = "5519992066177"  # José LZ Muzel — seed existente Sprint 1


async def seed() -> None:
    postgres_url = os.getenv("POSTGRES_URL", "")
    if not postgres_url:
        raise ValueError("POSTGRES_URL não configurada. Use: infisical run --env=staging -- ...")

    dsn = postgres_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        # 1. Upsert gestor de teste
        gestor_id = await conn.fetchval(
            """
            INSERT INTO gestores (tenant_id, telefone, nome, ativo)
            VALUES ($1, $2, $3, true)
            ON CONFLICT (tenant_id, telefone) DO UPDATE
                SET nome = EXCLUDED.nome, ativo = true
            RETURNING id
            """,
            TENANT_ID, GESTOR_TELEFONE, GESTOR_NOME,
        )
        log.info("gestor_seed_ok", gestor_id=gestor_id, telefone=GESTOR_TELEFONE)

        # 2. Obtém cliente para pedidos antigos
        cliente_row = await conn.fetchrow(
            "SELECT id FROM clientes_b2b WHERE tenant_id = $1 AND telefone = $2",
            TENANT_ID, CLIENTE_TELEFONE,
        )

        if cliente_row is None:
            log.warning("cliente_nao_encontrado", telefone=CLIENTE_TELEFONE,
                        msg="Seed do Sprint 1/2 deve ter criado este cliente. Execute seed anterior.")
        else:
            cliente_id = cliente_row["id"]

            # 3. Cria pedidos antigos (>31 dias) para clientes_inativos funcionar
            data_antiga = datetime.now(timezone.utc) - timedelta(days=35)
            for i in range(2):
                pedido_id = await conn.fetchval(
                    """
                    INSERT INTO pedidos (
                        tenant_id, cliente_b2b_id, status,
                        total_estimado, numero_pedido, criado_em
                    )
                    VALUES ($1, $2, 'pendente', 299.90, $3, $4)
                    RETURNING id
                    """,
                    TENANT_ID, cliente_id,
                    f"PED-SEED4-{i:03d}",
                    data_antiga - timedelta(days=i),
                )
                log.info("pedido_antigo_criado", pedido_id=pedido_id, dias_atras=35 + i)

        # 4. Summary
        n_gestores = await conn.fetchval(
            "SELECT COUNT(*) FROM gestores WHERE tenant_id = $1", TENANT_ID
        )
        n_pedidos = await conn.fetchval(
            "SELECT COUNT(*) FROM pedidos WHERE tenant_id = $1", TENANT_ID
        )
        n_clientes = await conn.fetchval(
            "SELECT COUNT(*) FROM clientes_b2b WHERE tenant_id = $1", TENANT_ID
        )

        print(f"\n=== SEED SPRINT 4 CONCLUÍDO ===")
        print(f"  Tenant:    {TENANT_ID}")
        print(f"  Gestores:  {n_gestores}")
        print(f"  Clientes:  {n_clientes}")
        print(f"  Pedidos:   {n_pedidos}")
        print(f"  Gestor de teste: {GESTOR_TELEFONE} ({GESTOR_NOME})")
        print(f"================================\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
