# Sprint Contract — Sprint 2 — Agente Cliente Completo

**Status:** ACEITO
**Data:** 2026-04-15

---

## Entregas comprometidas

1. `output/alembic/versions/0007_clientes_b2b.py` — tabela `clientes_b2b` (já criada)
2. `output/alembic/versions/0008_representantes.py` — tabela `representantes` (já criada)
3. `output/alembic/versions/0009_conversas.py` — tabela `conversas` (já criada)
4. `output/alembic/versions/0010_mensagens_conversa.py` — tabela `mensagens_conversa` (já criada)
5. `output/alembic/versions/0011_pedidos.py` — tabela `pedidos` (já criada)
6. `output/alembic/versions/0012_itens_pedido.py` — tabela `itens_pedido` (já criada)
7. `output/src/agents/types.py` — adição de: `ClienteB2B`, `Representante`, `Conversa`, `MensagemConversa`, `ItemIntento`, `IntentoPedido`
8. `output/src/orders/types.py` — novo: `StatusPedido`, `ItemPedidoInput`, `ItemPedido`, `CriarPedidoInput`, `Pedido`
9. `output/src/agents/repo.py` — adição de: `ClienteB2BRepo`, `RepresentanteRepo`, `ConversaRepo`
10. `output/src/orders/repo.py` — novo: `OrderRepo` com 4 métodos
11. `output/src/orders/config.py` — novo: `OrderConfig` (pdf_storage_path)
12. `output/src/orders/service.py` — novo: `OrderService` com 3 métodos
13. `output/src/agents/config.py` — adição de: `AgentClienteConfig`
14. `output/src/agents/service.py` — reescrita de `IdentityRouter.resolve()` (real); adição de `send_whatsapp_media()`
15. `output/src/orders/runtime/__init__.py` — novo (vazio)
16. `output/src/orders/runtime/pdf_generator.py` — novo: `PDFGenerator.gerar_pdf_pedido(pedido, tenant) -> bytes`
17. `output/src/agents/runtime/agent_cliente.py` — **REESCRITA COMPLETA** com Claude SDK, ferramentas, memória Redis, fluxo de pedido
18. `output/src/agents/ui.py` — atualização de `_process_message`: injeção de deps no AgentCliente
19. `output/src/main.py` — adição: `mkdir pdfs` no lifespan; mount `/pdfs` StaticFiles
20. `output/pyproject.toml` — adição: `fpdf2>=2.7.0`
21. `output/src/tests/unit/agents/test_identity_router.py` — reescrita com 5 casos reais
22. `output/src/tests/unit/agents/test_agent_cliente.py` — reescrita com 7 casos Claude SDK
23. `output/src/tests/unit/orders/__init__.py` — novo (vazio)
24. `output/src/tests/unit/orders/test_types.py` — novo (3 casos)
25. `output/src/tests/unit/orders/test_repo.py` — novo (4 casos)
26. `output/src/tests/unit/orders/test_service.py` — novo (3 casos)
27. `output/src/tests/unit/orders/test_pdf_generator.py` — novo (4 casos)

---

## Critérios de aceitação — Alta (bloqueantes)

**A1. import-linter — zero violações de camadas**
Teste: `lint-imports` na raiz do projeto
Evidência esperada: saída contendo `Kept` para todos os 5 contratos; zero linhas `Broken`

**A2. Sem secrets hardcoded**
Teste:
```bash
grep -r --include="*.py" \
  -E "(password|secret|api_key|apikey)\s*=\s*['\"][^'\"]{4,}" \
  output/src/ \
  --exclude-dir=tests
```
Evidência esperada: saída vazia

**A3. tenant_id obrigatório em todos os repos novos**
Teste: `pytest -m unit -k "test_todo_metodo_repo_tem_tenant_id"`
Evidência esperada: `PASSED` — inspeção de assinatura via `inspect.signature` confirma `tenant_id: str` em todos os métodos públicos de `ClienteB2BRepo`, `RepresentanteRepo`, `ConversaRepo`, `OrderRepo` que executam queries

**A4. pytest -m unit — 100% dos testes passam**
Teste: `pytest -m unit -v`
Evidência esperada: `0 failed, 0 error`

**A5. IdentityRouter: telefone em clientes_b2b → CLIENTE_B2B**
Teste: `pytest -m unit -k "test_identity_router_retorna_cliente_b2b"`
Evidência esperada: `PASSED`

**A6. IdentityRouter: telefone desconhecido → DESCONHECIDO**
Teste: `pytest -m unit -k "test_identity_router_retorna_desconhecido"`
Evidência esperada: `PASSED`

**A7. IdentityRouter: strip do sufixo @s.whatsapp.net**
Teste: `pytest -m unit -k "test_identity_router_strip_whatsapp_suffix"`
Evidência esperada: `PASSED` — repo chamado com digits apenas, sem sufixo

**A8. AgentCliente: confirmar_pedido executa cadeia completa (pedido + PDF + notificação)**
Teste: `pytest -m unit -k "test_agent_cliente_confirmar_pedido_cadeia_completa"`
Evidência esperada: `PASSED` — o teste verifica que, ao receber tool_use com `confirmar_pedido`:
(1) `OrderService.criar_pedido_from_intent` é chamado;
(2) `PDFGenerator.gerar_pdf_pedido` é chamado com o pedido retornado;
(3) `send_whatsapp_media` é chamado com pdf_bytes e número do gestor (tenant.whatsapp_number)

