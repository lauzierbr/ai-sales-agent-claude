# Sprint Contract — Sprint 6 — Pre-Pilot Hardening

**Status:** ACEITO — implementação completa (2026-04-21)
**Data:** 2026-04-21

## Entregas comprometidas

1. **E1** — `TenantService.criar_cliente_ficticio(...)` implementado; `POST /dashboard/clientes/novo` funcional com validação de CNPJ, duplicata por tenant e `representante_id` válido.
2. **E2** — `POST /dashboard/precos/upload` usa `CatalogService.processar_excel_precos(...)` e trata `ExcelUploadResult` sem AttributeError; feedback inline de sucesso/erro.
3. **E3** — `/dashboard/top-produtos` com entrada visível na navegação, link de retorno para `/dashboard/home` e filtros `dias`/`limite` preservados.
4. **E4** — `_get_pedidos_recentes` e todas as queries tocadas neste sprint filtram por `tenant_id`; JOINs entre tabelas multi-tenant incluem condição explícita de tenant.
5. **E5** — App falha no startup se qualquer secret crítico estiver ausente; lista todos os ausentes numa mensagem única legível.
6. **E6** — Rate limiting no login: 5 tentativas falhas por IP por 15min → HTTP 429 com mensagem visível.
7. **E7** — Rate limiting no webhook: 30 eventos/min por `instance_id + remoteJid` → HTTP 429; particionado por tenant.
8. **E8** — `/health` expõe componente Anthropic com estados `ok/degraded/fail`; `health_check.py` retorna exit ≠ 0 quando `fail`.
9. **E9** — CORS sem wildcard em staging/production; cookie `dashboard_session` com `Secure=True` apenas em production.
10. **E10** — Testes unitários cobrem todos os fluxos críticos (E1–E9); testes staging cobrem login + 3 fluxos críticos do gestor contra infra real.
11. **E11** — `scripts/smoke_sprint_6.py` e `scripts/seed_homologacao_sprint-6.py` entregues e passando no macmini-lablz.

## Critérios de aceitação — Alta (bloqueantes)

A1. **[B1-CLIENTE-NOVO]** POST /dashboard/clientes/novo cria cliente e redireciona
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k cliente_novo`
    Evidência esperada: 0 falhas; cobre criação válida, CNPJ inválido (<14 dígitos), CNPJ duplicado no mesmo tenant, `representante_id` de outro tenant

A2. **[B2-PRECOS-UPLOAD]** POST /dashboard/precos/upload processa ExcelUploadResult sem AttributeError
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k precos_upload`
    Evidência esperada: 0 falhas; cobre fixture xlsx válida, arquivo ausente e arquivo inválido

A3. **[B3-TOP-PRODUTOS]** GET /dashboard/top-produtos retorna 200 e sem link para rota inexistente
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k top_produtos`
    Evidência esperada: 0 falhas; response HTML não contém `href="/dashboard"` isolado; link "Voltar" aponta para `/dashboard/home`

A4. **[B4-TENANT-ISOLATION]** Queries corrigidas do dashboard não vazam dados entre tenants
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k tenant_isolation`
    Evidência esperada: 0 falhas; testes com 2 tenants; `/dashboard/clientes`, `/dashboard/top-produtos` e fluxos de criação/edição não leem nem alteram registros do tenant vizinho

A5. **[E5-STARTUP]** App não aceita requests quando qualquer secret crítico está ausente
    Teste: `pytest -m unit output/src/tests/unit/providers/test_startup_validation.py`
    Evidência esperada: 0 falhas; teste com múltiplos secrets ausentes → mensagem única lista todos os ausentes; `create_app()` não retorna app saudável
    Variáveis obrigatórias verificadas: `POSTGRES_URL`, `REDIS_URL`, `JWT_SECRET`, `DASHBOARD_SECRET`, `DASHBOARD_TENANT_ID`, `EVOLUTION_API_KEY`, `EVOLUTION_WEBHOOK_SECRET`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

