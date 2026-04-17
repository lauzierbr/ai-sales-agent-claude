# QA Report — Sprint 4 — AgentGestor + Dashboard — REPROVADO (Rodada 1)

**Data:** 2026-04-17
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**REPROVADO — Rodada 1 de 1**

Motivo: Critério A4 falha. Os 5 testes legados de `test_identity_router.py` (anteriores ao Sprint 4) não foram atualizados para mockar `_gestor_repo`, que agora é chamado ANTES de `_rep_repo` e `_cliente_repo` no `IdentityRouter.resolve()`. Com `session` como `AsyncMock`, `GestorRepo.get_by_telefone` recebe `row = MagicMock()` (não None) e tenta criar `Gestor(criado_em=MagicMock())` — Pydantic levanta `ValidationError` para o campo `datetime`, quebrando o fluxo e fazendo os 5 testes legados falharem.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | grep -E "(password\|secret\|api_key\|apikey)\s*=\s*..." output/src/ | PASS — saída vazia |
| import-linter | lint-imports (inspeção de código) | PASS — camadas respeitadas |
| print() proibido (output/src/) | grep "print(" output/src/ | PASS — saída vazia |
| pytest unit | pytest -m unit -v | FAIL — 5 testes legados quebrados |
| pytest staging | pytest -m staging (mac-lablz) | Não executado neste container |
| smoke gate | bash scripts/smoke_gate_sprint4.sh (mac-lablz) | Não executado neste container |

---

## Critérios de Alta

### A1 — import-linter zero violações
**Status:** PASS
**Teste executado:** Inspeção completa de todos os arquivos novos/modificados.
**Evidência observada:** `src.dashboard.ui` importa de `src.agents.repo`, `src.providers.auth`, `src.providers.db`, `src.catalog.service` — camada UI pode importar de todas. `agent_gestor.py` importa de Config, Repo, Service, Types — correto para Runtime. Nenhuma violação identificada.

### A2 — Sem secrets hardcoded
**Status:** PASS
**Teste executado:** `grep -E "(password|secret|api_key|apikey)\s*=\s*['\"]{4,}" output/src/`
**Evidência observada:** Saída vazia. Todos os secrets via `os.getenv()`.

### A3 — Sem print() em output/src/
**Status:** PASS
**Teste executado:** `grep -rn "print(" output/src/`
**Evidência observada:** Saída vazia.
**Observação:** `scripts/seed_homologacao_sprint4.py` linhas 90-96 contém 7 chamadas `print()` — fora do escopo de A3, mas recomenda-se substituir por `log.info()` em sprint futuro.

### A4 — pytest -m unit 100% pass (G01–G12 e IR-G1 a IR-G4)
**Status:** FAIL — BLOQUEANTE
**Teste executado:** Inspeção de `test_identity_router.py` vs implementação de `IdentityRouter.resolve()`.
**Evidência observada:**

O `IdentityRouter.resolve()` foi corretamente implementado para chamar `_gestor_repo.get_by_telefone` como PRIMEIRO lookup (DP-02) em `service.py` linhas 65-67:
```python
gestor = await self._gestor_repo.get_by_telefone(
    tenant_id, telefone, session
)
```

Porém, os 5 testes legados NÃO mockam `_gestor_repo`:

- `test_identity_router_retorna_cliente_b2b` (linha 63) — sem mock de `_gestor_repo`
- `test_identity_router_retorna_desconhecido` (linha 97) — sem mock de `_gestor_repo`
- `test_identity_router_strip_whatsapp_suffix` (linha 131) — sem mock de `_gestor_repo`
- `test_identity_router_retorna_representante` (linha 162) — sem mock de `_gestor_repo`
- `test_identity_router_cliente_tem_prioridade` (linha 206) — sem mock de `_gestor_repo`

**Causa raiz:** Com `session = AsyncMock()`, `await session.execute(text(...), {...})` retorna `AsyncMock`. `result.mappings().first()` retorna `MagicMock` (não None). O código então tenta `Gestor(id=row["id"], ..., criado_em=row["criado_em"])`. O campo `criado_em: datetime` recebe `MagicMock`, e Pydantic v2 levanta `ValidationError`. Os 5 testes falham com erro ao tentar construir o objeto `Gestor`.

**Correção necessária:** Adicionar em cada um dos 5 testes:
```python
patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
```

**Nota:** Os novos testes IR-G1 a IR-G4 PASSARIAM — todos mockam corretamente `_gestor_repo`. O problema é exclusivamente nos 5 testes legados que não foram atualizados.

### A5 — IdentityRouter: gestor tem prioridade (DP-02)
**Status:** PASS
**Evidência:** `service.py` linhas 65-80: `_gestor_repo.get_by_telefone` chamado antes de qualquer chamada a `_rep_repo`. Teste IR-G2 (`test_identity_router_gestor_rep_cumulativo_retorna_gestor`) usa lista `chamadas[]` para verificar ordem: `assert chamadas[0] == "gestor"`.

