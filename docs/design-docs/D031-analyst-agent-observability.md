# D031 — AnalystAgent: meta-agente de observabilidade do produto

**Status:** APROVADO (2026-04-29)
**Decisão de:** Lauzier (PO/Tech Lead) e Claude (arquitetura)
**Relacionado a:** D030 (adapter pattern), B-30 (pré-requisito — generations no Langfuse), F-05 (entrada de produto no backlog)

---

## Contexto

O produto AI Sales Agent já é um sistema de agentes conversacionais. Hoje, quando
algo dá errado em produção, alguém precisa ler manualmente logs do uvicorn,
inspecionar Langfuse, consultar o banco e correlacionar tudo. Casos recentes
investigados manualmente: B-26 (recovery destrutivo de histórico), B-28 (alucinação
"instabilidade de ID"), B-30 (generations não criadas no Langfuse).

Cada investigação custou tempo de análise nosso. Conforme o produto escala
(múltiplos tenants, múltiplos canais, múltiplos ERPs), esse trabalho cresce
linearmente — vira gargalo.

A solução proposta é **adicionar um meta-agente** (AnalystAgent) que tem como
input não os clientes/produtos do tenant, mas os **traces dos próprios agentes
operando**. Ele extrai inteligência operacional de conversas, custos, anomalias
e qualidade.

Isso vira **diferencial de produto** porque automatiza uma capacidade que normalmente
requer engenheiro especializado (análise de observabilidade LLM).

---

## Decisão

Adotar arquitetura de **AnalystAgent** como persona separada do produto, com
3 modos de operação complementares e adapter para Langfuse (com possibilidade
futura de Datadog/OTel).

### Decisões confirmadas pelo PO (2026-04-29)

1. **Escopo MVP:** 3 tools básicas — `cost_breakdown`, `top_anomalies`,
   `conversation_summary`. Endpoint dashboard `/dashboard/insights` com relatório
   semanal. Persona acessível via WhatsApp para admin.

2. **Persona separada:** AnalystAgent exclusivo para admin/operador do app.
   **NÃO integrar ao AgentGestor** — análise técnica (alucinações, custo,
   generations, recovery destrutivo) é vocabulário de engenharia que confunde
   o gestor de tenant. Um dia o gestor pode ter versão simplificada
   ("KPIs do meu negócio") via outro agente irmão (`ManagerInsightsAgent`),
   mas isso é futuro.

3. **Sprint alvo:** Sprint 11. Depende do Sprint 10 ter corrigido B-30 (sem
   generations no Langfuse, não há o que analisar).

4. **Multi-persona futuro preparado, não implementado:** arquitetura permite
   adicionar `ManagerInsightsAgent` no futuro sem refatorar. Mas hoje só admin.

5. **Privacidade:** dados de traces incluem mensagens de usuários. Considerados
   **dados internos por enquanto** — admin tem acesso a tudo, sem redação de
   PII. Decisão revisitada quando o produto for vendido para múltiplos tenants
   externos.

### 3 modos de operação

**Modo 1 — Sob demanda (chat)**
Persona Analyst no WhatsApp para admin: "Resume operação do JMB hoje" → relatório.

**Modo 2 — Proativo (scheduled)**
Roda diariamente às 8h, manda relatório consolidado pro admin.

**Modo 3 — Event-driven (alertador)**
Hooks que disparam quando padrões críticos aparecem (loop, alucinação repetida,
custo outlier, recovery destrutivo).

MVP entrega Modo 1 + relatório semanal scheduled (light). Modos 2+3 completos
ficam para Sprint 12+ (sprint Y/Z do roadmap).

### Arquitetura

```
output/src/insights/                    ← novo domínio (7º)
├── types.py                            ← TraceSummary, Anomaly, Insight
├── config.py                           ← thresholds (cost outlier, loop_max_tools)
├── repo.py                             ← persistência insights_runs
├── service.py                          ← orquestra análises
├── runtime/
│   └── analyst_agent.py                ← agente conversacional
├── ports/
│   └── observability.py                ← Protocol ObservabilityAdapter
└── ui.py                               ← rota /dashboard/insights

output/src/integrations/connectors/
└── langfuse/                           ← novo adapter
    ├── client.py                       ← wrapper REST (basic auth)
    ├── traces.py                       ← list/get/aggregate
    ├── generations.py                  ← list/aggregate
    └── analyzer.py                     ← detectores de anomalia
```

