# Sprint Contract — Sprint 1 — Infraestrutura da Aplicação

**Status:** ACEITO
**Data:** 2026-04-14

---

## Entregas comprometidas

1. `output/src/providers/tenant_context.py` — `TenantProvider(BaseHTTPMiddleware)` com cache Redis TTL 60s; rotas excluídas listadas explicitamente
2. `output/src/providers/auth.py` — `create_access_token`, `decode_token`, `get_current_user`, `require_role`; PyJWT + HS256 + bcrypt
3. `output/src/providers/scheduler.py` — `AsyncIOScheduler`; não inicia se `ENVIRONMENT == "test"`
4. `output/src/tenants/types.py` — `Tenant`, `Usuario`, `Role` (enum)
5. `output/src/tenants/config.py` — `TenantConfig`
6. `output/src/tenants/repo.py` — `TenantRepo` + `UsuarioRepo` com `tenant_id` obrigatório em queries
7. `output/src/tenants/service.py` — `TenantService.provision_tenant`
8. `output/src/tenants/ui.py` — `GET /tenants`, `GET /tenants/{id}`, `POST /tenants`
9. `output/src/agents/types.py` — `Mensagem`, `Persona` (enum), `WebhookPayload`
10. `output/src/agents/config.py` — `AgentConfig`, `EvolutionConfig`
11. `output/src/agents/service.py` — `IdentityRouter.resolve` (stub → DESCONHECIDO) + `send_whatsapp_message`
12. `output/src/agents/ui.py` — `POST /webhook/whatsapp` com validação HMAC-SHA256 + `BackgroundTasks`
13. `output/src/agents/runtime/agent_cliente.py` — `AgentCliente.responder`
14. `output/src/agents/runtime/agent_rep.py` — `AgentRep.responder`
15. `output/src/catalog/runtime/scheduler_job.py` — `run_crawl_for_tenant` com Redis SETNX lock
16. `output/src/catalog/ui.py` — atualizado: `POST /catalog/crawl` exige `require_role(["gestor"])`; adiciona `GET /catalog/schedule`, `PUT /catalog/schedule`
17. `output/src/main.py` — atualizado: middleware TenantProvider, lifespan com scheduler, routers tenants e agents
18. `output/alembic/versions/0002_tenants_usuarios.py` — tabelas `tenants` + `usuarios` + seed JMB (condicional se env var presente)
19. `output/alembic/versions/0003_crawl_schedule.py` — tabela `crawl_schedule`
20. `output/alembic/versions/0004_whatsapp_instancias.py` — tabela `whatsapp_instancias`
21. `output/scripts/provision_tenant.py` — CLI argparse para provisionar tenant via `TenantService`
22. Suite de testes unitários para todas as entregas acima (≥ 40 novos testes)
23. `output/src/tests/integration/tenants/test_isolation.py` — testes de isolamento multi-tenant

---

## Critérios de aceitação — Alta (bloqueantes)

**A1. import-linter — zero violações de camadas**
Teste: `lint-imports` na raiz do projeto
Evidência esperada: saída contendo `Kept` para todos os contratos definidos; zero linhas `Broken`

**A2. Sem secrets hardcoded**
Teste:
```bash
grep -r --include="*.py" \
  -E "(password|secret|api_key|apikey)\s*=\s*['\"][^'\"]{4,}" \
  output/src/ \
  --exclude-dir=tests
```
Evidência esperada: saída vazia (zero matches)

**A3. tenant_id obrigatório — verificado via teste unitário dedicado**
Teste: `pytest -m unit -k "test_todo_metodo_repo_tem_tenant_id"`
Evidência esperada: `PASSED`; teste valida via inspeção de assinatura (usando `inspect.signature`) que todos os métodos públicos de `TenantRepo` e `UsuarioRepo` que executam queries recebem `tenant_id: str` como parâmetro posicional ou keyword; zero métodos sem o parâmetro

**A4. pytest -m unit — 100% dos testes passam**
Teste: `pytest -m unit -v`
Evidência esperada: `0 failed, 0 error` — profundidade garantida pelos thresholds de cobertura M4 e M5

**A5. TenantProvider: tenant inválido → HTTP 401**
Teste: `pytest -m unit -k "test_tenant_invalido_retorna_401"`
Evidência esperada: `PASSED`; resposta com status 401 e body `{"detail": "Tenant inválido ou inativo"}`

**A6. TenantProvider: rota excluída passa sem header X-Tenant-ID**
Teste: `pytest -m unit -k "test_rota_excluida_sem_tenant"`
Evidência esperada: `PASSED`; requests para `/health` e `/auth/login` sem header X-Tenant-ID retornam 200/422 (nunca 401 do middleware)

**A7. Auth: token expirado → HTTP 401**
Teste: `pytest -m unit -k "test_token_expirado_retorna_401"`
Evidência esperada: `PASSED`; token com `exp` no passado retorna 401

**A8. Auth: role insuficiente → HTTP 403**
Teste: `pytest -m unit -k "test_role_insuficiente_retorna_403"`
Evidência esperada: `PASSED`; token com role `cliente` em endpoint `require_role(["gestor"])` retorna 403

**A9. POST /catalog/crawl exige JWT de gestor**
Teste: `pytest -m unit -k "test_crawl_sem_jwt_retorna_401 or test_crawl_role_cliente_retorna_403"`
Evidência esperada: ambos `PASSED`

