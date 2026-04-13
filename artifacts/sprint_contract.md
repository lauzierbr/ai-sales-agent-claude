# Sprint Contract — Sprint 0 — Catálogo

**Proposto por:** Generator  
**Data:** 2026-04-13  
**Referência:** `artifacts/spec.md`  
**Status:** Aguardando ACEITO do Evaluator

---

## Escopo acordado

Pipeline completo de catálogo: crawler Playwright (EFOS/JMB), enriquecimento Claude Haiku, pgvector embeddings, upload Excel preços diferenciados, FastAPI JSON API + painel Jinja2.

**Fora de escopo deste contrato:** autenticação JWT, scheduler de crawl, segundo tenant, API Bling.

---

## Critérios de Alta — Bloqueantes (todos devem PASS)

### A1 — Arquitetura: camadas sem violações
**Comando:**
```bash
cd /Users/lauzier/MyRepos/ai-sales-agent-claude
PYTHONPATH=output lint-imports
```
**PASS:** saída contém `"No contracts violated"` ou similar, exit code 0.  
**FAIL:** qualquer violação de contrato listada, exit code ≠ 0.  
**Nota:** `CatalogService` NÃO pode importar de `catalog.runtime.*`. Injeção via `EnricherProtocol` de `catalog.types`.

### A2 — Segurança: zero secrets hardcoded
**Comando:**
```bash
grep -rn "sk-ant\|api_key\s*=\s*['\"][a-zA-Z0-9]\|CRAWLER_PASS\s*=\s*['\"\|password\s*=\s*['\"][a-zA-Z0-9]" output/src/ --exclude-dir=tests
```
**PASS:** zero linhas de output.  
**FAIL:** qualquer match fora de `tests/` — bloqueante imediato, arquivo:linha reportado.  
**Nota (Evaluator):** diretório `tests/` excluído para evitar falso positivo em fixtures sintéticas. Se match em `tests/`, revisar manualmente se é dado real ou mock.

### A3 — Isolamento de tenant: todo método do Repo tem `tenant_id`
**Verificação dupla:**

_3a. grep estrutural:_
```bash
grep -n "async def " output/src/catalog/repo.py | grep -v "tenant_id"
```
**PASS:** zero linhas (todo método async tem `tenant_id` na assinatura).

_3b. teste unitário obrigatório:_
```bash
pytest -m unit -k "test_buscar_semantico_tenant_isolation or test_repo_tenant_isolation" -v
```
**PASS:** ambos os testes PASSED.  
**Nota:** `test_buscar_semantico_tenant_isolation` chama `service.buscar_semantico` com `"jmb"` e depois `"outro_tenant"`, verifica que `mock_repo.buscar_por_embedding.call_args_list[0].kwargs["tenant_id"] == "jmb"` e `[1]... == "outro_tenant"`.

### A4 — Testes unitários passam sem I/O real
**Comando:**
```bash
cd /Users/lauzier/MyRepos/ai-sales-agent-claude
infisical run --env=dev -- pytest -m unit -v --tb=short output/src/tests/unit/
```
**PASS:** `0 failed`, `0 error`. Ausência de `asyncpg.exceptions`, `ConnectionRefusedError`, `aiohttp.ClientError` no output (indicaria I/O acidental).  
**FAIL:** qualquer teste FAILED/ERROR, ou presença de erros de conexão.

### A5 — Endpoint GET /catalog/produtos responde 200
**Comando:**
```bash
pytest -m unit -k "test_listar_produtos_retorna_200" -v --tb=short
```
**PASS:** PASSED. O teste usa `httpx.AsyncClient` com `app.dependency_overrides[get_catalog_service]` injetando mock.  
**Cenário coberto:** header `X-Tenant-ID: jmb` presente → 200. Header ausente → 422 (validação FastAPI).

### A6 — Endpoint POST /catalog/busca retorna ResultadoBusca
**Comando:**
```bash
pytest -m unit -k "test_busca_semantica_retorna_resultado" -v --tb=short
```
**PASS:** PASSED. Resposta JSON tem lista com objetos contendo `produto` (objeto com `id`, `nome`) e `score` (float entre 0 e 1).

