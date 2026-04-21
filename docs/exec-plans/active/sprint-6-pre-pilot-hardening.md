# Sprint 6 — Pre-Pilot Hardening

**Status:** ✅ Implementado — aguardando homologação manual
**Data início:** 2026-04-21
**Spec:** `artifacts/spec.md`
**Base:** `docs/exec-plans/active/pre-pilot-hardening.md`
**Versão alvo:** v0.7.0-rc1 (commit 43f7302)
**QA:** APROVADO código local — staging pendente deploy (ver qa_sprint_6_r2.md)

---

## Objetivo

Liberar um baseline pré-piloto em que o gestor da JMB consiga operar o dashboard sem blockers reais e a aplicação tenha o hardening operacional mínimo para não falhar em silêncio.

---

## Blockers que vêm primeiro

Os quatro itens abaixo são prioridade absoluta. Nenhum hardening mais amplo entra antes deles:

- [x] **B1 — Cadastro de cliente quebrado** ✅
  `TenantService.criar_cliente_ficticio()` implementado; `POST /dashboard/clientes/novo` funcional.
- [x] **B2 — Upload de preços quebrado** ✅
  `POST /dashboard/precos/upload` usa `CatalogService.processar_excel_precos()` com feedback inline.
- [x] **B3 — Top produtos com fluxo incompleto** ✅
  Navegação corrigida; link "Voltar" aponta para `/dashboard/home`.
- [x] **B4 — Queries do dashboard precisam revisão de isolamento** ✅
  Todas as 9 queries corrigidas com filtro explícito de `tenant_id`.

**Regra do sprint:** B1-B4 resolvidos antes de E5-E9.

---

## Escopo por fase

### Fase 0 — Funcionalidade real do gestor

- [x] **E1 — Cadastro de cliente via dashboard** ✅
- [x] **E2 — Upload de preços via dashboard** ✅
- [x] **E3 — Top produtos: fluxo e navegação** ✅
- [x] **E4 — Revisão de queries do dashboard** ✅

### Fase 1 — Hardening operacional mínimo

- [x] **E5 — Startup validation** ✅ — `_validate_secrets()` lista 9 secrets; RuntimeError no boot
- [x] **E6 — Rate limiting no login do dashboard** ✅ — 5 falhas/IP/15min → HTTP 429
- [x] **E7 — Rate limiting no webhook WhatsApp** ✅ — 30/min/instance+jid → HTTP 429
- [x] **E8 — Health/monitoramento Anthropic** ✅ — `/health` ok/degraded/fail; health_check.py exit ≠ 0
- [x] **E9 — CORS/cookie por ambiente** ✅ — sem wildcard em staging; Secure=True apenas em production

### Fase 2 — Baseline de qualidade e go/no-go

- [x] **E10 — Expansão de testes do dashboard** ✅ — 281 unit tests; test_ui_injection.py; test_dashboard_pre_pilot.py
- [x] **E11 — Smoke e homologação pré-piloto** ✅ — smoke_sprint_6.py (G1–G9) + seed_homologacao_sprint-6.py entregues

---

## Gates de go/no-go

### G0 — Dashboard funcional

- [x] `POST /dashboard/clientes/novo` funcional ✅
- [x] `POST /dashboard/precos/upload` funcional ✅
- [x] `GET /dashboard/top-produtos` funcional ✅
- [x] navegação autenticada sem link quebrado ✅

### G1 — Isolamento e hardening mínimo

- [x] queries corrigidas do dashboard filtram por `tenant_id` ✅
- [x] startup falha se secret/config crítica estiver ausente ✅
- [x] rate limiting ativo em `/dashboard/login` ✅
- [x] rate limiting ativo em `/webhook/whatsapp` ✅
- [x] `/health` expõe estado Anthropic (`ok/degraded/fail`) ✅
- [x] CORS não usa wildcard em `staging`/`production` ✅

### G2 — Qualidade verificável

- [x] `pytest -m unit` verde — 281 passed ✅
- [x] testes novos cobrem cadastro, upload, top produtos e casos negativos de tenant ✅
- [x] `lint-imports` verde ✅
- [ ] smoke de staging do sprint verde — **pendente deploy no mac-lablz**

### G3 — Go/no-go pré-piloto

- [x] checklist humano de homologação atualizado ✅
- [ ] cenários críticos do gestor passam em staging — **pendente homologação manual**
- [x] nenhum blocker aberto em B1-B4 ✅

---

## Dependências

