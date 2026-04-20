# Homologação Sprint 4 — Gestor/Admin

**Status:** ✅ APROVADO
**Data:** 2026-04-20
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head` (confirmar migration 0015 presente)
- [ ] Seed de dados: `infisical run --env=staging -- python scripts/seed_homologacao_sprint4.py`
- [ ] Smoke gate passou: `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh` → `PASSED`
- [ ] Health check: `curl http://100.113.28.85:8000/health` → versão correta com Sprint 4
- [ ] Secrets configurados no Infisical staging: `DASHBOARD_SECRET`, `DASHBOARD_TENANT_ID`

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Gestor busca clientes por nome
**Resultado:** [x] PASSOU
**Observações:** Bot lista clientes com nome correspondente de qualquer rep; CNPJ exibido.

### H2 — Gestor pede relatório semanal
**Resultado:** [x] PASSOU
**Observações:** Total R$, número de pedidos e ticket médio dos últimos 7 dias retornados corretamente.

### H3 — Gestor pede ranking de representantes
**Resultado:** [x] PASSOU
**Observações:** Lista ordenada por GMV DESC com nomes dos reps.

### H4 — Gestor consulta clientes inativos
**Resultado:** [x] PASSOU
**Observações:** Clientes sem pedido há 30+ dias listados corretamente.

### H5 — Gestor fecha pedido para qualquer cliente (DP-03)
**Resultado:** [x] PASSOU
**Observações:** Pedido criado; PDF enviado; `representante_id` herdado do cliente (DP-03 validado).

### H6 — Isolamento: representante não vira gestor
**Resultado:** [x] PASSOU
**Observações:** AgentRep responde normalmente para número apenas em `representantes`.

### H7 — Isolamento: cliente não vira gestor
**Resultado:** [x] PASSOU
**Observações:** AgentCliente responde normalmente para número apenas em `clientes_b2b`.

### H8 — Dashboard requer autenticação
**Resultado:** [x] PASSOU
**Observações:** Redireciona para `/dashboard/login` sem cookie.

### H9 — Dashboard login funcional
**Resultado:** [x] PASSOU
**Observações:** Login com `DASHBOARD_SECRET` correto → home com KPIs do dia.

### H10 — Dashboard KPIs atualizam automaticamente
**Resultado:** [x] PASSOU
**Observações:** htmx polling 30s atualiza seção de KPIs sem reload.

### H11 — Upload de planilha de preços
**Resultado:** [x] PASSOU
**Observações:** Mensagem de sucesso inline; preços persistidos no banco.

### H12 — Dashboard representantes com GMV
**Resultado:** [x] PASSOU
**Observações:** Tabela com nomes e GMV do mês exibida corretamente.

---

## Bugs encontrados durante homologação (pós-QA)

Todos corrigidos como hotfixes antes do encerramento do sprint:

| # | Descrição | Resolução |
|---|-----------|-----------|
| B1 | Redis history corruption — orphaned `tool_result` → 400 na próxima mensagem | Auto-recovery: detecta 400, limpa chave Redis, retenta |
| B2 | Agentes anunciavam listar/aprovar pedidos sem ter a ferramenta | Adicionado `listar_pedidos_por_status` (Gestor), `listar_pedidos_carteira` (Rep), `listar_meus_pedidos` (Cliente) |
| B3 | `aprovar_pedidos` prometido pelo modelo sem ferramenta real | Implementado `aprovar_pedidos` (Gestor) e `aprovar_pedidos_carteira` (Rep, com validação de carteira) |
| B4 | WhatsApp não renderiza tabelas markdown (`\|`) | Formatação substituída por blocos `*bold* + •` em todos os system prompts |
| B5 | Parâmetro `dias` hardcoded 30 no SQL — não aceitava "últimos 60 dias" | Substituído por `timedelta(days=dias)` em Python em todos os repos e tools |
| B6 | rsync `--relative` copiava para caminho errado no macmini | Substituído por `scp` com destino explícito |
| B7 | Typing indicator: loop gerava "digitando" depois da mensagem chegar | Simplificado para fire-and-forget + `send_typing_stop` só em falha |
| B8 | `send_typing_indicator` bloqueava agente por 5s (ReadTimeout httpx) | Convertido para `asyncio.create_task` (fire-and-forget) |

---

## Resultado final

**Veredicto:** ✅ APROVADO
**Data:** 2026-04-20
**Executado por:** Lauzier
**Tag:** v0.5.0
