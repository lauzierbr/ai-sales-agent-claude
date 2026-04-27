# QA Report — Sprint 8 — Hotfixes Piloto + Integração EFOS via Backup Diário — APROVADO

**Data:** 2026-04-27
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**APROVADO**

A falha pontual da rodada anterior (A_TOOL_COVERAGE: 3 tools EFOS ausentes do
`system_prompt_template` do `AgentGestorConfig`) foi corrigida de forma cirúrgica.
O diff é mínimo — exatamente 3 linhas adicionadas, sem alteração colateral.
As ferramentas `relatorio_vendas_representante_efos`, `relatorio_vendas_cidade_efos`
e `clientes_inativos_efos` estão agora declaradas no system prompt, definidas em
`_TOOLS` (agent_gestor.py linhas 288, 315, 341), roteadas no dispatcher (linhas 678–697)
e implementadas (linhas 1123, 1174, 1214). Cobertura total: system prompt → _TOOLS →
dispatcher → implementação → testes. Nenhuma regressão introduzida.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/` | PASS (sem resultados) |
| Hardcoded URLs EFOS | `grep -r "jmbdistribuidora\|suporte\|oci-lablz" output/src/integrations/` | PASS (sem resultados) |
| print() proibido | `grep -rn "print(" output/src/` | PASS (verificado rodada anterior) |
| import-linter | `lint-imports` | PASS (verificado rodada anterior — 0 violações) |
| pytest unit | `pytest -m unit` | PASS (verificado rodada anterior — 0 falhas) |
| pytest staging | `pytest -m staging` (macmini-lablz) | PASS (verificado rodada anterior) |
| smoke gate | `python scripts/smoke_sprint_8.py` (macmini-lablz) | PASS (verificado rodada anterior) |

---

## Critérios de Alta — Re-avaliação focal

### A_TOOL_COVERAGE — Cobertura ferramentas vs. system prompt do AgentGestor

**Status:** PASS

**Teste executado:**
1. Inspeção de `output/src/agents/config.py` — `AgentGestorConfig.system_prompt_template`
2. Inspeção de `output/src/agents/runtime/agent_gestor.py` — lista `_TOOLS` e dispatcher

**Evidência observada:**

```
output/src/agents/config.py linhas 226-228:
  "- relatorio_vendas_representante_efos: relatório de vendas de um representante por mês/ano (dados EFOS).\n"
  "- relatorio_vendas_cidade_efos: relatório de vendas por cidade e mês/ano (dados EFOS).\n"
  "- clientes_inativos_efos: lista clientes inativos (situacao=2 no EFOS), com filtro opcional por cidade.\n"

output/src/agents/runtime/agent_gestor.py:
  linha 288: "name": "relatorio_vendas_representante_efos"   (_TOOLS)
  linha 315: "name": "relatorio_vendas_cidade_efos"           (_TOOLS)
  linha 341: "name": "clientes_inativos_efos"                 (_TOOLS)
  linha 678: dispatcher → _relatorio_vendas_representante_efos()
  linha 687: dispatcher → _relatorio_vendas_cidade_efos()
  linha 696: dispatcher → _clientes_inativos_efos()
  linha 1123: implementação _relatorio_vendas_representante_efos
  linha 1174: implementação _relatorio_vendas_cidade_efos
  linha 1214: implementação _clientes_inativos_efos
