# QA Report — Sprint 5-teste — Top Produtos por Período — REPROVADO (R1)

**Data:** 2026-04-20
**Avaliador:** Evaluator Subagent (isolado) — rodada R1 pós-correção
**Referência:** artifacts/sprint_contract.md
**Relatório anterior:** artifacts/qa_sprint_5_teste.md (R0)

## Veredicto: REPROVADO

Nenhuma correção foi aplicada entre R0 e R1. O Generator afirmou ter
corrigido, mas `git log` mostra que o último commit (`be5ae82 fix: B6 regression
test + smoke_ui DASHBOARD_SECRET skip`) é anterior ao R0 e não toca nenhum dos
arquivos dos 4 bugs. Os 4 bugs plantados continuam idênticos à R0, os mesmos 3
testes unit falham, e as mesmas 3 violações novas de gotchas permanecem no
código do sprint. Estado dos bugs: **4/4 AINDA PRESENTE, 0 CORRIGIDO,
0 REGREDIU, 0 novos problemas.**

## Evidência de ausência de correção

```
$ git log -5 --oneline
be5ae82 fix: B6 regression test + smoke_ui DASHBOARD_SECRET skip
b7501f7 test(harness): Sprint 5-teste — top produtos com 4 bugs plantados para validar harness v2
95971fc feat: Onda 3 — Evaluator subagent isolado + deploy via git checkout (harness v2)
827f5b2 feat: Onda 2 — multi-turn smoke, evaluator checkpoint, gotcha registry (harness v2)
41eac60 feat: harness v2 Onda 1 — gates mecânicos + retry 529 + regressão Sprint 4

$ git status
On branch claude/gallant-aryabhata-1aec12
Your branch is up to date with 'origin/claude/gallant-aryabhata-1aec12'.
Untracked files:
	artifacts/qa_sprint_5_teste.md
nothing added to commit but untracked files present
```

Nenhum commit novo em `output/src/**` desde R0. Nenhum arquivo de `output/`
modificado/staged.

## Pipeline mecânico

| Gate | Resultado | Evidência |
|------|-----------|-----------|
| G1 /health | PASS | HTTP 200 |
| G2 lint-imports | PASS | `Contracts: 5 kept, 0 broken.` |
| G3 tool coverage | FAIL | `capacidade_sem_tool=1 tool_sem_capacidade=0` — `[gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS` |
| G4 smoke_ui | SKIP | `[SKIP] DASHBOARD_SECRET não configurado` (não bloqueante — env local sem infisical) |
| G5 pytest unit | FAIL | `3 failed, 236 passed, 3 deselected in 1.81s` |
| G6 pytest regression | PASS | `8 passed in 0.24s` |
| G7 check_gotchas | FAIL | `check_gotchas: 8 violação(ões) encontrada(s)` — `sql_hardcoded_interval`, `jinja2_enumerate_filter`, `starlette_template_response_old_api` |
| G8 smoke_sprint_5_teste | FAIL | `Sprint 5-teste: 0/3 PASSED` |

### Saídas reais (não parafraseadas)

**G1:**
```
G1 /health → 200
```

**G2:**
```
Repo: não importa Service, Runtime ou UI KEPT
Service: não importa Runtime ou UI KEPT
Runtime: não importa UI KEPT

Contracts: 5 kept, 0 broken.
```

**G3:**
```
[cliente] tools=3 → ['buscar_produtos', 'listar_meus_pedidos', 'confirmar_pedido']
  OK: todas as 3 tools alinhadas com o prompt
[rep] tools=5 → ['buscar_produtos', 'buscar_clientes_carteira', 'aprovar_pedidos_carteira', 'listar_pedidos_carteira', 'confirmar_pedido_em_nome_de']
  OK: todas as 5 tools alinhadas com o prompt
[gestor] tools=7 → ['buscar_clientes', 'buscar_produtos', 'confirmar_pedido_em_nome_de', 'relatorio_vendas', 'clientes_inativos', 'aprovar_pedidos', 'listar_pedidos_por_status']

capacidade_sem_tool=1 tool_sem_capacidade=0

Divergências encontradas:
  - [gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS
```

