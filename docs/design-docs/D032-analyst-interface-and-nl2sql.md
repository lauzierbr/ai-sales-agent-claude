# D032 — AnalystAgent: tela web como interface principal + NL2SQL sobre commerce_*

**Status:** APROVADO (2026-05-01)
**Decisão de:** Lauzier (PO/Tech Lead) e Claude (arquitetura)
**Substitui:** Refina e estende [D031](D031-analyst-agent-observability.md) — define a interface concreta e o mecanismo de query
**Sprint alvo:** Sprint 11
**Relacionado a:** B-41, B-42 (busca lexical estrita + reads em commerce_orders), F-08 (clientes sem pedido há N dias)

---

## Contexto

D031 aprovou o AnalystAgent como meta-agente de observabilidade com persona admin via WhatsApp. Durante o piloto Sprint 10, observou-se um padrão recorrente:

- **Cada nova pergunta de negócio exige uma nova tool hardcoded** no AgentGestor (ranking_vendedores_efos, clientes_inativos_efos, relatorio_vendas_cidade_efos, ...). Adicionar "clientes sem pedidos há 90 dias" (F-08) seria mais um sprint.
- **Buscas lexicais estritas** falham em variações naturais (B-41: "Ariel supermercados" vs "ARIEL SUPERMERCADO LTDA").
- **Reads ad-hoc do banco** ficam refém de tools pré-existentes; perguntas exploratórias não são respondíveis.

A pesquisa do estado da arte (2024-2025) convergiu em três conclusões aplicáveis:

1. **Padrão híbrido** é o consenso: tools hardcoded para writes (lógica de negócio, validação, idempotência); NL2SQL read-only para reads analíticos.
2. **Schema documentado + few-shot real** atinge 80-90% de precisão em NL2SQL com Claude Sonnet em schemas pequenos como o nosso (~12 tabelas commerce_*).
3. **WhatsApp é ótimo para alertas push e perguntas curtas, mas quebra para uso analítico** — sem tabelas, links clicáveis, export ou histórico de queries.

---

## Decisão

Adotar o **padrão híbrido com NL2SQL** e **interface web como canal principal** do AnalystAgent.

### Componente 1 — Interface principal: `/dashboard/analyst`

Nova rota web com:

- Input de pergunta em linguagem natural
- Histórico das últimas N queries da sessão (cache por gestor admin)
- Resposta com markdown rico, tabelas estruturadas, links clicáveis para Langfuse
- Botões: "Exportar CSV", "Ver SQL gerado", "Copiar trace ID"
- Streaming via htmx para perguntas que demoram > 2s

**Por que web é principal:** análise é trabalho de tabela e link, não de texto corrido. WhatsApp tem 4096 chars/msg, sem tabelas, sem export — quebra para o caso de uso real do admin.

### Componente 2 — Canal complementar: persona ANALYST no WhatsApp (Sprint 12)

Reusa IdentityRouter (telefone do admin → `Persona.ANALYST` quando `gestores.role='admin'` e número está em allowlist específica).

**Uso restrito a:**
- Receber alertas push dos detectores D031 ("⚠️ Custo do bot 3x baseline na última hora")
- Perguntas curtas de status ("tem anomalia agora?", "custo de hoje?")
- Resposta sempre com link para `/dashboard/analyst?q=...` para investigação profunda

**Por que canal complementar:** alertas push são o forte do WhatsApp. Investigação aprofundada não é.

### Componente 3 — Mecanismo: NL2SQL read-only sobre `commerce_*`

Tool nova `consultar_dados(pergunta: str)` no AnalystAgent:

1. Recebe pergunta em português
2. Injeta contexto reduzido do schema (apenas tabelas autorizadas + descrições) no prompt
3. Few-shot com 5-10 queries reais do JMB no system prompt
4. Pede ao Claude para gerar SELECT com `LIMIT 200`
5. Valida AST com `pglast`: rejeita qualquer statement ≠ SELECT, qualquer CTE com side effect, qualquer referência a tabela fora da allowlist
6. Executa via role PostgreSQL `ai_readonly` com `statement_timeout = 5s`
7. Formata resultado para markdown (tabela) ou texto