| Dependência | Tipo | Impacto se faltar |
|-------------|------|-------------------|
| Branch/base do Sprint 5 estável | código | impossibilita fechar B1-B3 em cima do dashboard atual |
| `DASHBOARD_SECRET`, `JWT_SECRET`, `DASHBOARD_TENANT_ID` | config | login do dashboard não pode ser validado |
| `POSTGRES_URL` e `REDIS_URL` válidos | infra | rate limit, tenant isolation e smoke ficam inválidos |
| `ANTHROPIC_API_KEY` válida | integração | health check não consegue diferenciar ambiente saudável de falha definitiva |
| Seed com representante, pedidos confirmados e planilha de teste | dados | smoke e homologação de dashboard ficam bloqueados |

---

## Riscos principais

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Dataset de staging não sustenta os cenários de top produtos | Média | Alto | exigir `seed_homologacao_sprint-6.py` como pré-condição do smoke |
| Rate limiting bloquear uso legítimo do dashboard ou webhook | Média | Médio | usar defaults fixos, mas configuráveis por ambiente e cobertos por teste |
| Fallback silencioso de tenant continuar mascarando bug | Alta | Alto | tornar `DASHBOARD_TENANT_ID` obrigatório no startup |
| Health Anthropic virar só um check superficial de env | Média | Alto | exigir classificação por tipo de erro e saída não-zero no `health_check.py` quando `fail` |

---

## Sequência sugerida de execução

1. Corrigir `clientes/novo`
2. Corrigir `precos/upload`
3. Corrigir fluxo/navegação `top-produtos`
4. Revisar queries do dashboard tocadas nos itens 1-3
5. Fechar testes unitários dos fluxos funcionais
6. Implementar startup validation
7. Implementar rate limiting do login
8. Implementar rate limiting do webhook
9. Expor health Anthropic
10. Ajustar CORS/cookie por ambiente
11. Fechar staging tests, smoke e homologação

---

## Escopo explicitamente fora

- Novo modelo de usuários do dashboard
- Refactor arquitetural grande do dashboard
- Endurecimento geral de todos os endpoints da plataforma
- Testes de carga/performance além do smoke gate
- Novas features de produto no dashboard

---

## Saída esperada do sprint

Ao final deste sprint, o projeto deve sair de:

- dashboard parcialmente quebrado e operação frágil

para:

- dashboard do gestor funcional nos três fluxos críticos e baseline operacional mínimo suficiente para um piloto controlado com a JMB

---

## Handoff

- Smoke gate do sprint: `scripts/smoke_sprint_6.py`
- Checklist humano: `docs/exec-plans/active/homologacao_sprint-6.md`
- Sem APROVADO na homologação, o Sprint 6 não é considerado encerrado

---

## Log de rodadas QA

### Rodada 1 — 2026-04-21 — REPROVADO
- M_INJECT: `test_ui_injection.py` inexistente (estava em `test_dashboard_pre_pilot.py`)
- M3: `tenants/service.py` 71% coverage (< 80%)
- M5: `commit.assert_called` ausente nos testes de TenantService e CatalogService
- M1: 12 erros mypy (`Returning Any` no Redis, `dict` sem type args, `type: ignore` unused)
- A_SMOKE quality: smoke_sprint_6.py com gaps (GET em vez de POST, sem burst webhook)

### Rodada 1 de correção — 2026-04-21
- Criado `test_ui_injection.py` com 3 testes (AgentGestor, AgentCliente, AgentRep)
- Adicionados 6 testes em `tenants/test_service.py` → 100% coverage
- Adicionado `test_processar_excel_precos_commit_chamado` em `catalog/test_service.py`
- Corrigidos: `bool(count > MAX)`, `int(count)`, 9× `dict[str, Any]`, removido `# type: ignore` unused
- Smoke reescrito: G7 POST xlsx, G8 POST clientes/novo+verify, G9 burst webhook 429

### Rodada 2 — 2026-04-21 — ESCALADO (código aprovado, staging não sincronizado)
- Todos os checks locais PASS: 281 unit tests, mypy 0 erros, todos Média PASS
- Bloqueio: mac-lablz estava no commit `5355ee8` (Sprint 5-hotfix); Sprint 6 nunca deployado
- 12 falhas staging são regressões de Sprint 3-5, não do Sprint 6
- Usuário escolheu: prosseguir para homologação manual após deploy

### Próximos passos
1. `./scripts/deploy.sh staging` no mac-lablz
2. `infisical run --env=staging -- python scripts/seed_homologacao_sprint-6.py`
3. `infisical run --env=staging -- python scripts/smoke_sprint_6.py` → ALL OK
4. Homologação manual H1–H7 no checklist
5. Se APROVADO: criar tag v0.7.0 + mover este arquivo para `docs/exec-plans/completed/`
