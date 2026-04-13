# Decisões Arquiteturais — AI Sales Agent

Log de decisões técnicas. Atualizar sempre que uma nova decisão for tomada.

## Índice

| ID | Título | Sprint | Status |
|----|--------|--------|--------|
| D001 | Produto SaaS multi-tenant desde o início | Planejamento | ok |
| D002 | Infisical para gestão de secrets | Planejamento | ok |
| D003 | Claude Agent SDK + FastAPI + PostgreSQL | Planejamento | ok |
| D004 | Evolution API para WhatsApp | Planejamento | ok |
| D005 | Preço padrão via crawler, diferenciados via Excel | Planejamento | ok |
| D006 | Crawler apenas do site B2B | Planejamento | ok |
| D007 | Harness com sprints (não rounds autônomos) | Planejamento | ok |
| D008 | Deploy inicial no mac-mini-lablz | Planejamento | ok |
| D009 | Crawler via Playwright (não API REST) | Planejamento | ok |
| D010 | Sprints de infra antes do Sprint 0 | Planejamento | ok |
| D011 | Sprints de infra via Claude Code direto | Planejamento | ok |
| D012 | Repository knowledge como system of record | Planejamento | ok |
| D013 | Arquitetura em camadas fixas (Types→UI) | Planejamento | ok |
| D014 | VictoriaMetrics + VictoriaLogs para observabilidade | Planejamento | ok |
| D015 | Memory Stores: separação e mapeamento (Managed Agents Fase 2) | Planejamento | ok |
| D016 | Modelo de embeddings: text-embedding-3-small (OpenAI) | Sprint 0 | ok |
| D017 | Schema PostgreSQL multi-tenant: tabela compartilhada com tenant_id no Sprint 0 | Sprint 0 | ok |
| D018 | Trigger do crawler: on-demand via POST /catalog/crawl (sem scheduler no Sprint 0) | Sprint 0 | ok |

---

## D012 — Repository knowledge como system of record
Inspirado no artigo da OpenAI "Harness Engineering" (fev/2026).
AGENTS.md é mapa (~80 linhas), não enciclopédia. Conteúdo vive em docs/.
Conhecimento que não está no repo não existe para o agente.

## D013 — Arquitetura em camadas fixas (Types → Config → Repo → Service → Runtime → UI)
Inspirado no artigo da OpenAI. Agentes replicam padrões em escala.
Camadas fixas com import-linter enforçadas mecanicamente no CI.
Violações bloqueiam com mensagens de remediação injetadas no contexto do agente.

## D014 — VictoriaMetrics + VictoriaLogs para observabilidade
Single binary, PromQL + LogQL, extremamente leve para mac-mini.
OpenTelemetry desde Sprint 1 permite que o Evaluator consulte métricas
diretamente — prompts como "garanta latência < 3s p95" se tornam verificáveis.

## D016 — Modelo de embeddings: `text-embedding-3-small` (OpenAI)
Anthropic não oferece endpoint de embedding standalone. Voyage AI exige `VOYAGE_API_KEY` extra.
`text-embedding-3-small` via `AsyncOpenAI`: 1536 dims, $0.02/1M tokens, assíncrono, substituível por Voyage no Sprint 5 com mudança de config.
Variável Infisical: `OPENAI_API_KEY` (dev + staging).

## D017 — Schema PostgreSQL multi-tenant no Sprint 0: tabela compartilhada
`docs/DESIGN.md` e `docs/SECURITY.md` antecipam "schema por tenant" — referem-se à arquitetura final (Sprint 1+).
No Sprint 0, pgvector `<=>` requer tabela única para índice `ivfflat` eficiente. Schemas separados criam footgun de `search_path` para busca semântica.
Decisão: schema `public`, coluna `tenant_id TEXT NOT NULL` em `produtos`. Toda query filtra por `tenant_id`. Schemas por tenant entram no Sprint 1 para outras entidades.

## D018 — Trigger do crawler: on-demand via `POST /catalog/crawl`
Scheduler automático (APScheduler, Celery beat) pertence ao Sprint 1 (infra de aplicação).
No Sprint 0, o endpoint `POST /catalog/crawl` dispara crawl síncrono e retorna `CrawlStatus`. Agendamento recorrente é out of scope.

(Decisões D001-D011 em docs/design-docs/decisoes-planejamento.md)
