# QA Sprint 2 — Agente Cliente Completo

**Veredicto:** ✅ APROVADO  
**Data:** 2026-04-15  
**Evaluator:** Harness automático  
**Versão:** v0.3.0

---

## Resumo Executivo

Sprint 2 entregou o AgentCliente completo com Claude SDK, domínio Orders, PDFGenerator (fpdf2), IdentityRouter real e integração WhatsApp via send_whatsapp_media. Todos os 12 critérios de Alta passaram. Todos os 6 critérios de Média passaram (0 falhas, dentro do limite de 1).

---

## Critérios de Alta — Resultados

| ID | Descrição | Resultado | Evidência |
|----|-----------|-----------|-----------|
| A1 | lint-imports zero violações | ✅ PASSED | `5 kept, 0 broken` |
| A2 | Sem secrets hardcoded | ✅ PASSED | `grep` saída vazia |
| A3 | tenant_id em todos os repos | ✅ PASSED | `test_todo_metodo_repo_tem_tenant_id PASSED` |
| A4 | pytest -m unit 100% pass | ✅ PASSED | `163 passed, 0 failed` |
| A5 | IdentityRouter → CLIENTE_B2B | ✅ PASSED | `test_identity_router_retorna_cliente_b2b PASSED` |
| A6 | IdentityRouter → DESCONHECIDO | ✅ PASSED | `test_identity_router_retorna_desconhecido PASSED` |
| A7 | Strip @s.whatsapp.net | ✅ PASSED | `test_identity_router_strip_whatsapp_suffix PASSED` |
| A8 | confirmar_pedido cadeia completa | ✅ PASSED | `test_agent_cliente_confirmar_pedido_cadeia_completa PASSED` |
| A9 | max_iterations sem loop infinito | ✅ PASSED | `test_agent_cliente_max_iterations_nao_loop_infinito PASSED` |
| A10 | PDFGenerator retorna bytes > 1024 | ✅ PASSED | `test_gerar_pdf_retorna_bytes PASSED` |
| A11 | Sem print() em output/src/ | ✅ PASSED | `grep` saída vazia |
| A12 | total_estimado calculado em Python | ✅ PASSED | `test_criar_pedido_from_intent_calcula_total PASSED` |

---

## Critérios de Média — Resultados

| ID | Descrição | Resultado | Evidência |
|----|-----------|-----------|-----------|
| M1 | mypy --strict 0 erros | ✅ PASSED | `Success: no issues found in 76 source files` |
| M2 | OTel spans em IdentityRouter e AgentCliente | ✅ PASSED | `tracer.start_as_current_span("identity_router_resolve")` com `span.set_attribute("tenant_id", tenant_id)`; `tracer.start_as_current_span("agent_cliente_responder")` com `span.set_attribute("tenant_id", ...)` |
| M3 | send_whatsapp_media base64 + /sendMedia | ✅ PASSED | `base64.b64encode(pdf_bytes).decode()` no corpo; URL `/message/sendMedia/`; erro não propaga (testado) |
| M4 | Cobertura ≥ 80% em agents/service e orders/service | ✅ PASSED | `agents/service: 93%`, `orders/service: 87%` |
| M5 | Cobertura ≥ 60% em agents/repo e orders/repo | ✅ PASSED | `agents/repo: 84%`, `orders/repo: 82%` |
| M6 | Docstrings em métodos públicos de Repo e Service | ✅ PASSED | Todos os métodos públicos têm docstrings com Args e Returns |

**Falhas de Média:** 0 de 6 (limite: 1)

---

## Entregáveis Verificados

| # | Arquivo | Status |
|---|---------|--------|
| 1–6 | `alembic/versions/0007–0012` | ✅ Migrations existentes desde Fase 1 |
| 7 | `src/agents/types.py` | ✅ ClienteB2B, Representante, Conversa, MensagemConversa, ItemIntento, IntentoPedido |
| 8 | `src/orders/types.py` | ✅ StatusPedido, ItemPedidoInput, ItemPedido, CriarPedidoInput, Pedido |
| 9 | `src/agents/repo.py` | ✅ ClienteB2BRepo, RepresentanteRepo, ConversaRepo (4 métodos) |
| 10 | `src/orders/repo.py` | ✅ OrderRepo (criar_pedido, get_pedido, get_pedidos_pendentes, update_pdf_path) |
| 11 | `src/orders/config.py` | ✅ OrderConfig (pdf_storage_path) |
| 12 | `src/orders/service.py` | ✅ OrderService (3 métodos) |
| 13 | `src/agents/config.py` | ✅ AgentClienteConfig adicionado |
| 14 | `src/agents/service.py` | ✅ IdentityRouter real + send_whatsapp_media |
| 15 | `src/orders/runtime/__init__.py` | ✅ vazio |
| 16 | `src/orders/runtime/pdf_generator.py` | ✅ PDFGenerator.gerar_pdf_pedido → bytes |
| 17 | `src/agents/runtime/agent_cliente.py` | ✅ Claude SDK, 2 ferramentas, Redis, DB, max_iterations |
| 18 | `src/agents/ui.py` | ✅ _process_message com injeção de deps |
| 19 | `src/main.py` | ✅ lifespan mkdir pdfs + mount /pdfs |
| 20 | `pyproject.toml` | ✅ fpdf2>=2.7.0 |
| 21–27 | Testes unitários | ✅ 163 testes passando |

---

## Métricas Finais

```
pytest -m unit:        163 passed, 0 failed, 0 error
lint-imports:          5 kept, 0 broken
mypy --strict:         0 errors (76 files)
print() grep:          0 resultados
secrets grep:          0 resultados
agents/service cov:    93%
orders/service cov:    87%
agents/repo cov:       84%
orders/repo cov:       82%
```

---

## Decisões Arquiteturais Confirmadas

- **D023 (PDF + WhatsApp):** Implementado. AgentCliente confirma pedido → OrderService → PDFGenerator → send_whatsapp_media ao gestor.
- **Subtotal em Python:** `quantidade * preco_unitario` calculado em Python antes de passar ao repo. Nenhum `Computed` do SQLAlchemy.
- **fpdf2 2.x:** `bytes(pdf.output())` — encapsulamento de bytearray confirmado. API moderna (new_x/new_y) em vez de `ln=True` deprecated.
- **AgentCliente injeção de deps:** Construtor completo permite mock sem monkey-patching. _process_message em ui.py instancia e injeta.
- **Max iterations:** 5 iterações padrão. Após limite, agente envia mensagem de fallback.
- **Redis opcional:** Quando redis_client=None, funciona sem memória Redis (graceful degradation).

---

## Fora do Escopo (confirmado)

Itens não testados neste sprint (correto per contrato):
- AgentRep com Claude SDK (stub mantido)
- Envio real de WhatsApp
- Busca semântica real (mockada)
- Loja Integrada API
- resolve_preco() com preços diferenciados
- Painel de pedidos REST
