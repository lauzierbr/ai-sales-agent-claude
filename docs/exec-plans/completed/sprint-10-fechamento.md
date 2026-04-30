# Sprint 10 — Fechamento

**Data fechamento:** 2026-04-30
**Versão final em staging:** v0.10.13
**Status:** ✅ Concluído (H6/H7 validados via webhook simulado, não via WhatsApp real)

---

## Entregas concluídas

### W1 — Hotfixes não-estruturais
- ✅ B-26: `truncate_preserving_pairs` + `repair_history` em `agents/runtime/_history.py` (shared helper, 3 agentes)
- ✅ B-29: `.decode()` removido em `agents/ui.py` (redis-py >= 5.0 retorna str)
- ✅ B-30: wrapper Langfuse `observability/langfuse_anthropic.py` — generations com tokens/custo reais
- ✅ B-23: áudio via `POST /chat/getBase64FromMediaMessage` (Evolution API retorna 201, não 200 — hotfix v0.10.1)
- ✅ B-24: bloco `## Capacidades de mensagem` nos 3 system prompts
- ✅ B-25: `ranking_vendedores_efos` + defaults de ano + regra de contexto temporal no system prompt

### W2 — Foundations D030
- ✅ Migration 0025: tabela `contacts` + `pedidos.account_external_id` + 6 campos em `commerce_accounts_b2b`
- ✅ `normalize_accounts_b2b` com 6 campos D030 + UPSERT preservando embedding (publish.py)
- ✅ `ContactRepo` + auto-criação `self_registered` + `IdentityRouter` consulta `contacts`
- ✅ Notificação dual ao gestor (WhatsApp + dashboard) com throttle 6h + comando `AUTORIZAR`
- ✅ Dashboard `/contatos` refeito (INSERT em `contacts`, CAST JSONB) + `/clientes` read-only
- ✅ B-28: `confirmar_pedido_em_nome_de` com fallback `commerce_accounts_b2b` + `account_external_id`

### W3 — F-07 Sync EFOS schedule
- ✅ Migration 0026: `sync_schedule` + `gestores.role`
- ✅ APScheduler interno + Redis lock anti-overlap + `/dashboard/sync` admin
- ✅ Feedback visual "Rodar Agora" baseado em estado real do banco (não query string)
- ✅ Migração launchd → APScheduler (`com.jmb.efos-sync.plist.disabled`)

### W4 — Deprecação catalog legado
- ✅ Migration 0027: `commerce_products.embedding vector(1536)` + job `migrate_embeddings.py`
- ✅ `catalog/service.py` + `AgentCliente._buscar_produtos` leem `commerce_products`
- ✅ Removidos: crawler Playwright, EnricherAgent, scheduler_job, painel, template, rotas, playwright dep
- ✅ Migration 0028: DROP `produtos` + `crawl_runs` + `crawl_schedule`

### Hotfixes pós-homologação (v0.10.1 → v0.10.13)

| Versão | Data | Conteúdo |
|--------|------|----------|
| v0.10.0 | 29/04 | Entrega inicial Sprint 10 |
| v0.10.1 | 30/04 | B-23 fix: Evolution HTTP 201 ≠ 200 |
| v0.10.2 | 30/04 | H4: `pedidos.observacao` migration 0029 + B-28 account_external_id no INSERT |
| v0.10.3 | 30/04 | 8 bugs sweep: B-33 CAST JSONB, B-34 perfil normalize, B-35 guard cliente, B-36 ON CONFLICT, B-37 Rodar Agora async, B-38 send_whatsapp kwargs, B-39 KPI mês, B-40 IdentityRouter contacts |
| v0.10.4 | 30/04 | B-34 follow-up: `representante`→`rep` mapping |
| v0.10.5 | 30/04 | B-33 incompleto: SELECT contacts `::jsonb` + tenants/repo |
| v0.10.6 | 30/04 | CSS: `input { width:100% }` quebrava radio/checkbox |
| v0.10.7 | 30/04 | Aba Sync ausente do menu de navegação |
| v0.10.8 | 30/04 | Feedback visual Rodar Agora (iniciado/em andamento/concluído) |
| v0.10.9 | 30/04 | `run_sync()` não aceita `session_factory` kwarg |
| v0.10.10 | 30/04 | Banner sync baseado em `last_triggered_at` (não query string) |
| v0.10.11 | 30/04 | ON CONFLICT 2→3 colunas + migration 0030 indexes order_items/sales_history |
| v0.10.12 | 30/04 | Langfuse: session_id no trace + pricing sonnet/haiku + AgentCliente/Rep → Haiku |
| v0.10.13 | 30/04 | Langfuse: input/output visíveis na UI de Sessions |

