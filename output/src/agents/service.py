"""Service do domínio Agents — Identity Router e envio de mensagens WhatsApp.

Camada Service: importa apenas Types, Config e Repo do domínio.
Não importa Runtime ou UI.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import structlog
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.repo import ClienteB2BRepo, ContactRepo, GestorRepo, RepresentanteRepo, WhatsappInstanciaRepo
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
        self._gestor_repo = GestorRepo()
        self._contact_repo = ContactRepo()

    async def resolve(
        self, mensagem: Mensagem, tenant_id: str, session: AsyncSession
    ) -> Persona:
        """Resolve persona do remetente pelo número de telefone.

        Lookup em ordem: gestores → representantes → clientes_b2b → contacts → DESCONHECIDO.
        B-40: contacts consultados antes de DESCONHECIDO — número autorizado via D030
        retorna CLIENTE_B2B em vez de DESCONHECIDO.
        Remove sufixo @s.whatsapp.net antes da busca.

        Args:
            mensagem: mensagem recebida com número do remetente.
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Persona identificada: GESTOR, REPRESENTANTE, CLIENTE_B2B ou DESCONHECIDO.
        """
        with tracer.start_as_current_span("identity_router_resolve") as span:
            span.set_attribute("tenant_id", tenant_id)

            telefone = mensagem.de.split("@")[0]

            # Gestor tem prioridade máxima (DP-02: perfis cumulativos)
            gestor = await self._gestor_repo.get_by_telefone(
                tenant_id, telefone, session
            )
            if gestor is not None:
                rep_also = await self._rep_repo.get_by_telefone(
                    tenant_id, telefone, session
                )
                if rep_also is not None:
                    log.info(
                        "identity_router_gestor_rep_cumulativo",
                        tenant_id=tenant_id,
                        telefone_hash=hashlib.sha256(telefone.encode()).hexdigest()[:12],
                        gestor_id=str(gestor.id),
                    )
                span.set_attribute("persona", "gestor")
                return Persona.GESTOR

            rep = await self._rep_repo.get_by_telefone(
                tenant_id, telefone, session
            )
            cliente = await self._cliente_repo.get_by_telefone(
                tenant_id, telefone, session
            )

            # Detecta conflito cross-table
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

            if rep is not None:
                span.set_attribute("persona", "representante")
                return Persona.REPRESENTANTE

            if cliente is not None:
                span.set_attribute("persona", "cliente_b2b")
                return Persona.CLIENTE_B2B

            # B-40: consultar contacts (D030) antes de retornar DESCONHECIDO.
            # Número autorizado via comando AUTORIZAR deve ser roteado como CLIENTE_B2B.
            try:
                contact = await self._contact_repo.get_by_channel(
                    tenant_id=tenant_id,
                    kind="whatsapp",
                    identifier=telefone,
                    session=session,
                )
                if contact is not None and contact.get("authorized"):
                    log.info(
                        "identity_router_contact_autorizado",
                        tenant_id=tenant_id,
                        telefone_hash=hashlib.sha256(telefone.encode()).hexdigest()[:12],
                        contact_id=str(contact.get("id", "")),
                    )
                    span.set_attribute("persona", "cliente_b2b")
                    return Persona.CLIENTE_B2B
            except Exception as exc:
                log.warning(
                    "identity_router_contact_lookup_erro",
                    tenant_id=tenant_id,
                    error=str(exc),
                )

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

    message_type = data.get("messageType", "")

    # E3: audioMessage — retorna Mensagem com texto vazio e tipo="audioMessage"
    # A transcrição é feita em agents/ui.py (_transcrever_audio via asyncio.to_thread)
    if message_type == "audioMessage":
        timestamp_raw = data.get("messageTimestamp", 0)
        return Mensagem(
            id=key.get("id", ""),
            de=remote_jid,
            para=payload.instance,
            texto="",  # preenchido em ui.py após transcrição Whisper
            tipo="audioMessage",
            instancia_id=payload.instance,
            timestamp=datetime.fromtimestamp(float(timestamp_raw), tz=timezone.utc),
        )

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
    """Envia UM pulso de 'digitando...' via Evolution API.

    Baileys (lib subjacente à Evolution API) cappeia 'composing' em ~20s.
    Evolution *não* limpa o indicador automaticamente quando a mensagem
    é enviada (Evolution API #1639). Portanto:

    - Para cobrir respostas longas, use `show_typing_presence()` (context
      manager com pulso contínuo).
    - Para chamadas pontuais, SEMPRE pareie com `send_typing_stop()` após
      `send_whatsapp_message()`.

    Args:
        instancia_id: nome da instância Evolution API.
        remote_jid: JID do destinatário (ex: 5519...@s.whatsapp.net).
        duration_ms: duração do indicador em ms. Máximo efetivo ~20000
            (cap do Baileys); valores maiores são ignorados pelo WhatsApp.
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
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload, headers={"apikey": api_key})
            resp.raise_for_status()
    except Exception as exc:
        log.debug("typing_indicator_erro", instancia_id=instancia_id, error_type=type(exc).__name__)


