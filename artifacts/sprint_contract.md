# Sprint Contract — Sprint 4 — Gestor/Admin

**Status:** ACEITO
**Data:** 2026-04-17

---

## Entregas comprometidas

1. `output/alembic/versions/0015_gestores_pedidos_index.py` — tabela `gestores` + `ix_pedidos_tenant_criado_em` + fix `ck_conversas_persona` (adiciona `'gestor'`)
2. `output/src/agents/types.py` — `Persona.GESTOR = "gestor"` + `class Gestor(BaseModel)`
3. `output/src/agents/repo.py` — `GestorRepo.get_by_telefone()` + `ClienteB2BRepo.buscar_todos_por_nome()` + `ClienteB2BRepo.get_by_id()` + `RelatorioRepo` (4 métodos)
4. `output/src/agents/config.py` — `AgentGestorConfig` com `max_iterations=8` e `system_prompt_template`
5. `output/src/agents/runtime/agent_gestor.py` — `AgentGestor` com 5 ferramentas: `buscar_clientes`, `buscar_produtos`, `confirmar_pedido_em_nome_de`, `relatorio_vendas`, `clientes_inativos`
6. `output/src/agents/service.py` — `IdentityRouter.resolve()` com prioridade `gestores → representantes → clientes_b2b → DESCONHECIDO`
7. `output/src/agents/ui.py` — wiring de `AgentGestor` quando `Persona.GESTOR`; deps não-None verificadas
8. `output/src/dashboard/` (novo módulo) — 12 endpoints, Jinja2+htmx, auth via `DASHBOARD_SECRET` cookie HttpOnly (D023)
9. `output/src/main.py` — `app.include_router(dashboard_router)` + `src/providers/tenant_context.py` com `/dashboard` em `_EXCLUDED_PREFIXES`
10. `output/src/tests/unit/agents/test_agent_gestor.py` — 12 testes G01–G12 `@pytest.mark.unit`
11. `output/src/tests/unit/agents/test_identity_router.py` — adição de IR-G1 a IR-G4
12. `output/src/tests/staging/agents/test_agent_gestor_staging.py` — 2 testes `@pytest.mark.staging`
13. `scripts/seed_homologacao_sprint4.py` — seed do gestor de teste + pedidos antigos para `clientes_inativos`
14. `scripts/smoke_gate_sprint4.sh` — verifica S1–S9; saída `PASSED` com exit 0
15. `docs/design-docs/index.md` — ADR D023 registrado (já presente — confirmar bloco inline)
16. `artifacts/handoff_sprint_4.md` — handoff ao Sprint 5

---

## Critérios de aceitação — Alta (bloqueantes)

**A1. import-linter — zero violações de camadas (incluindo `src.dashboard`)**
Teste: `lint-imports` na raiz do projeto
Evidência esperada: `Kept` para todos os contratos; zero linhas `Broken`
Nota: `src.dashboard.ui` é UI layer — pode importar de `src.agents.repo`, `src.orders.repo` e outros. Sem violação.

**A2. Sem secrets hardcoded**
Teste:
```bash
grep -r --include="*.py" \
  -E "(password|secret|api_key|apikey)\s*=\s*['\"][^'\"]{4,}" \
  output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A3. Sem print() em output/src/**
Teste:
```bash
grep -r --include="*.py" "print(" output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A4. pytest -m unit — 100% dos testes passam (incluindo G01–G12 e IR-G1 a IR-G4)**
Teste: `pytest -m unit -v`
Evidência esperada: `0 failed, 0 error`

**A5. IdentityRouter: gestor tem prioridade sobre rep no mesmo número (DP-02)**
Teste: `pytest -m unit -k "test_identity_router_gestor_rep_cumulativo_retorna_gestor"`
Evidência esperada: `PASSED` — quando mock retorna gestor ativo E representante ativo para o mesmo telefone, `IdentityRouter.resolve()` retorna `Persona.GESTOR`; `GestorRepo.get_by_telefone` chamado antes de `RepresentanteRepo.get_by_telefone`

