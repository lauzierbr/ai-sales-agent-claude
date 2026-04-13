# Harness — Como desenvolver neste repositório

## Filosofia

Inspirado nos artigos da Anthropic ("Harness design for long-running
application development") e da OpenAI ("Harness Engineering", fev/2026).

**Regra central:** nenhuma linha de código é escrita manualmente.
Quando algo falha, a pergunta não é "como corrijo o código?" mas
"o que está faltando no prompt, contrato ou documentação que levou
o agente a errar aqui?" A correção entra no sistema, não no código.

## Método atual — Claude Code

O harness roda via Claude Code no terminal. O Claude Code lê o
repositório inteiro via filesystem — CLAUDE.md, todos os docs,
os prompts — substituindo os Memory Stores de forma natural.

### Iniciar uma sessão

```bash
cd ai-sales-agent
claude
```

O Claude Code lê `CLAUDE.md` automaticamente ao iniciar.

### Comandos por agente

**Planner:**
```
Leia CLAUDE.md e prompts/planner.md. Você é o Planner.
Execute o planejamento do sprint: [prompt do sprint]
```

**Generator (Fase 1 — contrato):**
```
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O spec está em artifacts/spec.md. Comece pela Fase 1: proponha o sprint contract.
```

**Evaluator (revisar contrato):**
```
Leia CLAUDE.md e prompts/evaluator.md. Você é o Evaluator.
Revise o contrato em artifacts/sprint_contract.md e responda ACEITO ou com objeções.
```

**Generator (Fase 2 — implementação):**
```
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O contrato foi ACEITO. Execute a Fase 2: implemente o sprint conforme artifacts/sprint_contract.md.
```

**Evaluator (avaliar código):**
```
Leia CLAUDE.md e prompts/evaluator.md. Você é o Evaluator.
Execute a avaliação completa do sprint. Contrato em artifacts/sprint_contract.md.
```

## Fluxo por sprint

```
1. Você escreve um prompt de 1-4 frases descrevendo o sprint
2. Planner lê docs e ADRs → gera artifacts/spec.md
3. Você revisa o spec  ← checkpoint humano
4. Generator propõe artifacts/sprint_contract.md (Fase 1)
5. Evaluator revisa o contrato — negocia até ACEITO
6. Generator implementa output/src/ e roda auto-avaliação (Fase 2)
7. Evaluator testa contra o contrato
   PASS → artifacts/qa_sprint_N.md, atualiza QUALITY_SCORE.md
   FAIL → Generator tem 1 rodada de correção
   2x FAIL → escalonamento para você
8. Você avança para o próximo sprint
```

## Artifacts gerados

```
artifacts/
├── spec.md                   ← Planner
├── sprint_contract.md        ← Generator + Evaluator
├── qa_sprint_N.md            ← Evaluator (aprovação)
├── qa_sprint_N_r1.md         ← Evaluator (1ª reprovação)
├── qa_sprint_N_r2.md         ← Evaluator (2ª reprovação)
└── handoff_sprint_N.md       ← Generator (resumo para próximo sprint)
```

## Método futuro — Managed Agents API

Quando o acesso ao Research Preview de Memory Stores estiver disponível,
o harness pode ser executado de forma autônoma via API Python, sem
interação manual entre os agentes.

Ver `scripts/managed-agents/` e `docs/design-docs/memory-stores.md` (D015).
