# Sprint Contract — Sprint 3 — AgentRep + Hardening de Linguagem Brasileira

**Status:** ACEITO
**Data:** 2026-04-16

---

## Entregas comprometidas

1. `output/alembic/versions/0013_clientes_b2b_representante_id.py` — coluna `representante_id` + FK + índice
2. `output/src/agents/types.py` — campo `representante_id: str | None = None` em `ClienteB2B`
3. `output/src/agents/repo.py` — `ClienteB2BRepo.listar_por_representante()` + `ClienteB2BRepo.buscar_por_nome()` com `unaccent + ILIKE`
4. `output/src/agents/config.py` — `AgentRepConfig` + `AgentClienteConfig.system_prompt_template` expandido com vocabulário coloquial brasileiro
5. `output/src/agents/runtime/agent_rep.py` — `AgentRep` completo (substitui stub): 3 ferramentas, loop tool_use, memória Redis, validação de carteira
6. `output/src/agents/ui.py` — wiring do `AgentRep` quando `Persona.REPRESENTANTE`; deps não-None verificadas
7. `output/src/tests/unit/agents/test_agent_cliente_linguagem_br.py` — 30 casos (grupos A–H): consultas informais, saudações, pedidos diretos, confirmações coloquiais, cancelamentos, multi-produto, quantidade ausente, regressão Sprint 2
8. `output/src/tests/unit/agents/test_agent_rep.py` — reescrita do stub: 8 casos (R01–R08)
9. `output/src/tests/staging/agents/test_agent_rep_staging.py` — smoke `@pytest.mark.staging` + isolamento de carteira por tenant

---

## Critérios de aceitação — Alta (bloqueantes)

**A1. import-linter — zero violações de camadas**
Teste: `lint-imports` na raiz do projeto
Evidência esperada: `Kept` para todos os contratos configurados; zero linhas `Broken`