**A6. AgentGestor: buscar_clientes não filtra por representante_id (acesso irrestrito)**
Teste: `pytest -m unit -k "test_agent_gestor_g01_buscar_clientes_sem_filtro_rep"`
Evidência esperada: `PASSED` — mock de `ClienteB2BRepo.buscar_todos_por_nome` captura os argumentos; teste asserta **explicitamente** que `representante_id` **não** está nos argumentos passados

**A7. AgentGestor: confirmar_pedido_em_nome_de não valida carteira**
Teste: `pytest -m unit -k "test_agent_gestor_g03_pedido_sem_validacao_carteira"`
Evidência esperada: `PASSED` — cliente fora de qualquer carteira passa pelo teste sem erro; `OrderService.criar_pedido_from_intent` chamado 1x

**A8. DP-03: representante_id do pedido herdado do cliente**
Teste (dois casos):
```bash
pytest -m unit -k "test_agent_gestor_g04_dp03_herda_rep_do_cliente"
pytest -m unit -k "test_agent_gestor_g05_dp03_sem_rep_none"
```
Evidência esperada: ambos `PASSED`
- G04: `CriarPedidoInput.representante_id` = `cliente.representante_id` (não None quando cliente tem rep)
- G05: `CriarPedidoInput.representante_id` = None quando `cliente.representante_id` é None

**A9. relatorio_vendas("semana") usa timedelta(7), não DATE_TRUNC**
Teste: `pytest -m unit -k "test_agent_gestor_g06_semana_usa_timedelta"`
Evidência esperada: `PASSED` — o mock de `RelatorioRepo.totais_periodo` captura `data_inicio`; o teste asserta que `data_inicio ≈ now - timedelta(days=7)` (diferença < 5 segundos) e que nenhuma string `DATE_TRUNC` ou `TRUNC` foi passada como argumento

**A10. Migration 0015: gestores + índice + fix CHECK CONSTRAINT**
Teste:
```bash
alembic upgrade head     # aplica 0015
alembic downgrade -1     # reverte 0015
alembic upgrade head     # reaaplica
```
Evidência esperada: nenhum erro nas 3 execuções; após `upgrade head`:
- `SELECT COUNT(*) FROM gestores;` retorna 0 (tabela vazia, criada com sucesso)
- `SELECT indexname FROM pg_indexes WHERE indexname = 'ix_pedidos_tenant_criado_em';` retorna 1 linha
- `SELECT consrc FROM pg_constraint WHERE conname = 'ck_conversas_persona';` contém `'gestor'`

**A11. Dashboard: sem cookie → 302 para /dashboard/login**
Teste: `pytest -m unit -k "test_dashboard_home_sem_cookie_redireciona"`
Evidência esperada: `PASSED` — `GET /dashboard/home` sem cookie retorna status 302 com `Location: /dashboard/login`

**A12. Dashboard: login correto → cookie dashboard_session setado**
Teste: `pytest -m unit -k "test_dashboard_login_correto_seta_cookie"`
Evidência esperada: `PASSED` — `POST /dashboard/login` com `DASHBOARD_SECRET` correto retorna resposta com `Set-Cookie: dashboard_session=...` com atributos `HttpOnly` e `SameSite=lax`

**A13. AgentGestor: session.commit() chamado após resposta**
Teste: `pytest -m unit -k "test_agent_gestor_g11_commit_chamado"`
Evidência esperada: `PASSED` — `mock_session.commit` chamado ao menos 1x durante `AgentGestor.responder` (para persistência de ConversaRepo.add_mensagem); `OrderService` pode ser mockado neste teste

**A14. AgentGestor: Persona.GESTOR passado ao ConversaRepo**
Teste: `pytest -m unit -k "test_agent_gestor_g10_persona_gestor_em_conversa"`
Evidência esperada: `PASSED` — `ConversaRepo.get_or_create_conversa` chamado com `persona=Persona.GESTOR` (não REPRESENTANTE nem CLIENTE_B2B)

