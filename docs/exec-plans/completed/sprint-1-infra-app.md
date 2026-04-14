# Plano de Execução — Sprint 1 — Infraestrutura da Aplicação

**Status:** 🔄 Em planejamento
**Data início:** 2026-04-14
**Spec:** `artifacts/spec.md`
**Contrato:** `artifacts/sprint_contract.md` (a gerar)
**QA:** `artifacts/qa_sprint_1.md` (a gerar)

---

## Objetivo

Middleware multi-tenant, auth JWT, scheduler de crawl, webhook WhatsApp com identity router, resposta básica por persona e provisionamento de segundo tenant — plataforma pronta para Sprint 2 (agente cliente completo).

---

## Checklist de Deliverables

### E1 — TenantProvider middleware

**Providers**
- [ ] `output/src/providers/tenant_context.py` — `TenantProvider(BaseHTTPMiddleware)` com cache Redis TTL 60s

**Tenants (parcial — apenas o necessário para E1)**
- [ ] `output/src/tenants/types.py` — `Tenant` model, `Role` enum
- [ ] `output/src/tenants/config.py` — `TenantConfig`
- [ ] `output/src/tenants/repo.py` — `TenantRepo.get_by_id`, `TenantRepo.get_active_tenants`

**App**
- [ ] `output/src/main.py` — middleware registrado; rotas excluídas: `/health`, `/docs`, `/openapi.json`, `/redoc`, `/auth/login`, `/webhook/whatsapp`

**Testes**
- [ ] `output/src/tests/unit/providers/test_tenant_context.py` — tenant válido, inválido, rota excluída

---

### E2 — Auth JWT

**Providers**
- [ ] `output/src/providers/auth.py` — `create_access_token`, `decode_token`, `get_current_user`, `require_role`

**Tenants (complemento)**
- [ ] `output/src/tenants/types.py` — adiciona `Usuario` model

**Alembic**
- [ ] `output/alembic/versions/0002_tenants_usuarios.py` — tabelas `tenants` + `usuarios` + seed JMB

**Catalog (atualização)**
- [ ] `output/src/catalog/ui.py` — `POST /catalog/crawl` passa a exigir `require_role(["gestor"])`

**Testes**
- [ ] `output/src/tests/unit/providers/test_auth.py` — todos os casos de auth

---

### E3 — Domínio Tenants (completo)

- [ ] `output/src/tenants/types.py` — completo (Tenant, Usuario, Role)
- [ ] `output/src/tenants/config.py` — completo
- [ ] `output/src/tenants/repo.py` — `TenantRepo` + `UsuarioRepo` completos
- [ ] `output/src/tenants/service.py` — `TenantService.provision_tenant`
- [ ] `output/src/tenants/ui.py` — `GET /tenants`, `GET /tenants/{id}`, `POST /tenants`
- [ ] `output/src/main.py` — inclui router tenants

**Testes**
- [ ] `output/src/tests/unit/tenants/test_types.py`
- [ ] `output/src/tests/unit/tenants/test_repo.py`
- [ ] `output/src/tests/unit/tenants/test_service.py`
- [ ] `output/src/tests/unit/tenants/test_ui.py`

---

### E4 — Scheduler de crawl

**Providers**
- [ ] `output/src/providers/scheduler.py` — `AsyncIOScheduler`; não inicia se `ENVIRONMENT == "test"`

**Catalog**
- [ ] `output/src/catalog/runtime/scheduler_job.py` — `run_crawl_for_tenant(tenant_id)` com Redis lock
- [ ] `output/src/catalog/config.py` — `CrawlScheduleConfig` (cron_expression, default)
- [ ] `output/src/catalog/ui.py` — `GET /catalog/schedule`, `PUT /catalog/schedule`

**Alembic**
- [ ] `output/alembic/versions/0003_crawl_schedule.py` — tabela `crawl_schedule`

**App**
- [ ] `output/src/main.py` — `lifespan` com scheduler startup/shutdown

**Testes**
- [ ] `output/src/tests/unit/catalog/test_scheduler_job.py` — lock obtido, lock existente, cron inválido

---

### E5 — Webhook Evolution API → Identity Router

**Agents**
- [ ] `output/src/agents/types.py` — `Mensagem`, `Persona` enum, `WebhookPayload`
- [ ] `output/src/agents/config.py` — `AgentConfig`, `EvolutionConfig`
- [ ] `output/src/agents/service.py` — `IdentityRouter.resolve` (stub → DESCONHECIDO)
- [ ] `output/src/agents/ui.py` — `POST /webhook/whatsapp` com validação HMAC + BackgroundTasks

**Alembic**
- [ ] `output/alembic/versions/0004_whatsapp_instancias.py` — tabela `whatsapp_instancias`

**App**
- [ ] `output/src/main.py` — inclui router agents

**Testes**
- [ ] `output/src/tests/unit/agents/test_webhook.py` — assinatura válida/inválida, header ausente
- [ ] `output/src/tests/unit/agents/test_identity_router.py`

---

### E6 — Resposta básica WhatsApp por persona

**Agents Runtime**
- [ ] `output/src/agents/runtime/__init__.py`
- [ ] `output/src/agents/runtime/agent_cliente.py` — `AgentCliente.responder`
- [ ] `output/src/agents/runtime/agent_rep.py` — `AgentRep.responder`

**Agents Service (atualização)**
- [ ] `output/src/agents/service.py` — `send_whatsapp_message` via httpx

**Testes**
- [ ] `output/src/tests/unit/agents/test_agent_cliente.py`
- [ ] `output/src/tests/unit/agents/test_agent_rep.py`

