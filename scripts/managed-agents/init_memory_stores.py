#!/usr/bin/env python3
"""
init_memory_stores.py — Cria e popula os Memory Stores do harness

Uso (primeira vez):
    python3 scripts/init_memory_stores.py --init

Uso (sincronizar após mudanças no repo):
    python3 scripts/init_memory_stores.py --sync

Pré-requisitos:
    export ANTHROPIC_API_KEY=...

    pip install anthropic>=0.52.0

Após rodar --init, copie os IDs exibidos para o Infisical:
    HARNESS_STORE_PROJECT_KNOWLEDGE_ID=store_...
    HARNESS_STORE_AGENT_PROMPTS_ID=store_...
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import anthropic

BETA_HEADER = "managed-agents-2026-04-01"

# Mapeamento: (path_no_repo, path_no_store)
# Baseado em docs/design-docs/memory-stores.md (D015)
PROJECT_KNOWLEDGE_DOCS = [
    ("AGENTS.md",                              "/map.md"),
    ("ARCHITECTURE.md",                        "/architecture.md"),
    ("docs/PRODUCT_SENSE.md",                  "/product.md"),
    ("docs/DESIGN.md",                         "/design.md"),
    ("docs/SECURITY.md",                       "/security.md"),
    ("docs/RELIABILITY.md",                    "/reliability.md"),
    ("docs/FRONTEND.md",                       "/frontend.md"),
    ("docs/design-docs/index.md",              "/adrs/index.md"),
    ("docs/design-docs/harness.md",            "/harness.md"),
    ("docs/design-docs/memory-stores.md",      "/adrs/D015.md"),
    ("docs/PLANS.md",                          "/plans.md"),
    ("pyproject.toml",                         "/pyproject.toml"),
    ("output/.env.example",                    "/env-example.md"),
]

AGENT_PROMPTS_DOCS = [
    ("prompts/planner.md",   "/planner.md"),
    ("prompts/generator.md", "/generator.md"),
    ("prompts/evaluator.md", "/evaluator.md"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN  = "\033[36m"
RESET = "\033[0m"

def ok(text):   print(f"  {GREEN}✓{RESET} {text}")
def warn(text): print(f"  {YELLOW}⚠{RESET}  {text}")
def info(text): print(f"  {text}")
def head(text): print(f"\n{BOLD}{CYAN}  {text}{RESET}")


def file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def read_repo_file(path: str) -> str | None:
    """Lê arquivo do repositório relativo à raiz do projeto."""
    root = Path(__file__).parent.parent
    full = root / path
    if not full.exists():
        warn(f"Arquivo não encontrado: {path} — pulando")
        return None
    return full.read_text(encoding="utf-8")


def make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Erro: ANTHROPIC_API_KEY não configurada")
        sys.exit(1)
    return anthropic.Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": BETA_HEADER},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Operações nos stores
# ─────────────────────────────────────────────────────────────────────────────

def upsert_memory(
    client: anthropic.Anthropic,
    store_id: str,
    store_path: str,
    content: str,
    dry_run: bool = False,
) -> str:
    """
    Escreve ou atualiza um documento no store.
    Retorna 'created', 'updated' ou 'skipped'.
    """
    # Verificar se já existe
    existing_content = None
    existing_id = None
    existing_sha = None

    try:
        memories = client.beta.memory_stores.memories.list(
            store_id, path_prefix=store_path
        )
        for mem in memories.data:
            if mem.path == store_path:
                existing_id = mem.id
                existing_sha = mem.content_sha256
                break
    except Exception:
        pass

    new_sha = file_sha256(content)

    # Se já existe e o conteúdo é idêntico, pular
    if existing_sha and existing_sha == new_sha:
        return "skipped"

    if dry_run:
        return "would-update" if existing_id else "would-create"

    if existing_id:
        # Atualizar com precondição de sha para evitar conflito
        client.beta.memory_stores.memories.update(
            store_id,
            existing_id,
            content=content,
            precondition={"type": "content_sha256", "content_sha256": existing_sha},
        )
        return "updated"
    else:
        # Criar novo
        client.beta.memory_stores.memories.write(
            store_id,
            path=store_path,
            content=content,
            precondition={"type": "not_exists"},
        )
        return "created"


def populate_store(
    client: anthropic.Anthropic,
    store_id: str,
    store_name: str,
    doc_map: list[tuple[str, str]],
    dry_run: bool = False,
) -> None:
    """Popula um store com o mapeamento de documentos fornecido."""
    head(f"Populando store: {store_name} ({store_id})")

    counts = {"created": 0, "updated": 0, "skipped": 0}

    for repo_path, store_path in doc_map:
        content = read_repo_file(repo_path)
        if content is None:
            continue

        result = upsert_memory(client, store_id, store_path, content, dry_run)
        counts[result if result in counts else "created"] += 1

        icon = {"created": "✓", "updated": "↻", "skipped": "—",
                "would-create": "?", "would-update": "?"}.get(result, "?")
        color = GREEN if result in ("created", "would-create") else (
                YELLOW if result in ("updated", "would-update") else RESET)
        print(f"    {color}{icon}{RESET}  {store_path}  [{result}]")

    print()
    ok(f"Criados: {counts['created']}  |  Atualizados: {counts['updated']}  |  Sem mudança: {counts['skipped']}")


# ─────────────────────────────────────────────────────────────────────────────
# Comandos principais
# ─────────────────────────────────────────────────────────────────────────────

def cmd_init(client: anthropic.Anthropic) -> None:
    """Cria os stores e popula pela primeira vez."""
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  INIT — Criando Memory Stores do harness{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}\n")

    # Criar store project-knowledge
    head("Criando store: project-knowledge")
    pk_store = client.beta.memory_stores.create(
        name="project-knowledge",
        description=(
            "Conhecimento permanente do projeto ai-sales-agent: arquitetura, "
            "ADRs aprovados, product sense, design, security, reliability, "
            "histórico de sprints concluídos. Read-only para todos os agents."
        ),
    )
    ok(f"Criado: {pk_store.id}")

    # Criar store agent-prompts
    head("Criando store: agent-prompts")
    ap_store = client.beta.memory_stores.create(
        name="agent-prompts",
        description=(
            "System prompts dos três agents do harness: Planner, Generator, Evaluator. "
            "Consultado pelos agents para entender o protocolo uns dos outros. "
            "Read-only para todos os agents."
        ),
    )
    ok(f"Criado: {ap_store.id}")

    # Criar também os agents via API (opcional — pode ser feito separado)
    print()
    head("Populando stores...")
    populate_store(client, pk_store.id, "project-knowledge", PROJECT_KNOWLEDGE_DOCS)
    populate_store(client, ap_store.id, "agent-prompts", AGENT_PROMPTS_DOCS)

    # Salvar IDs localmente
    ids_file = Path(__file__).parent.parent / ".harness-ids.json"
    data = {
        "stores": {
            "project_knowledge": pk_store.id,
            "agent_prompts": ap_store.id,
        },
        "note": "Copie estes IDs para o Infisical como variáveis de ambiente"
    }
    ids_file.write_text(json.dumps(data, indent=2))

    # Instruções finais
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  STORES CRIADOS COM SUCESSO{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}\n")

    print("  Adicione ao Infisical (environment: development):\n")
    print(f"    HARNESS_STORE_PROJECT_KNOWLEDGE_ID={pk_store.id}")
    print(f"    HARNESS_STORE_AGENT_PROMPTS_ID={ap_store.id}")
    print()
    print("  IDs também salvos em: .harness-ids.json")
    print("  (adicione .harness-ids.json ao .gitignore)\n")
    print("  Próximo passo: criar os 3 agents e o environment:")
    print("    python3 scripts/init_agents.py\n")


def cmd_sync(client: anthropic.Anthropic, dry_run: bool = False) -> None:
    """Sincroniza os stores com o estado atual do repositório."""
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {'DRY-RUN — ' if dry_run else ''}SYNC — Sincronizando Memory Stores{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}\n")

    # Ler IDs dos stores
    pk_id = os.environ.get("HARNESS_STORE_PROJECT_KNOWLEDGE_ID")
    ap_id = os.environ.get("HARNESS_STORE_AGENT_PROMPTS_ID")

    if not pk_id or not ap_id:
        # Tentar ler do arquivo local
        ids_file = Path(__file__).parent.parent / ".harness-ids.json"
        if ids_file.exists():
            data = json.loads(ids_file.read_text())
            pk_id = pk_id or data.get("stores", {}).get("project_knowledge")
            ap_id = ap_id or data.get("stores", {}).get("agent_prompts")

    if not pk_id or not ap_id:
        print("Erro: IDs dos stores não encontrados.")
        print("Execute primeiro: python3 scripts/init_memory_stores.py --init")
        sys.exit(1)

    populate_store(
        client, pk_id, "project-knowledge",
        PROJECT_KNOWLEDGE_DOCS, dry_run
    )
    populate_store(
        client, ap_id, "agent-prompts",
        AGENT_PROMPTS_DOCS, dry_run
    )

    if dry_run:
        print()
        warn("Dry-run: nenhuma alteração foi feita.")
        warn("Execute sem --dry-run para aplicar as mudanças.")
    else:
        print()
        ok("Sincronização concluída.")


def cmd_add_sprint_history(
    client: anthropic.Anthropic,
    sprint_n: str,
    summary_file: str,
) -> None:
    """Adiciona o resumo de um sprint concluído ao project-knowledge store."""
    pk_id = os.environ.get("HARNESS_STORE_PROJECT_KNOWLEDGE_ID")
    if not pk_id:
        print("Erro: HARNESS_STORE_PROJECT_KNOWLEDGE_ID não configurada")
        sys.exit(1)

    summary_path = Path(summary_file)
    if not summary_path.exists():
        print(f"Erro: arquivo não encontrado: {summary_file}")
        sys.exit(1)

    content = summary_path.read_text(encoding="utf-8")
    store_path = f"/sprint-history/sprint-{sprint_n}.md"

    result = upsert_memory(client, pk_id, store_path, content)
    ok(f"Sprint {sprint_n} adicionado ao project-knowledge: {store_path} [{result}]")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gerencia os Memory Stores do harness ai-sales-agent"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--init",
        action="store_true",
        help="Cria os stores e popula pela primeira vez",
    )
    group.add_argument(
        "--sync",
        action="store_true",
        help="Sincroniza os stores com o repositório atual",
    )
    group.add_argument(
        "--add-sprint-history",
        nargs=2,
        metavar=("SPRINT_N", "ARQUIVO"),
        help="Adiciona resumo de sprint concluído ao project-knowledge",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria feito sem fazer nada (só funciona com --sync)",
    )

    args = parser.parse_args()
    client = make_client()

    if args.init:
        cmd_init(client)
    elif args.sync:
        cmd_sync(client, dry_run=args.dry_run)
    elif args.add_sprint_history:
        sprint_n, summary_file = args.add_sprint_history
        cmd_add_sprint_history(client, sprint_n, summary_file)
