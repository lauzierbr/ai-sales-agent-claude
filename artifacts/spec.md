# Sprint 3 — AgentRep + Hardening de Linguagem Brasileira

**Status:** Em planejamento
**Data:** 2026-04-16
**Pré-requisitos:** Sprint 2 APROVADO (v0.3.0), migrations 0001–0012 aplicadas

---

## Objetivo

Ao final deste sprint existem dois agentes funcionais (AgentCliente e AgentRep) e
uma suite de regressão que garante robustez a linguagem natural coloquial brasileira —
incluindo abreviações, gírias, confirmações informais e typos comuns de celular.

---

## Contexto

O AgentCliente está em produção e funcional. O AgentRep permaneceu como stub
desde o Sprint 2 (arquivo: `src/agents/runtime/agent_rep.py`). O representante
comercial da JMB precisa de um canal WhatsApp próprio para consultar catálogo e
criar pedidos em nome dos clientes da sua carteira, sem precisar de acesso ao painel.

Paralelamente, a homologação do Sprint 2 revelou que o AgentCliente funciona bem
em cenários formais mas não foi testado com a linguagem que brasileiros realmente
usam no WhatsApp. Esta lacuna precisa ser fechada antes de ir a múltiplos clientes.

---

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents  | Types, Config, Repo, Runtime |
| orders  | Service, Runtime (reutilização) |
| db      | Migration (0013) |
| tests   | unit, staging |

---

## Considerações multi-tenant

- AgentRep filtra `clientes_b2b` por `tenant_id` E `representante_id` — nunca retorna
  clientes de outro representante ou outro tenant.
- `confirmar_pedido_em_nome_de` passa `tenant_id` explicitamente para `OrderService`.
- A migration 0013 adiciona coluna `representante_id NULLABLE` em `clientes_b2b` —
  clientes sem representante vinculado continuam funcionando (valor NULL).
- Testes de isolamento devem verificar que `buscar_clientes_carteira` de rep do tenant
  A não retorna clientes do tenant B.

---

## Secrets necessários (Infisical)

Nenhum secret novo. Sprint 3 reutiliza os existentes:

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| ANTHROPIC_API_KEY | development, staging | Claude SDK |
| AGENT_REP_MODEL | development | Modelo do AgentRep (padrão: claude-sonnet-4-6) |
| AGENT_REP_MAX_TOKENS | development | Max tokens (padrão: 4096) |

`AGENT_REP_MODEL` e `AGENT_REP_MAX_TOKENS` são opcionais — o sistema usa os defaults
se não estiverem definidos. Adicionar ao Infisical development antes da execução.

---

## Entregas

### E1 — Migration 0013: representante_id em clientes_b2b

**Camadas:** DB (Alembic)
**Arquivo(s):** `output/alembic/versions/0013_clientes_b2b_representante_id.py`

**Critérios de aceitação:**
- [ ] Coluna `representante_id TEXT NULLABLE` adicionada a `clientes_b2b`
- [ ] FK para `representantes.id` com `ON DELETE SET NULL`
- [ ] Índice `ix_clientes_b2b_rep` em `(tenant_id, representante_id)`
- [ ] `downgrade()` reverte sem perda de dados (DROP COLUMN IF EXISTS)
- [ ] `alembic upgrade head` aplica sem erro partindo de 0012

---

### E2 — ClienteB2B.representante_id no tipo e no repo

**Camadas:** Types, Repo
**Arquivo(s):**
- `output/src/agents/types.py`
- `output/src/agents/repo.py`

**Critérios de aceitação:**
- [ ] `ClienteB2B` tem campo `representante_id: str | None = None`
- [ ] `ClienteB2BRepo.listar_por_representante(tenant_id, representante_id, session)`
  retorna `list[ClienteB2B]` — só clientes com `representante_id` igual ao informado
  E `tenant_id` igual — ordenados por `nome ASC`
- [ ] `ClienteB2BRepo.buscar_por_nome(tenant_id, representante_id, query, session)`
  retorna `list[ClienteB2B]` usando `ILIKE '%query%'` no campo `nome`
  — sempre com filtro `tenant_id` E `representante_id`
