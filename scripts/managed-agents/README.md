# scripts/managed-agents — Harness via Anthropic Managed Agents API

Scripts para execução do harness Planner/Generator/Evaluator via
Anthropic Managed Agents API (beta).

## Status atual

**Aguardando acesso ao Research Preview** — Memory Stores (`client.beta.memory_stores`)
requer acesso especial além do beta padrão.

Formulário: https://claude.com/form/claude-managed-agents

## Quando usar

Use estes scripts quando tiver acesso ao Research Preview e quiser
executar o harness de forma autônoma via API, sem interação manual.

Enquanto isso, use o **Claude Code** conforme descrito em `CLAUDE.md`.

## Scripts

| Script | Função |
|--------|--------|
| `init_memory_stores.py` | Cria e popula os Memory Stores com docs do projeto |
| `init_agents.py` | Cria os 3 Agents e o Environment via API |
| `run_sprint.py` | Orquestra sessões Planner → Generator → Evaluator |

## Pré-requisitos

```bash
source .venv/bin/activate
pip install anthropic

infisical secrets set ANTHROPIC_API_KEY=sk-ant-... --env=dev
```

## Sequência de uso (quando disponível)

```bash
# 1. Memory Stores (requer Research Preview)
infisical run --env=dev -- python3 scripts/managed-agents/init_memory_stores.py --init

# 2. Agents e Environment
infisical run --env=dev -- python3 scripts/managed-agents/init_agents.py --init

# 3. Verificar
infisical run --env=dev -- python3 scripts/managed-agents/init_agents.py --status

# 4. Rodar um sprint
infisical run --env=dev -- python3 scripts/managed-agents/run_sprint.py \
  "Sprint 0 — Catálogo: crawler EFOS + enriquecimento Haiku"
```
