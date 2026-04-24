#!/usr/bin/env python3
"""smoke_sprint_7.py — Smoke gate Sprint 7 (Notificação ao Gestor).

Valida o caminho crítico: health, gestor ativo no banco JMB, pytest unit.
Uso: infisical run --env=staging -- python scripts/smoke_sprint_7.py

Saída: "ALL OK" + exit 0 se tudo passou.
       "FAILED: [razão]" + exit 1 se algum teste falhou.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

BASE_URL = os.getenv("APP_HEALTH_URL", "http://100.113.28.85:8000")
# POSTGRES_URL vem do Infisical; asyncpg precisa de URL sem o prefixo "+asyncpg"
_pg_url = os.getenv("POSTGRES_URL", os.getenv("DATABASE_URL", ""))
DATABASE_URL = _pg_url.replace("postgresql+asyncpg://", "postgresql://")
JMB_TENANT_ID = os.getenv("DASHBOARD_TENANT_ID", "jmb")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    results.append((name, ok, detail))


async def check_health() -> None:
    """S1: GET /health → {"status": "ok"}."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/health", timeout=10)
        assert r.status_code == 200, f"status {r.status_code}"
        data = r.json()
        assert data.get("status") == "ok" or "components" in data, (
            f"Resposta inesperada: {data!r}"
        )
        record("S1-HEALTH", True, f"status={data.get('status', 'ok')}")
    except Exception as e:
        record("S1-HEALTH", False, str(e))


async def check_gestor_ativo() -> None:
    """S2: SELECT COUNT(*) FROM gestores WHERE tenant_id=JMB AND ativo=true → >= 1."""
    if not DATABASE_URL:
        record("S2-GESTOR-ATIVO", False, "DATABASE_URL não configurado")
        return
    try:
        import asyncpg  # type: ignore[import]
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM gestores WHERE tenant_id = $1 AND ativo = true",
                JMB_TENANT_ID,
            )
            assert count >= 1, (
                f"Nenhum gestor ativo para tenant_id='{JMB_TENANT_ID}' — "
                "inserir ao menos 1 gestor via dashboard antes do piloto"
            )
            record("S2-GESTOR-ATIVO", True, f"count={count} gestores ativos em tenant={JMB_TENANT_ID!r}")
        finally:
            await conn.close()
    except ImportError:
        record("S2-GESTOR-ATIVO", False, "asyncpg não disponível — instalar no staging")
    except Exception as e:
        record("S2-GESTOR-ATIVO", False, str(e))


def check_pytest_unit() -> None:
    """S3: pytest -m unit passa com 0 falhas."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "-m", "unit",
                "output/src/tests/unit/agents/",  # domínio afetado pelo Sprint 7
                "-q", "--tb=short",
                "--no-header",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if result.returncode == 0:
            # Extrai sumário (última linha relevante)
            lines = [l for l in output.splitlines() if l.strip()]
            summary = lines[-1] if lines else "passed"
            record("S3-PYTEST-UNIT", True, summary)
        else:
            # Extrai falhas
            fail_lines = [l for l in output.splitlines() if "FAILED" in l or "ERROR" in l]
            detail = "; ".join(fail_lines[:3]) if fail_lines else output[-300:]
            record("S3-PYTEST-UNIT", False, detail)
    except subprocess.TimeoutExpired:
        record("S3-PYTEST-UNIT", False, "timeout após 120s")
    except Exception as e:
        record("S3-PYTEST-UNIT", False, str(e))


async def main() -> None:
    print(f"\nSmoke Sprint 7 — Notificação ao Gestor")
    print(f"BASE_URL: {BASE_URL}")
    print(f"TENANT:   {JMB_TENANT_ID}")
    print("=" * 50)

    await check_health()
    await check_gestor_ativo()
    check_pytest_unit()

    print("=" * 50)
    failed = [(n, d) for n, ok, d in results if not ok]
    if not failed:
        print("ALL OK")
        sys.exit(0)
    else:
        print(f"FAILED ({len(failed)} checks):")
        for name, detail in failed:
            print(f"  - {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
