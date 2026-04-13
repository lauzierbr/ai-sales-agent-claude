"""Configuração raiz do pytest — adiciona output/ ao sys.path.

Permite que os testes importem `from src.catalog.types import ...`
sem precisar de PYTHONPATH=output na linha de comando.
"""

from __future__ import annotations

import os
import sys

# Adiciona output/ ao início do sys.path
_output_path = os.path.join(os.path.dirname(__file__), "output")
if _output_path not in sys.path:
    sys.path.insert(0, _output_path)