### Tags git
- v0.10.0 (inicial), v0.10.1 a v0.10.13 (hotfixes)

---

## Estado do produto em staging (30/04/2026)

- **Versão:** v0.10.13
- **Banco:** migration 0030
- **EFOS sync:** 5 runs (1 success 27/04 com 61.891 rows pré-fix, 1 success 30/04 com 62.461 rows pós-fix B-36)
- **`commerce_*`:** 743 produtos (743/743 com embedding), 614 clientes, 2.592+ pedidos
- **`contacts`:** 0 registros manuais (clientes_b2b estava vazio — sem migração de legado)
- **`sync_schedule`:** jmb → preset diário, APScheduler registrado
- **Langfuse:** sessions operacionais, custo calculado ($0.14/sessão gestor típica)
- **Modelos:** AgentCliente/Rep → `claude-haiku-4-5`; AgentGestor → `claude-sonnet-4-6`

---

## Lições e decisões arquiteturais

### Lição principal — gate de homologação (formalizado)
Sprint 10 exigiu 13 hotfixes em 1 dia de homologação. Causa raiz: smoke gate de "existência" (GETs + COUNT no banco + unit tests com mocks) não captura:
- HTTP status codes reais de APIs externas (B-23: 201 vs 200)
- SQL com colunas inexistentes em banco real (B-28: `observacao`)
- CSS quebrando layout visual (radio/checkbox)
- Formulários que nunca foram submetidos de fato

**Adicionado ao protocolo:**
- `PRE_HOMOLOGATION_REVIEW.md`: Part 1 exige `take_screenshot()` + submit real de cada form; Part 2 exige webhook HMAC multi-turn
- `prompts/evaluator.md`: A_E2E_FORMS + A_REAL_TURN + A_SCHEMA_DRIFT_GUARD obrigatórios
- `prompts/generator.md`: 3 regras novas (mock = realidade verificada; POST real; grep exaustivo do padrão)

### Decisões confirmadas
- `contacts` é write model canônico (D030) — pronto para Bling
- `pedidos.account_external_id` permite remover FK rígida com `clientes_b2b`
- `gestores.role` (admin/gestor) — F-07 admin gate
- Retenção `self_registered` indefinida com throttle 6h
- Plist launchd `.disabled` (remoção no Sprint 11)
- AgentCliente/Rep em Haiku; AgentGestor em Sonnet

---

## Bugs abertos para Sprint 11

### Críticos
Nenhum.

### Altos
| ID | Descrição |
|----|-----------|
| B-01 | Gestor não recebe notificação quando pedido é feito (legacy — ver D030, pode estar resolvido com B-28 fix) |
| B-10 | Pedido criado sem representante mesmo quando cliente tem rep. vinculado |
| B-11 | Agente perde contexto mid-session após troca de persona do número |

### Débitos técnicos
| ID | Descrição |
|----|-----------|
| TD-Sprint10-1 | 5 rotas dashboard sem screenshot de evidência no pre-homolog |
| TD-Sprint10-2 | Whisper não instrumentado no Langfuse ($0.006/min não rastreado) |
| TD | Plist launchd `.disabled` — remover do repo no Sprint 11 |
| TD | `clientes_b2b` legado — deprecar quando confiança total em `contacts` |
| TD | Hide condicional da aba Sync (só para role=admin) — refatorar contexto Jinja |

---

## Para o Planner do Sprint 11

**Estado inicial:**
1. Banco em migration 0030, staging v0.10.13
2. Langfuse operacional — AnalystAgent (D031) pode ler generations reais
3. `contacts` write model pronto — Bling adapter pode usar `WRITE_CONTACTS`
4. AgentCliente/Rep em Haiku — monitorar qualidade nas primeiras semanas
5. Sync EFOS rodando diariamente via APScheduler (13:00 BRT)

**Sprints recomendados:**
- Sprint 11: AnalystAgent MVP (D031) — pré-requisito B-30 ✅ resolvido
- Sprint 12: Bling adapter read-only (D030 completo)

**Pendências de planejamento:**
- Janela de migração JMB EFOS → Bling (thread separada com PO)
- Política de `contacts.self_registered` não autorizados após longo período
- B-01, B-10, B-11 — verificar se D030 resolveu ou agendar hotfix