---

### E7 — Onboarding segundo tenant

**Scripts**
- [ ] `output/scripts/provision_tenant.py` — CLI com argparse; usa `TenantService.provision_tenant`

**Testes de isolamento**
- [ ] `output/src/tests/integration/tenants/__init__.py`
- [ ] `output/src/tests/integration/tenants/test_isolation.py` — isolamento catálogo + isolamento auth

---

### Infraestrutura de testes (novos diretórios)

- [ ] `output/src/tests/unit/providers/__init__.py`
- [ ] `output/src/tests/unit/tenants/__init__.py`
- [ ] `output/src/tests/unit/agents/__init__.py`
- [ ] `output/src/tests/integration/tenants/__init__.py`

---

## Ordem de implementação recomendada ao Generator

```
E1 (middleware base) →
E2 (auth JWT) →
E3 (domínio tenants completo) →
E4 (scheduler) →
E7 (provision + tests isolamento) →
E5 (webhook + identity router) →
E6 (resposta básica agentes)
```

Justificativa: E1 e E2 são dependências de tudo. E3 completa o domínio que E1+E2 iniciaram. E4 depende de tenants (schedule vinculado a tenant_id). E7 valida o isolamento antes de expor o canal WhatsApp. E5+E6 são os menos críticos para infra core e mais dependentes de infra externa (Evolution API).

---

## ADRs que governam este sprint

| ADR | Decisão |
|-----|---------|
| D019 | Scheduler: APScheduler 3.x AsyncIOScheduler (embedded) |
| D020 | Multi-tenant: tabela compartilhada + tenant_id para todos os domínios |
| D021 | JWT: PyJWT + HS256, access token 8h, sem refresh |
| D022 | Auth scope: TenantProvider (X-Tenant-ID), JWT (privilegiados), HMAC (webhook) |

---

## Critérios de aprovação do Evaluator

### Alta prioridade (bloqueantes)

| ID | Check | Comando / Método |
|----|-------|-----------------|
| A1 | lint-imports sem violações | `lint-imports` |
| A2 | Sem secrets hardcoded | `grep -r "sk-\|password\|secret" output/src/ --include="*.py"` (excluindo tests/) |
| A3 | tenant_id obrigatório em todas as queries | revisão manual de todos os métodos de Repo |
| A4 | pytest unit passa 100% | `pytest -m unit -v` |
| A5 | TenantProvider: tenant inválido → 401 | `test_tenant_invalido_retorna_401` |
| A6 | Auth: token expirado → 401 | `test_token_expirado_retorna_401` |
| A7 | Webhook: assinatura inválida → 403 | `test_assinatura_invalida_retorna_403` |
| A8 | Sem print() | `grep -r "print(" output/src/ --include="*.py"` |
| A9 | mypy --strict sem erros | `mypy --strict output/src/` |
| A10 | Isolamento: dados JMB não vazam para outro tenant | `pytest -m integration tests/integration/tenants/test_isolation.py` |

### Média prioridade (não bloqueantes isolados, bloqueantes em conjunto)

| ID | Check | Método |
|----|-------|--------|
| M1 | OTel spans em todos os jobs do scheduler | revisão manual de scheduler_job.py |
| M2 | structlog em webhook (número hasheado) | revisão manual de agents/ui.py |
| M3 | Cobertura ≥ 80% em providers/auth.py | `pytest --cov=src/providers/auth` |
| M4 | Seed JMB funcional (migration 0002) | `alembic upgrade head && psql -c "SELECT * FROM tenants"` |
| M5 | APScheduler não inicia em ENVIRONMENT=test | revisão manual de providers/scheduler.py |

---

## Secrets a criar no Infisical (ação manual — usuário)

```bash
# Antes de rodar o Generator:
infisical secrets set JWT_SECRET="$(openssl rand -hex 32)" --env=dev
infisical secrets set JWT_SECRET="$(openssl rand -hex 32)" --env=staging
infisical secrets set EVOLUTION_WEBHOOK_SECRET="$(openssl rand -hex 32)" --env=dev
infisical secrets set EVOLUTION_WEBHOOK_SECRET="$(openssl rand -hex 32)" --env=staging
infisical secrets set GESTOR_PASSWORD_JMB="sua_senha_aqui" --env=dev
infisical secrets set GESTOR_PASSWORD_JMB="sua_senha_aqui" --env=staging
```

---

## Dependências Python a adicionar (pyproject.toml)

| Pacote | Versão mínima | Motivo |
|--------|--------------|--------|
| `PyJWT` | `2.8+` | JWT auth |
| `bcrypt` | `4.0+` | Hash de senha |
| `apscheduler` | `3.10+` | Scheduler de crawl |
| `python-multipart` | já existe | (já adicionado em Sprint 0) |

---

## Log de decisões tomadas durante execução

_(preenchido pelo Generator durante Sprint 1)_

| Data | Decisão | Motivo |
|------|---------|--------|
| — | — | — |

---

## Log de execução

### 2026-04-14 — Planner

- ✅ `artifacts/spec.md` gerado (Sprint 1)
- ✅ ADRs D019–D022 registrados em `docs/design-docs/index.md`
- ✅ `docs/PLANS.md` atualizado → Sprint 1 🔄
- ✅ Este arquivo criado
- ⏳ Aguardando aprovação do spec pelo usuário

### Generator Fase 1 — (a executar)

### Evaluator Fase 1 — (a executar)

### Generator Fase 2 — (a executar)

### Evaluator Fase 2 — (a executar)
