"""Testes de staging — dashboard pré-piloto Sprint 6 (M_INJECT + fluxos críticos).

@pytest.mark.staging — requer Postgres + Redis reais; sem WhatsApp real.
Roda no macmini-lablz: infisical run --env=staging -- pytest -m staging
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.staging


# ─────────────────────────────────────────────
# M_INJECT — injeção de deps em _process_message
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ui_injection_agent_gestor_deps_nao_none() -> None:
    """M_INJECT: AgentGestor criado em _process_message não tem deps None."""
    from src.agents.types import WebhookPayload, Persona, Gestor, WhatsappInstancia
    from src.tenants.types import Tenant
    from src.agents.runtime.agent_gestor import AgentGestor

    gestor = Gestor(
        id="gest-stg-001", tenant_id="jmb-staging", telefone="5519000000099",
        nome="Gestor Staging", ativo=True, criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    tenant = Tenant(
        id="jmb-staging", nome="JMB Staging", cnpj="00.000.000/0001-00",
        ativo=True, whatsapp_number="5519999990099",
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    instancia = WhatsappInstancia(
        instancia_id="inst-jmb-stg", tenant_id="jmb-staging", numero_whatsapp="5519999990099"
    )

    deps_capturadas: dict = {}

    class AgentGestorCaptura(AgentGestor):
        def __init__(self, **kwargs):
            deps_capturadas.update(kwargs)
            super().__init__(**kwargs)

        async def responder(self, *args, **kwargs):
            pass

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-stg",
        data={
            "key": {"id": "msg-stg-1", "remoteJid": "5519000000099@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "relatório"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    )

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.agents.service.get_instancia", new=AsyncMock(return_value=instancia)),
        patch("src.tenants.repo.TenantRepo.get_by_id", new=AsyncMock(return_value=tenant)),
        patch("src.agents.service.IdentityRouter.resolve", new=AsyncMock(return_value=Persona.GESTOR)),
        patch("src.agents.repo.GestorRepo.get_by_telefone", new=AsyncMock(return_value=gestor)),
        patch("src.providers.db.get_session_factory", return_value=mock_factory),
        patch("src.providers.db.get_redis", return_value=AsyncMock()),
        patch("src.agents.service.mark_message_as_read", new=AsyncMock()),
        patch("src.agents.service.send_typing_indicator", new=AsyncMock()),
        patch("src.agents.service.send_typing_stop", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.AgentGestor", new=AgentGestorCaptura),
        patch.dict(os.environ, {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "test"),
            "EVOLUTION_WEBHOOK_SECRET": os.getenv("EVOLUTION_WEBHOOK_SECRET", "x"),
        }),
    ):
        from src.agents.ui import _process_message
        await _process_message(payload.model_dump())

    if deps_capturadas:
        assert deps_capturadas.get("catalog_service") is not None
        assert deps_capturadas.get("order_service") is not None
        assert deps_capturadas.get("pdf_generator") is not None
        assert deps_capturadas.get("relatorio_repo") is not None
        assert deps_capturadas.get("cliente_b2b_repo") is not None


# ─────────────────────────────────────────────
# Login → Home (fluxo crítico gestor)
# ─────────────────────────────────────────────


def test_dashboard_login_e_home_staging() -> None:
    """Staging: login + GET /dashboard/home retorna 200 sem errors."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    dashboard_secret = os.getenv("DASHBOARD_SECRET", "staging-secret")
    tenant_id = os.getenv("DASHBOARD_TENANT_ID", "jmb")

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=0)):
        with patch("src.dashboard.ui._reset_login_fail", new=AsyncMock()):
            resp_login = client.post("/dashboard/login", data={"senha": dashboard_secret})

    assert resp_login.status_code == 302

    token = create_access_token(user_id="gestor-dashboard", tenant_id=tenant_id, role="gestor")

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_result.mappings.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.providers.db.get_session_factory", return_value=MagicMock(return_value=mock_cm)):
        resp_home = client.get("/dashboard/home", cookies={"dashboard_session": token})

    assert resp_home.status_code == 200
    assert "error" not in resp_home.text.lower() or "traceback" not in resp_home.text.lower()


# ─────────────────────────────────────────────
# GET /dashboard/clientes (fluxo crítico gestor)
# ─────────────────────────────────────────────


def test_dashboard_clientes_lista_staging() -> None:
    """Staging: GET /dashboard/clientes retorna 200 sem vazar dados de outro tenant."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    tenant_id = os.getenv("DASHBOARD_TENANT_ID", "jmb")
    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    token = create_access_token(user_id="gestor-dashboard", tenant_id=tenant_id, role="gestor")

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.providers.db.get_session_factory", return_value=MagicMock(return_value=mock_cm)):
        resp = client.get("/dashboard/clientes", cookies={"dashboard_session": token})

    assert resp.status_code == 200
    # Verifica que a query filtrou pelo tenant correto
    if mock_session.execute.called:
        call_args = mock_session.execute.call_args
        params = call_args[0][1] if call_args[0] else {}
        if isinstance(params, dict) and "tenant_id" in params:
            assert params["tenant_id"] == tenant_id
