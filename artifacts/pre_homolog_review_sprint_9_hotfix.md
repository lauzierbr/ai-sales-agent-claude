# Pre-Homologation Review — Sprint 9 Hotfix v0.9.1

**Data:** 2026-04-28
**Versão deployada:** v0.9.1 (commit `5dc5021`)
**Executado por:** Claude (Opus 4.7) via Chrome DevTools MCP
**Protocolo:** `docs/PRE_HOMOLOGATION_REVIEW.md`

---

## Pré-condições — PASS

- [x] App em staging respondendo: `GET /health → {"version":"0.9.1","status":"ok"}`
- [x] `commerce_products` populado (743 produtos), `commerce_accounts_b2b` (614),
      `commerce_orders` (2.592), `commerce_order_items` (29.433),
      `commerce_vendedores` (24)
- [x] 4 sync_runs no histórico, 1 success com 61.891 registros publicados
- [x] pytest -m unit local: 386 passed, 0 failed
- [x] lint-imports: 7 contracts kept, 0 broken

---

## Parte 1 — Dashboard (10 rotas via Chrome DevTools MCP)

| # | Rota | Esperado | Observado | Status |
|---|------|----------|-----------|--------|
| 1 | `/dashboard/home` | KPIs reais + sync EFOS visível | GMV R$ 2.106.925,14 ; 2592 pedidos ; ticket R$ 812.86 ; sync "OK 27/04/2026 17:42 • 61891 registros" ; 11 pedidos recentes | **PASS** |
| 2 | `/dashboard/pedidos` | ~50 pedidos com cliente real | 50 rows: "3113 LUNA & MARTINS LTDA. R$ 1607.45", "3112 DROGARIA ARTHUR FERREIRA…" etc | **PASS** |
| 3 | `/dashboard/conversas` | ≥ 1 conversa de teste | 1 row (gestor 6177) | **PASS** |
| 4 | `/dashboard/contatos` | 3 contatos cadastrados (Lauzier, Ronaldo, Rondinele) | 3 rows | **PASS** |
| 5 | `/dashboard/clientes` | 100+ clientes do EFOS com nome de rep via JOIN | 100 rows: "ADRIANA ELOISA RIBEIRO ... RONDINELE RITTER DIAS sim" etc | **PASS** |
| 6 | `/dashboard/precos` | UI de upload Excel | UI renderiza | **PASS** |
| 7 | `/dashboard/feedbacks` | 4 feedbacks históricos | 4 rows | **PASS** |
| 8 | `/dashboard/top-produtos` | Top N produtos vendidos com nomes reais | 10 rows: "1 CHAVEIRO PERSONAGENS 1011 R$ 9048.45", "2 FIO DENT 100M HILLO 170 R$ 1006.40" etc | **PASS** |
| 9 | `/dashboard/representantes` | 24 reps com GMV agregado + link no menu | 24 rows: "1 RONALDO PINTO DE MORAIS 32 R$ 29911.06" etc; menu agora exibe link "Representantes" | **PASS** |
| 10 | `/dashboard/configuracoes` | Tenant info | jmb / JMB Distribuidora / 00.000.000/0001-00 | **PASS** |

**Resultado Dashboard:** 10/10 rotas PASS.

---

## Parte 2 — Bot

Não foi executado simulação real de webhook nesta rodada. Validação de bot é
deferida para a homologação manual humana (Lauzier via WhatsApp), com atenção
especial aos bugs B-13, B-14, B-15 e B-22 que foram corrigidos no hotfix.

**Cenários a validar manualmente na homologação:**

- Cliente: "EAN 7898923148571" → produto encontrado (B-13)
- Gestor: "lista de clientes inativos" → ≥ 1 resultado de `commerce_accounts_b2b` (B-15)
- Gestor: "quais os representantes" → tool nova `listar_representantes` (24 reps EFOS) (B-15)
- Gestor: "lista pedidos pendentes" → fallback `commerce_orders` (B-14)
- Qualquer persona: nenhuma resposta com emoji 😊👇🏆👋 (B-22)

