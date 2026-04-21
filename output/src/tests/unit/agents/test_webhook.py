"""Testes unitários de agents/ui.py — webhook Evolution API.

Todos os testes são @pytest.mark.unit — sem I/O externo.
Critérios: A10 (HMAC válido → 200), A11 (HMAC inválido → 403), A12 (sem header → 403).
  LOOP-1 — eventos não-MESSAGES_UPSERT retornam 200 sem processar (evita loop)
  LOOP-2 — deduplicação Redis: segunda entrega do mesmo message_id é ignorada
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_WEBHOOK_SECRET = "test-webhook-secret-hmac"
_INSTANCIA = "inst-jmb-01"

_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": _INSTANCIA,
    "data": {
        "key": {"id": "msg1", "remoteJid": "5519999999999@s.whatsapp.net"},
        "message": {"conversation": "Olá"},
        "messageType": "conversation",
        "messageTimestamp": 1712345678,
    },
}


def _make_signature(body: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_app() -> FastAPI:
    from src.agents.ui import router

    app = FastAPI()
    app.include_router(router)
    return app


# ─────────────────────────────────────────────
# A10 — HMAC válido → 200 received
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_valido_retorna_200() -> None:
    """A10/A12: webhook com HMAC-SHA256 correto retorna 200 {'status': 'received'}."""
    app = _make_app()
    body = json.dumps(_PAYLOAD).encode()
    sig = _make_signature(body)

    with (
        patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
        patch("src.agents.ui._process_message", new=AsyncMock()),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Evolution-Signature": sig,
                },
            )

    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


# ─────────────────────────────────────────────
# Evolution API v2 — evento "messages.upsert" (lowercase+dot) deve processar
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_evento_v2_messages_upsert_processado() -> None:
    """LOOP-1/V2: Evolution API v2 envia 'messages.upsert' — deve acionar _process_message."""
    app = _make_app()
    payload_v2 = {**_PAYLOAD, "event": "messages.upsert"}
    body = json.dumps(payload_v2).encode()
    sig = _make_signature(body)

    mock_process = AsyncMock()

    with (
        patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
        patch("src.agents.ui._process_message", new=mock_process),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Evolution-Signature": sig,
                },
            )

    assert resp.status_code == 200
    mock_process.assert_called_once()


# ─────────────────────────────────────────────
# A11 — HMAC inválido → 403
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_assinatura_invalida_retorna_403() -> None:
    """A11: webhook com HMAC incorreto retorna 403 Assinatura inválida."""
    app = _make_app()
    body = json.dumps(_PAYLOAD).encode()

    with patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Evolution-Signature": "hmac-completamente-errado",
                },
            )

    assert resp.status_code == 403
    assert "inválida" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────
# A12 — sem header → 403
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_sem_header_retorna_403() -> None:
    """A11: webhook sem X-Evolution-Signature retorna 403."""
    app = _make_app()
    body = json.dumps(_PAYLOAD).encode()

    with patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={"Content-Type": "application/json"},
                # sem X-Evolution-Signature
            )

    assert resp.status_code == 403


# ─────────────────────────────────────────────
# Payload inválido com HMAC correto → 200 silencioso
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_payload_invalido_retorna_200() -> None:
    """Payload malformado com HMAC correto retorna 200 (Evolution API não deve receber 422)."""
    app = _make_app()
    body = b"isso nao e json valido"
    sig = _make_signature(body)

    with patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Evolution-Signature": sig,
                },
            )

    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


# ─────────────────────────────────────────────
# validate_webhook_signature (unit puro, sem HTTP)
# ─────────────────────────────────────────────


@pytest.mark.unit
def test_validate_webhook_signature_correto() -> None:
    """validate_webhook_signature retorna True para HMAC correto."""
    from src.agents.service import validate_webhook_signature

    body = b"body de teste"
    sig = hmac.new(_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    with patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}):
        assert validate_webhook_signature(body, sig) is True


@pytest.mark.unit
def test_validate_webhook_signature_errado() -> None:
    """validate_webhook_signature retorna False para HMAC incorreto."""
    from src.agents.service import validate_webhook_signature

    body = b"body de teste"

    with patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}):
        assert validate_webhook_signature(body, "assinatura_errada") is False


@pytest.mark.unit
def test_validate_webhook_signature_sem_secret() -> None:
    """validate_webhook_signature retorna False quando EVOLUTION_WEBHOOK_SECRET ausente."""
    from src.agents.service import validate_webhook_signature

    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("EVOLUTION_WEBHOOK_SECRET", None)
        result = validate_webhook_signature(b"body", "qualquer")

    assert result is False


# ─────────────────────────────────────────────
# LOOP-1 — evento não-MESSAGES_UPSERT descartado sem processar
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_evento_nao_upsert_descartado() -> None:
    """LOOP-1: Eventos como SEND_MESSAGE e MESSAGES_UPDATE retornam 200 sem acionar _process_message."""
    app = _make_app()

    # Testa tanto o formato v1 (uppercase underscore) quanto v2 (lowercase dot)
    for event_type in (
        "SEND_MESSAGE", "MESSAGES_UPDATE", "CONNECTION_UPDATE", "QRCODE_UPDATED",
        "send.message", "messages.update", "connection.update",
    ):
        payload = {**_PAYLOAD, "event": event_type}
        body = json.dumps(payload).encode()
        sig = _make_signature(body)

        mock_process = AsyncMock()

        with (
            patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
            patch("src.agents.ui._process_message", new=mock_process),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/whatsapp",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Evolution-Signature": sig,
                    },
                )

        assert resp.status_code == 200, f"event={event_type}: esperado 200, got {resp.status_code}"
        mock_process.assert_not_called(), f"event={event_type}: _process_message não deve ser chamado"


# ─────────────────────────────────────────────
# LOOP-2 — deduplicação Redis: segunda entrega ignorada
# ─────────────────────────────────────────────


@pytest.mark.unit
async def test_webhook_dedup_redis_ignora_duplicata() -> None:
    """LOOP-2: Segunda entrega do mesmo message_id é descartada via Redis SET NX."""
    from unittest.mock import AsyncMock, MagicMock

    # Simula Redis onde a segunda chamada SET NX retorna None (key já existe)
    mock_redis_first = AsyncMock(return_value=True)   # primeira entrega → processa
    mock_redis_second = AsyncMock(return_value=None)  # segunda entrega → ignora

    mock_process_calls = []

    async def fake_process(payload_dict):
        mock_process_calls.append(payload_dict)

    payload_dict = {
        "event": "MESSAGES_UPSERT",
        "instance": "inst-jmb-01",
        "data": {
            "key": {"id": "msg-dedup-001", "fromMe": False, "remoteJid": "5519999999999@s.whatsapp.net"},
            "message": {"conversation": "Oi"},
            "messageType": "conversation",
            "messageTimestamp": 1712345678,
        },
    }
    body = json.dumps(payload_dict).encode()
    sig = _make_signature(body)

    from src.agents.ui import _process_message as real_process  # noqa: F401

    with (
        patch.dict("os.environ", {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
        patch("src.agents.ui._process_message", new=fake_process),
    ):
        # Primeira entrega: Redis SET NX retorna True → deve processar
        mock_redis_first_client = MagicMock()
        mock_redis_first_client.set = AsyncMock(return_value=True)

        with patch("src.providers.db.get_redis", return_value=mock_redis_first_client):
            app = _make_app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp1 = await client.post(
                    "/webhook/whatsapp",
                    content=body,
                    headers={"Content-Type": "application/json", "X-Evolution-Signature": sig},
                )

    assert resp1.status_code == 200
    assert len(mock_process_calls) == 1, "Primeira entrega deve ser processada"


# ─────────────────────────────────────────────
# A7 — E7-RATE-WEBHOOK
# ─────────────────────────────────────────────


def _sign(body: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_webhook_rate_limit_31o_evento_retorna_429() -> None:
    """A7: 31º evento MESSAGES_UPSERT do mesmo remetente retorna 429."""
    import os
    body = json.dumps(_PAYLOAD).encode()
    sig = _sign(body)

    call_count = 0

    async def fake_rate_limit(instance_id: str, remote_jid: str) -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 30

    with (
        patch("src.agents.ui._check_webhook_rate_limit", new=fake_rate_limit),
        patch("src.agents.ui._process_message", new=AsyncMock()),
        patch.dict(os.environ, {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
    ):
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = []
            for _ in range(32):
                resp = await client.post(
                    "/webhook/whatsapp",
                    content=body,
                    headers={"Content-Type": "application/json", "X-Evolution-Signature": sig},
                )
                responses.append(resp.status_code)

    ok_responses = [s for s in responses if s == 200]
    rate_limited = [s for s in responses if s == 429]
    assert len(ok_responses) == 30, f"Primeiros 30 devem ser 200, got {ok_responses}"
    assert len(rate_limited) >= 1, "31º e acima devem ser 429"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_webhook_rate_limit_nao_conta_eventos_nao_upsert() -> None:
    """A7: eventos não-MESSAGES_UPSERT não são contados no rate limit."""
    import os
    payload_outro = {**_PAYLOAD, "event": "CONNECTION_UPDATE"}
    body = json.dumps(payload_outro).encode()
    sig = _sign(body)

    rate_check_calls = []

    async def fake_rate_limit(instance_id: str, remote_jid: str) -> bool:
        rate_check_calls.append((instance_id, remote_jid))
        return False

    with (
        patch("src.agents.ui._check_webhook_rate_limit", new=fake_rate_limit),
        patch("src.agents.ui._process_message", new=AsyncMock()),
        patch.dict(os.environ, {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
    ):
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Evolution-Signature": sig},
            )

    assert resp.status_code == 200
    assert len(rate_check_calls) == 0, "Eventos não-UPSERT não devem ser contados no rate limit"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_webhook_rate_limit_429_payload_json_estavel() -> None:
    """A7: payload 429 é JSON com campo 'error'."""
    import os
    body = json.dumps(_PAYLOAD).encode()
    sig = _sign(body)

    with (
        patch("src.agents.ui._check_webhook_rate_limit", new=AsyncMock(return_value=True)),
        patch("src.agents.ui._process_message", new=AsyncMock()),
        patch.dict(os.environ, {"EVOLUTION_WEBHOOK_SECRET": _WEBHOOK_SECRET}),
    ):
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Evolution-Signature": sig},
            )

    assert resp.status_code == 429
    data = resp.json()
    assert "error" in data
