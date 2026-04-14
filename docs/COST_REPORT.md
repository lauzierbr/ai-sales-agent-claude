# Relatório de Custos e Tamanho do Projeto

**Gerado em:** 2026-04-14  
**Período coberto:** 2026-04-13 a 2026-04-14  
**Sprints concluídos:** Infra-Dev, Infra-Staging, Sprint 0, Sprint 1

---

## Tamanho do Projeto

### Código

| Categoria | Arquivos | Linhas |
|-----------|----------|--------|
| Python — produção | 37 | 5.521 |
| Python — testes | 27 | 3.844 |
| Migrations Alembic | 7 | 547 |
| Templates HTML | 1 | 171 |
| **Total Python** | **72** | **10.083** |
| Docs / Prompts / Artifacts | 23 | 3.609 |
| Scripts shell | 4 | 243 |
| Infra YAML | 3 | — |

**Arquivos rastreados pelo git:** 123 (inclui 446 JPGs do catálogo JMB)

### Maiores arquivos de produção

| Arquivo | Linhas |
|---------|--------|
| `output/src/catalog/ui.py` | 601 |
| `output/src/catalog/repo.py` | 562 |
| `output/src/catalog/runtime/crawler/efos.py` | 540 |
| `output/src/catalog/service.py` | 493 |
| `output/src/catalog/runtime/crawler/efos_http.py` | 403 |
| `output/src/catalog/types.py` | 382 |

### Histórico Git

**9 commits** ao longo de 2 dias:

| Sprint | Commits | Entregou |
|--------|---------|----------|
| Infra-Dev + Infra-Staging | 3 | Docker, Postgres, Redis, pgvector, Grafana, Infisical |
| Sprint 0 | 1 | Crawler EFOS, enriquecimento Haiku, embeddings, painel |
| Sprint 1 | 1 | FastAPI, JWT, TenantProvider, scheduler, Evolution webhook |
| Homologação + pré-Sprint 2 | 4 | mypy zero, FK migration, deploy.sh, pipeline completo |

---

## Uso de Tokens

### Dados brutos (Anthropic Console)

| Data | Modelo | Chave | Input s/ cache | Cache write | Cache read | Output |
|------|--------|-------|---------------|-------------|------------|--------|
| 13/04 | Haiku 4.5 | ai-sales-agent | 318.315 | 0 | 0 | 326.647 |
| 13/04 | Haiku 4.5 | Claude Code | 5.489 | 49.457 | 247.516 | 8.745 |
| 13/04 | Sonnet 4.6 | Claude Code | 21.224 | 1.922.899 | 53.660.520 | 393.052 |
| 14/04 | Haiku 4.5 | ai-sales-agent | 158.271 | 0 | 0 | 161.352 |
| 14/04 | Sonnet 4.6 | Claude Code | 23.226 | 1.717.808 | 59.105.309 | 378.753 |

### Totais agregados

| Categoria | Tokens |
|-----------|--------|
| Input sem cache | 526.525 |
| Cache write | 3.690.164 |
| Cache read | 113.013.345 |
| Output | 1.268.549 |
| **Total bruto** | **118.498.583** |

---

## Custo em USD

### Tabela de preços aplicada

| Modelo | Input | Cache write | Cache read | Output |
|--------|-------|-------------|------------|--------|
| Claude Sonnet 4.6 | $3,00/MTok | $3,75/MTok | $0,30/MTok | $15,00/MTok |
| Claude Haiku 4.5 | $0,80/MTok | $1,00/MTok | $0,08/MTok | $4,00/MTok |

### Breakdown por linha de uso

| Data | Modelo | Uso | Custo |
|------|--------|-----|-------|
| 13/04 | Haiku 4.5 | App produção — enriquecimento Sprint 0 (446 produtos) | $1,56 |
| 13/04 | Haiku 4.5 | Claude Code (sessões de desenvolvimento) | $0,11 |
| 13/04 | Sonnet 4.6 | Claude Code — desenvolvimento Sprint 0 + Sprint 1 | $29,27 |
| 14/04 | Haiku 4.5 | App produção — enriquecimento Sprint 1 staging | $0,77 |
| 14/04 | Sonnet 4.6 | Claude Code — homologação Sprint 1 + pré-Sprint 2 | $29,93 |

### Resumo por categoria

| Categoria | Custo |
|-----------|-------|
| Claude Code — desenvolvimento (Sonnet 4.6 + Haiku) | $59,31 |
| App em produção — enricher (Haiku) | $2,33 |
| **Total 2 dias** | **$61,64** |

---

## Análise

### Cache economizou ~$303

113M tokens foram lidos do cache em vez de processados como input fresco.  
Custo real: `113M × $0,30 = $33,90`  
Custo sem cache: `113M × $3,00 = $339,00`  
**Economia: ~$303 (89% de desconto)**

O Claude Code mantém CLAUDE.md + arquivos do projeto em cache entre turns.
Quanto maior o contexto acumulado, maior o benefício do cache.

### Distribuição do custo

| Componente | Valor | % do total |
|------------|-------|-----------|
| Cache read (113M tokens) | $33,90 | 55% |
| Cache write (3,7M tokens) | $13,84 | 22% |
| Output (1,3M tokens) | $11,58 | 19% |
| Input fresco (527K tokens) | $1,38 | 2% |
| Haiku produção | $2,33 | 4% |

### Custo por produto enriquecido

892 enriquecimentos totais (446 Sprint 0 + 446 Sprint 1) via Haiku:  
`$2,33 ÷ 892 = ~$0,003 por produto`

---

## Projeção

| Período | Estimativa |
|---------|-----------|
| Por sprint de desenvolvimento (~2 dias) | ~$60 Claude Code + ~$3 produção |
| 4 sprints restantes até MVP | ~$250–280 |
| Custo por produto enriquecido (escala) | ~$0,003 |
| 10.000 produtos (catálogo completo) | ~$30 em enriquecimento |

---

*Dados de uso extraídos do Anthropic Console. Preços vigentes em abril de 2026.*
