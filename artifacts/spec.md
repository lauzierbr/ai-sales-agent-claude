# Sprint 0 — Catálogo (Crawler + Enriquecimento + pgvector)

**Status:** Planning  
**Data:** 2026-04-13  
**Pré-requisitos:** Sprint Infra-Dev ✅, Sprint Infra-Staging ✅

---

## Objetivo

Ao final deste sprint, o sistema terá um pipeline completo de catálogo de produtos: crawler Playwright autenticado no site EFOS da JMB, enriquecimento via Claude Haiku, armazenamento com embeddings pgvector, upload de preços diferenciados via Excel, e endpoints FastAPI com painel Jinja2 para revisão de produtos.

---

## Contexto

Por que agora: as sprints de infra estão concluídas. O agente de vendas (Sprint 2) depende de um catálogo enriquecido e pesquisável por semântica. Sem o Sprint 0, o agente não consegue responder "tem shampoo Natura?" ou recuperar preços diferenciados por cliente. Sprint 0 é o fundamento de produto.

Problema resolvido: JMB possui ~N mil produtos no EFOS. Não há API. O único acesso é via browser autenticado. Os nomes de produto são brutos (ex: "SHAM HID NAT 300ML CX12"). O agente precisa de nomes, marcas, tags e texto de busca semântica para responder bem.

---

## Decisões Arquiteturais (ADRs aprovados neste sprint)

### D016 — Modelo de embeddings: `text-embedding-3-small` (OpenAI)
**Contexto:** Anthropic não oferece endpoint de embedding standalone. Voyage AI é affiliated com Anthropic mas exige `VOYAGE_API_KEY` extra e SDK separado.  
**Decisão:** `text-embedding-3-small` via `AsyncOpenAI`, 1536 dimensões.  
**Razão:** SDK maduro, assíncrono, $0.02/1M tokens, troca por Voyage no Sprint 5 com mudança de config.  
**Variável Infisical:** `OPENAI_API_KEY` (dev + staging)  
**Status:** ok

### D017 — Schema PostgreSQL multi-tenant no Sprint 0: tabela compartilhada com `tenant_id`
**Contexto:** `docs/DESIGN.md` e `docs/SECURITY.md` antecipam "schema por tenant". No entanto, pgvector com `<=>` exige tabela única para índice `ivfflat` eficiente. Schemas separados dificultam busca semântica cross-tenant e criam footgun de `search_path`.  
**Decisão:** Schema `public`, tabela `produtos` com coluna `tenant_id TEXT NOT NULL`. Toda query filtra por `tenant_id`. Schemas por tenant entram no Sprint 1 para outras entidades.  
**Status:** ok

### D018 — Trigger do crawler: on-demand via API, sem scheduler
**Contexto:** Scheduler (APScheduler, Celery beat) pertence ao Sprint 1 (infra de aplicação).  
**Decisão:** `POST /catalog/crawl` inicia crawl síncrono e retorna `CrawlStatus`. Agendamento automático fora do escopo deste sprint.  
**Status:** ok

---

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| catalog | Types, Config, Repo, Service, Runtime (Crawler + Enricher), UI |
| providers | db.py (async SQLAlchemy session factory) |

---

## Multi-tenant

- Todo método de `CatalogRepo` recebe `tenant_id: str` como parâmetro obrigatório.
- Todo SQL filtra por `WHERE tenant_id = :tenant_id`.
- A variável de tenant para o projeto piloto é `"jmb"`.
- O Evaluator validará isolamento com teste unitário de dois tenants distintos em chamadas consecutivas.
- Tabela `produtos`: `UNIQUE (tenant_id, codigo_externo)` — garante que mesmo SKU em tenants diferentes não colidem.

---

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| `ANTHROPIC_API_KEY` | dev + staging | já existe — Claude Haiku |
| `OPENAI_API_KEY` | dev + staging | **novo (D016)** — embeddings |
| `POSTGRES_URL` | dev + staging | já existe |
| `CRAWLER_USER_JMB` | dev + staging | usuário EFOS da JMB |
| `CRAWLER_PASS_JMB` | dev + staging | senha EFOS da JMB |
| `CRAWLER_BASE_URL_JMB` | dev + staging | `https://pedido.jmbdistribuidora.com.br` |

