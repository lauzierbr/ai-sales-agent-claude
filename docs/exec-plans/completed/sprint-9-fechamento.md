# Sprint 9 — Fechamento

**Data fechamento:** 2026-04-29
**Versão final em staging:** v0.9.4
**Status:** ✅ Concluído com bugs abertos para Sprint 10

---

## Entregas concluídas

### Original (planejado)

- ✅ B-13 hotfix: busca por EAN completo (`query[-6:]` para queries numéricas > 6 dígitos)
- ✅ Migração leituras catalog → `commerce_products` (com fallback)
- ✅ Migração leituras agents → `commerce_accounts_b2b` (com fallback)
- ✅ Dashboard bloco "Última sincronização EFOS" (depois removido em v0.9.4 — info migrou para card "Atualizado em")
- ✅ Áudio WhatsApp via Whisper (parcial — funcional para dev, falha em produção por conteúdo criptografado E2E — ver B-23)
- ✅ AgentGestor: 3 tools EFOS (relatorio_vendas_representante, relatorio_vendas_cidade, listar_clientes_inativos)
- ✅ E0-A: migration 0024 `pedidos.ficticio` + watermark PDF + caption ⚠️ TESTE
- ✅ E0-B: tools antigas removidas, EFOS assumiu lugar
- ✅ Convenção de versionamento `v0.{SPRINT}.{HOTFIX}` + auto-tag deploy
- ✅ Badge de versão no dashboard

### Hotfixes pós-homologação (v0.9.1 → v0.9.4)

| Versão | Data | Conteúdo |
|--------|------|----------|
| v0.9.0 | 27/04 22:00 | Entrega inicial Sprint 9 |
| v0.9.1 | 28/04 09:30 | Migração exaustiva — corrige B-14, B-15, B-16, B-17, B-19, B-20, B-21 (queries em tabelas legadas vazias após reset); B-18 (sync-status); B-22 (emojis no system prompt) |
| v0.9.2 | 29/04 ~13:00 | B-31: formatação monetária pt-BR (`R$ 1.234,56` em vez de `R$ 1234.56`) — função central + filter Jinja |
| v0.9.3 | 29/04 ~13:50 | B-32: KPIs HOJE não inflam com histórico EFOS — removido fallback `efos_total` |
| v0.9.4 | 29/04 ~14:00 | UX KPIs: janela mensal + "Atualizado no sync EFOS" + remoção do bloco redundante |

### Tags git
- v0.7.0, v0.8.0 (retroativas)
- v0.9.0, v0.9.1, v0.9.2, v0.9.3, v0.9.4

### Decisões arquiteturais aprovadas durante o sprint

- **D030 — ERP adapter pattern + canonical contact ownership:** App é dono
  de canais/contatos; ERP é dono de cadastro fiscal. Bling como ERP alvo.
  Tabela `contacts` (write model app) + `commerce_accounts_b2b` (read model ERP).
- **D031 — AnalystAgent (meta-agente de observabilidade):** persona admin
  que consulta Langfuse para extrair custo/anomalias/qualidade.
  Sprint 11 alvo.

### Documentação criada

- `docs/VERSIONING.md` — convenção de versão e auto-tag
- `docs/PRE_HOMOLOGATION_REVIEW.md` — protocolo concreto (10 rotas + 13+ cenários bot)
- `docs/DEPRECATIONS.md` — plano de remoção do catalog legado
- `docs/design-docs/D030-erp-adapter-and-contact-ownership.md`
- `docs/design-docs/D031-analyst-agent-observability.md`

### Lições retroativas registradas em prompts

- `prompts/evaluator.md` — Lição Sprint 9: A_BEHAVIORAL obrigatório em sprints
  com agente/dashboard, A_VERSION obrigatório, gotchas de schema confirmados
- `prompts/generator.md` — 5 regras pós-Sprint 9: grep exaustivo de migração,
  smoke comportamental, browser MCP, "pronto = produto funciona", resposta a rejeição
- `prompts/planner.md` — A_BEHAVIORAL obrigatório no spec, migração exaustiva
- `docs/GOTCHAS.yaml` — `migration_cherry_picking`, `smoke_gate_existence_only`

---

## Bugs abertos para Sprint 10

### Críticos (CRITICAL — bloqueiam fluxos centrais)

