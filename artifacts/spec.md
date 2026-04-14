# Sprint 1 — Infraestrutura da Aplicação

**Status:** Em planejamento
**Data:** 2026-04-14
**Pré-requisitos:** Sprint 0 concluído — catálogo com crawler httpx + pgvector operacional; Infra-Dev e Infra-Staging concluídos

---

## Objetivo

Ao final deste sprint, a aplicação tem middleware multi-tenant funcional, autenticação JWT para gestores, scheduler de crawl configurável por tenant, webhook WhatsApp com roteamento de persona, resposta básica de agente e infraestrutura de provisionamento de novos tenants — a plataforma está pronta para receber um segundo tenant sem intervenção manual em código.

---

## Contexto

Sprint 0 entregou o pipeline de catálogo isolado. A aplicação ainda não tem: (1) middleware que identifica o tenant em cada request, (2) autenticação para ações privilegiadas, (3) agendamento automático de crawl, (4) canal WhatsApp funcional, (5) domínio de tenants com provisionamento. Sem esses pilares, qualquer feature de Sprint 2+ (agente cliente, pedidos) não tem onde se apoiar.

O sprint segue o roadmap de `docs/PLANS.md` Sprint 1, com adição explícita de scheduler de crawl (D018 postergou para cá) e infraestrutura de onboarding do segundo tenant.

ADRs que governam este sprint: D019, D020, D021, D022 (ver `docs/design-docs/index.md`).

---

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| providers | Types, Config, Runtime (auth.py, tenant_context.py, scheduler.py) |
| tenants | Types, Config, Repo, Service, UI |
| agents | Types, Config, Service, Runtime, UI |
| catalog | Runtime (scheduler_job.py), UI (schedule endpoints) |
| alembic | Migrations 0002, 0003 (+ 0004 se necessário) |
| scripts | scripts/provision_tenant.py |

---

## Considerações multi-tenant

Decisão D020: tabela compartilhada + `tenant_id TEXT NOT NULL` para todos os domínios deste sprint. Nenhum schema por tenant será criado.

O TenantProvider middleware é o gatekeeper central: extrai `X-Tenant-ID` do header, valida existência e status ativo no DB, injeta `request.state.tenant_id: str` e `request.state.tenant: Tenant` antes de qualquer handler. Endpoints sem tenant (health, docs, auth/login, webhook) são explicitamente excluídos do middleware.

O webhook WhatsApp resolve `tenant_id` a partir do campo `instancia_id` do payload Evolution API, via lookup na tabela `whatsapp_instancias`. Esse lookup ocorre dentro do handler (o webhook não carrega X-Tenant-ID — a instância IS o tenant identifier).

Testes de isolamento são critério obrigatório: dados do tenant JMB não podem aparecer em queries com tenant_id de outro tenant.

---

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| `JWT_SECRET` | development | Chave HMAC HS256 (≥256 bits, hex aleatório) para assinar tokens JWT |
| `JWT_SECRET` | staging | Idem, valor diferente do dev |
| `EVOLUTION_WEBHOOK_SECRET` | development | Segredo HMAC-SHA256 para validar requests do webhook Evolution API |
| `EVOLUTION_WEBHOOK_SECRET` | staging | Idem |
| `GESTOR_PASSWORD_JMB` | development | Senha plaintext do gestor JMB (apenas para seed; não usada em runtime) |
| `GESTOR_PASSWORD_JMB` | staging | Idem |

> Nota: `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_NAME` já devem existir do Sprint Infra-Dev.

---

## Entregas

### E1 — TenantProvider middleware

**Camadas:** Types, Config, Repo (providers + tenants), Runtime (FastAPI middleware)
**Arquivos:**
- `output/src/providers/tenant_context.py` (novo, substitui stub)
- `output/src/tenants/types.py` (novo)
- `output/src/tenants/config.py` (novo)
- `output/src/tenants/repo.py` (novo — TenantRepo.get_by_id + get_active)
- `output/src/main.py` (atualização — adiciona middleware)

