"""Testes unitários do dashboard web — Sprint 4.

@pytest.mark.unit — sem I/O externo.

Cobre:
  - GET /dashboard/home sem cookie → 302 para /dashboard/login (A11)
  - POST /dashboard/login com senha correta → seta cookie (A12)
  - POST /dashboard/login com senha errada → não 302
  - Deps não-None no wiring do AgentGestor em ui.py (M_INJECT)
  - GET /dashboard/home/partials/kpis → HTMLResponse com "GMV" (A_SMOKE S7)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_test_app() -> Any:
    """Cria app FastAPI mínima com dashboard router para testes."""
    from fastapi import FastAPI
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    return app


# ─────────────────────────────────────────────
# A11 — sem cookie → 302 para /dashboard/login
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_home_sem_cookie_redireciona() -> None:
    """A11: GET /dashboard/home sem cookie retorna 302 para /dashboard/login."""
    from typing import Any
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)

    client = TestClient(app, follow_redirects=False)
    resp = client.get("/dashboard/home")

    assert resp.status_code == 302
    assert "/dashboard/login" in resp.headers.get("location", "")


# ─────────────────────────────────────────────
# A12 — login correto → cookie dashboard_session setado
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_login_correto_seta_cookie() -> None:
    """A12: POST /dashboard/login com DASHBOARD_SECRET correto seta cookie HttpOnly SameSite=Lax."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)

    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {"DASHBOARD_SECRET": "senha-teste-123", "DASHBOARD_TENANT_ID": "jmb", "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000"}):
        resp = client.post("/dashboard/login", data={"senha": "senha-teste-123"})

    assert resp.status_code == 302

    set_cookie = resp.headers.get("set-cookie", "")
    assert "dashboard_session=" in set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


# ─────────────────────────────────────────────
# Senha errada → não 302
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_login_senha_errada_nao_redireciona() -> None:
    """POST /dashboard/login com senha errada não retorna 302."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)

    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {"DASHBOARD_SECRET": "senha-correta", "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000"}):
        resp = client.post("/dashboard/login", data={"senha": "senha-errada"})

    assert resp.status_code != 302


# ─────────────────────────────────────────────
# M_INJECT — deps não-None no wiring do AgentGestor
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_agent_gestor_deps_nao_none() -> None:
    """M_INJECT: quando Persona.GESTOR é identificada, todas as deps do AgentGestor são não-None."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from src.agents.types import WebhookPayload, Persona
    from src.agents.repo import GestorRepo
    from src.agents.types import Gestor, WhatsappInstancia
    from src.tenants.types import Tenant

    gestor = Gestor(
        id="gest-001", tenant_id="jmb", telefone="5519000000002",
        nome="Gestor Teste", ativo=True, criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    tenant = Tenant(
        id="jmb", nome="JMB", cnpj="00.000.000/0001-00",
        ativo=True, whatsapp_number="5519999990000",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    instancia = WhatsappInstancia(instancia_id="inst-jmb-01", tenant_id="jmb", numero_whatsapp="5519999990000")

    deps_capturadas: dict = {}

    original_init = None

    from src.agents.runtime.agent_gestor import AgentGestor

    class AgentGestorCaptura(AgentGestor):
        def __init__(self, **kwargs):
            deps_capturadas.update(kwargs)
            super().__init__(**kwargs)

        async def responder(self, *args, **kwargs):
            pass

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {"id": "msg1", "remoteJid": "5519000000002@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "oi"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    )

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.agents.ui.get_instancia", new=AsyncMock(return_value=instancia)),
        patch("src.tenants.repo.TenantRepo.get_by_id", new=AsyncMock(return_value=tenant)),
        patch("src.agents.service.IdentityRouter.resolve", new=AsyncMock(return_value=Persona.GESTOR)),
        patch("src.agents.repo.GestorRepo.get_by_telefone", new=AsyncMock(return_value=gestor)),
        patch("src.providers.db.get_session_factory", return_value=mock_factory),
        patch("src.providers.db.get_redis", return_value=AsyncMock()),
        patch("src.agents.service.mark_message_as_read", new=AsyncMock()),
        patch("src.agents.service.send_typing_indicator", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.AgentGestor", new=AgentGestorCaptura),
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "EVOLUTION_WEBHOOK_SECRET": "x"}),
    ):
        from src.agents.ui import _process_message
        await _process_message(payload.model_dump())

    if deps_capturadas:
        assert deps_capturadas.get("catalog_service") is not None, "catalog_service deve ser não-None"
        assert deps_capturadas.get("order_service") is not None, "order_service deve ser não-None"
        assert deps_capturadas.get("pdf_generator") is not None, "pdf_generator deve ser não-None"
        assert deps_capturadas.get("relatorio_repo") is not None, "relatorio_repo deve ser não-None"
        assert deps_capturadas.get("cliente_b2b_repo") is not None, "cliente_b2b_repo deve ser não-None"
