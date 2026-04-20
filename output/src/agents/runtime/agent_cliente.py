"""Agente Cliente B2B — Claude SDK com ferramentas e memória Redis.

Camada Runtime: pode importar Types, Config, Repo e Service de qualquer domínio.
Não importa UI.

Ferramentas expostas ao modelo:
  - buscar_produtos: busca semântica no catálogo
  - confirmar_pedido: cria pedido + gera PDF + notifica gestor/rep
  - listar_meus_pedidos: lista pedidos do próprio cliente por status

Memória:
  - Redis: histórico de conversa (TTL 24h, máx 20 mensagens)
  - PostgreSQL: persistência de longo prazo via ConversaRepo
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.config import AgentClienteConfig
from src.agents.repo import ConversaRepo
from src.agents.runtime._retry import call_with_overload_retry
from src.agents.service import send_whatsapp_media, send_whatsapp_message
from src.agents.types import IntentoPedido, ItemIntento, Mensagem, Persona
from src.orders.repo import OrderRepo
from src.orders.service import OrderService
from src.orders.types import CriarPedidoInput, ItemPedidoInput
from src.orders.runtime.pdf_generator import PDFGenerator
from src.tenants.types import Tenant

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Definição das ferramentas expostas ao Claude
_TOOLS: list[dict[str, Any]] = [
    {
        "name": "buscar_produtos",
        "description": (
            "Busca produtos no catálogo do tenant por texto livre. "
            "Use quando o cliente perguntar sobre produtos, preços ou disponibilidade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de busca — nome, categoria, código ou descrição do produto.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de resultados. Padrão: 5.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "listar_meus_pedidos",
        "description": (
            "Lista os pedidos do próprio cliente filtrando por status. "
            "Retorna apenas os pedidos deste cliente, não de outros. "
            "Use quando o cliente perguntar sobre seus pedidos pendentes, histórico ou status de um pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pendente", "confirmado", "cancelado"],
                    "description": "Filtro por status. Omita para listar todos.",
                },
                "dias": {
                    "type": "integer",
                    "description": "Janela de dias para busca. Padrão: 30.",
                    "default": 30,
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de pedidos a retornar. Padrão: 10.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "confirmar_pedido",
        "description": (
            "Confirma e registra um pedido B2B após o cliente aprovar os itens e quantidades. "
            "Gera PDF e notifica o gestor via WhatsApp. "
            "Use APENAS quando o cliente confirmar explicitamente o pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "itens": {
                    "type": "array",
                    "description": "Lista de itens do pedido confirmado pelo cliente.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "produto_id": {"type": "string", "description": "ID UUID do produto."},
                            "codigo_externo": {"type": "string", "description": "Código do produto no ERP."},
                            "nome_produto": {"type": "string", "description": "Nome comercial do produto."},
                            "quantidade": {"type": "integer", "description": "Quantidade pedida."},
                            "preco_unitario": {"type": "string", "description": "Preço unitário como string decimal."},
                        },
                        "required": ["produto_id", "codigo_externo", "nome_produto", "quantidade", "preco_unitario"],
                    },
                },
                "observacao": {
                    "type": "string",
                    "description": "Observação opcional do cliente sobre o pedido.",
                },
            },
            "required": ["itens"],
        },
    },
]


class AgentCliente:
    """Agente de atendimento ao cliente B2B via WhatsApp com Claude SDK.

    Dependências injetadas no construtor para facilitar testes unitários.
    """

    def __init__(
        self,
        order_service: OrderService,
        conversa_repo: ConversaRepo,
        pdf_generator: PDFGenerator,
        config: AgentClienteConfig,
        catalog_service: Any | None = None,  # CatalogService — Any para evitar import circular
        anthropic_client: Any | None = None,  # anthropic.AsyncAnthropic
        redis_client: Any | None = None,  # redis.asyncio.Redis
        order_repo: OrderRepo | None = None,
    ) -> None:
        """Inicializa AgentCliente com dependências injetadas.

        Args:
            order_service: serviço de pedidos para criar_pedido_from_intent.
            conversa_repo: repositório de conversas e mensagens.
            pdf_generator: gerador de PDF de pedido.
            config: configuração do agente (model, max_tokens, etc.).
            catalog_service: serviço de catálogo para busca semântica (opcional).
            anthropic_client: cliente Anthropic assíncrono (opcional — criado internamente se None).
            redis_client: cliente Redis assíncrono (opcional — sem memória Redis se None).
            order_repo: repositório de pedidos (opcional — instanciado internamente).
        """
        self._order_service = order_service
        self._conversa_repo = conversa_repo
        self._pdf_generator = pdf_generator
        self._config = config
        self._catalog_service = catalog_service
        self._anthropic = anthropic_client
        self._redis = redis_client
        self._order_repo = order_repo or OrderRepo()

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
        cliente_b2b_id: str | None = None,
        representante_id: str | None = None,
    ) -> None:
        """Responde mensagem do cliente usando Claude SDK com tool use.

        Fluxo:
        1. Obtém/cria conversa no PostgreSQL
        2. Carrega histórico do Redis (se disponível)
        3. Chama Claude com ferramentas disponíveis
        4. Executa ferramentas se solicitado (máx max_iterations)
        5. Envia resposta final via WhatsApp

        Args:
            mensagem: mensagem recebida do cliente.
            tenant: dados do tenant para personalização e notificação.
            session: sessão SQLAlchemy assíncrona.
            cliente_b2b_id: ID do cliente B2B identificado (se houver).
            representante_id: ID do representante (se houver).
        """
        with tracer.start_as_current_span("agent_cliente_responder") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("instancia_id", mensagem.instancia_id)

            numero = mensagem.de.split("@")[0]

            # 1. Obtém conversa ativa
            conversa = await self._conversa_repo.get_or_create_conversa(
                tenant_id=tenant.id,
                telefone=mensagem.de,
                persona=Persona.CLIENTE_B2B,
                session=session,
            )

            # 2. Carrega histórico do Redis
            messages = await self._carregar_historico_redis(tenant.id, numero)

            # 3. Adiciona mensagem do usuário
            messages.append({"role": "user", "content": mensagem.texto})

            # 4. Persiste mensagem do usuário no banco
            await self._conversa_repo.add_mensagem(
                conversa_id=conversa.id,
                role="user",
                conteudo=mensagem.texto,
                session=session,
            )

            # 5. System prompt
            system_prompt = self._config.system_prompt_template.format(
                tenant_nome=tenant.nome
            )

            # 6. Loop de tool use (máx max_iterations)
            resposta_final: str | None = None
            client = self._get_anthropic_client()

            for iteration in range(self._config.max_iterations):
                try:
                    response = await call_with_overload_retry(
                        client.messages.create,
                        agent_name="cliente",
                        model=self._config.model,
                        max_tokens=self._config.max_tokens,
                        system=system_prompt,
                        tools=_TOOLS,
                        messages=messages,
                    )
                except Exception as api_exc:
                    err_str = str(api_exc)
                    if "400" in err_str and ("tool_use_id" in err_str or "tool_result" in err_str):
                        log.warning("agent_cliente_historico_corrompido_recovery", error=err_str[:120])
                        await self._limpar_historico_redis(tenant.id, numero)
                        messages = [{"role": "user", "content": mensagem.texto}]
                        response = await call_with_overload_retry(
                            client.messages.create,
                            agent_name="cliente",
                            model=self._config.model,
                            max_tokens=self._config.max_tokens,
                            system=system_prompt,
                            tools=_TOOLS,
                            messages=messages,
                        )
                    else:
                        raise

                if response.stop_reason == "end_turn":
                    # Extrai texto da resposta final
                    for block in response.content:
                        if block.type == "text":
                            resposta_final = block.text
                            break
                    break

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

                    # Executa cada ferramenta solicitada
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            resultado = await self._executar_ferramenta(
                                tool_name=block.name,
                                tool_input=block.input,
                                tenant=tenant,
                                session=session,
                                cliente_b2b_id=cliente_b2b_id,
                                representante_id=representante_id,
                                instancia_id=mensagem.instancia_id,
                                numero=numero,
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(resultado, ensure_ascii=False, default=str),
                            })

                    messages.append({"role": "user", "content": tool_results})
                    log.info(
                        "agent_cliente_tool_executada",
                        tenant_id=tenant.id,
                        iteration=iteration + 1,
                        n_tools=len(tool_results),
                    )
                else:
                    # stop_reason inesperado — sai do loop
                    break

            # 7. Se não houve resposta final (max_iterations atingido ou stop inesperado)
            if resposta_final is None:
                resposta_final = (
                    "Desculpe, não consegui processar sua solicitação. "
                    "Por favor, tente novamente."
                )
                log.warning(
                    "agent_cliente_max_iter_atingido",
                    tenant_id=tenant.id,
                    max_iterations=self._config.max_iterations,
                )

            # 8. Persiste resposta do assistente no banco
            await self._conversa_repo.add_mensagem(
                conversa_id=conversa.id,
                role="assistant",
                conteudo=resposta_final,
                session=session,
            )

            # 8.1 Commit — persiste conversa, mensagens (e pedido se tool foi chamada)
            await session.commit()

            # 9. Atualiza Redis com histórico
            messages.append({"role": "assistant", "content": resposta_final})
            await self._salvar_historico_redis(tenant.id, numero, messages)

            # 10. Envia resposta via WhatsApp
            await send_whatsapp_message(mensagem.instancia_id, numero, resposta_final)

            log.info(
                "agent_cliente_respondeu",
                tenant_id=tenant.id,
                conversa_id=conversa.id,
                resposta_len=len(resposta_final),
            )

    def _get_anthropic_client(self) -> Any:
        """Retorna cliente Anthropic (injetado ou criado internamente).

        Returns:
            Cliente anthropic.AsyncAnthropic.
        """
        if self._anthropic is not None:
            return self._anthropic

        import anthropic

        return anthropic.AsyncAnthropic()

    async def _carregar_historico_redis(
        self, tenant_id: str, telefone_normalizado: str
    ) -> list[dict[str, Any]]:
        """Carrega histórico de conversa do Redis.

        Args:
            tenant_id: ID do tenant.
            telefone_normalizado: número sem @s.whatsapp.net.

        Returns:
            Lista de mensagens em formato anthropic (role + content).
        """
        if self._redis is None:
            return []

        key = f"conv:{tenant_id}:{telefone_normalizado}"
        try:
            data = await self._redis.get(key)
            if data is None:
                return []
            historico: list[dict[str, Any]] = json.loads(data)
            # Limita ao máximo configurado
            return historico[-self._config.historico_max_msgs:]
        except Exception as exc:
            log.warning("redis_historico_erro", tenant_id=tenant_id, error=str(exc))
            return []

    async def _salvar_historico_redis(
        self,
        tenant_id: str,
        telefone_normalizado: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Salva histórico de conversa no Redis com TTL.

        Args:
            tenant_id: ID do tenant.
            telefone_normalizado: número sem @s.whatsapp.net.
            messages: lista de mensagens para persistir.
        """
        if self._redis is None:
            return

        key = f"conv:{tenant_id}:{telefone_normalizado}"
        # Filtra apenas mensagens de texto simples (não tool_use/tool_result)
        salvavel = [
            m for m in messages
            if isinstance(m.get("content"), str)
        ]
        # Limita ao máximo configurado
        salvavel = salvavel[-self._config.historico_max_msgs:]

        try:
            await self._redis.setex(
                key,
                self._config.redis_ttl,
                json.dumps(salvavel, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            log.warning("redis_salvar_erro", tenant_id=tenant_id, error=str(exc))

    async def _limpar_historico_redis(self, tenant_id: str, numero: str) -> None:
        if self._redis is None:
            return
        try:
            key = f"conv:{tenant_id}:{numero}"
            await self._redis.delete(key)
        except Exception as exc:
            log.warning("agent_cliente_redis_clear_erro", error=str(exc))

    async def _executar_ferramenta(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tenant: Tenant,
        session: AsyncSession,
        cliente_b2b_id: str | None,
        representante_id: str | None,
        instancia_id: str,
        numero: str,
    ) -> dict[str, Any]:
        """Executa ferramenta solicitada pelo modelo.

        Args:
            tool_name: nome da ferramenta.
            tool_input: parâmetros da ferramenta.
            tenant: dados do tenant.
            session: sessão SQLAlchemy.
            cliente_b2b_id: ID do cliente B2B (se identificado).
            representante_id: ID do representante (se identificado).
            instancia_id: ID da instância WhatsApp.
            numero: número do remetente.

        Returns:
            Resultado da ferramenta como dict serializável.
        """
        if tool_name == "buscar_produtos":
            return await self._buscar_produtos(
                query=tool_input.get("query", ""),
                limit=tool_input.get("limit", 5),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "listar_meus_pedidos":
            if not cliente_b2b_id:
                return {"erro": "Cliente não identificado — não é possível listar pedidos."}
            return await self._listar_meus_pedidos(
                status=tool_input.get("status"),
                dias=tool_input.get("dias", 30),
                limit=tool_input.get("limit", 10),
                tenant_id=tenant.id,
                cliente_b2b_id=cliente_b2b_id,
                session=session,
            )

        if tool_name == "confirmar_pedido":
            return await self._confirmar_pedido(
                tool_input=tool_input,
                tenant=tenant,
                session=session,
                cliente_b2b_id=cliente_b2b_id,
                representante_id=representante_id,
                instancia_id=instancia_id,
                numero=numero,
            )

        log.warning("ferramenta_desconhecida", tool_name=tool_name)
        return {"erro": f"Ferramenta desconhecida: {tool_name}"}

    async def _listar_meus_pedidos(
        self,
        status: str | None,
        dias: int,
        limit: int,
        tenant_id: str,
        cliente_b2b_id: str,
        session: AsyncSession,
    ) -> list[dict]:
        """Lista pedidos do próprio cliente filtrados por status."""
        pedidos = await self._order_repo.listar_por_cliente(
            tenant_id=tenant_id,
            cliente_b2b_id=cliente_b2b_id,
            status=status,
            limit=limit,
            session=session,
            dias=dias,
        )
        return [
            {
                "id": p["id"],
                "total_estimado": str(p["total_estimado"]),
                "status": p["status"],
                "criado_em": p["criado_em"].strftime("%d/%m/%Y %H:%M") if p["criado_em"] else None,
            }
            for p in pedidos
        ]

    async def _buscar_produtos(
        self,
        query: str,
        limit: int,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Executa busca semântica no catálogo.

        Args:
            query: texto de busca.
            limit: máximo de resultados.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy.

        Returns:
            Dict com lista de produtos encontrados.
        """
        if self._catalog_service is None:
            return {"produtos": [], "aviso": "Catálogo não disponível."}

        try:
            resultados = []

            # Se a query parece um código (só dígitos), tenta lookup exato primeiro
            query_stripped = query.strip()
            if query_stripped.isdigit() and len(query_stripped) >= 4:
                por_codigo = await self._catalog_service.get_por_codigo(
                    tenant_id=tenant_id,
                    codigo_externo=query_stripped,
                )
                if por_codigo is not None:
                    resultados = [por_codigo]

            # Fallback (ou pesquisa normal): busca semântica
            if not resultados:
                resultados = await self._catalog_service.buscar_semantico(
                    tenant_id=tenant_id,
                    query=query,
                    limit=limit,
                )

            # resultados é list[ResultadoBusca]; cada item tem .produto e .score
            produtos = [
                {
                    "produto_id": str(r.produto.id),
                    "codigo_externo": r.produto.codigo_externo,
                    "nome": r.produto.nome or r.produto.nome_bruto,
                    "marca": r.produto.marca,
                    "categoria": r.produto.categoria,
                    "preco_padrao": str(r.produto.preco_padrao) if r.produto.preco_padrao else None,
                    "score": r.score,
                }
                for r in resultados
            ]
            return {"produtos": produtos, "total": len(produtos)}
        except Exception as exc:
            log.error("buscar_produtos_erro", tenant_id=tenant_id, error=str(exc))
            return {"produtos": [], "erro": "Erro ao buscar produtos."}

    async def _confirmar_pedido(
        self,
        tool_input: dict[str, Any],
        tenant: Tenant,
        session: AsyncSession,
        cliente_b2b_id: str | None,
        representante_id: str | None,
        instancia_id: str,
        numero: str,
    ) -> dict[str, Any]:
        """Cria pedido, gera PDF e notifica gestor/rep.

        Args:
            tool_input: parâmetros da ferramenta confirmar_pedido.
            tenant: dados do tenant.
            session: sessão SQLAlchemy.
            cliente_b2b_id: ID do cliente B2B.
            representante_id: ID do representante.
            instancia_id: ID da instância WhatsApp.
            numero: número do remetente.

        Returns:
            Dict com pedido_id e status de confirmação.
        """
        from decimal import Decimal

        itens_input = tool_input.get("itens", [])
        itens = [
            ItemPedidoInput(
                produto_id=item["produto_id"],
                codigo_externo=item["codigo_externo"],
                nome_produto=item["nome_produto"],
                quantidade=item["quantidade"],
                preco_unitario=Decimal(str(item["preco_unitario"])),
            )
            for item in itens_input
        ]

        pedido_input = CriarPedidoInput(
            tenant_id=tenant.id,
            cliente_b2b_id=cliente_b2b_id,
            representante_id=representante_id,
            itens=itens,
        )

        # 1. Cria pedido no banco
        pedido = await self._order_service.criar_pedido_from_intent(
            pedido_input=pedido_input,
            session=session,
        )

        # 2. Gera PDF
        pdf_bytes = self._pdf_generator.gerar_pdf_pedido(pedido, tenant)

        # 3. Notifica gestor via WhatsApp
        if tenant.whatsapp_number:
            total_br = f"{pedido.total_estimado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            caption = (
                f"Novo pedido PED-{pedido.id[:8].upper()} | "
                f"{len(pedido.itens)} iten(s) | "
                f"R$ {total_br}"
            )
            await send_whatsapp_media(
                instancia_id=instancia_id,
                numero=tenant.whatsapp_number,
                pdf_bytes=pdf_bytes,
                caption=caption,
                file_name=f"pedido-{pedido.id[:8]}.pdf",
            )

        log.info(
            "pedido_confirmado",
            tenant_id=tenant.id,
            pedido_id=pedido.id,
            total=str(pedido.total_estimado),
        )

        return {
            "pedido_id": pedido.id,
            "status": "confirmado",
            "total_estimado": str(pedido.total_estimado),
            "n_itens": len(pedido.itens),
            "mensagem": (
                f"Pedido PED-{pedido.id[:8].upper()} registrado com sucesso! "
                "O gestor foi notificado e processara em breve."
            ),
        }
