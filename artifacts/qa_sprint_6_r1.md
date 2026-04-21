# QA Report — Sprint 6 — Pre-Pilot Hardening — REPROVADO

**Data:** 2026-04-21
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**REPROVADO — rodada 1 de 1**

Você tem uma rodada de correção. Se reprovar novamente, o sprint será escalado para o usuário.

**Motivo resumido:** M_INJECT bloqueou independentemente do threshold (arquivo `test_ui_injection.py` inexistente — exceção obrigatória per contrato). Threshold de Média também excedido: 4 falhas de 5 critérios (M1, M3, M5, M_INJECT) contra máximo de 1.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded (sk-ant) | `grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/` | PASS — 0 resultados |
| Passwords hardcoded | `grep -rn "password\s*=\s*['\"][^{]" output/src/` | PASS — 0 resultados |
| print() proibido | `grep -rn "print(" output/src/` (excl. testes) | PASS — 0 resultados em produção |
| import-linter | `.venv/bin/lint-imports` (PYTHONPATH=output) | PASS — 5/5 contratos KEPT, 0 violações |
| pytest unit | `.venv/bin/python -m pytest -m unit output/src/tests/unit/` | PASS — 266 passed, 0 falhas |
| pytest staging | `pytest -m staging` (mac-lablz) | CANNOT RUN — requer mac-lablz |
| smoke gate A_SMOKE | `scripts/smoke_sprint_6.py` (mac-lablz) | CANNOT RUN — requer mac-lablz |
| smoke gate A10 | `scripts/smoke_ui.sh` (mac-lablz) | CANNOT RUN — requer mac-lablz |

---

## Critérios de Alta

### A1 — [B1-CLIENTE-NOVO] POST /dashboard/clientes/novo
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k cliente_novo`
**Evidência observada:** 4 testes PASS — `test_dashboard_cliente_novo_valido_redireciona`, `test_dashboard_cliente_novo_cnpj_invalido_retorna_erro`, `test_dashboard_cliente_novo_cnpj_duplicado_retorna_erro`, `test_dashboard_cliente_novo_rep_outro_tenant_retorna_erro`
**Cobertura de casos:** criação válida ✅ | CNPJ < 14 dígitos ✅ | CNPJ duplicado no tenant ✅ | representante_id de outro tenant ✅

### A2 — [B2-PRECOS-UPLOAD] POST /dashboard/precos/upload
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k precos_upload`
**Evidência observada:** 2 testes PASS — `test_dashboard_precos_upload_sucesso`, `test_dashboard_precos_upload_arquivo_ausente_retorna_400`
**Cobertura de casos:** xlsx válida ✅ | arquivo ausente (400) ✅ | ExcelUploadResult sem AttributeError ✅

### A3 — [B3-TOP-PRODUTOS] GET /dashboard/top-produtos
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k top_produtos`
**Evidência observada:** 2 testes PASS — `test_dashboard_top_produtos_retorna_200`, `test_dashboard_top_produtos_sem_link_dashboard_isolado`
**Cobertura de casos:** 200 ✅ | href="/dashboard" isolado ausente ✅ | link "Voltar" → /dashboard/home ✅

### A4 — [B4-TENANT-ISOLATION] Queries não vazam entre tenants
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k tenant_isolation`
**Evidência observada:** `test_dashboard_tenant_isolation_pedidos` PASS — JOIN `c.tenant_id = p.tenant_id` verificado em `_get_pedidos_recentes`

### A5 — [E5-STARTUP] App não aceita requests com secret ausente
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/providers/test_startup_validation.py`
**Evidência observada:** 4 testes PASS — inclui cenário com múltiplas variáveis ausentes → mensagem única lista todas; `create_app()` não retorna app saudável
**Variáveis verificadas:** POSTGRES_URL, REDIS_URL, JWT_SECRET, DASHBOARD_SECRET, DASHBOARD_TENANT_ID, EVOLUTION_API_KEY, EVOLUTION_WEBHOOK_SECRET, OPENAI_API_KEY, ANTHROPIC_API_KEY (9/9) ✅

### A6 — [E6-RATE-LOGIN] 6ª tentativa de login retorna 429
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k rate_limit_login`
**Evidência observada:** 3 testes PASS — 5ª tentativa→401 ✅ | 6ª tentativa→429 ✅ | login correto reseta contador ✅

### A7 — [E7-RATE-WEBHOOK] 31º MESSAGES_UPSERT retorna 429
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_webhook.py -k rate_limit`
**Evidência observada:** 3 testes PASS — `test_webhook_rate_limit_31o_evento_retorna_429`, `test_webhook_rate_limit_nao_conta_eventos_nao_upsert`, `test_webhook_rate_limit_429_payload_json_estavel`

### A8 — [E8-HEALTH-ANTHROPIC] /health classifica ok/degraded/fail
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_anthropic_health.py`
**Evidência observada:** 6 testes PASS — ok após sucesso ✅ | degraded em overload 529 ✅ | fail em 401/402/403 ✅ | health_check.py sai exit≠0 quando fail ✅

