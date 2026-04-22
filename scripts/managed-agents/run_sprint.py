#!/usr/bin/env python3
"""
run_sprint.py — Orquestrador do harness Planner → Generator → Evaluator

Uso:
    python3 scripts/run_sprint.py "Sprint 0 — Catálogo: crawler + enriquecimento"

Pré-requisitos:
    export ANTHROPIC_API_KEY=...
    export HARNESS_AGENT_PLANNER_ID=...
    export HARNESS_AGENT_GENERATOR_ID=...
    export HARNESS_AGENT_EVALUATOR_ID=...
    export HARNESS_ENVIRONMENT_ID=...
    export HARNESS_STORE_PROJECT_KNOWLEDGE_ID=...
    export HARNESS_STORE_AGENT_PROMPTS_ID=...

    pip install anthropic>=0.52.0
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

BETA_HEADER = "managed-agents-2026-04-01"
IDS_FILE = Path(__file__).parent.parent / ".harness-ids.json"


def _load_ids_file() -> dict:
    """Lê .harness-ids.json se existir. Fallback silencioso."""
    if IDS_FILE.exists():
        try:
            return json.loads(IDS_FILE.read_text())
        except Exception:
            pass
    return {}


def _resolve_id(env_var: str, file_keys: list[str]) -> str:
    """
    Resolve um ID pela ordem de precedência:
      1. Variável de ambiente (Infisical em produção)
      2. .harness-ids.json (desenvolvimento local)
    """
    val = os.environ.get(env_var, "")
    if val:
        return val
    data = _load_ids_file()
    node = data
    for key in file_keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(key, "")
    return node if isinstance(node, str) else ""


# IDs dos recursos — variável de ambiente tem precedência, .harness-ids.json é fallback
AGENT_IDS = {
    "planner":   _resolve_id("HARNESS_AGENT_PLANNER_ID",   ["agents", "planner"]),
    "generator": _resolve_id("HARNESS_AGENT_GENERATOR_ID", ["agents", "generator"]),
    "evaluator": _resolve_id("HARNESS_AGENT_EVALUATOR_ID", ["agents", "evaluator"]),
}
ENVIRONMENT_ID = _resolve_id("HARNESS_ENVIRONMENT_ID", ["environment"])
STORE_IDS = {
    "project_knowledge": _resolve_id(
        "HARNESS_STORE_PROJECT_KNOWLEDGE_ID", ["stores", "project_knowledge"]
    ),
    "agent_prompts": _resolve_id(
        "HARNESS_STORE_AGENT_PROMPTS_ID", ["stores", "agent_prompts"]
    ),
}

# Polling
POLL_INTERVAL_SEC = 5
SESSION_TIMEOUT_SEC = 60 * 60  # 1 hora por session


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários de terminal
# ─────────────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED   = "\033[31m"
CYAN  = "\033[36m"
RESET = "\033[0m"

def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}\n")

def info(text: str) -> None:
    print(f"  {text}")

def ok(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")

def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {text}")

def error(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")

def checkpoint(prompt: str) -> bool:
    """Pausa para decisão humana. Retorna True para continuar, False para abortar."""
    print(f"\n{BOLD}{YELLOW}  ⏸  CHECKPOINT{RESET}")
    print(f"  {prompt}")
    print(f"  {BOLD}[Enter]{RESET} para continuar  |  {BOLD}[a + Enter]{RESET} para abortar\n")
    resp = input("  > ").strip().lower()
    return resp != "a"


# ─────────────────────────────────────────────────────────────────────────────
# Validação de pré-requisitos
# ─────────────────────────────────────────────────────────────────────────────

def validate_env() -> None:
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    for name, val in AGENT_IDS.items():
        if not val:
            missing.append(f"HARNESS_AGENT_{name.upper()}_ID")
    if not ENVIRONMENT_ID:
        missing.append("HARNESS_ENVIRONMENT_ID")
    for name, val in STORE_IDS.items():
        if not val:
            missing.append(f"HARNESS_STORE_{name.upper()}_ID")

    if missing:
        error("Variáveis de ambiente não configuradas:")
        for m in missing:
            print(f"    export {m}=...")
        print()
        print("  Configure via Infisical:")
        print("    infisical run -- python3 scripts/run_sprint.py '...'")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Cliente Anthropic com beta header
# ─────────────────────────────────────────────────────────────────────────────

def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        default_headers={"anthropic-beta": BETA_HEADER},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gestão de Memory Stores
# ─────────────────────────────────────────────────────────────────────────────

def create_active_sprint_store(client: anthropic.Anthropic, sprint_name: str) -> str:
    """Cria um store fresh para o sprint atual. Retorna o ID."""
    store = client.beta.memory_stores.create(
        name=f"active-sprint-{datetime.now().strftime('%Y%m%d-%H%M')}",
        description=(
            f"Artefatos do sprint em execução: {sprint_name}. "
            "Contém spec.md, contract.md, exec-plan.md, handoff.md e qa-report(s). "
            "Read-write para Planner, Generator e Evaluator."
        ),
    )
    ok(f"Store active-sprint criado: {store.id}")
    return store.id


def read_memory(
    client: anthropic.Anthropic,
    store_id: str,
    path: str,
) -> Optional[str]:
    """Lê um documento do store por path. Retorna None se não existir."""
    try:
        memories = client.beta.memory_stores.memories.list(
            store_id, path_prefix=path
        )
        for mem in memories.data:
            if mem.path == path:
                full = client.beta.memory_stores.memories.retrieve(
                    store_id, mem.id
                )
                return full.content
    except Exception:
        pass
    return None


def print_memory(
    client: anthropic.Anthropic,
    store_id: str,
    path: str,
    label: str,
) -> None:
    """Imprime o conteúdo de um documento do store, se existir."""
    content = read_memory(client, store_id, path)
    if content:
        header(label)
        print(content)
    else:
        warn(f"{path} não encontrado no store (agente pode não ter escrito ainda)")


# ─────────────────────────────────────────────────────────────────────────────
# Gestão de Sessions
# ─────────────────────────────────────────────────────────────────────────────

def create_session(
    client: anthropic.Anthropic,
    agent_name: str,
    active_sprint_store_id: str,
    title: str,
) -> str:
    """Cria uma session para o agente dado com os três stores anexados."""
    session = client.beta.sessions.create(
        agent=AGENT_IDS[agent_name],
        environment_id=ENVIRONMENT_ID,
        title=title,
        resources=[
            {
                "type": "memory_store",
                "memory_store_id": STORE_IDS["project_knowledge"],
                "access": "read_only",
                "prompt": (
                    "Conhecimento permanente do projeto: arquitetura, ADRs, "
                    "product sense, design, security, reliability, histórico de sprints. "
                    "Consulte antes de qualquer decisão técnica."
                ),
            },
            {
                "type": "memory_store",
                "memory_store_id": active_sprint_store_id,
                "access": "read_write",
                "prompt": (
                    "Artefatos do sprint em execução. "
                    "Leia spec.md antes de começar. "
                    "Escreva seus artefatos aqui ao concluir."
                ),
            },
            {
                "type": "memory_store",
                "memory_store_id": STORE_IDS["agent_prompts"],
                "access": "read_only",
                "prompt": (
                    "System prompts dos três agentes do harness. "
                    "Consulte o prompt do outro agente quando precisar "
                    "entender o que ele vai verificar ou produzir."
                ),
            },
        ],
    )
    ok(f"Session {agent_name} criada: {session.id}")
    return session.id


def send_event(
    client: anthropic.Anthropic,
    session_id: str,
    message: str,
) -> None:
    """Envia um user.message event para a session."""
    client.beta.sessions.events.create(
        session_id=session_id,
        events=[
            {
                "type": "user.message",
                "content": [{"type": "text", "text": message}],
            }
        ],
    )


def wait_for_idle(
    client: anthropic.Anthropic,
    session_id: str,
    agent_name: str,
    timeout_sec: int = SESSION_TIMEOUT_SEC,
) -> str:
    """
    Aguarda a session entrar em status idle.
    Faz streaming dos eventos para o terminal enquanto espera.
    Retorna o stop_reason final.
    """
    start = time.time()
    last_printed_type = None

    info(f"Aguardando {agent_name} completar...")
    print()

    for event in client.beta.sessions.stream(session_id):
        elapsed = time.time() - start
        if elapsed > timeout_sec:
            error(f"Timeout após {timeout_sec}s aguardando {agent_name}")
            sys.exit(1)

        event_type = getattr(event, "type", "")

        # Imprimir texto do agente em tempo real
        if event_type == "agent.message":
            for block in getattr(event, "content", []):
                if getattr(block, "type", "") == "text":
                    text = block.text
                    if text:
                        if last_printed_type != "agent.message":
                            print(f"  {CYAN}[{agent_name}]{RESET}")
                        print(f"  {text}")
                        last_printed_type = "agent.message"

        # Mostrar uso de tools
        elif event_type == "agent.tool_use":
            tool_name = getattr(event, "name", "?")
            print(f"  {YELLOW}→ tool:{RESET} {tool_name}")
            last_printed_type = "agent.tool_use"

        # Session encerrou
        elif event_type == "session.status_idle":
            stop_reason = getattr(event, "stop_reason", {})
            stop_type = getattr(stop_reason, "type", "end_turn") if stop_reason else "end_turn"
            print()
            return stop_type

        # Erro de session
        elif event_type == "session.error":
            error_msg = getattr(event, "message", str(event))
            error(f"Erro na session do {agent_name}: {error_msg}")
            sys.exit(1)

    return "end_turn"


def archive_session(client: anthropic.Anthropic, session_id: str) -> None:
    """Arquiva a session após uso."""
    try:
        client.beta.sessions.archive(session_id)
    except Exception:
        pass  # não bloqueia o fluxo


# ─────────────────────────────────────────────────────────────────────────────
# Persistência local dos artefatos
# ─────────────────────────────────────────────────────────────────────────────

def save_artifact_locally(content: str, path: str) -> None:
    """
    Salva uma cópia local do artefato em artifacts/.
    Útil para auditoria e para o caso de precisar rodar sem acesso à API.
    """
    os.makedirs("artifacts", exist_ok=True)
    local_path = os.path.join("artifacts", os.path.basename(path))
    with open(local_path, "w") as f:
        f.write(content)
    ok(f"Salvo localmente: {local_path}")


def sync_artifacts_from_store(
    client: anthropic.Anthropic,
    store_id: str,
    sprint_n: int,
) -> None:
    """Baixa todos os artefatos do active-sprint store para artifacts/ local."""
    paths = [
        "/spec.md",
        "/contract.md",
        "/exec-plan.md",
        "/handoff.md",
        "/qa-report.md",
        f"/qa-report-r1.md",
        f"/qa-report-r2.md",
    ]
    for path in paths:
        content = read_memory(client, store_id, path)
        if content:
            filename = f"sprint{sprint_n}{path.replace('/', '_')}"
            os.makedirs("artifacts", exist_ok=True)
            with open(f"artifacts/{filename}", "w") as f:
                f.write(content)


# ─────────────────────────────────────────────────────────────────────────────
# Fluxo principal
# ─────────────────────────────────────────────────────────────────────────────

def run_sprint(sprint_prompt: str) -> None:
    validate_env()
    client = make_client()

    # Extrair número do sprint do prompt (heurística simples)
    sprint_n = "N"
    for word in sprint_prompt.split():
        if word.isdigit():
            sprint_n = word
            break

    header(f"HARNESS — {sprint_prompt}")
    info(f"Iniciado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    info(f"Environment: {ENVIRONMENT_ID}")
    print()

    # ── Criar store do sprint ────────────────────────────────────────────────
    active_store_id = create_active_sprint_store(client, sprint_prompt)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1 — PLANNER
    # ══════════════════════════════════════════════════════════════════════════

    header("FASE 1 — PLANNER")

    planner_session_id = create_session(
        client, "planner", active_store_id,
        title=f"Planner — {sprint_prompt}",
    )

    planner_msg = (
        f"Sprint a planejar: {sprint_prompt}\n\n"
        "Siga o protocolo do seu system prompt:\n"
        "1. Leia os documentos obrigatórios no store project-knowledge\n"
        "2. Identifique ambiguidades antes de gerar o spec\n"
        "3. Se houver ambiguidade, liste as perguntas e aguarde resposta\n"
        "4. Se não houver ambiguidade, gere artifacts/spec.md no store active-sprint\n"
        "5. Crie o exec-plan em active-sprint/exec-plan.md\n"
        "6. Avise quando o spec estiver pronto para revisão"
    )

    send_event(client, planner_session_id, planner_msg)
    stop_reason = wait_for_idle(client, planner_session_id, "Planner")

    # Verificar se o Planner pausou para pedir clarificação
    if stop_reason == "requires_action":
        warn("Planner pausou para clarificação. Verifique o output acima.")
        warn("Responda às perguntas e reenvie o prompt com as respostas.")
        archive_session(client, planner_session_id)
        sys.exit(0)

    # Mostrar spec gerado
    print_memory(client, active_store_id, "/spec.md", "SPEC GERADO PELO PLANNER")

    # ── Checkpoint 1: aprovação do spec ─────────────────────────────────────
    if not checkpoint(
        "Revise o spec acima.\n"
        "  Se precisar de ajustes: responda 'a' para abortar, edite o spec\n"
        "  manualmente em artifacts/ e reexecute com o prompt ajustado.\n"
        "  Se o spec estiver bom: pressione Enter para iniciar o Generator."
    ):
        warn("Sprint abortado pelo usuário após revisão do spec.")
        warn("Ajuste o prompt ou edite artifacts/spec.md e reexecute.")
        archive_session(client, planner_session_id)
        sync_artifacts_from_store(client, active_store_id, sprint_n)
        sys.exit(0)

    archive_session(client, planner_session_id)
    ok("Spec aprovado. Iniciando Generator.")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 2 — GENERATOR (implementação + negociação do contrato)
    # ══════════════════════════════════════════════════════════════════════════

    header("FASE 2 — GENERATOR")

    generator_session_id = create_session(
        client, "generator", active_store_id,
        title=f"Generator — {sprint_prompt}",
    )

    generator_msg = (
        "Leia active-sprint/spec.md.\n\n"
        "Siga o protocolo do seu system prompt em ordem:\n"
        "1. Fase 1: gere a proposta de sprint contract em active-sprint/contract.md\n"
        "   e aguarde revisão do Evaluator antes de começar a implementar\n"
        "2. Fase 2: após contrato ACEITO, implemente o código em output/src/\n"
        "3. Execute o checklist de auto-avaliação completo\n"
        "4. Avise quando a implementação estiver pronta para o Evaluator"
    )

    send_event(client, generator_session_id, generator_msg)

    # O Generator vai pausar internamente para negociar o contrato com o
    # Evaluator. Esse ciclo de negociação pode gerar múltiplos eventos idle.
    # Aguardamos o idle final que indica implementação concluída.
    stop_reason = wait_for_idle(client, generator_session_id, "Generator")

    # Mostrar contrato negociado
    print_memory(
        client, active_store_id, "/contract.md",
        "SPRINT CONTRACT (negociado Generator + Evaluator)"
    )

    # ── Checkpoint 2: revisão opcional do contrato ───────────────────────────
    if not checkpoint(
        "O contrato acima foi negociado entre Generator e Evaluator.\n"
        "  Você pode revisar antes de o Evaluator avaliar o código.\n"
        "  Pressione Enter para continuar para a avaliação."
    ):
        warn("Sprint abortado pelo usuário após revisão do contrato.")
        archive_session(client, generator_session_id)
        sync_artifacts_from_store(client, active_store_id, sprint_n)
        sys.exit(0)

    archive_session(client, generator_session_id)
    ok("Implementação concluída. Iniciando Evaluator.")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 3 — EVALUATOR (rodada 1)
    # ══════════════════════════════════════════════════════════════════════════

    header("FASE 3 — EVALUATOR (rodada 1)")

    evaluator_session_id = create_session(
        client, "evaluator", active_store_id,
        title=f"Evaluator rodada 1 — {sprint_prompt}",
    )

    evaluator_msg = (
        "Leia active-sprint/contract.md e active-sprint/spec.md.\n\n"
        "Execute a avaliação completa seguindo o protocolo do seu system prompt:\n"
        "1. Rode todos os checks automáticos (grep, lint-imports, pytest -m unit)\n"
        "2. Avalie cada critério de Alta com evidência específica\n"
        "3. Avalie critérios de Média e aplique o threshold do contrato\n"
        "4. Salve o relatório em active-sprint/qa-report.md\n"
        "5. Se REPROVADO: salve em active-sprint/qa-report-r1.md também\n"
        "6. Comunique o veredicto final claramente"
    )

    send_event(client, evaluator_session_id, evaluator_msg)
    wait_for_idle(client, evaluator_session_id, "Evaluator")

    qa_content = read_memory(client, active_store_id, "/qa-report.md")
    print_memory(client, active_store_id, "/qa-report.md", "QA REPORT — RODADA 1")

    archive_session(client, evaluator_session_id)

    # ── Verificar veredicto ──────────────────────────────────────────────────
    is_approved = qa_content and "APROVADO" in qa_content.upper()
    is_reprovado = qa_content and "REPROVADO" in qa_content.upper()

    if is_approved:
        header("✅  SPRINT APROVADO")
        ok("Todos os critérios passaram.")
        ok("Sincronizando artefatos localmente...")
        sync_artifacts_from_store(client, active_store_id, sprint_n)
        ok(f"Artefatos salvos em artifacts/sprint{sprint_n}_*.md")
        print()
        info("Próximos passos:")
        info("  1. Revise artifacts/ e commite o código gerado em output/")
        info("  2. Execute os testes de integração manualmente no macmini-lablz")
        info(f"  3. Mova docs/exec-plans/active/sprint-{sprint_n}-*.md → completed/")
        info(f"  4. Execute: python3 scripts/run_sprint.py '<próximo sprint>'")
        return

    if not is_reprovado:
        warn("Não foi possível determinar o veredicto. Verifique qa-report.md manualmente.")
        sync_artifacts_from_store(client, active_store_id, sprint_n)
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 4 — GENERATOR (rodada de correção — única chance)
    # ══════════════════════════════════════════════════════════════════════════

    header("FASE 4 — GENERATOR (rodada de correção)")
    warn("Sprint reprovado. Iniciando única rodada de correção.")

    generator_correction_id = create_session(
        client, "generator", active_store_id,
        title=f"Generator correção — {sprint_prompt}",
    )

    correction_msg = (
        "O sprint foi REPROVADO. Leia active-sprint/qa-report-r1.md.\n\n"
        "Esta é sua ÚNICA rodada de correção. Se reprovar novamente,\n"
        "você deve escalar para o usuário — não tentar uma terceira vez.\n\n"
        "Siga o protocolo de reprovação do seu system prompt:\n"
        "1. Leia o relatório completo antes de tocar em qualquer arquivo\n"
        "2. Corrija na ordem de prioridade: Segurança → Funcionalidade → Média\n"
        "3. Registre cada correção no exec-plan (active-sprint/exec-plan.md)\n"
        "4. Execute o checklist de auto-avaliação completo\n"
        "5. Resubmeta ao Evaluator com a mensagem de rodada de correção"
    )

    send_event(client, generator_correction_id, correction_msg)
    wait_for_idle(client, generator_correction_id, "Generator (correção)")
    archive_session(client, generator_correction_id)

    ok("Correção concluída. Iniciando Evaluator (rodada 2).")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 5 — EVALUATOR (rodada 2 — definitiva)
    # ══════════════════════════════════════════════════════════════════════════

    header("FASE 5 — EVALUATOR (rodada 2 — definitiva)")

    evaluator_r2_id = create_session(
        client, "evaluator", active_store_id,
        title=f"Evaluator rodada 2 — {sprint_prompt}",
    )

    evaluator_r2_msg = (
        "Esta é a rodada 2 — avaliação definitiva após correção.\n\n"
        "Leia active-sprint/contract.md e active-sprint/qa-report-r1.md\n"
        "(para comparar com a rodada anterior).\n\n"
        "Execute a avaliação completa novamente:\n"
        "1. Rode todos os checks automáticos\n"
        "2. Avalie cada critério de Alta\n"
        "3. Avalie critérios de Média e threshold\n"
        "4. Salve o relatório em active-sprint/qa-report-r2.md com\n"
        "   a seção comparativa de rodadas obrigatória\n"
        "5. Se REPROVADO: não comunique ao Generator — o usuário\n"
        "   receberá o relatório e decidirá o próximo passo"
    )

    send_event(client, evaluator_r2_id, evaluator_r2_msg)
    wait_for_idle(client, evaluator_r2_id, "Evaluator (rodada 2)")

    qa_r2_content = read_memory(client, active_store_id, "/qa-report-r2.md")
    print_memory(client, active_store_id, "/qa-report-r2.md", "QA REPORT — RODADA 2")

    archive_session(client, evaluator_r2_id)
    sync_artifacts_from_store(client, active_store_id, sprint_n)

    is_approved_r2 = qa_r2_content and "APROVADO" in qa_r2_content.upper()

    if is_approved_r2:
        header("✅  SPRINT APROVADO (após correção)")
        ok(f"Artefatos salvos em artifacts/sprint{sprint_n}_*.md")
        print()
        info("Próximos passos:")
        info("  1. Revise artifacts/ e commite o código gerado em output/")
        info("  2. Execute os testes de integração manualmente no macmini-lablz")
        info(f"  3. Mova docs/exec-plans/active/sprint-{sprint_n}-*.md → completed/")
        info(f"  4. Execute: python3 scripts/run_sprint.py '<próximo sprint>'")
        return

    # ── Escalonamento para o usuário ─────────────────────────────────────────
    header("🚨  ESCALONAMENTO — INTERVENÇÃO HUMANA NECESSÁRIA")
    error("Sprint reprovado após rodada de correção.")
    error("O Generator deve ter incluído o motivo no output acima.")
    print()
    warn("Ações disponíveis:")
    warn("  1. Revise artifacts/sprint{N}_qa-report-r2.md para o comparativo")
    warn("  2. Edite o código em output/src/ manualmente e reexecute o Evaluator:")
    warn(f"     python3 scripts/run_evaluator_only.py {sprint_n}")
    warn("  3. Revise o contrato (renegociação requer atualizar o store):")
    warn(f"     python3 scripts/run_sprint.py '<prompt ajustado>'")
    warn("  4. Consulte o Generator para diagnóstico:")
    warn(f"     python3 scripts/run_generator_debug.py {sprint_n}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 scripts/run_sprint.py '<prompt do sprint>'")
        print()
        print("Exemplos:")
        print("  python3 scripts/run_sprint.py 'Sprint 0 — Catálogo: crawler EFOS + enriquecimento Haiku'")
        print("  python3 scripts/run_sprint.py 'Sprint 1 — Infraestrutura: webhook WhatsApp + Identity Router'")
        sys.exit(1)

    sprint_prompt = " ".join(sys.argv[1:])
    run_sprint(sprint_prompt)
