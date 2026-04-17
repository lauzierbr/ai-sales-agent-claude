# Sprint 3 — AgentRep + Hardening de Linguagem Brasileira

**Status:** ✅ APROVADO — 2026-04-16
**Data início:** 2026-04-16
**Spec:** `artifacts/spec.md`
**Branch:** claude/awesome-benz

---

## Objetivo

Dois agentes funcionais (AgentCliente hardened + AgentRep) com suite de 30+
testes de linguagem coloquial brasileira.

---

## Entregas (checklist)

### Infra / Schema
- [ ] E1 — Migration 0013: `representante_id` em `clientes_b2b`

### Types + Repo
- [ ] E2 — `ClienteB2B.representante_id`, `ClienteB2BRepo.buscar_por_nome()`

### Config
- [ ] E3 — `AgentRepConfig` em `config.py`
- [ ] E6 — Hardening do system prompt do `AgentClienteConfig`

### Runtime
- [ ] E4 — `AgentRep` completo (substitui stub)
- [ ] E5 — Wiring do `AgentRep` no `ui.py`

### Testes
- [ ] E7 — `test_agent_cliente_linguagem_br.py` (30+ cenários A–H)
- [ ] E8 — `test_agent_rep.py` (R01–R08, reescreve stub)
- [ ] E9 — `test_agent_rep_staging.py` (smoke + isolamento)

---

## Decisões pendentes (bloqueiam Generator)

- [x] **DP-01** aprovado: `unaccent + ILIKE` — 2026-04-16

---

## Sequência sugerida de implementação

```
1. E1 (migration) → aplica alembic upgrade
2. E2 (types + repo) → pytest -m unit agents/repo
3. E3 + E6 (configs) → import-linter
4. E4 (AgentRep runtime) → E8 (testes unitários)
5. E5 (wiring ui.py) → E9 (staging smoke)
6. E7 (hardening linguagem) → regressão completa
7. pytest -m unit → pytest -m staging → avaliação Evaluator
```

---

## Arquivos impactados

| Arquivo | Ação |
|---------|------|
| `output/alembic/versions/0013_clientes_b2b_representante_id.py` | Criar |
| `output/src/agents/types.py` | Editar (campo `representante_id`) |
| `output/src/agents/repo.py` | Editar (2 novos métodos em `ClienteB2BRepo`) |
| `output/src/agents/config.py` | Editar (`AgentRepConfig` + sistema prompt) |
| `output/src/agents/runtime/agent_rep.py` | Reescrever (era stub) |
| `output/src/agents/ui.py` | Editar (wiring AgentRep) |
| `output/src/tests/unit/agents/test_agent_cliente_linguagem_br.py` | Criar |
| `output/src/tests/unit/agents/test_agent_rep.py` | Reescrever (era stub) |
| `output/src/tests/staging/agents/test_agent_rep_staging.py` | Criar |

---

## Notas de execução

### Gotchas conhecidos (herdados do Sprint 2)

1. **asyncpg + pgvector**: ORDER BY vetorial retorna 0 rows silenciosamente.
   Workaround ativo: fetch all sem ORDER BY/LIMIT, sort+slice em Python.
   AgentRep usa CatalogService existente — não recriar esse padrão.

2. **session.commit()**: Chamar explicitamente após criar pedido E após responder.
   Sem commit → rollback silencioso. Ver `agent_cliente.py` linha 265.

3. **Dependências não-None no ui.py**: Verificar `catalog_service`, `order_service`,
   `pdf_generator` com assert ou log.error antes de passar para AgentRep.

4. **fpdf2**: `bytes(pdf.output())` — não `pdf.output()` diretamente.

5. **Evolution API**: `send_whatsapp_media` envia para `tenant.whatsapp_number`
   (gestor), não para o remetente. Para o rep, usar `send_whatsapp_message`.

### Seed de homologação

Antes do staging smoke (E9), criar seed:
```sql
-- Representante de teste
INSERT INTO representantes (tenant_id, telefone, nome, ativo)
VALUES ('jmb', '5519000000001', 'Rep Teste Sprint3', true);

-- Cliente vinculado à carteira do rep acima
UPDATE clientes_b2b
SET representante_id = (
    SELECT id FROM representantes
    WHERE telefone = '5519000000001' AND tenant_id = 'jmb'
)
WHERE tenant_id = 'jmb' AND telefone = '5519992066177';  -- José LZ Muzel
```

### Critério de aprovação Evaluator

- `pytest -m unit` passa: 100% dos testes E7 (A01–H04) + E8 (R01–R08)
- `pytest -m staging` passa: E9 (smoke + isolamento)
- `import-linter` sem violações
- Nenhum `print()` introduzido
- `session.commit()` presente nos dois agentes

---

## Log de decisões

| Data | Decisão | Quem |
|------|---------|------|
| 2026-04-16 | Spec aprovado pelo Planner | Planner |
| 2026-04-16 | DP-01: unaccent + ILIKE aprovado | usuário |

---

## Checklist de homologação manual (WhatsApp real)

A ser preenchido pelo Generator em `docs/exec-plans/active/homologacao_sprint-3.md`
após implementação. Cenários mínimos:

1. Representante consulta produto por nome informal → recebe resposta com produtos
2. Representante busca cliente da carteira pelo nome → recebe nome + CNPJ
3. Representante cria pedido em nome de cliente → gestor recebe PDF no WhatsApp
4. Representante tenta criar pedido para cliente fora da carteira → recebe erro claro
5. Cliente B2B (não rep) envia "fecha" após ver produtos → pedido criado normalmente
6. Cliente B2B envia "oi" → saudação sem busca
7. Cliente B2B envia "manda 5 cx de heineken" → pedido com quantidade 5
8. Cliente B2B envia "cancela" → nenhum pedido criado
