# Doc Gardening — Agente de Manutenção de Documentação

Instruções para execução periódica do agente de doc-gardening.
Inspirado no artigo da OpenAI: agente recorrente que detecta documentação
desatualizada e abre PRs de correção.

## Quando executar

- Ao final de cada sprint (pelo Evaluator, como parte do processo)
- Semanalmente via Claude Code manual: `claude` → usar estas instruções

## Prompt para o Claude Code

```
Você é o Doc Gardening Agent do projeto ai-sales-agent.

Sua função é verificar se a documentação reflete o estado real do código.
Execute as verificações abaixo e abra issues ou corrija diretamente.

## Verificações obrigatórias

### 1. QUALITY_SCORE.md
Compare o status declarado em docs/QUALITY_SCORE.md com o código real em src/.
Para cada domínio marcado como ✅, verifique se:
- O módulo existe em src/
- Os testes existem em src/tests/
- O linter passa: import-linter --config pyproject.toml

Atualize qualquer status incorreto.

### 2. docs/exec-plans/active/
Para cada exec-plan em active/:
- Verifique as checkboxes contra o código real
- Marque itens concluídos com [x]
- Se o plan estiver 100% concluído, mova para completed/

### 3. docs/design-docs/index.md
Verifique se todas as ADRs listadas têm arquivo correspondente em design-docs/.
Liste as que estão no índice mas sem arquivo.

### 4. docs/product-specs/index.md
Verifique se specs marcados como "em desenvolvimento" têm
sprint_contract correspondente em artifacts/.

### 5. AGENTS.md
Verifique se os comandos rápidos em AGENTS.md ainda funcionam
(sintaxe correta, arquivos referenciados existem).

### 6. tech-debt-tracker.md
Verifique se itens marcados como Alta já foram corrigidos no código.
Se sim, mova para a seção "Itens resolvidos".

## Output esperado

Crie o arquivo docs/gardening/report-AAAA-MM-DD.md com:
- Lista de inconsistências encontradas
- Correções aplicadas diretamente
- Itens que requerem atenção humana

Faça commit com a mensagem:
"docs: gardening report AAAA-MM-DD — [N] correções aplicadas"
```

## Histórico de execuções

| Data | Correções | Itens pendentes | Executado por |
|------|-----------|----------------|---------------|
| — | — | — | — |
