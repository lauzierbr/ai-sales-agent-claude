# QA Report — Sprint 9 Hotfix v0.9.1 — APROVADO (condicional)

**Data:** 2026-04-27
**Avaliador:** Evaluator Agent
**Commit avaliado:** 35e0f8b
**Referência:** docs/PRE_HOMOLOGATION_REVIEW.md, docs/BUGS.md

## Veredicto

**APROVADO** — código correto, testes verdes, lint limpo, versão correta.

> Aprovação condicional ao PASS do protocolo PRE_HOMOLOGATION_REVIEW pós-deploy.
> O Evaluator não pode validar A_BEHAVIORAL nesta fase porque o app ainda não foi
> deployado para staging com este hotfix. Antes da homologação humana, o
> Generator DEVE executar `docs/PRE_HOMOLOGATION_REVIEW.md` e anexar
> `artifacts/pre_homolog_review_sprint_9_hotfix.md` com PASS em todos os itens.
> Se algum FAIL surgir, este APROVADO é revogado.

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded | `grep -rn "sk-ant\|api_key=..." output/src/` | PASS (apenas fixtures de teste) |
| import-linter | `lint-imports` | PASS — 7 kept, 0 broken |
| print() proibido | `grep -rn "print(" output/src/` (não-teste) | PASS — 0 ocorrências |
| pytest unit | `.venv/bin/python -m pytest output/src/tests/ -m unit -q` | PASS — 386 passed, 0 failed |
| Versão app | `grep "0\.9\." output/src/main.py` | PASS — 3 ocorrências (0.9.1) |

## Categorização do grep de tabelas legadas

`grep -rn "FROM clientes_b2b|FROM pedidos|FROM itens_pedido|JOIN clientes_b2b|JOIN pedidos" output/src/ --include="*.py"`

Cada hit cabe em uma das três categorias previstas no commit message:

| Arquivo:linha | Tabela | Categoria | Verificado |
|---------------|--------|-----------|-----------|
| agents/repo.py:110-370 | clientes_b2b | (a) write model bot — fallback já no buscar | OK |
| agents/repo.py:731-866 | pedidos / clientes_b2b | (a) write model bot — relatórios usam dados próprios | OK |
| agents/repo.py:918-919 | itens_pedido + pedidos | (b) FIXED — fallback `commerce_order_items` linhas 940-965 | OK |
| dashboard/ui.py:788 | pedidos | (b) FIXED — `_get_kpis` fallback `commerce_orders` linha 802+ | OK |
| dashboard/ui.py:865-866 | pedidos + clientes_b2b | (b) FIXED — `_get_pedidos_recentes` fallback linha 877+ | OK |
| dashboard/ui.py:943 | clientes_b2b | (b) FIXED — `_get_clientes` fallback `commerce_accounts_b2b` linha 967+ | OK |
| dashboard/ui.py:1026 | pedidos | (b) FIXED — `_get_representantes_com_gmv` fallback linha 1045+ | OK |
| dashboard/ui.py:1216, 1273 | clientes_b2b | (a) write model — edição de cadastro | OK |
| tenants/repo.py:227 | clientes_b2b | (c) verificação semântica — uniqueness CNPJ no onboarding | OK |
| orders/repo.py:160-560 | pedidos / itens_pedido / clientes_b2b | (a) write model exclusivo do bot | OK |

Nenhum hit órfão. Estratégia fallback (não substituição) corretamente implementada.

## Critérios bug a bug

### B-14 — AgentGestor `_listar_pedidos_por_status` fallback
**Status:** PASS
**Evidência:** `output/src/agents/runtime/agent_gestor.py:933-950` — quando `OrderRepo.listar_por_tenant_status` retorna lista vazia, chama `self._commerce_repo.listar_pedidos_efos(...)`. Teste: `test_listar_pedidos_usa_commerce_quando_vazio`.

### B-15 — Tool `listar_representantes` em AgentGestor
**Status:** PASS
**Evidência:**
- Tool em `_TOOLS`: `agent_gestor.py:333` ("listar_representantes").
- System prompt anuncia: `agents/config.py:235` ("- listar_representantes: lista todos os representantes cadastrados no EFOS...").
- Implementação: `agent_gestor.py:1021+` consulta `commerce_vendedores`.
- Testes: `test_listar_representantes_em_tools`, `test_listar_representantes_no_system_prompt`, `test_listar_representantes_retorna_dados`, `test_tool_coverage_listar_representantes_e_anunciada`.

### B-16 — Dashboard `/clientes` fallback `commerce_accounts_b2b`
**Status:** PASS (código)
**Evidência:** `dashboard/ui.py:927-1004` — `_get_clientes` faz query em `clientes_b2b` e, se vazia, consulta `commerce_accounts_b2b LEFT JOIN commerce_vendedores`.
**Débito Média:** ausência de teste unitário específico em `test_hotfixes_sprint9.py`.

### B-17 — Dashboard `/pedidos` fallback `commerce_orders`
**Status:** PASS (código)
**Evidência:** `dashboard/ui.py:849-925` — `_get_pedidos_recentes` faz query em `pedidos` e, se vazia, faz fallback `commerce_orders`.
**Débito Média:** ausência de teste unitário específico do fallback em `test_hotfixes_sprint9.py` (existe teste de JOIN não relacionado em `test_dashboard.py:464`).