- [ ] import-linter passa sem violações (Repo não importa Service)

---

### E3 — AgentRepConfig

**Camadas:** Config
**Arquivo(s):** `output/src/agents/config.py`

**Critérios de aceitação:**
- [ ] Classe `AgentRepConfig` adicionada ao arquivo (ao lado de `AgentClienteConfig`)
- [ ] Campos: `model`, `max_tokens`, `redis_ttl`, `max_iterations`, `historico_max_msgs`,
  `system_prompt_template`
- [ ] `system_prompt_template` parametrizado com `{tenant_nome}` e `{rep_nome}`
- [ ] System prompt instrui o agente a:
  - Sempre confirmar o nome do cliente antes de fechar pedido
  - Exibir nome + CNPJ do cliente ao localizá-lo
  - Usar linguagem direta com representante (mais técnica que com cliente)
  - Nunca inventar clientes — usar apenas os retornados por `buscar_clientes_carteira`
- [ ] `repr()` retorna string com model e max_iterations

---

### E4 — AgentRep (substitui stub)

**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/runtime/agent_rep.py`

**Ferramentas expostas ao Claude:**

```
buscar_produtos(query: str, limit: int = 5)
  → mesmo CatalogService do AgentCliente

buscar_clientes_carteira(query: str)
  → ClienteB2BRepo.buscar_por_nome() filtrado por representante_id do rep atual
  → retorna lista de {cliente_id, nome, cnpj, telefone}

confirmar_pedido_em_nome_de(cliente_b2b_id: str, itens: list[ItemInput], observacao: str | None)
  → valida que cliente_b2b_id pertence à carteira do rep (tenant_id + representante_id)
  → chama OrderService.criar_pedido_from_intent()
  → gera PDF e envia para tenant.whatsapp_number (gestor)
  → envia confirmação texto para o rep (não para o cliente)
```

**Critérios de aceitação:**
- [ ] `AgentRep.__init__` recebe as mesmas dependências injetáveis do AgentCliente
  (order_service, conversa_repo, pdf_generator, config, catalog_service,
  anthropic_client, redis_client) mais `representante: Representante`
- [ ] `AgentRep.responder(mensagem, tenant, session)` — mesmo fluxo do AgentCliente
  (histórico Redis, loop tool_use, persiste no banco, commit, envia WhatsApp)
- [ ] Validação de segurança: `confirmar_pedido_em_nome_de` verifica que
  `cliente_b2b_id` existe na carteira do rep antes de criar pedido.
  Se não existir: retorna `{"erro": "Cliente não encontrado na sua carteira."}`
- [ ] Se Claude chamar `confirmar_pedido_em_nome_de` sem ter chamado
  `buscar_clientes_carteira` antes (cliente_b2b_id desconhecido): a validação
  acima captura isso e retorna erro sem criar pedido
- [ ] `Persona.REPRESENTANTE` usado em `get_or_create_conversa`
- [ ] import-linter passa (Runtime não importa UI)
- [ ] OpenTelemetry: span `agent_rep_responder` com atributos `tenant_id`, `rep_id`

---

### E5 — Wiring do AgentRep no webhook (ui.py)

**Camadas:** UI
**Arquivo(s):** `output/src/agents/ui.py`

**Critérios de aceitação:**
- [ ] Quando `identity_router` retorna `Persona.REPRESENTANTE`, instancia `AgentRep`
  com `representante=` o objeto obtido do `RepresentanteRepo`
- [ ] AgentRep injetado com as mesmas dependências já construídas para AgentCliente
  (mesmos singletons: catalog_service, order_service, etc.)
- [ ] Dependências nunca None: `catalog_service`, `order_service`, `pdf_generator`
  verificados no startup ou no handler — log.error + return 500 se None
- [ ] `@pytest.mark.staging` smoke: POST /webhook/whatsapp com payload de representante
  real → 200 OK (sem verificar resposta Claude)

---

### E6 — Hardening do system prompt do AgentCliente

**Camadas:** Config
**Arquivo(s):** `output/src/agents/config.py`

**Critérios de aceitação:**
- [ ] `AgentClienteConfig.system_prompt_template` expandido com seção
  `## Linguagem coloquial brasileira` contendo:
  - Mapeamento de expressões de pedido: "manda", "me manda", "quero", "bota",
    "coloca", "pega", "preciso de" → intenção de consulta ou compra
  - Mapeamento de confirmações: "pode mandar", "fecha", "fecha aí", "vai lá",
    "beleza", "tá bom", "confirmo", "sim", "pode ir", "manda tudo",
    "FECHA", "vai!" → `confirmar_pedido`
  - Mapeamento de cancelamentos: "não", "cancela", "esquece", "para",
    "peraí", "deixa pra lá", "não quero mais" → não confirmar pedido
  - Abreviações numéricas: "cx" = caixa, "und" / "un" = unidade,
    "pct" = pacote, "fdo" / "frd" = fardo, "dz" = dúzia
  - Instrução: se quantidade não for especificada, perguntar antes de confirmar
  - Instrução: se mensagem for só saudação ("oi", "bom dia", "e aí"), responder
    com saudação + oferta de ajuda, sem chamar ferramentas