async def send_typing_stop(instancia_id: str, remote_jid: str) -> None:
    """Limpa o indicador 'digitando...' explicitamente via Evolution API.

    OBRIGATÓRIO após enviar a mensagem — Evolution API NÃO emite 'paused'
    automaticamente quando sendText é chamado (ver issue #1639). Sem essa
    chamada, o 'digitando...' persiste até o delay original expirar,
    aparecendo depois da mensagem no cliente WhatsApp.
    """
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", "")

    url = f"{api_url}/chat/sendPresence/{instancia_id}"
    payload = {"number": remote_jid, "delay": 0, "presence": "paused"}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload, headers={"apikey": api_key})
            resp.raise_for_status()
    except Exception as exc:
        log.debug("typing_stop_erro", instancia_id=instancia_id, error_type=type(exc).__name__)


@asynccontextmanager
async def show_typing_presence(
    instancia_id: str, remote_jid: str
) -> AsyncIterator[None]:
    """Mostra 'digitando...' enquanto o bloco executa; garante limpeza na saída.

    Uso:
        async with show_typing_presence(instancia_id, remote_jid):
            await agent.responder(mensagem, tenant, session)

    Por que context manager e não fire-and-forget?

    Evolution API (#1639) tem comportamento contra-intuitivo:
    1. sendPresence com delay=N *mantém* 'composing' por N ms, independente
       do sendText ser chamado no meio.
    2. sendText NÃO emite 'paused' automaticamente (Baileys não faz isso).
    3. Fire-and-forget (asyncio.create_task) cria race: o sendPresence pode
       chegar DEPOIS do sendText, fazendo 'digitando...' aparecer pós-mensagem.

    Solução (baseada em recomendação do mantenedor em issue #418):
    - Ao entrar: envia 1º pulso 'composing' (await — sem race condition).
    - Durante: re-emite a cada 15s, contornando o cap de 20s do Baileys.
    - Ao sair: cancela pulso E envia 'paused' explícito — garante limpeza.

    Se Evolution API estiver indisponível, falha silenciosa (debug log).
    """
    stop = asyncio.Event()

    async def _pulse() -> None:
        while not stop.is_set():
            await send_typing_indicator(
                instancia_id=instancia_id,
                remote_jid=remote_jid,
                duration_ms=20000,  # Cap do Baileys
            )
            try:
                # Dorme 15s ou acorda se stop.set() for chamado.
                # Re-emite antes do cap de 20s para cobertura contínua.
                await asyncio.wait_for(stop.wait(), timeout=15.0)
                return  # stop sinalizado — sai do loop
            except asyncio.TimeoutError:
                continue  # ciclo expirou, re-emite

    # Primeiro pulso awaited: garante ordenação com o sendText subsequente.
    pulse_task = asyncio.create_task(_pulse())
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(pulse_task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pulse_task.cancel()
        # Explicit paused — Evolution/Baileys NÃO limpam automaticamente.
        await send_typing_stop(
            instancia_id=instancia_id, remote_jid=remote_jid
        )


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


async def notify_gestor_pendente(
    tenant_id: str,
    numero_desconhecido: str,
    mensagem_original: str,
    instancia_id: str,
    session: AsyncSession,
    redis_client: object | None = None,
) -> bool:
    """Notifica gestores ativos sobre contato pendente de autorização (E10, D030).

    Throttle: 1 notificação por número por 6h (via Redis key).
    Template: "[CONTATO PENDENTE] +55... mandou: '...'. Responda AUTORIZAR {numero} ou abra o painel."

    Args:
        tenant_id: ID do tenant — filtro obrigatório.
        numero_desconhecido: número WhatsApp do contato desconhecido.
        mensagem_original: primeira mensagem enviada (para contexto).
        instancia_id: ID da instância Evolution API.
        session: sessão SQLAlchemy assíncrona.
        redis_client: cliente Redis para throttle (opcional; sem throttle se None).

    Returns:
        True se notificação foi enviada, False se throttled.
    """
    # Throttle: verificar se já notificamos sobre este número nas últimas 6h
    throttle_key = f"notify_gestor_pendente:{tenant_id}:{numero_desconhecido}"
    throttle_ttl = 6 * 60 * 60  # 6 horas em segundos

    if redis_client is not None:
        try:
            already_sent = await redis_client.get(throttle_key)  # type: ignore[attr-defined]
            if already_sent:
                log.info(
                    "notify_gestor_throttle",
                    tenant_id=tenant_id,
                    numero_hash=numero_desconhecido[-4:] if len(numero_desconhecido) >= 4 else "****",
                )
                return False
        except Exception as exc:
            log.warning("notify_gestor_redis_check_erro", error=str(exc))

    # Buscar candidato em commerce_accounts_b2b por telefone
    candidato_nome = ""
    candidato_cnpj = ""
    try:
        from sqlalchemy import text as _text
        numero_limpo = numero_desconhecido.lstrip("+").lstrip("55")
        result = await session.execute(
            _text("""
                SELECT nome, cnpj, nome_fantasia
                FROM commerce_accounts_b2b
                WHERE tenant_id = :tenant_id
                  AND (
                    telefone LIKE :numero_sufixo
                    OR telefone_celular LIKE :numero_sufixo
                  )
                LIMIT 1
            """),
            {
                "tenant_id": tenant_id,
                "numero_sufixo": f"%{numero_limpo[-8:]}",
            },
        )
        row = result.mappings().first()
        if row:
            candidato_nome = row["nome_fantasia"] or row["nome"] or ""
            candidato_cnpj = row["cnpj"] or ""
    except Exception as exc:
        log.warning("notify_gestor_candidato_lookup_erro", error=str(exc))

    # Montar template da notificação
    msg_preview = mensagem_original[:50] + ("..." if len(mensagem_original) > 50 else "")
    if candidato_nome:
        cnpj_fmt = candidato_cnpj
        # Formatar CNPJ: "12345678000199" → "12.345.678/0001-99"
        if candidato_cnpj and len(candidato_cnpj.replace(".", "").replace("/", "").replace("-", "")) == 14:
            raw = candidato_cnpj.replace(".", "").replace("/", "").replace("-", "")
            cnpj_fmt = f"{raw[:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:14]}"
        template = (
            f"[CONTATO PENDENTE] {numero_desconhecido} mandou: \"{msg_preview}\". "
            f"Possivel cliente: {candidato_nome} (CNPJ {cnpj_fmt}). "
            f"Responda AUTORIZAR {numero_desconhecido} ou abra o painel."
        )
    else:
        template = (
            f"[CONTATO PENDENTE] {numero_desconhecido} mandou: \"{msg_preview}\". "
            f"Responda AUTORIZAR {numero_desconhecido} ou abra o painel."
        )

    # Buscar gestores ativos e notificar
    gestor_repo = GestorRepo()
    gestores = await gestor_repo.listar_ativos_por_tenant(tenant_id=tenant_id, session=session)
    enviou = False
    for gestor in gestores:
        if gestor.telefone:
            try:
                # B-38: assinatura real é (instancia_id, numero, texto)
                await send_whatsapp_message(
                    instancia_id,
                    gestor.telefone,
                    template,
                )
                enviou = True
                log.info(
                    "notify_gestor_enviado",
                    tenant_id=tenant_id,
                    gestor_id=gestor.id,
                )
            except Exception as exc:
                log.warning(
                    "notify_gestor_send_erro",
                    tenant_id=tenant_id,
                    error=str(exc),
                )

    # Registrar throttle no Redis
    if enviou and redis_client is not None:
        try:
            await redis_client.set(throttle_key, "1", ex=throttle_ttl)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("notify_gestor_redis_set_erro", error=str(exc))

    return enviou
