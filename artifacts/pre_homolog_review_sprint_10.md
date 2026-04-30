# Pre-Homologation Review — Sprint 10

**Status:** PENDENTE DE EXECUCAO EM STAGING
**Data:** 2026-04-29
**Protocolo:** docs/PRE_HOMOLOGATION_REVIEW.md

---

## Como executar

```bash
ssh macmini-lablz
cd ~/MyRepos/ai-sales-agent-claude
infisical run --env=staging -- python scripts/smoke_sprint_10.py
```

---

## A. 10 Rotas do Dashboard (A_BEHAVIORAL_UI)

| # | Rota | Criterio | Status |
|---|------|----------|--------|
| D1 | /dashboard/home | Carrega sem erro; KPIs visiveis | PENDENTE |
| D2 | /dashboard/pedidos | Lista pedidos EFOS; nao vazio | PENDENTE |
| D3 | /dashboard/clientes | Sem botao "Novo Cliente"; 614 clientes visiveis | PENDENTE |
| D4 | /dashboard/contatos | Badge "Pendentes" visivel quando ha contacts nao-autorizados | PENDENTE |
| D5 | /dashboard/contatos (criar) | POST cria em contacts (nao clientes_b2b); aparece na listagem | PENDENTE |
| D6 | /dashboard/sync (admin) | Presets visiveis; salvar muda proxima execucao; "Rodar Agora" cria sync_run | PENDENTE |
| D7 | /dashboard/sync (gestor nao-admin) | Retorna 403 | PENDENTE |
| D8 | /dashboard/representantes | Lista 24 reps do EFOS | PENDENTE |
| D9 | /dashboard/configuracoes | Carrega sem erro | PENDENTE |
| D10 | /dashboard/logout | Encerra sessao; redireciona para login | PENDENTE |

---

## B. Cenarios de Bot (A_BEHAVIORAL_AGENT)

| # | Cenario | Criterio | Status |
|---|---------|----------|--------|
| B1 | Cliente envia audio | Bot responde com base no texto transcrito (prefixo "Ouvi:") | PENDENTE |
| B2 | Cliente: "voce ouve audio?" | Bot confirma capacidade | PENDENTE |
| B3 | Gestor faz >= 6 tool calls | Historico mantido; log historico_corrompido_recovery ausente | PENDENTE |
| B4 | Gestor: "melhor vendedor de marco" | 1 tool call ranking_vendedores_efos; ano 2026 na resposta | PENDENTE |
| B5 | Gestor pede pedido em nome de cliente EFOS | Pedido criado; PDF emitido; sem mensagem tecnica | PENDENTE |
| B6 | Numero desconhecido envia "oi" | Recebe "vou avisar o gestor"; gestor recebe notificacao WhatsApp | PENDENTE |
| B7 | Gestor responde AUTORIZAR +55... | contacts.authorized=true; proxima msg do numero processada normalmente | PENDENTE |

---

## C. Smoke Gate (A_SMOKE)

Script: `scripts/smoke_sprint_10.py`

| # | Verificacao | Status |
|---|-------------|--------|
| S1 | GET /health retorna version=0.10.0 | PENDENTE |
| S2 | alembic current em 0028 | PENDENTE |
| S3 | contacts WHERE origin='manual' >= 5 | PENDENTE |
| S4 | commerce_accounts_b2b WHERE telefone IS NOT NULL >= 900 | PENDENTE |
| S5 | commerce_products WHERE embedding IS NOT NULL >= 700 | PENDENTE |
| S6 | sync_schedule.enabled=true para jmb | PENDENTE |
| S7 | APScheduler lista job EFOS | PENDENTE |
| S8 | produtos nao existe (does not exist) | PENDENTE |
| S9 | Trace Langfuse com usage.input_tokens > 0 | PENDENTE |
| S10 | /dashboard/contatos retorna 200 | PENDENTE |
| S11 | /dashboard/clientes sem "Novo Cliente" | PENDENTE |
| S12 | /dashboard/sync: 200 admin, 403 nao-admin | PENDENTE |

---

## RESULTADO FINAL

**Status:** PENDENTE — Executar smoke gate e navegacao manual em staging antes de invocar Evaluator.

Para marcar como PASS: executar smoke_sprint_10.py com saida "ALL OK" + navegar as 10 rotas + verificar 7 cenarios de bot.
