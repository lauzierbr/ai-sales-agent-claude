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
    # Filtra linhas de comentário — o fix pode mencionar o bug no comentário
    # explicativo sem que isso constitua regressão.
    code_lines = [l for l in deploy.splitlines() if not l.strip().startswith("#")]
    deploy_code = "\n".join(code_lines)
    assert "rsync --relative" not in deploy_code, (
        "deploy.sh voltou a usar `rsync --relative` (B6)"
    )
    assert "rsync -R" not in deploy_code, (
        "deploy.sh usa alias `-R` de `--relative` (B6)"
    )


@pytest.mark.unit
def test_b7_typing_indicator_via_context_manager() -> None:
    """B7 (atualizado pós-Sprint 5): typing indicator via context manager.

    Histórico:
    - Sprint 4: typing era síncrono → atraso. Fix: `asyncio.create_task(...)`
      (fire-and-forget).
    - Pós-Sprint 5: fire-and-forget causava 'digitando...' persistente após
      a resposta (Evolution API #1639: sendText não emite 'paused'; race
      condition entre sendPresence e sendText). Fix definitivo: context
      manager `show_typing_presence` que pulsa durante o processamento e
      garante 'paused' explícito ao sair.

    O atraso original foi resolvido por outra via: `_process_message`
    roda como BackgroundTask, então awaitar a presença não bloqueia o
    webhook ACK.
    """
    ui_code = (REPO_ROOT / "output" / "src" / "agents" / "ui.py").read_text()
    pattern = re.compile(
        r"async with show_typing_presence\(", re.DOTALL
    )
    assert pattern.search(ui_code), (
        "agents/ui.py não usa show_typing_presence como context manager (B7)"
    )
    # Anti-regressão: fire-and-forget não deve voltar — ele causa o bug.
    assert "asyncio.create_task(\n            send_typing_indicator" not in ui_code, (
        "fire-and-forget de send_typing_indicator voltou — causa 'digitando' fantasma (B7)"
    )


@pytest.mark.unit
def test_b8_typing_indicator_timeout_limitado() -> None:
    """B8: Evolution `/chat/sendPresence` bloqueia até `delay` ms (ReadTimeout).

    Sprint 4: sem timeout, a chamada a Evolution podia demorar dezenas
    de segundos. O fix foi adicionar `httpx.AsyncClient(timeout=...)`
    curto nos helpers `send_typing_indicator` e `send_typing_stop`.
    """
    service_code = (
        REPO_ROOT / "output" / "src" / "agents" / "service.py"
    ).read_text()

    for fn_name in ("send_typing_indicator", "send_typing_stop"):
        func_start = service_code.find(f"async def {fn_name}")
        assert func_start > 0, f"{fn_name} foi removido"
        func_end = service_code.find("async def ", func_start + 1)
        # Se for a última função, pega até o final do arquivo
        if func_end < 0:
            func_end = len(service_code)
        func_body = service_code[func_start:func_end]

        assert re.search(r"timeout=\s*\d", func_body), (
            f"{fn_name} perdeu o timeout explícito do httpx (B8)"
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
