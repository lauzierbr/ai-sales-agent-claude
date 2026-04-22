# AI Sales Agent — Claude Code

Agente de vendas B2B via WhatsApp para pequenas distribuidoras brasileiras.
Multi-tenant. Cliente piloto: JMB Distribuidora (Vinhedo-SP).

## Leia primeiro

Antes de qualquer ação, leia nesta ordem:
1. `AGENTS.md` — mapa completo do repositório
2. `ARCHITECTURE.md` — camadas fixas e regras de dependência
3. `docs/PLANS.md` — roadmap e status dos sprints
4. `docs/design-docs/index.md` — decisões arquiteturais (ADRs)
5. `docs/exec-plans/active/` — planos do sprint em execução

## Como usar o harness neste repositório

Este projeto usa um harness de três agentes: **Planner**, **Generator** e
**Evaluator**. Você aciona cada um com um comando específico abaixo.
Os system prompts completos estão em `prompts/`.

### Acionar o Planner
```
Leia CLAUDE.md e prompts/planner.md. Você é o Planner.
Execute o planejamento do sprint: [descreva o sprint em 1-4 frases]
```

### Acionar o Generator
```
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O spec está em artifacts/spec.md. Comece pela Fase 1: proponha o sprint contract.
```

### Acionar o Evaluator
```
Leia CLAUDE.md e prompts/evaluator.md. Você é o Evaluator.
O contrato está em artifacts/sprint_contract.md. Execute a avaliação completa.
```

## Fluxo completo de um sprint

```
1. Você: aciona o Planner com o prompt do sprint
2. Planner: gera artifacts/spec.md e docs/exec-plans/active/sprint-N.md
3. Você: revisa o spec → [Enter para aprovar ou ajuste o prompt]
4. Você: aciona o Generator
5. Generator: propõe artifacts/sprint_contract.md (Fase 1)
6. Você: aciona o Evaluator para revisar o contrato
7. Evaluator: ACEITO ou objeções → negocia até acordo
8. Você: aciona o Generator novamente para implementar (Fase 2)
9. Generator: implementa output/src/, roda auto-avaliação
10. Você: aciona o Evaluator para avaliar o código
11. Evaluator: APROVADO → artifacts/qa_sprint_N.md
             REPROVADO → Generator tem 1 rodada de correção
             2x REPROVADO → escalonamento para você
12. Generator: prepara ambiente de homologação
    - Executa deploy.sh staging
    - Aplica seed de dados reais (scripts/seed_homologacao_sprint-N.py)
    - Entrega checklist em docs/exec-plans/active/homologacao_sprint-N.md
13. Você: executa homologação manual no staging (WhatsApp real)
    - Segue checklist de cenários do arquivo acima
    - Registra resultado: APROVADO ou lista de bugs
14. Se APROVADO: sprint encerrado, move plano para completed/
    Se REPROVADO: bugs viram hotfixes antes do próximo sprint
```

> **Regra:** Nenhum sprint avança para o seguinte sem APROVADO na homologação.
> Protocolo completo em `docs/HOMOLOGACAO.md`.

## Regras inegociáveis (nunca ignore)

1. **Secrets via Infisical** — nunca hardcoded, nunca em .env commitado
2. **Camadas fixas** — Types → Config → Repo → Service → Runtime → UI
   import-linter bloqueia violações mecanicamente
3. **Isolamento de tenant** — toda query filtra por tenant_id
4. **Zero print()** — structlog sempre
5. **Testes unitários** — pytest -m unit antes de qualquer aprovação
6. **Nunca edite código manualmente** — corrija o prompt ou o contrato
7. **Sem worktrees** — o Generator trabalha diretamente no repo principal
   (`/Users/lauzier/MyRepos/ai-sales-agent-claude`). Nunca use
   `isolation: "worktree"` ao acionar subagentes. Worktrees ficam obsoletos
   rapidamente e criam confusão de CWD sem benefício (o Evaluator já é o
   mecanismo de revisão antes de qualquer merge).

## Estrutura de arquivos

```
ai-sales-agent/
├── CLAUDE.md           ← você está aqui (lido pelo Claude Code)
├── AGENTS.md           ← mapa completo do repositório
├── ARCHITECTURE.md     ← camadas e domínios
├── prompts/            ← system prompts dos 3 agentes
│   ├── planner.md
│   ├── generator.md
│   └── evaluator.md
├── artifacts/          ← outputs do harness (gerados, não editar)
│   ├── spec.md
│   ├── sprint_contract.md
│   └── qa_sprint_N.md
├── output/             ← código gerado pelo Generator
│   └── src/
├── docs/               ← system of record do projeto
└── scripts/            ← utilitários (setup, deploy, health-check)
```

## Cliente piloto — JMB Distribuidora

- Site B2B (EFOS): https://pedido.jmbdistribuidora.com.br
- Site B2C (Loja Integrada): https://www.jmbdistribuidora.com.br
- Endereço: Av. Independência, 4676, Santa Rosa, 13289-152, Vinhedo-SP
- Horário: Seg-Sex 08:00-17:00 | Pedido mínimo B2B: R$ 300,00