**Nota:** variáveis EFOS seguem padrão dinâmico `CRAWLER_USER_{TENANT_ID_UPPER}`. Para tenant `"jmb"` → `CRAWLER_USER_JMB`. Isso permite onboarding de novos tenants sem alterar código.

---

## Deliverables

### 1. Playwright Crawler EFOS
**Camadas:** Config, Runtime  
**Arquivos:**
- `output/src/catalog/config.py` — `CrawlerConfig.for_tenant(tenant_id)`
- `output/src/catalog/runtime/crawler/base.py` — ABC `CrawlerBase`
- `output/src/catalog/runtime/crawler/efos.py` — `EfosCrawler(CrawlerBase)`

**Critérios de aceite:**
- [ ] `EfosCrawler.login()` autentica no EFOS e retorna `True` — verificado por teste de integração (`@pytest.mark.integration`)
- [ ] `EfosCrawler.get_categorias()` retorna `list[Categoria]` não vazia — teste de integração
- [ ] `EfosCrawler.get_produtos(categoria_id)` retorna `list[ProdutoBruto]` com `codigo_externo` e `nome_bruto` preenchidos — teste de integração
- [ ] Credenciais lidas via `os.getenv()` — jamais hardcoded
- [ ] Rate limiting: `asyncio.sleep` entre páginas conforme `CrawlerConfig.delay_between_pages_ms`
- [ ] structlog em cada operação de página

### 2. Pipeline de Enriquecimento (Claude Haiku)
**Camadas:** Types (Protocol), Runtime  
**Arquivos:**
- `output/src/catalog/types.py` — `EnricherProtocol` (Protocol class)
- `output/src/catalog/runtime/enricher.py` — `EnricherAgent` implementa `EnricherProtocol`

**Critérios de aceite:**
- [ ] `EnricherAgent.enriquecer(produto_bruto)` retorna `ProdutoEnriquecido` com todos os campos preenchidos (`nome`, `marca`, `categoria`, `tags`, `texto_rag`, `meta_agente`)
- [ ] Prompt do Haiku retorna JSON puro (sem markdown) — `ProdutoEnriquecido` valida via Pydantic
- [ ] Falha na resposta do LLM gera log com structlog + raise, não `print()`
- [ ] Teste unitário com Anthropic SDK mockado (sem chamada real à API)

### 3. CatalogRepo com pgvector
**Camadas:** Types, Repo  
**Arquivos:**
- `output/src/catalog/types.py` — `Produto`, `ProdutoBruto`, `ProdutoEnriquecido`, `PrecoDiferenciado`, `ResultadoBusca`, `StatusEnriquecimento`
- `output/src/catalog/repo.py` — `CatalogRepo`
- `output/alembic/versions/0001_catalog_initial.py` — tabelas `produtos` + `precos_diferenciados`

**Critérios de aceite:**
- [ ] Migration cria tabelas com `CREATE EXTENSION IF NOT EXISTS vector`, índice `ivfflat`, constraint unique `(tenant_id, codigo_externo)`
- [ ] `upsert_produto_bruto()`: INSERT ... ON CONFLICT atualiza `nome_bruto`, `preco_padrao`, `atualizado_em`
- [ ] `buscar_por_embedding()`: SQL com `embedding <=> CAST(:embedding AS vector) AS distancia`, filtra `tenant_id` e `distancia_maxima`
- [ ] Teste unitário com mock da session SQLAlchemy — verificar que SQL da busca por embedding contém `tenant_id = :tenant_id`
- [ ] NENHUMA função pública de `CatalogRepo` sem parâmetro `tenant_id`

### 4. CatalogService
**Camadas:** Service  
**Arquivo:** `output/src/catalog/service.py`

**Critérios de aceite:**
- [ ] `enriquecer_produto()`: chama enricher, salva resultado e dispara `gerar_e_salvar_embedding()` em sequência
- [ ] `buscar_semantico()`: gera embedding via OpenAI, chama `repo.buscar_por_embedding()`, retorna `list[ResultadoBusca]`
- [ ] `processar_excel_precos()`: parseia Excel com pandas/openpyxl, valida com Pydantic, faz batch upsert
- [ ] Todo método de service tem `with tracer.start_as_current_span(...)` (OTel)
- [ ] Cobertura de testes unitários ≥ 80%
- [ ] `CatalogService` NÃO importa nada de `catalog.runtime` — injeta `EnricherProtocol` de `catalog.types`

