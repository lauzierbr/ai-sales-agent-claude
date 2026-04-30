# Sprint 10 — Hotfixes críticos + foundations D030 + F-07 + deprecação catalog

**Status:** 🔄 Em planejamento
**Data início:** 2026-04-29
**Versão alvo:** v0.10.0
**Spec:** `artifacts/spec.md`
**Homologação:** `docs/exec-plans/active/homologacao_sprint-10.md`

---

## Objetivo

Estabilizar o piloto JMB resolvendo os 8 bugs abertos no Sprint 9, introduzir
as foundations da modelagem D030 (`contacts`), entregar F-07 (controle de
frequência sync EFOS) e remover o catalog legado preservando a busca semântica.

## Workstreams

### W1 — Hotfixes não-estruturais (bloqueia W2)

| ID | Bug/Feature | Status |
|----|-------------|--------|
| E1 | B-26 — truncação preservando pares + recovery não-destrutivo | ✅ |
| E2 | B-29 — persona_key_redis decode em str já decodada | ✅ |
| E3 | B-30 — wrapper Langfuse para Anthropic (Opção A) | ✅ |
| E4 | B-23 — áudio descriptografado via Evolution API | ✅ |
| E5 | B-24 — capacidade áudio no system prompt + fallback direto | ✅ |
| E6 | B-25 — ranking_vendedores_efos + ano default + contexto temporal | ✅ |

### W2 — Foundations D030 (contacts + dashboard refeito)

| ID | Entrega | Status |
|----|---------|--------|
| E7 | Migration `contacts` + `pedidos.account_external_id` + extensão `commerce_accounts_b2b` | ✅ |
| E8 | `normalize_accounts_b2b` populando os 6 novos campos + UPSERT preservando `embedding` | ✅ |
| E9 | `ContactRepo` + auto-criação `self_registered` + IdentityRouter | ✅ |
| E10 | Notificação dual ao gestor + comando `AUTORIZAR` | ✅ |
| E11 | Dashboard `/dashboard/contatos` refeito + `/dashboard/clientes` read-only + audit `rowcount` | ✅ |
| E12 | `confirmar_pedido_em_nome_de` aceita `account_external_id` (B-28 fix) | ✅ |

### W3 — F-07 Sync EFOS schedule (admin only)

| ID | Entrega | Status |
|----|---------|--------|
| E13 | Migration `sync_schedule` + `gestores.role` | ✅ |
| E14 | APScheduler interno + reschedule em runtime + Redis lock | ✅ |
| E15 | UI `/dashboard/sync` (admin only) | ✅ |
| E16 | Migração launchd → APScheduler (plist renomeado .disabled) | ✅ |

### W4 — Deprecação catalog legado (bloqueada por embeddings)

| ID | Entrega | Status |
|----|---------|--------|
| E17 | Migration `commerce_products.embedding` + job batch | ✅ |
| E18 | AgentCliente + CatalogService leem `commerce_products` | ✅ |
| E19 | Remover crawler/enricher/scheduler/painel/rotas/template/playwright | ✅ |
| E20 | Migration drop `produtos` + `crawl_runs` | ✅ |

## Sequenciamento obrigatório

```
W1 (paralelo entre Es) ──┐
                         ├─→ W2 (E7 → E8 → E9 → E10/E11/E12)
W3 (paralelo a W2) ──────┘
                         └─→ W4 (E17 → E18 → E19 → E20)
                              └─ pré-condição: smoke comportamental AgentCliente
```

## Notas de execução (preencher durante o sprint)

### Decisões técnicas tomadas

**DT-1 — Modelo de embedding histórico confirmado:**
- Comando: `SELECT vector_dims(embedding) FROM produtos LIMIT 1;`
- Resultado: A confirmar em staging (esperado 1536 com base em sprints anteriores)
- Modelo presumido: `text-embedding-3-small` (dims=1536)
- Decisão: cópia direta sem custo extra. Se dims=3072, escalar para PO (custo > $5).
- Script: `scripts/migrate_embeddings.py --tenant jmb` (executa ANTES da migration 0028)

**DT-2 — UPSERT preservando embedding:**
- `publish.py` EFOS substituiu DELETE+INSERT por UPSERT com `ON CONFLICT DO UPDATE`
- Coluna `embedding` não é incluída no UPDATE SET (preservada via COALESCE implícito)
- Verificação: `COUNT(*) WHERE embedding IS NOT NULL` deve ser >= valor pré-sync após cada sync

### Bugs encontrados durante implementação

1. `ClienteB2B.criado_em` era `datetime` obrigatório — corrigido para `Optional[datetime]` para suportar fallback `commerce_accounts_b2b` (E12)
2. `call_with_overload_retry` importado localmente em `langfuse_anthropic.py` impedia mock nos testes — resolvido com export no nível de módulo
3. Testes legados de `test_enricher.py`, `test_scheduler_job.py`, `test_ui.py` (catalog) falhavam após remoção dos arquivos em E19 — marcados com `pytestmark.skip`
4. Import-linter: `observability` inicialmente tentou importar de `agents.runtime` — resolvido com lazy import e export no nível de módulo

### Verificações pré-homologação
- [ ] `python scripts/smoke_sprint_10.py` → ALL OK
- [x] `pytest -m unit` → 407 passed, 0 failed, 18 skipped
- [x] `import-linter` → 7 kept, 0 broken
- [x] zero print() em código de produção
- [x] zero secrets hardcoded
- [ ] `artifacts/pre_homolog_review_sprint_10.md` → PASS em 10 rotas + cenários bot (pendente staging)

## Log de decisões (timeline)

| Data | Decisão | Origem |
|------|---------|--------|
| 2026-04-29 | Gate admin via `gestores.role` (não `tenant.is_admin_role`) | PO |
| 2026-04-29 | Retenção `self_registered`: manter indefinidamente, throttle 6h | PO |
| 2026-04-29 | Plist launchd renomeado `.disabled` (não removido) este sprint | Planner |
| 2026-04-29 | `clientes_b2b` legado mantido como fallback por 1-2 sprints | D030 |
