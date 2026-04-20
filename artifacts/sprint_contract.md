# Sprint Contract — Sprint 5-teste — Top Produtos por Período

**Status:** ACEITO
**Data:** 2026-04-20

## Entregas comprometidas

1. `RelatorioRepo.top_produtos_por_periodo(tenant_id, dias, limite)` em `output/src/agents/repo.py`
2. Endpoint `GET /dashboard/top-produtos` em `output/src/dashboard/ui.py`
3. Template `output/src/dashboard/templates/top_produtos.html`
4. Tool `consultar_top_produtos` em `_TOOLS` do `agent_gestor.py` + system prompt atualizado
5. Testes unitários em `output/src/tests/unit/agents/test_top_produtos.py`
6. Smoke gate `scripts/smoke_sprint_5_teste.sh`

## Critérios de aceitação — Alta (bloqueantes)

A1. Endpoint retorna HTTP 200 com sessão válida e 302 sem sessão
    Teste: curl com cookie válido
    Evidência esperada: HTTP 200 com HTML contendo "Top Produtos"

A2. SQL não usa INTERVAL hardcoded
    Teste: `grep -rn "INTERVAL" output/src/agents/repo.py`
    Evidência esperada: sem resultados

A3. Template não usa |enumerate
    Teste: `grep -n "enumerate" output/src/dashboard/templates/top_produtos.html`
    Evidência esperada: sem resultados

A4. Tool consultar_top_produtos em _TOOLS
    Teste: `python scripts/check_tool_coverage.py`
    Evidência esperada: `capacidade_sem_tool=0 tool_sem_capacidade=0`

A5. Testes unitários passam
    Teste: `pytest -m unit output/src/tests/unit/agents/test_top_produtos.py -v`
    Evidência esperada: 3 passed, 0 failed

A_SMOKE. Smoke gate staging
    Teste: `bash scripts/smoke_sprint_5_teste.sh`
    Evidência esperada: saída ALL OK, exit code 0

## Critérios de aceitação — Média

M1. Cobertura branches novas ≥ 80%
    Teste: `pytest -m unit --cov=output/src --cov-report=term`

## Threshold de Média

Máximo de falhas de Média permitidas: 1

## Fora do escopo deste contrato

Gráfico de barras, filtro por categoria/rep, partial htmx.

## Ambiente de testes

pytest -m unit    → container local (sem infra)
pytest -m staging → mac-lablz com Postgres + Redis reais