- [ ] Nenhuma outra lógica do AgentCliente alterada — só o template de string

---

### E7 — Suite de testes de linguagem coloquial brasileira (AgentCliente)

**Camadas:** Tests (unit)
**Arquivo(s):** `output/src/tests/unit/agents/test_agent_cliente_linguagem_br.py`

Esta suite verifica que o AgentCliente reage corretamente quando Claude (mockado)
retorna respostas consistentes com o system prompt expandido.

**Estrutura dos testes:**
Cada teste injeta um mock do Anthropic que responde como Claude responderia dado
o system prompt correto. O teste verifica o COMPORTAMENTO DO AGENTE (ferramentas
chamadas, respostas enviadas), não o texto gerado pelo Claude.

**Critérios de aceitação — cada item abaixo é um test case individual:**

#### Grupo A: Consultas informais → buscar_produtos chamado

- [ ] `A01` "oi, tem shampoo?" → Claude retorna tool_use buscar_produtos(query="shampoo")
      → agente executa busca → envia resposta via WhatsApp
- [ ] `A02` "manda o preço da heineken" → buscar_produtos(query="heineken") chamado
- [ ] `A03` "qual o valor do nescau?" → buscar_produtos(query="nescau") chamado
- [ ] `A04` "tem alguma coisa de higiene?" → buscar_produtos(query="higiene") chamado
- [ ] `A05` "me mostra condicionadro" (typo) → buscar_produtos chamado (query não vazia)
- [ ] `A06` "quero ver o catálogo de bebê" → buscar_produtos(query contém "bebê")

#### Grupo B: Saudações → sem ferramenta chamada

- [ ] `B01` "oi" → Claude retorna end_turn (sem tool_use) → agente envia saudação
- [ ] `B02` "bom dia" → end_turn, nenhuma tool chamada
- [ ] `B03` "boa tarde, tudo bem?" → end_turn, nenhuma tool chamada
- [ ] `B04` "olá posso fazer um pedido?" → end_turn com resposta orientando o cliente,
      sem buscar_produtos (ainda não há produto mencionado)

#### Grupo C: Pedidos diretos → buscar_produtos + confirmar_pedido em sequência

- [ ] `C01` "manda 10 shampoo 300ml" →
      iter 1: buscar_produtos(query="shampoo 300ml")
      iter 2: confirmar_pedido(itens=[{quantidade: 10, ...}])
      → OrderService.criar_pedido_from_intent chamado 1x
- [ ] `C02` "quero 2 cx de heineken long neck" →
      buscar_produtos("heineken long neck") chamado, depois confirmar_pedido
- [ ] `C03` "fecha aí, 3 de shampoo e 2 de condicionador" →
      buscar_produtos chamado (pode ser 1 ou 2x), confirmar_pedido com 2 itens