**Tabelas autorizadas no NL2SQL:**
- `commerce_products`, `commerce_accounts_b2b`, `commerce_orders`, `commerce_order_items`, `commerce_inventory`, `commerce_sales_history`, `commerce_vendedores` (read-only EFOS)
- `pedidos`, `itens_pedido` (write model do bot — read-only para analyst)

**Tabelas NÃO autorizadas:**
- `gestores`, `representantes`, `clientes_b2b`, `usuarios` (PII)
- `contacts.channels` (telefones — usar projeções específicas)
- `mensagens_conversa`, `conversas` (dados de outras conversas — usar Langfuse)

### Componente 4 — Segurança em camadas

```sql
-- Camada 1: role PostgreSQL dedicado (Sprint 11 migration nova)
CREATE ROLE ai_readonly NOLOGIN;
GRANT CONNECT ON DATABASE ai_sales_agent TO ai_readonly;
GRANT USAGE ON SCHEMA public TO ai_readonly;
GRANT SELECT ON commerce_products, commerce_accounts_b2b,
                commerce_orders, commerce_order_items,
                commerce_inventory, commerce_sales_history,
                commerce_vendedores, pedidos, itens_pedido
                TO ai_readonly;
-- gestores, representantes, contacts, etc. NÃO concedidos

-- Conexão dedicada com role ai_readonly (não app role)
DATABASE_URL_AI_READONLY=postgresql://ai_readonly:senha@host/db
```

```python
# Camada 2: validação AST do SQL gerado
from pglast import parse_sql
from pglast.ast import SelectStmt

def validate_readonly_sql(sql: str, allowed_tables: set[str]) -> str:
    parsed = parse_sql(sql)
    if len(parsed) != 1:
        raise ValueError("multiple statements")
    stmt = parsed[0].stmt
    if not isinstance(stmt, SelectStmt):
        raise ValueError(f"not a SELECT: {type(stmt).__name__}")
    # walk AST → coletar tabelas referenciadas → checar allowlist
    ...
```

```
# Camada 3: prompt engineering
"Gere APENAS queries SELECT. Nunca INSERT/UPDATE/DELETE/DROP/CREATE/TRUNCATE."
"Tabelas disponíveis: <allowlist>. Não referencie outras."
```

```
# Camada 4: limites de execução
SET statement_timeout = '5s';
LIMIT 200;  -- injetado pelo wrapper, não pelo LLM
```

### Componente 5 — Tool de detecção (D031 original) coexiste

A tool `consultar_dados` é nova, mas as 4 tools de detecção já planejadas no D031 (`cost_breakdown`, `top_anomalies`, `conversation_summary`, detectores) permanecem como hardcoded — são lógica de negócio observacional sobre Langfuse, não SQL ad-hoc.

---

## Consequências

### Positivas

- **Escalabilidade do produto:** novas perguntas analíticas viram zero código (basta ajustar few-shot ou criar query favorita)
- **B-41 e B-42 resolvidos transitivamente:** Claude entende variações de nome no LLM-side e pode gerar SQL com ILIKE/unaccent/JOIN em commerce_orders sem nova tool
- **F-08 fica trivial:** "clientes sem pedidos há 90 dias" é uma pergunta NL2SQL imediata
- **Diferencial competitivo:** distribuidoras pequenas raramente têm BI; ter "pergunte ao banco em português" é vendável
- **Custo controlado:** queries com LIMIT 200 + statement_timeout 5s + role read-only

### Negativas

- **Risco de hallucination de schema:** mitigado por few-shot real e validação AST + fallback amigável
- **Risco de prompt injection via dados do banco:** mitigado por não injetar valores brutos do banco no contexto do LLM antes de formatar a resposta
- **Custo de manutenção do schema documentado:** comentários nas tabelas commerce_* devem ser mantidos atualizados — virou contrato com o LLM
- **Investimento inicial:** Sprint 11 fica mais carregado (era D031 simples, agora é D031 + NL2SQL + tela analyst)

### Migrações implícitas

- **Migration nova:** `CREATE ROLE ai_readonly` + GRANTs explícitos
- **Variável Infisical nova:** `DATABASE_URL_AI_READONLY` (development + staging)
- **Dependência nova:** `pglast` (PostgreSQL AST parser, MIT license)