| ID | Descrição | Resolução proposta |
|----|-----------|---------------------|
| **B-26** | Truncação cega do histórico Redis quebra pares tool_use/tool_result → erro 400 → "recovery destrutivo" que apaga TODO contexto. Afeta os 3 agentes. 3 ocorrências em 19h. | Truncação preservando pares + recovery não-destrutivo |
| **B-27** | Criar contato cliente é NO-OP silencioso (UPDATE em clientes_b2b com ID do EFOS acerta 0 rows) | Estrutural via D030 — tabela `contacts` |
| **B-28** | Pedido em nome de cliente EFOS falha — `get_by_id` sem fallback commerce; LLM aluciena "instabilidade de ID" | Estrutural via D030 — `pedidos.account_external_id` |

### Altos

| ID | Descrição |
|----|-----------|
| **B-23** | Áudio Whisper rejeita 400 — `audioMessage.url` retorna conteúdo criptografado E2E. Solução: endpoint `/chat/getBase64FromMediaMessage` da Evolution API |
| **B-24** | Bot nega capacidade de áudio — fallback de erro injeta texto que confunde LLM + system prompt não menciona capacidade |
| **B-25** | Ranking de vendedores: agente faz 24 chamadas seriais (sem tool consolidada) + ano default inconsistente + sem manutenção de contexto temporal |

### Médios/Baixos

| ID | Descrição |
|----|-----------|
| **B-30** | Langfuse continua sem tokens/custo — `_get_anthropic_client` não wrappa generations (B-12 só parcialmente resolvido no Sprint 8) |
| **B-29** | Logs poluídos com `'str' object has no attribute 'decode'` em `persona_key_redis_erro` (redis-py >= 5.0 já retorna str com decode_responses) |

### Já resolvidos (validar não regrediram)

- B-10, B-11, B-12 (parcial — ver B-30), B-13, B-14 a B-22, B-31, B-32

---

## Features para Sprint 10 (priorizadas)

| ID | Descrição | Tipo |
|----|-----------|------|
| **D030 foundations** | Tabela `contacts` (PF, write model) + dashboard contatos refeito + auto-criação de pendentes + notificação dual (dashboard + WhatsApp ao gestor) | Estrutural |
| **F-07** | Controle de frequência do sync EFOS (UI admin, presets, "Rodar agora", APScheduler interno substitui launchd) | Feature temporária |
| **Deprecação catalog legado** | Remover `/catalog/painel`, crawler Playwright, EnricherAgent, scheduler_job, tabela `produtos`. **Bloqueante:** migrar embeddings vector(1536) para `commerce_products` antes do drop | Limpeza |

### Backlog para Sprint 11+

- F-05 (D031) — AnalystAgent MVP
- Bling adapter read-only (D030)
- F-02a (áudio WhatsApp) — depende de B-23 fix

---

## Estado do produto em staging (29/04/2026)

- **Versão:** v0.9.4
- **Banco:** migration 0024 (`pedidos.ficticio`)
- **EFOS sync:** 4 runs (1 success em 27/04 17:42 com 61.891 rows)
- **`commerce_*`:** 743 produtos, 614 clientes, 2.592 pedidos, 24 representantes
- **`pedidos`:** vazio (write model do bot, ainda sem pedidos reais)
- **`clientes_b2b`:** vazio (write model legado — D030 vai substituir por `contacts`)

### Métricas observáveis

- Dashboard 10 rotas funcionando com dados reais (validado 29/04)
- Bot operacional para gestor (com bugs B-25/B-26/B-28)
- Bot ainda sem áudio funcional em produção (B-23)
- Langfuse traces existem mas sem custo/tokens (B-30)

---

## Para o Planner do Sprint 10

**Contexto inicial obrigatório:**
1. Ler `docs/BUGS.md` — bugs abertos
2. Ler `docs/design-docs/D030-erp-adapter-and-contact-ownership.md` — modelagem `contacts`
3. Ler `docs/DEPRECATIONS.md` — ordem segura de remoção do catalog legado
4. Ler `docs/BACKLOG.md` F-07 — controle de frequência sync EFOS
5. Ler `docs/PRE_HOMOLOGATION_REVIEW.md` — protocolo a executar antes de declarar pronto
6. Ler `prompts/planner.md` — regras (A_BEHAVIORAL obrigatório, migração exaustiva)

**Versão alvo Sprint 10:** v0.10.0 (bumpar `output/src/__init__.py` no primeiro commit)

**Critério de pronto para homologação (decisão produto):**
- `./scripts/deploy.sh staging` sem erros
- `alembic upgrade head` aplicado
- `python scripts/smoke_sprint_10.py` → ALL OK
- Pre-homolog review (10 rotas + 13+ cenários bot) com PASS

**Pendências de planejamento:**
- Sequenciamento Bling vs AnalystAgent: Sprint 11 ou Sprint 12?
- Política de retenção de `contacts.origin='self_registered'` não autorizados
- Migração dos 5 contatos atuais em `clientes_b2b` legado: automática ou descarte?
