"""Testes unitários de agents/service.py — IdentityRouter e parse_mensagem.

Todos os testes são @pytest.mark.unit — sem I/O externo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.agents.types import Mensagem, Persona, WebhookPayload


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def mensagem_fixture() -> Mensagem:
    return Mensagem(
        id="msg1",
        de="5519999999999@s.whatsapp.net",
        para="inst-jmb-01",
        texto="Olá, quero fazer um pedido",
        tipo="conversation",
        instancia_id="inst-jmb-01",
        timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def webhook_payload_fixture() -> WebhookPayload:
    return WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {"id": "msg1", "remoteJid": "5519999999999@s.whatsapp.net"},
            "message": {"conversation": "Olá"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    )


# ─────────────────────────────────────────────
# IdentityRouter — Sprint 1 stub
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_identity_router_retorna_desconhecido(mensagem_fixture: Mensagem) -> None:
    """Sprint 1: IdentityRouter.resolve sempre retorna Persona.DESCONHECIDO."""
    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()
    persona = await router.resolve(mensagem_fixture, "jmb", session)

    assert persona == Persona.DESCONHECIDO


@pytest.mark.unit
async def test_identity_router_desconhecido_independe_do_numero(
    mensagem_fixture: Mensagem,
) -> None:
    """IdentityRouter retorna DESCONHECIDO para qualquer número (Sprint 1)."""
    from src.agents.service import IdentityRouter

    session = AsyncMock()
    router = IdentityRouter()

    # Testa com número diferente — ainda deve retornar DESCONHECIDO
    mensagem_fixture.de = "5511888888888@s.whatsapp.net"
    persona = await router.resolve(mensagem_fixture, "outro_tenant", session)

    assert persona == Persona.DESCONHECIDO


# ─────────────────────────────────────────────
# parse_mensagem
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_parse_mensagem_extrai_texto_conversation(
    webhook_payload_fixture: WebhookPayload,
) -> None:
    """parse_mensagem extrai texto de mensagem tipo conversation."""
    from src.agents.service import parse_mensagem

    mensagem = parse_mensagem(webhook_payload_fixture)

    assert mensagem.texto == "Olá"
    assert mensagem.de == "5519999999999@s.whatsapp.net"
    assert mensagem.instancia_id == "inst-jmb-01"


@pytest.mark.unit
def test_parse_mensagem_extrai_texto_extended() -> None:
    """parse_mensagem extrai texto de extendedTextMessage."""
    from src.agents.service import parse_mensagem

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {"id": "msg2", "remoteJid": "5519999999999@s.whatsapp.net"},
            "message": {
                "extendedTextMessage": {"text": "Mensagem longa aqui"}
            },
            "messageType": "extendedTextMessage",
            "messageTimestamp": 1712345678,
        },
    )

    mensagem = parse_mensagem(payload)
    assert mensagem.texto == "Mensagem longa aqui"


@pytest.mark.unit
def test_parse_mensagem_texto_vazio_sem_crash() -> None:
    """parse_mensagem não falha com payload sem texto (retorna string vazia)."""
    from src.agents.service import parse_mensagem

    payload = WebhookPayload(
        event="MESSAGES_UPSERT",
        instance="inst-jmb-01",
        data={
            "key": {"id": "msg3", "remoteJid": "5519999999999@s.whatsapp.net"},
            "message": {},
            "messageType": "imageMessage",
            "messageTimestamp": 1712345678,
        },
    )

    mensagem = parse_mensagem(payload)
    assert mensagem.texto == ""
    assert mensagem.tipo == "imageMessage"


# ─────────────────────────────────────────────
# send_whatsapp_message (M4 coverage)
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_send_whatsapp_message_sucesso() -> None:
    """send_whatsapp_message envia POST para Evolution API com sucesso."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.agents.service import send_whatsapp_message

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        await send_whatsapp_message("inst-jmb-01", "5519999999999", "Olá!")

    mock_client_instance.post.assert_called_once()
    call_kwargs = mock_client_instance.post.call_args
    assert "inst-jmb-01" in call_kwargs[0][0]  # URL contém instancia_id


@pytest.mark.unit
async def test_send_whatsapp_message_erro_nao_propaga() -> None:
    """send_whatsapp_message captura HTTPStatusError sem propagar (background task seguro)."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.agents.service import send_whatsapp_message

    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)

    with (
        patch.dict("os.environ", {
            "EVOLUTION_API_URL": "http://evolution-test:8080",
            "EVOLUTION_API_KEY": "test-key",
        }),
        patch("src.agents.service.httpx.AsyncClient") as MockClient,
    ):
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=error)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # Não deve propagar exceção
        await send_whatsapp_message("inst-jmb-01", "5519999999999", "Olá!")
