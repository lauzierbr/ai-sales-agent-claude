"""Tipos do domínio Agents — Pydantic models e enums.

Camada Types: sem imports internos do projeto.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Persona(StrEnum):
    """Persona identificada pelo Identity Router a partir do número WhatsApp."""

    CLIENTE_B2B = "cliente_b2b"
    REPRESENTANTE = "representante"
    DESCONHECIDO = "desconhecido"
    GESTOR = "gestor"


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
    data: dict[str, Any]       # dados brutos — parseados em Mensagem


class WhatsappInstancia(BaseModel):
    """Associação entre instância Evolution API e tenant."""

    model_config = ConfigDict(from_attributes=True)

    instancia_id: str
    tenant_id: str
    numero_whatsapp: str
    ativo: bool = True


class ClienteB2B(BaseModel):
    """Cliente B2B identificado pelo número de telefone WhatsApp."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    nome: str
    cnpj: str
    telefone: str | None = None  # E.164 digits; None = cliente sem WhatsApp (atendido via rep)
    ativo: bool = True
    criado_em: datetime
    representante_id: str | None = None


class Representante(BaseModel):
    """Representante comercial identificado pelo número de telefone WhatsApp."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    usuario_id: str | None
    telefone: str
    nome: str
    ativo: bool = True


class Conversa(BaseModel):
    """Sessão de conversa entre cliente/rep e o agente."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    telefone: str
    persona: Persona
    iniciada_em: datetime
    encerrada_em: datetime | None = None


class MensagemConversa(BaseModel):
    """Mensagem individual dentro de uma conversa."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    conversa_id: str
    role: str   # "user" ou "assistant"
    conteudo: str
    criado_em: datetime


class ItemIntento(BaseModel):
    """Item de um pedido em fase de intenção (ainda não confirmado)."""

    produto_id: str
    codigo_externo: str
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal


class IntentoPedido(BaseModel):
    """Intenção de pedido capturada pelo AgentCliente durante a conversa."""

    tenant_id: str
    cliente_b2b_id: str | None
    representante_id: str | None
    telefone_solicitante: str
    itens: list[ItemIntento]


class Gestor(BaseModel):
    """Gestor/dono do tenant — acesso irrestrito via WhatsApp e dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    telefone: str
    nome: str
    ativo: bool = True
    criado_em: datetime
