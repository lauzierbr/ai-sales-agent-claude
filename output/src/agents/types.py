"""Tipos do domínio Agents — Pydantic models e enums.

Camada Types: sem imports internos do projeto.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Persona(StrEnum):
    """Persona identificada pelo Identity Router a partir do número WhatsApp."""

    CLIENTE_B2B = "cliente_b2b"
    REPRESENTANTE = "representante"
    DESCONHECIDO = "desconhecido"


class Mensagem(BaseModel):
    """Mensagem WhatsApp normalizada a partir do payload da Evolution API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    de: str          # número remetente (ex: "5519999999999@s.whatsapp.net")
    para: str        # número destinatário ou instancia_id
    texto: str
    tipo: str        # "conversation", "imageMessage", etc.
    instancia_id: str
    timestamp: datetime


class WebhookPayload(BaseModel):
    """Payload recebido da Evolution API no webhook."""

    event: str       # ex: "MESSAGES_UPSERT"
    instance: str    # instancia_id (nome da instância Evolution)
    data: dict       # dados brutos — parseados em Mensagem


class WhatsappInstancia(BaseModel):
    """Associação entre instância Evolution API e tenant."""

    model_config = ConfigDict(from_attributes=True)

    instancia_id: str
    tenant_id: str
    numero_whatsapp: str
    ativo: bool = True
