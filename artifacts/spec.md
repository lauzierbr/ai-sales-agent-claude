# Sprint 5-teste — Top Produtos por Período

**Status:** Em planejamento
**Data:** 2026-04-20
**Pré-requisitos:** Sprint 4 APROVADO (v0.5.0) — dashboard web e AgentGestor funcionais

## Objetivo

Ao final deste sprint, o gestor consegue ver no dashboard e perguntar ao bot
quais produtos foram mais vendidos em um período, com drill-down por quantidade
e valor.

## Contexto

Sprint de validação do harness v2. Escolhido por incluir exatamente as três
classes de bug que escaparam no Sprint 4:
- SQL INTERVAL hardcoded (gotcha `sql_hardcoded_interval`)
- Filtro Jinja2 `|enumerate` inexistente (gotcha `jinja2_enumerate_filter`)
- Tool anunciada no system prompt sem estar em `_TOOLS` (D4)

Se o harness v2 estiver funcionando, os gates G3, G4 e G7 capturam esses bugs
antes da homologação humana.

## Domínios e camadas afetadas

| Domínio  | Camadas |
|----------|---------|
| agents   | Repo, Runtime (AgentGestor), Config |
| dashboard | UI (novo endpoint + template) |

## Considerações multi-tenant

- `top_produtos_por_periodo` filtra obrigatoriamente por `tenant_id`
- O endpoint `/dashboard/top-produtos` resolve tenant via cookie JWT (padrão
  dos outros endpoints — `_verify_session`)
- A tool do AgentGestor recebe `tenant_id` implicitamente do contexto do Gestor

## Secrets necessários (Infisical)

Nenhum novo. Reutiliza `POSTGRES_URL`, `DASHBOARD_SECRET`, `JWT_SECRET`
já presentes no ambiente `staging`.

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| SQL período | `INTERVAL '30 days'` hardcoded ignora o parâmetro `dias` passado | Receber `dias: int`, computar `data_inicio = datetime.now(timezone.utc) - timedelta(days=dias)` em Python, passar como bind param |
| Jinja2 | Filter `\|enumerate` não existe — levanta `UndefinedError` em runtime (500) | Usar `loop.index` dentro do `{% for %}` |
| Starlette 1.0 | `TemplateResponse("name", {ctx})` — 1º arg deve ser `request` | `templates.TemplateResponse(request, "top_produtos.html", ctx)` |
| check_gotchas.py | Detecta `INTERVAL '\d+ days'` e `\| enumerate` mecanicamente | Estes patterns bloqueiam em G7 — não depende de memória do Generator |

## Entregas

### E1 — Query top_produtos_por_periodo no RelatorioRepo

**Camadas:** Repo (`output/src/agents/repo.py`)
**Critérios de aceitação:**
- [ ] Método `top_produtos_por_periodo(tenant_id, dias, limite)` adicionado a `RelatorioRepo`
- [ ] Parâmetro `dias` computado via `timedelta` em Python — NUNCA `INTERVAL` SQL hardcoded
- [ ] Retorna `list[dict]` com campos `produto_nome`, `quantidade_total`, `valor_total`
- [ ] Filtra por `tenant_id` e `criado_em >= data_inicio`
- [ ] Apenas pedidos com `status = 'confirmado'` contam

### E2 — Endpoint GET /dashboard/top-produtos

**Camadas:** UI (`output/src/dashboard/ui.py`)
**Critérios de aceitação:**
- [ ] `GET /dashboard/top-produtos?dias=30&limite=10` retorna HTTP 200 autenticado
- [ ] Redireciona para `/dashboard/login` se sessão inválida
- [ ] `TemplateResponse` usa assinatura Starlette 1.0: `templates.TemplateResponse(request, "top_produtos.html", ctx)`
- [ ] `ctx` contém `produtos` (list), `dias` (int), `limite` (int)

### E3 — Template top_produtos.html

**Camadas:** UI (`output/src/dashboard/templates/top_produtos.html`)
**Critérios de aceitação:**
- [ ] Renderiza tabela com colunas: Posição, Produto, Qtd, Valor
- [ ] Posição via `loop.index` — NUNCA `|enumerate`
- [ ] Mensagem "Nenhum produto no período" quando lista vazia
- [ ] Link de volta para home

### E4 — Tool consultar_top_produtos no AgentGestor

**Camadas:** Runtime (`output/src/agents/runtime/agent_gestor.py`), Config (`output/src/agents/config.py`)
**Critérios de aceitação:**
- [ ] `consultar_top_produtos` adicionada à lista `_TOOLS` com params `dias: int`, `limite: int`
- [ ] `system_prompt_template` em `AgentGestorConfig` anuncia a capacidade
- [ ] `check_tool_coverage.py` retorna `capacidade_sem_tool=0 tool_sem_capacidade=0`

### E5 — Testes unitários

**Camadas:** Unit tests
**Arquivo(s):** `output/src/tests/unit/agents/test_top_produtos.py`
**Critérios de aceitação:**
- [ ] `test_relatorio_top_produtos_usa_timedelta` — verifica que SQL gerado NÃO contém `INTERVAL`
- [ ] `test_tool_consultar_top_produtos_existe` — verifica que `_TOOLS` contém `"consultar_top_produtos"`
- [ ] `test_template_nao_usa_enumerate` — grep no arquivo HTML confirma ausência de `|enumerate`
- [ ] Todos marcados `@pytest.mark.unit`, sem I/O externo

## Critério de smoke staging (obrigatório — toca Runtime e UI)

Script: `scripts/smoke_sprint_5_teste.sh`

O script verifica contra staging real:
- [ ] GET `/dashboard/top-produtos?dias=30` retorna HTTP 200
- [ ] Resposta HTML contém âncora "Top Produtos"
- [ ] Sem sessão → HTTP 302 redirect para login
- [ ] `check_gotchas.py` retorna 0 violações

Execução: `bash scripts/smoke_sprint_5_teste.sh` → saída `ALL OK`

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | Página top-produtos carrega | Abrir `/dashboard/top-produtos?dias=30` logado | Tabela renderizada, sem erro 500 |
| H2 | Período sem dados | `?dias=1` em banco sem pedidos confirmados | "Nenhum produto no período" |
| H3 | Bot responde sobre top produtos | WhatsApp: "quais produtos mais vendidos este mês?" | Lista dos top 5 sem erro 400 |
| H4 | Follow-up multi-turn | Após H3: "e nos últimos 7 dias?" | Resposta coerente, histórico preservado |

## Decisões pendentes

Nenhuma — reutiliza ADRs existentes (D021 JWT, D023 dashboard auth, DP-03).

## Fora do escopo

- Gráfico de barras — apenas tabela HTML simples
- Filtro por categoria ou representante — top global do tenant apenas
- Partial htmx para polling — página estática

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| JOIN pesado sem índice em itens_pedido | Média | Baixo | Sprint de teste — aceitar latência |
| itens_pedido pode não ter produto_nome denormalizado | Baixa | Médio | Verificar schema antes de E1 |

## Handoff para o próximo sprint

Sprint de validação do harness — não avança para Sprint 5 real.