**A_SMOKE. Smoke gate staging — S1 a S9 passam com infra real**
Teste:
```bash
infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh
```
Evidência esperada: saída `=== SMOKE GATE: PASSED ===`, exit code 0.
Verifica obrigatoriamente:
- S1: `/health` → 200 com `"status":"ok"`
- S2: Unit tests IR-G1 (IdentityRouter GESTOR) passam
- S3: `GET /dashboard/home` sem cookie → 302
- S4: `POST /dashboard/login` com senha errada → NÃO 302
- S5: `POST /dashboard/login` com senha correta → cookie setado
- S6: `GET /dashboard/home` com cookie → 200
- S7: `GET /dashboard/home/partials/kpis` → HTML com "GMV" ou "R$"
- S8: `pytest -m unit test_agent_gestor.py` → 0 falhas
- S9: `lint-imports` → zero violações

**M_INJECT. Dependências não-None no wiring do AgentGestor em ui.py**
Teste: `pytest -m unit -k "test_webhook_agent_gestor_deps_nao_none"`
Evidência esperada: `PASSED` — quando `Persona.GESTOR` é identificada em `_process_message`, `catalog_service`, `order_service`, `pdf_generator`, `relatorio_repo` e `cliente_b2b_repo` passados ao `AgentGestor` são todos não-None

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

**M1. mypy sem erros nos arquivos novos/modificados**
Teste: `mypy output/src/agents/types.py output/src/agents/repo.py output/src/agents/config.py output/src/agents/runtime/agent_gestor.py output/src/agents/service.py output/src/dashboard/ui.py`
Evidência esperada: `Found 0 errors`

**M2. OTel span em AgentGestor.responder**
Teste: inspeção de `output/src/agents/runtime/agent_gestor.py`
```bash
grep "start_as_current_span" output/src/agents/runtime/agent_gestor.py
```
Evidência esperada: ao menos 1 linha contendo `start_as_current_span("agent_gestor_responder")` com atributos `tenant_id` e `gestor_id`

**M3. Cobertura ≥ 80% em agent_gestor.py**
Teste: `pytest -m unit --cov=output/src/agents/runtime/agent_gestor --cov-report=term-missing`
Evidência esperada: cobertura de linhas ≥ 80%

**M4. Cobertura ≥ 60% em agents/repo.py (novos métodos)**
Teste: `pytest -m unit --cov=output/src/agents/repo --cov-report=term-missing`
Evidência esperada: cobertura de linhas ≥ 60%

**M5. htmx partials retornam HTMLResponse (não JSONResponse)**
Teste: inspeção de `output/src/dashboard/ui.py`
```bash
grep -A 3 "partials/kpis" output/src/dashboard/ui.py | grep "HTMLResponse"
```
Evidência esperada: linha contendo `HTMLResponse` no handler do partial `/home/partials/kpis`

**M6. Docstrings em todos os métodos públicos novos de Repo e Runtime**
Teste: inspeção manual de `repo.py` (GestorRepo, RelatorioRepo, adições em ClienteB2BRepo) e `agent_gestor.py` (métodos públicos)
Evidência esperada: cada método público tem docstring com Args e Returns

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 6**

Se 2 ou mais critérios de Média falharem, o sprint é reprovado mesmo com
todos os de Alta passando.

---

## Fora do escopo deste contrato

O Evaluator **não** testa neste sprint:

- `cancelar_pedido` via WhatsApp
- Criação ou edição de clientes via dashboard
- Edição de configurações do tenant via dashboard (read-only)
- Autenticação multi-usuário (múltiplos gestores com senhas individuais)
- SSE ou WebSockets para real-time (polling htmx 30s é o contratado)
- Regras de comissão por rep
- Segundo tenant real
- Envio real de WhatsApp no smoke gate (mockado em staging)
- Comportamento do Evaluator.py (sem alteração neste sprint)