---

## Por que NÃO MCP server externo agora

A pesquisa identificou MCP servers maduros para PostgreSQL (`@modelcontextprotocol/server-postgres`, pgEdge). Avaliados e descartados nesta fase:

1. **Latência extra:** MCP é processo separado com IPC; NL2SQL inline economiza 100-200ms por query
2. **Controle granular:** validação AST + role específico no banco oferece controle mais fino que delegar ao MCP server
3. **Footprint:** MCP server adiciona um processo Node ou outro binário ao deploy; NL2SQL inline reusa o que já existe
4. **Multi-tenant:** MCP servers públicos não consideram tenant_id — teria que customizar de qualquer jeito

**Quando MCP fará sentido:** se o produto evoluir para multi-tenant em escala (10+ tenants) com schemas heterogêneos (cada tenant com ERP diferente), um MCP server por tenant seria considerado. Hoje é over-engineering.

---

## Por que NÃO semantic layer (dbt MetricFlow / Cube) agora

Pesquisa indicou ganho de precisão de 16% → 83% com semantic layer. Mas:

1. **Custo de manutenção alto:** definir métricas, dimensões, joins canônicos em YAML/SQL — outro produto para manter
2. **Schema atual é simples:** 12 tabelas commerce_* com nomes descritivos e relações claras; few-shot resolve 80%+ sem semantic layer
3. **Reavaliar quando:** se a taxa de erro do NL2SQL inline ficar acima de 30% após 1 sprint de uso, semantic layer entra na pauta

---

## Roadmap

### Sprint 11

1. Migration: `CREATE ROLE ai_readonly` + GRANTs
2. Domínio `analyst/` (config, repo, service, runtime, ui) com `AnalystAgent`
3. Endpoint `/dashboard/analyst` (admin gate via D023+gestores.role)
4. Tool `consultar_dados(pergunta)` no AnalystAgent com NL2SQL + validação AST
5. Detectores D031 (cost_outlier, recovery_destrutivo, loop, tool_failure)
6. Few-shot inicial com 8-10 queries reais JMB no system prompt
7. Comentários SQL nas tabelas `commerce_*` (`COMMENT ON TABLE/COLUMN ... IS '...'`)

### Sprint 12

1. Persona ANALYST no IdentityRouter (telefone admin → AnalystAgent)
2. Alertas push WhatsApp dos detectores
3. Comando WhatsApp → resposta resumida + link para `/dashboard/analyst`
4. Histórico de queries por usuário
5. "Salvar como query favorita" (templates reutilizáveis)

### Sprint 13+

- Avaliação de precisão real do NL2SQL (taxa de erro, queries que precisaram retry)
- Decisão sobre semantic layer baseada em métricas
- Expansão para AgentGestor (substituir tools EFOS hardcoded por NL2SQL com role específico)

---

## Decisões pendentes (para Sprint 11)

1. **Modelo do AnalystAgent:** Sonnet ou Haiku? NL2SQL exige raciocínio sobre schema — sugestão: Sonnet inicial, comparar com Haiku após 2 semanas com queries reais.
2. **Cache de queries:** mesmas perguntas no mesmo dia retornam cached? Reduz custo mas pode mascarar dados que mudaram em sync.
3. **Allowlist de IPs / 2FA para `/dashboard/analyst`:** queries arbitrárias em produção exigem mais que cookie? Considerar para Sprint 12.

---

## Referências

- Relatório de pesquisa: `artifacts/sweep_analyst_research_2026-05-01.md` (gerado durante esta decisão)
- [D031](D031-analyst-agent-observability.md) — base original do AnalystAgent
- [D013](index.md#d013) — camadas fixas (analyst/ é novo domínio)
- [arxiv 2408.05109](https://arxiv.org/abs/2408.05109) — Survey of Text-to-SQL in the Era of LLMs
- [dbt Semantic Layer vs Text-to-SQL 2026](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
- [pgEdge Postgres MCP](https://www.pgedge.com/blog/introducing-the-pgedge-postgres-mcp-server)
- [OWASP SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- B-41, B-42 — bugs que NL2SQL resolve transitivamente
- F-08 — feature exemplar que vira zero-código com NL2SQL