### A9 — [E9-CORS] Staging sem wildcard; cookie Secure=True apenas em production
**Status:** PASS
**Teste executado:** `pytest -m unit output/src/tests/unit/agents/test_dashboard.py -k cors_cookie`
**Evidência observada:** 2 testes PASS — `test_dashboard_cookie_secure_false_em_staging` ✅ | `test_dashboard_cookie_secure_true_em_production` ✅
**CORS verificado em código:** `create_app()` usa `CORS_ALLOWED_ORIGINS` explícito em staging; levanta `RuntimeError` se ausente

### A10 — [G4-SMOKE-UI] Todas as rotas do dashboard retornam 200
**Status:** CANNOT RUN — requer mac-lablz
**Teste:** `ssh macmini-lablz "... infisical run --env=staging -- bash ../scripts/smoke_ui.sh"`
**Nota:** `scripts/smoke_ui.sh` existe no repositório ✅; execução pendente no mac-lablz.

### A_SMOKE — Smoke gate staging — caminho crítico completo
**Status:** CANNOT RUN — requer mac-lablz + NOTA DE GAP
**Teste:** `ssh macmini-lablz "... infisical run --env=staging -- python ../scripts/smoke_sprint_6.py"`
**Nota de GAP:** `scripts/smoke_sprint_6.py` existe ✅ mas tem cobertura incompleta vs. spec:
- G7 verifica apenas `GET /dashboard/precos` (página carrega) ❌ em vez de `POST /dashboard/precos/upload` (processar fixture)
- Smoke NÃO verifica `POST /dashboard/clientes/novo` com criação real
- Smoke NÃO verifica burst de webhook → 429
Mesmo que retorne "ALL OK" no mac-lablz, esses três caminhos críticos não serão exercitados. Registrado como débito — script deve ser corrigido na rodada de correção.

---

## Critérios de Média

### M1 — [TYPE-HINTS] type hints em funções públicas novas/modificadas
**Status:** FAIL
**Teste executado:** `mypy --strict output/src/tenants/service.py output/src/catalog/service.py output/src/dashboard/ui.py output/src/agents/ui.py output/src/main.py`
**Evidência observada:**
```
output/src/agents/ui.py:43: error: Returning Any from function declared to return "bool"
output/src/dashboard/ui.py:60: error: Returning Any from function declared to return "int"
output/src/dashboard/ui.py:664: error: Unused "type: ignore" comment
output/src/dashboard/ui.py:754,782,809,848,935,960,984,999,1015: Missing type arguments for generic type "dict"
output/src/main.py:140: error: Missing type arguments for generic type "dict"
Found 46 errors in 9 files (checked 5 source files)
```
Erros em arquivos do Sprint 6: agents/ui.py (1), dashboard/ui.py (~10), main.py (1). Total: ~12 erros em escopo.

### M2 — [DOCSTRINGS] docstrings em funções públicas de Service
**Status:** PASS (inspeção de código)
**Evidência:** Funções inspecionadas em tenants/service.py e catalog/service.py têm docstrings. `criar_cliente_ficticio` e `processar_excel_precos` documentadas. Estimativa visual: ≥ 80%.

### M3 — [COVERAGE-UNIT] cobertura ≥ 80% em Service modificados
**Status:** FAIL
**Teste executado:** `pytest -m unit --cov=output/src --cov-report=term-missing`
**Evidência observada:**
```
output/src/catalog/service.py     156     25    84%   ← PASS
output/src/tenants/service.py      58     17    71%   133-159 ← FAIL (criar_cliente_ficticio)
```
`catalog/service.py` 84% ✅ | `tenants/service.py` 71% ❌ (threshold: ≥ 80%)
**Causa raiz:** `criar_cliente_ficticio` (linhas 133-159) não é coberta por testes de Service — testes de dashboard mockam o Service, sem cobertura direta do método.

### M5 — [COMMIT-SERVICE] Testes de Service verificam session.commit()
**Status:** FAIL
**Teste executado:** `grep -rn "commit.assert_called" output/src/tests/unit/`
**Evidência observada:**
```
# Encontrado em:
tests/unit/agents/test_agent_gestor.py:854  → AgentGestor (fora do escopo M5)
tests/unit/agents/test_agent_gestor.py:1178 → AgentGestor (fora do escopo M5)
tests/unit/catalog/test_repo.py:240,269,305,324,451 → CatalogRepo (não CatalogService)

# NÃO encontrado em:
tests/unit/tenants/test_service.py → 0 ocorrências
tests/unit/catalog/test_service.py → 0 ocorrências
```
**Causa raiz:** Testes de TenantService e CatalogService não verificam `session.commit()`. O gotcha de AsyncSession (commit não automático) está documentado no spec mas não coberto nos unit tests dos Services que escrevem no banco.
**Correção necessária:** Adicionar `mock_session.commit.assert_called()` em `test_startup_validation.py` (TenantService.criar_cliente_ficticio) e `test_service.py` (CatalogService.processar_excel_precos/repo delegation).

