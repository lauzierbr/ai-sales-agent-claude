"""Agente Gestor/Admin — Claude SDK com ferramentas e memória Redis.

Camada Runtime: pode importar Types, Config, Repo e Service de qualquer domínio.
Não importa UI.

Ferramentas expostas ao modelo:
  - buscar_clientes: busca qualquer cliente do tenant por nome (sem filtro de carteira)
  - buscar_produtos: busca semântica no catálogo
  - confirmar_pedido_em_nome_de: cria pedido em nome de qualquer cliente (DP-03)
  - relatorio_vendas: relatório GMV por período (hoje/ontem/semana/mes/Nd)
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
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

# Langfuse — instrumentação LLM (condicional: desativado em testes com LANGFUSE_ENABLED=false)
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

from src.agents.config import AgentGestorConfig
from src.agents.repo import ClienteB2BRepo, ConversaRepo, RelatorioRepo
from src.agents.runtime._retry import call_with_overload_retry
from src.agents.service import send_whatsapp_media, send_whatsapp_message
from src.agents.types import Gestor, Mensagem, Persona
from src.commerce.repo import CommerceRepo
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
            "Aceita períodos nomeados (hoje, ontem, semana, mes) ou qualquer número de dias "
            "no formato Nd — ex: '3d', '10d', '45d'. "
            "Tipos: totais (GMV geral), por_rep (por representante), por_cliente (por cliente)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {
                    "type": "string",
                    "description": (
                        "Período do relatório. Exemplos: 'hoje', 'ontem', 'semana' (7 dias), "
                        "'mes' (mês atual), '3d' (últimos 3 dias), '30d' (últimos 30 dias), "
                        "'90d' (últimos 90 dias)."
                    ),
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
        "name": "consultar_top_produtos",
        "description": (
            "Consulta os produtos mais vendidos no tenant por quantidade no período. "
            "Use quando o gestor perguntar sobre ranking de produtos, mais vendidos, "
            "top produtos ou volume de vendas por item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Período em dias para análise. Padrão: 30.",
                    "default": 30,
                },
                "limite": {
                    "type": "integer",
                    "description": "Número máximo de produtos a retornar. Padrão: 5.",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "relatorio_representantes",
        "description": (
            "Ranking de representantes com GMV, número de pedidos e cliente topo no período. "
            "Use quando o gestor perguntar sobre performance de reps, quem vendeu mais, "
            "ranking de representantes ou resultados por rep em qualquer janela de dias."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Período em dias para análise. Ex: 7, 30, 60, 90. Padrão: 30.",
                    "default": 30,
                },
            },
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
    {
        "name": "relatorio_vendas_representante_efos",
        "description": (
            "Relatório de vendas de um representante por mês/ano usando dados EFOS. "
            "Use quando o gestor perguntar sobre vendas de um representante específico. "
            "Aceita variações do nome (ex: 'Rondinele', 'rondinele ritter', 'RONDINELE'). "
            "Retorna total vendido, quantidade de pedidos e lista de clientes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome_rep": {
                    "type": "string",
                    "description": "Nome (ou parte do nome) do representante. Aceita variações.",
                },
                "mes": {
                    "type": "integer",
                    "description": "Mês (1–12) ou string como 'abril', 'mes 4'. Obrigatório.",
                },
                "ano": {
                    "type": "integer",
                    "description": "Ano (ex: 2026). Padrão: ano atual.",
                },
            },
            "required": ["nome_rep", "mes"],
        },
    },
    {
        "name": "relatorio_vendas_cidade_efos",
        "description": (
            "Relatório de vendas por cidade em um mês/ano usando dados EFOS. "
            "Use quando o gestor perguntar sobre vendas em uma cidade específica. "
            "Normaliza cidade para UPPERCASE automaticamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cidade": {
                    "type": "string",
                    "description": "Nome da cidade (case-insensitive).",
                },
                "mes": {
                    "type": "integer",
                    "description": "Mês (1–12). Obrigatório.",
                },
                "ano": {
                    "type": "integer",
                    "description": "Ano (ex: 2026). Padrão: ano atual.",
                },
            },
            "required": ["cidade", "mes"],
        },
    },
    {
        "name": "clientes_inativos_efos",
        "description": (
            "Lista clientes inativos (situacao=2 no EFOS) usando dados sincronizados. "
            "Use quando o gestor perguntar sobre clientes inativos, clientes parados "
            "ou clientes para reativar. "
            "Opcionalmente filtra por cidade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cidade": {
                    "type": "string",
                    "description": "Filtrar por cidade (opcional; case-insensitive). Omita para todas.",
                },
            },
        },
    },
    {
        "name": "registrar_feedback",
        "description": (
            "Registra feedback do gestor sobre uma resposta do assistente. "
            "Use quando o gestor indicar que uma resposta estava errada, incompleta "
            "ou sugerir como deveria ser."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mensagem": {
                    "type": "string",
                    "description": "Texto do feedback do gestor.",
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
        commerce_repo: CommerceRepo | None = None,
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
            order_repo: repositório de pedidos (opcional).
            commerce_repo: repositório de dados EFOS (opcional — para tools EFOS).
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
        self._commerce_repo = commerce_repo or CommerceRepo()

    @_lf_observe(name="processar_mensagem_gestor")  # type: ignore[untyped-decorator]
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
        _lf_ctx.update_current_trace(
            metadata={"persona": "gestor", "tenant_id": tenant.id},
            tags=[tenant.id],
            user_id=tenant.id,
        )
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
            client = self._get_anthropic_client(session_id=str(conversa.id))

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

            _lf_ctx.update_current_observation(output=resposta_final)

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

        if tool_name == "consultar_top_produtos":
            return await self._consultar_top_produtos(
                dias=int(tool_input.get("dias", 30)),
                limite=int(tool_input.get("limite", 5)),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "relatorio_representantes":
            return await self._relatorio_representantes(
                dias=int(tool_input.get("dias", 30)),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "relatorio_vendas_representante_efos":
            return await self._relatorio_vendas_representante_efos(
                nome_rep=tool_input.get("nome_rep", ""),
                mes=tool_input.get("mes", 0),
                ano=tool_input.get("ano", 0),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "relatorio_vendas_cidade_efos":
            return await self._relatorio_vendas_cidade_efos(
                cidade=tool_input.get("cidade", ""),
                mes=tool_input.get("mes", 0),
                ano=tool_input.get("ano", 0),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "clientes_inativos_efos":
            return await self._clientes_inativos_efos(
                cidade=tool_input.get("cidade"),
                tenant_id=tenant.id,
                session=session,
            )

        if tool_name == "registrar_feedback":
            return await self._registrar_feedback(
                mensagem=tool_input.get("mensagem", ""),
                contexto=tool_input.get("contexto", ""),
                de=numero,
                tenant_id=tenant.id,
                session=session,
            )

        log.warning("agent_gestor_ferramenta_desconhecida", tool_name=tool_name)
        return {"erro": f"Ferramenta desconhecida: {tool_name}"}

    async def _buscar_clientes(
        self, query: str, tenant_id: str, session: AsyncSession
    ) -> list[dict]:
        # buscar_todos_com_representante retorna dicts com representante_nome via JOIN
        return await self._cliente_b2b_repo.buscar_todos_com_representante(
            tenant_id=tenant_id,
            query=query,
            session=session,
        )

    async def _buscar_produtos(
        self, query: str, limit: int, tenant_id: str
    ) -> list[dict]:
        if self._catalog_service is None:
            log.warning("agent_gestor_catalog_service_none", tenant_id=tenant_id)
            return [{"aviso": "Catálogo indisponível no momento. Tente novamente."}]
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
            log.error("agent_gestor_busca_produtos_erro", error=str(exc))
            return [{"erro": "Erro ao buscar produtos."}]

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
            ped_num = f"PED-{pedido.id[:8].upper()}"
            try:
                pdf_bytes = self._pdf_generator.gerar_pdf_pedido(
                    pedido, tenant,
                    cliente_nome=cliente.nome,
                )
                await send_whatsapp_media(
                    instancia_id=instancia_id,
                    numero=numero,
                    pdf_bytes=pdf_bytes,
                    caption=f"{ped_num} — {cliente.nome}",
                    file_name=f"pedido-{pedido.id[:8]}.pdf",
                )
            except Exception as exc:
                log.warning("agent_gestor_pdf_erro", error=str(exc))

            return {
                "sucesso": True,
                "pedido_id": str(pedido.id),
                "numero_pedido": ped_num,
                "total_estimado": str(pedido.total_estimado),
                "cliente_nome": cliente.nome,
                "representante_id": representante_id,
            }
        except Exception as exc:
            log.error("agent_gestor_confirmar_pedido_erro", error=str(exc))
            return {"erro": f"Falha ao criar pedido: {exc}"}

    async def _consultar_top_produtos(
        self,
        dias: int,
        limite: int,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        try:
            produtos = await self._relatorio_repo.top_produtos_por_periodo(
                tenant_id=tenant_id,
                dias=dias,
                limite=limite,
                session=session,
            )
            return {"produtos": produtos, "dias": dias, "total": len(produtos)}
        except Exception as exc:
            log.error("agent_gestor_top_produtos_erro", error=str(exc))
            return {"erro": f"Falha ao consultar top produtos: {exc}"}

    async def _relatorio_vendas(
        self,
        periodo: str,
        tipo: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        now = datetime.now(timezone.utc)
        data_fim = now

        hoje_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if periodo == "hoje":
            data_inicio = hoje_inicio
        elif periodo == "ontem":
            data_inicio = hoje_inicio - timedelta(days=1)
            data_fim = hoje_inicio - timedelta(microseconds=1)
        elif periodo == "semana":
            data_inicio = now - timedelta(days=7)
        elif periodo == "mes":
            data_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Aceita qualquer "Nd" — ex: "3d", "15d", "90d"
            match = re.match(r"^(\d+)d$", periodo)
            dias_n = int(match.group(1)) if match else 30
            data_inicio = now - timedelta(days=dias_n)

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
                "representante_nome": p["representante_nome"] or "Sem representante",
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

    async def _relatorio_representantes(
        self,
        dias: int,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[dict]:
        from datetime import datetime, timedelta, timezone
        from src.agents.repo import RelatorioRepo
        now = datetime.now(timezone.utc)
        data_inicio = now - timedelta(days=dias)
        repo = RelatorioRepo()
        rows = await repo.totais_por_rep(
            tenant_id=tenant_id,
            data_inicio=data_inicio,
            data_fim=now,
            session=session,
        )
        return [
            {
                "rep_nome": r.get("rep_nome") or "Sem representante",
                "n_pedidos": r.get("n_pedidos", 0),
                "gmv": float(r.get("total_gmv", 0)),
            }
            for r in rows
        ]

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
            perfil="gestor",
            de=de,
            nome=self._gestor.nome,
            mensagem=mensagem,
            contexto=contexto,
            session=session,
        )
        return {"feedback_id": feedback_id, "status": "registrado"}

    # ─────────────────────────────────────────────────────────────────────────
    # Tools EFOS — relatórios via commerce_*
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_mes(mes: object) -> int:
        """Normaliza mes: 'abril' → 4, 'mes 4' → 4, '4' → 4, 4 → 4.

        Args:
            mes: mês em qualquer formato aceito.

        Returns:
            Inteiro de 1 a 12.

        Raises:
            ValueError: se não conseguir normalizar.
        """
        _MESES = {
            "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
            "abril": 4, "maio": 5, "junho": 6, "julho": 7,
            "agosto": 8, "setembro": 9, "outubro": 10,
            "novembro": 11, "dezembro": 12,
        }
        if isinstance(mes, int):
            return mes
        s = str(mes).strip().lower()
        # Remove prefixo "mes " ou "mês "
        s = s.replace("mês", "").replace("mes", "").strip()
        if s in _MESES:
            return _MESES[s]
        try:
            return int(s)
        except ValueError:
            raise ValueError(f"Não foi possível normalizar mês: {mes!r}")

    async def _fuzzy_match_vendedor(
        self,
        nome_rep: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> str | None:
        """Busca ve_codigo do representante mais próximo via fuzzy match.

        Usa difflib.SequenceMatcher para encontrar o representante cujo ve_nome
        tem similaridade >= 80% com nome_rep.

        Args:
            nome_rep: nome (ou parte do nome) digitado pelo gestor.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            ve_codigo do melhor match, ou None se nenhum atingir threshold 80%.
        """
        import difflib
        from sqlalchemy import text as _text

        result = await session.execute(
            _text("""
                SELECT ve_codigo, ve_nome
                FROM commerce_vendedores
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.mappings().all()

        best_ratio = 0.0
        best_codigo: str | None = None
        nome_lower = nome_rep.lower()

        for row in rows:
            ve_nome = str(row["ve_nome"] or "").lower()
            ratio = difflib.SequenceMatcher(None, nome_lower, ve_nome).ratio()
            # Também testa se nome_rep é substring do ve_nome
            if nome_lower in ve_nome:
                ratio = max(ratio, 0.85)
            if ratio > best_ratio:
                best_ratio = ratio
                best_codigo = str(row["ve_codigo"])

        _FUZZY_THRESHOLD = 0.80
        if best_ratio >= _FUZZY_THRESHOLD:
            log.info(
                "fuzzy_match_vendedor",
                tenant_id=tenant_id,
                nome_rep=nome_rep,
                best_codigo=best_codigo,
                ratio=round(best_ratio, 3),
            )
            return best_codigo

        log.warning(
            "fuzzy_match_vendedor_sem_resultado",
            tenant_id=tenant_id,
            nome_rep=nome_rep,
            best_ratio=round(best_ratio, 3),
        )
        return None

    async def _relatorio_vendas_representante_efos(
        self,
        nome_rep: str,
        mes: object,
        ano: object,
        tenant_id: str,
        session: AsyncSession,
    ) -> dict:
        """Relatório de vendas de representante via commerce_* (dados EFOS).

        Args:
            nome_rep: nome (fuzzy) do representante.
            mes: mês (string ou int).
            ano: ano (int ou 0 = ano atual).
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Dict com resultado ou mensagem de erro.
        """
        try:
            mes_int = self._normalizar_mes(mes)
        except ValueError as exc:
            return {"erro": str(exc)}

        ano_int = int(ano) if ano else datetime.now(timezone.utc).year

        vendedor_id = await self._fuzzy_match_vendedor(nome_rep, tenant_id, session)
        if vendedor_id is None:
            return {
                "erro": f"Representante '{nome_rep}' não encontrado. Verifique o nome.",
                "dica": "Use o nome completo ou parte do nome como aparece no EFOS.",
            }

        dados = await self._commerce_repo.relatorio_vendas_representante(
            tenant_id=tenant_id,
            vendedor_id=vendedor_id,
            mes=mes_int,
            ano=ano_int,
            session=session,
        )
        return {
            "representante": nome_rep,
            "vendedor_id": vendedor_id,
            "mes": mes_int,
            "ano": ano_int,
            "total_vendido": str(dados["total_vendido"]),
            "qtde_pedidos": dados["qtde_pedidos"],
            "clientes": dados["clientes"][:10],  # máximo 10 clientes na resposta
        }

    async def _relatorio_vendas_cidade_efos(
        self,
        cidade: str,
        mes: object,
        ano: object,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[dict] | dict:
        """Relatório de vendas por cidade via commerce_* (dados EFOS).

        Args:
            cidade: nome da cidade (normalizado para UPPERCASE).
            mes: mês.
            ano: ano.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de {cliente, total} ou dict de erro.
        """
        try:
            mes_int = self._normalizar_mes(mes)
        except ValueError as exc:
            return {"erro": str(exc)}

        ano_int = int(ano) if ano else datetime.now(timezone.utc).year
        cidade_upper = cidade.upper()

        dados = await self._commerce_repo.relatorio_vendas_cidade(
            tenant_id=tenant_id,
            cidade=cidade_upper,
            mes=mes_int,
            ano=ano_int,
            session=session,
        )
        return [
            {"cliente": d["cliente"], "total": str(d["total"])}
            for d in dados
        ]

    async def _clientes_inativos_efos(
        self,
        cidade: str | None,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[dict]:
        """Lista clientes inativos EFOS (situacao=2).

        Args:
            cidade: filtrar por cidade (UPPERCASE); None = todas.
            tenant_id: ID do tenant.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de clientes inativos.
        """
        cidade_upper = cidade.upper() if cidade else None
        return await self._commerce_repo.listar_clientes_inativos(
            tenant_id=tenant_id,
            cidade=cidade_upper,
            session=session,
        )

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
