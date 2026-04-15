#!/usr/bin/env python3
"""Seed de dados reais para homologação do Sprint 2.

Executar no ambiente de staging APÓS deploy e migrations:

    cd ~/ai-sales-agent-claude/output
    export PYTHONPATH=.
    infisical run --env=staging -- python ../scripts/seed_homologacao_sprint2.py

O que este script faz:
1. Verifica que a instância WhatsApp do bot JMB existe em whatsapp_instancias
2. Insere José (LZ Muzel) como clientes_b2b com tenant_id=jmb
3. Confirma que o IdentityRouter retornará CLIENTE_B2B para o número de José

Números reais:
  Bot JMB:      5519991463559  (já deve estar em whatsapp_instancias)
  José LZ Muzel: 5519992066177  (inserido aqui como cliente B2B)
"""

from __future__ import annotations

import asyncio
import os
import sys

TENANT_ID = "jmb"
BOT_INSTANCIA_ID = "jmb-01"         # nome da instância na Evolution API
BOT_NUMERO = "5519991463559"        # número do bot E.164
CLIENTE_TELEFONE = "5519992066177"  # José LZ Muzel E.164
CLIENTE_NOME = "LZ Muzel"
CLIENTE_CNPJ = "00.000.000/0001-00"  # CNPJ placeholder — ajustar se real


async def main() -> None:
    """Executa o seed de homologação."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    postgres_url = os.getenv("POSTGRES_URL")
    if not postgres_url:
        print("❌  POSTGRES_URL não configurada. Execute via infisical run.")
        sys.exit(1)

    engine = create_async_engine(postgres_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=" * 60)
        print("  Seed Homologação Sprint 2")
        print("=" * 60)

        # ── 1. Verifica tenant JMB ───────────────────────────────────
        print(f"\n[1/4] Verificando tenant {TENANT_ID!r}...")
        result = await session.execute(
            text("SELECT id, nome FROM tenants WHERE id = :id"),
            {"id": TENANT_ID},
        )
        row = result.mappings().first()
        if row is None:
            print(f"❌  Tenant {TENANT_ID!r} não encontrado. Execute o provision do tenant primeiro.")
            sys.exit(1)
        print(f"     ✅  Tenant: {row['nome']} ({row['id']})")

        # ── 2. Verifica/registra instância WhatsApp do bot ──────────
        print(f"\n[2/4] Verificando instância WhatsApp bot ({BOT_NUMERO})...")
        result2 = await session.execute(
            text("SELECT instancia_id, numero_whatsapp, ativo FROM whatsapp_instancias WHERE instancia_id = :iid"),
            {"iid": BOT_INSTANCIA_ID},
        )
        row2 = result2.mappings().first()
        if row2 is None:
            print(f"     ⚠️   Instância {BOT_INSTANCIA_ID!r} não encontrada — criando...")
            await session.execute(
                text("""
                    INSERT INTO whatsapp_instancias (instancia_id, tenant_id, numero_whatsapp, ativo)
                    VALUES (:instancia_id, :tenant_id, :numero_whatsapp, true)
                    ON CONFLICT (instancia_id) DO NOTHING
                """),
                {
                    "instancia_id": BOT_INSTANCIA_ID,
                    "tenant_id": TENANT_ID,
                    "numero_whatsapp": BOT_NUMERO,
                },
            )
            print(f"     ✅  Instância criada: {BOT_INSTANCIA_ID} → {BOT_NUMERO}")
        else:
            status = "ativo" if row2["ativo"] else "⚠️ INATIVO"
            print(f"     ✅  Instância {row2['instancia_id']} | {row2['numero_whatsapp']} | {status}")
            if not row2["ativo"]:
                print("     ⚠️   Ativando instância...")
                await session.execute(
                    text("UPDATE whatsapp_instancias SET ativo = true WHERE instancia_id = :iid"),
                    {"iid": BOT_INSTANCIA_ID},
                )

        # ── 3. Insere José como cliente B2B ─────────────────────────
        print(f"\n[3/4] Configurando cliente B2B: {CLIENTE_NOME} ({CLIENTE_TELEFONE})...")
        result3 = await session.execute(
            text("""
                SELECT id, nome, telefone, ativo
                FROM clientes_b2b
                WHERE tenant_id = :tenant_id AND telefone = :telefone
            """),
            {"tenant_id": TENANT_ID, "telefone": CLIENTE_TELEFONE},
        )
        row3 = result3.mappings().first()
        if row3 is None:
            await session.execute(
                text("""
                    INSERT INTO clientes_b2b (tenant_id, nome, cnpj, telefone, ativo)
                    VALUES (:tenant_id, :nome, :cnpj, :telefone, true)
                """),
                {
                    "tenant_id": TENANT_ID,
                    "nome": CLIENTE_NOME,
                    "cnpj": CLIENTE_CNPJ,
                    "telefone": CLIENTE_TELEFONE,
                },
            )
            print(f"     ✅  Cliente inserido: {CLIENTE_NOME} | {CLIENTE_TELEFONE}")
        else:
            print(f"     ℹ️   Cliente já existe: {row3['nome']} | {row3['telefone']} | ativo={row3['ativo']}")
            if not row3["ativo"]:
                await session.execute(
                    text("""
                        UPDATE clientes_b2b SET ativo = true
                        WHERE tenant_id = :tenant_id AND telefone = :telefone
                    """),
                    {"tenant_id": TENANT_ID, "telefone": CLIENTE_TELEFONE},
                )
                print("     ✅  Cliente reativado.")

        # ── 4. Validação final ───────────────────────────────────────
        print("\n[4/4] Validação final...")
        result4 = await session.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM whatsapp_instancias WHERE tenant_id = :tid AND ativo = true) AS instancias_ativas,
                    (SELECT COUNT(*) FROM clientes_b2b WHERE tenant_id = :tid AND ativo = true) AS clientes_ativos,
                    (SELECT COUNT(*) FROM produtos WHERE tenant_id = :tid) AS n_produtos
            """),
            {"tid": TENANT_ID},
        )
        row4 = result4.mappings().first()
        if row4 is not None:
            print(f"     Instâncias ativas:  {row4['instancias_ativas']}")
            print(f"     Clientes B2B ativos: {row4['clientes_ativos']}")
            print(f"     Produtos no catálogo: {row4['n_produtos']}")

        await session.commit()

    print("\n" + "=" * 60)
    print("  Seed concluído com sucesso! ✅")
    print("=" * 60)
    print("""
Próximos passos:
  1. Verifique o health check: curl http://100.113.28.85:8000/health
  2. Abra o checklist:        docs/exec-plans/active/homologacao_sprint2.md
  3. Execute os cenários de teste enviando mensagens para o bot JMB:
       Bot JMB:  (19) 99146-3559
       Do número: (19) 99206-6177  (José LZ Muzel)
""")


if __name__ == "__main__":
    asyncio.run(main())