**A2. Sem secrets hardcoded**
Teste:
```bash
grep -r --include="*.py" \
  -E "(password|secret|api_key|apikey)\s*=\s*['\"][^'\"]{4,}" \
  output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A3. Sem print() em output/src/**
Teste:
```bash
grep -r --include="*.py" "print(" output/src/ --exclude-dir=tests
```
Evidência esperada: saída vazia

**A4. pytest -m unit — 100% dos testes passam**
Teste: `pytest -m unit -v`
Evidência esperada: `0 failed, 0 error`

**A5. AgentRep: buscar_clientes_carteira filtra por tenant_id E representante_id**
Teste: `pytest -m unit -k "test_agent_rep_buscar_clientes_carteira_filtra_por_rep"`
Evidência esperada: `PASSED` — o mock de `ClienteB2BRepo.buscar_por_nome` captura os
argumentos da chamada e o teste asserta **explicitamente**:
(1) `tenant_id="jmb"` foi passado como argumento;
(2) `representante_id` do representante injetado foi passado como argumento;
(3) mock com `representante_id="rep-outro-tenant"` + `tenant_id="outro"` **nunca**
é chamado — verifica cross-tenant: se AgentRep do tenant "jmb" chamar buscar_por_nome,
o tenant_id na chamada deve ser sempre "jmb".

**A6. AgentRep: confirmar_pedido_em_nome_de com cliente fora da carteira não cria pedido**
Teste: `pytest -m unit -k "test_agent_rep_confirmar_cliente_invalido_nao_cria_pedido"`
Evidência esperada: `PASSED` — `OrderService.criar_pedido_from_intent` **não chamado**;
resultado da ferramenta contém `{"erro": ...}` com texto legível

**A7. AgentCliente: confirmações coloquiais disparam confirmar_pedido (D01–D07)**
Teste:
```bash
pytest -m unit -k "grupo_d" -v 2>&1 | grep -E "PASSED|FAILED|collected"
```
Evidência esperada:
- Linha `collected N items` onde N ≥ 7 (se N < 7: critério FAIL por coleta insuficiente)
- 7 testes PASSED com nomes no padrão `test_grupo_d_d0[1-7]_*`
- Mensagens: "pode mandar", "vai lá", "fecha!", "beleza, pode ir", "FECHA",
  "sim confirmo", "tô dentro, manda tudo" — cada uma como test separado
- `OrderService.criar_pedido_from_intent` chamado 1x em cada caso

Convenção obrigatória de nomenclatura: `test_grupo_d_d01_pode_mandar`,
`test_grupo_d_d02_vai_la`, ..., `test_grupo_d_d07_to_dentro_manda_tudo`

**A8. AgentCliente: cancelamentos não disparam confirmar_pedido (E01–E05)**
Teste:
```bash
pytest -m unit -k "grupo_e" -v 2>&1 | grep -E "PASSED|FAILED|collected"
```
Evidência esperada:
- Linha `collected N items` onde N ≥ 5 (se N < 5: critério FAIL por coleta insuficiente)
- 5 testes PASSED com nomes no padrão `test_grupo_e_e0[1-5]_*`
- Mensagens: "não, deixa", "cancela", "esquece", "peraí vou ver com o chefe",
  "não quero mais" — cada uma como test separado
- `OrderService.criar_pedido_from_intent` **não chamado** em nenhum caso

Convenção obrigatória de nomenclatura: `test_grupo_e_e01_nao_deixa`,
`test_grupo_e_e02_cancela`, ..., `test_grupo_e_e05_nao_quero_mais`

**A9. AgentRep: conversa persistida com Persona.REPRESENTANTE**
Teste: `pytest -m unit -k "test_agent_rep_persona_representante"`
Evidência esperada: `PASSED` — `ConversaRepo.get_or_create_conversa` chamado com
`persona=Persona.REPRESENTANTE` (não CLIENTE_B2B)

**A10. AgentRep: session.commit() chamado após confirmar pedido**
Teste: `pytest -m unit -k "test_agent_rep_commit_apos_pedido"`
Evidência esperada: `PASSED` — `session.commit` chamado ao menos 1x quando
`confirmar_pedido_em_nome_de` é executada com sucesso

**A11. buscar_por_nome usa unaccent + ILIKE**
Teste: inspeção de `output/src/agents/repo.py`
```bash
grep -A 5 "def buscar_por_nome" output/src/agents/repo.py | grep -i unaccent
```
Evidência esperada: linha contendo `unaccent` no corpo do método

**A12. Migration 0013 aplica e reverte sem erro**
Teste:
```bash
alembic upgrade head   # aplica 0013
alembic downgrade -1   # reverte 0013
alembic upgrade head   # reaaplica
```
Evidência esperada: nenhum erro nas 3 execuções; coluna `representante_id` existe
após `upgrade head`, ausente após `downgrade -1`

**A_SMOKE. Staging smoke: AgentRep responde sem crash (Postgres + Redis reais)**
Teste: `pytest -m staging -k "test_agent_rep_smoke"`
Evidência esperada: `PASSED` — `AgentRep.responder` executa com Claude real + banco real;
conversa e mensagem persistidas; nenhuma exceção não tratada

**M_INJECT. Dependências não-None no wiring do AgentRep em ui.py**
Teste: `pytest -m unit -k "test_webhook_agent_rep_deps_nao_none"`
Evidência esperada: `PASSED` — quando `Persona.REPRESENTANTE` é identificada,
`catalog_service`, `order_service` e `pdf_generator` passados ao `AgentRep` são
todos não-None; test verifica via mock de construtor

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

**M1. mypy --strict sem erros nos arquivos novos/modificados**
Teste: `mypy --strict output/src/agents/ output/src/tests/unit/agents/`
Evidência esperada: `Found 0 errors`

**M2. OTel span em AgentRep.responder**
Teste: inspeção manual de `output/src/agents/runtime/agent_rep.py`
Evidência esperada: `tracer.start_as_current_span("agent_rep_responder")` com
atributos `tenant_id` e `rep_id`

**M3. Cobertura ≥ 80% em agents/runtime/agent_rep.py**
Teste: `pytest -m unit --cov=output/src/agents/runtime/agent_rep --cov-report=term-missing`
Evidência esperada: cobertura de linhas ≥ 80%

**M4. Cobertura ≥ 60% em agents/repo.py (novos métodos)**
Teste: `pytest -m unit --cov=output/src/agents/repo --cov-report=term-missing`
Evidência esperada: cobertura de linhas ≥ 60%

**M5. Regressão Sprint 2: 4 testes H01–H04 passam sem modificação**
Teste: `pytest -m unit -k "grupo_h"`
Evidência esperada: todos os 4 casos do grupo H passam — confirma que o
system_prompt_template expandido não quebrou comportamentos existentes

**M6. Docstrings em todos os métodos públicos novos de Repo e Runtime**
Teste: inspeção manual de `repo.py` (`buscar_por_nome`, `listar_por_representante`)
e `agent_rep.py` (métodos públicos)
Evidência esperada: cada método público tem docstring com Args e Returns

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 6**

Se 2 ou mais critérios de Média falharem, o sprint é reprovado mesmo com
todos os de Alta passando.

---

## Fora do escopo deste contrato

O Evaluator **não** testa neste sprint:

- Preço de custo ou margem visível ao representante
- Alertas proativos de clientes inativos
- Busca por trigrama (`pg_trgm`) — ILIKE + unaccent é o contratado
- Envio real de WhatsApp para o representante (mockado em unit tests)
- Cadastro ou edição de clientes da carteira via painel (Sprint 4)
- Segundo tenant real
- Upload de planilha de preços diferenciados por rep
- Avaliação do evaluator.py (sem alteração neste sprint)

---

## Ambiente de testes

```
pytest -m unit      → sem I/O externo; PostgreSQL, Redis, Anthropic API: todos mockados
                      Requerido: 100% pass, 0 falhas — inclui A_SMOKE? NÃO