---

## Ambiente de testes

```
pytest -m unit    → sem I/O externo; PostgreSQL, Redis, Anthropic API, Evolution API: todos mockados
                    Requerido: 100% pass, 0 falhas (A1–A14, M_INJECT)

pytest -m staging → Postgres + Redis reais (mac-lablz); sem Evolution API; Claude real para A_SMOKE
                    Requerido para A_SMOKE: smoke gate passa S1–S9

pytest -m integration → NÃO roda no Evaluator; valida após aprovação no mac-lablz
```

**Regra crítica (herdada Sprint 2/3):** teste `@pytest.mark.unit` que realiza conexão TCP, acesso ao filesystem fora de `/tmp` ou chamada HTTP real é tratado como **falha de Alta**, independentemente do resultado.

---

## Notas de implementação (binding para o Generator)

1. **Ordem de implementação:**
   E1 (migration 0015) → E2 (types) → E3 (repo) → E4 (config) → E5 (runtime agent_gestor) →
   E6 (service IdentityRouter) → E7 (ui webhook) → E9 (ADR D023) → E8 (dashboard) →
   E10 (testes + smoke + seed)

2. **unaccent:** extensão já ativada em migration 0013 — não reativar. `buscar_todos_por_nome` usa mesma query de `buscar_por_nome` mas sem filtro `representante_id`.

3. **CHECK CONSTRAINT `ck_conversas_persona`:** migration 0015 deve:
   ```python
   op.execute("ALTER TABLE conversas DROP CONSTRAINT ck_conversas_persona")
   op.execute("""ALTER TABLE conversas ADD CONSTRAINT ck_conversas_persona
                 CHECK (persona IN ('cliente_b2b', 'representante', 'desconhecido', 'gestor'))""")
   ```

4. **session.commit() em AgentGestor:** chamar `await session.commit()` após `add_mensagem` da resposta do assistente — mesmo padrão de `AgentRep` linha 292. `OrderService.criar_pedido_from_intent` já chama `await session.commit()` internamente; isso resulta em dois commits em produção (pedido + conversa) — comportamento esperado e seguro.

5. **DP-03 em confirmar_pedido_em_nome_de:** antes de chamar `OrderService.criar_pedido_from_intent`, chamar `ClienteB2BRepo.get_by_id(cliente_b2b_id, tenant.id, session)` para obter `cliente.representante_id`. Usar esse valor em `CriarPedidoInput.representante_id`. Verificar que `CriarPedidoInput` aceita `representante_id: str | None`.

6. **Dashboard auth:** `hmac.compare_digest(stored_secret.encode(), received.encode())`. NUNCA `stored_secret == received` (timing attack). Token JWT do cookie usa `create_access_token` existente de `src.providers.auth` se disponível; se não, implementar com `python-jose` ou `PyJWT` (já no projeto por D021).

7. **TenantProvider exclusão:** em `src/providers/tenant_context.py`, adicionar `/dashboard` à lista `_EXCLUDED_PREFIXES` (ou equivalente). Verificar se existe constante ou lógica de exclusão no middleware atual.

8. **Test G01 (buscar_clientes sem rep filter):** usar `mocker.call_args` para capturar argumentos do mock de `ClienteB2BRepo.buscar_todos_por_nome` e verificar que `representante_id` não está nos `kwargs`.

9. **Test G06 (timedelta vs DATE_TRUNC):** mock `datetime.now` ou `datetime.utcnow` no módulo `agent_gestor` para controlar `now`. Verificar que `data_inicio` passado ao `RelatorioRepo` está dentro de 5s de `mocked_now - timedelta(days=7)`.

10. **Staging seed:** o telefone do gestor de teste deve ser `"5519000000002"` para não colidir com rep de teste (`5519000000001`) nem com cliente de teste (`5519992066177`). Verificar no seed se o número do gestor real (Lauzier) deve ser incluído separado.