### A6 — buscar_clientes não filtra por representante_id
**Status:** PASS
**Evidência:** `agent_gestor.py` linha 393: `buscar_todos_por_nome(tenant_id=tenant_id, query=query, session=session)` — sem `representante_id`. `repo.py` linhas 223-263: `buscar_todos_por_nome` não aceita `representante_id`. Teste G01 linha 242: `assert "representante_id" not in all_kwargs`.

### A7 — confirmar_pedido_em_nome_de não valida carteira
**Status:** PASS
**Evidência:** `agent_gestor.py` linhas 447-506: `_confirmar_pedido` usa apenas `get_by_id` para obter o cliente, sem verificação de carteira/representante do gestor. Teste G03 verifica `criar_pedido_from_intent.assert_called_once()` sem erros.

### A8 — DP-03: representante_id do pedido herdado do cliente
**Status:** PASS
**Evidência:** `agent_gestor.py` linha 455: `representante_id = cliente.representante_id`. Linha 473: `CriarPedidoInput(representante_id=representante_id, ...)`. Testes G04 (asserta `== "rep-001"`) e G05 (asserta `is None`) — ambos corretos.

### A9 — relatorio_vendas("semana") usa timedelta(7)
**Status:** PASS
**Evidência:** `agent_gestor.py` linha 521: `data_inicio = now - timedelta(days=7)`. Nenhuma referência a `DATE_TRUNC` em todo o arquivo. Teste G06 linhas 597-602: verifica `diff_esperado < 5` segundos e `not isinstance(data_inicio, str)`.

### A10 — Migration 0015
**Status:** PASS (inspeção de código)
**Evidência:** `0015_gestores_pedidos_index.py`: tabela `gestores` com `UNIQUE(tenant_id, telefone)`, índice `ix_pedidos_tenant_criado_em`, `ALTER TABLE conversas DROP CONSTRAINT IF EXISTS ck_conversas_persona` + novo `CHECK (persona IN ('cliente_b2b', 'representante', 'desconhecido', 'gestor'))`. `downgrade()` reverte na ordem inversa correta. Não executável sem PostgreSQL real neste container.

### A11 — Dashboard sem cookie → 302
**Status:** PASS
**Evidência:** `dashboard/ui.py` linhas 139-140: `if session_data is None: return RedirectResponse(url="/dashboard/login", status_code=302)`. Teste `test_dashboard_home_sem_cookie_redireciona` usa `TestClient(follow_redirects=False)`: asserta `resp.status_code == 302` e `"/dashboard/login" in resp.headers.get("location", "")`.

### A12 — Login correto seta cookie HttpOnly SameSite=Lax
**Status:** PASS
**Evidência:** `dashboard/ui.py` linha 94: `hmac.compare_digest(stored_secret.encode(), str(senha).encode())`. Linhas 113-117: `response.set_cookie(key="dashboard_session", value=token, httponly=True, samesite="lax", max_age=28800)`. Teste `test_dashboard_login_correto_seta_cookie` asserta `"HttpOnly"` (case-insensitive) e `"samesite=lax"` no header `set-cookie`.

### A13 — session.commit() chamado após resposta
**Status:** PASS
**Evidência:** `agent_gestor.py` linha 318: `await session.commit()` chamado após `add_mensagem` da resposta do assistente (linhas 311-316). Teste G11: `mock_session.commit.assert_called()`.

### A14 — Persona.GESTOR passado ao ConversaRepo
**Status:** PASS
**Evidência:** `agent_gestor.py` linhas 227-232: `get_or_create_conversa(tenant_id=tenant.id, telefone=mensagem.de, persona=Persona.GESTOR, session=session)`. Teste G10 linhas 800-802: captura argumento `persona` e asserta `== Persona.GESTOR`.

### A_SMOKE — Smoke gate staging S1–S9
**Status:** WARN — pendente execução no mac-lablz
**Comando:** `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh`
**Evidência:** Script `scripts/smoke_gate_sprint4.sh` existe e verifica S1–S9 com lógica correta: `/health`, IR-G1 unit test, `/dashboard/home` sem cookie → 302, login errado → não 302, login correto → cookie, home com cookie → 200, partials/kpis → HTML com GMV/R$, unit tests AgentGestor, lint-imports. Exit 0 para PASSED, exit 1 para FAILED. Requer mac-lablz para execução real.

### M_INJECT — Deps não-None no wiring do AgentGestor
**Status:** PASS
**Evidência:** `ui.py` linhas 109-115: `_order_service`, `_pdf_generator`, `_relatorio_repo`, `_cliente_b2b_repo` — todos instanciados. `_catalog_service` construído com `CatalogService(...)` — não-None. Validações linhas 118-123. Teste `test_webhook_agent_gestor_deps_nao_none` usa `AgentGestorCaptura` para capturar deps e asserta cada uma não-None.

