"""Serviço do domínio Orders — lógica de negócio de pedidos.

Camada Service: importa apenas src.orders.types, src.orders.config e src.orders.repo.
NÃO importa nada de src.agents/ ou src.catalog/.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.config import OrderConfig
from src.orders.repo import OrderRepo
from src.orders.types import CriarPedidoInput, Pedido

log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class OrderService:
    """Serviço de captura e gestão de pedidos B2B."""

    def __init__(
        self,
        repo: OrderRepo,
        config: OrderConfig,
    ) -> None:
        """Inicializa o serviço com dependências injetadas.

        Args:
            repo: repositório de pedidos.
            config: configuração do domínio de pedidos.
        """
        self._repo = repo
        self._config = config

    async def criar_pedido_from_intent(
        self,
        pedido_input: CriarPedidoInput,
        session: AsyncSession,
    ) -> Pedido:
        """Cria pedido a partir de intenção capturada pelo agente.

        Calcula total_estimado em Python (sum dos subtotais dos itens).
        Não delega cálculo ao banco de dados.

        Args:
            pedido_input: DTO com tenant_id, cliente, representante e itens.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Pedido persistido com ID gerado e total_estimado calculado.
        """
        with tracer.start_as_current_span("order_service_criar_pedido") as span:
            span.set_attribute("tenant_id", pedido_input.tenant_id)
            span.set_attribute("n_itens", len(pedido_input.itens))

            # Calcula total em Python — não usar SQLAlchemy Computed
            total_estimado: Decimal = sum(
                (item.quantidade * item.preco_unitario for item in pedido_input.itens),
                Decimal("0"),
            )

            pedido = await self._repo.criar_pedido(
                tenant_id=pedido_input.tenant_id,
                pedido_input=pedido_input,
                total_estimado=total_estimado,
                session=session,
            )

            log.info(
                "pedido_criado_service",
                tenant_id=pedido_input.tenant_id,
                pedido_id=pedido.id,
                total=str(total_estimado),
            )
            return pedido

    async def update_pdf_path(
        self,
        tenant_id: str,
        pedido_id: str,
        pdf_path: str,
        session: AsyncSession,
    ) -> None:
        """Atualiza caminho do PDF após geração.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            pedido_id: ID do pedido.
            pdf_path: caminho relativo do PDF gerado.
            session: sessão SQLAlchemy assíncrona.
        """
        with tracer.start_as_current_span("order_service_update_pdf_path") as span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("pedido_id", pedido_id)

            await self._repo.update_pdf_path(
                tenant_id=tenant_id,
                pedido_id=pedido_id,
                pdf_path=pdf_path,
                session=session,
            )

    async def get_pedidos_pendentes(
        self,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[Pedido]:
        """Retorna pedidos pendentes do tenant para processamento manual.

        Args:
            tenant_id: ID do tenant — filtro obrigatório.
            session: sessão SQLAlchemy assíncrona.

        Returns:
            Lista de Pedido com status PENDENTE, ordenada por criado_em DESC.
        """
        with tracer.start_as_current_span("order_service_get_pendentes") as span:
            span.set_attribute("tenant_id", tenant_id)

            return await self._repo.get_pedidos_pendentes(
                tenant_id=tenant_id,
                session=session,
            )
