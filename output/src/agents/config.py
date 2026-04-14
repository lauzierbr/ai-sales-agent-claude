"""Configurações do domínio Agents.

Camada Config: importa apenas stdlib.
Secrets lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import os


class EvolutionConfig:
    """Configuração da Evolution API para envio de mensagens WhatsApp."""

    def __init__(self) -> None:
        self.api_url: str = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self.api_key: str = os.getenv("EVOLUTION_API_KEY", "")
        self.webhook_secret: str = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")

        if not self.api_key:
            raise ValueError(
                "Variável Infisical não configurada: EVOLUTION_API_KEY"
            )
        if not self.webhook_secret:
            raise ValueError(
                "Variável Infisical não configurada: EVOLUTION_WEBHOOK_SECRET"
            )

    def __repr__(self) -> str:
        return f"EvolutionConfig(api_url={self.api_url!r})"


class AgentConfig:
    """Configuração geral dos agentes."""

    mensagem_cliente: str = (
        "Olá! Sou o assistente da {tenant_nome}. "
        "Como posso ajudar? Consulte produtos, verifique pedidos "
        "ou fale com um atendente."
    )
    mensagem_rep: str = (
        "Olá! Use este canal para consultar catálogo, "
        "registrar pedidos da sua carteira ou verificar metas."
    )
    mensagem_desconhecido: str = (
        "Olá! Para atendimento, entre em contato pelo WhatsApp {whatsapp_number}."
    )