- [ ] `C04` "me manda: 10 heineken 600ml e 5 skol" →
      confirmar_pedido com pelo menos 2 itens no final do loop

#### Grupo D: Confirmações coloquiais → confirmar_pedido acionado

Cenário base: agente já mostrou produtos, cliente responde com confirmação.
Mock do histórico Redis contém os produtos apresentados.

- [ ] `D01` "pode mandar" → Claude retorna confirmar_pedido → pedido criado
- [ ] `D02` "vai lá" → confirmar_pedido → OrderService chamado
- [ ] `D03` "fecha!" → confirmar_pedido → pedido criado
- [ ] `D04` "beleza, pode ir" → confirmar_pedido → pedido criado
- [ ] `D05` "FECHA" (maiúsculas) → confirmar_pedido → pedido criado
- [ ] `D06` "sim confirmo" → confirmar_pedido → pedido criado
- [ ] `D07` "tô dentro, manda tudo" → confirmar_pedido → pedido criado

#### Grupo E: Cancelamentos → confirmar_pedido NÃO chamado

- [ ] `E01` "não, deixa" → end_turn sem confirmar_pedido, OrderService não chamado
- [ ] `E02` "cancela" → end_turn, OrderService não chamado
- [ ] `E03` "esquece" → end_turn, OrderService não chamado
- [ ] `E04` "peraí vou ver com o chefe" → end_turn, OrderService não chamado
- [ ] `E05` "não quero mais" → end_turn, OrderService não chamado

#### Grupo F: Multi-produto em uma mensagem

- [ ] `F01` "quero 3 shampoo e 2 condicionador" →
      buscar_produtos chamado pelo menos 1x → confirmar_pedido com 2 itens distintos
- [ ] `F02` "me manda: 10 heineken, 5 skol, 3 brahma" →
      confirmar_pedido final tem 3 itens (ou agente pede confirmação com 3 itens)

#### Grupo G: Quantidade ausente → agente pede esclarecimento

- [ ] `G01` "quero shampoo" (sem quantidade) →
      Claude retorna end_turn perguntando a quantidade → OrderService NÃO chamado
- [ ] `G02` "tem nescau? quero" (sem quantidade) →
      end_turn perguntando quantidade → OrderService NÃO chamado

#### Grupo H: Regressão dos testes do Sprint 2 (não deve quebrar)

- [ ] `H01` Equivalente ao antigo `test_agent_cliente_confirmar_pedido_cadeia_completa`
      ainda passa após mudança no system_prompt_template
- [ ] `H02` Equivalente ao `test_agent_cliente_max_iterations_nao_loop_infinito` ainda passa
- [ ] `H03` Equivalente ao `test_agent_cliente_persiste_mensagens_db` ainda passa
- [ ] `H04` Equivalente ao `test_agent_cliente_buscar_produtos_sem_catalog_service` ainda passa

**Observação de implementação para o Generator:**
Os testes dos grupos A–G são parametrizados via factory de mock: dado que Claude
retornaria tool_use X com input Y, o AgentCliente executa corretamente a ferramenta
e envia a resposta. O mock do Anthropic é construído com `side_effect` para simular
a sequência de chamadas. Não é necessário verificar o texto da mensagem enviada ao
WhatsApp — apenas que a ferramenta correta foi (ou não foi) chamada.

---

### E8 — Testes unitários do AgentRep

**Camadas:** Tests (unit)
**Arquivo(s):** `output/src/tests/unit/agents/test_agent_rep.py`
(reescrever o stub existente)

**Critérios de aceitação:**

- [ ] `R01` AgentRep.responder com buscar_produtos → CatalogService chamado
- [ ] `R02` AgentRep.responder com buscar_clientes_carteira →
      ClienteB2BRepo.buscar_por_nome chamado com tenant_id e representante_id corretos
- [ ] `R03` confirmar_pedido_em_nome_de com cliente válido (na carteira) →
      OrderService.criar_pedido_from_intent chamado, PDF gerado, gestor notificado
