# Handoff Sprint 6 → Homologação

**Data:** 2026-04-21
**Sprint:** 6 — Pre-Pilot Hardening
**Versão:** v0.7.0-rc1
**Commit:** 43f7302
**Status:** Aguardando homologação manual no mac-lablz

---

## O que foi entregue

### E1 — Cadastro de cliente via dashboard
- `output/src/tenants/service.py` — `TenantService.criar_cliente_ficticio()` implementado
- `output/src/tenants/repo.py` — `ClienteB2BCreateRepo` com `create()`, `exists_by_cnpj()`, `representante_pertence_ao_tenant()`
- `output/src/dashboard/ui.py` — `POST /dashboard/clientes/novo` funcional com validação CNPJ + duplicata + rep por tenant
- Template `clientes_novo.html` — form corrigido

### E2 — Upload de preços via dashboard
- `output/src/dashboard/ui.py` — `POST /dashboard/precos/upload` usa `CatalogService.processar_excel_precos()` e trata `ExcelUploadResult` corretamente
- Feedback inline com contagem de inseridos/erros

### E3 — Top produtos: fluxo e navegação
- `output/src/agents/repo.py` — query top-produtos com `tenant_id`
- Templates: `base.html` (nav), `home.html` (link), `top_produtos.html` (Voltar → `/dashboard/home`)

### E4 — Isolamento de tenant nas queries
- `dashboard/ui.py` — todas as queries corrigidas: `_get_pedidos_recentes`, `_get_conversas_ativas`, `_get_clientes`, `_get_representantes_com_gmv`, `_get_todos_contatos`, `_get_gestores`, `_get_cliente_by_id`, `_get_contato_by_id`, `_get_representantes_simples`

### E5 — Startup validation
- `output/src/main.py` — `_validate_secrets()` lista todos os 9 secrets faltantes em única mensagem; `RuntimeError` antes de aceitar requests

### E6 — Rate limiting no login
- `output/src/dashboard/ui.py` — `_increment_login_fail()` via Redis; 5 falhas/IP/15min → HTTP 429

### E7 — Rate limiting no webhook
- `output/src/agents/ui.py` — `_check_webhook_rate_limit()` via Redis; 30 eventos/min por `instance_id+remoteJid` → HTTP 429

### E8 — Health Anthropic
- `output/src/agents/runtime/_retry.py` — `get_anthropic_health()` classifica `ok/degraded/fail` por tipo de exceção
- `output/src/main.py` — `/health` expõe componente `anthropic`
- `scripts/health_check.py` — sai com exit ≠ 0 quando `fail`

### E9 — CORS por ambiente
- `output/src/main.py` — `development` aceita localhost; `staging/production` exigem `CORS_ALLOWED_ORIGINS` explícito
- Cookie `dashboard_session` com `Secure=True` apenas em `production`

### E10 — Testes
- `output/src/tests/unit/agents/test_dashboard.py` — 18 testes (A1–A4, A6, A9)
- `output/src/tests/unit/agents/test_webhook.py` — rate limit webhook (A7)
- `output/src/tests/unit/providers/test_startup_validation.py` — startup (A5)
- `output/src/tests/unit/agents/test_anthropic_health.py` — health (A8)
- `output/src/tests/unit/tenants/test_service.py` — 13 testes, 100% coverage
- `output/src/tests/staging/agents/test_ui_injection.py` — M_INJECT (3 agentes)
- `output/src/tests/staging/agents/test_dashboard_pre_pilot.py` — login + fluxos gestor

### E11 — Smoke e seed
- `scripts/smoke_sprint_6.py` — G1 health, G2 login, G3 home, G4 clientes, G5 top-produtos, G7 POST precos/upload, G8 POST clientes/novo, G9 webhook burst 429
- `scripts/seed_homologacao_sprint-6.py` — representante, cliente B2B, pedido confirmado

---

## Decisões técnicas tomadas

| Decisão | Motivo |
|---------|--------|
| `ClienteB2BCreateRepo` separado de `ClienteB2BRepo` | Evitar que o repo de leitura tenha deps de escrita |
| Rate limit Redis com `INCR + EXPIRE` (não TTL sliding) | Compatível com Redis sem GETSET atômico; janela fixa aceitável para o caso de uso |
| Cookie `Secure` apenas em `production` (não em `staging`) | staging roda em HTTP; Secure=True quebraria o login |
| `get_anthropic_health()` retorna `"ok"` se não houve chamada | Primeiro request do servidor não deve aparecer como degraded |
| Smoke G8 verifica visibilidade em `/dashboard/clientes` | Garante que criação + redirect + listagem funcionam como fluxo real |

---

## Para o próximo sprint saber

1. **12 falhas pré-existentes no staging** (sprints 3-5): seed_data ausente, asyncio loop bug, FakeRedis sem `setex`, agents/repo coroutine bug. Não são regressões do Sprint 6 — precisam de hotfix no início do Sprint 7.

2. **Versão alvo**: v0.7.0 após aprovação na homologação. Tag ainda não criada.

3. **Tabela `representantes` sem coluna `usuario_id`**: `Representante` type tem `usuario_id: str | None`. A coluna pode não existir no banco — confirmar na migration antes do Sprint 7 adicionar mais campos.

4. **`orders/ui` painel de pedidos** ainda 🔲 — pendente Sprint 4 scope.

5. **catalog/schedule endpoints** sem auth — pendente Sprint 3 scope.

---

## Pré-condições de homologação (Generator confirma)

- [x] Código commitado: `43f7302 feat: Sprint 6 — Pre-Pilot Hardening (v0.7.0-rc1)`
- [x] `pytest -m unit` → 281 passed, 0 falhas
- [x] `mypy --strict` → 0 erros nos arquivos do sprint
- [x] `lint-imports` → 0 violações
- [x] `scripts/seed_homologacao_sprint-6.py` pronto
- [x] `scripts/smoke_sprint_6.py` pronto (G1–G9)
- [ ] **Deploy staging**: `./scripts/deploy.sh staging` (executor: Lauzier)
- [ ] **Seed staging**: `infisical run --env=staging -- python scripts/seed_homologacao_sprint-6.py`
- [ ] **Smoke gate**: `infisical run --env=staging -- python scripts/smoke_sprint_6.py` → ALL OK

---

## Gotchas encontrados que não estavam no spec

| Gotcha | Workaround aplicado |
|--------|---------------------|
| mypy strict: `await r.incr(key)` retorna `Any` | Cast explícito `int(count)` / `bool(count > MAX)` |
| Representante.usuario_id obrigatório no type mas coluna pode não estar no banco | `usuario_id=None` nos testes de staging; confirmar migration antes do Sprint 7 |
| CatalogRepo chama `session.commit()` internamente — não visível para mock total do repo | Usar `CatalogRepo` real com mock de session_factory no teste M5 |
| Evolution API NÃO limpa indicador "digitando..." ao enviar sendText (issue #1639) | `show_typing_presence` context manager já implementado no Sprint 5 |
