# QA Report — Sprint 4 — AgentGestor + Dashboard — REPROVADO

**Data:** 2026-04-20
**Avaliador:** Evaluator Agent (retroativo — falha de processo identificada em homologação humana)
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**REPROVADO — rodada 1 de 1**

Dois bugs críticos descobertos durante homologação humana que deveriam ter sido
capturados pelo Evaluator. Ambos são falhas de processo do harness, não apenas
de implementação. O prompt do Evaluator foi atualizado para exigir os critérios
ausentes em todos os sprints futuros.

---

## Falhas identificadas

### FAIL-1 — Serialização de tool_use blocks (Alta)

**Arquivos:** `output/src/agents/runtime/agent_gestor.py:269`,
`agent_rep.py:240`, `agent_cliente.py:211`

**Erro observado em produção:**
```
agent_resposta_erro error="Error code: 400 - messages.5.content.0:
Input should be a valid dictionary or object to extract fields from"
persona=gestor tenant_id=jmb
```

**Causa raiz:** `response.content` do SDK Anthropic são objetos Python
(`TextBlock`, `ToolUseBlock`). O código fazia:
```python
messages.append({"role": "assistant", "content": response.content})
```
Ao salvar no Redis com `json.dumps(..., default=str)`, esses objetos
viravam strings. Na mensagem seguinte, a API recebia strings onde
esperava dicts → erro 400 silencioso para o usuário.

**Correção aplicada (hotfix 2026-04-20):**
```python
messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
```

**Por que o Evaluator não capturou:** nenhum teste simulava conversa
multi-turn onde uma tool call ocorre e o usuário faz uma pergunta de
follow-up na mesma sessão. Todos os testes testavam cada tool call em
isolamento.

**Critério ausente:** `A_MULTITURN` — obrigatório a partir de agora.

---

### FAIL-2 — Capacidade "listar pedidos" anunciada sem ferramenta (Alta)

**Arquivo:** `output/src/agents/config.py` (system_prompt_template do AgentGestor)

**Comportamento observado:** usuário enviou "Quais os pedidos pendentes".
O bot não respondeu. O AgentGestor não tem ferramenta para listar pedidos
por status — só tem `confirmar_pedido_em_nome_de`.

**Ferramentas existentes vs. capacidades anunciadas:**
| Capacidade anunciada | Ferramenta | Status |
|---|---|---|
| Fechar pedidos | `confirmar_pedido_em_nome_de` | ✓ |
| Buscar produtos | `buscar_produtos` | ✓ |
| Relatórios de vendas | `relatorio_vendas` | ✓ |
| Clientes inativos | `clientes_inativos` | ✓ |
| Ver pedidos por status | — | **✗ ausente** |

**Por que o Evaluator não capturou:** o checklist testou cada ferramenta
isolada. Nunca foi feita a verificação de cobertura: "cada capacidade
anunciada tem ferramenta + teste?"

**Critério ausente:** `A_TOOL_COVERAGE` — obrigatório a partir de agora.

---

## O que o Generator deve entregar na correção

### 1. Ferramenta `listar_pedidos_por_status` no AgentGestor

```python
listar_pedidos_por_status(status: "pendente" | "confirmado" | "cancelado" | None = None)
```
- Delega a `OrderRepo.listar_por_tenant_status(tenant_id, status, session)`
- Retorna: `[{id, cliente_nome, total_estimado, status, criado_em}]` ordenado por `criado_em DESC`
- Sem `status`: retorna todos os pedidos dos últimos 30 dias

### 2. Teste G13 — multi-turn após tool call (A_MULTITURN)

```python
# test_agent_gestor.py
async def test_g13_multiturn_sem_erro_400():
    # mock: primeira mensagem aciona relatorio_vendas → tool result
    # segunda mensagem na mesma sessão: follow-up simples
    # verifica: sem KeyError, sem erro 400, messages list tem dicts (não strings)
    for msg in messages:
        if msg["role"] == "assistant":
            for block in msg["content"]:
                assert isinstance(block, dict), "block deve ser dict, não objeto SDK"
```

### 3. Teste A_TOOL_COVERAGE

```python
def test_todas_capacidades_anunciadas_tem_ferramenta():
    tools = {t["name"] for t in GESTOR_TOOLS}
    assert "listar_pedidos_por_status" in tools
    assert "buscar_clientes" in tools
    assert "relatorio_vendas" in tools
    assert "clientes_inativos" in tools
    assert "confirmar_pedido_em_nome_de" in tools
```

### 4. Confirmar hotfix de model_dump() nos três agentes

Verificar (não reimplementar — já foi aplicado):
```bash
grep "model_dump" output/src/agents/runtime/agent_gestor.py
grep "model_dump" output/src/agents/runtime/agent_rep.py
grep "model_dump" output/src/agents/runtime/agent_cliente.py
```
Esperado: uma linha por arquivo com `b.model_dump()`.

---

## Checks automáticos

| Check | Resultado |
|-------|-----------|
| Secrets hardcoded | PASS |
| import-linter | PASS |
| print() proibido | PASS |
| pytest unit (224 testes) | PASS |
| pytest staging (19 testes) | PASS |
| smoke gate S1–S9 | PASS |
| **A_MULTITURN** | **FAIL — critério ausente no contrato** |
| **A_TOOL_COVERAGE** | **FAIL — ferramenta ausente + critério ausente** |

---

## Mudança de processo registrada

`prompts/evaluator.md` atualizado com:
1. Seção "Lição aprendida — Sprint 4" com os dois padrões de falha
2. Critérios obrigatórios `A_MULTITURN` e `A_TOOL_COVERAGE` para agentes conversacionais
3. Dois itens na lista "Nunca" do Evaluator

---

## Próximos passos para o Generator

1. Implementar `listar_pedidos_por_status` (AgentGestor + OrderRepo)
2. Escrever G13 (multi-turn) e `test_todas_capacidades_anunciadas_tem_ferramenta`
3. Confirmar `b.model_dump()` nos três agentes (hotfix já aplicado)
4. Resubmeter para nova avaliação do Evaluator
