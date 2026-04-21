#!/usr/bin/env python3
"""smoke_sprint_6.py — Smoke gate Sprint 6 (Pre-Pilot Hardening).

Valida o caminho crítico completo contra infra real (staging).
Uso: infisical run --env=staging -- python scripts/smoke_sprint_6.py

Saída: "ALL OK" + exit 0 se tudo passou.
       Lista de falhas + exit 1 se algum teste falhou.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

BASE_URL = os.getenv("APP_HEALTH_URL", "http://localhost:8000")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
DASHBOARD_TENANT_ID = os.getenv("DASHBOARD_TENANT_ID", "jmb")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    results.append((name, ok, detail))


async def check_health() -> None:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/health", timeout=10)
        assert r.status_code == 200, f"status {r.status_code}"
        data = r.json()
        assert "components" in data, "campo 'components' ausente"
        anthropic_state = data["components"].get("anthropic", "unknown")
        assert anthropic_state in ("ok", "degraded"), f"Anthropic state inesperado: {anthropic_state}"
        record("G1-HEALTH-ANTHROPIC", True, f"anthropic={anthropic_state}")
    except Exception as e:
        record("G1-HEALTH-ANTHROPIC", False, str(e))


async def check_dashboard_login_ok() -> str | None:
    """Retorna cookie de sessão se login bem-sucedido."""
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            r = await client.post(
                f"{BASE_URL}/dashboard/login",
                data={"senha": DASHBOARD_SECRET},
                timeout=10,
            )
        assert r.status_code == 302, f"status {r.status_code}, esperado 302"
        cookie = r.cookies.get("dashboard_session")
        assert cookie, "cookie dashboard_session ausente após login"
        record("G2-DASHBOARD-LOGIN", True)
        return cookie
    except Exception as e:
        record("G2-DASHBOARD-LOGIN", False, str(e))
        return None


async def check_dashboard_home(cookie: str) -> None:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/dashboard/home",
                cookies={"dashboard_session": cookie},
                timeout=10,
            )
        assert r.status_code == 200, f"status {r.status_code}"
        assert "GMV" in r.text or "pedidos" in r.text.lower() or "dashboard" in r.text.lower(), \
            "Conteúdo esperado ausente"
        record("G3-DASHBOARD-HOME", True)
    except Exception as e:
        record("G3-DASHBOARD-HOME", False, str(e))


async def check_dashboard_clientes(cookie: str) -> None:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/dashboard/clientes",
                cookies={"dashboard_session": cookie},
                timeout=10,
            )
        assert r.status_code == 200, f"status {r.status_code}"
        record("G4-DASHBOARD-CLIENTES", True)
    except Exception as e:
        record("G4-DASHBOARD-CLIENTES", False, str(e))


async def check_top_produtos(cookie: str) -> None:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/dashboard/top-produtos",
                cookies={"dashboard_session": cookie},
                timeout=10,
            )
        assert r.status_code == 200, f"status {r.status_code}"
        assert 'href="/dashboard"' not in r.text, "Link /dashboard isolado encontrado (deve ser /dashboard/home)"
        assert 'href="/dashboard/home"' in r.text, "Link Voltar deve apontar para /dashboard/home"
        record("G5-TOP-PRODUTOS-LINK", True)
    except Exception as e:
        record("G5-TOP-PRODUTOS-LINK", False, str(e))


async def check_rate_limit_login() -> None:
    """Verifica que 6 tentativas de login com senha errada retorna 429."""
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            # Até 5 tentativas devem retornar 401
            for i in range(5):
                r = await client.post(
                    f"{BASE_URL}/dashboard/login",
                    data={"senha": "senha-errada-smoke"},
                    timeout=5,
                )
                # Pode ser 401 (senha errada) ou 429 (já rate limited de run anterior)
                assert r.status_code in (401, 429), f"Tentativa {i+1}: status inesperado {r.status_code}"
                if r.status_code == 429:
                    record("G6-RATE-LIMIT-LOGIN", True, "já rate limited (run anterior)")
                    return
            # 6ª deve retornar 429
            r = await client.post(
                f"{BASE_URL}/dashboard/login",
                data={"senha": "senha-errada-smoke"},
                timeout=5,
            )
            assert r.status_code == 429, f"6ª tentativa retornou {r.status_code}, esperado 429"
            record("G6-RATE-LIMIT-LOGIN", True)
    except Exception as e:
        record("G6-RATE-LIMIT-LOGIN", False, str(e))


async def check_precos_upload(cookie: str) -> None:
    """G7: POST /dashboard/precos/upload com fixture real."""
    import httpx
    import io
    try:
        import pandas as pd
        df = pd.DataFrame([
            {"codigo": "SKU-SMOKE-001", "cnpj": "12345678000195", "preco": "15.90"},
            {"codigo": "SKU-SMOKE-002", "cnpj": "98765432000100", "preco": "27.50"},
        ])
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        excel_bytes = buf.getvalue()
    except ImportError:
        record("G7-PRECOS-UPLOAD", False, "pandas não disponível — instalar para smoke")
        return

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/dashboard/precos/upload",
                files={"arquivo": ("precos_smoke.xlsx", excel_bytes,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                cookies={"dashboard_session": cookie},
                timeout=15,
            )
        assert r.status_code == 200, f"status {r.status_code}: {r.text[:200]}"
        assert "inseridos" in r.text.lower() or "sucesso" in r.text.lower() or any(
            c.isdigit() for c in r.text
        ), "Resposta não contém contagem de inserções"
        record("G7-PRECOS-UPLOAD", True)
    except Exception as e:
        record("G7-PRECOS-UPLOAD", False, str(e))


async def check_cliente_novo(cookie: str) -> str | None:
    """G8: POST /dashboard/clientes/novo cria cliente e aparece na lista."""
    import httpx
    import uuid
    cnpj_smoke = f"111{uuid.uuid4().int % 10**11:011d}"  # 14 dígitos únicos
    nome_smoke = f"Empresa Smoke {uuid.uuid4().hex[:6].upper()}"

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            r = await client.post(
                f"{BASE_URL}/dashboard/clientes/novo",
                data={"nome": nome_smoke, "cnpj": cnpj_smoke, "telefone": "", "representante_id": ""},
                cookies={"dashboard_session": cookie},
                timeout=10,
            )
        assert r.status_code == 302, f"criação retornou {r.status_code} (esperado 302)"
        record("G8-CLIENTE-NOVO-CRIA", True, f"CNPJ={cnpj_smoke}")

        # Verifica que o cliente aparece na listagem
        async with httpx.AsyncClient() as client:
            r2 = await client.get(
                f"{BASE_URL}/dashboard/clientes",
                cookies={"dashboard_session": cookie},
                timeout=10,
            )
        assert r2.status_code == 200
        assert nome_smoke in r2.text, f"Cliente '{nome_smoke}' não aparece em /dashboard/clientes"
        record("G8-CLIENTE-NOVO-VISIVEL", True)
        return cnpj_smoke
    except Exception as e:
        record("G8-CLIENTE-NOVO", False, str(e))
        return None


async def check_webhook_burst_429() -> None:
    """G9: 31º evento MESSAGES_UPSERT do mesmo remetente retorna 429."""
    import hashlib
    import hmac as hmac_lib
    import json
    import httpx

    webhook_secret = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")
    if not webhook_secret:
        record("G9-WEBHOOK-BURST-429", False, "EVOLUTION_WEBHOOK_SECRET não configurado")
        return

    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "inst-smoke-burst",
        "data": {
            "key": {"id": "msg-smoke-burst", "remoteJid": "5519000000099@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "smoke burst"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    }
    body = json.dumps(payload).encode()
    sig = hmac_lib.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient() as client:
            status_codes = []
            for _ in range(32):
                r = await client.post(
                    f"{BASE_URL}/webhook/whatsapp",
                    content=body,
                    headers={"Content-Type": "application/json", "X-Evolution-Signature": sig},
                    timeout=5,
                )
                status_codes.append(r.status_code)

        rate_limited = [s for s in status_codes if s == 429]
        ok_responses = [s for s in status_codes if s == 200]
        assert len(rate_limited) >= 1, f"Nenhum 429 após 32 eventos. Todos: {set(status_codes)}"
        record("G9-WEBHOOK-BURST-429", True, f"ok={len(ok_responses)} 429={len(rate_limited)}")
    except Exception as e:
        record("G9-WEBHOOK-BURST-429", False, str(e))


async def main() -> None:
    print(f"\nSmoke Sprint 6 — {BASE_URL}")
    print("=" * 50)

    await check_health()
    cookie = await check_dashboard_login_ok()

    if cookie:
        await asyncio.gather(
            check_dashboard_home(cookie),
            check_dashboard_clientes(cookie),
            check_top_produtos(cookie),
            check_precos_upload(cookie),
        )
        await check_cliente_novo(cookie)
    else:
        for name in ["G3-DASHBOARD-HOME", "G4-DASHBOARD-CLIENTES", "G5-TOP-PRODUTOS-LINK",
                     "G7-PRECOS-UPLOAD", "G8-CLIENTE-NOVO"]:
            record(name, False, "login falhou — pulado")

    await asyncio.gather(
        check_rate_limit_login(),
        check_webhook_burst_429(),
    )

    print("=" * 50)
    failed = [(n, d) for n, ok, d in results if not ok]
    if not failed:
        print("ALL OK")
        sys.exit(0)
    else:
        print(f"FALHAS ({len(failed)}):")
        for name, detail in failed:
            print(f"  - {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
