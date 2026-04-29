"""Gerador de PDF para pedidos B2B.

Camada Runtime: importa apenas src.orders.types e src.tenants.types.
Usa fpdf2 para gerar PDF A4 com layout profissional.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import structlog
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src.orders.types import Pedido
from src.tenants.types import Tenant

log = structlog.get_logger(__name__)

# Cores (R, G, B)
_COR_AZUL_ESCURO = (0, 51, 102)
_COR_CINZA_CLARO = (240, 240, 240)
_COR_PRETO = (0, 0, 0)
_COR_BRANCO = (255, 255, 255)


class PDFGenerator:
    """Gera PDF de pedido B2B no formato A4."""

    def gerar_pdf_pedido(
        self,
        pedido: Pedido,
        tenant: Tenant,
        *,
        cliente_nome: str | None = None,
        representante_nome: str | None = None,
    ) -> bytes:
        """Gera PDF do pedido com layout A4.

        Layout:
        - Header: nome do tenant em azul escuro
        - Bloco: data + ID curto do pedido + nomes de cliente e rep
        - Tabela: Codigo | Produto | Qtd | Preco Unit. | Subtotal
        - Total alinhado a direita em formato brasileiro
        - Rodape: timestamp e instrucao ao gestor

        Args:
            pedido: pedido completo com itens.
            tenant: dados do tenant para personalizacao do header.
            cliente_nome: nome da empresa cliente B2B (exibido no PDF).
            representante_nome: nome do representante comercial (exibido no PDF).

        Returns:
            PDF como bytes (encapsulado de bytearray retornado pelo fpdf2).
        """
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        self._header(pdf, tenant)
        if pedido.ficticio:
            self._watermark_teste(pdf)
        self._bloco_info(pdf, pedido, cliente_nome=cliente_nome, representante_nome=representante_nome)
        self._tabela_itens(pdf, pedido)
        self._total(pdf, pedido)
        self._rodape(pdf)

        log.info(
            "pdf_gerado",
            pedido_id=pedido.id,
            tenant_id=pedido.tenant_id,
            n_itens=len(pedido.itens),
            ficticio=pedido.ficticio,
        )
        # fpdf2 2.x retorna bytearray — encapsular em bytes()
        return bytes(pdf.output())

    def _watermark_teste(self, pdf: FPDF) -> None:
        """Renderiza marca d'água diagonal 'PEDIDO DE TESTE — NÃO PROCESSAR'.

        Usada quando pedido.ficticio=True (ambientes de staging/desenvolvimento).

        Args:
            pdf: instancia FPDF com página já adicionada.
        """
        # Salva estado para restaurar depois
        pdf.set_font("Helvetica", style="B", size=36)
        pdf.set_text_color(220, 50, 50)

        # Posiciona no centro diagonal da página
        with pdf.rotation(angle=45, x=105, y=148):
            pdf.set_xy(20, 120)
            pdf.cell(
                170,
                20,
                "PEDIDO DE TESTE - NAO PROCESSAR",
                align="C",
            )

        # Restaura cor de texto padrão
        pdf.set_text_color(*_COR_PRETO)

    def _header(self, pdf: FPDF, tenant: Tenant) -> None:
        """Renderiza cabecalho com nome do tenant.

        Args:
            pdf: instancia FPDF.
            tenant: dados do tenant.
        """
        r, g, b = _COR_AZUL_ESCURO
        pdf.set_fill_color(r, g, b)
        pdf.rect(0, 0, 210, 28, style="F")

        pdf.set_text_color(*_COR_BRANCO)
        pdf.set_font("Helvetica", style="B", size=18)
        pdf.set_xy(10, 8)
        pdf.cell(0, 10, tenant.nome, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", size=9)
        pdf.set_xy(10, 18)
        pdf.cell(0, 6, "Pedido B2B - Uso Interno", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_text_color(*_COR_PRETO)
        pdf.ln(8)

    def _bloco_info(
        self,
        pdf: FPDF,
        pedido: Pedido,
        *,
        cliente_nome: str | None = None,
        representante_nome: str | None = None,
    ) -> None:
        """Renderiza bloco com ID do pedido, data, cliente e representante.

        Args:
            pdf: instancia FPDF.
            pedido: pedido com id e criado_em.
            cliente_nome: nome da empresa cliente (preferido ao ID).
            representante_nome: nome do representante (preferido ao ID).
        """
        pdf.set_font("Helvetica", style="B", size=10)
        id_curto = pedido.id[:8].upper()
        pdf.cell(0, 7, f"Pedido: PED-{id_curto}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", size=10)
        data_br = pedido.criado_em.strftime("%d/%m/%Y %H:%M")
        pdf.cell(0, 7, f"Data: {data_br}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Cliente: exibe nome quando disponível, senão ID curto
        if cliente_nome:
            pdf.cell(0, 7, f"Cliente: {cliente_nome}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif pedido.cliente_b2b_id:
            pdf.cell(0, 7, f"Cliente: {pedido.cliente_b2b_id[:8].upper()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Representante: exibe nome quando disponível, senão ID curto
        if representante_nome:
            pdf.cell(0, 7, f"Representante: {representante_nome}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif pedido.representante_id:
            pdf.cell(0, 7, f"Representante: {pedido.representante_id[:8].upper()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(4)

    def _tabela_itens(self, pdf: FPDF, pedido: Pedido) -> None:
        """Renderiza tabela de itens do pedido.

        Args:
            pdf: instancia FPDF.
            pedido: pedido com lista de itens.
        """
        # Cabecalho da tabela
        r, g, b = _COR_AZUL_ESCURO
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(*_COR_BRANCO)
        pdf.set_font("Helvetica", style="B", size=9)

        col_widths = [25, 85, 15, 33, 33]
        headers = ["Codigo", "Produto", "Qtd", "Preco Unit.", "Subtotal"]

        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, border=1, fill=True, align="C")
        pdf.ln()

        # Linhas de dados
        pdf.set_text_color(*_COR_PRETO)
        pdf.set_font("Helvetica", size=9)

        for i, item in enumerate(pedido.itens):
            fill = i % 2 == 1
            if fill:
                r2, g2, b2 = _COR_CINZA_CLARO
                pdf.set_fill_color(r2, g2, b2)

            pdf.cell(col_widths[0], 7, item.codigo_externo, border=1, fill=fill)
            pdf.cell(col_widths[1], 7, item.nome_produto[:55], border=1, fill=fill)
            pdf.cell(col_widths[2], 7, str(item.quantidade), border=1, align="C", fill=fill)
            pdf.cell(col_widths[3], 7, self._fmt_brl(item.preco_unitario), border=1, align="R", fill=fill)
            pdf.cell(col_widths[4], 7, self._fmt_brl(item.subtotal), border=1, align="R", fill=fill)
            pdf.ln()

        pdf.ln(2)

    def _total(self, pdf: FPDF, pedido: Pedido) -> None:
        """Renderiza linha de total estimado alinhada a direita.

        Args:
            pdf: instancia FPDF.
            pedido: pedido com total_estimado.
        """
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.cell(
            0, 8,
            f"Total Estimado: {self._fmt_brl(pedido.total_estimado)}",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(4)

    def _rodape(self, pdf: FPDF) -> None:
        """Renderiza rodape com timestamp e instrucao ao gestor.

        Args:
            pdf: instancia FPDF.
        """
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(100, 100, 100)

        agora = datetime.now(tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        pdf.cell(0, 6, f"Gerado automaticamente em {agora}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(
            0, 6,
            "Instrucao: verifique disponibilidade e processe o pedido no EFOS.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    @staticmethod
    def _fmt_brl(valor: Decimal) -> str:
        """Formata valor decimal no padrão brasileiro (R$ 1.250,00).

        Delega para src.providers.format.format_brl (função central — B-31).
        """
        from src.providers.format import format_brl
        return format_brl(valor)
