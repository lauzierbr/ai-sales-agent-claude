# Arquitetura — AI Sales Agent

## Domínios de negócio

O sistema é dividido em domínios independentes. Cada domínio segue a
mesma estrutura de camadas. Cross-cutting concerns entram via Providers.

```
┌─────────────────────────────────────────────────────────┐
│                    DOMÍNIOS                             │
├──────────────┬──────────────┬──────────────┬───────────┤
│   Catalog    │    Orders    │    Agents    │  Tenants  │
│  (catálogo   │  (pedidos,   │  (runtime    │  (gestão  │
│  produtos,   │  carrinho,   │   Claude,    │   multi-  │
│  crawler,    │  histórico)  │   personas,  │  tenant)  │
│  embeddings) │              │   evaluator) │           │
└──────────────┴──────────────┴──────────────┴───────────┘
                        │
              Cross-cutting Providers
         (auth, telemetria, feature flags,
          tenant context, Infisical)
```

## Camadas fixas por domínio

Cada domínio é dividido em camadas com direção de dependência estrita.
Dependências só fluem para frente: **Types → Config → Repo → Service → Runtime → UI**

```
┌─────────┐
│  Types  │  Pydantic models, schemas, enums, tipos de domínio
└────┬────┘  Não importa nada de dentro do projeto
     ↓
┌─────────┐
│ Config  │  Settings (pydantic-settings + Infisical)
└────┬────┘  Importa: Types
     ↓
┌─────────┐
│  Repo   │  Data Access Layer — queries PostgreSQL (SQLAlchemy async)
└────┬────┘  Importa: Types, Config
     ↓
┌─────────┐
│ Service │  Lógica de negócio pura
└────┬────┘  Importa: Types, Config, Repo
     ↓        Exemplos: resolve_preco(), enriquecer_produto(), crawl_catalog()
┌─────────┐
│ Runtime │  Agentes Claude (AgentRep, AgentCliente, Evaluator, Crawler)
└────┬────┘  Importa: Types, Config, Repo, Service
     ↓
┌─────────┐
│   UI    │  FastAPI endpoints, webhooks WhatsApp, painel gestor
└─────────┘  Importa: tudo
```

### Regra de ouro
> Nenhuma camada pode importar uma camada à sua direita.
> Repo nunca importa Service. Service nunca importa Runtime.
> Violações são bloqueadas por linter no CI.

### Providers (cross-cutting)
Entram por interface explícita, não por import direto:
- `TenantProvider` — injeta `tenant_id` no contexto de cada request
- `TelemetryProvider` — OpenTelemetry (traces, métricas, logs)
- `AuthProvider` — validação de JWT / sessão WhatsApp
- `FeatureFlagProvider` — flags por tenant (futuro)

## Estrutura de pacotes

```
output/src/
├── catalog/
│   ├── types.py          # ProdutoBruto, ProdutoEnriquecido, Categoria
│   ├── config.py         # CrawlerConfig, EnrichmentConfig
│   ├── repo.py           # CatalogRepo (PostgreSQL + pgvector)
│   ├── service.py        # enriquecer_produto(), buscar_semantico()
│   ├── runtime/
│   │   ├── crawler/
│   │   │   ├── base.py   # CrawlerBase (interface abstrata)
│   │   │   └── efos.py   # EFOSCrawler (Playwright)
│   │   └── enricher.py   # EnricherAgent (Haiku)
│   └── ui.py             # endpoints /catalog
│
├── orders/
│   ├── types.py          # Pedido, ItemPedido, StatusPedido
│   ├── config.py
│   ├── repo.py           # OrderRepo
│   ├── service.py        # criar_pedido(), resolve_preco()
│   ├── runtime/
│   │   └── order_agent.py
│   └── ui.py             # endpoints /orders, webhook confirmação
│
├── agents/
│   ├── types.py          # Mensagem, Conversa, Persona, Role
│   ├── config.py         # AgentConfig por persona
│   ├── repo.py           # ConversaRepo (histórico, memória)
│   ├── service.py        # identity_router(), resolve_persona()
│   ├── runtime/
│   │   ├── agent_rep.py
│   │   ├── agent_cliente.py
│   │   ├── agent_onboarding.py
│   │   └── evaluator.py
│   └── ui.py             # webhook WhatsApp (Evolution API)
│
├── tenants/
│   ├── types.py          # Tenant, Representante, ClienteB2B
│   ├── config.py
│   ├── repo.py           # TenantRepo, RepRepo, ClienteRepo
│   ├── service.py        # onboarding_tenant(), validar_cnpj()
│   ├── runtime/
│   │   └── onboarding_agent.py
│   └── ui.py             # endpoints /tenants, painel gestor
│
└── providers/
    ├── telemetry.py      # OpenTelemetry setup
    ├── tenant_context.py # TenantProvider (middleware FastAPI)
    ├── auth.py
    └── db.py             # connection pool PostgreSQL + Redis
```

## Enforcement mecânico

### import-linter (pyproject.toml)
```toml
[tool.importlinter]
root_packages = ["src"]

[[tool.importlinter.contracts]]
name = "Repo não importa Service ou Runtime"
type = "forbidden"
source_modules = ["src.*.repo"]
forbidden_modules = ["src.*.service", "src.*.runtime", "src.*.ui"]

[[tool.importlinter.contracts]]
name = "Service não importa Runtime ou UI"
type = "forbidden"
source_modules = ["src.*.service"]
forbidden_modules = ["src.*.runtime", "src.*.ui"]

[[tool.importlinter.contracts]]
name = "Runtime não importa UI"
type = "forbidden"
source_modules = ["src.*.runtime"]
forbidden_modules = ["src.*.ui"]
```

### Mensagens de erro (injetadas no contexto do agente)
Cada violação de lint inclui instrução de remediação:
```
ERRO: src/orders/repo.py importa src/orders/service.py
REGRA VIOLADA: Repo não pode importar Service
REMEDIAÇÃO: Mova a lógica de negócio para src/orders/service.py
            e injete-a no Repo via parâmetro de função, não por import.
```

## Decisões de arquitetura

Ver `docs/design-docs/index.md` para o log completo de decisões.
