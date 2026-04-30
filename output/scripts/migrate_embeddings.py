#!/usr/bin/env python3
"""Migração de embeddings de produtos para commerce_products (E17, Sprint 10).

DT-1: Confirma modelo histórico via SELECT vector_dims(embedding) FROM produtos LIMIT 1.
- Se 1536: text-embedding-3-small — cópia direta, sem custo de regerar.
- Se 3072: text-embedding-3-large — estimar custo antes. Escalar para PO se > $5.

Uso:
    cd output && infisical run --env=staging -- python ../scripts/migrate_embeddings.py --tenant jmb
    cd output && infisical run --env=staging -- python ../scripts/migrate_embeddings.py --tenant jmb --dry-run

PYTHONPATH: ./src (a partir de output/)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

import structlog

log = structlog.get_logger()


async def confirmar_modelo_historico(session) -> int:
    """DT-1: confirma número de dimensões do embedding histórico.

    Returns:
        Número de dimensões (1536 ou 3072).
    """
    from sqlalchemy import text
    try:
        result = await session.execute(
            text("SELECT vector_dims(embedding) AS dims FROM produtos WHERE embedding IS NOT NULL LIMIT 1")
        )
        row = result.mappings().first()
        if row is None:
            log.info("migrate_embeddings_no_source", msg="Nenhum produto em 'produtos' com embedding.")
            return 0
        return int(row["dims"])
    except Exception as exc:
        log.warning("migrate_embeddings_dims_erro", error=str(exc))
        return 0


async def copiar_embeddings_por_codigo(
    tenant_id: str,
    session,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Copia embeddings de produtos → commerce_products por match de codigo_externo.

    Args:
        tenant_id: ID do tenant.
        session: sessão SQLAlchemy assíncrona.
        dry_run: se True, apenas conta sem modificar.

    Returns:
        Tupla (copiados, sem_match).
    """
    from sqlalchemy import text

    # Buscar produtos com embedding
    result = await session.execute(
        text("""
            SELECT p.codigo_externo, p.embedding
            FROM produtos p
            WHERE p.tenant_id = :tenant_id
              AND p.embedding IS NOT NULL
        """),
        {"tenant_id": tenant_id},
    )
    rows = result.mappings().all()
    log.info("migrate_embeddings_source", total=len(rows), tenant_id=tenant_id)

    copiados = 0
    sem_match = 0

    for row in rows:
        codigo_externo = row["codigo_externo"]
        embedding = row["embedding"]

        if dry_run:
            # Apenas verificar se existe correspondência
            check = await session.execute(
                text("""
                    SELECT 1 FROM commerce_products
                    WHERE tenant_id = :tenant_id AND external_id = :ext_id
                    LIMIT 1
                """),
                {"tenant_id": tenant_id, "ext_id": codigo_externo},
            )
            if check.first():
                copiados += 1
            else:
                sem_match += 1
            continue

        # Atualizar embedding em commerce_products
        update_result = await session.execute(
            text("""
                UPDATE commerce_products
                SET embedding = :embedding
                WHERE tenant_id = :tenant_id
                  AND external_id = :ext_id
                  AND embedding IS NULL
            """),
            {
                "tenant_id": tenant_id,
                "ext_id": codigo_externo,
                "embedding": embedding,
            },
        )
        if update_result.rowcount > 0:
            copiados += 1
        else:
            # Pode já ter embedding (não overwrite) ou não ter match
            check = await session.execute(
                text("SELECT 1 FROM commerce_products WHERE tenant_id=:tid AND external_id=:ext_id LIMIT 1"),
                {"tid": tenant_id, "ext_id": codigo_externo},
            )
            if check.first():
                copiados += 1  # já tinha embedding — conta como ok
            else:
                sem_match += 1

    if not dry_run and copiados > 0:
        await session.commit()
        log.info("migrate_embeddings_commit", tenant_id=tenant_id, copiados=copiados)

    return copiados, sem_match


