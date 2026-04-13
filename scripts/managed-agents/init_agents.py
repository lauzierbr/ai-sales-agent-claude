#!/usr/bin/env python3
"""
init_agents.py — Cria os 3 Agents e o Environment do harness via Managed Agents API

Uso (primeira vez):
    python3 scripts/init_agents.py --init

Atualizar um agent após mudança no system prompt:
    python3 scripts/init_agents.py --update planner
    python3 scripts/init_agents.py --update generator
    python3 scripts/init_agents.py --update evaluator
    python3 scripts/init_agents.py --update all

Ver estado atual dos recursos criados:
    python3 scripts/init_agents.py --status

Pré-requisitos:
    export ANTHROPIC_API_KEY=...
    pip install anthropic>=0.52.0

Após rodar --init, adicione os IDs ao Infisical (environment: development):
    HARNESS_AGENT_PLANNER_ID=agent_...
    HARNESS_AGENT_GENERATOR_ID=agent_...
    HARNESS_AGENT_EVALUATOR_ID=agent_...
    HARNESS_ENVIRONMENT_ID=env_...
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

BETA_HEADER = "managed-agents-2026-04-01"
IDS_FILE = Path(__file__).parent.parent / ".harness-ids.json"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Modelos — conforme docs/DESIGN.md e decisão de arquitetura
MODEL_PLANNER   = "claude-opus-4-6"    # síntese de spec — passo mais crítico
MODEL_GENERATOR = "claude-sonnet-4-6"  # volume de código — custo-benefício
MODEL_EVALUATOR = "claude-sonnet-4-6"  # verificação — não precisa de Opus

# ─────────────────────────────────────────────────────────────────────────────
# Terminal
# ─────────────────────────────────────────────────────────────────────────────

BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
RESET  = "\033[0m"

def ok(t):    print(f"  {GREEN}✓{RESET} {t}")
def warn(t):  print(f"  {YELLOW}⚠{RESET}  {t}")
def err(t):   print(f"  {RED}✗{RESET} {t}")
def info(t):  print(f"  {t}")
def head(t):  print(f"\n{BOLD}{CYAN}  {t}{RESET}")
def rule():   print(f"\n{BOLD}{CYAN}  {'─' * 56}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Persistência de IDs
# ─────────────────────────────────────────────────────────────────────────────

def load_ids() -> dict:
    if IDS_FILE.exists():
        return json.loads(IDS_FILE.read_text())
    return {}


def save_ids(data: dict) -> None:
    # Mescla com o que já existe (init_memory_stores pode ter gravado stores)
    existing = load_ids()
    existing.update(data)
    IDS_FILE.write_text(json.dumps(existing, indent=2))


def get_id(key: str) -> str | None:
    """Lê ID do .harness-ids.json ou de variável de ambiente."""
    env_map = {
        "agents.planner":   "HARNESS_AGENT_PLANNER_ID",
        "agents.generator": "HARNESS_AGENT_GENERATOR_ID",
        "agents.evaluator": "HARNESS_AGENT_EVALUATOR_ID",
        "environment":      "HARNESS_ENVIRONMENT_ID",
    }
    env_key = env_map.get(key)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val

    # Tentar no arquivo
    data = load_ids()
    parts = key.split(".")
    node = data
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node if isinstance(node, str) else None


# ─────────────────────────────────────────────────────────────────────────────
# Leitura dos system prompts
# ─────────────────────────────────────────────────────────────────────────────

def read_prompt(name: str) -> str:
    """Lê o system prompt de prompts/<name>.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        err(f"Prompt não encontrado: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Definições dos Agents
# ─────────────────────────────────────────────────────────────────────────────

def agent_definition(name: str) -> dict:
    """
    Retorna o payload completo para criar/atualizar um agent.
    O system prompt é lido diretamente de prompts/<name>.md —
    a fonte de verdade é o arquivo, não este script.
    """
    system = read_prompt(name)

    base = {
        "system": system,
        "tools": [],
    }

    if name == "planner":
        return {
            **base,
            "name": "Planner — ai-sales-agent",
            "model": MODEL_PLANNER,
            "description": (
                "Expande prompt de sprint em spec completo. "
                "Lê ADRs e documentação do projeto, identifica ambiguidades, "
                "gera artifacts/spec.md e exec-plan."
            ),
            # Planner só precisa ler e escrever arquivos — sem bash, sem web
            "tools": [
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {
                        "permission_policy": {"type": "always_allow"},
                        "enabled": False,               # começa tudo desabilitado
                    },
                    "configs": [
                        {"name": "read",  "enabled": True},
                        {"name": "write", "enabled": True},
                        {"name": "edit",  "enabled": True},
                        {"name": "glob",  "enabled": True},
                        {"name": "grep",  "enabled": True},
                        # bash desabilitado — Planner não executa código
                        # web_fetch desabilitado — sem acesso à internet
                        # web_search desabilitado
                    ],
                }
            ],
        }

    elif name == "generator":
        return {
            **base,
            "name": "Generator — ai-sales-agent",
            "model": MODEL_GENERATOR,
            "description": (
                "Implementa código por sprint. Negocia sprint contract com o Evaluator, "
                "escreve código em output/src/, roda pytest e import-linter, "
                "faz auto-avaliação antes de submeter ao Evaluator."
            ),
            # Generator precisa de tudo: bash para testes, web_fetch para docs
            "tools": [
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {
                        "permission_policy": {"type": "always_allow"},
                    },
                    # Todos os tools habilitados por padrão para o Generator
                    # bash: pytest, lint-imports, grep de secrets
                    # read/write/edit: código em output/src/
                    # glob/grep: navegação no repositório
                    # web_fetch: consultar docs de libs quando necessário
                    # web_search: pesquisar quando web_fetch não for suficiente
                }
            ],
        }

    elif name == "evaluator":
        return {
            **base,
            "name": "Evaluator — ai-sales-agent",
            "model": MODEL_EVALUATOR,
            "description": (
                "QA do harness. Negocia contratos rigorosos, executa testes automatizados, "
                "verifica segurança e arquitetura. Aprova ou reprova com evidência específica. "
                "Nunca edita código."
            ),
            "tools": [
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {
                        "permission_policy": {"type": "always_allow"},
                        "enabled": True,
                    },
                    "configs": [
                        # Evaluator NUNCA escreve em output/ — só lê e executa
                        {"name": "write", "enabled": False},
                        {"name": "edit",  "enabled": False},
                        # bash habilitado: pytest, grep, lint-imports
                        # read habilitado: leitura de código e artefatos
                        # glob/grep habilitados: navegação e verificações
                        # web_fetch/web_search desabilitados: sem necessidade
                        {"name": "web_fetch",  "enabled": False},
                        {"name": "web_search", "enabled": False},
                    ],
                }
            ],
        }

    else:
        err(f"Agent desconhecido: {name}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Definição do Environment
# ─────────────────────────────────────────────────────────────────────────────

ENVIRONMENT_DEFINITION = {
    "name": "ai-sales-agent-harness",
    "config": {
        "type": "cloud",
        # Pacotes pré-instalados no container
        # Mantém em sincronia com pyproject.toml
        "packages": {
            "pip": [
                # Core
                "anthropic",
                "fastapi",
                "httpx",
                "pydantic>=2.0",
                "pydantic-settings",
                # Banco de dados
                "sqlalchemy[asyncio]>=2.0",
                "asyncpg",
                # Testes
                "pytest",
                "pytest-asyncio",
                "pytest-cov",
                "pytest-mock",
                # Arquitetura
                "import-linter",
                # Observabilidade
                "structlog",
                "opentelemetry-sdk",
                "opentelemetry-instrumentation-fastapi",
                # Qualidade de código
                "mypy",
                "ruff",
            ],
            "apt": [
                "postgresql-client",   # psql para debug de queries
            ],
        },
        # Networking limitado por princípio de least privilege
        # Generator precisa de PyPI para instalar deps; API Anthropic para testes de agente
        "networking": {
            "type": "limited",
            "allowed_hosts": [
                "https://api.anthropic.com",
            ],
            # Permite pip install durante setup do container
            "allow_package_managers": True,
            # MCP servers não usados no harness de desenvolvimento
            "allow_mcp_servers": False,
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Cliente
# ─────────────────────────────────────────────────────────────────────────────

def make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        err("ANTHROPIC_API_KEY não configurada")
        sys.exit(1)
    return anthropic.Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": BETA_HEADER},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Operações
# ─────────────────────────────────────────────────────────────────────────────

def create_agent(client: anthropic.Anthropic, name: str) -> tuple[str, int]:
    """Cria um agent. Retorna (id, version)."""
    defn = agent_definition(name)
    agent = client.beta.agents.create(**defn)
    return agent.id, agent.version


def update_agent(
    client: anthropic.Anthropic,
    agent_id: str,
    current_version: int,
    name: str,
) -> int:
    """
    Atualiza o system prompt de um agent existente.
    Retorna a nova versão.
    """
    new_system = read_prompt(name)
    updated = client.beta.agents.update(
        agent_id,
        version=current_version,
        system=new_system,
    )
    return updated.version


def get_agent_current_version(client: anthropic.Anthropic, agent_id: str) -> int:
    """Busca a versão atual de um agent."""
    agent = client.beta.agents.retrieve(agent_id)
    return agent.version


def create_environment(client: anthropic.Anthropic) -> str:
    """Cria o Environment. Retorna o id."""
    env = client.beta.environments.create(**ENVIRONMENT_DEFINITION)
    return env.id


# ─────────────────────────────────────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────────────────────────────────────

def cmd_init(client: anthropic.Anthropic) -> None:
    """Cria os 3 agents e o environment. Idempotente: detecta se já existem."""

    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  INIT — Criando Agents e Environment do harness{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    ids: dict = {"agents": {}, "agents_versions": {}}

    # ── Agents ────────────────────────────────────────────────────────────────
    for agent_name, model in [
        ("planner",   MODEL_PLANNER),
        ("generator", MODEL_GENERATOR),
        ("evaluator", MODEL_EVALUATOR),
    ]:
        head(f"Agent: {agent_name}  ({model})")

        # Verificar se já existe
        existing_id = get_id(f"agents.{agent_name}")
        if existing_id:
            warn(f"Já existe: {existing_id}")
            warn("Use --update para atualizar o system prompt.")
            ids["agents"][agent_name] = existing_id
            try:
                v = get_agent_current_version(client, existing_id)
                ids["agents_versions"][agent_name] = v
                info(f"Versão atual: {v}")
            except Exception:
                pass
            continue

        agent_id, version = create_agent(client, agent_name)
        ids["agents"][agent_name] = agent_id
        ids["agents_versions"][agent_name] = version
        ok(f"Criado: {agent_id}  (versão {version})")

        # Mostrar resumo de tools configurados
        defn = agent_definition(agent_name)
        tool_cfg = defn.get("tools", [{}])[0]
        configs = tool_cfg.get("configs", [])
        disabled = [c["name"] for c in configs if not c.get("enabled", True)]
        enabled_extra = [c["name"] for c in configs if c.get("enabled", False)
                         and tool_cfg.get("default_config", {}).get("enabled") is False]
        if disabled:
            info(f"Tools desabilitados: {', '.join(disabled)}")
        if enabled_extra:
            info(f"Tools habilitados (whitelist): {', '.join(enabled_extra)}")

    # ── Environment ───────────────────────────────────────────────────────────
    head("Environment: ai-sales-agent-harness")

    existing_env = get_id("environment")
    if existing_env:
        warn(f"Já existe: {existing_env}")
        warn("Environments não são versionados — para atualizar, arquive e recrie.")
        ids["environment"] = existing_env
    else:
        packages = ENVIRONMENT_DEFINITION["config"].get("packages", {})
        pip_count = len(packages.get("pip", []))
        apt_count = len(packages.get("apt", []))
        info(f"Pacotes pip: {pip_count}  |  apt: {apt_count}")
        info("Networking: limited (PyPI + api.anthropic.com)")

        env_id = create_environment(client)
        ids["environment"] = env_id
        ok(f"Criado: {env_id}")

    # ── Persistir IDs ─────────────────────────────────────────────────────────
    save_ids(ids)

    # ── Output final ──────────────────────────────────────────────────────────
    rule()
    print(f"\n{BOLD}{CYAN}  RECURSOS CRIADOS — adicione ao Infisical{RESET}\n")
    print(f"  {BOLD}environment: development{RESET}\n")

    agent_env_map = {
        "planner":   "HARNESS_AGENT_PLANNER_ID",
        "generator": "HARNESS_AGENT_GENERATOR_ID",
        "evaluator": "HARNESS_AGENT_EVALUATOR_ID",
    }
    for name, env_var in agent_env_map.items():
        aid = ids["agents"].get(name, "—")
        ver = ids.get("agents_versions", {}).get(name, "?")
        print(f"  {env_var}={aid}  # v{ver}")

    print(f"  HARNESS_ENVIRONMENT_ID={ids.get('environment', '—')}")

    stores = load_ids().get("stores", {})
    if stores.get("project_knowledge"):
        print(f"  HARNESS_STORE_PROJECT_KNOWLEDGE_ID={stores['project_knowledge']}")
    else:
        warn("Stores ainda não criados. Execute:")
        info("  python3 scripts/init_memory_stores.py --init")

    if stores.get("agent_prompts"):
        print(f"  HARNESS_STORE_AGENT_PROMPTS_ID={stores['agent_prompts']}")

    print(f"\n  IDs persistidos em: .harness-ids.json")
    print(f"  (certifique-se que .harness-ids.json está no .gitignore)\n")


def cmd_update(client: anthropic.Anthropic, target: str) -> None:
    """
    Atualiza o system prompt de um ou todos os agents.
    Lê o prompt atual de prompts/<name>.md e cria uma nova versão.
    """
    targets = ["planner", "generator", "evaluator"] if target == "all" else [target]

    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  UPDATE — Atualizando system prompts{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    ids = load_ids()
    new_versions: dict = {}

    for name in targets:
        head(f"Atualizando: {name}")

        agent_id = get_id(f"agents.{name}")
        if not agent_id:
            err(f"ID do agent '{name}' não encontrado.")
            err("Execute --init primeiro.")
            continue

        try:
            current_version = get_agent_current_version(client, agent_id)
            info(f"Versão atual: {current_version}")

            new_version = update_agent(client, agent_id, current_version, name)
            new_versions[name] = new_version
            ok(f"Atualizado: {agent_id}  v{current_version} → v{new_version}")

        except anthropic.APIError as e:
            # No-op detection: se o prompt não mudou, a API retorna a mesma versão
            if "no change" in str(e).lower() or "no-op" in str(e).lower():
                warn(f"Sem mudança detectada — versão mantida")
            else:
                err(f"Erro ao atualizar {name}: {e}")

    # Persistir novas versões
    if new_versions:
        existing = load_ids()
        if "agents_versions" not in existing:
            existing["agents_versions"] = {}
        existing["agents_versions"].update(new_versions)
        IDS_FILE.write_text(json.dumps(existing, indent=2))
        ok("Versões atualizadas em .harness-ids.json")

    print()
    warn("Lembre-se: sessions existentes usam a versão do agent no momento")
    warn("da criação. Novas sessions usarão a versão mais recente automaticamente.")


def cmd_status(client: anthropic.Anthropic) -> None:
    """Exibe o estado atual de todos os recursos do harness."""

    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  STATUS — Recursos do harness{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    all_ok = True

    # ── Agents ────────────────────────────────────────────────────────────────
    head("Agents")
    for name, model in [
        ("planner",   MODEL_PLANNER),
        ("generator", MODEL_GENERATOR),
        ("evaluator", MODEL_EVALUATOR),
    ]:
        agent_id = get_id(f"agents.{name}")
        if not agent_id:
            err(f"{name:<12} — ID não encontrado (execute --init)")
            all_ok = False
            continue

        try:
            agent = client.beta.agents.retrieve(agent_id)
            archived = agent.archived_at is not None
            status = f"{RED}ARQUIVADO{RESET}" if archived else f"{GREEN}ativo{RESET}"
            prompt_size = len(agent.system or "") if agent.system else 0
            print(
                f"  {GREEN if not archived else RED}{'✓' if not archived else '!'}{RESET}"
                f"  {name:<12} {agent_id}  "
                f"v{agent.version}  {model}  "
                f"[{status}]  prompt: {prompt_size} chars"
            )
        except anthropic.NotFoundError:
            err(f"{name:<12} {agent_id} — NOT FOUND (foi deletado?)")
            all_ok = False
        except anthropic.APIError as e:
            err(f"{name:<12} {agent_id} — erro: {e}")
            all_ok = False

    # ── Environment ───────────────────────────────────────────────────────────
    head("Environment")
    env_id = get_id("environment")
    if not env_id:
        err("ID não encontrado (execute --init)")
        all_ok = False
    else:
        try:
            env = client.beta.environments.retrieve(env_id)
            archived = env.archived_at is not None
            status = f"{RED}ARQUIVADO{RESET}" if archived else f"{GREEN}ativo{RESET}"
            print(
                f"  {GREEN if not archived else RED}{'✓' if not archived else '!'}{RESET}"
                f"  {env_id}  [{status}]  {env.name}"
            )
        except anthropic.NotFoundError:
            err(f"{env_id} — NOT FOUND")
            all_ok = False
        except anthropic.APIError as e:
            err(f"{env_id} — erro: {e}")
            all_ok = False

    # ── Memory Stores ──────────────────────────────────────────────────────────
    head("Memory Stores")
    stores = {
        "project_knowledge": "HARNESS_STORE_PROJECT_KNOWLEDGE_ID",
        "agent_prompts":     "HARNESS_STORE_AGENT_PROMPTS_ID",
    }
    for store_key, env_var in stores.items():
        store_id = (
            os.environ.get(env_var)
            or load_ids().get("stores", {}).get(store_key)
        )
        if not store_id:
            warn(f"{store_key:<22} — ID não encontrado")
            warn(f"  Execute: python3 scripts/init_memory_stores.py --init")
            continue

        try:
            store = client.beta.memory_stores.retrieve(store_id)
            archived = store.archived_at is not None
            status = f"{RED}ARQUIVADO{RESET}" if archived else f"{GREEN}ativo{RESET}"
            print(
                f"  {GREEN if not archived else RED}{'✓' if not archived else '!'}{RESET}"
                f"  {store_key:<22} {store_id}  [{status}]"
            )
        except anthropic.NotFoundError:
            err(f"{store_key:<22} {store_id} — NOT FOUND")
            all_ok = False
        except anthropic.APIError as e:
            err(f"{store_key:<22} {store_id} — erro: {e}")

    # ── Resumo ─────────────────────────────────────────────────────────────────
    rule()
    if all_ok:
        print(f"\n  {GREEN}{BOLD}Todos os recursos estão prontos.{RESET}")
        print(f"\n  Para iniciar um sprint:")
        print(f"    infisical run --env=dev -- \\")
        print(f"      python3 scripts/run_sprint.py '<prompt do sprint>'\n")
    else:
        print(f"\n  {YELLOW}{BOLD}Alguns recursos precisam de atenção (ver acima).{RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gerencia os Agents e Environment do harness ai-sales-agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Primeira vez
  python3 scripts/init_agents.py --init

  # Após editar prompts/generator.md
  python3 scripts/init_agents.py --update generator

  # Após editar todos os prompts
  python3 scripts/init_agents.py --update all

  # Verificar estado
  python3 scripts/init_agents.py --status
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--init",
        action="store_true",
        help="Cria agents e environment (idempotente)",
    )
    group.add_argument(
        "--update",
        metavar="AGENT",
        choices=["planner", "generator", "evaluator", "all"],
        help="Atualiza system prompt: planner | generator | evaluator | all",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Exibe estado atual de todos os recursos",
    )

    args = parser.parse_args()
    client = make_client()

    if args.init:
        cmd_init(client)
    elif args.update:
        cmd_update(client, args.update)
    elif args.status:
        cmd_status(client)
