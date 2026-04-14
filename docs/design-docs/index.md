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
| D019 | Scheduler de crawl: APScheduler 3.x AsyncIOScheduler (embedded, sem broker) | Sprint 1 | ok |
| D020 | Multi-tenant Sprint 1+: manter tabela compartilhada + tenant_id para todos os domínios | Sprint 1 | ok |
| D021 | Auth JWT: PyJWT + HS256, access token 8h, sem refresh em Sprint 1 | Sprint 1 | ok |
| D022 | Auth scope: TenantProvider via X-Tenant-ID; JWT apenas para ações privilegiadas; webhook via HMAC-SHA256 | Sprint 1 | ok |

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

## D019 — Scheduler de crawl: APScheduler 3.x AsyncIOScheduler

**Contexto:** Sprint 1 introduz agendamento automático de crawl por tenant. Alternativas avaliadas: APScheduler 3.x embedded, Celery beat (broker Redis), asyncio loop interno.

**Decisão:** APScheduler 3.x com `AsyncIOScheduler`.

**Rationale:** Zero broker adicional (Redis já existe mas para cache/sessão, não filas); API async nativa; adequado para 1–20 tenants no mac-mini; substituível por Celery sem mudança de interface de serviço se escala exigir.

**Trade-off:** Com múltiplas instâncias do app (ex. Gunicorn multi-worker), cada worker dispara jobs duplicados. Mitigado por Redis SETNX lock por tenant. Em escala real (>50 tenants), migrar para Celery beat.

**Variável Infisical:** nenhuma nova (usa `REDIS_URL` existente para lock).

---

## D020 — Multi-tenant Sprint 1+: tabela compartilhada + tenant_id para todos os domínios

**Contexto:** SECURITY.md e DESIGN.md antecipavam "schema por tenant" como arquitetura final. D017 usou tabela compartilhada para catalog por limitação do pgvector. Discussão Sprint 1: extender schema por tenant para novos domínios ou uniformizar shared table.

**Decisão:** Tabela compartilhada com `tenant_id TEXT NOT NULL` para TODOS os domínios em Sprint 1 (tenants, usuarios, crawl_schedule, agentes).

**Rationale:** `search_path` dinâmico com asyncpg connection pool é footgun comprovado — conexões reutilizadas podem vazar search_path entre requests. TenantProvider middleware + lint rule de tenant_id obrigatório oferecem isolamento lógico equivalente ao isolamento físico por schema para o escopo atual. Schema por tenant pode ser introducido em sprint dedicado de hardening antes de produção com múltiplos tenants reais.

**Trade-off:** Isolamento lógico (não físico). Um bug de middleware poderia vazar dados entre tenants — mitigado por testes de isolamento obrigatórios em cada sprint.

---

## D021 — Auth JWT: PyJWT + HS256, access token 8h, sem refresh em Sprint 1

**Contexto:** Sprint 1 introduz autenticação para gestores acionarem endpoints privilegiados (crawl, futuro painel).

**Decisão:** PyJWT 2.x, algoritmo HS256, access token com TTL 8h. Sem refresh token em Sprint 1.

**Rationale:** PyJWT é mais simples que python-jose (sem dependência de criptografia adicional). HS256 com segredo forte (256 bits, Infisical) é adequado para sistema single-service. RS256 seria preferível em arquitetura multi-serviço com validação distribuída — não é o caso agora. 8h cobre uma sessão de trabalho completa sem necessidade de refresh.

**Claims do token:** `sub` (user_id), `tenant_id`, `role` (gestor|rep|cliente), `exp`, `iat`.

**Variável Infisical:** `JWT_SECRET` (development + staging).

---

## D022 — Auth scope: três camadas de autenticação por tipo de endpoint

**Contexto:** O sistema tem três tipos de caller: gestor via painel web, webhook da Evolution API (WhatsApp), agentes internos.

**Decisão:**
- `GET /catalog/*`, `POST /catalog/crawl` (trigger manual): requer **JWT de gestor** em `/catalog/crawl`; `GET /catalog/*` requer apenas **X-Tenant-ID** válido (TenantProvider)
- `POST /webhook/whatsapp`: validação **HMAC-SHA256** do payload com `EVOLUTION_WEBHOOK_SECRET` (header `X-Evolution-Signature`)
- `GET|POST /tenants/*`, `POST /auth/login`: sem auth em Sprint 1 (endpoints internos, acesso via rede local ou script)
- Todos os endpoints: TenantProvider middleware valida X-Tenant-ID e injeta tenant no request.state

**Rationale:** JWT para webhook WhatsApp seria over-engineering — Evolution API é self-hosted na mesma rede, HMAC-SHA256 é o padrão de webhooks. Endpoints /tenants/* são admin-only via script em Sprint 1; receberão auth de plataforma em Sprint futuro.

**Variável Infisical:** `EVOLUTION_WEBHOOK_SECRET` (development + staging).

---

(Decisões D001-D011 em docs/design-docs/decisoes-planejamento.md)
