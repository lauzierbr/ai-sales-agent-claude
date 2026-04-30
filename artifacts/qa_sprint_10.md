# QA Report — Sprint 10 — Hotfixes + D030 + F-07 + Deprecação Catalog — REPROVADO

**Data:** 2026-04-29
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md (Revisão-2)
**Versão alvo:** v0.10.0

---

## Veredicto

**REPROVADO — rodada 1 de 1.**

Motivo resumido: o critério bloqueante **A_W4_E18_NO_PRODUTOS_READ** falhou — `output/src/catalog/repo.py` ainda contém 5 ocorrências de `FROM produtos` em métodos de produção (`get_produto`, `get_produto_por_codigo`, `listar_produtos`, `listar_produtos_sem_embedding`) e `output/src/catalog/types.py:139` mantém `class Produto`. Esses métodos são chamados por `CatalogService.get_por_codigo` e em cascata por `AgentCliente._buscar_produtos` (caminho B-13 / busca por EAN). Após a migration `0028_drop_produtos_legacy`, a tabela `produtos` deixa de existir e o agente quebra ao buscar produto por código — exatamente o cenário coberto por A_BEHAVIORAL_AGENT (cliente: "shampoo" / EAN). Adicionalmente, A_SMOKE, A_BEHAVIORAL_AGENT/UI e A_PRE_HOMOLOG **não puderam ser avaliados** porque o código do Sprint 10 ainda não foi commitado nem deployado em staging (working tree todo modificado; remoto e staging continuam em v0.9.4).

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -rn "sk-ant\|api_key\s*=\s*['\"]" output/src/` | PASS — 0 hits |
| import-linter | `cd output && PYTHONPATH=. lint-imports` | PASS — 7 kept, 0 broken |
| print() proibido | `grep -rn "print(" output/src/` | PASS — 0 ocorrências em produção |
| pytest unit | `cd output && PYTHONPATH=. pytest -m unit src/tests/unit src/tests/regression` | PASS — 407 passed, 18 skipped |
| pytest unit (coleta global) | `cd output && PYTHONPATH=. pytest -m unit` | FAIL — `tests/integration/catalog/test_crawler.py` importa `src.catalog.runtime.crawler.efos` removido pelo E19. Workaround: skip/remove. |
| version=0.10.0 | `grep __version__ output/src/__init__.py` | PASS — `0.10.0`; `main.py` usa `from src import __version__ as APP_VERSION` |
| Deploy staging | `curl /health` | NÃO EXECUTADO — staging em v0.9.4; código não commitado |
| Smoke gate Sprint 10 | `python scripts/smoke_sprint_10.py` | NÃO EXECUTADO — depende de deploy |
| Pre-homolog review | navegação 10 rotas + 7 cenários bot | NÃO EXECUTADO — depende de deploy |
| migrate_embeddings.py | `python scripts/migrate_embeddings.py --tenant jmb` | NÃO EXECUTADO — depende de deploy |

---

## Critérios de Alta — Avaliação estática

### A_VERSION
**Status:** PASS (estático)
**Evidência:** `output/src/__init__.py:12 __version__ = "0.10.0"`; `main.py:19 from src import __version__ as APP_VERSION`. Falta confirmar via `GET /health` em staging (depende de deploy).

### A_W1_B26_TRUNCATION (E1)
**Status:** PASS
**Evidência:** `output/src/agents/runtime/_history.py` existe; os 3 agentes importam o helper; `test_b26_truncation_integrity.py` está na suite regression que passou (407 unit incluindo regression).

### A_W1_B23_AUDIO (E4)
**Status:** PASS
**Evidência:** `output/src/agents/ui.py:297` faz `POST {EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}`; fallback chama `send_whatsapp_message()` direto (linha 350). `test_audio_evolution.py` passa.

### A_W1_B30_LANGFUSE (E3)
**Status:** PASS (unit)
**Evidência:** `output/src/observability/langfuse_anthropic.py` implementa `call_anthropic_with_langfuse` com `lf.generation()` + `generation.update(usage={input,output})` + `generation.end()`. Os 3 agentes substituem chamadas diretas. `test_langfuse_anthropic.py` passa. **Sub-critério S9** (Langfuse trace real com `usage.input_tokens > 0` em staging) NÃO EXECUTADO — depende de deploy + smoke gate.

### A_W2_E7_MIGRATION
**Status:** NÃO VERIFICÁVEL EM STAGING
**Evidência:** Migration `0025_d030_contacts_and_account_extras.py` cria `contacts` (campos OK) e `pedidos.account_external_id`. Não foi aplicada — banco staging continua em revisão antiga.

### A_W2_E8_UPSERT_PRESERVES_EMBEDDING
**Status:** PASS estático / NÃO VERIFICADO em staging
**Evidência:** `output/src/integrations/connectors/efos_backup/publish.py:113` faz `ON CONFLICT (tenant_id, external_id) DO UPDATE SET ...` sem sobrescrever `embedding`. `normalize.py` mapeia os 6 campos (`cl_contato`, `cl_telefone`, `cl_telefonecelular`, `cl_email`, `cl_nomefantasia`, `cl_dataultimacompra`).

### A_W2_E9_SELF_REGISTERED
**Status:** PASS (unit)
**Evidência:** `ContactRepo` em `output/src/agents/repo.py:1008`; `create_self_registered` idempotente; testes `test_contact_repo.py` e `test_service.py::test_nao_roteia_unauthorized` passam.

### A_W2_E10_AUTORIZAR
**Status:** PASS (unit)
**Evidência:** `notify_gestor_pendente` em `agents/service.py:478` com throttle 6h via Redis (`throttle_ttl = 6 * 60 * 60`); template inclui "AUTORIZAR"; comando `AUTORIZAR ` interceptado em `agents/ui.py:431`. Testes throttle/template/comando passam. **Cenário B6/B7 em WhatsApp real** NÃO VERIFICADO — depende de deploy.

### A_W2_E11_DASHBOARD_CONTACTS
**Status:** PASS (unit) com **defeito menor**
**Evidência:** `output/src/dashboard/ui.py:519` faz `INSERT INTO contacts`; `result.rowcount` checado em UPDATEs (linha 881). `test_b27_contato_dashboard.py` passa. Defeito: `output/src/dashboard/templates/clientes.html` — grep não encontrou `Novo Cliente` (texto removido), mas o critério A_BEHAVIORAL_UI exige verificação visual real ainda pendente.

### A_W2_E12_PEDIDO_EFOS
**Status:** PASS (unit)
**Evidência:** `agents/repo.py:316` (fallback `commerce_accounts_b2b` em `get_by_id`); `agents/repo.py:391` fallback no `get_by_external_id`; `pedidos.account_external_id` populado. `test_b28_pedido_efos.py` passa.

### A_W3_E13_MIGRATION
**Status:** NÃO VERIFICÁVEL EM STAGING
**Evidência:** Migration `0026` cria `role_enum('admin','gestor')`, tabela `sync_schedule` e seed `(jmb, efos_backup, diario, '0 13 * * *', true)`. Não aplicada.

### A_W3_E14_SCHEDULER (E14)
**Status:** PASS (unit)
**Evidência:** `output/src/integrations/runtime/scheduler.py` cria `AsyncIOScheduler(timezone="America/Sao_Paulo")`; lock Redis `sync:efos:{tenant}:running` TTL 30min; `replace_existing=True`; try/except interno. `test_scheduler.py` passa. Verificação real com `scheduler.get_jobs()` em staging NÃO EXECUTADA.

### A_W3_E15_ADMIN_GATE (E15)
**Status:** PASS (unit)
**Evidência:** `dashboard/ui.py:782` `if role != "admin": 403`; rota `/dashboard/sync` definida; template `sync.html` existe; `test_sync_admin_gate.py` passa. Verificação real em staging NÃO EXECUTADA.

### A_W4_E17_EMBEDDINGS
**Status:** NÃO VERIFICÁVEL EM STAGING
**Evidência:** Migration `0027` cria `CREATE EXTENSION IF NOT EXISTS vector` + `ADD COLUMN embedding vector(1536)`. `scripts/migrate_embeddings.py` existe. Cobertura ≥ 95% (706/743) NÃO MEDIDA porque o batch não foi rodado.

### A_W4_E18_NO_PRODUTOS_READ — **FAIL (BLOQUEANTE)**
**Status:** **FAIL**
**Comando executado:**
```
grep -rn "FROM produtos\|JOIN produtos\|from .* import Produto\b\|class Produto\b\|select(Produto)\|query(Produto)" \
  output/src/ --include="*.py" | grep -v test | grep -v "commerce_products"
