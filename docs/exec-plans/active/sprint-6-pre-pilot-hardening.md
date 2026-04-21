# Sprint 6 — Pre-Pilot Hardening

**Status:** 🔄 Em planejamento
**Data início:** 2026-04-21
**Spec:** `artifacts/spec.md`
**Base:** `docs/exec-plans/active/pre-pilot-hardening.md`
**Versão alvo:** v0.6.1-rc1

---

## Objetivo

Liberar um baseline pré-piloto em que o gestor da JMB consiga operar o dashboard sem blockers reais e a aplicação tenha o hardening operacional mínimo para não falhar em silêncio.

---

## Blockers que vêm primeiro

Os quatro itens abaixo são prioridade absoluta. Nenhum hardening mais amplo entra antes deles:

- [ ] **B1 — Cadastro de cliente quebrado**
  `POST /dashboard/clientes/novo` depende de `TenantService.criar_cliente_ficticio(...)`, inexistente hoje.
- [ ] **B2 — Upload de preços quebrado**
  `POST /dashboard/precos/upload` chama um método inexistente no `CatalogService` atual.
- [ ] **B3 — Top produtos com fluxo incompleto**
  A tela existe, mas a navegação é incompleta e o template ainda aponta retorno para `/dashboard`.
- [ ] **B4 — Queries do dashboard precisam revisão de isolamento**
  Ainda há SQL no dashboard com risco de join sem vínculo explícito por `tenant_id`.

**Regra do sprint:** B1-B4 resolvidos antes de E5-E9.

---

## Escopo por fase

### Fase 0 — Funcionalidade real do gestor

- [ ] **E1 — Cadastro de cliente via dashboard**
  Implementar o contrato completo do fluxo `GET/POST /dashboard/clientes/novo`, com validação mínima de CNPJ, duplicidade por tenant e verificação de `representante_id`.
- [ ] **E2 — Upload de preços via dashboard**
  Corrigir o endpoint para usar o contrato real do catálogo e devolver feedback inline útil para sucesso/erro.
- [ ] **E3 — Top produtos: fluxo e navegação**
  Dar entrada visível na UI, corrigir link de retorno e validar filtros `dias`/`limite`.
- [ ] **E4 — Revisão de queries do dashboard**
  Revisar todas as queries tocadas nesta fase e corrigir joins/filters que ainda possam vazar tenant.

### Fase 1 — Hardening operacional mínimo

- [ ] **E5 — Startup validation**
  Falar cedo quando secrets/configs críticas estiverem ausentes; não aceitar piloto com app subindo "meio quebrado".
- [ ] **E6 — Rate limiting no login do dashboard**
  Bloquear brute force básico sem reescrever auth.
- [ ] **E7 — Rate limiting no webhook WhatsApp**
  Conter burst abusivo sem quebrar o processamento normal.
- [ ] **E8 — Health/monitoramento Anthropic**
  Tornar falha transiente vs falha definitiva observável em `/health` e no `health_check.py`.
- [ ] **E9 — CORS/cookie por ambiente**
  Sair do wildcard global e ajustar `Secure` do cookie conforme o ambiente real.

### Fase 2 — Baseline de qualidade e go/no-go

- [ ] **E10 — Expansão de testes do dashboard**
  Cobrir os fluxos críticos em unit + staging, com foco explícito em isolamento de tenant.
- [ ] **E11 — Smoke e homologação pré-piloto**
  Fechar um smoke gate executável e um checklist humano para liberar o piloto controlado.

---

## Gates de go/no-go

### G0 — Dashboard funcional

- [ ] `POST /dashboard/clientes/novo` funcional
- [ ] `POST /dashboard/precos/upload` funcional
- [ ] `GET /dashboard/top-produtos` funcional
- [ ] navegação autenticada sem link quebrado para esses fluxos

### G1 — Isolamento e hardening mínimo

- [ ] queries corrigidas do dashboard filtram por `tenant_id`
- [ ] startup falha se secret/config crítica estiver ausente
- [ ] rate limiting ativo em `/dashboard/login`
- [ ] rate limiting ativo em `/webhook/whatsapp`
- [ ] `/health` expõe estado Anthropic (`ok/degraded/fail`)
- [ ] CORS não usa wildcard em `staging`/`production`

### G2 — Qualidade verificável

- [ ] `pytest -m unit` verde
- [ ] testes novos cobrem cadastro, upload, top produtos e casos negativos de tenant
- [ ] `lint-imports` verde
- [ ] smoke de staging do sprint verde

### G3 — Go/no-go pré-piloto

- [ ] checklist humano de homologação atualizado
- [ ] cenários críticos do gestor passam em staging
- [ ] nenhum blocker aberto em B1-B4

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
