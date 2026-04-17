# Sprint 4 — Gestor/Admin: AgentGestor + Dashboard Web

**Status:** 🔄 Em planejamento
**Data:** 2026-04-17
**Spec:** `artifacts/spec.md`
**Contrato:** `artifacts/sprint_contract.md` (a criar pelo Generator)
**QA:** `artifacts/qa_sprint_4.md` (a criar pelo Evaluator)

---

## Objetivo

Entregar o terceiro perfil do sistema (`GESTOR`) via WhatsApp com acesso irrestrito
a clientes, pedidos e relatórios, mais o primeiro dashboard web operacional com
painel de pedidos em tempo real, gestão de clientes e representantes, upload de
preços e configuração por tenant.

---

## Entregas (checklist de implementação)

### E1 — Migration 0015
- [ ] Tabela `gestores` criada
- [ ] Índice `ix_pedidos_tenant_criado_em` criado
- [ ] CHECK CONSTRAINT `ck_conversas_persona` atualizado com `'gestor'`
- [ ] `alembic upgrade head` sem erro
- [ ] `alembic downgrade -1` funcional

### E2 — Types
- [ ] `Persona.GESTOR = "gestor"` adicionado
- [ ] `class Gestor(BaseModel)` criado com `model_config = ConfigDict(from_attributes=True)`

### E3 — Repo
- [ ] `GestorRepo.get_by_telefone` implementado
- [ ] `ClienteB2BRepo.buscar_todos_por_nome` (sem filtro rep) implementado
- [ ] `ClienteB2BRepo.get_by_id` implementado
- [ ] `RelatorioRepo.totais_periodo` implementado
- [ ] `RelatorioRepo.totais_por_rep` implementado
- [ ] `RelatorioRepo.totais_por_cliente` implementado
- [ ] `RelatorioRepo.clientes_inativos` implementado

### E4 — Config
- [ ] `AgentGestorConfig` com `max_iterations=8` e `system_prompt_template`

### E5 — Runtime
- [ ] `AgentGestor` com 5 ferramentas: `buscar_clientes`, `buscar_produtos`, `confirmar_pedido_em_nome_de`, `relatorio_vendas`, `clientes_inativos`
- [ ] DP-03: `representante_id` herdado de `cliente.representante_id`
- [ ] Cálculo de períodos em Python (sem DATE_TRUNC)

### E6 — Service
- [ ] `IdentityRouter.resolve()` com nova prioridade `gestores → representantes → clientes_b2b → DESCONHECIDO`

### E7 — UI (webhook)
- [ ] `_process_message()` instancia `AgentGestor` para `Persona.GESTOR`

### E8 — Dashboard web
- [ ] ADR D023 registrado em `docs/design-docs/index.md`
- [ ] Módulo `output/src/dashboard/` criado
- [ ] 12 endpoints implementados
- [ ] Auth via `DASHBOARD_SECRET` + cookie HttpOnly
- [ ] htmx auto-refresh nas KPIs (30s)
- [ ] `/dashboard` excluído do TenantProvider
- [ ] `main.py` registra dashboard router

### E9 — ADR D023
- [ ] Linha D023 adicionada à tabela de `docs/design-docs/index.md`
- [ ] Bloco D023 adicionado com contexto, decisão e rationale

### E10 — Testes + smoke + seed
- [ ] `test_agent_gestor.py` com G01–G12
- [ ] `test_identity_router.py` com IR-G1 a IR-G4
- [ ] `test_agent_gestor_staging.py` com 2 testes `@pytest.mark.staging`
- [ ] `seed_homologacao_sprint4.py` funcional
- [ ] `smoke_gate_sprint4.sh` retorna `PASSED`

---

## Sequência de implementação recomendada

```
E1 (migration) → E2 (types) → E3 (repo) → E4 (config) → E5 (runtime)
                                                        → E6 (service)
                                                        → E7 (ui webhook)
                                                        → E8 (dashboard) — paralelo a E5-E7
E9 (ADR) — antes de E8
E10 (testes + smoke) — após tudo
```

---

## Log de decisões

| Data | Decisão | Quem |
|------|---------|------|
| 2026-04-17 | DP-01: AgentGestor + dashboard no mesmo sprint | Lauzier |
| 2026-04-17 | DP-02: Gestor tem prioridade sobre rep no IdentityRouter (perfis cumulativos) | Lauzier |
| 2026-04-17 | DP-03: Pedido gestor herda `representante_id` do cliente | Lauzier |
| 2026-04-17 | D023: Dashboard stack Jinja2+htmx+CSS, auth DASHBOARD_SECRET cookie HttpOnly | Planner |

---

## Notas de execução

_(Preenchido pelo Generator durante implementação)_

---

## Homologação

Checklist: `docs/exec-plans/active/homologacao_sprint4.md`
Protocolo completo: `docs/HOMOLOGACAO.md`