**Camadas:** mesma hierarquia (Types → Config → Repo → Service → Runtime → UI).
`insights/` consome `integrations/connectors/langfuse` como `agents/` consome
`commerce/`. import-linter atualizado.

**Adapter pattern (D030):** se amanhã trocar Langfuse por Datadog/OTel direto,
troca o adapter. Domain core de insights não muda.

### Persona Analyst no IdentityRouter

Adicionar como **4ª persona** depois de gestor, rep, cliente:

```python
class Persona(str, Enum):
    DESCONHECIDO = "desconhecido"
    CLIENTE_B2B = "cliente"
    REPRESENTANTE = "rep"
    GESTOR = "gestor"
    ANALYST = "analyst"  # ← novo, exclusivo do app admin
```

Cadastro de admin numa tabela `app_admins` separada (não em `gestores` que é
multi-tenant). IdentityRouter prioriza: `app_admins → gestores → representantes
→ clientes_b2b`.

### Tools do MVP (Sprint 11)

```python
@tool("cost_breakdown")
async def cost_breakdown(
    period: str,            # "hoje", "7d", "30d"
    group_by: str,          # "persona" | "day" | "tool" | "tenant"
    tenant_id: str | None,  # filtro opcional
) -> dict:
    """Decomposição de custo agregado por dimensão."""

@tool("top_anomalies")
async def top_anomalies(
    period: str,
    types: list[str] | None,  # ["loop", "hallucination", "cost_outlier", ...]
    limit: int = 10,
) -> list[dict]:
    """Lista top N anomalias detectadas no período."""

@tool("conversation_summary")
async def conversation_summary(
    trace_id: str,
) -> dict:
    """Análise detalhada de uma conversa específica:
    - Sequência de tool calls e resultados
    - Pontos de erro / fallback / recovery
    - Custo total
    - Avaliação qualitativa (LLM-as-judge light)"""
```

### Anomaly detectors do MVP

1. **Loop infinito**: `n_tool_calls > 10` em 1 conversa
2. **Cost outlier**: trace com `total_cost > z_score(3)` sobre média do tenant
3. **Recovery destrutivo (B-26)**: presença de `historico_corrompido_recovery`
   no log da conversa
4. **Tool failure repetido**: mesma tool falhou >= 3x no período

Sprint 12+ adiciona: alucinação semântica (LLM-as-judge), latency outlier,
abandono (conversa sem confirmação), violação de feedback histórico.

### Persistência: tabela `insights_runs`

```sql
CREATE TABLE insights_runs (
    id UUID PRIMARY KEY,
    tipo VARCHAR(32),              -- "cost", "anomalies", "summary", "scheduled"
    parametros JSONB,              -- input args
    resultado JSONB,               -- output gerado
    custo_geracao DECIMAL,         -- meta-custo (LLM da própria análise)
    duracao_ms INT,
    criado_por VARCHAR(64),        -- admin que pediu OR "scheduler"
    criado_em TIMESTAMPTZ DEFAULT NOW()
);
```

Útil para:
- Auditoria: quem pediu o quê
- Cache: análises repetidas reusam resultado se janela igual
- Tendência: comparar custo desta semana vs anterior

### Dashboard `/dashboard/insights`

MVP renderiza:
- KPIs do período (custo, conversas, anomalias)
- Top 10 anomalias com link pro trace no Langfuse
- Gráfico simples de custo/dia (pode ser tabela no MVP, gráfico depois)
- Botão "rodar análise agora" que dispara AnalystAgent

---

## Consequências

### Positivas

- **Diferencial de produto**: poucos sistemas SaaS de agentes têm meta-observabilidade
  conversacional. Pode ser argumento comercial.
