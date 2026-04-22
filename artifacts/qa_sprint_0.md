# QA Sprint 0 — Catálogo (Crawler + Enriquecimento + pgvector)

**Avaliador:** Evaluator  
**Data:** 2026-04-13  
**Resultado:** ✅ APROVADO

---

## Critérios de Alta (A1–A9) — todos PASS

### A1 — lint-imports: zero violações de arquitetura
```
Analyzed 60 files, 137 dependencies.
Types: não importa nenhuma camada interna       KEPT
Config: importa apenas Types                    KEPT
Repo: não importa Service, Runtime ou UI        KEPT
Service: não importa Runtime ou UI              KEPT
Runtime: não importa UI                         KEPT
Contracts: 5 kept, 0 broken.
```
**Status: PASS**

---

### A2 — Segurança: zero secrets hardcoded
```bash
grep -rn "sk-ant\|api_key\s*=\s*['\"][a-zA-Z0-9]\|CRAWLER_PASS\s*=\s*['\"\|password\s*=\s*['\"][a-zA-Z0-9]" output/src/ --exclude-dir=tests
```
**Output:** (vazio)  
**Status: PASS**

---

### A3 — Isolamento de tenant: toda função de CatalogRepo tem tenant_id
Verificações estruturais (test_repo.py):
- `test_todos_metodos_publicos_tem_tenant_id` — PASSED  
- SQL de `buscar_por_embedding` contém `tenant_id = :tenant_id` — PASSED  
- SQL de `listar_produtos` contém `tenant_id = :tenant_id` — PASSED  
- SQL de `get_produto` contém `tenant_id = :tenant_id` — PASSED  
- SQL de `update_status` contém `tenant_id = :tenant_id` — PASSED  

Verificação de isolamento em Service:
- `test_buscar_semantico_tenant_isolation` — verifica que chamadas para "jmb" e "outro_tenant" usam tenant_ids separados corretamente — PASSED  

**Status: PASS**

---

### A4 — pytest -m unit: 53/53 passaram, zero I/O externo
```
53 passed, 3 deselected in 1.08s
```
Nenhuma conexão real a PostgreSQL, Anthropic ou OpenAI.  
**Status: PASS**

---

### A5 — GET /catalog/produtos retorna 200 com serviço mockado
- `test_listar_produtos_retorna_200` — status_code=200, lista com 1 produto, `codigo_externo="SKU001"` — PASSED  
- `test_listar_produtos_sem_header_retorna_422` — status_code=422 sem X-Tenant-ID — PASSED  

**Status: PASS**

---

### A6 — POST /catalog/busca retorna list[ResultadoBusca] com campos produto e score
- `test_busca_semantica_retorna_resultado` — status_code=200, `"produto"` e `"score"` presentes, `0.0 ≤ score ≤ 1.0` — PASSED  
- `test_busca_semantica_query_vazia_retorna_422` — status_code=422 para query="" — PASSED  

**Status: PASS**

---

### A7 — POST /catalog/precos/upload retorna ExcelUploadResult
- `test_upload_precos_excel_retorna_resultado` — com fixture `precos_teste.xlsx` (3 válidas + 1 inválida), retorna `ExcelUploadResult` com `linhas_processadas`, `inseridos`, `erros` — PASSED  

**Status: PASS**

---

### A8 — Zero print() em output/src/
```bash
grep -rn "print(" output/src/ --include="*.py"
```
**Output:** (vazio)  
**Status: PASS**

---

### A9 — mypy --strict: zero erros
```bash
mypy --strict --ignore-missing-imports --python-version 3.11 output/src/catalog/
```
**Output:** `Success: no issues found in 11 source files`  
**Status: PASS**

---

## Critérios de Média (M1–M3) — 3/3

### M1 — OTel span em toda função de service.py
Verificação: todos os métodos públicos de `CatalogService` têm `with tracer.start_as_current_span(...)`:
- `salvar_produto_bruto`, `enriquecer_produto`, `gerar_e_salvar_embedding`, `buscar_semantico`, `processar_excel_precos`, `aprovar_produto`, `rejeitar_produto`, `listar_produtos`, `get_produto`  