### A7 — Upload Excel retorna ExcelUploadResult
**Comando:**
```bash
pytest -m unit -k "test_upload_precos_excel" -v --tb=short
```
**PASS:** PASSED. Fixture `output/src/tests/fixtures/precos_teste.xlsx` com 3 linhas válidas (1 com CNPJ com pontuação, 1 sem) + 1 linha inválida (CNPJ ausente). Resultado: `linhas_processadas=4`, `inseridos+atualizados=3`, `len(erros)==1`.

### A8 — Zero print() no código fonte
**Comando:**
```bash
grep -rn "print(" output/src/
```
**PASS:** zero linhas de output.  
**FAIL:** qualquer match — arquivo:linha reportado, log deve usar `structlog.get_logger()`.

### A9 — mypy --strict sem erros
**Comando:**
```bash
mypy --strict output/src/catalog/ --exclude "output/src/catalog/runtime/crawler/efos.py"
```
**PASS:** `Success: no issues found`.  
**Nota:** `efos.py` excluído porque Playwright não tem stubs mypy. A exclusão deve ser registrada como tech debt em `docs/exec-plans/tech-debt.md`.  
**FAIL:** qualquer erro em arquivos não excluídos.

---

## Critérios de Média — Não bloqueantes individualmente (threshold: falha em ≤ 1)

### M1 — OTel spans em todo o Service
**Verificação:**
```bash
python3 -c "
import ast, sys
src = open('output/src/catalog/service.py').read()
tree = ast.parse(src)
funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and not n.name.startswith('_')]
# verificar que cada função tem 'tracer' no corpo
print('Funções públicas:', funcs)
"
```
**PASS:** todas as funções públicas têm `tracer.start_as_current_span` no corpo — verificado via grep complementar:
```bash
grep -c "start_as_current_span" output/src/catalog/service.py
```
Valor ≥ número de funções públicas (mínimo 6: `salvar_produto_bruto`, `enriquecer_produto`, `gerar_e_salvar_embedding`, `buscar_semantico`, `processar_excel_precos`, `aprovar_produto`, `rejeitar_produto`).

### M2 — Docstrings nos métodos públicos
**Verificação:**
```bash
python3 -m pydocstyle output/src/catalog/service.py output/src/catalog/repo.py --convention=google 2>&1 | head -20
```
**PASS:** zero erros de docstring ausente (D100, D101, D102, D103).

### M3 — Cobertura mínima
**Comando:**
```bash
infisical run --env=dev -- pytest -m unit --cov=output/src/catalog --cov-report=term-missing --cov-fail-under=70
```
**PASS:** cobertura geral ≥ 70%. Breakdowns esperados: `service.py` ≥ 80%, `repo.py` ≥ 60%.  
**Nota:** `runtime/crawler/efos.py` pode ter cobertura baixa — headless Playwright não roda em CI.

---

## Evidências obrigatórias para APROVADO

O Generator deve incluir no relatório de auto-avaliação:

1. Saída completa de `lint-imports` (A1)
2. Output (vazio) de grep de secrets (A2)
3. Output (vazio) de grep de `print(` (A8)
4. Saída de `pytest -m unit -v` (A4) — últimas 30 linhas
5. Saída de `mypy --strict` (A9)
6. Saída de coverage (M3)

---

## Protocolo de falha

- **REPROVADO 1ª vez:** Evaluator entrega `artifacts/qa_sprint_0_r1.md` com `REPROVADO`, arquivo:linha:causa de cada falha. Generator tem **1 rodada** de correção.
- **REPROVADO 2ª vez:** Evaluator entrega `artifacts/qa_sprint_0_r2.md`. **NÃO contatar Generator.** Escalar para o usuário com tabela comparativa r1 vs r2.

---

## Assinatura

| Parte | Status | Data |
|-------|--------|------|
| Generator | Proposto | 2026-04-13 |
| Evaluator | **ACEITO** | 2026-04-13 |
