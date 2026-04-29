"""Formatação de valores monetários e numéricos no padrão pt-BR.

Função central usada por:
- Templates Jinja2 (registrada como filter `|brl` em dashboard/ui.py)
- PDF generator (orders/runtime/pdf_generator.py)
- Agentes runtime (cliente/rep/gestor) ao formatar respostas WhatsApp

Padrão brasileiro:
  - Separador de milhar: ponto (.)
  - Separador decimal: vírgula (,)
  - Prefixo: "R$ "

Exemplos:
  format_brl(1234.5)     → "R$ 1.234,50"
  format_brl(0.5)        → "R$ 0,50"
  format_brl(2106925.14) → "R$ 2.106.925,14"
  format_brl(None)       → "R$ 0,00"
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def format_brl(value: Any) -> str:
    """Formata valor monetário no padrão brasileiro (R$ 1.234,56).

    Aceita Decimal, float, int, str numérica ou None. Em caso de
    valor inválido retorna "R$ 0,00" (defensivo — não quebra a UI).

    Args:
        value: valor a formatar.

    Returns:
        String formatada com prefixo "R$ ".
    """
    if value is None:
        return "R$ 0,00"
    try:
        v = Decimal(str(value))
    except Exception:
        return "R$ 0,00"

    # f"{v:,.2f}" produz "1,234.56" (padrão americano).
    # Trocamos: vírgula → marcador → ponto, ponto → vírgula, marcador → ponto.
    formatted = f"{v:,.2f}"
    formatted = formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {formatted}"


def format_int_br(value: Any) -> str:
    """Formata inteiro no padrão brasileiro (1.234 ao invés de 1,234).

    Útil para contagens (qtde de pedidos, registros, etc).
    """
    if value is None:
        return "0"
    try:
        v = int(Decimal(str(value)))
    except Exception:
        return "0"
    formatted = f"{v:,}"
    return formatted.replace(",", ".")


def register_jinja_filters(env: Any) -> None:
    """Registra os filters pt-BR (`|brl`, `|int_br`) num ambiente Jinja2.

    Chamar uma vez logo após `Jinja2Templates(...)` em cada router que
    renderiza templates HTML (dashboard/ui.py, catalog/ui.py, etc).
    """
    env.filters["brl"] = format_brl
    env.filters["int_br"] = format_int_br
