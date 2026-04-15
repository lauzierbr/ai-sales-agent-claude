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


class AgentClienteConfig:
    """Configuração do AgentCliente B2B — Claude SDK."""

    def __init__(self) -> None:
        self.model: str = os.getenv("AGENT_CLIENTE_MODEL", "claude-sonnet-4-5")
        self.max_tokens: int = int(os.getenv("AGENT_CLIENTE_MAX_TOKENS", "4096"))
        self.redis_ttl: int = int(os.getenv("AGENT_CLIENTE_REDIS_TTL", "86400"))  # 24h
        self.max_iterations: int = int(os.getenv("AGENT_CLIENTE_MAX_ITER", "5"))
        self.historico_max_msgs: int = int(os.getenv("AGENT_CLIENTE_HIST_MAX", "20"))
        self.system_prompt_template: str = (
            "Você é um assistente de vendas B2B da {tenant_nome}. "
            "Ajude o cliente a encontrar produtos e registrar pedidos. "
            "Seja objetivo, profissional e use linguagem formal mas acessível. "
            "Ao confirmar um pedido, use a ferramenta confirmar_pedido com os "
            "itens acordados. Ao buscar produtos, use buscar_produtos. "
            "Nunca invente produtos — use apenas os retornados pela busca."
        )

    def __repr__(self) -> str:
        return (
            f"AgentClienteConfig(model={self.model!r}, "
            f"max_iterations={self.max_iterations})"
        )