```
**Evidência observada (saída real, 6 hits — esperado: 0):**
```
output/src/catalog/types.py:139:class Produto:
output/src/catalog/repo.py:287:            FROM produtos
output/src/catalog/repo.py:318:            FROM produtos
output/src/catalog/repo.py:356:                FROM produtos
output/src/catalog/repo.py:374:                FROM produtos
output/src/catalog/repo.py:404:            FROM produtos
```
**Causa raiz:** apenas `CatalogRepo.buscar_por_embedding` (linha 421) foi migrada para `commerce_products`. Os métodos `get_produto`, `get_produto_por_codigo`, `listar_produtos`, `listar_produtos_sem_embedding`, `update_embedding`, `update_status`, `update_produto_enriquecido`, `upsert_produto_bruto` **continuam lendo/escrevendo na tabela `produtos`** legada. Eles são chamados por `output/src/catalog/service.py` (linhas 90, 128, 150, 182, 201, 226, 230, 510, 536, 568, 591), que por sua vez é injetado no `AgentCliente` (caminho `_buscar_produtos` — linha 638 chama `get_por_codigo` que cai em `get_produto_por_codigo` → `FROM produtos`).

**Impacto:** se a migration `0028_drop_produtos_legacy` rodar (como previsto pelo deploy), o caminho de busca por código (B-13 / EAN sufixo) do AgentCliente quebrará em runtime — `relation "produtos" does not exist`. O critério `A_BEHAVIORAL_AGENT` falhará no cenário "Cliente envia EAN/código".

**Pré-condição obrigatória do sequenciamento (sprint contract, secção "Sequenciamento obrigatório"):**
> "2. grep 'FROM produtos' = 0 hits em código produção" — antes de E20.

**Não foi cumprida.** E20 não pode ser executada com segurança.

**Correção necessária:** migrar os métodos restantes de `CatalogRepo` para `commerce_products` (ou removê-los e ajustar os 11 callers em `catalog/service.py`). Decidir destino do tipo `class Produto` — manter como DTO se ainda for usado, ou substituir por `CommerceProduct`. Reexecutar grep até 0 hits.

### A_W4_E19_REMOCAO
**Status:** PASS estático com **bug menor**
**Evidência:** os 5 arquivos previstos foram removidos (`crawler/efos.py`, `crawler/efos_http.py`, `crawler/base.py`, `enricher.py`, `templates/produtos.html`). `playwright` removido de `pyproject.toml`. Bug menor: `output/src/tests/integration/catalog/test_crawler.py` ainda importa `src.catalog.runtime.crawler.efos` — quebra a coleta global do pytest. Não é teste unit (marca `integration`), por isso 407 unit passam quando paths explicitos são usados, mas `pytest -m unit` sem path quebra na coleta. Adicionar skip ou remover o arquivo.

### A_W4_E20_DROP_CONFIRMADO
**Status:** **NÃO EXECUTÁVEL** — bloqueado por A_W4_E18.
**Evidência:** Migration `0028` existe (`op.execute("DROP TABLE IF EXISTS produtos CASCADE;")`), mas a pré-condição 2 do sequenciamento não foi atendida.

### A_BEHAVIORAL_AGENT — **NÃO EXECUTADO**
**Status:** NÃO VERIFICADO
**Motivo:** depende de deploy + execução real de cenários B1..B7 via WhatsApp/webhook em staging.

### A_BEHAVIORAL_UI — **NÃO EXECUTADO**
**Status:** NÃO VERIFICADO
**Motivo:** depende de deploy + navegação real de 10 rotas em staging.

### A_TOOL_COVERAGE
**Status:** NÃO EXECUTADO neste turno (script externo `scripts/check_tool_coverage.py` requer ambiente Python configurado). Tester independente reportou PASS em iteração anterior.

### A_MULTITURN
**Status:** PASS (unit) — `test_runtime.py::test_multiturn_truncation_valid` está na suite que passou (5 testes multi-turn verdes segundo handoff).

### A_SMOKE — **NÃO EXECUTADO**
**Status:** NÃO VERIFICADO
**Motivo:** `scripts/smoke_sprint_10.py` existe em `output/scripts/`, mas não foi rodado porque a infra-staging continua em v0.9.4. Deploy não foi feito (working tree não-commitado; `deploy.sh` é interativo e requer commit + push antes).

### A_PRE_HOMOLOG — **NÃO EXECUTADO**
**Status:** NÃO VERIFICADO
**Evidência:** `artifacts/pre_homolog_review_sprint_10.md` existe mas todos os 29 itens estão em **PENDENTE** (10 rotas + 7 cenários bot + 12 smoke checks).

---

## Critérios de Média

| Critério | Status | Observação |
|----------|--------|------------|
| M1 — Type hints novos arquivos | NÃO EXECUTADO | mypy não rodado neste turno; tester anterior não reportou |
| M2 — Docstrings em Service novos | PASS visual | `langfuse_anthropic.py`, `service.notify_gestor_pendente`, `scheduler.py` têm docstrings |
| M3 — Cobertura unit ≥ 80% | NÃO MEDIDO | coverage report não rodado |
| M_INJECT — Injeção sem None | NÃO EXECUTADO | `tests/staging/agents/test_ui_injection.py` requer infra staging |

**Resumo de Média:** 0 falhas confirmadas, 3 NÃO MEDIDOS por dependência de staging. Threshold (1 de 4) — não impacta o veredicto, que já é FAIL por A_W4_E18.

---

## Bugs encontrados

### B-33 (FAIL bloqueante) — `catalog/repo.py` lê de `produtos` em 5 métodos de produção
- **Arquivo:linha:** `output/src/catalog/repo.py:287, 318, 356, 374, 404`; `output/src/catalog/types.py:139`
- **Impacto:** após `0028_drop_produtos_legacy`, `AgentCliente._buscar_produtos` (caminho `get_por_codigo`) e `CatalogService` quebrarão em runtime.
- **Fix:** migrar `get_produto`, `get_produto_por_codigo`, `listar_produtos`, `listar_produtos_sem_embedding`, `update_embedding`, `update_status` para `commerce_products`, ajustando os 11 callers em `service.py`. Revisitar `class Produto` (manter como DTO ou substituir por `CommerceProduct`).

### B-34 (defeito menor) — coleta pytest global quebra após E19
- **Arquivo:** `output/src/tests/integration/catalog/test_crawler.py:20`
- **Sintoma:** `ModuleNotFoundError: No module named 'src.catalog.runtime.crawler.efos'`
- **Fix:** adicionar `pytestmark = pytest.mark.skip(reason="crawler removido em E19")` ou deletar o arquivo (já marcado `@integration`).

### B-35 (operacional) — Sprint 10 não commitado nem deployado
- **Estado:** working tree com 38 arquivos modificados/novos; remoto e staging em v0.9.4.
- **Impacto:** `deploy.sh` é interativo (`read -p`) e exige commit+push prévio. Evaluator não pode autonomamente commitar trabalho do Generator.
- **Fix:** Generator (ou usuário) precisa criar commit `feat(sprint-10): v0.10.0 — hotfixes + D030 + F-07 + catalog deprecado`, push, e rodar `./scripts/deploy.sh staging main`. Em seguida: `migrate_embeddings.py` (antes de 0028), validar cobertura ≥ 95%, e só então rodar `smoke_sprint_10.py` + pre-homolog review.

---

## Causa raiz do REPROVADO

A_W4_E18_NO_PRODUTOS_READ é Alta bloqueante e o grep de validação retorna 6 hits onde o contrato exige 0. Esse mesmo grep é a pré-condição 2 antes de E20 e não foi atendido. Os critérios dependentes de staging (A_SMOKE, A_BEHAVIORAL_*, A_PRE_HOMOLOG) ficaram em NÃO EXECUTADO por falta de deploy — mas são gating: sem essas evidências, mesmo sem o E18 a aprovação seria insuficiente.

---

## Como reproduzir

```bash
# 1. Reproduzir o FAIL de E18:
cd /Users/lauzier/MyRepos/ai-sales-agent-claude
grep -rn "FROM produtos\|JOIN produtos\|from .* import Produto\b\|class Produto\b\|select(Produto)\|query(Produto)" \
  output/src/ --include="*.py" | grep -v test | grep -v "commerce_products"
