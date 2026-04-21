# QA Report — Sprint 6 — Pre-Pilot Hardening — REPROVADO (Escalação)

**Data:** 2026-04-21
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md
**Rodada:** 2 de 2 — escalado ao usuário

---

## Veredicto

**REPROVADO — rodada 2 de 2 → ESCALADO AO USUÁRIO**

O Generator não tem mais rodadas de correção automática.
O usuário deve decidir o próximo passo antes de qualquer ação.

**Motivo resumido:** Todo o código local está correto (273 unit tests PASS, todos os critérios de Média PASS). O bloqueio é infraestrutura: Sprint 6 nunca foi sincronizado para o mac-lablz. Os testes staging específicos do sprint (`test_dashboard_pre_pilot.py`, `test_ui_injection.py`) não existem na máquina de staging, logo não foi possível executar o contrato de staging conforme exigido pelo evaluator.md: *"Nunca: Aprovar sem evidência de testes executados (incluindo smoke gate)"*.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -rn "sk-ant\|api_key=..." output/src/` | **PASS** — 0 resultados |
| Passwords hardcoded | `grep -rn "password=..." output/src/` | **PASS** — 0 resultados |
| print() proibido | `grep -rn "print(" output/src/` (excl. testes) | **PASS** — 0 resultados |
| import-linter | `PYTHONPATH=output .venv/bin/lint-imports` | **PASS** — 5/5 KEPT, 0 violações |
| pytest unit | `.venv/bin/python -m pytest -m unit output/src/tests/unit/` | **PASS** — 273 passed, 0 falhas |
| pytest staging | `pytest -m staging` (mac-lablz) | **FAIL** — 12 falhas / 17 pass / 3 skip (ver categorização abaixo) |
| M_INJECT | `pytest test_ui_injection.py` (mac-lablz) | **FAIL** — arquivo não existe no mac-lablz |
| smoke gate A_SMOKE | `smoke_sprint_6.py` (mac-lablz) | **NÃO EXECUTADO** — código não deployado |
| smoke gate A10 | `smoke_ui.sh` (mac-lablz) | **NÃO EXECUTADO** — código não deployado |

---

## Critérios de Alta

### A1–A9 — Todos os critérios de funcionalidade
**Status:** PASS (validados por 273 unit tests em rodada local)
- A1 [B1-CLIENTE-NOVO]: PASS | A2 [B2-PRECOS-UPLOAD]: PASS | A3 [B3-TOP-PRODUTOS]: PASS
- A4 [B4-TENANT-ISOLATION]: PASS | A5 [E5-STARTUP]: PASS | A6 [E6-RATE-LOGIN]: PASS
- A7 [E7-RATE-WEBHOOK]: PASS | A8 [E8-HEALTH-ANTHROPIC]: PASS | A9 [E9-CORS]: PASS

### A10 — [G4-SMOKE-UI] Todas as rotas do dashboard retornam 200
**Status:** NÃO EXECUTADO
**Motivo:** `scripts/smoke_ui.sh` existe no repositório ✅, mas o app não está rodando no mac-lablz com código do Sprint 6. Mac-lablz está no commit `5355ee8` (Sprint 5-hotfix). Sprint 6 não foi sincronizado.

### A_SMOKE — Smoke gate staging
**Status:** NÃO EXECUTADO
**Motivo:** `scripts/smoke_sprint_6.py` existe e foi atualizado com G7/G8/G9 ✅, mas não foi executado. Mac-lablz não tem Sprint 6.
**Nota positiva:** O script agora é completo — inclui `check_precos_upload` (POST real com fixture), `check_cliente_novo` (POST + verificação na lista) e `check_webhook_burst_429` (32 eventos → 429). A cobertura do gap apontado na rodada 1 foi corrigida.

---

## Critérios de Média

### M1 — [TYPE-HINTS]
**Status:** PASS
**Evidência:** `mypy --strict` nos 5 arquivos do Sprint 6 → 0 erros em escopo do sprint. Erros reportados são em arquivos pre-existentes não modificados no sprint (agents/runtime/*, orders/repo.py).

### M2 — [DOCSTRINGS]
**Status:** PASS (inspeção de código — docstrings presentes nas funções públicas)

### M3 — [COVERAGE-UNIT]
**Status:** PASS
**Evidência:**
```
output/src/catalog/service.py   85%  ✅
output/src/tenants/service.py  100%  ✅  (era 71% na rodada 1)
```

### M5 — [COMMIT-SERVICE]
**Status:** PASS
**Evidência:**
```
tests/unit/tenants/test_service.py:318  session.commit.assert_called()  ✅
tests/unit/catalog/test_service.py:272  mock_session.commit.assert_called()  ✅
```

### M_INJECT — Injeção de dependências
**Status:** PASS local / NÃO EXECUTADO em staging
**Arquivo local:** `output/src/tests/staging/agents/test_ui_injection.py` ✅ existe com 3 testes (AgentGestor, AgentCliente, AgentRep)
**Arquivo no mac-lablz:** NÃO EXISTE (código não sincronizado)
**Execução staging:** IMPOSSÍVEL — `pytest test_ui_injection.py` retornou "file or directory not found" no mac-lablz

---

**Resumo de Média:** 0 falhas confirmadas de 5 critérios. Threshold: 1. **Dentro do threshold** — o problema não é qualidade de código.

---

## Análise das falhas de staging (categorização)

O `pytest -m staging` rodou no mac-lablz com código PRE-Sprint 6 (commit `5355ee8`). As 12 falhas são:

| Categoria | Falhas | Causa raiz | Sprint 6? |
|-----------|--------|------------|-----------|
| Seed data ausente no staging DB | 5 | Precisa `seed_homologacao_sprint-3.py`; telefones desatualizados; cliente H4 não existe | ❌ Não |
| asyncio event loop bug | 2 | `Task got Future attached to a different loop` — bug pre-existente em fixtures de Sprint 3/4 | ❌ Não |
| FakeRedis sem `setex` | 4 | `'_FakeRedis' object has no attribute 'setex'` — bug pre-existente em Sprint 5 multiturn tests | ❌ Não |
| agents/repo.py:706 bug | 1 | `'coroutine' object has no attribute 'all'` — pre-existente na repo do gestor | ❌ Não |
| **Sprint 6 staging** | 0 | Não coletados — código não deployado | ❌ Não executados |

**Conclusão:** Nenhuma das 12 falhas foi introduzida pelo Sprint 6. São todas regressões pre-existentes de sprints anteriores.

---

## Comparativo de rodadas

| Critério | Rodada 1 | Rodada 2 |
|----------|----------|----------|
| Secrets / print() | PASS | PASS |
| import-linter | PASS | PASS |
| pytest unit | PASS (266) | PASS (273 +7 novos) |
| M_INJECT arquivo | FAIL — não existia | PASS local / NÃO EXECUTADO staging |
| M3 tenants/service.py | FAIL 71% | PASS 100% |
| M5 commit.assert_called | FAIL — ausente | PASS — adicionado |
| M1 mypy sprint files | FAIL 12 erros | PASS 0 erros |
| smoke_sprint_6.py cobertura | FAIL — gaps | PASS local — G7/G8/G9 adicionados |
| Staging executado | CANNOT RUN | FAIL — código não no mac-lablz |
| A_SMOKE executado | CANNOT RUN | NÃO EXECUTADO |

Falhas persistentes após correção: **nenhuma falha de código** — bloqueio é infraestrutura.
Melhorias confirmadas: M_INJECT, M3, M5, M1, smoke_sprint_6.py — todos corrigidos.

---

## Situação para o usuário

**O código está pronto.** Todos os checks de qualidade que podem ser executados localmente passam. O bloqueio é operacional:

1. **Mac-lablz está 3 commits atrás** (no `5355ee8`, Sprint 5-hotfix). O Sprint 6 nunca foi sincronizado.
2. **Testes staging e smoke gate não podem ser executados** enquanto o código não estiver no mac-lablz.
3. **Pre-existing staging failures:** 12 falhas em testes de Sprint 3-5 que já existiam antes do Sprint 6 — não são regressões.

**Opções para o usuário:**

**Opção A — Sincronizar e re-avaliar (recomendado):**
```bash
# No mac-lablz, sincronizar código do Sprint 6:
cd ~/ai-sales-agent-claude && git pull
# Depois re-executar avaliação staging/smoke
```
E aprovar o Evaluator a fazer uma nova rodada de staging (decisão do usuário — é a terceira avaliação, fora do protocolo padrão de 2 rodadas).

**Opção B — Aceitar código e prosseguir para homologação manual:**
Se o usuário confia nos checks locais (273 unit tests PASS, todos Média PASS), pode aceitar o sprint condicionalmente e ir direto para a homologação humana com base no smoke gate rodando manualmente após sincronização.

**Opção C — Escalar para o Generator sincronizar e entregar staging funcional:**
O Generator deve: (1) sincronizar código para mac-lablz via `git pull` + `deploy.sh staging`, (2) rodar `seed_homologacao_sprint-6.py`, (3) confirmar que `smoke_sprint_6.py` retorna ALL OK antes de repassar ao Evaluator.

---

## Como reproduzir após sincronização

```bash
# Após `git pull` no mac-lablz:
ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
  infisical run --env=staging -- /Users/dev/ai-sales-agent-claude/.venv/bin/python \
  -m pytest -m staging src/tests/staging/agents/test_dashboard_pre_pilot.py \
  src/tests/staging/agents/test_ui_injection.py -v --tb=short"

ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
  infisical run --env=staging -- python ../scripts/smoke_sprint_6.py"

ssh macmini-lablz "cd ~/ai-sales-agent-claude/output && \
  infisical run --env=staging -- bash ../scripts/smoke_ui.sh"
```
