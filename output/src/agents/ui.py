"""UI do domínio Agents — webhook Evolution API e identity router.

Camada UI: importa tudo.
POST /webhook/whatsapp excluído do TenantProvider (resolução via instancia_id).
Decisão D022: validação HMAC-SHA256 + resposta 200 imediata + BackgroundTask.
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from src.agents.service import (
    mark_message_as_read,
    send_typing_indicator,
    validate_webhook_signature,
)
from src.agents.types import WebhookPayload

log = structlog.get_logger(__name__)

router = APIRouter(tags=["agents"])


@router.post("/webhook/whatsapp")
async def webhook_whatsapp(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Recebe webhook da Evolution API e processa em background.

    Fluxo:
    1. Lê body e valida HMAC-SHA256 (X-Evolution-Signature).
    2. Retorna 200 imediatamente.
    3. Background task: resolve tenant → persona → envia resposta.

    Returns:
        {"status": "received"}

    Raises:
        HTTPException 403: se assinatura ausente ou inválida.
    """
    body = await request.body()

    # Valida assinatura HMAC
    signature = request.headers.get("X-Evolution-Signature", "")
    if not signature or not validate_webhook_signature(body, signature):
        log.warning("webhook_assinatura_invalida", path=str(request.url.path))
        raise HTTPException(status_code=403, detail="Assinatura inválida")

    # Parse payload (falha silenciosa — não retorna 422 para Evolution API)
    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception as exc:
        log.warning("webhook_payload_invalido", error=str(exc))
        return JSONResponse({"status": "received"})

    # Processamento em background — resposta não é bloqueada
    background_tasks.add_task(_process_message, payload.model_dump())

    return JSONResponse({"status": "received"})


