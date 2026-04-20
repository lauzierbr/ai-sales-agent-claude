"""Agente Gestor/Admin — Claude SDK com ferramentas e memória Redis.

Camada Runtime: pode importar Types, Config, Repo e Service de qualquer domínio.
Não importa UI.

Ferramentas expostas ao modelo:
  - buscar_clientes: busca qualquer cliente do tenant por nome (sem filtro de carteira)
  - buscar_produtos: busca semântica no catálogo
  - confirmar_pedido_em_nome_de: cria pedido em nome de qualquer cliente (DP-03)
  - relatorio_vendas: relatório GMV por período (hoje/semana/mes/30d)
  - clientes_inativos: lista clientes sem pedido nos últimos N dias
  - listar_pedidos_por_status: lista pedidos filtrando por status (pendente/confirmado/cancelado)
  - aprovar_pedidos: aprova (confirma) um ou mais pedidos pendentes em lote

Segurança:
  - Acesso irrestrito — gestor vê todos os clientes do tenant
  - representante_id do pedido herdado do cliente (DP-03)
  - Sem validação de carteira em confirmar_pedido_em_nome_de
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.config import AgentGestorConfig
from src.agents.repo import ClienteB2BRepo, ConversaRepo, RelatorioRepo
from src.agents.runtime._retry import call_with_overload_retry
from src.agents.service import send_whatsapp_media, send_whatsapp_message
from src.agents.types import Gestor, Mensagem, Persona
from src.orders.repo import OrderRepo
from src.orders.service import OrderService
from src.orders.types import CriarPedidoInput, ItemPedidoInput
from src.orders.runtime.pdf_generator import PDFGenerator
from src.tenants.types import Tenant

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "buscar_clientes",
        "description": (
            "Busca clientes do tenant por nome — acesso irrestrito, sem filtro de carteira. "
            "Use para localizar o cliente antes de fechar um pedido."
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
        "name": "buscar_produtos",
        "description": (
            "Busca produtos no catálogo do tenant por texto livre. "
            "Use quando o gestor perguntar sobre produtos, preços ou disponibilidade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de busca — nome, categoria, código ou descrição.",
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
        "name": "confirmar_pedido_em_nome_de",
        "description": (
            "Confirma e registra um pedido em nome de qualquer cliente do tenant. "
            "Não valida carteira. SEMPRE chame buscar_clientes antes para obter o cliente_b2b_id. "
            "Use APENAS quando o gestor confirmar explicitamente o pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_b2b_id": {
                    "type": "string",
                    "description": "ID UUID do cliente B2B obtido via buscar_clientes.",
                },
                "itens": {
                    "type": "array",
                    "description": "Lista de itens do pedido.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "produto_id": {"type": "string"},
                            "codigo_externo": {"type": "string"},
                            "nome_produto": {"type": "string"},
                            "quantidade": {"type": "integer"},
                            "preco_unitario": {"type": "string", "description": "Decimal como string."},
                        },
                        "required": ["produto_id", "codigo_externo", "nome_produto", "quantidade", "preco_unitario"],
                    },
                },
                "observacao": {
                    "type": "string",
                    "description": "Observação opcional.",
                },
            },
            "required": ["cliente_b2b_id", "itens"],
        },
    },
    {
        "name": "relatorio_vendas",
        "description": (
            "Gera relatório de vendas por período. "
            "Períodos: hoje, semana (últimos 7 dias), mes (mês atual), 30d (últimos 30 dias). "
            "Tipos: totais (GMV geral), por_rep (por representante), por_cliente (por cliente)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {
                    "type": "string",
                    "enum": ["hoje", "semana", "mes", "30d"],
                    "description": "Período do relatório.",
                },
                "tipo": {
                    "type": "string",
                    "enum": ["totais", "por_rep", "por_cliente"],
                    "description": "Tipo de agregação. Padrão: totais.",
                    "default": "totais",
                },
            },
            "required": ["periodo"],
        },
    },
    {
        "name": "clientes_inativos",
        "description": (
            "Lista clientes sem pedido nos últimos N dias. "
            "Use para identificar clientes que precisam de follow-up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Número de dias sem pedido para considerar inativo. Padrão: 30.",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "aprovar_pedidos",
        "description": (
            "Aprova (confirma) um ou mais pedidos pendentes. "
            "Status muda de 'pendente' para 'confirmado'. "
            "Use quando o gestor pedir para aprovar ou confirmar pedidos já existentes. "
            "Retorna o resultado de cada pedido individualmente."
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
        "name": "listar_pedidos_por_status",
        "description": (
            "Lista pedidos do tenant filtrando por status e/ou período. "
            "Status disponíveis: pendente, confirmado, cancelado. "
            "Use dias para controlar o período (padrão 30, máximo 365). "
            "Use quando o gestor perguntar sobre pedidos pendentes, confirmados ou histórico."
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
                    "description": "Janela de dias para busca. Padrão: 30. Ex: 60 para últimos 60 dias.",
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
]


class AgentGestor:
    """Agente de atendimento ao gestor/dono via WhatsApp com Claude SDK.

    Acesso irrestrito a todos os clientes e pedidos do tenant.
    Dependências injetadas no construtor para facilitar testes unitários.
    """

    def __init__(
        self,
        order_service: OrderService,
        conversa_repo: ConversaRepo,
        pdf_generator: PDFGenerator,
        config: AgentGestorConfig,
        gestor: Gestor,
        catalog_service: Any | None = None,
        anthropic_client: Any | None = None,
        redis_client: Any | None = None,
        cliente_b2b_repo: ClienteB2BRepo | None = None,
        relatorio_repo: RelatorioRepo | None = None,
        order_repo: OrderRepo | None = None,
    ) -> None:
        """Inicializa AgentGestor com dependências injetadas.

        Args:
            order_service: serviço de pedidos para criar_pedido_from_intent.
            conversa_repo: repositório de conversas e mensagens.
            pdf_generator: gerador de PDF de pedido.
            config: configuração do agente.
            gestor: objeto Gestor identificado pelo webhook.
            catalog_service: serviço de catálogo para busca semântica (opcional).
            anthropic_client: cliente Anthropic assíncrono (opcional).
            redis_client: cliente Redis assíncrono (opcional).
            cliente_b2b_repo: repositório de clientes B2B (opcional).
            relatorio_repo: repositório de relatórios (opcional).
        """
        self._order_service = order_service
        self._conversa_repo = conversa_repo
        self._pdf_generator = pdf_generator
        self._config = config
        self._gestor = gestor
        self._catalog_service = catalog_service
        self._anthropic = anthropic_client
        self._redis = redis_client
        self._cliente_b2b_repo = cliente_b2b_repo or ClienteB2BRepo()
        self._relatorio_repo = relatorio_repo or RelatorioRepo()
        self._order_repo = order_repo or OrderRepo()

    async def responder(
        self,
        mensagem: Mensagem,
        tenant: Tenant,
        session: AsyncSession,
    ) -> None:
        """Responde mensagem do gestor usando Claude SDK com tool use.

        Args:
            mensagem: mensagem recebida do gestor.
            tenant: dados do tenant para personalização.
            session: sessão SQLAlchemy assíncrona.
        """
        with tracer.start_as_current_span("agent_gestor_responder") as span:
            span.set_attribute("tenant_id", tenant.id)
            span.set_attribute("gestor_id", self._gestor.id)

            numero = mensagem.de.split("@")[0]

            conversa = await self._conversa_repo.get_or_create_conversa(
                tenant_id=tenant.id,
                telefone=mensagem.de,
                persona=Persona.GESTOR,
                session=session,
            )

            messages = await self._carregar_historico_redis(tenant.id, numero)
            messages.append({"role": "user", "content": mensagem.texto})

            await self._conversa_repo.add_mensagem(
                conversa_id=conversa.id,
                role="user",
                conteudo=mensagem.texto,
                session=session,
            )

            system_prompt = self._config.system_prompt_template.format(
                tenant_nome=tenant.nome,
                gestor_nome=self._gestor.nome,
            )

            resposta_final: str | None = None
            client = self._get_anthropic_client()

            for iteration in range(self._config.max_iterations):
                try:
                    response = await call_with_overload_retry(
                        client.messages.create,
                        agent_name="gestor",
                        model=self._config.model,
                        max_tokens=self._config.max_tokens,
                        system=system_prompt,
                        tools=_TOOLS,
                        messages=messages,
                    )
                except Exception as api_exc:
                    err_str = str(api_exc)
                    if "400" in err_str and ("tool_use_id" in err_str or "tool_result" in err_str):
                        log.warning(
                            "agent_gestor_historico_corrompido_recovery",
                            tenant_id=tenant.id,
                            error=err_str[:120],
                        )
                        await self._limpar_historico_redis(tenant.id, numero)
                        messages = [{"role": "user", "content": mensagem.texto}]
                        response = await call_with_overload_retry(
                            client.messages.create,
                            agent_name="gestor",
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
                    # model_dump() converte SDK objects para dicts — necessário para
                    # serialização correta no Redis e reenvio à API na próxima iteração
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
                        "agent_gestor_tool_executada",
                        tenant_id=tenant.id,
                        gestor_id=self._gestor.id,
                        iteration=iteration + 1,
                        n_tools=len(tool_results),
                    )
                else:
                    break

            if resposta_final is None:
                resposta_final = (
                    "Desculpe, não consegui processar sua solicitação. "
                    "Por favor, tente novamente."
                )
                log.warning(
                    "agent_gestor_max_iter_atingido",
                    tenant_id=tenant.id,
                    gestor_id=self._gestor.id,
                    max_iterations=self._config.max_iterations,
                )

            await self._conversa_repo.add_mensagem(
                conversa_id=conversa.id,
                role="assistant",
                conteudo=resposta_final,
                session=session,
            )

            await session.commit()

            messages.append({"role": "assistant", "content": resposta_final})
            await self._salvar_historico_redis(tenant.id, numero, messages)

            await send_whatsapp_message(mensagem.instancia_id, numero, resposta_final)

    async def _executar_ferramenta(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tenant: Tenant,
        session: AsyncSession,
        instancia_id: str,
        numero: str,
    ) -> Any:
        """Despacha execução da ferramenta solicitada pelo modelo.

        Args:
            tool_name: nome da ferramenta a executar.
            tool_input: argumentos da ferramenta.
            tenant: dados do tenant.
            session: sessão SQLAlchemy assíncrona.
            instancia_id: instância Evolution API para envio de mídia.
            numero: número do gestor para envio de PDF.

        Returns:
            Resultado serializado da ferramenta.
        """
        if tool_name == "buscar_clientes":
            return await self._buscar_clientes(
                query=tool_input.get("query", ""),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "buscar_produtos":
            return await self._buscar_produtos(
                query=tool_input.get("query", ""),
                limit=tool_input.get("limit", 5),
                tenant_id=tenant.id,
            )

        if tool_name == "confirmar_pedido_em_nome_de":
            return await self._confirmar_pedido(
                cliente_b2b_id=tool_input["cliente_b2b_id"],
                itens=tool_input["itens"],
                observacao=tool_input.get("observacao"),
                tenant=tenant,
                session=session,
                instancia_id=instancia_id,
                numero=numero,
            )

        if tool_name == "relatorio_vendas":
            return await self._relatorio_vendas(
                periodo=tool_input.get("periodo", "hoje"),
                tipo=tool_input.get("tipo", "totais"),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "clientes_inativos":
            return await self._clientes_inativos(
                dias=tool_input.get("dias", 30),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "listar_pedidos_por_status":
            return await self._listar_pedidos_por_status(
                status=tool_input.get("status"),
                dias=tool_input.get("dias", 30),
                limit=tool_input.get("limit", 20),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "aprovar_pedidos":
            return await self._aprovar_pedidos(
                pedido_ids=tool_input.get("pedido_ids", []),
                tenant_id=tenant.id,
                session=session,
            )

        log.warning("agent_gestor_ferramenta_desconhecida", tool_name=tool_name)
        return {"erro": f"Ferramenta desconhecida: {tool_name}"}

    async def _buscar_clientes(
        self, query: str, tenant_id: str, session: AsyncSession
    ) -> list[dict]:
        clientes = await self._cliente_b2b_repo.buscar_todos_por_nome(
            tenant_id=tenant_id,
            query=query,
            session=session,
        )
        return [
            {
                "id": c.id,
                "nome": c.nome,
                "cnpj": c.cnpj,
                "telefone": c.telefone,
                "representante_id": c.representante_id,
            }
            for c in clientes
        ]

    async def _buscar_produtos(
        self, query: str, limit: int, tenant_id: str
    ) -> list[dict]:
        if self._catalog_service is None:
            log.warning("agent_gestor_catalog_service_none", tenant_id=tenant_id)
            return [{"aviso": "Catálogo indisponível no momento. Tente novamente."}]
        try:
            produtos = await self._catalog_service.buscar_produtos(
                tenant_id=tenant_id,
                query=query,
                limit=limit,
            )
            return [
                {
                    "id": str(p.id),
                    "nome": p.nome,
                    "codigo_externo": p.codigo_externo,
                    "preco": str(p.preco) if p.preco else None,
                    "unidade": p.unidade,
                    "descricao": p.descricao,
                }
                for p in produtos
            ]
        except Exception as exc:
            log.error("agent_gestor_busca_produtos_erro", error=str(exc))
            return [{"erro": "Falha ao buscar produtos. Tente novamente."}]

    async def _confirmar_pedido(
        self,
        cliente_b2b_id: str,
        itens: list[dict],
        observacao: str | None,
        tenant: Tenant,
        session: AsyncSession,
        instancia_id: str,
        numero: str,
    ) -> dict:
        # DP-03: herda representante_id do cliente
        cliente = await self._cliente_b2b_repo.get_by_id(
            id=cliente_b2b_id,
            tenant_id=tenant.id,
            session=session,
        )
        if cliente is None:
            return {"erro": f"Cliente {cliente_b2b_id} não encontrado."}

        representante_id = cliente.representante_id

        from decimal import Decimal
        itens_input = [
            ItemPedidoInput(
                produto_id=item["produto_id"],
                codigo_externo=item["codigo_externo"],
                nome_produto=item["nome_produto"],
                quantidade=int(item["quantidade"]),
                preco_unitario=Decimal(str(item["preco_unitario"])),
            )
            for item in itens
        ]

        pedido_input = CriarPedidoInput(
            tenant_id=tenant.id,
            cliente_b2b_id=cliente_b2b_id,
            representante_id=representante_id,
            itens=itens_input,
            observacao=observacao,
        )

        try:
            pedido = await self._order_service.criar_pedido_from_intent(
                pedido_input=pedido_input,
                session=session,
            )

            # Envia PDF ao gestor
            try:
                pdf_bytes = self._pdf_generator.gerar_pdf_pedido(pedido)
                await send_whatsapp_media(
                    instancia_id=instancia_id,
                    numero=numero,
                    pdf_bytes=pdf_bytes,
                    caption=f"Pedido {pedido.numero_pedido} — {cliente.nome}",
                    file_name=f"pedido-{pedido.numero_pedido}.pdf",
                )
            except Exception as exc:
                log.warning("agent_gestor_pdf_erro", error=str(exc))

            return {
                "sucesso": True,
                "pedido_id": str(pedido.id),
                "numero_pedido": pedido.numero_pedido,
                "total_estimado": str(pedido.total_estimado),
                "cliente_nome": cliente.nome,
                "representante_id": representante_id,
            }
        except Exception as exc:
            log.error("agent_gestor_confirmar_pedido_erro", error=str(exc))
            return {"erro": f"Falha ao criar pedido: {exc}"}

    async def _relatorio_vendas(
        self,
        periodo: str,
        tipo: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        now = datetime.now(timezone.utc)
        data_fim = now

        if periodo == "hoje":
            data_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif periodo == "semana":
            data_inicio = now - timedelta(days=7)
        elif periodo == "mes":
            data_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # 30d
            data_inicio = now - timedelta(days=30)

        if tipo == "por_rep":
            dados = await self._relatorio_repo.totais_por_rep(
                tenant_id=tenant_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
                session=session,
            )
        elif tipo == "por_cliente":
            dados = await self._relatorio_repo.totais_por_cliente(
                tenant_id=tenant_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
                session=session,
            )
        else:
            dados = await self._relatorio_repo.totais_periodo(
                tenant_id=tenant_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
                session=session,
            )

        return {"periodo": periodo, "tipo": tipo, "dados": dados}

    async def _clientes_inativos(
        self, dias: int, tenant_id: str, session: AsyncSession
    ) -> list[dict]:
        return await self._relatorio_repo.clientes_inativos(
            tenant_id=tenant_id,
            dias=dias,
            session=session,
        )

    async def _listar_pedidos_por_status(
        self,
        status: str | None,
        dias: int,
        limit: int,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[dict]:
        pedidos = await self._order_repo.listar_por_tenant_status(
            tenant_id=tenant_id,
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

    async def _aprovar_pedidos(
        self,
        pedido_ids: list[str],
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        """Aprova em lote pedidos pendentes do tenant."""
        aprovados = []
        nao_encontrados = []
        for pedido_id in pedido_ids:
            resultado = await self._order_repo.aprovar_pedido(
                tenant_id=tenant_id,
                pedido_id=pedido_id,
                session=session,
            )
            if resultado:
                aprovados.append(pedido_id)
            else:
                nao_encontrados.append(pedido_id)
        await session.commit()
        return {
            "aprovados": aprovados,
            "nao_encontrados": nao_encontrados,
            "total_aprovados": len(aprovados),
        }

    def _get_anthropic_client(self) -> Any:
        if self._anthropic is not None:
            return self._anthropic
        import anthropic
        return anthropic.AsyncAnthropic()

    async def _carregar_historico_redis(
        self, tenant_id: str, numero: str
    ) -> list[dict[str, Any]]:
        if self._redis is None:
            return []
        try:
            key = f"hist:gestor:{tenant_id}:{numero}"
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except Exception as exc:
            log.warning("agent_gestor_redis_load_erro", error=str(exc))
        return []

    async def _salvar_historico_redis(
        self,
        tenant_id: str,
        numero: str,
        messages: list[dict[str, Any]],
    ) -> None:
        if self._redis is None:
            return
        try:
            key = f"hist:gestor:{tenant_id}:{numero}"
            max_msgs = self._config.historico_max_msgs
            trimmed = messages[-max_msgs:] if len(messages) > max_msgs else messages
            await self._redis.set(key, json.dumps(trimmed, default=str), ex=self._config.redis_ttl)
        except Exception as exc:
            log.warning("agent_gestor_redis_save_erro", error=str(exc))

    async def _limpar_historico_redis(self, tenant_id: str, numero: str) -> None:
        if self._redis is None:
            return
        try:
            key = f"hist:gestor:{tenant_id}:{numero}"
            await self._redis.delete(key)
        except Exception as exc:
            log.warning("agent_gestor_redis_clear_erro", error=str(exc))