**Critérios de aceitação:**
- [ ] `TenantProvider` é um `BaseHTTPMiddleware` FastAPI registrado em `main.py`
- [ ] Extrai `X-Tenant-ID` do header de cada request
- [ ] Faz lookup em tabela `tenants` (DB) e verifica `ativo == True`
- [ ] Injeta `request.state.tenant_id: str` e `request.state.tenant: Tenant` no request
- [ ] Retorna `HTTP 401 {"detail": "Tenant inválido ou inativo"}` se tenant não encontrado ou inativo
- [ ] Rotas excluídas do middleware: `/health`, `/docs`, `/openapi.json`, `/redoc`, `/auth/login`, `/webhook/whatsapp`
- [ ] Cache Redis do tenant com TTL 60s para evitar lookup a cada request
- [ ] `lint-imports` passa sem violações
- [ ] `pytest -m unit` cobre: tenant válido → injeta; inválido → 401; rota excluída → passa sem header

---

### E2 — Auth JWT (gestor)

**Camadas:** Types, Config, Service, UI (providers/auth.py)
**Arquivos:**
- `output/src/providers/auth.py` (novo)
- `output/src/tenants/types.py` (adiciona modelo `Usuario` e enum `Role`)
- `output/alembic/versions/0002_tenants_usuarios.py` (novo)

**Critérios de aceitação:**
- [ ] Migration 0002 cria tabelas `tenants` e `usuarios` no schema `public`
  - `tenants(id TEXT PK, nome TEXT NOT NULL, cnpj TEXT UNIQUE NOT NULL, ativo BOOL NOT NULL DEFAULT true, whatsapp_number TEXT, config_json JSONB NOT NULL DEFAULT '{}', criado_em TIMESTAMPTZ NOT NULL DEFAULT now())`
  - `usuarios(id TEXT PK, tenant_id TEXT NOT NULL REFERENCES tenants(id), cnpj TEXT NOT NULL, senha_hash TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('gestor','rep','cliente')), ativo BOOL NOT NULL DEFAULT true, criado_em TIMESTAMPTZ NOT NULL DEFAULT now())`
  - Índice único em `usuarios(cnpj, tenant_id)`
- [ ] Seed em migration 0002: tenant JMB + usuário gestor JMB com `bcrypt(GESTOR_PASSWORD_JMB)` lido de variável de ambiente
- [ ] `POST /auth/login` recebe `{"cnpj": "...", "senha": "..."}` (body JSON), retorna `{"access_token": "...", "token_type": "bearer"}`
- [ ] Token JWT contém claims: `sub` (user_id), `tenant_id`, `role`, `exp` (agora + 8h), `iat`
- [ ] Senha verificada com `bcrypt.checkpw`; nunca plaintext em DB ou log
- [ ] `providers/auth.py` exporta: `create_access_token()`, `decode_token()`, `get_current_user` (FastAPI Depends), `require_role(roles)` (dependency factory)
- [ ] `get_current_user` retorna `HTTP 401` se token ausente, inválido ou expirado
- [ ] `require_role(["gestor"])` retorna `HTTP 403` se role não está na lista
- [ ] `POST /catalog/crawl` passa a exigir `Depends(require_role(["gestor"]))` — atualização em `catalog/ui.py`
- [ ] `pytest -m unit` cobre: login correto → token; cnpj errado → 401; senha errada → 401; token expirado → 401; role insuficiente → 403
- [ ] Cobertura ≥ 80% das funções de `providers/auth.py`

---

### E3 — Domínio Tenants (completo)

**Camadas:** Types, Config, Repo, Service, UI
**Arquivos:**
- `output/src/tenants/types.py` (completo)
- `output/src/tenants/config.py` (novo)
- `output/src/tenants/repo.py` (completo — TenantRepo + UsuarioRepo)
- `output/src/tenants/service.py` (novo)
- `output/src/tenants/ui.py` (novo)
- `output/src/main.py` (atualização — inclui router tenants)

