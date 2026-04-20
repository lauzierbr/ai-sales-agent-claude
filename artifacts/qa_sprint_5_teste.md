# QA Report — Sprint 5-teste — Top Produtos por Período — REPROVADO

**Data:** 2026-04-20
**Avaliador:** Evaluator Subagent (isolado)
**Referência:** artifacts/sprint_contract.md

## Veredicto: REPROVADO

Gates de Alta falharam: A2 (INTERVAL hardcoded em SQL), A3 (|enumerate em template Jinja2), A4 (tool `consultar_top_produtos` anunciada e ausente de `_TOOLS`), A5 (3 testes unit FAIL), e G7 (check_gotchas com 8 violações, incluindo `starlette_template_response_old_api` na view nova). Smoke de sprint (G8) falhou 3/3. Todos os 4 bugs plantados foram detectados.

## Pipeline mecânico

| Gate | Resultado | Evidência |
|------|-----------|-----------|
| G1 /health | PASS | HTTP 200 |
| G2 lint-imports | PASS | `Contracts: 5 kept, 0 broken.` |
| G3 tool coverage | FAIL | `capacidade_sem_tool=1 tool_sem_capacidade=0` — `[gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS` |
| G4 smoke_ui | SKIP/FAIL ambiental | `[ABORT] DASHBOARD_SECRET não configurado.` (não bloqueante — env de CI) |
| G5 pytest unit | FAIL | `3 failed, 236 passed, 3 deselected in 2.33s` |
| G6 pytest regression | FAIL | `1 failed, 7 passed` — `test_b6_deploy_nao_usa_rsync_relative` |
| G7 check_gotchas | FAIL | `check_gotchas: 8 violação(ões) encontrada(s)` — sql_hardcoded_interval, jinja2_enumerate_filter, starlette_template_response_old_api |
| G8 smoke_sprint_5 | FAIL | `Sprint 5-teste: 0/3 PASSED` |

### Saídas reais (não parafraseadas)

**G2:**
```
Analyzed 136 files, 658 dependencies.
Contracts: 5 kept, 0 broken.
```

**G3:**
```
capacidade_sem_tool=1 tool_sem_capacidade=0
Divergências encontradas:
  - [gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS
```

**G5 (trecho das falhas):**
```
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_relatorio_top_produtos_usa_timedelta
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_tool_consultar_top_produtos_existe
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_template_nao_usa_enumerate
3 failed, 236 passed, 3 deselected in 2.33s
```

**G7 (violações novas introduzidas pelo sprint):**
```
[starlette_template_response_old_api]
  → output/src/dashboard/ui.py:574: return templates.TemplateResponse("top_produtos.html", {"request": request, **ctx})
[jinja2_enumerate_filter]
  → output/src/dashboard/templates/top_produtos.html:27: {% for idx, produto in produtos|enumerate %}
[sql_hardcoded_interval]
  → output/src/agents/repo.py:795:                   AND p.criado_em >= NOW() - INTERVAL '30 days'
```

**G8:**
```
[FAIL] S1 — /dashboard/top-produtos sem sessão → HTTP 401 (esperado 302)
[FAIL] S2 — check_gotchas detectou violações
[FAIL] S3 — tool coverage com divergência
Sprint 5-teste: 0/3 PASSED
```

## Segurança

| Check | Resultado |
|-------|-----------|
| Secrets hardcoded (`sk-ant`, `api_key=`) | OK — sem ocorrências |
| Passwords hardcoded | OK — sem ocorrências |
| `print()` em código de produção | OK — sem ocorrências |

## A_MULTITURN — serialização de histórico Redis

PASS. Grep em `output/src/agents/runtime/`:
- `agent_gestor.py:350` usa `[b.model_dump() for b in response.content]`
- `agent_cliente.py:264` usa `[b.model_dump() for b in response.content]`
- `agent_rep.py:314` usa `[b.model_dump() for b in response.content]`

## Critérios de Alta

### A1 — Endpoint HTTP 200/302 conforme sessão
**Status:** FAIL
**Evidência real:** Smoke `S1 — /dashboard/top-produtos sem sessão → HTTP 401 (esperado 302)`
**Causa raiz:** `output/src/dashboard/ui.py:574` — endpoint usa API antiga de `TemplateResponse` (violação `starlette_template_response_old_api`). Além disso, comportamento sem sessão retornou 401 em vez de 302 esperado no contrato.

