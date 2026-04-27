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
| D008 | Deploy inicial no macmini-lablz | Planejamento | ok |
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
| D023 | Dashboard web: Jinja2+htmx+CSS puro, auth via DASHBOARD_SECRET + cookie HttpOnly JWT | Sprint 4 | ok |
| D024 | Langfuse v2 self-hosted Docker para observabilidade LLM | Sprint 5 | ok |
| D025 | Integração EFOS via backup diário SSH/SFTP (sem crawler Playwright) | Sprint 8 | ok |
| D026 | Domínio integrations/ isolado de domínios de negócio por import-linter | Sprint 8 | ok |
| D027 | Domínio commerce/ como camada de dados EFOS normalizada | Sprint 8 | ok |
| D028 | Langfuse session_id + update_current_observation em todos os agentes | Sprint 8 | ok |
| D029 | Staging DB efos_staging destruído em bloco finally após cada sync | Sprint 8 | ok |

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

## D023 — Dashboard web: Jinja2 + htmx + CSS puro, auth via DASHBOARD_SECRET cookie

**Contexto:** Sprint 4 introduz o primeiro dashboard web para o gestor. Decisão DP-01
determina que o dashboard é entregue no mesmo sprint que o AgentGestor WhatsApp.
Alternativas avaliadas: (a) Jinja2+htmx (sem build step), (b) Streamlit (serviço
separado), (c) React/Next.js (build step + SPA).