**Critérios de aceitação:**
- [ ] `Tenant` Pydantic model: `id, nome, cnpj, ativo, whatsapp_number, config_json: dict, criado_em`
- [ ] `Usuario` Pydantic model: `id, tenant_id, cnpj, senha_hash, role: Role, ativo, criado_em`
- [ ] `Role` enum: `gestor`, `rep`, `cliente`
- [ ] `TenantRepo.get_by_id(tenant_id, session) → Tenant | None`
- [ ] `TenantRepo.get_active_tenants(session) → list[Tenant]`
- [ ] `TenantRepo.create(tenant, session) → Tenant`
- [ ] `UsuarioRepo.get_by_cnpj(cnpj, tenant_id, session) → Usuario | None`
- [ ] `UsuarioRepo.create(usuario, session) → Usuario`
- [ ] `TenantService.provision_tenant(nome, cnpj, gestor_cnpj, gestor_senha_hash, session) → Tenant` — cria tenant + usuário gestor em transação única
- [ ] `GET /tenants` — lista tenants ativos (sem auth — endpoint interno)
- [ ] `GET /tenants/{tenant_id}` — retorna tenant ou 404
- [ ] `POST /tenants` — body `{nome, cnpj, gestor_cnpj, gestor_senha}`, cria via provision_tenant, retorna Tenant
- [ ] Todos os métodos de Repo com parâmetro `tenant_id` obrigatório onde aplicável
- [ ] `lint-imports` passa: Repo não importa Service; Service não importa UI
- [ ] `pytest -m unit` cobre TenantRepo e TenantService com mocks; cobertura ≥ 80%

---

### E4 — Scheduler de crawl

**Camadas:** Config, Service, Runtime (catalog + providers)
**Arquivos:**
- `output/src/providers/scheduler.py` (novo)
- `output/src/catalog/runtime/scheduler_job.py` (novo)
- `output/alembic/versions/0003_crawl_schedule.py` (novo)
- `output/src/catalog/config.py` (atualização — CrawlScheduleConfig)
- `output/src/catalog/ui.py` (atualização — endpoints /catalog/schedule)
- `output/src/main.py` (atualização — lifespan com scheduler)

**Critérios de aceitação:**
- [ ] Migration 0003 cria tabela `crawl_schedule`:
  - `(id TEXT PK, tenant_id TEXT NOT NULL UNIQUE REFERENCES tenants(id), cron_expression TEXT NOT NULL DEFAULT '0 2 1 * *', enabled BOOL NOT NULL DEFAULT true, last_run_at TIMESTAMPTZ, next_run_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now())`
- [ ] `providers/scheduler.py` inicializa `AsyncIOScheduler` com `asyncio` executor; não inicia se `ENVIRONMENT == "test"`
- [ ] Startup FastAPI via `lifespan`: lê `crawl_schedule` do DB, adiciona job por tenant com `enabled=True`
- [ ] `scheduler_job.run_crawl_for_tenant(tenant_id)`: tenta Redis SETNX `crawl_lock:{tenant_id}` TTL 3600s; se obtém lock → executa crawl → libera lock; se não obtém → loga skip
- [ ] Default cron `0 2 1 * *` (02h00 do dia 1 de cada mês)
- [ ] `GET /catalog/schedule` — lista schedules do tenant extraído do `request.state.tenant_id` (requer `Depends(require_role(["gestor"]))`)
- [ ] `PUT /catalog/schedule` — recebe `{cron_expression: str, enabled: bool}`, valida sintaxe cron (apscheduler CronTrigger.from_crontab), retorna 422 se inválido; requer JWT gestor
- [ ] OTel span `crawler_scheduled_run` com atributos `tenant_id`, `triggered_by: "scheduler"`
- [ ] Métricas OTel: `crawler_job_started_total{tenant_id}`, `crawler_job_completed_total{tenant_id}`, `crawler_job_failed_total{tenant_id}`
- [ ] `structlog` em: job iniciado, lock obtido, lock já existe (skip), job concluído, job falhou
- [ ] `pytest -m unit` cobre: lock obtido → executa; lock existente → skip; cron inválido → 422
- [ ] APScheduler não inicia se `ENVIRONMENT == "test"` (variável de ambiente)

