# QA Report — Sprint 5-teste — Top Produtos por Período — REPROVADO

**Data:** 2026-04-20
**Avaliador:** Evaluator Subagent (isolado)
**Branch:** claude/gallant-aryabhata-1aec12
**Referência:** artifacts/sprint_contract.md

## Veredicto: REPROVADO

4 bugs plantados detectados mecanicamente pelos gates G3, G5, G7 e G8. Critérios
de Alta A2, A3, A4, A5 e A_SMOKE falharam. Nenhum gate mecânico precisou de
inspeção humana para localizar causa raiz — harness v2 validado.

## Pipeline mecânico

| Gate | Resultado | Evidência |
|------|-----------|-----------|
| G1 /health | SKIP | App não subido neste ambiente de avaliação (Evaluator isolado) |
| G2 lint-imports | PASS | `Contracts: 5 kept, 0 broken` |
| G3 tool coverage | FAIL | `capacidade_sem_tool=1 tool_sem_capacidade=0` — `consultar_top_produtos` anunciada no system_prompt mas ausente em `_TOOLS` |
| G4 smoke_ui | SKIP | Requer app rodando + DASHBOARD_SECRET; fora do escopo do Evaluator isolado |
| G5 pytest unit | FAIL | `3 failed` em `test_top_produtos.py` (todos os 3 testes plantados) |
| G6 pytest regression | SKIP | Sem mudanças em arquivos B1..B8; regressão do Sprint-4 não afetada por este diff |
| G7 check_gotchas | FAIL | 8 violações (3 bugs plantados + 5 ocorrências em testes/comentários) |
| G8 smoke_sprint_5_teste | FAIL | `0/3 PASSED` — S1 (HTTP 401 em vez de 302), S2 (gotchas), S3 (tool coverage) |

## Critérios de Alta

### A1 — Endpoint retorna 200 com sessão e 302 sem sessão
**Status:** FAIL
**Evidência real (S1 do smoke):**
```
S1: /dashboard/top-produtos sem sessão → HTTP 401 (esperado 302)
```
**Causa raiz:** `output/src/dashboard/ui.py:574` — `templates.TemplateResponse("top_produtos.html", {"request": request, ...})` usa a API antiga do Starlette 1.0. Além disso, `_verify_session` retorna 401 em vez de 302 para o endpoint novo — o contrato pede 302. Fix: usar nova API `TemplateResponse(request, "top_produtos.html", ctx)` e alinhar comportamento de redirect.

### A2 — SQL não usa INTERVAL hardcoded
**Status:** FAIL
**Evidência real:**
```
output/src/agents/repo.py:795:                   AND p.criado_em >= NOW() - INTERVAL '30 days'
```
**Causa raiz:** `output/src/agents/repo.py:795` — hardcoded `INTERVAL '30 days'` ignora o parâmetro `dias` passado para `top_produtos_por_periodo`. Fix: computar `data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)` em Python e passar como parâmetro bindado (`:data_inicio`).

### A3 — Template não usa |enumerate
**Status:** FAIL
**Evidência real:**
```
output/src/dashboard/templates/top_produtos.html:27: {% for idx, produto in produtos|enumerate %}
```
**Causa raiz:** `output/src/dashboard/templates/top_produtos.html:27` — filtro `|enumerate` não existe em Jinja2. Causa `UndefinedError` em runtime (500 na rota). Fix: `{% for produto in produtos %}` + `{{ loop.index }}` (1-based) ou `{{ loop.index0 }}` (0-based).

### A4 — Tool consultar_top_produtos em _TOOLS
**Status:** FAIL
**Evidência real:**
```
capacidade_sem_tool=1 tool_sem_capacidade=0
Divergências encontradas:
  - [gestor] bullet '- consultar_top_produtos:' no system_prompt mas tool ausente em _TOOLS
```
**Causa raiz:** `output/src/agents/config.py` declara `consultar_top_produtos` no `system_prompt_template` do `AgentGestorConfig`, mas `output/src/agents/runtime/agent_gestor.py` não inclui o tool correspondente em `_TOOLS`. O modelo anuncia a capacidade mas não consegue executar. Fix: adicionar definição da tool em `_TOOLS` + handler que chame `RelatorioRepo.top_produtos_por_periodo`.

### A5 — Testes unitários passam
**Status:** FAIL
**Evidência real:**
```
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_relatorio_top_produtos_usa_timedelta
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_tool_consultar_top_produtos_existe
FAILED output/src/tests/unit/agents/test_top_produtos.py::test_template_nao_usa_enumerate
3 failed in 0.34s
```
**Causa raiz:** Os 3 testes cobrem exatamente os 4 bugs plantados (A2, A3, A4) e falharam como esperado. Corrigir A2/A3/A4 faz esta suíte ficar verde.

### A_SMOKE — Smoke gate staging
**Status:** FAIL
**Evidência real:**
```
=== Sprint 5-teste: 0/3 PASSED ===
Falhas: S1 S2 S3
```
**Observação bloqueante:** `scripts/smoke_sprint_5_teste.sh` imprime `0/3 PASSED` mas termina com `exit=0`. O smoke deve retornar exit-code não-zero em falha para bloquear CI — abrir débito.

## Critérios de Média

| Critério | Status | Evidência |
|----------|--------|-----------|
| M1 cobertura ≥ 80% | N/A | Não avaliado — sprint reprovado em Alta; cobertura sem sentido enquanto código não compila o contrato |

## Segurança

Sem ocorrências de secrets hardcoded, passwords não-env ou `print()` nos arquivos do diff (verificação extraída via `grep`).

## Se REPROVADO — correções necessárias

1. `output/src/agents/repo.py:795` — substituir `INTERVAL '30 days'` por parâmetro `:data_inicio` calculado a partir de `dias` em Python (com `timedelta`).
2. `output/src/dashboard/templates/top_produtos.html:27` — remover `|enumerate`; usar `{% for produto in produtos %}` + `loop.index`.
3. `output/src/dashboard/ui.py:574` — migrar para API nova do Starlette: `templates.TemplateResponse(request, "top_produtos.html", ctx)`.
4. `output/src/agents/runtime/agent_gestor.py` — adicionar entry `consultar_top_produtos` em `_TOOLS` + handler que invoca `RelatorioRepo.top_produtos_por_periodo(tenant_id, dias, limite)`.
5. Revisar comportamento de `_verify_session` para `/dashboard/top-produtos` — contrato pede 302 sem sessão; atualmente retorna 401.

## Débitos (para tech-debt tracker)

- `scripts/smoke_sprint_5_teste.sh` — deve `exit 1` quando `PASSED < TOTAL` (hoje sai com 0 mesmo em 0/3).
- `scripts/check_gotchas.py` — considera match em arquivos de teste; pode poluir relatório de produção (5 das 8 violações do G7 vêm de `test_top_produtos.py` citando o nome do bug). Avaliar excluir `tests/` por default.

## Nota final

O handoff `artifacts/handoff_sprint_5_teste.md` declara veredicto esperado
**REPROVADO** com 4 bugs listados. O harness v2 os localizou todos por
arquivo:linha via gates mecânicos sem depender de inspeção visual — objetivo
do sprint de validação atingido.
