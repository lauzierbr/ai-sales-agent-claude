"""M_INJECT — Injeção de dependências em agents/ui.py._process_message.

@pytest.mark.staging — sem I/O externo; mocks completos de infra.
Verifica que AgentCliente, AgentRep e AgentGestor são construídos sem deps None
em _process_message para cada persona.

Referência: M_INJECT do sprint_contract.md (Sprint 6).
Falha sozinha → bloqueia aprovação.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.staging

_TENANT_ID = "jmb-inject-test"
_INSTANCIA_ID = "inst-inject-01"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_tenant():
    from src.tenants.types import Tenant
    return Tenant(
        id=_TENANT_ID, nome="JMB Inject Test", cnpj="00.000.000/0001-00",
        ativo=True, whatsapp_number="5519999990000", criado_em=_NOW,
    )


def _make_instancia():
    from src.agents.types import WhatsappInstancia
    return WhatsappInstancia(
        instancia_id=_INSTANCIA_ID, tenant_id=_TENANT_ID, numero_whatsapp="5519999990000"
    )


def _make_mock_db():
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


def _payload(remote_jid: str, text: str = "oi") -> dict:
    from src.agents.types import WebhookPayload
    return WebhookPayload(
        event="MESSAGES_UPSERT",
        instance=_INSTANCIA_ID,
        data={
            "key": {"id": "msg-inject-01", "remoteJid": remote_jid, "fromMe": False},
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    ).model_dump()


# ─────────────────────────────────────────────
# AgentGestor — deps não-None
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ui_injection_agent_gestor_deps_nao_none() -> None:
    """M_INJECT: AgentGestor construído em _process_message sem deps None."""
    from src.agents.types import Persona, Gestor
    from src.agents.runtime.agent_gestor import AgentGestor

    gestor = Gestor(
        id="gest-inj-01", tenant_id=_TENANT_ID, telefone="5519000000001",
        nome="Gestor Inject", ativo=True, criado_em=_NOW,
    )

    deps: dict = {}

    class _Capture(AgentGestor):
        def __init__(self, **kwargs):
            deps.update(kwargs)
            super().__init__(**kwargs)

        async def responder(self, *args, **kwargs):
            pass

    mock_factory, _ = _make_mock_db()

    with (
        patch("src.agents.service.get_instancia", new=AsyncMock(return_value=_make_instancia())),
        patch("src.tenants.repo.TenantRepo.get_by_id", new=AsyncMock(return_value=_make_tenant())),
        patch("src.agents.service.IdentityRouter.resolve", new=AsyncMock(return_value=Persona.GESTOR)),
        patch("src.agents.repo.GestorRepo.get_by_telefone", new=AsyncMock(return_value=gestor)),
        patch("src.providers.db.get_session_factory", return_value=mock_factory),
        patch("src.providers.db.get_redis", return_value=AsyncMock()),
        patch("src.agents.service.mark_message_as_read", new=AsyncMock()),
        patch("src.agents.service.send_typing_indicator", new=AsyncMock()),
        patch("src.agents.service.send_typing_stop", new=AsyncMock()),
        patch("src.agents.runtime.agent_gestor.AgentGestor", new=_Capture),
        patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test",
            "EVOLUTION_WEBHOOK_SECRET": "x",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }),
    ):
        from src.agents.ui import _process_message
        await _process_message(_payload("5519000000001@s.whatsapp.net"))

    if deps:
        assert deps.get("catalog_service") is not None, "AgentGestor.catalog_service is None"
        assert deps.get("order_service") is not None, "AgentGestor.order_service is None"
        assert deps.get("pdf_generator") is not None, "AgentGestor.pdf_generator is None"
        assert deps.get("relatorio_repo") is not None, "AgentGestor.relatorio_repo is None"
        assert deps.get("cliente_b2b_repo") is not None, "AgentGestor.cliente_b2b_repo is None"
        assert deps.get("redis_client") is not None, "AgentGestor.redis_client is None"


# ─────────────────────────────────────────────
# AgentCliente — deps não-None
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ui_injection_agent_cliente_deps_nao_none() -> None:
    """M_INJECT: AgentCliente construído em _process_message sem deps None."""
    from src.agents.types import Persona
    from src.agents.runtime.agent_cliente import AgentCliente

    deps: dict = {}

    class _Capture(AgentCliente):
        def __init__(self, **kwargs):
            deps.update(kwargs)
            super().__init__(**kwargs)

        async def responder(self, *args, **kwargs):
            pass

    mock_factory, mock_session = _make_mock_db()
    # Simula get_by_telefone retornando None (cliente não identificado ainda é válido)
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("src.agents.service.get_instancia", new=AsyncMock(return_value=_make_instancia())),
        patch("src.tenants.repo.TenantRepo.get_by_id", new=AsyncMock(return_value=_make_tenant())),
        patch("src.agents.service.IdentityRouter.resolve", new=AsyncMock(return_value=Persona.CLIENTE_B2B)),
        patch("src.providers.db.get_session_factory", return_value=mock_factory),
        patch("src.providers.db.get_redis", return_value=AsyncMock()),
        patch("src.agents.service.mark_message_as_read", new=AsyncMock()),
        patch("src.agents.service.send_typing_indicator", new=AsyncMock()),
        patch("src.agents.service.send_typing_stop", new=AsyncMock()),
        patch("src.agents.runtime.agent_cliente.AgentCliente", new=_Capture),
        patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test",
            "EVOLUTION_WEBHOOK_SECRET": "x",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }),
    ):
        from src.agents.ui import _process_message
        await _process_message(_payload("5519000000002@s.whatsapp.net", "quero ver produtos"))

    if deps:
        assert deps.get("catalog_service") is not None, "AgentCliente.catalog_service is None"
        assert deps.get("order_service") is not None, "AgentCliente.order_service is None"
        assert deps.get("pdf_generator") is not None, "AgentCliente.pdf_generator is None"
        assert deps.get("redis_client") is not None, "AgentCliente.redis_client is None"
        assert deps.get("conversa_repo") is not None, "AgentCliente.conversa_repo is None"


# ─────────────────────────────────────────────
# AgentRep — deps não-None
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ui_injection_agent_rep_deps_nao_none() -> None:
    """M_INJECT: AgentRep construído em _process_message sem deps None."""
    from src.agents.types import Persona, Representante
    from src.agents.runtime.agent_rep import AgentRep

    rep = Representante(
        id="rep-inj-01", tenant_id=_TENANT_ID, telefone="5519000000003",
        nome="Rep Inject", ativo=True, usuario_id=None,
    )

    deps: dict = {}

    class _Capture(AgentRep):
        def __init__(self, **kwargs):
            deps.update(kwargs)
            super().__init__(**kwargs)

        async def responder(self, *args, **kwargs):
            pass

    mock_factory, _ = _make_mock_db()

    with (
        patch("src.agents.service.get_instancia", new=AsyncMock(return_value=_make_instancia())),
        patch("src.tenants.repo.TenantRepo.get_by_id", new=AsyncMock(return_value=_make_tenant())),
        patch("src.agents.service.IdentityRouter.resolve", new=AsyncMock(return_value=Persona.REPRESENTANTE)),
        patch("src.agents.repo.RepresentanteRepo.get_by_telefone", new=AsyncMock(return_value=rep)),
        patch("src.providers.db.get_session_factory", return_value=mock_factory),
        patch("src.providers.db.get_redis", return_value=AsyncMock()),
        patch("src.agents.service.mark_message_as_read", new=AsyncMock()),
        patch("src.agents.service.send_typing_indicator", new=AsyncMock()),
        patch("src.agents.service.send_typing_stop", new=AsyncMock()),
        patch("src.agents.runtime.agent_rep.AgentRep", new=_Capture),
        patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test",
            "EVOLUTION_WEBHOOK_SECRET": "x",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }),
    ):
        from src.agents.ui import _process_message
        await _process_message(_payload("5519000000003@s.whatsapp.net", "clientes da carteira"))

    if deps:
        assert deps.get("catalog_service") is not None, "AgentRep.catalog_service is None"
        assert deps.get("order_service") is not None, "AgentRep.order_service is None"
        assert deps.get("pdf_generator") is not None, "AgentRep.pdf_generator is None"
        assert deps.get("redis_client") is not None, "AgentRep.redis_client is None"
        assert deps.get("conversa_repo") is not None, "AgentRep.conversa_repo is None"
        assert deps.get("representante") is not None, "AgentRep.representante is None"
