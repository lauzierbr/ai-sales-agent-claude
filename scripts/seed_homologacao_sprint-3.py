"""Seed de homologação Sprint 3 — AgentRep.

Cria representante de teste e vincula cliente da carteira para permitir
execução do staging smoke e da homologação manual via WhatsApp.

Uso:
    infisical run --env=staging -- python scripts/seed_homologacao_sprint-3.py
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import structlog

log = structlog.get_logger(__name__)

REP_TELEFONE = "5519000000001"
REP_NOME = "Rep Teste Sprint3"
TENANT_ID = "jmb"
CLIENTE_TELEFONE = "5519992066177"  # José LZ Muzel — seed existente Sprint 1


async def seed() -> None:
    postgres_url = os.getenv("POSTGRES_URL", "")
    if not postgres_url:
        raise ValueError("POSTGRES_URL não configurada. Use: infisical run --env=staging -- ...")

    # asyncpg não aceita o prefixo postgresql+asyncpg
    dsn = postgres_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        # 1. Upsert representante de teste
        rep_id = await conn.fetchval(
            """
            INSERT INTO representantes (tenant_id, telefone, nome, ativo)
            VALUES ($1, $2, $3, true)
            ON CONFLICT (tenant_id, telefone) DO UPDATE
                SET nome = EXCLUDED.nome, ativo = true
            RETURNING id
            """,
            TENANT_ID, REP_TELEFONE, REP_NOME,
        )
        log.info("rep_seed_ok", rep_id=rep_id, telefone=REP_TELEFONE)

        # 2. Vincula cliente existente à carteira do rep
        updated = await conn.execute(
            """
            UPDATE clientes_b2b
            SET representante_id = $1
            WHERE tenant_id = $2 AND telefone = $3
            """,
            rep_id, TENANT_ID, CLIENTE_TELEFONE,
        )
        log.info("cliente_vinculado", cliente_telefone=CLIENTE_TELEFONE, updated=updated)

        # 3. Verifica
        row = await conn.fetchrow(
            """
            SELECT c.nome, c.representante_id, r.nome AS rep_nome
            FROM clientes_b2b c
            JOIN representantes r ON r.id = c.representante_id
            WHERE c.tenant_id = $1 AND c.telefone = $2
            """,
            TENANT_ID, CLIENTE_TELEFONE,
        )
        if row:
            log.info("seed_verificado", cliente=row["nome"], rep=row["rep_nome"])
        else:
            log.warning("seed_verificacao_falhou", cliente_telefone=CLIENTE_TELEFONE)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