- [ ] `R04` confirmar_pedido_em_nome_de com cliente_b2b_id inválido (não na carteira) →
      OrderService NÃO chamado, resultado contém {"erro": ...}
- [ ] `R05` Pedido criado pelo rep tem representante_id preenchido no OrderService
- [ ] `R06` Persona.REPRESENTANTE usado em get_or_create_conversa
- [ ] `R07` AgentRep instanciado com catalog_service=None não lança exceção
      (retorna {"aviso": "Catálogo não disponível."} quando busca é chamada)
- [ ] `R08` max_iterations impede loop infinito (mesmo padrão do AgentCliente)

---

### E9 — Staging smoke do AgentRep

**Camadas:** Tests (staging)
**Arquivo(s):** `output/src/tests/staging/agents/test_agent_rep_staging.py`

**Critérios de aceitação:**
- [ ] `@pytest.mark.staging` — requer Postgres + Redis reais, sem WhatsApp real
- [ ] Seed: representante de teste com telefone `5519000000001`, tenant `jmb`,
      vinculado a pelo menos 1 cliente na tabela `clientes_b2b`
- [ ] Teste chama `AgentRep.responder` com Claude real + banco real
- [ ] Verificação: `conversa` e `mensagem` persistidos no banco para o rep de teste
- [ ] Teste de isolamento: `buscar_clientes_carteira` retorna só clientes
      do representante do tenant jmb, não de outro tenant

---

## Decisões pendentes

### DP-01 — Busca textual de clientes ✅ APROVADO

**Decisão:** `unaccent + ILIKE` — aprovado pelo usuário em 2026-04-16.

Implementar em `ClienteB2BRepo.buscar_por_nome()`:

```sql
AND unaccent(lower(nome)) ILIKE unaccent(lower('%' || :query || '%'))
```

`unaccent` é extensão nativa do PostgreSQL — sem migration extra além da 0013.
Cobre o caso mais comum de acentuação errada no celular ("sao" → "são",
"farmacia" → "farmácia") sem custo de trigrama.

Tech debt registrado: trigrama (`pg_trgm`) pode entrar no Sprint 5 se representantes
reportarem falhas de busca por typos mais graves.

---

## Fora do escopo

- Preço de custo e margem visível ao representante (Sprint 4)
- Alertas proativos de clientes inativos (Sprint 5)
- Pedido direto por cliente B2B para o representante (fluxo híbrido — Sprint 4)
- Interface de cadastro de clientes da carteira (Sprint 4 — painel gestor)
- Relatórios de performance por representante (Sprint 5)
- Busca fonética ou trigrama de clientes (Sprint 5)
- Segundo tenant (Sprint 5)
- Modificação do evaluator.py ou do fluxo de homologação

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Migration 0013 em banco com dados reais (clientes_b2b já tem rows) | Alta | Baixo | ALTER TABLE ADD COLUMN NULLABLE — sem downtime, sem perda |
| AgentRep validar cliente da carteira quando representante_id ainda NULL no banco | Média | Médio | Seed de homologação adiciona FK antes dos testes; staging smoke falha explicitamente |
| Testes do grupo C/D/F dependem de sequência exata de tool_use do mock | Média | Baixo | Mock com side_effect lista completa; se sequência variar, ajustar mock — não o agente |
| system_prompt_template muito longo → context window maior → latência | Baixa | Baixo | Medido em staging smoke — se p95 > 4s, truncar exemplos |

---

## Handoff para Sprint 4

Sprint 3 entrega:
- `AgentRep` funcional com carteira de clientes e pedido em nome de
- `ClienteB2B.representante_id` no schema e no tipo
- Suite de regressão de linguagem brasileira (30+ cenários)

Sprint 4 (Painel do gestor) pode partir de:
- Endpoint para cadastrar/vincular clientes à carteira de um representante
  (agora que a FK existe)
- Dashboard que exibe pedidos criados por representante_id
- Upload de planilha que inclui coluna `representante_responsavel`