---

### E5 — Webhook Evolution API → Identity Router

**Camadas:** Types, Config, Service, UI (agents)
**Arquivos:**
- `output/src/agents/types.py` (novo)
- `output/src/agents/config.py` (novo)
- `output/src/agents/service.py` (novo — IdentityRouter)
- `output/src/agents/ui.py` (novo — webhook endpoint)
- `output/alembic/versions/0004_whatsapp_instancias.py` (novo, se não couber em 0003)
- `output/src/main.py` (atualização — inclui router agents)

**Critérios de aceitação:**
- [ ] Tabela `whatsapp_instancias`: `(instancia_id TEXT PK, tenant_id TEXT NOT NULL REFERENCES tenants(id), numero_whatsapp TEXT NOT NULL, ativo BOOL NOT NULL DEFAULT true)`
- [ ] `Mensagem` Pydantic model: `id: str, de: str, para: str, texto: str, tipo: str, instancia_id: str, timestamp: datetime`
- [ ] `Persona` enum: `CLIENTE_B2B`, `REPRESENTANTE`, `DESCONHECIDO`
- [ ] `POST /webhook/whatsapp` — aceita payload JSON da Evolution API
- [ ] Valida assinatura: `hmac.compare_digest(HMAC-SHA256(body_bytes, secret), header_value)`; retorna `HTTP 403` se inválido ou header ausente
- [ ] Retorna `HTTP 200 {"status": "received"}` imediatamente; processamento via `BackgroundTasks`
- [ ] `IdentityRouter.resolve(mensagem, tenant_id, session) → Persona`:
  - Stub Sprint 1: sempre retorna `DESCONHECIDO` (lookup real em Sprint 2 quando tabelas existirem)
  - Interface definida para facilitar substituição em Sprint 2
- [ ] `structlog`: `webhook_recebido{tenant_id, persona, from_number_hash}` — número hasheado SHA256 (LGPD)
- [ ] `pytest -m unit` cobre: assinatura válida → 200; assinatura inválida → 403; header ausente → 403
- [ ] Cobertura ≥ 80% do handler webhook

---

### E6 — Resposta básica WhatsApp por persona

**Camadas:** Service, Runtime, UI (agents)
**Arquivos:**
- `output/src/agents/runtime/agent_cliente.py` (novo)
- `output/src/agents/runtime/agent_rep.py` (novo)
- `output/src/agents/service.py` (atualização — send_whatsapp_message)

**Critérios de aceitação:**
- [ ] `send_whatsapp_message(instancia_id, numero, texto, session) → None` → POST `{EVOLUTION_API_URL}/message/sendText/{instancia_id}` com header `apikey: {EVOLUTION_API_KEY}`; usa `httpx.AsyncClient`
- [ ] `AgentCliente.responder(mensagem, tenant, session)` → envia: `"Olá! Sou o assistente da {tenant.nome}. Como posso ajudar? Consulte produtos, verifique pedidos ou fale com um atendente."`
- [ ] `AgentRep.responder(mensagem, tenant, session)` → envia: `"Olá! Use este canal para consultar catálogo, registrar pedidos da sua carteira ou verificar metas."`
- [ ] `Persona.DESCONHECIDO` → envia: `"Olá! Para atendimento, entre em contato pelo WhatsApp {tenant.whatsapp_number or 'da distribuidora'}."`
- [ ] Falha na Evolution API (status != 2xx) → `structlog.error("evolution_api_erro", status_code=..., tenant_id=...)` + exceção não propagada (background task não crasha)
- [ ] OTel span `agent_response` com atributos: `tenant_id`, `persona`
- [ ] Métricas: contador `whatsapp_mensagens_enviadas_total{tenant_id, persona}`
- [ ] `pytest -m unit` cobre cada persona com mock httpx; cobertura ≥ 80%

---

### E7 — Onboarding segundo tenant (infraestrutura + validação de isolamento)