```

**Diff aplicado (exato):**
```diff
+            "- relatorio_vendas_representante_efos: relatório de vendas de um representante por mês/ano (dados EFOS).\n"
+            "- relatorio_vendas_cidade_efos: relatório de vendas por cidade e mês/ano (dados EFOS).\n"
+            "- clientes_inativos_efos: lista clientes inativos (situacao=2 no EFOS), com filtro opcional por cidade.\n"
```

Zero capacidades anunciadas sem tool correspondente. Critério cumprido.

**Verificação de regressão:** Nenhuma outra linha alterada no arquivo. Estrutura
de classes, demais ferramentas, regras e blocos de formatação WhatsApp intactos.

---

## Critérios de Alta — Status consolidado (todos PASS)

| Critério | ID | Status |
|----------|----|--------|
| `representante_id` propagado para pedidos B2B | A1 | PASS |
| `ClienteB2B.representante_id` no type | A2 | PASS |
| Troca de persona invalida Redis | A3 | PASS |
| Wrapper Langfuse + session_id + output em todos os agentes | A4 | PASS |
| Testes existentes não quebram após mudança em agentes | A5 | PASS |
| Domínio integrations/ não importa domínios de negócio | A6 | PASS |
| `SyncRunRepo` e `SyncArtifactRepo` persistem com tenant_id | A7 | PASS |
| `EFOSBackupConfig.for_tenant("jmb")` sem hardcoded | A8 | PASS |
| `normalize.py` aplica DISTINCT ON ve_codigo | A9 | PASS |
| `publish.py` faz rollback total em falha | A10 | PASS |
| Migrations aplicam sem erro em banco limpo | A11 | PASS |
| Downgrade reverte sem resíduos | A12 | PASS |
| CLI dry-run não modifica banco | A13 | PASS |
| CLI idempotência (skip se checksum já importado) | A14 | PASS |
| Staging DB destruído em finally (mesmo em erro) | A15 | PASS |
| Domínio commerce/ não importa outros domínios | A16 | PASS |
| Todos os métodos `CommerceRepo` filtram por tenant_id | A17 | PASS |
| Fuzzy match retorna mesmo representante para variações | A18 | PASS |
| Normalização cidade → UPPERCASE | A19 | PASS |
| Normalização mês aceita string e int | A20 | PASS |
| Suite unit completa passa sem falhas | A21 | PASS |
| Nenhum teste unit usa I/O externo | A22 | PASS |
| Conversa multi-turn com tool do gestor + follow-up | A_MULTITURN | PASS |
| Cobertura ferramentas vs. system prompt AgentGestor | A_TOOL_COVERAGE | PASS |
| Testes de regressão B-10/B-11/B-12 existem e passam | A_REGRESSION | PASS |
| Smoke gate staging — caminho crítico completo | A_SMOKE | PASS |

---

## Critérios de Média — Status consolidado

| Critério | Status |
|----------|--------|
| M1 — Type hints nas camadas novas | PASS |
| M2 — Docstrings em integrations/ e commerce/ | PASS |
| M3 — Cobertura >= 80% nas camadas novas | PASS |
| M4 — Cobertura >= 80% nos hotfixes | PASS |
| M5 — Zero print() nas novas camadas | PASS |
| M6 — structlog sem event= como kwarg | PASS |
| M_INJECT — Injeção de deps no AgentGestor sem None | PASS |

**Resumo de Média:** 0 falhas de 7. Threshold: 1. Status: dentro do threshold.

---

## Débitos registrados no tech-debt-tracker

Nenhum. Todos os critérios de Média passaram.

---

## O que foi entregue no Sprint 8

1. **Fase 0 — Hotfixes JMB piloto:**
   - B-10: `representante_id` propagado corretamente de `get_by_telefone()` para criação de pedido
   - B-11: troca de persona invalida todas as chaves Redis da conversa (`conv:{tenant_id}:{numero}*`)
   - B-12: todos os 3 agentes usam wrapper Langfuse com `session_id` e `update_current_observation`

2. **Fase 1 — Pipeline EFOS:**
   - Domínio `integrations/` com types, config, repo
   - Conector `efos_backup/` com acquire (SSH/SFTP), stage (pg_restore), normalize, publish
   - 6 migrations Alembic (0018–0023) criando tabelas `commerce_*` e `sync_*`
   - CLI `python -m integrations.jobs.sync_efos` com `--dry-run`, `--force`, `--tenant`
   - launchd plist agendado para 13:00 BRT

3. **Fase 2 — Queries do gestor via commerce_*:**
   - Domínio `commerce/` com types e `CommerceRepo` (3 métodos)
   - `AgentGestor` com 3 novos tools EFOS: `relatorio_vendas_representante_efos`,
     `relatorio_vendas_cidade_efos`, `clientes_inativos_efos`
   - Fuzzy match para nomes de representante, normalização de cidade e mês
   - System prompt atualizado declarando as 3 ferramentas

4. **Testes:**
   - Suite unit passa com 0 falhas
   - Testes de regressão B-10/B-11/B-12 criados test-first
   - Smoke gate staging ALL OK

---

## Como reproduzir os testes

```bash
# Testes unitários (sem infra)
pytest -m unit -v output/src/tests/

# Testes de regressão
pytest output/src/tests/regression/test_sprint_8_bugs.py -v --tb=short

# Testes staging (macmini-lablz)
ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
  infisical run --env=staging -- pytest -m staging -v --tb=short"

# Smoke gate (macmini-lablz)
ssh macmini-lablz "cd ~/ai-sales-agent-claude && \
  infisical run --env=staging -- python scripts/smoke_sprint_8.py"

# Linter e segurança
lint-imports
grep -rn "print(" output/src/
grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/
```

---

## Próximos passos

Sprint 8 APROVADO pelo Evaluator. Ambiente staging pronto para homologação humana.

Smoke gate passou — `scripts/smoke_sprint_8.py` retornou ALL OK no macmini-lablz.

**Próximo passo:** execute os cenários em
`docs/exec-plans/active/homologacao_sprint-8.md` usando WhatsApp real e registre
o resultado.

Só avançar para o Sprint 9 após APROVADO na homologação humana.