pytest -m staging   → Postgres + Redis reais (mac-lablz); sem Evolution API; Claude real
                      Requerido para A_SMOKE: 1 teste smoke do AgentRep

pytest -m integration → NÃO roda no Evaluator; valida após aprovação no mac-lablz

pytest -m slow      → nunca roda no loop automático
```

**Regra crítica (herdada do Sprint 2):** teste `@pytest.mark.unit` que realiza
conexão TCP, acesso ao filesystem fora de `/tmp` ou chamada HTTP real é tratado
como **falha de Alta**, independentemente do resultado.

---

## Notas de implementação (binding para o Generator)

1. **Ordem de implementação:**
   E1 (migration 0013) → E2 (types + repo) → E3 (AgentRepConfig + system prompt) →
   E4 (AgentRep runtime) → E8 (unit tests AgentRep) → E5 (wiring ui.py) →
   E7 (hardening linguagem) → E9 (staging smoke)

2. **unaccent:** extensão já disponível no PostgreSQL — ativar com
   `CREATE EXTENSION IF NOT EXISTS unaccent;` no `upgrade()` da migration 0013.
   Query: `unaccent(lower(nome)) ILIKE unaccent(lower('%' || :query || '%'))`

3. **Validação de carteira em confirmar_pedido_em_nome_de:** chamar
   `ClienteB2BRepo.listar_por_representante()` e verificar se `cliente_b2b_id`
   está na lista antes de chamar `OrderService`. Não confiar no `cliente_b2b_id`
   vindo do Claude sem validar — evita que rep crie pedido para cliente de outro rep.

4. **AgentRep e session.commit():** mesmo padrão do AgentCliente (linha 265 de
   `agent_cliente.py`) — commit após `add_mensagem` do assistente, antes de enviar
   WhatsApp.

5. **Testes grupo D e E:** cada caso é um teste independente com mock Anthropic
   diferente. Usar `@pytest.mark.parametrize` é permitido mas cada case_id deve
   aparecer no nome do teste para facilitar debug (`grupo_d_d01_pode_mandar`, etc.).

6. **Testes grupo C e F (multi-produto / pedido direto):** mock Anthropic com
   `side_effect` lista a sequência completa: `[tool_use_busca, tool_use_confirma, end_turn]`.
   O teste não verifica a query de busca — apenas que `OrderService` foi chamado
   com `n_itens` ≥ 1.

7. **System prompt do AgentRep:** `{rep_nome}` resolvido em `AgentRep.__init__` a
   partir do `representante.nome` injetado — não lido em tempo de execução por request.

8. **Gotcha asyncpg + pgvector (herdado Sprint 2):** `buscar_por_nome` usa SQL
   puro (não pgvector) — sem ORDER BY vetorial. Safe.

9. **Staging seed:** o seed do representante de teste (`5519000000001`) deve ser
   aplicado em script separado `scripts/seed_homologacao_sprint-3.py`, não em migration.
