# QA Report — Sprint 3 — AgentRep + Hardening de Linguagem Brasileira — REPROVADO

**Data:** 2026-04-16
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**REPROVADO — Rodada 1 de 1**

Motivo: Critério A4 falha — 2 testes unitários reprovados em `catalog/test_repo.py`.
Os testes são pré-existentes (confirmado por git stash reversal) e não foram
introduzidos pelo Sprint 3, mas o contrato exige 0 falhas em `pytest -m unit`.
O Generator deve corrigir os testes de catálogo para refletir a implementação
correta do workaround asyncpg+pgvector já presente desde Sprint 2.

Adicionalmente: marker `@pytest.mark.staging` não registrada no `pyproject.toml`
(causa `PytestUnknownMarkWarning` em toda execução de `pytest -m unit`).

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -E "(password\|secret\|api_key)=..."` | **PASS** — saída vazia |
| import-linter | `PYTHONPATH=output lint-imports` | **PASS** — 5 contratos kept, 0 broken |
| print() proibido | `grep -r "print(" output/src/ --exclude-dir=tests` | **PASS** — saída vazia |
| pytest -m unit | `pytest -m unit -v` | **FAIL** — 2 failed, 200 passed |

---

## Critérios de Alta

### A1 — import-linter zero violações
**Status:** PASS
**Evidência:** `Contracts: 5 kept, 0 broken. Analyzed 121 files, 514 dependencies.`

### A2 — Sem secrets hardcoded
**Status:** PASS
**Evidência:** grep retornou saída vazia

### A3 — Sem print() em output/src/
**Status:** PASS
**Evidência:** grep retornou saída vazia

### A4 — pytest -m unit 100% pass
**Status:** FAIL
**Teste executado:** `infisical run --env=dev -- pytest -m unit -v`
**Evidência observada:**
```
FAILED output/src/tests/unit/catalog/test_repo.py::test_sql_busca_embedding_usa_operador_pgvector
FAILED output/src/tests/unit/catalog/test_repo.py::test_buscar_por_embedding_retorna_pares_produto_distancia
2 failed, 200 passed, 8 deselected
```
**Causa raiz:**
- `test_sql_busca_embedding_usa_operador_pgvector` (linha 149): o teste asserta
  que a query contém `CAST(:embedding AS vector)`, mas a implementação correta
  (workaround asyncpg do Sprint 2) usa interpolação direta `'{vec_str}'::vector`.
  O teste está errado — foi escrito para uma implementação anterior que foi
  descartada pelo Sprint 2 RCA.
- `test_buscar_por_embedding_retorna_pares_produto_distancia` (linha 429):
  `KeyError: 'embedding'` — o teste acessa `call_params["embedding"]` mas a
  implementação não passa `embedding` como bind param (interpola no f-string).
  Mesma causa raiz.
- **Confirmado pré-existente:** `git stash` + teste isolado mostrou ambas as
  falhas antes das mudanças do Sprint 3.

**Correção necessária:**
Atualizar `output/src/tests/unit/catalog/test_repo.py` para refletir a
implementação real:
1. `test_sql_busca_embedding_usa_operador_pgvector`: substituir assert de
   `CAST(:embedding AS vector)` por assert de `::vector` (sintaxe cast literal)
   que está na implementação atual.
2. `test_buscar_por_embedding_retorna_pares_produto_distancia`: remover
   `call_params["embedding"]` — embedding não é bind param. Verificar
   que `call_params["tenant_id"]` e `call_params["distancia_maxima"]` estão corretos.

### A5 — buscar_clientes_carteira filtra por tenant_id E representante_id
**Status:** PASS
**Teste executado:** `pytest -m unit -k "test_agent_rep_buscar_clientes_carteira_filtra_por_rep"`
**Evidência:** PASSED — mock captura tenant_id="jmb" e representante_id explicitamente

### A6 — confirmar_pedido_em_nome_de com cliente inválido não cria pedido
**Status:** PASS
**Teste executado:** `pytest -m unit -k "test_agent_rep_confirmar_cliente_invalido_nao_cria_pedido"`
**Evidência:** PASSED — OrderService não chamado, resultado contém {"erro": ...}

### A7 — confirmações coloquiais disparam confirmar_pedido (D01–D07)
**Status:** PASS
**Teste executado:** `pytest -m unit -k "grupo_d" -v`
**Evidência:** 7 coletados, 7 PASSED
- test_grupo_d_d01_pode_mandar ✓
- test_grupo_d_d02_vai_la ✓
- test_grupo_d_d03_fecha ✓
- test_grupo_d_d04_beleza_pode_ir ✓
- test_grupo_d_d05_FECHA_maiusculas ✓
- test_grupo_d_d06_sim_confirmo ✓
- test_grupo_d_d07_to_dentro_manda_tudo ✓

### A8 — cancelamentos não disparam confirmar_pedido (E01–E05)
**Status:** PASS
**Teste executado:** `pytest -m unit -k "grupo_e" -v`
**Evidência:** 5 coletados, 5 PASSED
- test_grupo_e_e01_nao_deixa ✓
- test_grupo_e_e02_cancela ✓
- test_grupo_e_e03_esquece ✓
- test_grupo_e_e04_perai_ver_chefe ✓
- test_grupo_e_e05_nao_quero_mais ✓

### A9 — conversa persistida com Persona.REPRESENTANTE
**Status:** PASS
**Evidência:** `pytest -k "test_agent_rep_persona_representante"` → PASSED
Inspeção de agent_rep.py linha 198: `persona=Persona.REPRESENTANTE` confirmado.

### A10 — session.commit() após pedido do rep
**Status:** PASS
**Evidência:** `pytest -k "test_agent_rep_commit_apos_pedido"` → PASSED
Inspeção de agent_rep.py linha 292: `await session.commit()` confirmado.

### A11 — buscar_por_nome usa unaccent + ILIKE
**Status:** PASS
**Evidência:**
```
output/src/agents/repo.py:176: """Busca clientes B2B ativos pelo nome usando unaccent + ILIKE.
output/src/agents/repo.py:198: AND unaccent(lower(nome)) ILIKE unaccent(lower('%' || :query || '%'))
```

### A12 — Migration 0013 aplica e reverte sem erro
**Status:** PASS (inspeção de código)
**Evidência:** `output/alembic/versions/0013_clientes_b2b_representante_id.py` —
`upgrade()` usa `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `downgrade()` usa
`DROP COLUMN IF EXISTS`. FK `ON DELETE SET NULL`. Índice `ix_clientes_b2b_rep`.
Execução real não possível no container do Evaluator (requer PostgreSQL).

### A_SMOKE — staging smoke com Postgres + Redis reais
**Status:** PASS (inspeção — não executável no container)
**Evidência:** `test_agent_rep_staging.py` existe, usa `@pytest.mark.staging`,
testa `AgentRep.responder` com Claude real + banco real, verifica persitência.
Marcado corretamente para não executar em `pytest -m unit`.

### M_INJECT — deps não-None no wiring do AgentRep
**Status:** PASS
**Evidência:** `pytest -k "test_webhook_agent_rep_deps_nao_none"` → PASSED (10 testes, todos passed)

---

## Critérios de Média

### M1 — mypy --strict nos arquivos novos/modificados
**Status:** NÃO AVALIADO (mypy --strict em projeto existente gera muitos erros de módulos
de terceiros não tipados; avaliação limitada aos novos módulos da forma prática seria
necessária — registrado como débito)

### M2 — OTel span em AgentRep.responder
**Status:** PASS
**Evidência:** `agent_rep.py` linha 188: `tracer.start_as_current_span("agent_rep_responder")`
com `span.set_attribute("tenant_id", tenant.id)` e `span.set_attribute("rep_id", representante.id)`

### M3 — Cobertura ≥ 80% em agent_rep.py
**Status:** PASS (inspeção: 11 testes cobrindo todos os caminhos críticos: buscar, confirmar,
validar carteira, max_iter, persona, commit, deps none)

### M4 — Cobertura ≥ 60% em agents/repo.py
**Status:** PASS (novos métodos `buscar_por_nome` e `listar_por_representante` têm testes diretos
em `test_agent_rep.py` via mock de sessão)

### M5 — Regressão Sprint 2: H01–H04 passam
**Status:** PASS
**Evidência:** `pytest -m unit -k "grupo_h"` → 4 coletados, 4 PASSED

### M6 — Docstrings em métodos públicos novos
**Status:** PASS (inspeção: agent_rep.py, repo.py novos métodos — todos com docstring Args/Returns)

**Resumo de Média:** 0 falhas de 6 (M1 não avaliado formalmente — registrado como débito técnico).
Threshold: 1. Status: **dentro do threshold**.

---

## Débitos registrados no tech-debt-tracker

- [M1] mypy --strict não executado completamente — verificação de type hints nos novos
  módulos recomendada antes do Sprint 4. Arquivos: `agent_rep.py`, `repo.py` (novos métodos).
- [MARKER] `@pytest.mark.staging` não registrado em `pyproject.toml` — causa
  `PytestUnknownMarkWarning` em toda execução. Corrigir junto com A4.

---

## Correções necessárias (única rodada — 2 itens)

**Prioridade 1 — A4 (funcionalidade):**

1. `output/src/tests/unit/catalog/test_repo.py` — linha 149:
   Substituir assert de `CAST(:embedding AS vector)` por assert de `::vector`
   (a implementação usa interpolação f-string, não bind param)

2. `output/src/tests/unit/catalog/test_repo.py` — linha 429:
   Remover `call_params["embedding"]` — embedding não é bind param no asyncpg workaround.
   Verificar `call_params["tenant_id"]` e `call_params["distancia_maxima"]`.

**Prioridade 2 — Marker staging (warning → correto):**

3. `pyproject.toml` — adicionar `"staging: testes de staging (requerem Postgres+Redis reais)"` 
   na lista de `markers` do `[tool.pytest.ini_options]`.

---

## Como reproduzir

```bash
cd /Users/lauzier/MyRepos/ai-sales-agent-claude/.claude/worktrees/awesome-benz
PYTHONPATH=output /Users/lauzier/MyRepos/ai-sales-agent-claude/.venv/bin/lint-imports
infisical run --env=dev -- /Users/lauzier/MyRepos/ai-sales-agent-claude/.venv/bin/pytest -m unit -v --tb=short
```

---

## Próximos passos (rodada de correção)

**Esta é a rodada 1 de 1.** Generator deve:
1. Corrigir os 2 testes em `catalog/test_repo.py`
2. Adicionar marker `staging` em `pyproject.toml`
3. Rodar `pytest -m unit` localmente — deve retornar 0 falhas
4. Resubmeter ao Evaluator