---

## Parte 3 — Invariantes históricos

- **B-13 EAN search** — código corrigido em `_buscar_produtos` dos 3 agentes (Sprint 9 original); validação manual no WhatsApp pendente
- **Feedback "Não usar emojis" (20/04)** — system prompt dos 3 agentes em `agents/config.py` bloco "Regra de linguagem (prioridade máxima)" proibindo emojis; validação manual no WhatsApp pendente
- **B-10/B-11/B-12** (Sprint 8) — tests/regression cobrem; sem regressão em pytest

---

## Bugs corrigidos (do BUGS.md)

| Bug | Status |
|-----|--------|
| B-14 listar_pedidos_por_status fallback commerce_orders | RESOLVIDO via dashboard (mostra 50) e agent_gestor; validação WhatsApp pendente |
| B-15 listar_representantes tool + JOIN cliente×rep | RESOLVIDO no dashboard `/clientes` (JOIN funcionando); tool agente pendente WhatsApp |
| B-16 dashboard /clientes fallback commerce_accounts_b2b | RESOLVIDO — 100 rows |
| B-17 dashboard /pedidos fallback commerce_orders | RESOLVIDO — 50 rows com cliente_nome via JOIN |
| B-18 home sync_info no contexto inicial | RESOLVIDO — bloco mostra "OK 27/04/2026 17:42 • 61891 registros" |
| B-19 home KPIs fallback commerce_orders | RESOLVIDO — GMV/Pedidos/Ticket reais |
| B-20 top_produtos fallback + nome via JOIN commerce_products | RESOLVIDO — 10 rows com nomes reais |
| B-21 dashboard /representantes nav menu + fallback | RESOLVIDO — 24 reps com GMV; link no menu |
| B-22 emojis proibidos nos system prompts | RESOLVIDO no código; validação WhatsApp pendente |

---

## Iterações de correção desta rodada

A revisão exploratória inicial encontrou bugs que o smoke gate de endpoints
não pegava. O hotfix passou por **4 iterações** de correção:

1. **v0.9.1 inicial** — Generator implementou fallbacks mas usou nomes EFOS (`pe_numeropedido`, `vendedor_nome`, `ve_situacaovendedor`) que não existem em `commerce_*`
2. **Iteração SQL #1** — corrigido `pe_numeropedido` → `numero_pedido`, removido `ve_situacaovendedor` (coluna inexistente), JOIN explícito em commerce_vendedores para `representante_nome`, qualificação `a.external_id` por ambiguidade
3. **Iteração SQL #2** — `commerce_orders.cliente_nome` e `commerce_order_items.produto_nome` vêm NULL do EFOS; adicionado `LEFT JOIN commerce_accounts_b2b/commerce_products` + `COALESCE(NULLIF(...,''), ..., código)` para fallback
4. **Iteração SQL #3** — bug pré-existente: `top_produtos` SQL primária usava `ip.produto_nome` mas tabela `itens_pedido` tem coluna `nome_produto` (e `subtotal` em vez de `preco_unitario * quantidade`). Só apareceu agora com `itens_pedido` vazio e fallback ativo expondo o exception silencioso.

**Lição reforçada do gotcha `efos_schema_field_names`:** o Generator (Sonnet 4.6)
falhou em conferir o schema real das tabelas commerce/legadas antes de escrever
SQL, mesmo com o gotcha registrado em `docs/GOTCHAS.yaml`. Uma evolução do
prompt para forçar o grep do `information_schema.columns` antes de qualquer SQL
seria útil.

---

## Veredicto

**PASS — Pronto para homologação humana**

10/10 rotas do dashboard mostram dados reais do EFOS via fallback `commerce_*`.
KPIs reais. Sync status visível. Listagens populadas com nomes de clientes,
representantes e produtos.

**Próximo passo:** Lauzier executa cenários de bot via WhatsApp para validar
B-13, B-14, B-15 e B-22 com agentes reais.
