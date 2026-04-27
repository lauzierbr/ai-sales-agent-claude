"""Agente Representante Comercial — Claude SDK com ferramentas e memória Redis.

Camada Runtime: pode importar Types, Config, Repo e Service de qualquer domínio.
Não importa UI.

Ferramentas expostas ao modelo:
  - buscar_produtos: busca semântica no catálogo
  - buscar_clientes_carteira: busca clientes da carteira do representante
  - confirmar_pedido_em_nome_de: cria pedido em nome de um cliente da carteira
  - listar_pedidos_carteira: lista pedidos dos clientes da carteira do rep
  - aprovar_pedidos_carteira: aprova pedidos pendentes de clientes da carteira

Memória:
  - Redis: histórico de conversa (TTL 24h, máx 20 mensagens)
  - PostgreSQL: persistência de longo prazo via ConversaRepo

Segurança:
  - confirmar_pedido_em_nome_de valida que cliente_b2b_id pertence à carteira
    do representante (tenant_id + representante_id) antes de criar pedido.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog
from opentelemetry import trace

# Langfuse — instrumentação LLM (condicional)
_LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "true").lower() != "false"
if _LANGFUSE_ENABLED:
    try:
        from langfuse.decorators import langfuse_context as _lf_ctx
        from langfuse.decorators import observe as _lf_observe
    except ImportError:
        _LANGFUSE_ENABLED = False

if not _LANGFUSE_ENABLED:
    def _lf_observe(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return lambda f: f

    class _DummyLfCtx:
        @staticmethod
        def update_current_trace(**kwargs: Any) -> None:
            pass

        @staticmethod
        def update_current_observation(**kwargs: Any) -> None:
            pass

    _lf_ctx = _DummyLfCtx()
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.config import AgentRepConfig
from src.agents.repo import ClienteB2BRepo, ConversaRepo, GestorRepo
from src.agents.runtime._retry import call_with_overload_retry
from src.agents.service import send_whatsapp_media, send_whatsapp_message
from src.agents.types import Mensagem, Persona, Representante
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
            "Use quando o representante perguntar sobre produtos, preços ou disponibilidade."
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
        "name": "buscar_clientes_carteira",
        "description": (
            "Busca clientes na carteira do representante por nome. "
            "Retorna nome, CNPJ e telefone dos clientes encontrados. "
            "Use ANTES de confirmar um pedido para identificar o cliente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nome ou parte do nome do cliente para busca.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "aprovar_pedidos_carteira",
        "description": (
            "Aprova (confirma) pedidos pendentes de clientes da carteira do representante. "
            "Rejeita pedidos de clientes fora da carteira. "
            "Use quando o representante pedir para aprovar ou confirmar pedidos existentes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de IDs dos pedidos a aprovar.",
                },
            },
            "required": ["pedido_ids"],
        },
    },
    {
        "name": "listar_pedidos_carteira",
        "description": (
            "Lista pedidos dos clientes da carteira do representante. "
            "Filtra por status e/ou período (dias). Padrão: últimos 30 dias. "
            "Use quando o representante perguntar sobre pedidos pendentes, histórico ou status de pedidos."
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
                    "description": "Número máximo de pedidos a retornar. Padrão: 20.",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "confirmar_pedido_em_nome_de",
        "description": (
            "Confirma e registra um pedido em nome de um cliente da carteira do representante. "
            "SEMPRE chame buscar_clientes_carteira primeiro para obter o cliente_b2b_id correto. "
            "Use APENAS quando o representante confirmar explicitamente o pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_b2b_id": {
                    "type": "string",
                    "description": "ID UUID do cliente B2B obtido via buscar_clientes_carteira.",
                },
                "itens": {
                    "type": "array",
                    "description": "Lista de itens do pedido.",
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
                    "description": "Observação opcional sobre o pedido.",
                },
            },
            "required": ["cliente_b2b_id", "itens"],
        },
    },
    {
        "name": "registrar_feedback",
        "description": (
            "Registra feedback do representante sobre uma resposta do assistente. "
            "Use quando o representante indicar que uma resposta estava errada, incompleta "
            "ou sugerir como deveria ser."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mensagem": {
                    "type": "string",
                    "description": "Texto do feedback do representante.",
                },
                "contexto": {
                    "type": "string",
                    "description": "Resposta anterior do assistente que motivou o feedback.",
                },
            },
            "required": ["mensagem"],
        },
    },
]


class AgentRep:
    """Agente de atendimento ao representante comercial via WhatsApp com Claude SDK.

    Dependências injetadas no construtor para facilitar testes unitários.
    """

    def __init__(
        self,
        order_service: OrderService,
        conversa_repo: ConversaRepo,
        pdf_generator: PDFGenerator,
        config: AgentRepConfig,
        representante: Representante,
        catalog_service: Any | None = None,  # CatalogService — Any para evitar import circular
        anthropic_client: Any | None = None,  # anthropic.AsyncAnthropic
        redis_client: Any | None = None,  # redis.asyncio.Redis
        cliente_b2b_repo: ClienteB2BRepo | None = None,
        order_repo: OrderRepo | None = None,
        gestor_repo: GestorRepo | None = None,
    ) -> None:
        """Inicializa AgentRep com dependências injetadas.

        Args:
            order_service: serviço de pedidos para criar_pedido_from_intent.
            conversa_repo: repositório de conversas e mensagens.
            pdf_generator: gerador de PDF de pedido.
            config: configuração do agente (model, max_tokens, etc.).
            representante: objeto Representante identificado pelo webhook.
            catalog_service: serviço de catálogo para busca semântica (opcional).
            anthropic_client: cliente Anthropic assíncrono (opcional — criado internamente se None).
            redis_client: cliente Redis assíncrono (opcional — sem memória Redis se None).
            cliente_b2b_repo: repositório de clientes B2B (opcional — instanciado internamente).
            order_repo: repositório de pedidos (opcional — instanciado internamente).
            gestor_repo: repositório de gestores para notificação de pedidos.
        """
        self._order_service = order_service
        self._conversa_repo = conversa_repo
        self._pdf_generator = pdf_generator
        self._config = config
        self._representante = representante
        self._catalog_service = catalog_service
        self._anthropic = anthropic_client
        self._redis = redis_client
        self._cliente_b2b_repo = cliente_b2b_repo or ClienteB2BRepo()
        self._order_repo = order_repo or OrderRepo()
        self._gestor_repo = gestor_repo or GestorRepo()

        # System prompt resolvido na inicialização com nome do representante
        self._system_prompt_cache: str | None = None

    @_lf_observe(name="processar_mensagem_rep")  # type: ignore[untyped-decorator]
    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde mensagem do representante usando Claude SDK com tool use.

        Fluxo:
        1. Obtém/cria conversa com Persona.REPRESENTANTE no PostgreSQL
        2. Carrega histórico do Redis (se disponível)
        3. Chama Claude com ferramentas disponíveis
        4. Executa ferramentas se solicitado (máx max_iterations)
        5. Persiste resposta no banco + commit
        6. Envia resposta final via WhatsApp

        Args:
            mensagem: mensagem recebida do representante.
            tenant: dados do tenant para personalização e notificação.
            session: sessão SQLAlchemy assíncrona.
        """
        _lf_ctx.update_current_trace(
            metadata={"persona": "representante", "tenant_id": tenant.id},
            tags=[tenant.id],
            user_id=tenant.id,
        )
        with tracer.start_as_current_span("agent_rep_responder") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("rep_id", self._representante.id)

            numero = mensagem.de.split("@")[0]

            # 1. Obtém conversa ativa com Persona.REPRESENTANTE
            conversa = await self._conversa_repo.get_or_create_conversa(
                tenant_id=tenant.id,
                telefone=mensagem.de,
                persona=Persona.REPRESENTANTE,
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

            # 5. System prompt — resolve {tenant_nome} e {rep_nome}
            system_prompt = self._get_system_prompt(tenant)

            # 6. Loop de tool use (máx max_iterations)
            resposta_final: str | None = None
            client = self._get_anthropic_client(session_id=str(conversa.id))

            for iteration in range(self._config.max_iterations):
                try:
                    response = await call_with_overload_retry(
                        client.messages.create,
                        agent_name="rep",
                        model=self._config.model,
                        max_tokens=self._config.max_tokens,
                        system=system_prompt,
                        tools=_TOOLS,
                        messages=messages,
                    )
                except Exception as api_exc:
                    err_str = str(api_exc)
                    if "400" in err_str and ("tool_use_id" in err_str or "tool_result" in err_str):
                        log.warning("agent_rep_historico_corrompido_recovery", error=err_str[:120])
                        await self._limpar_historico_redis(tenant.id, numero)
                        messages = [{"role": "user", "content": mensagem.texto}]
                        response = await call_with_overload_retry(
                            client.messages.create,
                            agent_name="rep",
                            model=self._config.model,
                            max_tokens=self._config.max_tokens,
                            system=system_prompt,
                            tools=_TOOLS,
                            messages=messages,
                        )
                    else:
                        raise

                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if block.type == "text":
                            resposta_final = block.text
                            break
                    break

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            resultado = await self._executar_ferramenta(
                                tool_name=block.name,
                                tool_input=block.input,
                                tenant=tenant,
                                session=session,
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
                        "agent_rep_tool_executada",
                        tenant_id=tenant.id,
                        rep_id=self._representante.id,
                        iteration=iteration + 1,
                        n_tools=len(tool_results),
                    )
                else:
                    break

            # 7. Fallback se max_iterations atingido
            if resposta_final is None:
                resposta_final = (
                    "Desculpe, não consegui processar sua solicitação. "
                    "Por favor, tente novamente."
                )
                log.warning(
                    "agent_rep_max_iter_atingido",
                    tenant_id=tenant.id,
                    rep_id=self._representante.id,
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

            _lf_ctx.update_current_observation(output=resposta_final)

            # 10. Envia resposta via WhatsApp para o representante
            await send_whatsapp_message(mensagem.instancia_id, numero, resposta_final)

            log.info(
                "agent_rep_respondeu",
                tenant_id=tenant.id,
                rep_id=self._representante.id,
                conversa_id=conversa.id,
                resposta_len=len(resposta_final),
            )

    def _get_system_prompt(self, tenant: Tenant) -> str:
        """Retorna system prompt resolvido com tenant_nome e rep_nome.

        Args:
            tenant: dados do tenant.

        Returns:
            System prompt com variáveis substituídas.
        """
        if self._system_prompt_cache is None:
            self._system_prompt_cache = self._config.system_prompt_template.format(
                tenant_nome=tenant.nome,
                rep_nome=self._representante.nome,
            )
        return self._system_prompt_cache

    def _get_anthropic_client(self, session_id: str = "") -> Any:
        """Retorna cliente Anthropic com wrapper Langfuse e session_id.

        Args:
            session_id: ID da conversa para rastreamento no Langfuse.

        Returns:
            AsyncAnthropic com wrapper Langfuse ou injetado em testes.
        """
        if self._anthropic is not None:
            return self._anthropic

        import anthropic

        if _LANGFUSE_ENABLED and session_id:
            try:
                _lf_ctx.update_current_trace(session_id=session_id)
            except Exception:
                pass

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
        salvavel = [
            m for m in messages
            if isinstance(m.get("content"), str)
        ]
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
            log.warning("agent_rep_redis_clear_erro", error=str(exc))

    async def _executar_ferramenta(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tenant: Tenant,
        session: AsyncSession,
        instancia_id: str,
        numero: str,
    ) -> dict[str, Any]:
        """Executa ferramenta solicitada pelo modelo.

        Args:
            tool_name: nome da ferramenta.
            tool_input: parâmetros da ferramenta.
            tenant: dados do tenant.
            session: sessão SQLAlchemy.
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

        if tool_name == "buscar_clientes_carteira":
            return await self._buscar_clientes_carteira(
                query=tool_input.get("query", ""),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "aprovar_pedidos_carteira":
            return await self._aprovar_pedidos_carteira(
                pedido_ids=tool_input.get("pedido_ids", []),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "listar_pedidos_carteira":
            return await self._listar_pedidos_carteira(
                status=tool_input.get("status"),
                dias=tool_input.get("dias", 30),
                limit=tool_input.get("limit", 20),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "confirmar_pedido_em_nome_de":
            return await self._confirmar_pedido_em_nome_de(
                tool_input=tool_input,
                tenant=tenant,
                session=session,
                instancia_id=instancia_id,
                numero=numero,
            )

        if tool_name == "registrar_feedback":
            return await self._registrar_feedback(
                mensagem=tool_input.get("mensagem", ""),
                contexto=tool_input.get("contexto", ""),
                de=numero,
                tenant_id=tenant.id,
                session=session,
            )

        log.warning("ferramenta_desconhecida", tool_name=tool_name)
        return {"erro": f"Ferramenta desconhecida: {tool_name}"}

    async def _registrar_feedback(
        self,
        mensagem: str,
        contexto: str,
        de: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        from src.agents.repo_feedback import FeedbackRepo
        feedback_id = await FeedbackRepo().criar(
            tenant_id=tenant_id,
            perfil="rep",
            de=de,
            nome=self._representante.nome,
            mensagem=mensagem,
            contexto=contexto,
            session=session,
        )
        return {"feedback_id": feedback_id, "status": "registrado"}

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

            query_stripped = query.strip()
            if query_stripped.isdigit() and len(query_stripped) >= 4:
                por_codigo = await self._catalog_service.get_por_codigo(
                    tenant_id=tenant_id,
                    codigo_externo=query_stripped,
                )
                if por_codigo is not None:
                    resultados = [por_codigo]

            if not resultados:
                resultados = await self._catalog_service.buscar_semantico(
                    tenant_id=tenant_id,
                    query=query,
                    limit=limit,
                )

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

    async def _buscar_clientes_carteira(
        self,
        query: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Busca clientes na carteira do representante por nome.

        Filtra por tenant_id E representante_id — nunca retorna clientes
        de outro representante ou tenant.

        Args:
            query: texto de busca no nome do cliente.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy.

        Returns:
            Dict com lista de clientes encontrados (cliente_id, nome, cnpj, telefone).
        """
        try:
            clientes = await self._cliente_b2b_repo.buscar_por_nome(
                tenant_id=tenant_id,
                representante_id=self._representante.id,
                query=query,
                session=session,
            )
            return {
                "clientes": [
                    {
                        "cliente_id": c.id,
                        "nome": c.nome,
                        "cnpj": c.cnpj,
                        "telefone": c.telefone,
                    }
                    for c in clientes
                ],
                "total": len(clientes),
            }
        except Exception as exc:
            log.error(
                "buscar_clientes_carteira_erro",
                tenant_id=tenant_id,
                rep_id=self._representante.id,
                error=str(exc),
            )
            return {"clientes": [], "erro": "Erro ao buscar clientes."}

    async def _aprovar_pedidos_carteira(
        self,
        pedido_ids: list[str],
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        """Aprova pedidos validando que cada pedido pertence a cliente da carteira."""
        clientes_carteira = await self._cliente_b2b_repo.listar_por_representante(
            tenant_id=tenant_id,
            representante_id=self._representante.id,
            session=session,
        )
        ids_carteira = {c.id for c in clientes_carteira}

        aprovados = []
        recusados = []
        nao_encontrados = []

        for pedido_id in pedido_ids:
            cliente_b2b_id = await self._order_repo.get_pedido_cliente_b2b_id(
                tenant_id=tenant_id,
                pedido_id=pedido_id,
                session=session,
            )
            if cliente_b2b_id is None:
                nao_encontrados.append(pedido_id)
                continue
            if cliente_b2b_id not in ids_carteira:
                recusados.append(pedido_id)
                continue
            resultado = await self._order_repo.aprovar_pedido(
                tenant_id=tenant_id,
                pedido_id=pedido_id,
                session=session,
            )
            if resultado:
                aprovados.append(pedido_id)
            else:
                nao_encontrados.append(pedido_id)

        if aprovados:
            await session.commit()

        return {
            "aprovados": aprovados,
            "recusados_fora_carteira": recusados,
            "nao_encontrados": nao_encontrados,
            "total_aprovados": len(aprovados),
        }

    async def _listar_pedidos_carteira(
        self,
        status: str | None,
        dias: int,
        limit: int,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[dict]:
        """Lista pedidos da carteira do representante filtrados por status."""
        pedidos = await self._order_repo.listar_por_representante(
            tenant_id=tenant_id,
            representante_id=self._representante.id,
            status=status,
            limit=limit,
            session=session,
            dias=dias,
        )
        return [
            {
                "id": p["id"],
                "cliente_nome": p["cliente_nome"],
                "total_estimado": str(p["total_estimado"]),
                "status": p["status"],
                "criado_em": p["criado_em"].strftime("%d/%m/%Y %H:%M") if p["criado_em"] else None,
            }
            for p in pedidos
        ]

    async def _confirmar_pedido_em_nome_de(
        self,
        tool_input: dict[str, Any],
        tenant: Tenant,
        session: AsyncSession,
        instancia_id: str,
        numero: str,
    ) -> dict[str, Any]:
        """Valida carteira e cria pedido em nome de um cliente.

        Segurança: verifica que cliente_b2b_id pertence à carteira do representante
        (filtra por tenant_id + representante_id) antes de criar o pedido.

        Args:
            tool_input: parâmetros da ferramenta confirmar_pedido_em_nome_de.
            tenant: dados do tenant.
            session: sessão SQLAlchemy.
            instancia_id: ID da instância WhatsApp.
            numero: número do representante remetente.

        Returns:
            Dict com pedido_id e status, ou {"erro": ...} se cliente não na carteira.
        """
        from decimal import Decimal

        cliente_b2b_id: str = tool_input.get("cliente_b2b_id", "")

        # Validação de segurança: cliente deve estar na carteira do representante
        clientes_carteira = await self._cliente_b2b_repo.listar_por_representante(
            tenant_id=tenant.id,
            representante_id=self._representante.id,
            session=session,
        )
        ids_carteira = {c.id for c in clientes_carteira}

        if cliente_b2b_id not in ids_carteira:
            log.warning(
                "confirmar_pedido_cliente_invalido",
                tenant_id=tenant.id,
                rep_id=self._representante.id,
                cliente_b2b_id=cliente_b2b_id,
            )
            return {"erro": "Cliente não encontrado na sua carteira."}

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
            representante_id=self._representante.id,
            itens=itens,
        )

        # Cria pedido no banco
        pedido = await self._order_service.criar_pedido_from_intent(
            pedido_input=pedido_input,
            session=session,
        )

        # Resolve nome do cliente para o PDF (já temos a lista da validação)
        cliente_obj = next((c for c in clientes_carteira if c.id == cliente_b2b_id), None)
        cliente_nome_pdf = cliente_obj.nome if cliente_obj else None

        # Gera PDF e notifica gestor — falha silenciosa: pedido já criado,
        # não podemos perder a confirmação por falha no PDF.
        try:
            pdf_bytes = self._pdf_generator.gerar_pdf_pedido(
                pedido, tenant,
                cliente_nome=cliente_nome_pdf,
                representante_nome=self._representante.nome,
            )

            # Notifica gestores ativos via WhatsApp
            gestores = await self._gestor_repo.listar_ativos_por_tenant(tenant.id, session)
            if gestores:
                total_br = f"{pedido.total_estimado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                caption = (
                    f"Novo pedido PED-{pedido.id[:8].upper()} | "
                    f"Rep: {self._representante.nome} | "
                    f"{len(pedido.itens)} iten(s) | "
                    f"R$ {total_br}"
                )
                for gestor in gestores:
                    try:
                        await send_whatsapp_media(
                            instancia_id=instancia_id,
                            numero=gestor.telefone,
                            pdf_bytes=pdf_bytes,
                            caption=caption,
                            file_name=f"pedido-{pedido.id[:8]}.pdf",
                        )
                    except Exception as exc:
                        log.warning("notif_gestor_falha", gestor_id=gestor.id, error=str(exc))
        except Exception as exc:
            log.warning("agent_rep_pdf_erro", error=str(exc))

        log.info(
            "pedido_rep_confirmado",
            tenant_id=tenant.id,
            rep_id=self._representante.id,
            pedido_id=pedido.id,
            cliente_b2b_id=cliente_b2b_id,
            total=str(pedido.total_estimado),
        )

        return {
            "pedido_id": pedido.id,
            "status": "confirmado",
            "total_estimado": str(pedido.total_estimado),
            "n_itens": len(pedido.itens),
            "representante_id": self._representante.id,
            "mensagem": (
                f"Pedido PED-{pedido.id[:8].upper()} registrado com sucesso em nome do cliente! "
                "O gestor foi notificado."
            ),
        }


class AgentDesconhecido:
    """Agente de resposta para remetentes não identificados."""

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde remetente desconhecido com mensagem de boas-vindas.

        Args:
            mensagem: mensagem recebida.
            tenant: dados do tenant para personalização.
            session: sessão SQLAlchemy.
        """
        with tracer.start_as_current_span("agent_response") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("persona", "desconhecido")
            span.set_attribute("mensagem_len", len(mensagem.texto))

            whatsapp = tenant.whatsapp_number or "da distribuidora"
            texto = (
                f"Olá! Para atendimento, entre em contato pelo WhatsApp {whatsapp}."
            )
            numero = mensagem.de.split("@")[0]

            log.info(
                "agent_desconhecido_respondendo",
                tenant_id=tenant.id,
                instancia_id=mensagem.instancia_id,
            )

            await send_whatsapp_message(mensagem.instancia_id, numero, texto)