**G4:**
```
=== UI SMOKE GATE ===
  Base URL: http://localhost:8000
[L0] Login dashboard...
  [SKIP] DASHBOARD_SECRET não configurado — smoke_ui ignorado.
=== UI SMOKE GATE: SKIP (sem DASHBOARD_SECRET) ===
```

**G5 (trecho das falhas):**
```
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_relatorio_top_produtos_usa_timedelta
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_tool_consultar_top_produtos_existe
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_template_nao_usa_enumerate
3 failed, 236 passed, 3 deselected in 1.81s
```

**G6:**
```
output/src/tests/regression/test_sprint_4_bugs.py ........               [100%]
8 passed in 0.24s
```

**G7 (violações novas do sprint — idênticas à R0):**
```
check_gotchas: 8 violação(ões) encontrada(s)

[starlette_template_response_old_api]
  → output/src/dashboard/ui.py:574:     return templates.TemplateResponse("top_produtos.html", {"request": request, **ctx})

[jinja2_enumerate_filter]
  → output/src/dashboard/templates/top_produtos.html:26:       {# BUG PLANTADO: |enumerate não existe em Jinja2 — causa UndefinedError #}
  → output/src/dashboard/templates/top_produtos.html:27:       {% for idx, produto in produtos|enumerate %}

[sql_hardcoded_interval]
  → output/src/agents/repo.py:795:                   AND p.criado_em >= NOW() - INTERVAL '30 days'
```

**G8:**
```
=== SMOKE Sprint 5-teste — Top Produtos ===
  [FAIL] S1 — /dashboard/top-produtos sem sessão → HTTP 401 (esperado 302)
  [FAIL] S2 — check_gotchas detectou violações — ver /tmp/gotchas_s5.log
  [FAIL] S3 — tool coverage com divergência — ver /tmp/tool_cov_s5.log
=== Sprint 5-teste: 0/3 PASSED ===
```

## Segurança

| Check | Resultado |
|-------|-----------|
| Secrets hardcoded (`sk-ant`, `api_key=`) | OK — sem ocorrências |
| Passwords hardcoded | OK — sem ocorrências |
| `print()` em código de produção | OK — sem ocorrências |

## A_MULTITURN — serialização de histórico Redis

PASS (inalterado vs R0). Grep em `output/src/agents/runtime/`:
```
agent_rep.py:314:     messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
agent_gestor.py:350:  messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
agent_cliente.py:264: messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
```

## Estado dos 4 bugs originais (R0 → R1)

| # | Bug | Arquivo:linha | Estado R1 |
|---|-----|---------------|-----------|
| 1 | `sql_hardcoded_interval` — `INTERVAL '30 days'` ignora parâmetro `dias` | `output/src/agents/repo.py:795` | **AINDA PRESENTE** |
| 2 | `jinja2_enumerate_filter` — `produtos\|enumerate` inexistente em Jinja2 | `output/src/dashboard/templates/top_produtos.html:27` | **AINDA PRESENTE** |
| 3 | `starlette_template_response_old_api` — dict-style API antiga | `output/src/dashboard/ui.py:574` | **AINDA PRESENTE** |
| 4 | Tool `consultar_top_produtos` anunciada mas ausente de `_TOOLS` | `output/src/agents/runtime/agent_gestor.py` | **AINDA PRESENTE** (`grep consultar_top_produtos agent_gestor.py` → 0 matches) |

Nenhum bug novo introduzido (não há mudanças em `output/` entre R0 e R1).

## Critérios de Alta

### A1 — Endpoint HTTP 200/302 conforme sessão
**Status:** FAIL
**Evidência real:** `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/dashboard/top-produtos` → `401`. Smoke S1: `/dashboard/top-produtos sem sessão → HTTP 401 (esperado 302)`.
**Causa raiz:** `output/src/dashboard/ui.py:574` — endpoint usa API antiga `TemplateResponse("name", {"request": ...})`. Além disso, middleware de auth retorna 401 onde o contrato exigia 302.

### A2 — SQL não usa INTERVAL hardcoded
**Status:** FAIL
**Evidência real:**
```
$ grep -n "INTERVAL" output/src/agents/repo.py
413:                  AND iniciada_em > NOW() - INTERVAL '24 hours'
750:                    OR MAX(p.criado_em) < NOW() - (:dias * INTERVAL '1 day')
784:        # BUG PLANTADO: INTERVAL hardcoded ignora o parâmetro `dias`
795:                  AND p.criado_em >= NOW() - INTERVAL '30 days'
```
**Causa raiz:** `output/src/agents/repo.py:795` — `top_produtos_por_periodo` ignora `dias`. Correção: `data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)` + bind param `:data_inicio`.

