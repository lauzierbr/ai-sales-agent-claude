# Sprint 5 — Observabilidade LLM, Configurações e Relatórios

**Status:** 🔄 Em planejamento
**Data início:** 2026-04-20
**Versão alvo:** v0.6.0
**Planner:** Claude Sonnet 4.6

---

## Objetivo

Adicionar observabilidade LLM via Langfuse (self-hosted Docker), configuração de números
de celular para todos os perfis, cadastro de clientes fictícios pelo dashboard, e ampliar
relatórios de performance de representantes com filtro de período, breakdown por cliente,
e ferramenta WhatsApp no AgentGestor.

---

## Entregas (checklist do Generator)

### E1 — Langfuse self-hosted Docker + instrumentação dos 3 agentes
- [ ] `docker-compose.dev.yml` — adicionar serviços `langfuse` e `langfuse-db`
- [ ] `docker-compose.staging.yml` — idem com `NEXTAUTH_URL` apontando para IP staging
- [ ] `scripts/health_check.py` — adicionar check `GET /api/public/health` no Langfuse
- [ ] `output/src/agents/config.py` — adicionar `LangfuseConfig` (host, public_key, secret_key, enabled)
- [ ] `output/src/agents/runtime/agent_cliente.py` — `@observe()` em `processar_mensagem`, tags com `tenant_id`
- [ ] `output/src/agents/runtime/agent_rep.py` — idem
- [ ] `output/src/agents/runtime/agent_gestor.py` — idem
- [ ] `output/src/tests/unit/agents/test_langfuse_instrumentation.py` — testa com `LANGFUSE_ENABLED=false`
- [ ] `pyproject.toml` — adicionar `langfuse>=2.0,<3.0` em dependencies

### E2 — Configuração de números de celular via dashboard
- [ ] `output/alembic/versions/0016_representantes_telefone.py` — ADD COLUMN telefone
- [ ] `output/alembic/versions/0017_gestores_telefone.py` — ADD COLUMN telefone
- [ ] `output/src/tenants/repo.py` — `update_cliente_telefone`, `update_representante_telefone`, `update_gestor_telefone`
- [ ] `output/src/tenants/service.py` — `atualizar_telefone_perfil(perfil, id, telefone, tenant_id, session)`
- [ ] `output/src/dashboard/ui.py` — endpoints GET/POST `/clientes/{id}/editar`, `/representantes/{id}/editar`, `/gestores/{id}/editar`
- [ ] `output/src/dashboard/templates/clientes_editar.html`
- [ ] `output/src/dashboard/templates/representantes_editar.html`
- [ ] `output/src/dashboard/templates/gestores_editar.html`

### E3 — Cadastro de clientes fictícios via dashboard
- [ ] `output/src/tenants/repo.py` — `ClienteB2BRepo.create(cliente, session)`, `exists_by_cnpj(cnpj, tenant_id, session)`
- [ ] `output/src/tenants/service.py` — `criar_cliente_ficticio(tenant_id, dados, session)`
- [ ] `output/src/dashboard/ui.py` — endpoints GET/POST `/clientes/novo`
- [ ] `output/src/dashboard/templates/clientes_novo.html`
- [ ] `output/src/tests/unit/tenants/test_criar_cliente.py`

### E4 — Relatórios de performance por representante (ampliados)
- [ ] `output/src/agents/repo.py` — `relatorio_performance_rep(tenant_id, dias, session, representante_id?)`
- [ ] `output/src/agents/config.py` — atualizar `AgentGestorConfig._TOOLS` com `relatorio_representantes`
- [ ] `output/src/agents/runtime/agent_gestor.py` — implementar handler da ferramenta
- [ ] `output/src/dashboard/ui.py` — atualizar GET `/representantes` com `?dias=` param; novo GET `/representantes/{id}`
- [ ] `output/src/dashboard/templates/representantes.html` — adicionar seletor de período (htmx)
- [ ] `output/src/dashboard/templates/_partials/representantes_lista.html` — partial htmx
- [ ] `output/src/dashboard/templates/representantes_detalhe.html` — breakdown por cliente
- [ ] `output/src/tests/unit/agents/test_relatorio_rep.py`

### Scripts e documentação
- [ ] `scripts/smoke_sprint_5.py` — smoke gate contra staging
- [ ] `scripts/seed_homologacao_sprint-5.py` — seed dados para homologação manual
- [ ] `docs/exec-plans/active/homologacao_sprint-5.md` — criado pelo Planner ✅
- [ ] `docs/PLANS.md` — atualizar Sprint 5 para 🔄 ✅
- [ ] `docs/design-docs/index.md` — adicionar ADR D024 ✅

---

## Log de decisões

| Data | Decisão | ADR |
|------|---------|-----|
| 2026-04-20 | Langfuse v2 self-hosted Docker (não Cloud) | D024 |
| 2026-04-20 | Config números: editar campo telefone em todos os perfis (clientes, reps, gestores) | — |
| 2026-04-20 | Clientes fictícios: CNPJ validado só por formato (14 dígitos), sem Receita Federal | — |
| 2026-04-20 | Relatórios: período 7/30/90 dias; sem exportação Excel | — |
| 2026-04-20 | Doc-gardening agent: excluído → backlog | — |
| 2026-04-20 | OTEL spans completos: excluído → backlog (commit 60fab40) | — |

---

## Notas de execução

_Preenchidas pelo Generator durante implementação._

---

## Gates obrigatórios (harness v2)

- **G2** `lint-imports` — import-linter sem violações
- **G3** `check_tool_coverage.py` — `relatorio_representantes` declarada E anunciada
- **G5** `pytest -m unit` — todos os testes unitários passam
- **G7** `check_gotchas.py` — sem `INTERVAL` hardcoded, sem `|enumerate`, sem API antiga Starlette

Todos os 4 gates devem passar antes de o Evaluator emitir APROVADO.
