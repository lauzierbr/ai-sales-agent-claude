# Harness no Codex — Playbook Operacional

Guia prático para simular o harness deste repositório no Codex Desktop
usando chats separados para `Planner`, `Generator` e `Evaluator`.

## Objetivo

Preservar a separação de papéis do harness original:

- `Planner` define escopo, riscos e plano do sprint.
- `Generator` negocia contrato, implementa e prepara homologação.
- `Evaluator` revisa contrato e depois avalia a entrega com viés de reprovação.

A comunicação entre papéis deve acontecer por arquivos do repositório, não
por conversa entre chats.

## Estrutura recomendada

Abra 3 chats separados no Codex:

1. `Planner`
2. `Generator`
3. `Evaluator`

Use o mesmo repositório em todos os chats.

## Canal oficial de handoff

Os chats trocam contexto apenas por arquivos:

- `artifacts/spec.md`
- `artifacts/sprint_contract.md`
- `artifacts/qa_sprint_N.md`
- `docs/exec-plans/active/sprint-N-*.md`
- `docs/exec-plans/active/homologacao_sprint-N.md`

## Fluxo operacional

### 1. Planner

No chat `Planner`, usar:

```text
Leia CLAUDE.md e prompts/planner.md. Você é o Planner.
Execute o planejamento do sprint: [descreva o sprint em 1-4 frases]
```

Saídas esperadas:

- `artifacts/spec.md`
- `docs/exec-plans/active/sprint-N-nome.md`

Checkpoint humano:

- revisar `artifacts/spec.md`
- pedir ajustes ao Planner se o escopo estiver ruim
- encerrar o papel do Planner quando o spec estiver aceito

### 2. Generator — Fase 1 (contrato)

No chat `Generator`, usar:

```text
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O spec está em artifacts/spec.md. Comece pela Fase 1: proponha o sprint contract.
```

Saída esperada:

- `artifacts/sprint_contract.md`

### 3. Evaluator — revisão do contrato

No chat `Evaluator`, usar:

```text
Leia CLAUDE.md e prompts/evaluator.md. Você é o Evaluator.
O contrato está em artifacts/sprint_contract.md. Execute a avaliação completa.
```

Resultado esperado:

- `ACEITO`, ou
- objeções concretas ao contrato

Se houver objeções:

1. voltar ao `Generator`
2. ajustar `artifacts/sprint_contract.md`
3. rodar o `Evaluator` novamente

Repita até o contrato ficar aceito.

### 4. Generator — Fase 2 (implementação)

Quando o contrato estiver aceito, no chat `Generator`, usar:

```text
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O contrato em artifacts/sprint_contract.md foi aceito. Execute a Fase 2 completa:
implemente, rode os checks necessários e atualize os artefatos/documentação do sprint.
```

Saídas esperadas:

- código em `output/src/`
- testes e scripts do sprint
- documentação do sprint atualizada
- se aplicável, `docs/exec-plans/active/homologacao_sprint-N.md`

### 5. Congelar o estado antes da QA

Antes de pedir a avaliação final ao `Evaluator`:

- não deixe o `Generator` continuar editando
- idealmente faça um commit
- no mínimo, deixe a working tree estável

O `Evaluator` deve revisar um snapshot claro, não um alvo móvel.

### 6. Evaluator — avaliação do código

No chat `Evaluator`, usar:

```text
Leia CLAUDE.md e prompts/evaluator.md. Você é o Evaluator.
O contrato está em artifacts/sprint_contract.md. Execute a avaliação completa do código entregue.
```

Saída esperada:

- `artifacts/qa_sprint_N.md`
- veredito `APROVADO` ou `REPROVADO`

Se `REPROVADO`:

1. voltar ao `Generator`
2. corrigir o que foi apontado
3. congelar o estado novamente
4. rodar o `Evaluator` de novo

### 7. Generator — homologação

Depois do `APROVADO`, no chat `Generator`, usar:

```text
Leia CLAUDE.md e prompts/generator.md. Você é o Generator.
O sprint foi aprovado pelo Evaluator. Prepare a homologação: staging, seed,
checklist e atualização de docs.
```

Saídas esperadas:

- scripts/checks de staging
- `docs/exec-plans/active/homologacao_sprint-N.md`
- atualização de `docs/QUALITY_SCORE.md`, quando aplicável

## Snapshot recomendado entre fases

Se quiser mais disciplina entre chats, use um snapshot por fase:

1. após `artifacts/spec.md`
2. após `artifacts/sprint_contract.md` aceito
3. após implementação pronta
4. após `artifacts/qa_sprint_N.md`

O snapshot pode ser:

- um commit local, ou
- pelo menos uma working tree parada e sem edição concorrente

## Quando usar worktrees

Não é obrigatório usar worktrees separados.

Use worktrees apenas se quiser:

- executar papéis em paralelo
- preservar snapshots independentes
- impedir que o `Evaluator` veja arquivos sendo alterados no mesmo checkout

Para a maioria dos sprints, fluxo sequencial no mesmo checkout é suficiente.

## Configuração mínima aceitável

Se quiser simplificar para 2 chats:

- Chat A: `Planner`, depois `Generator`
- Chat B: `Evaluator`

Ainda assim, o recomendado é manter o `Evaluator` isolado.

## Anti-padrões

Evite estes modos de operação:

- `Generator` e `Evaluator` no mesmo chat
- `Evaluator` corrigindo código
- `Generator` se autoaprovando
- usar conversa entre chats como fonte oficial de handoff
- chamar o `Evaluator` enquanto o `Generator` ainda está editando

## Checklist por sprint

### Planejamento

- `Planner` gerou `artifacts/spec.md`
- humano revisou o spec

### Contrato

- `Generator` gerou `artifacts/sprint_contract.md`
- `Evaluator` aceitou o contrato

### Implementação

- `Generator` implementou o sprint
- checks locais mínimos rodaram
- estado foi congelado para QA

### QA

- `Evaluator` gerou `artifacts/qa_sprint_N.md`
- falhas, se houver, voltaram ao `Generator`

### Homologação

- `Generator` preparou staging/seed/checklist
- homologação humana executada

## Resumo operacional

O modelo correto no Codex é:

1. `Planner` escreve spec
2. `Generator` escreve contrato
3. `Evaluator` aceita ou objeta o contrato
4. `Generator` implementa
5. `Evaluator` aprova ou reprova o código
6. `Generator` prepara homologação

Regra de ouro:

- `Planner` e `Evaluator` escrevem especificação e avaliação
- `Generator` escreve código
- handoff sempre por arquivo