**Camadas:** Service, scripts, tests
**Arquivos:**
- `output/scripts/provision_tenant.py` (novo)
- `output/src/tests/integration/tenants/test_isolation.py` (novo)

**Critérios de aceitação:**
- [ ] `python scripts/provision_tenant.py --nome "Distribuidora Teste" --cnpj "00.000.000/0001-00" --gestor-cnpj "000.000.000-00" --gestor-senha "senha123"` cria tenant + usuário gestor via `TenantService.provision_tenant`
- [ ] Script inicia DB session via `providers/db.py`; não hardcoda URL — usa `POSTGRES_URL` injetada via `infisical run`
- [ ] Seed do JMB já existente via migration 0002 (não requer script)
- [ ] Teste de isolamento de catálogo (`@pytest.mark.integration`):
  - Cria tenant JMB + tenant TESTE no DB de teste
  - Insere produto com `tenant_id="JMB"`
  - `CatalogRepo.listar_produtos(tenant_id="TESTE", session)` → retorna lista vazia
  - `CatalogRepo.listar_produtos(tenant_id="JMB", session)` → retorna o produto inserido
- [ ] Teste de isolamento de auth:
  - Gestor JMB não pode autenticar com tenant_id TESTE (mesmo que o CNPJ seja igual — lookups filtram por tenant_id)
- [ ] `pytest -m integration` passa para `test_isolation.py`

---

## Decisões pendentes

Nenhuma. ADRs D019–D022 aprovados e documentados em `docs/design-docs/index.md` antes da geração deste spec.

---

## Fora do escopo

- Refresh token JWT
- Autenticação dos clientes WhatsApp (identificados apenas pelo número de telefone)
- Migração das tabelas de `catalog` para schemas por tenant (mantém D017)
- Schema por tenant para qualquer domínio (mantém D020)
- AgentCliente completo com Claude SDK e memória (Sprint 2)
- ConversaRepo / histórico de mensagens (Sprint 2)
- Tabelas `representantes` e `clientes_b2b` — E5 usa stub `DESCONHECIDO`
- Preços diferenciados por cliente (Sprint 2)
- Rate limiting por tenant via Redis (sprint futuro)
- HTTPS/TLS (staging tem HTTP; TLS em sprint de hardening)
- Platform admin role (Lauzier opera via script, não endpoint)
- Segundo tenant real com cliente definido (cliente não identificado ainda)
- Painel web do gestor (Sprint 4)
- Retry automático na Evolution API (Sprint 2)

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Sprint grande (7 entregas, ~22 arquivos novos) | Alta | Médio | Prioridade E1→E2→E3→E4→E7→E5→E6; Evaluator pode aprovar E1-E5+E7 e postergar E6 para Sprint 1b |
| APScheduler duplicando jobs com `uvicorn --reload` | Média | Médio | `scheduler.start()` condicionado a `not settings.debug` ou APScheduler `jobstore` com ID único |
| Evolution API indisponível em dev (sem instância configurada) | Alta | Baixo | E5+E6 100% unit com mocks; teste real apenas em staging com instância ativa |
| `bcrypt` lento em testes (rounds=12 por padrão) | Média | Baixo | Fixture de teste usa `rounds=4`; produção usa `rounds=12` |
| Middleware TenantProvider com latência de DB por request | Baixa | Médio | Cache Redis do tenant com TTL 60s (especificado em E1) |

---

## Handoff para o próximo sprint

Sprint 2 (Agente cliente completo) encontrará:
- **TenantProvider** funcional → qualquer novo endpoint tem tenant no contexto sem código adicional
- **Auth JWT** operacional → `require_role(["gestor"])` pronto para endpoints do painel
- **whatsapp_instancias** populada → webhook resolve tenant por instância automaticamente
- **IdentityRouter** com interface definida → Sprint 2 implementa lookup real em `representantes` + `clientes_b2b`
- **Scheduler** ativo → Sprint 2 ajusta cadência por tenant sem mudança de código
- **send_whatsapp_message** funcional → Sprint 2 usa para respostas reais do AgentCliente
- **provision_tenant** script → operações de onboarding sem intervenção em código
