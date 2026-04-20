# QA Report — Sprint 4 — AgentGestor + Dashboard — APROVADO (correção)

**Data:** 2026-04-20
**Avaliador:** Evaluator Agent — rodada de correção pós-REPROVADO r1
**Referência:** artifacts/qa_sprint_4_r1.md

---

## Veredicto

**APROVADO — após rodada de correção**

Ambas as falhas críticas identificadas na rodada r1 foram corrigidas com
evidência mecânica. Uma lacuna menor no system prompt foi identificada e
corrigida pelo Generator durante esta avaliação.

---

## Verificação das falhas do r1

### FAIL-1 — Serialização de tool_use blocks ✅ CORRIGIDO

**Evidência:**
```
grep "model_dump" output/src/agents/runtime/agent_gestor.py  → linha 299
grep "model_dump" output/src/agents/runtime/agent_rep.py     → linha 240
grep "model_dump" output/src/agents/runtime/agent_cliente.py → linha 210
```
Todos os três agentes aplicam `[b.model_dump() for b in response.content]`
antes de appender ao histórico.

**Teste G13 — A_MULTITURN:** PASS
- Simula conversa multi-turn: `relatorio_vendas` (tool_use) → follow-up
- Verifica que todos os blocos no histórico assistant são `dict`, não objetos SDK
- Confirms fix: sem caminho para erro 400 na segunda chamada à API

### FAIL-2 — Capacidade "listar pedidos" sem ferramenta ✅ CORRIGIDO

**Evidência:**
```
grep "listar_pedidos_por_status" output/src/agents/runtime/agent_gestor.py
  → linhas 163 (_TOOLS), 417 (dispatch), 598 (implementação)

grep "listar_por_tenant_status" output/src/orders/repo.py
  → linha 214 (método OrderRepo)
```

Tool definition incluída em `_TOOLS`, dispatch em `_executar_ferramenta`,
implementação delegando a `OrderRepo.listar_por_tenant_status`.

**Teste G14:** PASS — verifica que `_listar_pedidos_por_status` chama
`OrderRepo.listar_por_tenant_status` com `tenant_id` e `status` corretos.

**Teste A_TOOL_COVERAGE:** PASS — verifica que as 6 capacidades têm ferramentas:
`buscar_clientes`, `buscar_produtos`, `confirmar_pedido_em_nome_de`,
`relatorio_vendas`, `clientes_inativos`, `listar_pedidos_por_status`.

---

## Lacuna menor identificada e corrigida durante avaliação

**System prompt incompleto:** `AgentGestorConfig.system_prompt_template` listava
5 ferramentas em "## Ferramentas disponíveis" mas omitia `listar_pedidos_por_status`.
Embora a ferramenta fosse passada via `tools` parameter da API, a omissão reduzia
a probabilidade do modelo usá-la para "quais os pedidos pendentes".

**Correção aplicada:** linha adicionada ao system prompt:
```
"- listar_pedidos_por_status: lista pedidos filtrando por status (pendente/confirmado/cancelado).\n"
```
**Arquivo:** `output/src/agents/config.py`

---

## Checks automáticos — resultado final

| Check | Resultado |
|-------|-----------|
| Secrets hardcoded | PASS — `sk-ant-test-key` apenas em `patch.dict` de testes |
| `print()` proibido | PASS |
| import-linter | PASS — 5/5 contracts KEPT |
| pytest unit (228 testes) | PASS — 228 passed |
| G13 A_MULTITURN | PASS |
| G14 listar_pedidos_por_status | PASS |
| A_TOOL_COVERAGE | PASS — 6/6 capacidades cobertas |

---

## Pendências para homologação humana (não bloqueantes para APROVADO)

1. **Staging tests** (`pytest -m staging`) — devem ser executados no mac-lablz
   antes da homologação manual. O teste staging existente não cobre
   `listar_pedidos_por_status` — coverage staging é opcional para esta rodada
   de correção, mas recomendado.
2. **Smoke gate** `scripts/smoke_gate_sprint4.sh` — deve passar no mac-lablz
   com `infisical run --env=staging`.
3. **Deploy dos arquivos modificados** para o mac-lablz:
   - `output/src/agents/runtime/agent_gestor.py`
   - `output/src/agents/config.py`
   - `output/src/orders/repo.py`
   - `output/src/tests/unit/agents/test_agent_gestor.py`

---

## Próximos passos

1. Deploy staging (arquivos acima) + reiniciar uvicorn
2. `infisical run --env=staging -- pytest -m staging` no mac-lablz
3. `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh`
4. Homologação manual pelo checklist `docs/exec-plans/active/homologacao_sprint4.md`
   — cenários H1–H12 (incluindo "quais os pedidos pendentes" → deve responder)
