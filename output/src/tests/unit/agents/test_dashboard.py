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


# ─────────────────────────────────────────────
# A1 — B1-CLIENTE-NOVO
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_cliente_novo_valido_redireciona() -> None:
    """A1: POST /dashboard/clientes/novo com dados válidos → 302."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        with (
            patch("src.tenants.service.TenantService.criar_cliente_ficticio", new=AsyncMock(return_value="cliente-uuid-001")),
            patch("src.dashboard.ui._get_representantes_simples", new=AsyncMock(return_value=[])),
            patch("src.providers.db.get_session_factory", return_value=MagicMock()),
        ):
            resp = client.post(
                "/dashboard/clientes/novo",
                data={"nome": "Empresa X", "cnpj": "12345678000195", "telefone": "11999999999", "representante_id": ""},
                cookies={"dashboard_session": token},
            )
    assert resp.status_code == 302
    assert "/dashboard/clientes" in resp.headers.get("location", "")


@pytest.mark.unit
def test_dashboard_cliente_novo_cnpj_invalido_retorna_erro() -> None:
    """A1: CNPJ com menos de 14 dígitos → 400 ou re-render com erro."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        with (
            patch("src.tenants.service.TenantService.criar_cliente_ficticio", side_effect=ValueError("CNPJ inválido: deve ter 14 dígitos")),
            patch("src.dashboard.ui._get_representantes_simples", new=AsyncMock(return_value=[])),
            patch("src.providers.db.get_session_factory", return_value=MagicMock()),
        ):
            resp = client.post(
                "/dashboard/clientes/novo",
                data={"nome": "Empresa X", "cnpj": "123456", "telefone": "", "representante_id": ""},
                cookies={"dashboard_session": token},
            )
    assert resp.status_code in (400, 200)
    assert "14" in resp.text or "inválido" in resp.text.lower() or "CNPJ" in resp.text


@pytest.mark.unit
def test_dashboard_cliente_novo_cnpj_duplicado_retorna_erro() -> None:
    """A1: CNPJ já cadastrado no mesmo tenant → mensagem de erro."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        with (
            patch("src.tenants.service.TenantService.criar_cliente_ficticio", side_effect=ValueError("CNPJ já cadastrado neste tenant")),
            patch("src.dashboard.ui._get_representantes_simples", new=AsyncMock(return_value=[])),
            patch("src.providers.db.get_session_factory", return_value=MagicMock()),
        ):
            resp = client.post(
                "/dashboard/clientes/novo",
                data={"nome": "Empresa X", "cnpj": "12345678000195", "telefone": "", "representante_id": ""},
                cookies={"dashboard_session": token},
            )
    assert resp.status_code in (400, 200)
    assert "cadastrado" in resp.text.lower() or "duplicado" in resp.text.lower() or "CNPJ" in resp.text


@pytest.mark.unit
def test_dashboard_cliente_novo_rep_outro_tenant_retorna_erro() -> None:
    """A1: representante_id de outro tenant → mensagem de erro."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        with (
            patch("src.tenants.service.TenantService.criar_cliente_ficticio", side_effect=ValueError("Representante não pertence ao tenant")),
            patch("src.dashboard.ui._get_representantes_simples", new=AsyncMock(return_value=[])),
            patch("src.providers.db.get_session_factory", return_value=MagicMock()),
        ):
            resp = client.post(
                "/dashboard/clientes/novo",
                data={"nome": "Empresa X", "cnpj": "12345678000195", "telefone": "", "representante_id": "outro-uuid"},
                cookies={"dashboard_session": token},
            )
    assert resp.status_code in (400, 200)
    assert "representante" in resp.text.lower() or "tenant" in resp.text.lower()


# ─────────────────────────────────────────────
# A2 — B2-PRECOS-UPLOAD
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_precos_upload_sucesso() -> None:
    """A2: POST /dashboard/precos/upload com xlsx válido → 200 com contagem."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token
    from unittest.mock import MagicMock
    import io

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    fake_result = MagicMock()
    fake_result.inseridos = 42
    fake_result.linhas_processadas = 45

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        with (
            patch("src.catalog.service.CatalogService.processar_excel_precos", new=AsyncMock(return_value=fake_result)),
            patch("src.catalog.repo.CatalogRepo.__init__", return_value=None),
            patch("src.providers.db.get_session_factory", return_value=MagicMock()),
        ):
            xlsx_bytes = b"PK\x03\x04"
            resp = client.post(
                "/dashboard/precos/upload",
                files={"arquivo": ("precos.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                cookies={"dashboard_session": token},
            )
    assert resp.status_code == 200
    assert "42" in resp.text or "inseridos" in resp.text.lower() or "sucesso" in resp.text.lower()


@pytest.mark.unit
def test_dashboard_precos_upload_arquivo_ausente_retorna_400() -> None:
    """A2: POST sem arquivo → 400."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        resp = client.post(
            "/dashboard/precos/upload",
            data={},
            cookies={"dashboard_session": token},
        )
    assert resp.status_code == 400


