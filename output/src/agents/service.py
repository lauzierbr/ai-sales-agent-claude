"""Service do domínio Agents — Identity Router e envio de mensagens WhatsApp.

Camada Service: importa apenas Types, Config e Repo do domínio.
Não importa Runtime ou UI.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone

import httpx
import structlog
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.repo import WhatsappInstanciaRepo
from src.agents.types import Mensagem, Persona, WebhookPayload, WhatsappInstancia

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)
meter = get_meter(__name__)

_mensagens_enviadas = meter.create_counter(
    "whatsapp_mensagens_enviadas_total",
    description="Total de mensagens enviadas via WhatsApp por tenant e persona",
)


class IdentityRouter:
    """Resolve a persona de um remetente WhatsApp — Sprint 1: stub."""

    def __init__(self) -> None:
        self._instancia_repo = WhatsappInstanciaRepo()

    async def resolve(
        self, mensagem: Mensagem, tenant_id: str, session: AsyncSession
    ) -> Persona:
        """Resolve persona do remetente.

        Sprint 1: retorna sempre DESCONHECIDO.
        Sprint 2: implementará lookup em `representantes` e `clientes_b2b`.

        Args:
            mensagem: mensagem recebida.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy.

        Returns:
            Persona identificada (sempre DESCONHECIDO em Sprint 1).
        """
        with tracer.start_as_current_span("identity_router_resolve") as span:
            span.set_attribute("tenant_id", tenant_id)
            # Sprint 1 stub — Sprint 2 implementará lookup real
            return Persona.DESCONHECIDO


async def get_instancia(
    instancia_id: str, session: AsyncSession
) -> WhatsappInstancia | None:
    """Busca instância WhatsApp pelo ID.

    Args:
        instancia_id: ID/nome da instância na Evolution API.
        session: sessão SQLAlchemy.

    Returns:
        WhatsappInstancia ou None se não encontrada.
    """
    repo = WhatsappInstanciaRepo()
    return await repo.get_by_instancia_id(instancia_id, session)


def parse_mensagem(payload: WebhookPayload) -> Mensagem:
    """Converte WebhookPayload da Evolution API em Mensagem normalizada.

    Args:
        payload: payload bruto da Evolution API.

    Returns:
        Mensagem normalizada.
    """
    data = payload.data
    key = data.get("key", {})
    msg = data.get("message", {})

    # Texto pode vir em vários campos dependendo do tipo
    texto = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    )
    timestamp_raw = data.get("messageTimestamp", 0)

    return Mensagem(
        id=key.get("id", ""),
        de=key.get("remoteJid", ""),
        para=payload.instance,
        texto=texto,
        tipo=data.get("messageType", "text"),
        instancia_id=payload.instance,
        timestamp=datetime.fromtimestamp(float(timestamp_raw), tz=timezone.utc),
    )


def validate_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Valida assinatura HMAC-SHA256 do webhook da Evolution API.

    Args:
        body: corpo da requisição em bytes.
        signature_header: valor do header X-Evolution-Signature.

    Returns:
        True se assinatura válida, False caso contrário.
    """
    secret = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")
    if not secret:
        log.error("evolution_webhook_secret_ausente")
        return False

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def send_whatsapp_message(
    instancia_id: str, numero: str, texto: str
) -> None:
    """Envia mensagem de texto via Evolution API.

    Args:
        instancia_id: nome da instância Evolution API.
        numero: número destinatário (formato E.164 sem +).
        texto: texto da mensagem.

    Raises:
        httpx.HTTPStatusError: se a API retornar erro 4xx/5xx (logado, não propagado).
    """
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", "")

    url = f"{api_url}/message/sendText/{instancia_id}"
    payload = {"number": numero, "text": texto}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"apikey": api_key},
            )
            resp.raise_for_status()
            log.info(
                "mensagem_enviada",
                instancia_id=instancia_id,
                numero_hash=hashlib.sha256(numero.encode()).hexdigest()[:8],
            )
    except httpx.HTTPStatusError as exc:
        log.error(
            "evolution_api_erro",
            status_code=exc.response.status_code,
            instancia_id=instancia_id,
        )
        # Não propaga — background task não deve crashar por falha de envio
    except Exception as exc:
        log.error("evolution_api_timeout", instancia_id=instancia_id, error=str(exc))