**Decisão:**
- **Stack frontend:** Jinja2 templates + htmx + CSS puro, sem build step, sem framework JS
  pesado. Paleta visual reutiliza `catalog/templates/` (dark navy #1a1a2e, accent #e94560).
- **Real-time:** htmx polling `hx-trigger="every 30s"` nas KPIs do home. SSE/WebSocket
  somente Sprint 5 se necessário.
- **Auth:** `DASHBOARD_SECRET` (env var Infisical, senha compartilhada por tenant) +
  `DASHBOARD_TENANT_ID` (env var Infisical). Login via `hmac.compare_digest` (imune a
  timing attack). Sucesso → cookie `dashboard_session` (JWT HttpOnly SameSite=Lax 8h,
  reutiliza `JWT_SECRET` de D021). Sem tabela de usuários em Sprint 4.
- **Exclusão do TenantProvider:** prefixo `/dashboard` adicionado a `_EXCLUDED_PREFIXES`;
  tenant resolvido via cookie, não via `X-Tenant-ID` header.

**Rationale:** Jinja2+htmx já é o padrão do projeto (Sprint 0). Zero build step — funciona
com `uvicorn` sem configuração extra. Streamlit exigiria processo separado + port forwarding
adicional no mac-mini. React exigiria build pipeline não justificável para MVP single-tenant.
`hmac.compare_digest` é obrigatório para evitar timing attack em comparação de senhas.
Auth multi-usuário (um login por gestor com email/senha) entra no Sprint 5.

**Trade-off:** Senha única por tenant = se vazar, todos os gestores do tenant precisam
trocar. Mitigado em Sprint 5 com auth por usuário. Para piloto JMB (1 gestor = o próprio
Lauzier), é aceitável.

**Variáveis Infisical:** `DASHBOARD_SECRET` e `DASHBOARD_TENANT_ID` (development + staging).

---

## D024 — Langfuse v2 self-hosted Docker para observabilidade LLM

**Contexto:** Sprint 5 requer traces por conversa, custo por token e avaliação de qualidade dos 3 agentes (AgentCliente, AgentRep, AgentGestor). Sem observabilidade LLM, não é possível auditar custos nem detectar respostas ruins em produção.

**Alternativas avaliadas:**
- **Langfuse Cloud (free tier):** mais rápido de configurar; sem infra extra; mas dados saem da máquina local e free tier tem limites de volume.
- **OTEL customizado:** já temos OTEL (VictoriaMetrics), mas sem UI de traces LLM e custo de token.
- **Phoenix (Arize):** alternativa open-source; menos madura que Langfuse para integração com Anthropic SDK.
- **Langfuse v2 self-hosted Docker:** zero custo, dados locais, SDK Python maduro com `@observe()` decorator nativo para async.

**Decisão:** Langfuse v2 self-hosted Docker — dois serviços novos no docker-compose: `langfuse` (imagem `langfuse/langfuse:2`) e `langfuse-db` (Postgres 16 dedicado).

**Instrumentação:** `langfuse.decorators.observe` em `processar_mensagem` dos 3 agentes. `LANGFUSE_ENABLED=false` desabilita em unit tests. `langfuse.flush()` no lifespan FastAPI.

**Impacto:** ~1GB RAM extra no dev/staging; 6 novos secrets no Infisical (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT` — por ambiente). Langfuse importado apenas em Runtime (camada permitida por import-linter).

**Trade-off:** Requer setup manual de projeto/chaves no UI Langfuse após primeiro boot. Mitigado documentando o passo no handoff do Generator.

---

(Decisões D001-D011 em docs/design-docs/decisoes-planejamento.md)

## D025 — Integração EFOS via backup diário SSH/SFTP

**Contexto:** Sprint 8 precisa expor dados reais de vendas/clientes do ERP EFOS (Webrun) para o AgentGestor. O crawler Playwright era frágil (dependente de sessão web), lento e difícil de manter.

**Decisão:** Substituir crawler por pipeline SSH/SFTP + pg_restore diário. O servidor Windows do cliente gera um dump PostgreSQL às ~16:30 BRT. O pipeline baixa o arquivo via paramiko, restaura em banco efos_staging, normaliza e publica nas tabelas commerce_*.

**Rationale:** Dump PostgreSQL é determinístico, versionável por checksum SHA-256, e pg_restore é ordens de magnitude mais rápido que scraping. SSH não requer credenciais web. O arquivo existe independente de sessão/CSRF.

**Trade-off:** Depende de acesso SSH ao servidor Windows do cliente. Dados têm latência de ~24h. Mitigado pelo fato de que relatórios do gestor não exigem dados em tempo real.

## D026 — Domínio integrations/ isolado de domínios de negócio

**Decisão:** `src.integrations.*` é um domínio técnico que não importa `agents/`, `catalog/`, `orders/`, `tenants/` ou `dashboard/`. Enforçado por import-linter (contrato adicionado em pyproject.toml). O conector normaliza dados para `commerce/types.py` como camada intermediária.

**Rationale:** Evita acoplamento entre pipeline de dados e lógica de negócio. O conector pode ser substituído (ex: por API REST EFOS futura) sem tocar em agentes.

## D027 — Domínio commerce/ como camada de dados EFOS normalizada

**Decisão:** `src.commerce.types` define dataclasses puras (`CommerceProduct`, `CommerceAccountB2B`, etc.) e `src.commerce.repo` expõe queries agregadas sobre `commerce_*`. Sem `service.py` nem `runtime/`. Isolado de todos os outros domínios por import-linter.

**Rationale:** Separação limpa entre dados de origem EFOS (commerce/) e dados transacionais do agente (orders/, agents/). Futuro: migrar leituras de catálogo de `catalog/` para `commerce_products`.

## D028 — Langfuse session_id + update_current_observation em todos os agentes

**Contexto:** Bug B-12 no piloto JMB: traces Langfuse não tinham session_id nem output, impossibilitando análise por conversa.

**Decisão:** Todos os 3 agentes (`agent_cliente`, `agent_rep`, `agent_gestor`) agora:
1. Chamam `_get_anthropic_client(session_id=str(conversa.id))` — seta `session_id` no trace Langfuse.
2. Chamam `_lf_ctx.update_current_observation(output=resposta_final)` antes de retornar — popula o campo output do span.

**Impacto:** Traces Langfuse agora navegáveis por conversa; custo por mensagem visível.

## D029 — Staging DB efos_staging destruído em bloco finally após cada sync

**Decisão:** O banco temporário `efos_staging` é criado no início do sync e dropado em bloco `finally` — executado mesmo em caso de erro. Isso garante que o banco não acumule schema corrompido em runs consecutivos (gotcha: segunda restauração falha se schema anterior persiste).

**Rationale:** pg_restore em banco existente pode conflitar com constraints e índices. DROP/CREATE é atômico e idempotente. O bloco `finally` garante limpeza mesmo quando `stage()` ou `normalize()` lançam exceções.
