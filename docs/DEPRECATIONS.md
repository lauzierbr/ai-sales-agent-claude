# Deprecações planejadas

Componentes marcados para remoção, com justificativa e sprint alvo.
Cada item mantém badge ou aviso visual no produto até a remoção efetiva.

---

## Sprint 10 — Catalog legado (Sprint 0)

**Origem:** Sprint 0 (2026-04-13) — pipeline crawler Playwright + enricher
Haiku + painel de revisão. Substituído pelo pipeline EFOS via backup
(Sprint 8) + read model `commerce_*` (Sprint 9). Decisão registrada em
[D030](design-docs/D030-erp-adapter-and-contact-ownership.md).

### Componentes a remover

| Caminho | Tipo |
|---------|------|
| `output/src/catalog/runtime/crawler/efos.py` | Crawler Playwright |
| `output/src/catalog/runtime/crawler/efos_http.py` | Crawler HTTP alternativo |
| `output/src/catalog/runtime/crawler/base.py` | Interface CrawlerBase |
| `output/src/catalog/runtime/enricher.py` | EnricherAgent (Claude Haiku) |
| `output/src/catalog/runtime/scheduler_job.py` | Job de crawl periódico (APScheduler) |
| `output/src/catalog/templates/produtos.html` | Template do painel |
| `/catalog/painel` | Rota GET (visualização) |
| `/catalog/painel/{id}/aprovar` | Rota POST (aprovação) |
| `/catalog/painel/{id}/rejeitar` | Rota POST (rejeição) |
| `service.aprovar_produto` / `rejeitar_produto` / `listar_produtos` | Métodos do CatalogService |
| `StatusEnriquecimento` enum | Tipo |
| Tabela `produtos` (legado) | Schema (drop migration) |
| Tabela `crawl_runs` (se existir) | Schema |
| Categorias/subcategorias se forem só do crawler | Schema (verificar) |
| Dependência `playwright` em `pyproject.toml` | Dep |

### ADRs afetados

- **D018** (crawler trigger on-demand POST /catalog/crawl) → marcar obsoleto
- **D019** (APScheduler crawler job) → marcar obsoleto
- **D016** (text-embedding-3-small OpenAI) → manter — embeddings continuam
  úteis; vão migrar para `commerce_products`

### Bloqueante de pré-remoção

Antes de drop da tabela `produtos`, **migrar embeddings semânticos para
`commerce_products`**. Hoje a busca semântica do AgentCliente
(`_buscar_produtos`) usa `produtos.embedding` (vector pgvector). Se removermos
sem migrar, a busca semântica para de funcionar.

Sprint 10 deve incluir:
1. Migration nova: adicionar coluna `embedding vector(1536)` em
   `commerce_products`
2. Job batch que enriquece `commerce_products` com embedding
   (pode reaproveitar lógica do EnricherAgent ANTES de remover o enricher)
3. AgentCliente passa a buscar em `commerce_products` (atualizar
   `_buscar_produtos`)
4. Validar busca semântica em staging
5. Só então drop da tabela `produtos`

### Ordem segura de remoção

```
1. Adicionar embedding em commerce_products (migration + job)
2. Atualizar AgentCliente._buscar_produtos para usar commerce_products
3. Verificar: nenhum read em "FROM produtos" no código
4. Marcar template e rotas como [DEPRECATED] em produção (já feito 29/04)
5. Drop migration: tabelas produtos, crawl_runs, etc.
6. Remover código (crawler, enricher, scheduler_job, service methods, rotas, template)
7. Limpar pyproject (remover playwright)
8. Atualizar ARCHITECTURE.md (catalog domain reduzido a busca + service over commerce_*)
9. Marcar D018/D019 como obsoletos no design-docs/index.md
```

### Justificativa funcional

- 743 produtos em `commerce_products` (read model EFOS) já cobrem o catálogo
- Bot já lê de `commerce_products` (B-16 fix Sprint 9)
- 443 produtos legados em status `enriquecido` nunca aprovados — sinal claro
  de que o painel não estava em uso real
- D030 estabelece ERP como source of truth do catálogo
- Crawler Playwright tem custos de manutenção (Chrome, anti-bot, frágil) que
  não se justificam tendo o backup SSH

### Substituição funcional

A capacidade humana de "QA de catálogo" não se perde: vai para feature nova
[F-06 — Painel de Divergências do Catálogo ERP](BACKLOG.md), planejada para
pós-Bling. Foco diferente: em vez de aprovar produtos do crawler antes de
ativar, mostra produtos do ERP com dados suspeitos para o gestor corrigir
no ERP.

---

## Histórico

Quando uma deprecação for completada, mover para a seção abaixo com link
para o commit que removeu.

### Removidas

(vazio por enquanto)