### A3 — Template não usa |enumerate
**Status:** FAIL
**Evidência real:**
```
26:      {# BUG PLANTADO: |enumerate não existe em Jinja2 — causa UndefinedError #}
27:      {% for idx, produto in produtos|enumerate %}
```
**Causa raiz:** `output/src/dashboard/templates/top_produtos.html:27` — trocar por `{% for produto in produtos %}` + `{{ loop.index }}`.

### A4 — Tool consultar_top_produtos em _TOOLS
**Status:** FAIL
**Evidência real:**
```
[gestor] tools=7 → ['buscar_clientes', 'buscar_produtos', 'confirmar_pedido_em_nome_de', 'relatorio_vendas', 'clientes_inativos', 'aprovar_pedidos', 'listar_pedidos_por_status']
capacidade_sem_tool=1 tool_sem_capacidade=0
  - [gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS
```
`grep -n consultar_top_produtos output/src/agents/runtime/agent_gestor.py` → sem resultados.
**Causa raiz:** `output/src/agents/runtime/agent_gestor.py` — adicionar entrada `consultar_top_produtos` em `_TOOLS` + dispatcher chamando `RelatorioRepo.top_produtos_por_periodo`.

### A5 — Testes unitários passam
**Status:** FAIL
**Evidência real:**
```
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_relatorio_top_produtos_usa_timedelta
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_tool_consultar_top_produtos_existe
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_template_nao_usa_enumerate
3 failed, 236 passed, 3 deselected in 1.81s
```
**Causa raiz:** os 3 bugs plantados (A2, A3, A4) reprovam seus testes-sentinela.

### A_SMOKE — Smoke gate staging
**Status:** FAIL
**Evidência real:** `=== Sprint 5-teste: 0/3 PASSED ===`.

## Critérios de Média

Threshold: 1 falha máx.

| Critério | Status | Evidência |
|----------|--------|-----------|
| M1 Cobertura branches ≥ 80% | NÃO AVALIADO | Irrelevante — sprint REPROVADO por A1–A5. |

## Gates que falharam

- G3 tool coverage
- G5 pytest unit (3 failed)
- G7 check_gotchas (8 violações — 3 referentes ao sprint)
- G8 smoke_sprint_5_teste (0/3)
- Todos os critérios A1–A5 e A_SMOKE do contrato

## Correções necessárias

1. `output/src/agents/repo.py:795` — remover `INTERVAL '30 days'`; calcular `data_inicio` em Python com `timedelta(days=dias)` e passar como bind param `:data_inicio`. Remover comentário de bug em linha 784.
2. `output/src/dashboard/templates/top_produtos.html:26-27` — remover comentário de bug e trocar `{% for idx, produto in produtos|enumerate %}` por `{% for produto in produtos %}` com `{{ loop.index }}`; ajustar uso de `idx` no corpo.
3. `output/src/dashboard/ui.py:574` — usar API nova: `templates.TemplateResponse(request, "top_produtos.html", ctx)`. Remover comentário de bug acima.
4. `output/src/agents/runtime/agent_gestor.py` — adicionar entrada `consultar_top_produtos` em `_TOOLS` com schema `{tenant_id, dias, limite}` e dispatcher que chama `RelatorioRepo.top_produtos_por_periodo`.
5. Comitar as correções (agora estão ausentes — `git log` não mostra commit pós-R0).
6. Reexecutar pipeline completo (`pytest -m unit`, `check_gotchas.py`, `check_tool_coverage.py`, `smoke_sprint_5_teste.sh`) — exigir verdes antes de nova rodada.

## Observação para o harness

Esta rodada R1 foi disparada com a premissa "Generator afirma ter corrigido",
mas a árvore de trabalho está idêntica à R0 — zero commits novos, zero arquivos
modificados em `output/`. Recomenda-se que o Generator confirme (e o harness
valide via `git rev-parse HEAD` antes/depois) que as correções foram de fato
commitadas antes de acionar o Evaluator.

## Débitos

N/A — sprint REPROVADO.