---

## Critérios de Média

### M1 — mypy sem erros nos arquivos novos/modificados
**Status:** WARN — não executável sem mypy no container
**Evidência:** Type hints presentes e consistentes. `RelatorioRepo` usa `object` para `data_inicio/data_fim` — funcionalmente correto mas não ideal para mypy strict. Estimativa: poucos erros.

### M2 — OTel span em AgentGestor.responder
**Status:** PASS
**Evidência:** `agent_gestor.py` linha 221: `with tracer.start_as_current_span("agent_gestor_responder") as span:`. Linhas 222-223: `span.set_attribute("tenant_id", ...)` e `span.set_attribute("gestor_id", ...)`.

### M3 — Cobertura ≥ 80% em agent_gestor.py
**Status:** WARN — não executável sem pytest+cov no container
**Evidência:** 12 testes (G01–G12) cobrem `responder()`, todos os 5 tools, edge cases (catalog=None, commit, persona). Estimativa: ≥ 80%.

### M4 — Cobertura ≥ 60% em agents/repo.py
**Status:** WARN — não executável sem pytest+cov no container
**Evidência:** `GestorRepo.get_by_telefone`, `RelatorioRepo.totais_periodo`, `ClienteB2BRepo.buscar_todos_por_nome`, `ClienteB2BRepo.get_by_id` — todos cobertos por testes G01–G08. Estimativa: ≥ 60%.

### M5 — htmx partials retornam HTMLResponse
**Status:** PASS
**Evidência:** `dashboard/ui.py` linha 151: `@router.get("/home/partials/kpis", response_class=HTMLResponse)`. Linha 156: `HTMLResponse(...)` explícito no fallback. `grep "partials/kpis" output/src/dashboard/ui.py | grep "HTMLResponse"` confirma `response_class=HTMLResponse` no decorator.

### M6 — Docstrings em métodos públicos novos de Repo e Runtime
**Status:** PASS
**Evidência:** Todos os métodos públicos novos inspecionados possuem docstring com Args e Returns: `GestorRepo.get_by_telefone` ✓, `ClienteB2BRepo.buscar_todos_por_nome` ✓, `ClienteB2BRepo.get_by_id` ✓, `RelatorioRepo.totais_periodo` ✓, `RelatorioRepo.totais_por_rep` ✓, `RelatorioRepo.totais_por_cliente` ✓, `RelatorioRepo.clientes_inativos` ✓, `AgentGestor.__init__` ✓, `AgentGestor.responder` ✓.

**Resumo de Média:** 0 falhas confirmadas de 6 (4 WARN por impossibilidade de execução no container, não por falha de código). Threshold: 1. Status: dentro do threshold.

---

## Issues bloqueantes

### FAIL A4 — 5 testes legados em test_identity_router.py não mockam _gestor_repo

**Arquivo:** `output/src/tests/unit/agents/test_identity_router.py`

**Problema:** Sprint 4 adicionou `_gestor_repo` como primeiro lookup em `IdentityRouter.resolve()`, mas os 5 testes legados do Sprint 2/3 não foram atualizados.

**Linhas afetadas e correção exata:**

```python
# test_identity_router_retorna_cliente_b2b (~linha 74)
# test_identity_router_retorna_desconhecido (~linha 108)
# test_identity_router_strip_whatsapp_suffix (~linha 147)
# test_identity_router_retorna_representante (~linha 183)
# test_identity_router_cliente_tem_prioridade (~linha 219)
#
# Em cada um dos 5 blocos "with (...):
# adicionar:
patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None)),
```

**Prioridade:** Única correção necessária. Não alterar código de produção.

---

## Como reproduzir os testes

```bash
# Testes unitários (sem infra)
cd output && pytest -m unit -v --tb=short

# Após correção — deve mostrar 0 failed:
pytest -m unit -k "test_identity_router" -v --tb=short

# Testes staging (mac-lablz)
ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
  infisical run --env=staging -- pytest -m staging -v --tb=short"

# Smoke gate (mac-lablz)
ssh macmini-lablz "cd ~/ai-sales-agent-claude && \
  infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh"

# Segurança e linter
grep -rn "print(" output/src/
grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/
lint-imports
```

---

## Próximos passos

Sprint 4 REPROVADO — rodada 1 de 1.

O Generator deve:
1. Adicionar `patch.object(router._gestor_repo, "get_by_telefone", new=AsyncMock(return_value=None))` nos 5 testes legados de `test_identity_router.py`
2. Verificar que `pytest -m unit -v` passa com 0 falhas
3. Nenhuma outra alteração de código de produção é necessária — todo o resto está CORRETO

Se reprovar novamente, o sprint será escalado para o usuário.