### A2 — SQL não usa INTERVAL hardcoded
**Status:** FAIL
**Evidência real:**
```
output/src/agents/repo.py:784:        # BUG PLANTADO: INTERVAL hardcoded ignora o parâmetro `dias`
output/src/agents/repo.py:795:                  AND p.criado_em >= NOW() - INTERVAL '30 days'
```
**Causa raiz:** `output/src/agents/repo.py:795` — `top_produtos_por_periodo` usa `INTERVAL '30 days'` fixo, ignorando o parâmetro `dias`. Gotcha `sql_hardcoded_interval`. Correção: computar `data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)` em Python e passar como bind param.

### A3 — Template não usa |enumerate
**Status:** FAIL
**Evidência real:**
```
26:      {# BUG PLANTADO: |enumerate não existe em Jinja2 — causa UndefinedError #}
27:      {% for idx, produto in produtos|enumerate %}
```
**Causa raiz:** `output/src/dashboard/templates/top_produtos.html:27` — filter `|enumerate` não existe em Jinja2, causa `UndefinedError` em runtime (500). Correção: `{% for produto in produtos %}` + `{{ loop.index }}`.

### A4 — Tool consultar_top_produtos em _TOOLS
**Status:** FAIL
**Evidência real:**
```
[gestor] tools=7 → ['buscar_clientes', 'buscar_produtos', 'confirmar_pedido_em_nome_de', 'relatorio_vendas', 'clientes_inativos', 'aprovar_pedidos', 'listar_pedidos_por_status']
capacidade_sem_tool=1 tool_sem_capacidade=0
  - [gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS
```
**Causa raiz:** `output/src/agents/runtime/agent_gestor.py` — `_TOOLS` não inclui `consultar_top_produtos`, mas o system prompt anuncia essa capacidade. Modelo não pode chamar a tool → hallucination. Handoff confirma que `agent_gestor.py` "não foi modificado" (bug D4).

### A5 — Testes unitários passam
**Status:** FAIL
**Evidência real:**
```
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_relatorio_top_produtos_usa_timedelta
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_tool_consultar_top_produtos_existe
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_template_nao_usa_enumerate
3 failed, 236 passed
```
**Causa raiz:** os 3 bugs plantados (A2, A3, A4) reprovam seus respectivos testes-sentinela.

### A_SMOKE — Smoke gate staging
**Status:** FAIL
**Evidência real:** `=== Sprint 5-teste: 0/3 PASSED ===` — S1 (HTTP 401 vs 302), S2 (gotchas), S3 (tool coverage) todos FAIL.

## Critérios de Média

Threshold: 1 falha máx.

| Critério | Status | Evidência |
|----------|--------|-----------|
| M1 Cobertura branches ≥ 80% | NÃO AVALIADO | Irrelevante — sprint já REPROVADO por A1–A5. |

## Bugs plantados detectados (4/4)

1. **`sql_hardcoded_interval`** — `output/src/agents/repo.py:795` — `NOW() - INTERVAL '30 days'` ignora parâmetro `dias`.
2. **`jinja2_enumerate_filter`** — `output/src/dashboard/templates/top_produtos.html:27` — `produtos|enumerate` não existe em Jinja2, quebra em runtime.
3. **`starlette_template_response_old_api`** — `output/src/dashboard/ui.py:574` — `templates.TemplateResponse("top_produtos.html", {"request": request, ...})` usa API antiga; Starlette 1.0 exige `request` como 1º arg posicional.
4. **Tool coverage gap** — `output/src/agents/runtime/agent_gestor.py` — `consultar_top_produtos` anunciada em `system_prompt_template` (config.py) mas ausente em `_TOOLS` do `agent_gestor.py`.

## Correções necessárias

1. `output/src/agents/repo.py:795` — remover `INTERVAL '30 days'`; calcular `data_inicio` em Python com `timedelta(days=dias)` e passar como bind param `:data_inicio`.
2. `output/src/dashboard/templates/top_produtos.html:26-27` — remover comentário de bug e trocar `{% for idx, produto in produtos|enumerate %}` por `{% for produto in produtos %}` com `{{ loop.index }}`.
3. `output/src/dashboard/ui.py:574` — usar API nova: `templates.TemplateResponse(request, "top_produtos.html", ctx)`.
4. `output/src/agents/runtime/agent_gestor.py` — adicionar entrada `consultar_top_produtos` em `_TOOLS` com schema `{tenant_id, dias, limite}` e dispatcher que chama `RelatorioRepo.top_produtos_por_periodo`.
5. Após correções: reexecutar `pytest -m unit`, `check_gotchas.py`, `check_tool_coverage.py`, `smoke_sprint_5_teste.sh` — exigir verdes.

## Débitos

N/A — sprint REPROVADO.