**A10. Webhook: assinatura HMAC inválida → HTTP 403**
Teste: `pytest -m unit -k "test_webhook_assinatura_invalida_retorna_403"`
Evidência esperada: `PASSED`; header `X-Evolution-Signature` com valor incorreto retorna 403

**A11. Webhook: header ausente → HTTP 403**
Teste: `pytest -m unit -k "test_webhook_sem_header_retorna_403"`
Evidência esperada: `PASSED`

**A12. Webhook: assinatura válida → HTTP 200 imediato**
Teste: `pytest -m unit -k "test_webhook_valido_retorna_200"`
Evidência esperada: `PASSED`; resposta `{"status": "received"}` com status 200; processamento em BackgroundTask (não bloqueia resposta)

**A13. Scheduler não inicia com ENVIRONMENT=test**
Teste: `pytest -m unit -k "test_scheduler_nao_inicia_em_test"`
Evidência esperada: `PASSED`; `AsyncIOScheduler.start` nunca chamado quando `ENVIRONMENT == "test"`

**A14. Sem print() em output/src/**
Teste:
```bash
grep -r --include="*.py" "print(" output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A15. Isolamento multi-tenant — dois níveis de verificação**
Teste 1: `pytest -m unit -k "test_isolamento"` — lógica de isolamento via mock
Evidência: `PASSED`; mock de `CatalogRepo` confirma que query com `tenant_id="TESTE"` não retorna dado inserido com `tenant_id="JMB"`

Teste 2:
```bash
grep -c "@pytest.mark.integration" \
  output/src/tests/integration/tenants/test_isolation.py
```
Evidência: retorna `2` ou mais (arquivo existe e tem ≥ 2 testes de integração marcados corretamente)

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

**M1. mypy --strict sem erros**
Teste: `mypy --strict output/src/`
Evidência esperada: `Found 0 errors`

**M2. OTel spans em funções de Service e scheduler_job**
Teste: inspeção manual de `tenants/service.py`, `agents/service.py`, `catalog/runtime/scheduler_job.py`
Evidência esperada: toda função pública de Service tem `tracer.start_as_current_span(...)` com atributo `tenant_id`; scheduler_job tem span `crawler_scheduled_run`

**M3. structlog com from_number_hash (SHA256) no webhook**
Teste: inspeção manual de `agents/ui.py`
Evidência esperada: log `webhook_recebido` contém campo `from_number_hash` (SHA256 do número de telefone) e NÃO contém o número em plaintext; todos os eventos do scheduler logados via structlog

**M4. Cobertura ≥ 80% em providers/auth.py e agents/service.py**
Teste: `pytest -m unit --cov=output/src/providers/auth --cov=output/src/agents/service --cov-report=term-missing`
Evidência esperada: ambos os módulos com linha `TOTAL` ≥ 80%

**M5. Cobertura ≥ 60% em tenants/repo.py e providers/tenant_context.py**
Teste: `pytest -m unit --cov=output/src/tenants/repo --cov=output/src/providers/tenant_context --cov-report=term-missing`
Evidência esperada: ambos com `TOTAL` ≥ 60%

**M6. Docstrings em todas as funções públicas de Service e Repo**
Teste: inspeção manual de `tenants/service.py`, `tenants/repo.py`, `agents/service.py`
Evidência esperada: toda função pública tem docstring de ao menos uma linha

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 6**

Se 2 ou mais critérios de Média falharem, o sprint é reprovado mesmo com todos os de Alta passando.

---

## Fora do escopo deste contrato

O Evaluator **não** testa neste sprint:
- AgentCliente com Claude SDK real (stub de resposta fixa é o comportamento correto em Sprint 1)
- Execução real do crawler pelo scheduler (lógica testada via mock)
- Envio real de mensagem via Evolution API (100% mockado nos testes unit)
- Lookup real de `representantes` e `clientes_b2b` (IdentityRouter retorna DESCONHECIDO — correto para Sprint 1)
- Refresh token JWT
- Rate limiting Redis por tenant
- HTTPS/TLS
- Migração de dados do Sprint 0

---

## Ambiente de testes

```
pytest -m unit        → roda no container do Evaluator (zero I/O externo)
                        PostgreSQL, Redis, Evolution API: todos mockados
                        Requerido: 100% pass, 0 falhas

pytest -m integration → NÃO roda no container do Evaluator
                        Requer mac-lablz com PostgreSQL + Redis ativos
                        Validado manualmente após aprovação do Evaluator

pytest -m slow        → nunca roda no loop automático
```

**Regra crítica:** teste marcado como `unit` que realizar conexão TCP, acesso a arquivo fora de `/tmp` ou chamada HTTP real é tratado como **falha de Alta**, independentemente do resultado.

---

## Notas de implementação (binding para o Generator)

1. **Ordem de implementação:** E1 → E2 → E3 → E4 → E7 → E5 → E6
2. **Seed JMB na migration 0002:** lê `GESTOR_PASSWORD_JMB` de `os.getenv`; se ausente, pula seed com `structlog.warning` (não falha a migration)
3. **Cache Redis no TenantProvider:** chave `tenant:{tenant_id}`, TTL 60s, JSON; se Redis indisponível → fallback direto no DB sem erro
4. **bcrypt rounds:** produção `rounds=12`; testes unit injetam `rounds=4` via parâmetro de `create_access_token`
5. **APScheduler + uvicorn --reload:** `scheduler.start()` apenas dentro de `lifespan`; condicionado a `ENVIRONMENT != "test"`
6. **IdentityRouter interface:** `async def resolve(self, mensagem: Mensagem, tenant_id: str, session: AsyncSession) -> Persona`
