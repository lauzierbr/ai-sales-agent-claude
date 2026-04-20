"""Seed de homologação Sprint 4 — AgentGestor + Dashboard.

Cria gestor de teste e pedidos antigos para clientes_inativos funcionar.
Também define telefone de teste para LZ Muzel (H7 — isolamento cliente vs rep).

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

# Número de teste para LZ Muzel — NÃO deve estar em representantes
# Permite homologação H7: este número → CLIENTE_B2B, não REPRESENTANTE
CLIENTE_TESTE_TELEFONE = "5519991111111"


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

        # 2. Busca LZ Muzel por nome (não por telefone — telefone pode ser NULL)
        cliente_row = await conn.fetchrow(
            "SELECT id, telefone FROM clientes_b2b WHERE tenant_id = $1 AND nome ILIKE $2 LIMIT 1",
            TENANT_ID, "%muzel%",
        )

        if cliente_row is None:
            log.warning("cliente_muzel_nao_encontrado",
                        msg="Nenhum cliente com 'muzel' no nome. Verifique o seed anterior.")
        else:
            cliente_id = cliente_row["id"]
            telefone_atual = cliente_row["telefone"]

            # 2a. Atualiza telefone de LZ Muzel para número de teste (H7)
            if telefone_atual != CLIENTE_TESTE_TELEFONE:
                await conn.execute(
                    "UPDATE clientes_b2b SET telefone = $1 WHERE id = $2",
                    CLIENTE_TESTE_TELEFONE, cliente_id,
                )
                log.info("cliente_telefone_atualizado",
                         cliente_id=cliente_id, novo_telefone=CLIENTE_TESTE_TELEFONE)

            # 3. Cria pedidos antigos (>31 dias) para clientes_inativos funcionar (H4)
            # Verifica se já existem pedidos antigos para evitar duplicatas
            n_antigos = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pedidos
                WHERE tenant_id = $1 AND cliente_b2b_id = $2
                AND criado_em < NOW() - INTERVAL '30 days'
                """,
                TENANT_ID, cliente_id,
            )

            if n_antigos < 2:
                data_antiga = datetime.now(timezone.utc) - timedelta(days=35)
                for i in range(2):
                    pedido_id = await conn.fetchval(
                        """
                        INSERT INTO pedidos (
                            tenant_id, cliente_b2b_id, status,
                            total_estimado, criado_em
                        )
                        VALUES ($1, $2, 'pendente', 299.90, $3)
                        RETURNING id
                        """,
                        TENANT_ID, cliente_id,
                        data_antiga - timedelta(days=i),
                    )
                    log.info("pedido_antigo_criado", pedido_id=pedido_id, dias_atras=35 + i)
            else:
                log.info("pedidos_antigos_ja_existem", count=n_antigos)

        # 4. Verifica se representante "João" (5519992066177) ainda está em gestores (não deve)
        gestor_joao = await conn.fetchrow(
            "SELECT id FROM gestores WHERE tenant_id = $1 AND telefone = $2",
            TENANT_ID, "5519992066177",
        )
        if gestor_joao:
            log.warning("gestor_colisao_joao",
                        msg="5519992066177 está em GESTORES além de REPRESENTANTES — IdentityRouter retornará GESTOR")

        # 5. Summary
        n_gestores = await conn.fetchval(
            "SELECT COUNT(*) FROM gestores WHERE tenant_id = $1", TENANT_ID
        )
        n_pedidos = await conn.fetchval(
            "SELECT COUNT(*) FROM pedidos WHERE tenant_id = $1", TENANT_ID
        )
        n_clientes = await conn.fetchval(
            "SELECT COUNT(*) FROM clientes_b2b WHERE tenant_id = $1", TENANT_ID
        )
        n_inativos = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM clientes_b2b c
            WHERE c.tenant_id = $1
            AND NOT EXISTS (
                SELECT 1 FROM pedidos p
                WHERE p.tenant_id = $1
                AND p.cliente_b2b_id = c.id
                AND p.criado_em >= NOW() - INTERVAL '30 days'
            )
            """,
            TENANT_ID,
        )

        print(f"\n=== SEED SPRINT 4 CONCLUÍDO ===")
        print(f"  Tenant:        {TENANT_ID}")
        print(f"  Gestores:      {n_gestores}")
        print(f"  Clientes:      {n_clientes}")
        print(f"  Pedidos total: {n_pedidos}")
        print(f"  Inativos >30d: {n_inativos}  ← deve ser ≥1 para H4")
        print(f"  Gestor teste:  {GESTOR_TELEFONE} ({GESTOR_NOME})")
        print(f"  Cliente teste: LZ Muzel → telefone={CLIENTE_TESTE_TELEFONE} (para H7)")
        print(f"================================\n")

        if n_inativos == 0:
            print("⚠️  ATENÇÃO: n_inativos=0. H4 pode falhar.")
            print("   Verifique se pedidos antigos foram inseridos corretamente.\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
