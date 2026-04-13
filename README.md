# AI Sales Agent

Agente de vendas B2B via WhatsApp para pequenas distribuidoras brasileiras.
Multi-tenant. Cliente piloto: JMB Distribuidora (Vinhedo-SP).

## Comece aqui

```bash
cd ai-sales-agent
claude
```

O Claude Code lê `CLAUDE.md` automaticamente. Esse arquivo contém
tudo que o agente precisa para operar.

## Setup (macOS)

```bash
# Pré-requisitos
brew install infisical/get-cli/infisical
npm install -g @anthropic-ai/claude-code

# Clonar e entrar no projeto
git clone https://github.com/SEU_USUARIO/ai-sales-agent.git
cd ai-sales-agent

# Infisical
infisical login
infisical init
infisical secrets set ANTHROPIC_API_KEY=sk-ant-... --env=dev

# Infraestrutura local (Sprint Infra-Dev)
# Executar via Claude Code:
# "Leia CLAUDE.md. Execute o Sprint Infra-Dev."
```

## Harness — Planner / Generator / Evaluator

O desenvolvimento usa um harness de três agentes acionados via Claude Code.
Ver `docs/design-docs/harness.md` para o fluxo completo e os comandos.

Exemplo de uso:
```
# No Claude Code:
"Leia CLAUDE.md e prompts/planner.md. Você é o Planner.
Execute o planejamento do Sprint 0 — Catálogo: crawler EFOS + enriquecimento Haiku."
```

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| `CLAUDE.md` | Ponto de entrada para o Claude Code |
| `AGENTS.md` | Mapa completo do repositório |
| `ARCHITECTURE.md` | Camadas, domínios, regras de dependência |
| `docs/PRODUCT_SENSE.md` | Produto, personas, modelo de negócio |
| `docs/DESIGN.md` | Stack, ambientes, secrets, crawler |
| `docs/PLANS.md` | Roadmap de sprints |
| `docs/RELIABILITY.md` | Observabilidade: VictoriaMetrics, OTel |
| `docs/SECURITY.md` | Isolamento tenant, secrets, validação |
| `docs/QUALITY_SCORE.md` | Grade de qualidade por domínio |
| `docs/design-docs/harness.md` | Como usar o harness |
| `docs/design-docs/index.md` | Log de decisões (ADRs) |
| `prompts/planner.md` | System prompt do Planner |
| `prompts/generator.md` | System prompt do Generator |
| `prompts/evaluator.md` | System prompt do Evaluator |

## Estrutura

```
ai-sales-agent/
├── CLAUDE.md           ← ponto de entrada (Claude Code lê automaticamente)
├── AGENTS.md           ← mapa do repositório
├── ARCHITECTURE.md     ← camadas e domínios
├── prompts/            ← system prompts do harness
├── artifacts/          ← outputs do harness (gerados, não editar)
├── output/             ← código gerado pelo Generator
├── docs/               ← system of record
├── infra/              ← docker-compose, grafana, init-db
└── scripts/
    ├── setup.sh
    ├── deploy.sh
    ├── health-check.sh
    └── managed-agents/ ← scripts para Managed Agents API (futuro)
```

## Notas

- `.venv/` e `.harness-ids.json` estão no `.gitignore`
- Nunca commitar `.env` com valores reais — sempre via Infisical
- Nunca editar código em `output/` manualmente — use o harness
