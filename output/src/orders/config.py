"""Configurações do domínio Orders.

Camada Config: importa apenas stdlib.
Secrets lidos via os.getenv() — nunca hardcoded.
"""

from __future__ import annotations

import os


class OrderConfig:
    """Configuração do domínio de pedidos."""

    def __init__(self) -> None:
        self.pdf_storage_path: str = os.getenv("PDF_STORAGE_PATH", "./pdfs")

    def __repr__(self) -> str:
        return f"OrderConfig(pdf_storage_path={self.pdf_storage_path!r})"
