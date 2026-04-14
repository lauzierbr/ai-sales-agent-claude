"""Testes unitários de agents/ui.py — webhook Evolution API.

Todos os testes são @pytest.mark.unit — sem I/O externo.
Critérios: A10 (HMAC válido → 200), A11 (HMAC inválido → 403), A12 (sem header → 403).
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
