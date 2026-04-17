# Design — AI Sales Agent

## Stack

| Camada | Tecnologia | Versão mínima |
|--------|-----------|---------------|
| Linguagem | Python | 3.11+ |
| Framework agentes | Claude Agent SDK | latest |
| LLM principal | claude-sonnet-4-6 | — |
| LLM classificador / enriquecimento | claude-haiku-4-5-20251001 | — |
| API | FastAPI | 0.110+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Driver PostgreSQL | asyncpg | latest |
| Banco de dados | PostgreSQL + pgvector | 16+ |
| Cache / sessão | Redis | 7+ |
| WhatsApp | Evolution API (self-hosted) | latest |
| Crawler | Playwright (headless) | latest |
| Secrets | Infisical CLI | latest |
| Observabilidade | OpenTelemetry + VictoriaMetrics + VictoriaLogs | latest |
| Linting de arquitetura | import-linter | latest |
| Testes | pytest + pytest-asyncio | latest |
| HTTP client | httpx (async) | latest |
| Logging | structlog | latest |
| Validação | pydantic v2 | 2.0+ |

## Ambientes

| Ambiente | Máquina | Uso |
|----------|---------|-----|
| development | mac-lablz | desenvolvimento local |
| staging | macmini-lablz | validação antes de produção |
| production | macmini-lablz (futuro: VPS) | tenants reais |

## Gestão de secrets — Infisical

Todos os secrets gerenciados pelo Infisical. Nunca commitar valores reais.

```bash
# Setup
brew install infisical/get-cli/infisical
infisical login
infisical init   # dentro da pasta do projeto

# Uso
infisical run --env=dev -- uvicorn src.main:app --reload
infisical run --env=dev -- pytest -v
infisical run --env=staging -- python scripts/health_check.py
```

### Projeto Infisical: `ai-sales-agent`
```
ai-sales-agent
├── development    ← mac-lablz
├── staging        ← macmini-lablz
└── production     ← futuro VPS
```

### Variáveis por ambiente
Preenchidas após os Sprints de Infra.

```
# Anthropic
ANTHROPIC_API_KEY

# Evolution API (após Sprint Infra-Dev)
EVOLUTION_API_URL
EVOLUTION_API_KEY
EVOLUTION_INSTANCE_NAME

# PostgreSQL (após Sprint Infra-Dev)
POSTGRES_URL          # postgresql+asyncpg://user:pass@host:5432/db

# Redis (após Sprint Infra-Dev)
REDIS_URL             # redis://localhost:6379

# Observabilidade (após Sprint Infra-Dev)
VICTORIA_METRICS_URL
VICTORIA_LOGS_URL
OTEL_EXPORTER_OTLP_ENDPOINT

# Por tenant (prefixo com TENANT_ID)
LOJA_INTEGRADA_API_KEY_{TENANT_ID}
LOJA_INTEGRADA_STORE_ID_{TENANT_ID}
CRAWLER_USER_{TENANT_ID}
CRAWLER_PASS_{TENANT_ID}
CRAWLER_BASE_URL_{TENANT_ID}

# Runtime
ENVIRONMENT           # development | staging | production
LOG_LEVEL             # DEBUG | INFO | WARNING
```

## Crawler de catálogo

### Por que browser, não API

O site B2B do piloto JMB usa EFOS — ERP sem API pública. Autenticação
por sessão PHP, preços renderizados server-side por cliente logado.
Playwright é a única forma de capturar dados confiáveis.

### Playwright vs Chrome MCP
- **Playwright**: execução autônoma e agendada (headless) — produção
- **Chrome MCP**: desenvolvimento e debug interativo do crawler

### Interface abstrata
```python
class CrawlerBase(ABC):
    tenant_id: str

    async def login(self) -> bool: ...
    async def get_categorias(self) -> list[Categoria]: ...
    async def get_produtos(self, categoria_id: str) -> list[ProdutoBruto]: ...
    async def get_produto(self, produto_id: str) -> ProdutoBruto: ...
    async def logout(self) -> None: ...
```

Implementações:
- `catalog/runtime/crawler/efos.py` — EFOS (JMB piloto + futuros tenants EFOS)
- `catalog/runtime/crawler/bling.py` — stub, futura implementação via API Bling

### Pipeline de enriquecimento
```
Playwright crawler
    → ProdutoBruto (dados brutos)
    → EnricherAgent (Haiku): nome, marca, tags, texto_rag, meta_agente
    → pgvector: embeddings do texto_rag
    → Revisão gestor (painel web)
    → Catálogo ativo
```

## Multi-tenancy

PostgreSQL usa schema separado por tenant:
```sql
CREATE SCHEMA tenant_{id};
-- Todas as tabelas existem dentro do schema do tenant
```

Toda query é filtrada por tenant via `TenantProvider` (middleware FastAPI
que injeta `tenant_id` no contexto de cada request).

## Preços

1. **Preço padrão**: crawler com conta de referência do tenant
2. **Preços diferenciados**: upload Excel pelo gestor
3. **Futuro**: Bling API via webhook (substitui 1 e 2)

```python
# Tabela Excel de preços diferenciados
# | codigo_produto | ean | cliente_cnpj | preco_cliente |
```