**Status: PASS** ✅

---

### M2 — Docstrings em todos os métodos públicos de service.py e repo.py
Verificação por leitura direta dos arquivos: todos os métodos públicos têm docstrings com Args/Returns/Raises conforme pertinente.  

**Status: PASS** ✅

---

### M3 — Cobertura: service.py ≥ 80%, repo.py ≥ 60%
```
output/src/catalog/repo.py      103 stmts   0 miss   100%
output/src/catalog/service.py   151 stmts  21 miss    86%
TOTAL                           825 stmts 338 miss    59%  (fail_under=50 — PASS)
```
- service.py: **86%** ≥ 80% ✅  
- repo.py: **100%** ≥ 60% ✅  

**Status: PASS** ✅

---

## Observações de Tech Debt

1. **Jinja2 3.x + Starlette 2.x / Python 3.14**: `TemplateResponse` migrou para assinatura `(request, name, context)`. Corrigido neste sprint usando keyword args. O teste de painel ainda usa mock de `templates` para contornar incompatibilidade de cache de Jinja2 — registrar como tech debt para quando Jinja2 lançar fix.

2. **efos.py cobertura 15%**: Playwright crawler requer browser real — coberto por `@pytest.mark.integration @pytest.mark.slow`. Fora de escopo para critérios de alta.

3. **config.py cobertura 20%**: Métodos `CrawlerConfig.for_tenant()` não são testados em unit (requerem variáveis de ambiente de tenant). Integration tests cobrem este caminho.

4. **Anthropic SDK TextBlock**: A partir desta versão do SDK, `response.content[0]` é um `Union` de vários tipos de bloco. O `isinstance(block, TextBlock)` é a forma correta de narrowing — confirmado com mypy --strict passando.

---

## Arquivos produzidos neste sprint

| Arquivo | Status |
|---------|--------|
| `output/src/catalog/types.py` | ✅ criado |
| `output/src/catalog/config.py` | ✅ criado |
| `output/src/catalog/repo.py` | ✅ criado |
| `output/src/catalog/service.py` | ✅ criado |
| `output/src/catalog/ui.py` | ✅ criado |
| `output/src/catalog/templates/produtos.html` | ✅ criado |
| `output/src/catalog/runtime/enricher.py` | ✅ criado |
| `output/src/catalog/runtime/crawler/base.py` | ✅ criado |
| `output/src/catalog/runtime/crawler/efos.py` | ✅ criado |
| `output/src/providers/db.py` | ✅ criado |
| `output/src/providers/telemetry.py` | ✅ criado |
| `output/src/main.py` | ✅ criado |
| `output/alembic/versions/0001_catalog_initial.py` | ✅ criado |
| `output/src/tests/conftest.py` | ✅ criado |
| `output/src/tests/unit/catalog/test_types.py` | ✅ criado |
| `output/src/tests/unit/catalog/test_service.py` | ✅ criado |
| `output/src/tests/unit/catalog/test_repo.py` | ✅ criado |
| `output/src/tests/unit/catalog/test_enricher.py` | ✅ criado |
| `output/src/tests/unit/catalog/test_ui.py` | ✅ criado |
| `output/src/tests/fixtures/precos_teste.xlsx` | ✅ criado |
| `artifacts/spec.md` | ✅ criado |
| `artifacts/sprint_contract.md` | ✅ criado |
| `docs/exec-plans/active/sprint-0-catalogo.md` | ✅ criado |
| `docs/PLANS.md` | ✅ atualizado |
| `docs/design-docs/index.md` | ✅ ADRs D016/D017/D018 adicionados |
| `pyproject.toml` | ✅ dependências adicionadas (openai, openpyxl, pandas, python-multipart) |

---

## Veredicto

**APROVADO** — todos os 9 critérios de alta (A1–A9) passaram. Todos os 3 critérios de média (M1–M3) satisfeitos.

O Sprint 0 pode avançar para integração (pytest -m integration) no macmini-lablz com infra rodando.
