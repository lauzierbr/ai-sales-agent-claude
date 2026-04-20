#!/usr/bin/env python3
"""Capability ↔ Tool Coverage Linter (P3 do harness v2).

Para cada agente conversacional (cliente, rep, gestor), cruza:
  - `_TOOLS` em `src/agents/runtime/agent_*.py` (ferramentas reais).
  - `system_prompt_template` em `src/agents/config.py` (capacidades anunciadas).

Regras aplicadas (ambas bloqueantes):

1. **Tool sem capacidade** — se uma ferramenta existe em `_TOOLS` mas seu
   nome não aparece no system prompt, ela é código morto (o model não sabe
   que existe).

2. **Capacidade sem tool** — se uma linha de bullet no system prompt
   menciona um `snake_case_name` que não está em `_TOOLS`, o bot anuncia
   algo que não tem. Foi exatamente o bug `listar_pedidos_por_status` do
   Sprint 4.

Uso:
    python scripts/check_tool_coverage.py
    # exit 0 se OK, 1 se houver divergências.

Reporta no formato:
    capacidade_sem_tool=0 tool_sem_capacidade=0
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

# Repo root = diretório pai deste script
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "output"))

AGENTS = [
    ("cliente", "src.agents.runtime.agent_cliente", "AgentClienteConfig"),
    ("rep", "src.agents.runtime.agent_rep", "AgentRepConfig"),
    ("gestor", "src.agents.runtime.agent_gestor", "AgentGestorConfig"),
]

# Regex que captura nome de ferramenta em linha de bullet:
#   "- nome_da_tool: descrição"
#   "• nome_da_tool: descrição"
# Requer underscore no nome (filtra bullets de UX como "- 'manda'").
_BULLET_TOOL_RE = re.compile(r"^[\-•]\s+([a-z][a-z0-9_]*_[a-z0-9_]+)\s*:", re.MULTILINE)


def _load_tools_and_prompt(
    module_path: str, config_class_name: str
) -> tuple[list[str], str]:
    """Importa módulo runtime + config e devolve (tool_names, system_prompt)."""
    runtime_mod = importlib.import_module(module_path)
    tool_names = [t["name"] for t in runtime_mod._TOOLS]

    config_mod = importlib.import_module("src.agents.config")
    config_cls = getattr(config_mod, config_class_name)
    config = config_cls()
    return tool_names, config.system_prompt_template


def _check_agent(
    agent_name: str, tool_names: list[str], prompt: str
) -> tuple[list[str], list[str]]:
    """Retorna (tools_sem_capacidade, capacidades_sem_tool)."""
    tool_set = set(tool_names)

    # Tool names não mencionados no prompt
    tools_sem_capacidade = [t for t in tool_names if t not in prompt]

    # Candidatos mencionados como bullet mas não em _TOOLS
    candidates = set(_BULLET_TOOL_RE.findall(prompt))
    capacidades_sem_tool = sorted(c for c in candidates if c not in tool_set)

    return tools_sem_capacidade, capacidades_sem_tool


def main() -> int:
    total_cap_sem_tool = 0
    total_tool_sem_cap = 0
    erros: list[str] = []

    for agent_name, module_path, config_class in AGENTS:
        try:
            tool_names, prompt = _load_tools_and_prompt(module_path, config_class)
        except Exception as exc:
            erros.append(f"[{agent_name}] falha importando módulo: {exc}")
            total_tool_sem_cap += 1
            continue

        tools_sem_cap, caps_sem_tool = _check_agent(agent_name, tool_names, prompt)

        print(f"[{agent_name}] tools={len(tool_names)} → {tool_names}")
        if tools_sem_cap:
            total_tool_sem_cap += len(tools_sem_cap)
            for t in tools_sem_cap:
                erros.append(
                    f"[{agent_name}] tool '{t}' em _TOOLS mas não mencionada no system_prompt_template"
                )
        if caps_sem_tool:
            total_cap_sem_tool += len(caps_sem_tool)
            for c in caps_sem_tool:
                erros.append(
                    f"[{agent_name}] bullet '- {c}:' no system_prompt mas tool ausente em _TOOLS"
                )
        if not tools_sem_cap and not caps_sem_tool:
            print(f"  OK: todas as {len(tool_names)} tools alinhadas com o prompt")

    print()
    print(
        f"capacidade_sem_tool={total_cap_sem_tool} "
        f"tool_sem_capacidade={total_tool_sem_cap}"
    )

    if erros:
        print()
        print("Divergências encontradas:")
        for e in erros:
            print(f"  - {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