async def _process_message(payload_dict: dict[str, Any]) -> None:
    """Background task: resolve tenant e persona, envia resposta do agente.

    Cria própria sessão de DB (request session pode estar fechada).
    Injeta dependências no AgentCliente para permitir mock completo em testes.

    Args:
        payload_dict: payload serializado como dict para evitar problemas de serialização.
    """
    import os as _os

    import openai as _openai

    from src.agents.config import AgentClienteConfig, AgentRepConfig
    from src.agents.repo import ClienteB2BRepo, ConversaRepo, RepresentanteRepo
    from src.agents.runtime.agent_cliente import AgentCliente
    from src.agents.runtime.agent_rep import AgentDesconhecido, AgentRep
    from src.agents.service import IdentityRouter, get_instancia, parse_mensagem
    from src.agents.types import Persona, WebhookPayload
    from src.catalog.repo import CatalogRepo
    from src.catalog.service import CatalogService
    from src.orders.config import OrderConfig
    from src.orders.repo import OrderRepo
    from src.orders.runtime.pdf_generator import PDFGenerator
    from src.orders.service import OrderService
    from src.providers.db import get_redis, get_session_factory
    from src.tenants.repo import TenantRepo

    factory = get_session_factory()
    _redis = get_redis()

    # CatalogService — usa embedding OpenAI para busca semântica
    _embedding_client = _openai.AsyncOpenAI(api_key=_os.getenv("OPENAI_API_KEY"))
    _catalog_service = CatalogService(
        repo=CatalogRepo(session_factory=factory),
        enricher=None,  # type: ignore[arg-type]  # não usado na busca
        embedding_client=_embedding_client,
    )

    # Dependências compartilhadas — verificadas antes de uso
    _order_service = OrderService(
        repo=OrderRepo(),
        config=OrderConfig(),
    )
    _pdf_generator = PDFGenerator()

    # Validação de deps não-None
    if _catalog_service is None:
        log.error("deps_catalog_service_none", msg="CatalogService é None — falha na inicialização")
    if _order_service is None:
        log.error("deps_order_service_none", msg="OrderService é None — falha na inicialização")
    if _pdf_generator is None:
        log.error("deps_pdf_generator_none", msg="PDFGenerator é None — falha na inicialização")

    try:
        payload = WebhookPayload.model_validate(payload_dict)
    except Exception as exc:
        log.error("process_message_parse_erro", error=str(exc))
        return

    async with factory() as session:
        # 1. Resolve tenant via instancia
        instancia = await get_instancia(payload.instance, session)
        if instancia is None:
            log.warning("instancia_nao_encontrada", instancia_id=payload.instance)
            return

        tenant_id = instancia.tenant_id

        # 2. Busca tenant para personalização
        tenant_repo = TenantRepo()
        tenant = await tenant_repo.get_by_id(tenant_id, session)
        if tenant is None:
            log.warning("tenant_nao_encontrado", tenant_id=tenant_id)
            return

        # 3. Parseia mensagem (None = ignorar: fromMe, grupo, sem texto)
        try:
            mensagem = parse_mensagem(payload)
        except Exception as exc:
            log.error("parse_mensagem_erro", tenant_id=tenant_id, error=str(exc))
            return

        if mensagem is None:
            log.debug("webhook_mensagem_ignorada", tenant_id=tenant_id, instance=payload.instance)
            return

        # 3b. Feedback visual: marca como lido (✓✓ azul) imediatamente
        await mark_message_as_read(
            instancia_id=payload.instance,
            remote_jid=mensagem.de,
            message_id=mensagem.id,
        )

        # 4. Resolve persona
        identity_router = IdentityRouter()
        persona = await identity_router.resolve(mensagem, tenant_id, session)

        # Log com número hasheado (LGPD)
        from_hash = hashlib.sha256(mensagem.de.encode()).hexdigest()
        log.info(
            "webhook_recebido",
            tenant_id=tenant_id,
            persona=persona.value,
            from_number_hash=from_hash,
        )

        # 4b. Feedback visual: "digitando..." enquanto o agente processa
        await send_typing_indicator(
            instancia_id=payload.instance,
            remote_jid=mensagem.de,
            duration_ms=8000,
        )

        # 5. Chama agente correspondente
        try:
            if persona == Persona.CLIENTE_B2B:
                # Identifica cliente B2B para injetar ID no AgentCliente
                cliente_b2b_id: str | None = None
                telefone_norm = mensagem.de.split("@")[0]
                cliente = await ClienteB2BRepo().get_by_telefone(
                    tenant_id, telefone_norm, session
                )
                if cliente is not None:
                    cliente_b2b_id = cliente.id

                # Instancia AgentCliente com dependências injetadas
                agent_cliente = AgentCliente(
                    order_service=_order_service,
                    conversa_repo=ConversaRepo(),
                    pdf_generator=_pdf_generator,
                    config=AgentClienteConfig(),
                    catalog_service=_catalog_service,
                    redis_client=_redis,
                )
                await agent_cliente.responder(
                    mensagem=mensagem,
                    tenant=tenant,
                    session=session,
                    cliente_b2b_id=cliente_b2b_id,
                    representante_id=None,
                )

            elif persona == Persona.REPRESENTANTE:
                # Identifica representante para injetar no AgentRep
                telefone_norm_rep = mensagem.de.split("@")[0]
                rep = await RepresentanteRepo().get_by_telefone(
                    tenant_id, telefone_norm_rep, session
                )
                if rep is None:
                    log.warning(
                        "representante_nao_encontrado",
                        tenant_id=tenant_id,
                        telefone_hash=hashlib.sha256(telefone_norm_rep.encode()).hexdigest(),
                    )
                    return

                # Instancia AgentRep com dependências injetadas
                agent_rep = AgentRep(
                    order_service=_order_service,
                    conversa_repo=ConversaRepo(),
                    pdf_generator=_pdf_generator,
                    config=AgentRepConfig(),
                    representante=rep,
                    catalog_service=_catalog_service,
                    redis_client=_redis,
                )
                await agent_rep.responder(
                    mensagem=mensagem,
                    tenant=tenant,
                    session=session,
                )

            else:
                await AgentDesconhecido().responder(mensagem, tenant, session)

        except Exception as exc:
            log.error(
                "agent_resposta_erro",
                tenant_id=tenant_id,
                persona=persona.value,
                error=str(exc),
            )
