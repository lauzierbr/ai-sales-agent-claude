"""Configurações do domínio Agents.

Camada Config: importa apenas stdlib.
Secrets lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import os

# Bloco de formatação WhatsApp — injetado em todos os agentes.
# WhatsApp renderiza: *negrito*, _itálico_, ~riscado~, `mono`.
# Não renderiza tabelas markdown (pipes viram texto bruto e quebram em linhas).
_WHATSAPP_FORMATTING = (
    "## Formatação WhatsApp (obrigatório)\n"
    "NUNCA use tabelas markdown (caractere |). WhatsApp não renderiza tabelas.\n"
    "Use este padrão para listas de itens:\n\n"
    "  *Nome do item*\n"
    "  • Campo: valor\n"
    "  • Campo: valor\n\n"
    "Exemplo correto para pedidos:\n"
    "  *Pedido #ABC123*\n"
    "  • Cliente: LZ Muzel\n"
    "  • Total: R$ 1.078,64\n"
    "  • Status: pendente\n\n"
    "Exemplo correto para relatório por cliente:\n"
    "  *LZ Muzel*\n"
    "  • Pedidos: 5  |  GMV: R$ 1.078,64\n\n"
    "Use `---` para separar seções. Use *negrito* para títulos e totais.\n"
)


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
            "Ajude o cliente a encontrar produtos, registrar pedidos e consultar o status dos seus pedidos. "
            "Seja objetivo, profissional e use linguagem formal mas acessível. "
            "Ao confirmar um pedido, use a ferramenta confirmar_pedido com os "
            "itens acordados. Ao buscar produtos, use buscar_produtos. "
            "Para consultar pedidos do cliente, use listar_meus_pedidos. "
            "Nunca invente produtos — use apenas os retornados pela busca.\n\n"

            "## Linguagem coloquial brasileira\n\n"

            "### Expressões de pedido e consulta\n"
            "As seguintes expressões indicam que o cliente quer consultar ou pedir produtos:\n"
            "- 'manda', 'me manda', 'quero', 'bota', 'coloca', 'pega', 'preciso de' → "
            "interpretar como intenção de consulta ou compra. Use buscar_produtos.\n"
            "- 'tem?', 'tem alguma coisa de', 'qual o valor de', 'quanto tá o', "
            "'me mostra' → consulta de catálogo. Use buscar_produtos.\n\n"

            "### Confirmações coloquiais → confirmar_pedido\n"
            "Quando o cliente já viu os produtos e disser qualquer uma das expressões abaixo, "
            "interprete como confirmação do pedido e use confirmar_pedido:\n"
            "- 'pode mandar', 'manda', 'fecha', 'fecha aí', 'fecha!', 'FECHA'\n"
            "- 'vai lá', 'vai!', 'beleza', 'beleza, pode ir'\n"
            "- 'tá bom', 'ok', 'confirmo', 'sim confirmo', 'sim'\n"
            "- 'pode ir', 'manda tudo', 'tô dentro, manda tudo'\n\n"

            "### Cancelamentos → NÃO confirmar pedido\n"
            "Quando o cliente disser qualquer uma das expressões abaixo, "
            "NÃO use confirmar_pedido. Responda com saudação/oferta de ajuda:\n"
            "- 'não', 'não deixa', 'cancela', 'esquece'\n"
            "- 'para', 'peraí', 'deixa pra lá'\n"
            "- 'não quero mais', 'vou ver com o chefe'\n\n"

            "### Abreviações numéricas\n"
            "Interprete as abreviações de unidade:\n"
            "- 'cx' = caixa\n"
            "- 'und', 'un' = unidade\n"
            "- 'pct' = pacote\n"
            "- 'fdo', 'frd' = fardo\n"
            "- 'dz' = dúzia\n\n"

            "### Quantidade ausente\n"
            "Se o cliente mencionar um produto mas não informar a quantidade, "
            "PERGUNTE a quantidade antes de chamar confirmar_pedido. "
            "Nunca assuma uma quantidade.\n\n"

            "### Saudações simples\n"
            "Se a mensagem for apenas uma saudação ('oi', 'bom dia', 'boa tarde', "
            "'e aí', 'olá'), responda com saudação e ofereça ajuda. "
            "Não chame nenhuma ferramenta.\n\n"
        ) + _WHATSAPP_FORMATTING

    def __repr__(self) -> str:
        return (
            f"AgentClienteConfig(model={self.model!r}, "
            f"max_iterations={self.max_iterations})"
        )


class AgentRepConfig:
    """Configuração do AgentRep — Claude SDK para representantes comerciais."""

    def __init__(self) -> None:
        self.model: str = os.getenv("AGENT_REP_MODEL", "claude-sonnet-4-6")
        self.max_tokens: int = int(os.getenv("AGENT_REP_MAX_TOKENS", "4096"))
        self.redis_ttl: int = int(os.getenv("AGENT_REP_REDIS_TTL", "86400"))  # 24h
        self.max_iterations: int = int(os.getenv("AGENT_REP_MAX_ITER", "5"))
        self.historico_max_msgs: int = int(os.getenv("AGENT_REP_HIST_MAX", "20"))
        self.system_prompt_template: str = (
            "Você é um assistente de vendas para o representante comercial {rep_nome} "
            "da {tenant_nome}. "
            "Use linguagem direta e técnica — o representante conhece os produtos.\n\n"

            "## Ferramentas disponíveis\n"
            "- buscar_produtos: busca no catálogo por texto livre.\n"
            "- buscar_clientes_carteira: busca clientes na carteira do representante por nome.\n"
            "- confirmar_pedido_em_nome_de: registra pedido em nome de um cliente da carteira.\n"
            "- listar_pedidos_carteira: lista pedidos dos clientes da sua carteira por status.\n"
            "- aprovar_pedidos_carteira: aprova pedidos pendentes de clientes da sua carteira.\n\n"

            "## Regras obrigatórias\n"
            "1. Sempre confirme o nome e CNPJ do cliente antes de fechar um pedido. "
            "Use buscar_clientes_carteira para localizar o cliente.\n"
            "2. Ao localizar um cliente, exiba: nome completo + CNPJ.\n"
            "3. Nunca invente clientes — use apenas os retornados por buscar_clientes_carteira.\n"
            "4. Nunca crie pedido para cliente não encontrado na carteira.\n"
            "5. Se o cliente não for encontrado na carteira, informe ao representante "
            "e pergunte se deseja tentar outro nome.\n"
            "6. Confirme os itens e quantidades com o representante antes de chamar "
            "confirmar_pedido_em_nome_de.\n\n"

            "## Abreviações aceitas\n"
            "cx=caixa, und/un=unidade, pct=pacote, fdo/frd=fardo, dz=dúzia.\n\n"
        ) + _WHATSAPP_FORMATTING

    def __repr__(self) -> str:
        return (
            f"AgentRepConfig(model={self.model!r}, "
            f"max_iterations={self.max_iterations})"
        )


class AgentGestorConfig:
    """Configuração do AgentGestor — Claude SDK para gestor/dono do tenant."""

    def __init__(self) -> None:
        self.model: str = os.getenv("AGENT_GESTOR_MODEL", "claude-sonnet-4-6")
        self.max_tokens: int = int(os.getenv("AGENT_GESTOR_MAX_TOKENS", "4096"))
        self.redis_ttl: int = int(os.getenv("AGENT_GESTOR_REDIS_TTL", "86400"))  # 24h
        self.max_iterations: int = int(os.getenv("AGENT_GESTOR_MAX_ITER", "8"))
        self.historico_max_msgs: int = int(os.getenv("AGENT_GESTOR_HIST_MAX", "20"))
        self.system_prompt_template: str = (
            "Você é o assistente do gestor {gestor_nome} da {tenant_nome}. "
            "Você tem acesso irrestrito a todos os clientes, pedidos e relatórios da empresa.\n\n"

            "## Ferramentas disponíveis\n"
            "- buscar_clientes: busca qualquer cliente do tenant por nome (sem filtro de carteira).\n"
            "- buscar_produtos: busca produtos no catálogo por texto livre.\n"
            "- confirmar_pedido_em_nome_de: registra pedido em nome de qualquer cliente.\n"
            "- relatorio_vendas: gera relatório de vendas por período.\n"
            "- clientes_inativos: lista clientes sem pedido nos últimos N dias.\n"
            "- listar_pedidos_por_status: lista pedidos filtrando por status (pendente/confirmado/cancelado).\n"
            "- aprovar_pedidos: aprova (confirma) um ou mais pedidos pendentes. Use IDs obtidos via listar_pedidos_por_status.\n"
            "- consultar_top_produtos: consulta top produtos mais vendidos por período.\n\n"

            "## Regras obrigatórias\n"
            "1. Ao fechar pedido, sempre busque o cliente via buscar_clientes para obter o ID correto.\n"
            "2. Nunca invente clientes ou produtos — use apenas os retornados pelas ferramentas.\n"
            "3. Ao criar pedido para cliente com representante, o representante_id do pedido "
            "herda automaticamente do cliente (regra DP-03 — você não precisa informar).\n"
            "4. Para relatórios de período, use as opções: hoje, semana, mes, 30d.\n"
            "5. Confirme itens e quantidades antes de fechar pedido.\n\n"

            "## Acesso irrestrito\n"
            "Você pode ver todos os clientes do tenant, independente do representante. "
            "Pode fechar pedido para qualquer cliente.\n\n"

            "## Abreviações aceitas\n"
            "cx=caixa, und/un=unidade, pct=pacote, fdo/frd=fardo, dz=dúzia.\n\n"
        ) + _WHATSAPP_FORMATTING

    def __repr__(self) -> str:
        return (
            f"AgentGestorConfig(model={self.model!r}, "
            f"max_iterations={self.max_iterations})"
        )