### B-18 — `home()` carrega `sync_info` no contexto inicial
**Status:** PASS
**Evidência:** `dashboard/ui.py:194-215` — chamada `_get_last_sync_info(tenant_id)` antes do render, passada no template context. Teste: `test_get_last_sync_info_funcao_existe`, `test_home_passa_sync_info_no_contexto`.

### B-19 — KPIs `home` fallback `commerce_orders`
**Status:** PASS
**Evidência:** `dashboard/ui.py:767-848` — `_get_kpis` faz fallback `commerce_orders` para hoje (linha 807) e histórico (linha 826) com label "Histórico EFOS".

### B-20 — `top_produtos_por_periodo` fallback `commerce_order_items`
**Status:** PASS
**Evidência:** `agents/repo.py:940-965` — fallback `commerce_order_items JOIN commerce_orders` quando `itens_pedido` retorna vazio. Teste: `test_top_produtos_fallback_commerce`.

### B-21 — Link "Representantes" no menu de navegação
**Status:** PASS
**Evidência:** `output/src/dashboard/templates/base.html:68` — `<a href="/dashboard/representantes">Representantes</a>`. Teste: `test_base_html_contem_link_representantes`.
**Plus:** `_get_representantes_com_gmv` faz fallback `commerce_vendedores LEFT JOIN commerce_orders` quando `pedidos` vazio (linha 1045+).

### B-22 — System prompts proíbem emojis explicitamente
**Status:** PASS
**Evidência:** `output/src/agents/config.py` linhas 80-83 (cliente), 163-166 (rep), 220-223 (gestor). A regra é a PRIMEIRA do system prompt sob cabeçalho "## Regra de linguagem (prioridade maxima)" — explícita, prioritária, e enumera emojis específicos. Testes: `test_agentcliente_config_proibe_emojis`, `test_agentrep_config_proibe_emojis`, `test_agentgestor_config_proibe_emojis`.

## Cobertura de testes do hotfix

`output/src/tests/unit/agents/test_hotfixes_sprint9.py` (324 linhas, 11 testes) cobre:
- B-14 (1 teste), B-15 (4 testes), B-18 (2 testes), B-19 (implícito via _get_kpis indireto — não há teste direto), B-20 (1 teste), B-21 (1 teste), B-22 (3 testes).

**Lacunas (Débitos Média):**
- B-16: sem teste unitário do fallback `commerce_accounts_b2b` em `_get_clientes`.
- B-17: sem teste unitário do fallback `commerce_orders` em `_get_pedidos_recentes`.
- B-19: sem teste unitário do fallback de KPIs em `_get_kpis`.

Esses fallbacks SERÃO exercitados pelo protocolo PRE_HOMOLOGATION_REVIEW
(navegação real do dashboard com banco em estado fallback). Por isso o
Evaluator condiciona o APROVADO ao PASS desse protocolo.

## Critérios de Média

| ID | Critério | Status |
|----|----------|--------|
| M-COV-1 | Teste unitário para CADA bug B-14..B-22 | FAIL parcial — B-16, B-17, B-19 sem teste direto do fallback |
| M-LINT | lint-imports = 0 violações | PASS |
| M-PRINT | Zero print() em produção | PASS |

**Resumo Média:** 1 falha de 3 critérios. Threshold default ≤ 1 — DENTRO do threshold.

## Débitos registrados

- **M-COV-1**: adicionar testes de fallback explícitos em `test_hotfixes_sprint9.py` para `_get_clientes` (B-16), `_get_pedidos_recentes` (B-17) e `_get_kpis` (B-19). Mockar `session.execute` para retornar primeira query vazia e verificar que a segunda query (commerce_*) é executada.

## Como reproduzir

```bash
cd /Users/lauzier/MyRepos/ai-sales-agent-claude

# Unit tests
.venv/bin/python -m pytest output/src/tests/ -m unit --tb=short -q

# import-linter
PYTHONPATH=output .venv/bin/lint-imports

# Grep tabelas legadas
grep -rn "FROM clientes_b2b\|FROM pedidos\|FROM itens_pedido\|JOIN clientes_b2b\|JOIN pedidos" output/src/ --include="*.py"

# Versão
grep -n "0\.9\." output/src/main.py
```

## Próximos passos

1. **Generator deve executar** `docs/PRE_HOMOLOGATION_REVIEW.md`:
   - Deploy v0.9.1 em staging
   - Navegar TODAS as 10 rotas do dashboard com Chrome DevTools MCP
   - Disparar TODOS os cenários de bot por persona via webhook
   - Anexar `artifacts/pre_homolog_review_sprint_9_hotfix.md` com PASS por item
2. **Se PASS:** APROVADO definitivo, homologação humana pode iniciar.
3. **Se FAIL em qualquer item:** este APROVADO é revogado, vira REPROVADO rodada 1, Generator corrige.
4. **Após homologação humana APROVADA:** mover plano para completed e bumpar versão produção para 1.0.0 (ou conforme convenção).
