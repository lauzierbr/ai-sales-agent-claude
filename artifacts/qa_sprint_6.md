# QA Report — Sprint 6 — Pre-Pilot Hardening — APROVADO

**Data:** 2026-04-21
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md
**Versão entregue:** 0.6.1
**Commit:** 43f7302
**Rodadas:** 3 (r1: REPROVADO, r2: escalação, r3: APROVADO após sync macmini-lablz)

---

## Veredicto

**APROVADO**

Todos os critérios de Alta e Média passaram com evidências de execução no macmini-lablz (staging real).
273 unit tests PASS. 6/6 staging tests PASS. Smoke gate G1-G9 ALL OK. smoke_ui.sh 13/13 PASSED.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -rn "sk-ant\|api_key=..."` output/src/ | **PASS** — 0 resultados |
| Passwords hardcoded | `grep -rn "password=..."` output/src/ | **PASS** — 0 resultados |
| print() proibido | `grep -rn "print("` output/src/ (excl. testes) | **PASS** — 0 resultados |
| import-linter | `PYTHONPATH=output .venv/bin/lint-imports` | **PASS** — 5/5 KEPT, 0 violações |
| mypy sprint files | `mypy --strict` (5 arquivos do Sprint 6) | **PASS** — 0 erros |
| pytest unit | `pytest -m unit output/src/tests/unit/` | **PASS** — 273 passed, 0 falhas |
| coverage tenants/service | `--cov=output/src/tenants/service` | **PASS** — 100% |
| coverage catalog/service | `--cov=output/src/catalog/service` | **PASS** — 85% |
| pytest staging Sprint 6 | `test_dashboard_pre_pilot.py + test_ui_injection.py` (macmini-lablz) | **PASS** — 6/6 |
| M_INJECT | `pytest test_ui_injection.py` (macmini-lablz) | **PASS** — 3/3 |
| smoke gate A_SMOKE | `smoke_sprint_6.py` (macmini-lablz) | **PASS** — ALL OK, exit 0 |
| smoke gate A10 | `smoke_ui.sh` (macmini-lablz) | **PASS** — 13/13, exit 0 |

---

## Critérios de Alta

### A1–A9 — Funcionalidade

| Critério | Referência | Status | Evidência |
|----------|-----------|--------|-----------|
| A1 [B1-CLIENTE-NOVO] | E1 | PASS | 4 unit tests + G8 smoke: POST /dashboard/clientes/novo + verificação na lista |
| A2 [B2-PRECOS-UPLOAD] | E2 | PASS | 2 unit tests + G7 smoke: POST /dashboard/precos/upload com fixture pandas |
| A3 [B3-TOP-PRODUTOS] | E3 | PASS | 2 unit tests + G4 smoke: listagem com preços |
| A4 [B4-TENANT-ISOLATION] | E4 | PASS | 1 unit test + JOIN `c.tenant_id = p.tenant_id` em `_get_pedidos_recentes` |
| A5 [E5-STARTUP] | E5 | PASS | 4 unit tests; `_validate_secrets()` lista 9 secrets; RuntimeError correto |
| A6 [E6-RATE-LOGIN] | E6 | PASS | 3 unit tests + G6 smoke: 5 falhas → 429 na 6ª tentativa |
| A7 [E7-RATE-WEBHOOK] | E7 | PASS | 3 unit tests + G9 smoke: 32 eventos → 429 confirmado |
| A8 [E8-HEALTH-ANTHROPIC] | E8 | PASS | 6 unit tests; `/health` retorna `ok/degraded/fail` corretamente |
| A9 [E9-CORS] | E9 | PASS | 2 unit tests; sem wildcard em staging/production |

### A10 — [G4-SMOKE-UI]

**Status:** PASS

```
=== UI SMOKE: 13/13 PASSED, 0 FAILED ===
=== UI SMOKE GATE: PASSED ===
SMOKE_UI_EXIT:0
```

Rotas verificadas: L0 (login), U1 (home), U2 (clientes), U3 (precos), U4 (pedidos),
U5 (top-produtos), U6 (representantes), U7 (feedback), U8 (meus-clientes),
U9 (logout), U10 (health), U11 (cliente novo form), U12 (webhook).
Todas retornam 200 com conteúdo correto.

### A_SMOKE — Smoke gate staging

**Status:** PASS

```
G1 health .............. OK  {"status":"ok","version":"0.6.1","components":{"anthropic":"ok"}}
G2 login ............... OK  302 → /dashboard/
G3 home ................ OK  200 dashboard home
G4 clientes ............ OK  200 lista de clientes
G5 top-produtos ........ OK  200 top produtos com preços
G6 rate-limit-login .... OK  429 na 6ª tentativa (5 falhas/IP/15min)
G7 precos-upload ....... OK  200 upload Excel processado
G8 cliente-novo ........ OK  CRIA+VISIVEL — POST 200 + cliente visível na lista
G9 webhook-burst-429 ... OK  429 após 30 eventos (testado com 32 eventos HMAC)
```

Todos os 9 gates ALL OK. Exit code: 0.

---

## Critérios de Média

### M1 — [TYPE-HINTS]
**Status:** PASS
**Evidência:** `mypy --strict` nos 5 arquivos do Sprint 6 → 0 erros em escopo do sprint.

### M2 — [DOCSTRINGS]
**Status:** PASS — docstrings presentes em todas as funções públicas dos arquivos do sprint.

### M3 — [COVERAGE-UNIT]
**Status:** PASS

```
output/src/tenants/service.py   100%  ✅  (era 71% na rodada 1)
output/src/catalog/service.py    85%  ✅
```

### M5 — [COMMIT-SERVICE]
**Status:** PASS

```
tests/unit/tenants/test_service.py:318  session.commit.assert_called()  ✅
tests/unit/catalog/test_service.py:272  mock_session.commit.assert_called()  ✅
```

### M_INJECT — Injeção de dependências
**Status:** PASS

`output/src/tests/staging/agents/test_ui_injection.py` — 3/3 PASS no macmini-lablz:
- `test_ui_injection_agent_gestor_deps_nao_none` ✅ — catalog_service, order_service, pdf_generator, relatorio_repo, cliente_b2b_repo, redis_client todos não-None
- `test_ui_injection_agent_cliente_deps_nao_none` ✅ — catalog_service, order_service, pdf_generator, redis_client, conversa_repo todos não-None
- `test_ui_injection_agent_rep_deps_nao_none` ✅ — catalog_service, order_service, pdf_generator, redis_client, conversa_repo, representante todos não-None

---

**Resumo de Média:** 0 falhas de 5 critérios. Threshold: 1. **Dentro do threshold.**

---

## Falhas de staging pre-existentes (não introduzidas pelo Sprint 6)

O `pytest -m staging` no macmini-lablz tem 12 falhas de Sprint 3-5 que persistem:

| Categoria | Falhas | Sprint 6? |
|-----------|--------|-----------|
| Seed data ausente | 5 | ❌ Não |
| asyncio event loop bug | 2 | ❌ Não |
| FakeRedis sem `setex` | 4 | ❌ Não |
| agents/repo.py coroutine bug | 1 | ❌ Não |

Nenhuma das 12 falhas foi introduzida pelo Sprint 6.

---

## Histórico de rodadas

| Rodada | Veredicto | Motivo |
|--------|-----------|--------|
| R1 | REPROVADO | M_INJECT (arquivo ausente), M1 (12 erros mypy), M3 (71%), M5 (commit ausente) |
| R2 | Escalação | Todos critérios locais PASS; macmini-lablz sem código Sprint 6 |
| R3 | **APROVADO** | Código sincronizado pelo Evaluator; todos staging/smoke PASS |

---

## Próximo passo

**Homologação humana** — ambiente staging pronto.

Execute os cenários em [docs/exec-plans/active/homologacao_sprint-6.md](../docs/exec-plans/active/homologacao_sprint-6.md) usando WhatsApp real e registre o resultado.

Regra do projeto: nenhum sprint avança para o seguinte sem APROVADO na homologação humana.
