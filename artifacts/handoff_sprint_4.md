# Handoff Sprint 4 → Sprint 5

**Data:** 2026-04-17
**Sprint:** 4 — AgentGestor + Dashboard Web
**Status:** Pronto para homologação

---

## O que foi entregue

### Persona GESTOR (WhatsApp)
- Tabela `gestores` + migration 0015 (inclui fix de `ck_conversas_persona`)
- `Persona.GESTOR` adicionado ao `StrEnum`; `Gestor(BaseModel)` criado
- `GestorRepo.get_by_telefone` com filtro `ativo=true`
- `IdentityRouter` prioriza gestores → representantes → clientes_b2b → DESCONHECIDO (DP-02)
- `AgentGestor` com 5 ferramentas: buscar_clientes, buscar_produtos, confirmar_pedido_em_nome_de, relatorio_vendas, clientes_inativos
- DP-03: `representante_id` do pedido herdado de `cliente.representante_id`
- `relatorio_vendas("semana")` usa `timedelta(7)` — não `DATE_TRUNC`

### Dashboard Web (D023)
- Módulo `src/dashboard/` com 12 endpoints FastAPI
- Auth via `DASHBOARD_SECRET` + cookie `dashboard_session` (JWT HttpOnly SameSite=Lax 8h)
- Comparação com `hmac.compare_digest` (imune a timing attack)
- htmx polling `every 30s` nas KPIs do home
- 9 templates Jinja2 + 3 partials
- `/dashboard` excluído do `TenantProvider` (D023)
- `RelatorioRepo` com 4 métodos (totais_periodo, totais_por_rep, totais_por_cliente, clientes_inativos)

### Testes
- `test_agent_gestor.py` — G01–G12 (12 testes `@pytest.mark.unit`)
- `test_identity_router.py` — adicionados IR-G1 a IR-G4 (`@pytest.mark.unit`)
- `test_dashboard.py` — A11, A12, login errado, M_INJECT
- `test_agent_gestor_staging.py` — 2 testes `@pytest.mark.staging`

### Scripts
- `scripts/seed_homologacao_sprint4.py` — upsert gestor de teste + pedidos antigos
- `scripts/smoke_gate_sprint4.sh` — verifica S1–S9

---

## Estado do banco após Sprint 4

- Migration 0015 adicionada: `gestores`, `ix_pedidos_tenant_criado_em`, fix `ck_conversas_persona`
- Gestor de teste: `5519000000002` / `jmb` (via seed)
- Rep de teste: `5519000000001` / `jmb` (Sprint 3)
- Cliente de teste: `5519992066177` / `jmb` (José LZ Muzel, Sprint 1)

---

## Decisões técnicas tomadas

| ID | Decisão | Rationale |
|----|---------|-----------|
| DP-01 | AgentGestor + dashboard no mesmo sprint | Ciclo dos 3 perfis fechado antes do Sprint 5 |
| DP-02 | Gestor tem prioridade no IdentityRouter; perfis cumulativos | Lauzier pode ser gestor E ter número no rep |
| DP-03 | Pedido gestor herda `representante_id` do cliente | Preserva rastreabilidade de comissão |
| D023 | Jinja2+htmx+CSS puro; `DASHBOARD_SECRET` + cookie | Zero build step; MVP single-tenant |

---

## Pendências para Sprint 5

| Item | Motivo do adiamento |
|------|---------------------|
| `cancelar_pedido` via WhatsApp | Product spec em aberto |
| Auth multi-usuário dashboard | Sprint 4: senha única por tenant suficiente para piloto |
| SSE/WebSocket real-time | htmx polling 30s suficiente para MVP |
| Segundo tenant real | Foco no piloto JMB |
| Regras de comissão por rep | DP-03 é placeholder |
| Criação/edição de clientes via dashboard | Fora do escopo Sprint 4 |

---

## Para iniciar Sprint 5

1. `alembic upgrade head` em staging (já feito pelo Generator)
2. `infisical run --env=staging -- python scripts/seed_homologacao_sprint4.py`
3. Configurar `DASHBOARD_SECRET` e `DASHBOARD_TENANT_ID` no Infisical staging
4. `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh` → deve retornar PASSED
5. Executar homologação manual: `docs/exec-plans/active/homologacao_sprint4.md`