# Esperado: 0 hits. Atual: 6 hits.

# 2. Pytest unit (paths explícitos para evitar B-34):
cd output && PYTHONPATH=. ../.venv/bin/pytest -m unit src/tests/unit src/tests/regression -q
# 407 passed, 18 skipped.

# 3. lint-imports:
cd output && PYTHONPATH=. ../.venv/bin/lint-imports
# 7 kept, 0 broken.
```

---

## Próximos passos para o Generator (rodada 1 de 1)

Em ordem de prioridade:

1. **[BLOQUEANTE]** Migrar os 5 métodos restantes de `CatalogRepo` para `commerce_products`, ajustar os 11 callers em `catalog/service.py`. Decidir e documentar destino do tipo `class Produto`. Reexecutar grep até 0 hits. Adicionar teste unit que cubra `get_por_codigo` lendo de `commerce_products`.
2. **[Limpeza E19]** Skip ou remover `output/src/tests/integration/catalog/test_crawler.py` para destravar `pytest -m unit` global.
3. **[Operacional]** Commit + push do Sprint 10. Executar `./scripts/deploy.sh staging main`. Rodar `migrate_embeddings.py --tenant jmb` ANTES de aplicar 0028. Confirmar cobertura ≥ 95% (≥ 706/743) e SÓ ENTÃO permitir `alembic upgrade head` (que inclui 0028). Marcar Lauzier como `role='admin'`.
4. **[A_SMOKE]** Rodar `python scripts/smoke_sprint_10.py` no macmini-lablz e copiar saída para `artifacts/smoke_sprint_10.log`. Anexar ao próximo handoff.
5. **[A_BEHAVIORAL_*]** Executar protocolo `docs/PRE_HOMOLOGATION_REVIEW.md` (10 rotas dashboard + 7 cenários bot por persona). Atualizar `artifacts/pre_homolog_review_sprint_10.md` com PASS/FAIL real, screenshots e contagens de banco.
6. Reinvocar Evaluator para rodada de re-avaliação.

Se a rodada 2 falhar, o sprint escala para o usuário.
