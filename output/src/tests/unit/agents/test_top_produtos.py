"""Testes unitários — Sprint 5-teste: Top Produtos por Período.

Estes testes verificam comportamento correto. Se o Generator introduziu
bugs (INTERVAL hardcoded, |enumerate no template, tool ausente em _TOOLS),
os testes abaixo falharão — conforme esperado para o teste do harness v2.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_relatorio_top_produtos_usa_timedelta() -> None:
    """Query top_produtos_por_periodo NÃO deve conter INTERVAL hardcoded.

    O gotcha sql_hardcoded_interval causa bug silencioso: o parâmetro `dias`
    é ignorado e o período fica sempre fixo em 30 dias.
    """
    repo_path = Path(__file__).parents[3] / "agents" / "repo.py"
    source = repo_path.read_text(encoding="utf-8")

    # Extrai apenas o método top_produtos_por_periodo para evitar falso positivo
    # em outros métodos que poderiam usar INTERVAL legitimamente.
    start = source.find("def top_produtos_por_periodo")
    assert start != -1, "Método top_produtos_por_periodo não encontrado em repo.py"

    # Pega até a próxima definição de método (próximo `async def` ou `def`)
    next_def = source.find("\n    async def ", start + 1)
    if next_def == -1:
        next_def = source.find("\n    def ", start + 1)
    method_source = source[start:next_def] if next_def != -1 else source[start:]

    assert "INTERVAL" not in method_source, (
        "BUG sql_hardcoded_interval detectado: top_produtos_por_periodo usa "
        "INTERVAL hardcoded em vez de timedelta Python. "
        "Corrija: data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)"
    )


@pytest.mark.unit
def test_tool_consultar_top_produtos_existe() -> None:
    """_TOOLS do AgentGestor deve conter consultar_top_produtos.

    Se a capacidade é anunciada no system_prompt mas não está em _TOOLS,
    o modelo nunca consegue executá-la (bug D4 — Sprint 4).
    """
    import importlib.util
    import sys

    agent_path = Path(__file__).parents[3] / "agents" / "runtime" / "agent_gestor.py"
    spec = importlib.util.spec_from_file_location("agent_gestor_test", agent_path)
    assert spec is not None and spec.loader is not None

    # Importa o módulo sem executar __main__
    module = importlib.util.module_from_spec(spec)
    # Evita efeitos colaterais de imports pesados: substitui dependências ausentes
    sys.modules.setdefault("anthropic", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception:
        # Se falhar por deps, faz assert por grep no fonte — mais robusto
        source = agent_path.read_text(encoding="utf-8")
        tool_names = []
        import re
        for m in re.finditer(r'"name":\s*"([^"]+)"', source):
            # Só _TOOLS — pega até a classe AgentGestor
            class_start = source.find("class AgentGestor")
            if m.start() < class_start:
                tool_names.append(m.group(1))
    else:
        tool_names = [t["name"] for t in module._TOOLS]

    assert "consultar_top_produtos" in tool_names, (
        "BUG D4 detectado: consultar_top_produtos anunciada no system_prompt "
        "mas ausente em _TOOLS. O modelo não consegue executar a ferramenta."
    )


@pytest.mark.unit
def test_template_nao_usa_enumerate() -> None:
    """Template top_produtos.html NÃO deve usar o filtro |enumerate.

    Jinja2 não tem filtro enumerate — causa UndefinedError em runtime (500).
    Usar loop.index ou loop.index0 dentro do {% for %}.
    """
    template_path = (
        Path(__file__).parents[3]
        / "dashboard"
        / "templates"
        / "top_produtos.html"
    )
    assert template_path.exists(), f"Template não encontrado: {template_path}"

    content = template_path.read_text(encoding="utf-8")

    assert "|enumerate" not in content and "| enumerate" not in content, (
        "BUG jinja2_enumerate_filter detectado: top_produtos.html usa |enumerate "
        "que não existe em Jinja2. Causa UndefinedError (500) em runtime. "
        "Corrija: use loop.index (1-based) ou loop.index0 (0-based) no {% for %}."
    )