A6. **[E6-RATE-LOGIN]** 6ª tentativa falha de login dentro de 15min retorna 429
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k rate_limit_login`
    Evidência esperada: 0 falhas; 5ª tentativa ainda retorna 401; login correto antes do limite retorna 302; login correto após falhas abaixo do limite reseta contador

A7. **[E7-RATE-WEBHOOK]** 31º evento MESSAGES_UPSERT do mesmo remetente retorna 429
    Teste: `pytest -m unit output/src/tests/unit/agents/test_webhook.py -k rate_limit`
    Evidência esperada: 0 falhas; eventos não-MESSAGES_UPSERT não são contados; payload 429 é JSON estável

A8. **[E8-HEALTH-ANTHROPIC]** /health classifica estado Anthropic como ok/degraded/fail
    Teste: `pytest -m unit output/src/tests/unit/agents/test_anthropic_health.py`
    Evidência esperada: 0 falhas; overload 529/timeout → `degraded`; auth/quota/chave inválida → `fail`; `health_check.py` sai com exit ≠ 0 quando `fail`

A9. **[E9-CORS]** Staging não usa wildcard CORS; cookie Secure=True apenas em production
    Teste: `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k cors_cookie`
    Evidência esperada: 0 falhas; `ENVIRONMENT=development` aceita localhost; `staging` exige `CORS_ALLOWED_ORIGINS` explícito; Set-Cookie tem `Secure=False` em staging

A10. **[G4-SMOKE-UI]** Todas as rotas do dashboard retornam 200 após mudanças do sprint
    Teste: `ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
           infisical run --env=staging -- bash ../scripts/smoke_ui.sh"`
    Evidência esperada: `logs/smoke_ui.log` contém "ALL OK", exit code 0

A_SMOKE. **Smoke gate staging — caminho crítico completo com infra real**
    Teste: `ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
           infisical run --env=staging -- python ../scripts/smoke_sprint_6.py"`
    Evidência esperada: saída "ALL OK", exit code 0
    Nota: obrigatório — sprint toca Runtime e UI.

## Critérios de aceitação — Média (não bloqueantes individualmente)

M1. **[TYPE-HINTS]** type hints em todas as funções públicas novas/modificadas de Service e Repo
    Teste: `mypy --strict output/src/`
    Evidência esperada: 0 erros nos arquivos modificados neste sprint

M2. **[DOCSTRINGS]** docstrings em funções públicas de Service novas/modificadas
    Teste: inspeção manual + pydocstyle
    Evidência esperada: cobertura ≥ 80%

M3. **[COVERAGE-UNIT]** cobertura ≥ 80% das funções de Service novas/modificadas
    Teste: `pytest -m unit --cov=output/src --cov-report=term`
    Evidência esperada: cobertura ≥ 80% em `tenants/service.py` e `catalog/service.py` tocados

M5. **[COMMIT-SERVICE]** Testes unitários de Service verificam session.commit()
    Teste: `grep -rn "commit.assert_called" output/src/tests/unit/`
    Evidência esperada: ao menos 1 match em testes de `TenantService` (E1) e 1 match em testes de `CatalogService` (E2)

M_INJECT. **Injeção de dependências em ui.py sem None após _process_message**
    Teste: `pytest -m staging output/src/tests/staging/agents/test_ui_injection.py`
    Evidência esperada: nenhum atributo crítico de AgentCliente/AgentRep/AgentGestor é None após construção em `_process_message`

## Threshold de Média

Máximo de falhas de Média permitidas: 1 de 5
**Exceção:** M_INJECT falha sozinha → bloqueia independente das outras (injeção None causou bugs históricos no Sprint 2).

## Fora do escopo deste contrato

- Redesenho de auth multi-usuário do dashboard (D023 — adiado)
- Refactor amplo para remover toda SQL da camada UI além das queries tocadas nos blockers
- Hardening genérico de endpoints além de `/dashboard/login` e `/webhook/whatsapp`
- Teste de carga, chaos engineering ou tuning de performance além do smoke gate
- Novas features de produto no dashboard
- Observabilidade Langfuse / spans OTEL filhos (backlog)
- Onboarding de segundo tenant

## Ambiente de testes

pytest -m unit    → roda no container do Evaluator (sem serviços externos)
pytest -m staging → roda no mac-lablz com Postgres + Redis reais, sem WhatsApp real
pytest -m integration → não roda no container; requer mac-lablz com infra completa