- **Reduz tempo de investigação** de bugs/incidentes drasticamente.
- **Identifica oportunidades de produto** automaticamente (perguntas frequentes
  sem tool, capacidades subutilizadas).
- **Governance de custo**: alerta quando algo está fora do esperado.
- **Fundação para evals automatizados** futuros (LLM-as-judge no Langfuse).
- **Reusa infraestrutura existente** (Langfuse, Claude SDK, Anthropic, dashboard).

### Negativas

- **Custo recursivo**: o próprio AnalystAgent gera tokens (analisa traces e
  gera relatório usando LLM). Precisa monitorar para não virar gasto descontrolado.
  Mitigação: cache em `insights_runs` + scheduled em vez de on-demand para
  consultas pesadas.
- **Complexidade adicional**: novo domínio, novo adapter, nova persona. Mais
  superfície de teste.
- **Privacidade futura**: quando produto sair do single-tenant, redação de PII
  vira obrigatória. Atrasar essa decisão tem risco.

### Migrações implícitas

- Migration nova: `app_admins` (telefone, nome, email, ativo)
- Migration nova: `insights_runs`
- Persona ANALYST adicionada ao enum `Persona`
- import-linter: novo contrato `insights → integrations/langfuse, agents (read-only?)`

---

## Roadmap detalhado

### Sprint 11 (MVP) — ~10-14 dias

**Pré-requisito:** B-30 corrigido no Sprint 10.

**Entregas:**
1. LangfuseAdapter (read-only) com list_traces, get_trace, aggregate
2. Domínio `insights/` (types, config, repo, service)
3. AnalystAgent runtime com 3 tools (cost_breakdown, top_anomalies,
   conversation_summary)
4. Tabela `app_admins` + persona ANALYST no IdentityRouter
5. 4 anomaly detectors (loop, cost_outlier, recovery_destrutivo,
   tool_failure_repeated)
6. Endpoint `/dashboard/insights` (MVP minimalista)
7. WhatsApp: admin pode conversar com Analyst

**Critério de pronto:** admin pergunta "como foi a semana" e recebe relatório
com custo agregado + top 3 anomalias.

### Sprint 12 (Anomaly + Quality)

- 5+ anomaly detectors avançados
- LLM-as-judge para qualidade (1-5 score em coerência, alucinação, cumprimento
  de feedback)
- Tendência: gráficos de custo/anomalia/dia
- Cache em insights_runs

### Sprint 13 (Proativo + Sugestões)

- Scheduled diário (relatório automatizado)
- Event-driven alerts (anomalia crítica → push imediato)
- Sugestões de prompt (tools subutilizadas, capacidades não anunciadas)
- A/B comparativo entre versões de prompt

### Futuro (não datado)

- ManagerInsightsAgent (versão simplificada para gestor de tenant — KPIs
  de negócio em vez de técnico)
- Multi-tenant: análises por tenant, comparação cross-tenant (admin vê tudo)
- Redação de PII para relatórios compartilháveis
- Outros adapters de observabilidade (Datadog, OTel direto)

---

## Decisões pendentes

1. **Sequenciamento Sprint 11:** Bling adapter (D030) + AnalystAgent é muito
   pra 1 sprint. Sugestão: Sprint 11 = AnalystAgent (foco em diferencial),
   Sprint 12 = Bling read-only, Sprint 13 = Bling write + Analyst sprint Y.
   Confirmar em planejamento de sprint.

2. **Modelo do AnalystAgent:** Sonnet 4.6 ou Haiku para análises baratas?
   Recomendação: Sonnet para conversa, Haiku para classificadores de anomalia
   (loop detection, etc).

3. **Threshold defaults** para detectors. Sugestão: começar conservador
   (loop > 10 calls, cost > $0.20) e ajustar com dados reais.

---

## Referências

- B-30 (BUGS.md) — pré-requisito (generations no Langfuse)
- D030 (design-docs) — adapter pattern (modelo seguido)
- F-05 (BACKLOG.md) — entrada de produto correspondente
- Langfuse REST API: http://100.113.28.85:3000 (staging)
