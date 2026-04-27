# Arquitetura — AI Sales Agent

## Domínios de negócio

O sistema é dividido em domínios independentes. Cada domínio segue a
mesma estrutura de camadas. Cross-cutting concerns entram via Providers.

```
┌──────────────┬──────────────┬──────────────┬───────────┐
│   Catalog    │    Orders    │    Agents    │  Tenants  │
│  (catálogo   │  (pedidos,   │  (runtime    │  (gestão  │
│  produtos,   │  carrinho,   │   Claude,    │   multi-  │
│  crawler,    │  histórico)  │   personas,  │  tenant)  │
│  embeddings) │              │   evaluator) │           │
├──────────────┴──────────────┴──────────────┴───────────┤
│              Domínio 5: integrations/                   │
│  (pipeline SSH/SFTP + pg_restore EFOS; sync_runs;       │
│   sync_artifacts; isolado de domínios de negócio)       │
├────────────────────────────────────────────────────────┤
│              Domínio 6: commerce/                       │
│  (tabelas commerce_*; dados EFOS normalizados;          │
│   CommerceRepo; relatórios para AgentGestor)            │
└────────────────────────────────────────────────────────┘
                        │
              Cross-cutting Providers
         (auth, telemetria, feature flags,
          tenant context, Infisical)
```

### Domínio 5 — integrations/

Pipeline de integração com sistemas externos (EFOS/Webrun via backup SSH).

- `types.py`: `SyncStatus`, `ConnectorCapability`, `SyncRun`, `SyncArtifact`
- `config.py`: `EFOSBackupConfig.for_tenant()` — lê secrets via `os.getenv()`
- `repo.py`: `SyncRunRepo`, `SyncArtifactRepo` — persiste metadados de sync
- `connectors/efos_backup/`: `acquire.py`, `stage.py`, `normalize.py`, `publish.py`
- `jobs/sync_efos.py`: CLI com `--tenant`, `--dry-run`, `--force`

**Regras de isolamento:**
- Não importa `agents/`, `catalog/`, `orders/`, `tenants/` ou `dashboard/`
- Normaliza dados para `commerce/types.py` como camada de saída
- Enforçado por import-linter (contrato D026)

### Domínio 6 — commerce/

Camada de dados normalizados do ERP EFOS, usada pelo AgentGestor para relatórios.

- `types.py`: 8 dataclasses — `CommerceProduct`, `CommerceAccountB2B`, `CommerceOrder`,
  `CommerceOrderItem`, `CommerceInventory`, `CommerceSalesHistory`, `CommerceVendedor`
- `repo.py`: `CommerceRepo` com 3 métodos: `relatorio_vendas_representante`,
  `relatorio_vendas_cidade`, `listar_clientes_inativos`

**Regras de isolamento:**
- Não importa nenhum outro domínio (agentes, catálogo, pedidos, tenants, integrations)
- Enforçado por import-linter (contrato D027)
- Alimentado exclusivamente pelo pipeline `integrations/` via tabelas `commerce_*`

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
├── integrations/         # Domínio 5: pipeline EFOS
│   ├── types.py          # SyncStatus, ConnectorCapability, SyncRun, SyncArtifact
│   ├── config.py         # EFOSBackupConfig.for_tenant()
│   ├── repo.py           # SyncRunRepo, SyncArtifactRepo
│   ├── connectors/
│   │   └── efos_backup/
│   │       ├── acquire.py   # SSH/SFTP + SHA-256
│   │       ├── stage.py     # pg_restore + validação
│   │       ├── normalize.py # EFOS → commerce types
│   │       └── publish.py   # DELETE+INSERT em commerce_*
│   └── jobs/
│       └── sync_efos.py  # CLI --tenant, --dry-run, --force
│
├── commerce/             # Domínio 6: dados EFOS normalizados
│   ├── types.py          # CommerceProduct, CommerceAccountB2B, etc.
│   └── repo.py           # CommerceRepo (3 métodos de relatório)
│
└── providers/
    ├── telemetry.py      # OpenTelemetry setup
    ├── tenant_context.py # TenantProvider (middleware FastAPI)
    ├── auth.py
    └── db.py             # connection pool PostgreSQL + Redis
```

## Enforcement mecânico

### import-linter (pyproject.toml)

7 contratos ativos — 0 violações:

```toml
# Contratos de camada (todos os domínios)
"Types: não importa nenhuma camada interna"
"Config: importa apenas Types"
"Repo: não importa Service, Runtime ou UI"
"Service: não importa Runtime ou UI"
"Runtime: não importa UI"

# Contratos de isolamento entre domínios (Sprint 8)
"integrations: não importa domínios de negócio"
"commerce: não importa outros domínios de negócio"
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
