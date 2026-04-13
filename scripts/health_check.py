#!/usr/bin/env python3
"""
health_check.py — Verifica todos os servicos do ambiente
Uso: infisical run --env=dev -- python scripts/health_check.py
"""
import asyncio
import os
import sys


async def check_postgres():
    try:
        import asyncpg
        url = os.getenv("POSTGRES_URL", "").replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(url)
        await conn.execute("SELECT 1")
        await conn.close()
        return True, "PostgreSQL ok"
    except Exception as e:
        return False, f"PostgreSQL FALHOU: {e}"


async def check_redis():
    try:
        import redis.asyncio as redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        await r.ping()
        await r.aclose()
        return True, "Redis ok"
    except Exception as e:
        return False, f"Redis FALHOU: {e}"


async def check_evolution():
    try:
        import httpx
        url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/", timeout=5)
            return r.status_code < 500, f"Evolution API ok (status {r.status_code})"
    except Exception as e:
        return False, f"Evolution API FALHOU: {e}"


async def check_victoria_metrics():
    try:
        import httpx
        url = os.getenv("VICTORIA_METRICS_URL", "http://localhost:8428")
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/health", timeout=5)
            return r.status_code == 200, "VictoriaMetrics ok"
    except Exception as e:
        return False, f"VictoriaMetrics FALHOU: {e}"


async def check_victoria_logs():
    try:
        import httpx
        url = os.getenv("VICTORIA_LOGS_URL", "http://localhost:9428")
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/health", timeout=5)
            return r.status_code == 200, "VictoriaLogs ok"
    except Exception as e:
        return False, f"VictoriaLogs FALHOU: {e}"


async def main():
    checks = [
        check_postgres(),
        check_redis(),
        check_evolution(),
        check_victoria_metrics(),
        check_victoria_logs(),
    ]
    results = await asyncio.gather(*checks)
    all_ok = True
    for ok, msg in results:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {msg}")
        if not ok:
            all_ok = False
    print()
    if all_ok:
        print("Todos os servicos funcionando.")
        sys.exit(0)
    else:
        print("ATENCAO: Um ou mais servicos com problema.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