### 5. FastAPI UI + Painel Jinja2
**Camadas:** UI  
**Arquivos:**
- `output/src/catalog/ui.py` — router FastAPI `/catalog`
- `output/src/catalog/templates/produtos.html` — tabela Jinja2 com Aprovar/Rejeitar

**Endpoints JSON:**
| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/catalog/crawl` | Dispara crawl, retorna `CrawlStatus` |
| GET | `/catalog/produtos` | Lista produtos com filtro por status, paginação |
| GET | `/catalog/produtos/{id}` | Detalhe do produto |
| POST | `/catalog/produtos/{id}/aprovar` | Status → ATIVO |
| POST | `/catalog/produtos/{id}/rejeitar` | Status → INATIVO |
| POST | `/catalog/busca` | Busca semântica, retorna `list[ResultadoBusca]` |
| POST | `/catalog/precos/upload` | Upload Excel, retorna `ExcelUploadResult` |

**Endpoint HTML:**
| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/catalog/painel` | Renderiza `produtos.html` — lista produtos ENRIQUECIDO com botões Aprovar/Rejeitar |

**Critérios de aceite:**
- [ ] `GET /catalog/produtos` retorna 200 com `X-Tenant-ID: jmb` e serviço mockado
- [ ] `POST /catalog/busca` retorna `list[ResultadoBusca]` com campos `produto` e `score`
- [ ] `POST /catalog/precos/upload` com fixture `precos_teste.xlsx` retorna `ExcelUploadResult`
- [ ] `GET /catalog/painel` retorna 200 com `text/html` content-type
- [ ] `POST /catalog/produtos/{id}/aprovar` via form (HTML submit) redireciona de volta para `/catalog/painel`

---

## Fora de escopo

- Scheduler de crawl recorrente (Sprint 1)
- Integração WhatsApp (Sprint 2)
- Onboarding de segundo tenant
- API Bling / ERP
- Autenticação/JWT nos endpoints (Sprint 1 — TenantProvider middleware)
- Schema PostgreSQL por tenant (Sprint 1)
- Frontend React/Vue (Sprint 4)

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Estrutura HTML do EFOS muda entre planejamento e implementação | Média | Alto | Generator inspeciona o site live antes de escrever headless Playwright; métodos separados (login, categorias, produtos) isolam falhas |
| pgvector `<=>` com SQLAlchemy text() não aceita bind params de lista | Baixa | Alto | Usar `CAST(:embedding AS vector)` no SQL raw; teste unitário verifica shape do SQL |
| mypy --strict falha em tipos do Playwright (sem stubs) | Média | Baixo | `# type: ignore[import-untyped]` em efos.py; registrar como tech debt M-nível |
| `CatalogService` importa `EnricherAgent` violando camadas | Certa (se descuidado) | Bloqueante | `EnricherProtocol` em `catalog/types.py`; import-linter detecta no A1 |
| Excel da JMB tem CNPJ com pontuação (`12.345.678/0001-90`) | Média | Média | `PrecoDiferenciado` normaliza CNPJ para dígitos antes do upsert; fixture de teste inclui ambos os formatos |

---

## Handoff para Sprint 1

Este sprint entrega:
- Domínio `catalog` completo com tipos, repo, service, runtime e UI
- Tabelas `produtos` e `precos_diferenciados` no PostgreSQL com pgvector
- Endpoints `/catalog/*` prontos para serem protegidos pelo `TenantProvider` middleware do Sprint 1
- `providers/db.py` com session factory que o Sprint 1 reusará para todos os domínios
- `output/src/main.py` com FastAPI app base para o Sprint 1 expandir

O Sprint 1 precisará:
- Adicionar middleware `TenantProvider` que extrai `tenant_id` do JWT (hoje vem de `X-Tenant-ID` header)
- Migrar para schemas por tenant (para entidades de Sprint 1 em diante; catálogo pode permanecer em `public` por enquanto)
- Conectar crawler ao scheduler (APScheduler)