### M_INJECT — Injeção de dependências em ui.py sem None
**Status:** FAIL — BLOQUEANTE
**Teste executado:** `pytest -m staging output/src/tests/staging/agents/test_ui_injection.py`
**Evidência observada:**
```
$ ls output/src/tests/staging/agents/test_ui_injection.py
No files found
```
**Causa raiz:** O arquivo `test_ui_injection.py` não existe. O teste foi integrado em `test_dashboard_pre_pilot.py::test_ui_injection_agent_gestor_deps_nao_none`, mas o contrato exige explicitamente o arquivo separado. Per evaluator.md: "Se o arquivo não existir: FAIL de Média". Per contrato: "M_INJECT falha sozinha → bloqueia independente das outras".
**Correção necessária:** Criar `output/src/tests/staging/agents/test_ui_injection.py` com os testes de injeção para AgentCliente, AgentRep e AgentGestor.

---

**Resumo de Média:** 4 falhas de 5. Threshold: 1. Status: EXCEDEU threshold
M_INJECT: FAIL (bloqueante por exceção do contrato)
M1: FAIL (mypy errors nos arquivos modificados)
M3: FAIL (tenants/service.py 71% < 80%)
M5: FAIL (commit.assert_called ausente em TenantService e CatalogService unit tests)
M2: PASS

---

## Débitos registrados no tech-debt-tracker

Não aplicável — sprint REPROVADO. Nenhum débito registrado antes de aprovação.

**Nota adicional:** `smoke_sprint_6.py` tem cobertura incompleta (G7 testa GET em vez de POST precos/upload; faltam POST clientes/novo e burst webhook). Deve ser corrigido na rodada de correção.

---

## Como reproduzir os testes

```bash
# Testes unitários (sem infra)
PYTHONPATH=output .venv/bin/python -m pytest -m unit output/src/tests/unit/ -v

# Verificação de segurança
grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/ --include="*.py" | grep -v test_
grep -rn "print(" output/src/ --include="*.py" | grep -v test_

# Import-linter
PYTHONPATH=output .venv/bin/lint-imports

# Mypy (arquivos do sprint)
.venv/bin/mypy --strict output/src/tenants/service.py output/src/catalog/service.py \
  output/src/dashboard/ui.py output/src/agents/ui.py output/src/main.py

# Cobertura
.venv/bin/python -m pytest -m unit output/src/tests/unit/ \
  --cov=output/src --cov-report=term-missing

# Commit assert (M5)
grep -rn "commit.assert_called" output/src/tests/unit/tenants/
grep -rn "commit.assert_called" output/src/tests/unit/catalog/

# M_INJECT (mac-lablz)
pytest -m staging output/src/tests/staging/agents/test_ui_injection.py -v

# Testes staging (mac-lablz)
pytest -m staging output/src/tests/staging/ -v

# Smoke gate (mac-lablz)
infisical run --env=staging -- python scripts/smoke_sprint_6.py
infisical run --env=staging -- bash scripts/smoke_ui.sh
```

---

## Próximos passos

Sprint 6 REPROVADO — rodada 1 de 1.

**Falhas por prioridade para o Generator corrigir:**

1. **M_INJECT — CRÍTICO (bloqueante):**
   Criar `output/src/tests/staging/agents/test_ui_injection.py` com testes de injeção de deps para AgentCliente, AgentRep e AgentGestor. O teste pode ser movido de `test_dashboard_pre_pilot.py` para o arquivo correto.

2. **M3 — Cobertura de TenantService:**
   Adicionar testes unitários diretos de `TenantService.criar_cliente_ficticio()` em `tests/unit/tenants/test_service.py` para atingir ≥ 80% de cobertura (linhas 133-159).

3. **M5 — Commit assertions:**
   Adicionar `mock_session.commit.assert_called()` (ou `assert_called_once()`) nos testes de `TenantService.criar_cliente_ficticio` e nos testes de `CatalogService` que exercitam escrita no banco.

4. **M1 — Type hints:**
   Corrigir erros mypy nos arquivos do sprint:
   - `agents/ui.py:43` — Returning Any from bool
   - `dashboard/ui.py:60` — Returning Any from int
   - `dashboard/ui.py:664` — Unused type: ignore
   - `dashboard/ui.py:754+` — Missing type args for dict (use `dict[str, Any]`)
   - `main.py:140` — Missing type args for dict

5. **A_SMOKE — Cobertura do smoke script (qualidade):**
   Corrigir `scripts/smoke_sprint_6.py` para verificar:
   - `POST /dashboard/clientes/novo` + verificar cliente visível em lista
   - `POST /dashboard/precos/upload` com fixture real
   - Burst de webhook → 429 (30+ eventos MESSAGES_UPSERT)
