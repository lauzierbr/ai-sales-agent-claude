# Plano de Execução — Sprint 0 — Catálogo

**Status:** ✅ Concluído  
**Data início:** 2026-04-13  
**Data conclusão:** 2026-04-13  
**Spec:** `artifacts/spec.md`  
**Contrato:** `artifacts/sprint_contract.md` (ACEITO pelo Evaluator)  
**QA:** `artifacts/qa_sprint_0.md` (APROVADO pelo Evaluator)

---

## Checklist de Deliverables

### Infraestrutura / Suporte
- [x] `output/alembic.ini` — configuração Alembic apontando para `POSTGRES_URL`
- [x] `output/alembic/env.py` — env async SQLAlchemy
- [x] `output/alembic/versions/0001_catalog_initial.py` — tabelas `produtos` + `precos_diferenciados`
- [x] `output/src/providers/db.py` — async engine + session factory
- [x] `output/src/providers/telemetry.py` — OTel setup
- [x] `output/src/main.py` — FastAPI app + router mounting

### Domínio Catalog — Camada Types
- [x] `output/src/catalog/types.py` — todos os modelos Pydantic + `EnricherProtocol`

### Domínio Catalog — Camada Config
- [x] `output/src/catalog/config.py` — `CrawlerConfig`, `EnrichmentConfig`, `CatalogConfig`

### Domínio Catalog — Camada Repo
- [x] `output/src/catalog/repo.py` — `CatalogRepo` com todos os métodos + SQL pgvector

### Domínio Catalog — Camada Service
- [x] `output/src/catalog/service.py` — `CatalogService` com OTel spans

### Domínio Catalog — Camada Runtime
- [x] `output/src/catalog/runtime/__init__.py`
- [x] `output/src/catalog/runtime/crawler/__init__.py`
- [x] `output/src/catalog/runtime/crawler/base.py` — `CrawlerBase` ABC
- [x] `output/src/catalog/runtime/crawler/efos.py` — `EfosCrawler`
- [x] `output/src/catalog/runtime/enricher.py` — `EnricherAgent`

### Domínio Catalog — Camada UI
- [x] `output/src/catalog/ui.py` — FastAPI router (JSON + HTML)
- [x] `output/src/catalog/templates/produtos.html` — painel Jinja2

### Testes
- [x] `output/src/tests/conftest.py` — fixtures globais
- [x] `output/src/tests/unit/catalog/test_types.py`
- [x] `output/src/tests/unit/catalog/test_service.py` (cobertura 86% ≥ 80%)
- [x] `output/src/tests/unit/catalog/test_repo.py` (cobertura 100% ≥ 60%)
- [x] `output/src/tests/unit/catalog/test_enricher.py`
- [x] `output/src/tests/unit/catalog/test_ui.py`
- [x] `output/src/tests/integration/catalog/test_crawler.py` (`@pytest.mark.integration @pytest.mark.slow`)
- [x] `output/src/tests/fixtures/precos_teste.xlsx` — 3 linhas válidas + 1 inválida

### Dependências (pyproject.toml)
- [x] `openai>=1.50.0`
- [x] `openpyxl>=3.1.0`
- [x] `pandas>=2.0.0`
- [x] `jinja2>=3.1.0`
- [x] `python-multipart>=0.0.9` (adicionado durante execução — necessário para UploadFile)

### Infisical (pendente — ação manual do usuário)
- [ ] `OPENAI_API_KEY` adicionado em `development` + `staging`
- [ ] `CRAWLER_USER_JMB` adicionado em `development` + `staging`
- [ ] `CRAWLER_PASS_JMB` adicionado em `development` + `staging`
- [ ] `CRAWLER_BASE_URL_JMB` adicionado em `development` + `staging`

---

## Checks de Qualidade — Resultados Finais

| Check | Comando | Resultado |
|-------|---------|-----------|
| A1 lint-imports | `lint-imports` | 5/5 KEPT |
| A2 secrets | grep padrão | (vazio) PASS |
| A3 tenant_id | test_todos_metodos_publicos_tem_tenant_id | PASS |
| A4 pytest unit | `pytest -m unit` | 53/53 PASS |
| A5 GET /catalog/produtos | test_listar_produtos_retorna_200 | PASS |
| A6 POST /catalog/busca | test_busca_semantica_retorna_resultado | PASS |
| A7 POST /catalog/precos/upload | test_upload_precos_excel_retorna_resultado | PASS |
| A8 print() grep | grep padrão | (vazio) PASS |
| A9 mypy --strict | `mypy --strict output/src/catalog/` | 0 erros PASS |
| M1 OTel spans | revisão manual | PASS |
| M2 Docstrings | revisão manual | PASS |
| M3 cobertura | service.py 86%, repo.py 100% | PASS |

---

## Decisões tomadas durante execução

| Data | Decisão | Motivo |
|------|---------|--------|
| 2026-04-13 | D016: OpenAI text-embedding-3-small | Aprovado pelo usuário na fase de planejamento |
| 2026-04-13 | D017: tabela compartilhada com tenant_id | Aprovado pelo usuário na fase de planejamento |
| 2026-04-13 | D018: crawler on-demand via POST | Aprovado pelo usuário na fase de planejamento |
| 2026-04-13 | UI inclui painel Jinja2 | Solicitado pelo usuário — FastAPI + Jinja2, sem JS framework |
| 2026-04-13 | EnricherProtocol em types.py | Evita violação Service→Runtime; injeção via duck typing |
| 2026-04-13 | create_catalog_service() em ui.py | Service não pode importar Runtime; UI é última camada |
| 2026-04-13 | TextBlock isinstance check em enricher | mypy --strict exige narrowing do union type do SDK |
| 2026-04-13 | TemplateResponse com keyword args | Starlette 2.x mudou assinatura — request primeiro |

---

## Log de Execução

### 2026-04-13 — Planner
- ✅ `artifacts/spec.md` gerado
- ✅ ADRs D016, D017, D018 registrados em `docs/design-docs/index.md`
- ✅ `docs/PLANS.md` atualizado → Sprint 0 🔄 Planning
- ✅ Este arquivo criado

### 2026-04-13 — Generator Fase 1
- ✅ `artifacts/sprint_contract.md` gerado com critérios A1–A9, M1–M3

### 2026-04-13 — Evaluator Fase 1
- ✅ Contrato ACEITO com ajuste A2 (excluir tests/ do grep)

### 2026-04-13 — Generator Fase 2
- ✅ Todos os arquivos de `output/src/catalog/` criados
- ✅ 5 bugs corrigidos durante implementação:
  1. Service→Runtime violation: `create_catalog_service` movida para ui.py
  2. httpx API change: ASGITransport syntax
  3. test_enricher reload bug: `enricher._client = mock_client` direto
  4. 422 tests com dependency resolution: override adicionado
  5. Jinja2/Python 3.14 bug: mock do objeto `templates`
- ✅ mypy --strict: 0 erros (51 erros corrigidos)

### 2026-04-13 — Evaluator Fase 2
- ✅ `artifacts/qa_sprint_0.md` gerado: APROVADO
- ✅ `docs/PLANS.md` atualizado → Sprint 0 ✅
- ✅ Este arquivo atualizado