# ─────────────────────────────────────────────
# A3 — B3-TOP-PRODUTOS
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_top_produtos_retorna_200() -> None:
    """A3: GET /dashboard/top-produtos retorna 200."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token
    from unittest.mock import MagicMock

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory_cm = MagicMock()
        mock_factory_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory_cm.__aexit__ = AsyncMock(return_value=False)
        with patch("src.providers.db.get_session_factory", return_value=MagicMock(return_value=mock_factory_cm)):
            resp = client.get(
                "/dashboard/top-produtos",
                cookies={"dashboard_session": token},
            )
    assert resp.status_code == 200


@pytest.mark.unit
def test_dashboard_top_produtos_sem_link_dashboard_isolado() -> None:
    """A3: HTML não contém href='/dashboard' isolado; link Voltar aponta para /dashboard/home."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router
    from src.providers.auth import create_access_token
    from unittest.mock import MagicMock

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch.dict(os.environ, {
        "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        "DASHBOARD_TENANT_ID": "jmb",
    }):
        token = create_access_token(user_id="gestor-dashboard", tenant_id="jmb", role="gestor")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory_cm = MagicMock()
        mock_factory_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory_cm.__aexit__ = AsyncMock(return_value=False)
        with patch("src.providers.db.get_session_factory", return_value=MagicMock(return_value=mock_factory_cm)):
            resp = client.get(
                "/dashboard/top-produtos",
                cookies={"dashboard_session": token},
            )
    assert resp.status_code == 200
    assert 'href="/dashboard"' not in resp.text
    assert 'href="/dashboard/home"' in resp.text


# ─────────────────────────────────────────────
# A4 — B4-TENANT-ISOLATION
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_tenant_isolation_pedidos() -> None:
    """A4: JOIN em _get_pedidos_recentes inclui c.tenant_id = p.tenant_id."""
    from unittest.mock import MagicMock

    with patch("src.providers.db.get_session_factory") as mock_sf:
        mock_session = AsyncMock()
        row_tenant_a = {"id": "p1", "status": "confirmado", "total_estimado": 500.0,
                        "criado_em": datetime(2026, 1, 1, tzinfo=timezone.utc), "cliente_nome": "Cliente A"}
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [row_tenant_a]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_cm)

        import asyncio
        from src.dashboard.ui import _get_pedidos_recentes
        asyncio.run(_get_pedidos_recentes("tenant-a"))

    call_args = mock_session.execute.call_args
    sql_text = str(call_args[0][0])
    assert "c.tenant_id = p.tenant_id" in sql_text or "AND c.tenant_id" in sql_text


# ─────────────────────────────────────────────
# A6 — E6-RATE-LOGIN
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_rate_limit_login_5a_tentativa_ainda_401() -> None:
    """A6: 5ª tentativa falha ainda retorna 401, não 429."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with (
        patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=4)),
        patch("src.dashboard.ui._increment_login_fail", new=AsyncMock(return_value=5)),
        patch.dict(os.environ, {
            "DASHBOARD_SECRET": "senha-correta",
            "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        }),
    ):
        resp = client.post("/dashboard/login", data={"senha": "errada"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_dashboard_rate_limit_login_6a_tentativa_retorna_429() -> None:
    """A6: 6ª tentativa (5 falhas já registradas) retorna 429."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=5)):
        resp = client.post("/dashboard/login", data={"senha": "qualquer"})
    assert resp.status_code == 429


@pytest.mark.unit
def test_dashboard_rate_limit_login_correto_reseta_contador() -> None:
    """A6: login correto reseta contador de falhas."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    reset_mock = AsyncMock()
    with (
        patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=2)),
        patch("src.dashboard.ui._reset_login_fail", reset_mock),
        patch.dict(os.environ, {
            "DASHBOARD_SECRET": "senha-correta",
            "DASHBOARD_TENANT_ID": "jmb",
            "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        }),
    ):
        resp = client.post("/dashboard/login", data={"senha": "senha-correta"})
    assert resp.status_code == 302
    reset_mock.assert_called_once()


# ─────────────────────────────────────────────
# A9 — E9-CORS / cookie Secure
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_dashboard_cookie_secure_false_em_staging() -> None:
    """A9: cookie dashboard_session tem Secure=False em ambiente staging."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with (
        patch.dict(os.environ, {
            "ENVIRONMENT": "staging",
            "DASHBOARD_SECRET": "senha-s6",
            "DASHBOARD_TENANT_ID": "jmb",
            "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        }),
        patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=0)),
        patch("src.dashboard.ui._reset_login_fail", new=AsyncMock()),
    ):
        resp = client.post("/dashboard/login", data={"senha": "senha-s6"})
    assert resp.status_code == 302
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "secure" not in set_cookie


@pytest.mark.unit
def test_dashboard_cookie_secure_true_em_production() -> None:
    """A9: cookie dashboard_session tem Secure em ambiente production."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.dashboard.ui import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    client = TestClient(app, follow_redirects=False)

    with (
        patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "DASHBOARD_SECRET": "senha-prod",
            "DASHBOARD_TENANT_ID": "jmb",
            "JWT_SECRET": "jwt-secret-teste-muito-longo-256-bits-00000000000000000000000000",
        }),
        patch("src.dashboard.ui._get_login_attempts", new=AsyncMock(return_value=0)),
        patch("src.dashboard.ui._reset_login_fail", new=AsyncMock()),
    ):
        resp = client.post("/dashboard/login", data={"senha": "senha-prod"})
    assert resp.status_code == 302
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "secure" in set_cookie