**A9. AgentCliente: max_iterations impede loop infinito**
Teste: `pytest -m unit -k "test_agent_cliente_max_iterations_nao_loop_infinito"`
Evidência esperada: `PASSED` — mock sempre retorna tool_use; agente encerra após 5 iterações

**A10. PDFGenerator retorna bytes não vazio**
Teste: `pytest -m unit -k "test_gerar_pdf_retorna_bytes"`
Evidência esperada: `PASSED`; `isinstance(result, bytes)` e `len(result) > 1024`

**A11. Sem print() em output/src/**
Teste:
```bash
grep -r --include="*.py" "print(" output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A12. OrderService calcula total_estimado em Python**
Teste: `pytest -m unit -k "test_criar_pedido_from_intent_calcula_total"`
Evidência esperada: `PASSED` — 3 itens com preços conhecidos → `total_estimado` correto sem acesso ao DB

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

**M1. mypy --strict sem erros**
Teste: `mypy --strict output/src/`
Evidência esperada: `Found 0 errors`

**M2. OTel span em IdentityRouter e AgentCliente**
Teste: inspeção manual de `agents/service.py` e `agents/runtime/agent_cliente.py`
Evidência esperada: `tracer.start_as_current_span("identity_router_resolve")` com atributo `tenant_id`; `tracer.start_as_current_span("agent_cliente_responder")` com atributo `tenant_id`

**M3. send_whatsapp_media usa base64 e endpoint /sendMedia**
Teste: inspeção manual de `agents/service.py`
Evidência esperada: `base64.b64encode(pdf_bytes).decode()` no corpo; URL contém `/message/sendMedia/`; erro não propaga

**M4. Cobertura ≥ 80% em agents/service.py e orders/service.py**
Teste: `pytest -m unit --cov=output/src/agents/service --cov=output/src/orders/service --cov-report=term-missing`
Evidência esperada: ambos ≥ 80% de cobertura de linhas

**M5. Cobertura ≥ 60% em agents/repo.py e orders/repo.py**
Teste: `pytest -m unit --cov=output/src/agents/repo --cov=output/src/orders/repo --cov-report=term-missing`
Evidência esperada: ambos ≥ 60%

**M6. Docstrings em todos os métodos públicos de Repo e Service novos**
Teste: inspeção manual
Evidência esperada: cada método público tem docstring mínima com Args e Returns

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 6**

Se 2 ou mais critérios de Média falharem, o sprint é reprovado mesmo com todos os de Alta passando.

---

## Fora do escopo deste contrato

O Evaluator **não** testa neste sprint:
- AgentRep com Claude SDK (stub de template é comportamento correto em Sprint 2)
- Envio real de WhatsApp (100% mockado nos testes unit)
- Busca semântica real no pgvector (mockada em testes unit)
- Execução real do crawler (sem alteração no Sprint 2)
- Loja Integrada API (fora do MVP)
- resolve_preco() com preços diferenciados (fora do MVP)
- Painel de pedidos REST
- Refresh token JWT
- Segundo tenant real

---

## Ambiente de testes

```
pytest -m unit        → roda sem I/O externo
                        PostgreSQL, Redis, Evolution API, Anthropic API: todos mockados
                        Requerido: 100% pass, 0 falhas

pytest -m integration → NÃO roda no Evaluator
                        Valida após aprovação: alembic upgrade head + curl /health

pytest -m slow        → nunca roda no loop automático
```

**Regra crítica:** teste marcado como `unit` que realizar conexão TCP, acesso ao filesystem fora de `/tmp` ou chamada HTTP real é tratado como **falha de Alta**, independentemente do resultado.

---

## Notas de implementação (binding para o Generator)

1. **Ordem de implementação:** E1(migrations — já criadas) → E2(types) → E3(repos) → E4(services+config) → E5(pdf_generator) → E6(agent_cliente) → E7(ui+main+pyproject) → E8(testes)

2. **fpdf2:** `bytes(pdf.output())` — encapsular em `bytes()` pois fpdf2 2.x retorna `bytearray`

3. **subtotal em itens_pedido:** calcular em Python (`quantidade * preco_unitario`) e passar para repo. Não usar SQLAlchemy `Computed`.

4. **AgentCliente construtor:** dependências injetadas via `__init__` — permite mock completo nos testes sem monkey-patching. `_process_message` em `agents/ui.py` instancia e injeta.

5. **Redis key para histórico:** `conv:{tenant_id}:{telefone_normalizado}` onde `telefone_normalizado = telefone.split("@")[0]`. Normalization em método privado `_normalize_phone` dentro de `ConversaRepo`.

6. **Tool use sem TextBlock:** quando `stop_reason == "tool_use"`, a resposta pode não conter nenhum `TextBlock`. Não tentar extrair texto nesse caso — apenas executar a ferramenta e iterar.

7. **Imports cross-domain em Runtime:** `agents/runtime/agent_cliente.py` importa `catalog/service` e `orders/service` — permitido pela arquitetura (Runtime pode importar qualquer Service). `orders/runtime/pdf_generator.py` importa apenas `orders/types` e `tenants/types`.

8. **PDF path:** `{pdf_storage_path}/{tenant_id}/{pedido_id}.pdf` — criar diretório com `Path.mkdir(parents=True, exist_ok=True)` antes de escrever.

9. **Notificação após confirmar_pedido:** envia para `tenant.whatsapp_number`. Se `representante_id` presente no pedido, busca telefone do representante e envia cópia. Ambos usam `send_whatsapp_media`.

10. **Migrations 0007–0012 já existem no repositório** — Generator Fase 2 não deve recriá-las. Verificar que `alembic upgrade head` as aplica sem conflito.
