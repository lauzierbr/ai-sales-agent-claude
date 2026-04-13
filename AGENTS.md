# AI Sales Agent — Mapa do Repositório

Agente de vendas B2B via WhatsApp para pequenas distribuidoras e fabricantes.
Multi-tenant. Cliente piloto: JMB Distribuidora (Vinhedo-SP).

> Este arquivo é o ponto de entrada. Leia-o primeiro, depois navegue
> para os documentos referenciados conforme necessário.

## Onde encontrar o quê

| O que você precisa | Onde encontrar |
|--------------------|----------------|
| Visão geral do produto e negócio | `docs/PRODUCT_SENSE.md` |
| Arquitetura técnica e camadas | `ARCHITECTURE.md` |
| Stack, ambientes, secrets | `docs/DESIGN.md` |
| Segurança e isolamento de tenant | `docs/SECURITY.md` |
| Observabilidade (logs, métricas, traces) | `docs/RELIABILITY.md` |
| Frontend / painel do gestor | `docs/FRONTEND.md` |
| Decisões arquiteturais (log) | `docs/design-docs/index.md` |
| Planos de execução ativos | `docs/exec-plans/active/` |
| Planos completados | `docs/exec-plans/completed/` |
| Tech debt tracker | `docs/exec-plans/tech-debt-tracker.md` |
| Specs de produto por feature | `docs/product-specs/index.md` |
| Referências de libs (formato llms.txt) | `docs/references/` |
| Qualidade por domínio | `docs/QUALITY_SCORE.md` |
| Como usar o harness | `docs/design-docs/harness.md` |
| Roadmap de sprints | `docs/PLANS.md` |

## Regras inegociáveis (enforçadas mecanicamente)

1. **Secrets via Infisical** — nunca hardcoded, nunca em .env commitado
2. **Arquitetura em camadas** — `Types → Config → Repo → Service → Runtime → UI`
   dependências só fluem para frente; linter bloqueia violações
3. **Isolamento de tenant** — toda query filtra por `tenant_id`; vazamento é bloqueante
4. **Logging estruturado** — `structlog` sempre, nunca `print()`
5. **Testes por sprint** — sem aprovação do Evaluator sem cobertura dos critérios de Alta

## Como trabalhar neste repositório

- Leia `AGENTS.md` (este arquivo) primeiro
- Navegue para o documento relevante à sua tarefa
- Consulte `docs/exec-plans/active/` para o plano do sprint em execução
- Ao terminar um sprint, atualize `docs/exec-plans/` e `docs/QUALITY_SCORE.md`
- Nunca edite código manualmente — use o harness (ver `docs/design-docs/harness.md`)

## Estrutura de arquivos raiz

```
ai-sales-agent/
├── AGENTS.md           ← você está aqui
├── ARCHITECTURE.md     ← mapa de domínios e camadas
├── docs/               ← system of record
├── prompts/            ← system prompts do harness
├── artifacts/          ← outputs do harness (gerados, não editados)
├── output/             ← código gerado pelo Generator
└── scripts/            ← setup, deploy, health-check
```