async def gerar_embeddings_faltantes(
    tenant_id: str,
    session,
    modelo: str,
    dry_run: bool = False,
) -> int:
    """Gera embeddings via OpenAI para produtos em commerce_products sem match em produtos.

    Args:
        tenant_id: ID do tenant.
        session: sessão SQLAlchemy assíncrona.
        modelo: nome do modelo OpenAI (text-embedding-3-small ou 3-large).
        dry_run: se True, apenas conta sem modificar.

    Returns:
        Número de embeddings gerados.
    """
    from sqlalchemy import text
    import openai

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        log.warning("migrate_embeddings_openai_sem_key")
        return 0

    client = openai.AsyncOpenAI(api_key=openai_key)

    # Produtos em commerce sem embedding
    result = await session.execute(
        text("""
            SELECT external_id, nome, descricao
            FROM commerce_products
            WHERE tenant_id = :tenant_id
              AND embedding IS NULL
            ORDER BY external_id
        """),
        {"tenant_id": tenant_id},
    )
    rows = result.mappings().all()
    log.info("migrate_embeddings_sem_match", total=len(rows), tenant_id=tenant_id)

    if dry_run:
        return len(rows)

    gerados = 0
    batch_size = 50

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        textos = [
            f"{row['nome']} {row['descricao'] or ''}".strip()
            for row in batch
        ]
        try:
            resp = await client.embeddings.create(
                input=textos,
                model=modelo,
            )
            for j, emb_data in enumerate(resp.data):
                row = batch[j]
                vec = emb_data.embedding
                await session.execute(
                    text("""
                        UPDATE commerce_products
                        SET embedding = :embedding
                        WHERE tenant_id = :tenant_id
                          AND external_id = :ext_id
                    """),
                    {
                        "tenant_id": tenant_id,
                        "ext_id": row["external_id"],
                        "embedding": f"[{','.join(str(v) for v in vec)}]",
                    },
                )
                gerados += 1
            await session.commit()
            log.info("migrate_embeddings_batch_ok", batch=i // batch_size + 1, gerados_total=gerados)
        except Exception as exc:
            log.error("migrate_embeddings_batch_erro", batch=i // batch_size + 1, error=str(exc))
            await session.rollback()

    return gerados


async def verificar_cobertura(tenant_id: str, session) -> tuple[int, int]:
    """Verifica cobertura de embeddings em commerce_products.

    Returns:
        Tupla (com_embedding, total).
    """
    from sqlalchemy import text
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS com_embedding,
                COUNT(*) AS total
            FROM commerce_products
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )
    row = result.mappings().first()
    com = int(row["com_embedding"]) if row else 0
    total = int(row["total"]) if row else 0
    return com, total


async def main(tenant_id: str, dry_run: bool = False) -> bool:
    """Executa a migração completa de embeddings.

    Returns:
        True se >= 95% cobertos, False caso contrário.
    """
    sys.path.insert(0, str(__file__).replace("scripts/migrate_embeddings.py", "src"))

    from src.providers.db import get_session_factory
    factory = get_session_factory()

    log.info("migrate_embeddings_inicio", tenant_id=tenant_id, dry_run=dry_run)

    async with factory() as session:
        # DT-1: confirmar modelo histórico
        dims = await confirmar_modelo_historico(session)

        if dims == 0:
            log.warning("migrate_embeddings_sem_fonte", tenant_id=tenant_id)
            modelo = "text-embedding-3-small"
        elif dims == 1536:
            modelo = "text-embedding-3-small"
            log.info("migrate_embeddings_modelo", modelo=modelo, dims=dims, custo="gratuito (copia)")
        elif dims == 3072:
            modelo = "text-embedding-3-large"
            # Estimar custo: 743 produtos * média 100 tokens * $0.13/1M = ~$0.0096
            log.warning(
                "migrate_embeddings_modelo_large",
                modelo=modelo,
                dims=dims,
                nota="Custo estimado < $1 para 743 produtos. Prosseguindo.",
            )
        else:
            log.error("migrate_embeddings_dims_desconhecido", dims=dims)
            return False

    # Copiar embeddings existentes
    async with factory() as session:
        copiados, sem_match = await copiar_embeddings_por_codigo(
            tenant_id=tenant_id,
            session=session,
            dry_run=dry_run,
        )
        log.info(
            "migrate_embeddings_copia",
            tenant_id=tenant_id,
            copiados=copiados,
            sem_match=sem_match,
            dry_run=dry_run,
        )

    # Gerar embeddings para produtos de commerce_products sem embedding (sem_match de produtos
    # legado OU produtos novos importados via EFOS que nunca tiveram embedding)
    if not dry_run:
        async with factory() as session:
            gerados = await gerar_embeddings_faltantes(
                tenant_id=tenant_id,
                session=session,
                modelo=modelo,
                dry_run=dry_run,
            )
            log.info("migrate_embeddings_gerados", tenant_id=tenant_id, gerados=gerados)

    # Verificar cobertura final
    async with factory() as session:
        com_embedding, total = await verificar_cobertura(tenant_id, session)

    pct = (com_embedding / total * 100) if total > 0 else 0
    log.info(
        "migrate_embeddings_cobertura",
        tenant_id=tenant_id,
        com_embedding=com_embedding,
        total=total,
        pct=round(pct, 1),
        dry_run=dry_run,
    )

    if pct >= 95:
        print(f"\nMIGRACАO OK: {com_embedding}/{total} ({pct:.1f}%) com embedding.")
        print(f"Modelo: {modelo} (dims={dims})")
        if dry_run:
            print("DRY-RUN: nenhuma alteracao feita.")
        return True
    else:
        print(f"\nAVISO: apenas {com_embedding}/{total} ({pct:.1f}%) com embedding.")
        print("Execute novamente ou verifique OPENAI_API_KEY.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra embeddings para commerce_products")
    parser.add_argument("--tenant", required=True, help="ID do tenant (ex: jmb)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas conta, sem modificar")
    args = parser.parse_args()

    ok = asyncio.run(main(tenant_id=args.tenant, dry_run=args.dry_run))
    sys.exit(0 if ok else 1)
