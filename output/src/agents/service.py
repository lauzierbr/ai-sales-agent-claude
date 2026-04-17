"""Service do domínio Agents — Identity Router e envio de mensagens WhatsApp.

Camada Service: importa apenas Types, Config e Repo do domínio.
Não importa Runtime ou UI.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone

import httpx
import structlog
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.repo import ClienteB2BRepo, RepresentanteRepo, WhatsappInstanciaRepo
from src.agents.types import Mensagem, Persona, WebhookPayload, WhatsappInstancia

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)
meter = get_meter(__name__)

_mensagens_enviadas = meter.create_counter(
    "whatsapp_mensagens_enviadas_total",
    description="Total de mensagens enviadas via WhatsApp por tenant e persona",
)


class IdentityRouter:
    """Resolve a persona de um remetente WhatsApp via lookup no banco de dados."""

    def __init__(self) -> None:
        self._instancia_repo = WhatsappInstanciaRepo()
        self._cliente_repo = ClienteB2BRepo()
        self._rep_repo = RepresentanteRepo()

    async def resolve(
        self, mensagem: Mensagem, tenant_id: str, session: AsyncSession
    ) -> Persona:
        """Resolve persona do remetente pelo número de telefone.

        Lookup em ordem: clientes_b2b → representantes → DESCONHECIDO.
        Remove sufixo @s.whatsapp.net antes da busca.

        Args:
            mensagem: mensagem recebida com número do remetente.
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Persona identificada: CLIENTE_B2B, REPRESENTANTE ou DESCONHECIDO.
        """
        with tracer.start_as_current_span("identity_router_resolve") as span:
            span.set_attribute("tenant_id", tenant_id)

            telefone = mensagem.de.split("@")[0]

            rep = await self._rep_repo.get_by_telefone(
                tenant_id, telefone, session
            )
            cliente = await self._cliente_repo.get_by_telefone(
                tenant_id, telefone, session
            )

            # Detecta conflito cross-table — mesmo telefone em representantes E clientes_b2b
            # Indica erro de cadastro: o número deve existir em apenas uma tabela.
            if rep is not None and cliente is not None:
                log.warning(
                    "identity_router_conflito_telefone",
                    tenant_id=tenant_id,
                    telefone_hash=hashlib.sha256(telefone.encode()).hexdigest()[:12],
                    rep_id=str(rep.id),
                    cliente_id=str(cliente.id),
                    msg=(
                        "Mesmo telefone cadastrado como representante E cliente_b2b. "
                        "Prioridade: REPRESENTANTE. Corrija o cadastro do cliente."
                    ),
                )

            # Representante tem prioridade sobre cliente
            if rep is not None:
                span.set_attribute("persona", "representante")
                return Persona.REPRESENTANTE

            if cliente is not None:
                span.set_attribute("persona", "cliente_b2b")
                return Persona.CLIENTE_B2B

            span.set_attribute("persona", "desconhecido")
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


def parse_mensagem(payload: WebhookPayload) -> Mensagem | None:
    """Converte WebhookPayload da Evolution API em Mensagem normalizada.

    Retorna None para mensagens que não devem ser processadas:
    - fromMe=True: mensagens enviadas pelo próprio bot (evita loop)
    - texto vazio: status updates, reactions, etc.
    - remoteJid vazio ou de grupo (@g.us)

    Args:
        payload: payload bruto da Evolution API.

    Returns:
        Mensagem normalizada ou None se deve ser ignorada.
    """
    data = payload.data
    key = data.get("key", {})
    msg = data.get("message", {})

    # Ignora mensagens enviadas pelo próprio bot (evita loop infinito)
    if key.get("fromMe", False):
        return None

    remote_jid = key.get("remoteJid", "")

    # Ignora grupos (remoteJid termina em @g.us)
    if remote_jid.endswith("@g.us"):
        return None

    # Texto pode vir em vários campos dependendo do tipo
    texto = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    )

    # Ignora mensagens sem texto (status updates, reactions, etc.)
    if not texto.strip():
        return None

    timestamp_raw = data.get("messageTimestamp", 0)

    return Mensagem(
        id=key.get("id", ""),
        de=remote_jid,
        para=payload.instance,
        texto=texto,
        tipo=data.get("messageType", "text"),
        instancia_id=payload.instance,
        timestamp=datetime.fromtimestamp(float(timestamp_raw), tz=timezone.utc),
    )


def validate_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Valida assinatura do webhook da Evolution API.

    Suporta dois modos (detectado automaticamente pelo formato do header):
    - Token simples: Evolution envia o secret diretamente como X-Evolution-Signature.
      Usado no MVP/staging pois a Evolution API v2 não assina payloads nativamente.
    - HMAC-SHA256: header contém hexdigest — compatível com proxies futuros.

    Args:
        body: corpo da requisição em bytes.
        signature_header: valor do header X-Evolution-Signature.

    Returns:
        True se autenticação válida, False caso contrário.
    """
    secret = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")
    if not secret:
        log.error("evolution_webhook_secret_ausente")
        return False

    # Modo token simples (64 chars hex = HMAC, caso contrário = token direto)
    if len(signature_header) != 64:
        return hmac.compare_digest(secret, signature_header)

    # Modo HMAC-SHA256
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def mark_message_as_read(
    instancia_id: str, remote_jid: str, message_id: str
) -> None:
    """Marca mensagem como lida (✓✓ azul) via Evolution API.

    Chamado imediatamente após receber o webhook — feedback visual rápido
    que o bot "viu" a mensagem.

    Args:
        instancia_id: nome da instância Evolution API.
        remote_jid: JID do remetente (ex: 5519...@s.whatsapp.net).
        message_id: ID da mensagem recebida.
    """
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", "")

    url = f"{api_url}/chat/markMessageAsRead/{instancia_id}"
    payload = {
        "readMessages": [
            {"id": message_id, "fromMe": False, "remoteJid": remote_jid}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers={"apikey": api_key})
            resp.raise_for_status()
    except Exception as exc:
        # Não crítico — falha silenciosa para não bloquear o processamento
        log.debug("mark_as_read_erro", instancia_id=instancia_id, error=str(exc))


async def send_typing_indicator(
    instancia_id: str, remote_jid: str, duration_ms: int = 8000
) -> None:
    """Envia indicador "digitando..." via Evolution API.

    Chamado antes de processar a resposta do agente — o indicador desaparece
    automaticamente quando a mensagem chega ou após duration_ms.

    Args:
        instancia_id: nome da instância Evolution API.
        remote_jid: JID do destinatário (ex: 5519...@s.whatsapp.net).
        duration_ms: duração do indicador em ms (padrão 8s cobre a maioria das respostas).
    """
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", "")

    url = f"{api_url}/chat/sendPresence/{instancia_id}"
    payload = {
        "number": remote_jid,
        "delay": duration_ms,
        "presence": "composing",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers={"apikey": api_key})
            resp.raise_for_status()
    except Exception as exc:
        log.debug("typing_indicator_erro", instancia_id=instancia_id, error=str(exc))


async def send_whatsapp_message(
    instancia_id: str, numero: str, texto: str
) -> None:
    """Envia mensagem de texto via Evolution API.

    Args:
        instancia_id: nome da instância Evolution API.
        numero: número destinatário (formato E.164 sem +).
        texto: texto da mensagem.
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


async def send_whatsapp_media(
    instancia_id: str,
    numero: str,
    pdf_bytes: bytes,
    caption: str,
    file_name: str,
) -> None:
    """Envia PDF via Evolution API como documento WhatsApp.

    Usa base64 e endpoint /message/sendMedia/.
    Erros não propagam — background task deve ser resiliente.

    Args:
        instancia_id: nome da instância Evolution API.
        numero: número destinatário (formato E.164 sem +).
        pdf_bytes: conteúdo do PDF em bytes.
        caption: legenda exibida junto ao documento.
        file_name: nome do arquivo exibido ao destinatário.
    """
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", "")

    url = f"{api_url}/message/sendMedia/{instancia_id}"
    payload = {
        "number": numero,
        "mediatype": "document",
        "mimetype": "application/pdf",
        "caption": caption,
        "media": base64.b64encode(pdf_bytes).decode(),
        "fileName": file_name,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"apikey": api_key},
            )
            resp.raise_for_status()
            log.info(
                "media_enviada",
                instancia_id=instancia_id,
                numero_hash=hashlib.sha256(numero.encode()).hexdigest()[:8],
                file_name=file_name,
            )
    except httpx.HTTPStatusError as exc:
        log.error(
            "evolution_api_media_erro",
            status_code=exc.response.status_code,
            instancia_id=instancia_id,
        )
    except Exception as exc:
        log.error("evolution_api_media_timeout", instancia_id=instancia_id, error=str(exc))
