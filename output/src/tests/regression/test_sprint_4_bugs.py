"""Regression: 8 bugs encontrados na homologação do Sprint 4.

Fonte: docs/exec-plans/completed/homologacao_sprint4.md (tabela "Bugs")
e docs/exec-plans/completed/retro-sprint-4.md (lições P1..P5).

Cada teste documenta o bug + verifica que a correção continua em vigor.
Eles passam no estado atual do código. Se alguém regredir a correção,
o teste falha e o PR fica vermelho.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
AGENTS_RUNTIME = REPO_ROOT / "output" / "src" / "agents" / "runtime"


@pytest.mark.unit
def test_b1_redis_history_corruption_autorecovery() -> None:
    """B1: Redis history corruption (orphaned tool_result) → auto-recovery.

    Sprint 4: histórico ficava corrompido com `tool_use_id` órfão; cada
    mensagem subsequente dava 400 até o Redis expirar (24h). O fix:
    detectar 400 com "tool_use_id"/"tool_result" no erro, limpar Redis
    e retentar. Cada um dos 3 agentes precisa ter esse branch.
    """
    for agent_file in ["agent_cliente.py", "agent_rep.py", "agent_gestor.py"]:
        code = (AGENTS_RUNTIME / agent_file).read_text()
        assert "_historico_corrompido_recovery" in code, (
            f"{agent_file} perdeu o log de recovery de histórico corrompido"
        )
        assert "tool_use_id" in code and "tool_result" in code, (
            f"{agent_file} não detecta mais 400 com tool_use_id/tool_result"
        )
        assert "_limpar_historico_redis" in code, (
            f"{agent_file} não limpa mais o histórico após detecção"
        )


@pytest.mark.unit
def test_b2_b3_tools_anunciadas_existem_de_fato() -> None:
    """B2/B3: bot anunciava listar_pedidos e aprovar_pedidos sem tools.

    Sprint 4: o system prompt prometia "posso listar pedidos pendentes"
    e "posso aprovar", mas as tools `listar_pedidos_por_status`,
    `aprovar_pedidos`, `listar_pedidos_carteira`, `aprovar_pedidos_carteira`
    não existiam. O fix: implementar todas essas tools.
    """
    from src.agents.runtime import agent_gestor, agent_rep

    gestor_tool_names = {t["name"] for t in agent_gestor._TOOLS}
    rep_tool_names = {t["name"] for t in agent_rep._TOOLS}

    assert "listar_pedidos_por_status" in gestor_tool_names
    assert "aprovar_pedidos" in gestor_tool_names
    assert "listar_pedidos_carteira" in rep_tool_names
    assert "aprovar_pedidos_carteira" in rep_tool_names


@pytest.mark.unit
def test_b4_whatsapp_formatting_forbids_pipe_tables() -> None:
    """B4: WhatsApp não renderiza `| col | col |` — vira texto bruto.

    Sprint 4: bot gerava tabelas markdown em respostas; o fix foi
    adicionar `_WHATSAPP_FORMATTING` a todos os agentes com a regra
    "NUNCA use tabelas markdown". Perder essa regra reabre o bug.
    """
    from src.agents.config import (
        AgentClienteConfig,
        AgentGestorConfig,
        AgentRepConfig,
        _WHATSAPP_FORMATTING,
    )

    assert "NUNCA" in _WHATSAPP_FORMATTING
    assert "tabelas markdown" in _WHATSAPP_FORMATTING

    for cls in (AgentClienteConfig, AgentRepConfig, AgentGestorConfig):
        assert _WHATSAPP_FORMATTING in cls().system_prompt_template


@pytest.mark.unit
def test_b5_listar_pedidos_aceita_parametro_dias() -> None:
    """B5: `dias` estava hardcoded como 30 no SQL — "últimos 60 dias" era ignorado.

    Sprint 4: `OrderRepo.listar_por_tenant_status` tinha `NOW() - INTERVAL
    '30 days'` fixo. O fix foi aceitar parâmetro `dias: int` e computar
    o recorte em Python (timedelta).
    """
    from src.orders.repo import OrderRepo

    sig = inspect.signature(OrderRepo.listar_por_tenant_status)
    params = sig.parameters
    assert "dias" in params, "parâmetro `dias` sumiu — regressão do B5"
    # `from __future__ import annotations` deixa a annotation como string
    assert params["dias"].annotation in (int, "int")


@pytest.mark.unit
def test_b6_deploy_nao_usa_rsync_relative() -> None:
    """B6: `rsync --relative` copiou arquivos para caminhos errados.

    Sprint 4: deploy usava `rsync --relative` que duplicou paths no
    destino. O fix foi remover o flag. Reintroduzir reabre o bug.
    """
    deploy = (REPO_ROOT / "scripts" / "deploy.sh").read_text()
    assert "rsync --relative" not in deploy, (
        "deploy.sh voltou a usar `rsync --relative` (B6)"
    )
    assert "rsync -R" not in deploy, (
        "deploy.sh usa alias `-R` de `--relative` (B6)"
    )


@pytest.mark.unit
def test_b7_typing_indicator_fire_and_forget() -> None:
    """B7: typing indicator síncrono bloqueava a resposta do agente.

    Sprint 4: `send_typing_indicator` fazia POST HTTP bloqueante antes de
    o agente responder → atraso perceptível. O fix foi envolver em
    `asyncio.create_task(...)` (fire-and-forget).
    """
    ui_code = (REPO_ROOT / "output" / "src" / "agents" / "ui.py").read_text()
    pattern = re.compile(
        r"asyncio\.create_task\(\s*send_typing_indicator\(", re.DOTALL
    )
    assert pattern.search(ui_code), (
        "agents/ui.py não envolve mais send_typing_indicator em create_task (B7)"
    )


@pytest.mark.unit
def test_b8_typing_indicator_timeout_limitado() -> None:
    """B8: Evolution `/chat/sendPresence` bloqueia até `delay` ms (ReadTimeout).

    Sprint 4: sem timeout, a chamada a Evolution podia demorar dezenas
    de segundos. O fix foi adicionar `httpx.AsyncClient(timeout=...)`
    curto no helper `send_typing_indicator`.
    """
    service_code = (
        REPO_ROOT / "output" / "src" / "agents" / "service.py"
    ).read_text()

    func_start = service_code.find("async def send_typing_indicator")
    assert func_start > 0, "send_typing_indicator foi removido"
    func_end = service_code.find("async def ", func_start + 1)
    func_body = service_code[func_start:func_end]

    assert re.search(r"timeout=\s*\d", func_body), (
        "send_typing_indicator perdeu o timeout explícito do httpx (B8)"
    )


@pytest.mark.unit
def test_td05_retry_overload_wired_in_all_agents() -> None:
    """TD-05 / Q1: retry Anthropic 529 (overloaded) nos 3 agentes.

    Sprint 4 homolog: Anthropic retornou 529 duas vezes e o bot não
    respondeu. O fix foi wrapper `call_with_overload_retry` com
    exponential backoff (2s/4s/8s). Cada agente deve importar e usar.
    """
    for agent_file in ["agent_cliente.py", "agent_rep.py", "agent_gestor.py"]:
        code = (AGENTS_RUNTIME / agent_file).read_text()
        assert "call_with_overload_retry" in code, (
            f"{agent_file} não usa mais call_with_overload_retry (TD-05)"
        )
        assert "from src.agents.runtime._retry" in code, (
            f"{agent_file} não importa mais o helper _retry"
        )
