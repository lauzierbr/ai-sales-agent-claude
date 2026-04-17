# Sprint 4 — Gestor/Admin

**Status:** Em planejamento
**Data:** 2026-04-17
**Pré-requisitos:** Sprint 3 APROVADO (v0.4.0 + AgentRep funcional)

## Objetivo

Ao final deste sprint existe um terceiro perfil `GESTOR` que acessa o sistema
via WhatsApp com visão 360° (todos os clientes, pedidos, relatórios) e via
dashboard web com painel de pedidos em tempo real, gestão de clientes e
representantes, upload de preços e configuração por tenant.

## Contexto

Sprint 3 entregou AgentRep com acesso restrito à carteira do representante.
O gestor precisa de acesso irrestrito: fechar pedido por qualquer cliente,
ver relatórios por rep/período, identificar clientes inativos e monitorar
operações. O dashboard web é entregue no mesmo sprint (DP-01). Isso fecha
o ciclo dos três perfis WhatsApp antes do Sprint 5 (inteligência e escala).

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents | Types, Config, Repo, Service, Runtime, UI |
| dashboard (novo) | Config, Runtime, UI |

## Considerações multi-tenant

- Tabela `gestores` tem `tenant_id NOT NULL` — toda query filtra obrigatoriamente.
- `RelatorioRepo`: todas as queries recebem `tenant_id` como primeiro argumento.
- Dashboard: JWT no cookie contém `tenant_id` — todos os endpoints usam TenantProvider.
- `/dashboard` excluído do TenantProvider middleware (tenant resolvido via cookie, não X-Tenant-ID).
- Teste de isolamento obrigatório: gestor do tenant A não acessa dados do tenant B.

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| `JWT_SECRET` | dev + staging | Já existe (D021) — reutilizado para cookie dashboard |
| `DASHBOARD_SECRET` | dev + staging | Senha do gestor para o dashboard web |
| `DASHBOARD_TENANT_ID` | dev + staging | tenant_id resolvido no login do dashboard (ex: `"jmb"`) |

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| asyncpg + pgvector | ORDER BY com vetor → 0 rows silencioso | Fetch all, sort em Python |
| asyncpg + pgvector | CAST(:param AS vector) falha | Interpolar f-string diretamente no SQL |
| SQLAlchemy AsyncSession | auto-commit ausente | `await session.commit()` explícito após toda escrita |
| fpdf2 2.x | `pdf.output()` retorna bytearray | `bytes(pdf.output())` |
| Evolution API | Envia webhook fromMe=True | Ignorar fromMe=True em parse_mensagem |
| DATE_TRUNC PostgreSQL | 'week' usa domingo como início da semana | Usar `now - timedelta(days=7)` em Python; nunca DATE_TRUNC('week') |
| htmx + FastAPI | Partial precisa de Content-Type text/html | Usar `HTMLResponse` explicitamente em todos os endpoints de partial |
| DP-03 | Pedido do gestor precisa do rep do cliente | `ClienteB2BRepo.get_by_id` antes de criar pedido; usa `cliente.representante_id` |
| conversas CHECK CONSTRAINT | Migration 0009 tem `persona IN ('cliente_b2b', 'representante', 'desconhecido')` | Migration 0015 DEVE alterar o constraint para incluir `'gestor'`; sem isso, `ConversaRepo.get_or_create_conversa` falha no runtime |

## Entregas

### E1 — Migration 0015: tabela `gestores` + índice de pedidos + fix CHECK CONSTRAINT

**Camadas:** Types (DB schema)
**Arquivo:** `output/alembic/versions/0015_gestores_pedidos_index.py`
**Critérios de aceitação:**
- [ ] Tabela `gestores` criada: `id TEXT PK DEFAULT gen_random_uuid()`, `tenant_id TEXT NOT NULL`, `telefone TEXT NOT NULL`, `nome TEXT NOT NULL`, `ativo BOOLEAN NOT NULL DEFAULT true`, `criado_em TIMESTAMPTZ NOT NULL DEFAULT now()`
- [ ] `UNIQUE (tenant_id, telefone)` presente em `gestores`
- [ ] `CREATE INDEX ix_pedidos_tenant_criado_em ON pedidos(tenant_id, criado_em)` criado
- [ ] CHECK CONSTRAINT `ck_conversas_persona` alterado: DROP antigo + ADD novo com `persona IN ('cliente_b2b', 'representante', 'desconhecido', 'gestor')`
- [ ] `alembic upgrade head` executa sem erro
- [ ] `alembic downgrade -1` reverte tudo: drop index, drop table gestores, restaura constraint original

### E2 — Types: `Persona.GESTOR` + `Gestor` model

**Camadas:** Types
**Arquivo:** `output/src/agents/types.py`
**Critérios de aceitação:**
- [ ] `Persona.GESTOR = "gestor"` adicionado ao StrEnum `Persona`
- [ ] `class Gestor(BaseModel)` com campos: `id: str`, `tenant_id: str`, `telefone: str`, `nome: str`, `ativo: bool = True`, `criado_em: datetime`
- [ ] `model_config = ConfigDict(from_attributes=True)` presente
- [ ] `Persona("gestor") == Persona.GESTOR` sem exceção
- [ ] Nenhuma alteração nos valores existentes (`CLIENTE_B2B`, `REPRESENTANTE`, `DESCONHECIDO`)

### E3 — Repo: `GestorRepo` + `RelatorioRepo` + adições em `ClienteB2BRepo`

**Camadas:** Repo
**Arquivo:** `output/src/agents/repo.py`
**Critérios de aceitação:**
- [ ] `GestorRepo.get_by_telefone(tenant_id, telefone, session) -> Gestor | None` — filtra `ativo=true`
- [ ] `ClienteB2BRepo.buscar_todos_por_nome(tenant_id, query, session) -> list[ClienteB2B]` — sem filtro de `representante_id`; usa `unaccent + ILIKE`
- [ ] `ClienteB2BRepo.get_by_id(id, tenant_id, session) -> ClienteB2B | None` — lookup por PK com filtro tenant_id
- [ ] `RelatorioRepo.totais_periodo(tenant_id, data_inicio, data_fim, session) -> dict` retorna `{"total_gmv": Decimal, "n_pedidos": int, "ticket_medio": Decimal}`
- [ ] `RelatorioRepo.totais_por_rep(tenant_id, data_inicio, data_fim, session) -> list[dict]` — `[{"rep_id", "rep_nome", "n_pedidos", "total_gmv"}]` ordenado por `total_gmv` DESC em Python
- [ ] `RelatorioRepo.totais_por_cliente(tenant_id, data_inicio, data_fim, session) -> list[dict]` — `[{"cliente_id", "nome", "cnpj", "n_pedidos", "total_gmv"}]` ordenado por `total_gmv` DESC em Python
- [ ] `RelatorioRepo.clientes_inativos(tenant_id, dias, session) -> list[dict]` — clientes sem pedido ≥ `dias` dias; ordenado por `ultimo_pedido_em` ASC em Python (None primeiro)
- [ ] Todas as queries filtram por `tenant_id` (isolamento multi-tenant)
- [ ] Nenhum `ORDER BY` em SQL — sort sempre em Python (padrão do projeto)
- [ ] `pytest -m unit` passa para todos os métodos novos

**Query SQL orientativa para `RelatorioRepo.clientes_inativos`:**
```sql
SELECT c.id, c.nome, c.cnpj,
       MAX(p.criado_em) AS ultimo_pedido_em
FROM clientes_b2b c
LEFT JOIN pedidos p
    ON p.cliente_b2b_id = c.id
   AND p.tenant_id = :tenant_id
   AND p.status != 'cancelado'
WHERE c.tenant_id = :tenant_id AND c.ativo = true
GROUP BY c.id, c.nome, c.cnpj
HAVING MAX(p.criado_em) IS NULL
    OR MAX(p.criado_em) < NOW() - CAST(:dias || ' days' AS INTERVAL)
```

### E4 — Config: `AgentGestorConfig`

**Camadas:** Config
**Arquivo:** `output/src/agents/config.py`
**Critérios de aceitação:**
- [ ] `AgentGestorConfig` com campos: `model`, `max_tokens`, `redis_ttl`, `max_iterations=8`, `historico_max_msgs`, `system_prompt_template`
- [ ] Todos os valores lidos de `os.getenv()` com defaults (sem dependência de env na instanciação)
- [ ] System prompt define: papel gestor/dono, acesso irrestrito, ferramentas disponíveis, linguagem coloquial BR, regra DP-03 (preservar `representante_id` do cliente ao fechar pedido)
- [ ] `system_prompt_template` interpolável com `.format(tenant_nome=..., gestor_nome=...)`
- [ ] `max_iterations=8` (maior que AgentRep=5; relatórios podem exigir múltiplas ferramentas)

### E5 — Runtime: `AgentGestor` com 5 ferramentas

**Camadas:** Runtime
**Arquivo:** `output/src/agents/runtime/agent_gestor.py` (novo)

**Ferramentas (`_TOOLS` no módulo):**

1. `buscar_clientes(query: str)` → `ClienteB2BRepo.buscar_todos_por_nome` (sem filtro de rep)
2. `buscar_produtos(query: str)` → idêntico ao AgentRep (lookup exato + semântico)
3. `confirmar_pedido_em_nome_de(cliente_b2b_id: str, itens: list[{produto_id, nome_produto, quantidade, preco_unitario}])` → sem validação de carteira; `representante_id` herdado de `cliente.representante_id` (DP-03); requer `ClienteB2BRepo.get_by_id` antes de criar
4. `relatorio_vendas(periodo: str, tipo: str)` — `periodo` em `["hoje","semana","mes","30d"]`; `tipo` em `["totais","por_rep","por_cliente"]`; cálculo de datas em Python (nunca DATE_TRUNC); delega a `RelatorioRepo`
5. `clientes_inativos(dias: int = 30)` → `RelatorioRepo.clientes_inativos`

**Mapeamento período → datas (em Python, dentro de `_executar_ferramenta`):**
- `"hoje"` → `data_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)`, `data_fim = data_inicio + timedelta(days=1)`
- `"semana"` → `data_inicio = now - timedelta(days=7)`, `data_fim = now`
- `"mes"` → `data_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)`, `data_fim = now`
- `"30d"` → `data_inicio = now - timedelta(days=30)`, `data_fim = now`

**Critérios de aceitação:**
- [ ] Padrão idêntico ao `AgentRep`: injeção de dependências, Redis memory (TTL 24h), persistência PostgreSQL via `ConversaRepo`, `Persona.GESTOR` passado para `get_or_create_conversa`
- [ ] `confirmar_pedido_em_nome_de` NÃO verifica pertencimento à carteira
- [ ] DP-03: `representante_id` no pedido = `cliente.representante_id` (None se cliente não tiver rep)
- [ ] `relatorio_vendas(periodo="semana")` usa `now - timedelta(days=7)` — teste G06 cobre isso
- [ ] `session.commit()` chamado após criação de pedido (verificar se `OrderService.criar_pedido_from_intent` já faz commit; NÃO double-commit)
- [ ] `catalog_service=None` não levanta exceção em `buscar_produtos`
- [ ] `pytest -m unit` passa com todas as dependências mockadas

### E6 — Service: IdentityRouter atualizado

**Camadas:** Service
**Arquivo:** `output/src/agents/service.py`
**Nova prioridade de lookup:** `gestores → representantes → clientes_b2b → DESCONHECIDO`

**Critérios de aceitação:**
- [ ] `GestorRepo.get_by_telefone()` verificado **antes** de `representantes` e `clientes_b2b`
- [ ] Número em `gestores` E `representantes` → retorna `Persona.GESTOR` (DP-02); log INFO `identity_router_gestor_rep_cumulativo` (não WARNING — comportamento esperado)
- [ ] Número só em `representantes` → `Persona.REPRESENTANTE` (sem regressão)
- [ ] Número só em `clientes_b2b` → `Persona.CLIENTE_B2B` (sem regressão)
- [ ] Número desconhecido → `Persona.DESCONHECIDO` (sem regressão)
- [ ] `pytest -m unit` cobre os 4 cenários (IR-G1 a IR-G4)

### E7 — UI: wiring do `AgentGestor` no webhook handler

**Camadas:** UI
**Arquivo:** `output/src/agents/ui.py`

**Critérios de aceitação:**
- [ ] `_process_message()` instancia `AgentGestor` quando `persona == Persona.GESTOR`
- [ ] Branch inserido entre `REPRESENTANTE` e o `else` (DESCONHECIDO)
- [ ] Injeção de dependências: `GestorRepo`, `RelatorioRepo`, `ConversaRepo`, `OrderService`, `PDFGenerator`, `AgentGestorConfig`, `catalog_service`, `anthropic_client`, `redis_client`, `ClienteB2BRepo`
- [ ] Exceção em `AgentGestor.responder` capturada e logada — não crasha o background task
- [ ] `import-linter` passa sem violações de camada

### E8 — Dashboard web (MVP)

**Camadas:** Config, Runtime, UI (domínio novo `dashboard`)
**Arquivos:** `output/src/dashboard/` (novo módulo)
**Stack:** FastAPI + Jinja2 + htmx (`hx-trigger="every 30s"`) + CSS puro (paleta de `catalog/templates/`)
**ADR:** D023 — registrar antes de implementar

**Estrutura de arquivos:**
```
output/src/dashboard/
    __init__.py
    ui.py
    templates/
        base.html
        login.html
        home.html
        pedidos.html
        conversas.html
        clientes.html
        representantes.html
        precos.html
        configuracoes.html
        _partials/
            kpis.html
            pedidos_recentes.html
            conversas_ativas.html
```

**Endpoints:**
| Endpoint | Método | Auth | Comportamento |
|----------|--------|------|---------------|
| `/dashboard/login` | GET | Sem auth | Renderiza `login.html` |
| `/dashboard/login` | POST | Sem auth | Valida `DASHBOARD_SECRET` com `hmac.compare_digest`; sucesso → cookie `dashboard_session` (JWT HttpOnly SameSite=Lax 8h) + redirect `/dashboard/home`; falha → `login.html` com `error=True` |
| `/dashboard/logout` | GET | Cookie | Limpa cookie + redirect `/dashboard/login` |
| `/dashboard/home` | GET | Cookie | KPIs do dia via `RelatorioRepo.totais_periodo`; seção KPI com htmx auto-refresh |
| `/dashboard/home/partials/kpis` | GET | Cookie | `HTMLResponse` do fragmento `_partials/kpis.html` |
| `/dashboard/pedidos` | GET | Cookie | Lista pedidos; params `status`, `data_inicio`, `data_fim` |
| `/dashboard/conversas` | GET | Cookie | Conversas das últimas 24h via `ConversaRepo` |
| `/dashboard/clientes` | GET | Cookie | Todos os clientes; param `q` para busca por nome/CNPJ |
| `/dashboard/representantes` | GET | Cookie | Lista reps com GMV do mês via `RelatorioRepo.totais_por_rep` |
| `/dashboard/precos` | GET | Cookie | Form de upload |
| `/dashboard/precos/upload` | POST | Cookie | Delega a `CatalogService.upload_excel_precos`; retorna `HTMLResponse` inline (htmx) |
| `/dashboard/configuracoes` | GET | Cookie | Exibe configurações do tenant (read-only) |

**Alterações obrigatórias em outros arquivos:**
- `output/src/main.py`: `app.include_router(dashboard_router)`
- `output/src/providers/tenant_context.py`: adicionar `/dashboard` a `_EXCLUDED_PREFIXES`

**Critérios de aceitação:**
- [ ] `GET /dashboard/home` sem cookie → 302 para `/dashboard/login`
- [ ] `POST /dashboard/login` com senha errada → re-renderiza login com erro (não 302)
- [ ] `POST /dashboard/login` com senha correta → seta cookie + redirect home
- [ ] Todos os endpoints de partial retornam `HTMLResponse` (não JSONResponse)
- [ ] Upload de preço delega ao `CatalogService` existente (sem duplicar lógica)
- [ ] `/dashboard` excluído do TenantProvider middleware
- [ ] `pytest -m unit` cobre login, `require_dashboard_session`, upload

### E9 — ADR D023: Dashboard tech stack + auth

**Arquivo:** `docs/design-docs/index.md`
**Ação:** Adicionar linha `| D023 | Dashboard: Jinja2+htmx+CSS, auth DASHBOARD_SECRET cookie HttpOnly | Sprint 4 | ok |` + bloco D023 no estilo D022.

### E10 — Testes, smoke gate e seed

**Arquivos:**
- `output/src/tests/unit/agents/test_agent_gestor.py` (novo — 12+ testes `@pytest.mark.unit`)
- `output/src/tests/unit/agents/test_identity_router.py` (editar — IR-G1 a IR-G4)
- `output/src/tests/staging/agents/test_agent_gestor_staging.py` (novo — `@pytest.mark.staging`)
- `scripts/seed_homologacao_sprint4.py` (novo)
- `scripts/smoke_gate_sprint4.sh` (novo)

**Casos de teste unitário obrigatórios (AgentGestor):**

| ID | Cenário | O que verifica |
|----|---------|----------------|
| G01 | `buscar_clientes` | Chama `buscar_todos_por_nome` (sem `representante_id`) |
| G02 | `buscar_produtos` | Chama `CatalogService` |
| G03 | `confirmar_pedido_em_nome_de` | Cria pedido sem validar carteira |
| G04 | DP-03 — rep presente | `representante_id` do pedido = `cliente.representante_id` |
| G05 | DP-03 — sem rep | `representante_id` do pedido = None quando cliente não tem rep |
| G06 | `relatorio_vendas(periodo="semana")` | Usa `now - timedelta(days=7)` (não DATE_TRUNC) |
| G07 | `relatorio_vendas(tipo="por_rep")` | Chama `RelatorioRepo.totais_por_rep` |
| G08 | `clientes_inativos(dias=30)` | Chama `RelatorioRepo.clientes_inativos` |
| G09 | `catalog_service=None` | `buscar_produtos` retorna aviso sem levantar exceção |
| G10 | `ConversaRepo.get_or_create_conversa` | Chamado com `Persona.GESTOR` |
| G11 | `session.commit()` | Chamado após criação de pedido |
| G12 | Isolamento multi-tenant | `tenant_id` sempre passado para `RelatorioRepo` |

**Casos de teste IdentityRouter (adições):**

| ID | Cenário |
|----|---------|
| IR-G1 | Telefone em `gestores` → `Persona.GESTOR` |
| IR-G2 | Telefone em `gestores` E `representantes` → `Persona.GESTOR` (DP-02) |
| IR-G3 | Telefone só em `representantes` → `Persona.REPRESENTANTE` (sem regressão) |
| IR-G4 | Telefone só em `clientes_b2b` → `Persona.CLIENTE_B2B` (sem regressão) |

**Seed script (`seed_homologacao_sprint4.py`):**
1. Upsert gestor de teste (`tenant_id="jmb"`, `nome="Lauzier Gestor Teste"`, `telefone` = número real do gestor)
2. Garantir 2 pedidos antigos (≥31 dias) para um cliente existente → `clientes_inativos` retorna ≥1 resultado
3. Print summary com contagens

**Smoke gate (`smoke_gate_sprint4.sh`):**

| ID | Verificação |
|----|-------------|
| S1 | Health check → `{"status":"ok"}` |
| S2 | Unit tests IR-G1 (IdentityRouter GESTOR) passam |
| S3 | `GET /dashboard/home` sem cookie → 302 |
| S4 | `POST /dashboard/login` com senha errada → NÃO 302 |
| S5 | `POST /dashboard/login` com senha correta → seta cookie |
| S6 | `GET /dashboard/home` com cookie → 200 |
| S7 | `GET /dashboard/home/partials/kpis` → HTML contém "GMV" ou "R$" |
| S8 | `pytest -m unit output/src/tests/unit/agents/test_agent_gestor.py` passa |
| S9 | `lint-imports` sem violações |

Execução: `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh` → `=== SMOKE GATE: PASSED ===`

## Critério de smoke staging (obrigatório)

Script: `scripts/smoke_gate_sprint4.sh`
Verifica S1–S9 listados em E10.
Execução: `infisical run --env=staging -- bash scripts/smoke_gate_sprint4.sh` → saída `PASSED`

## Checklist de homologação humana

| ID | Canal | Ação | Resultado esperado |
|----|-------|------|--------------------|
| H1 | WhatsApp (gestor) | "busca cliente Muzel" | Lista clientes com "muzel" de qualquer rep; mostra CNPJ |
| H2 | WhatsApp (gestor) | "quanto vendeu essa semana?" | Total R$, número de pedidos, ticket médio dos últimos 7 dias |
| H3 | WhatsApp (gestor) | "ranking dos reps esse mês" | Lista ordenada por GMV DESC com nomes dos reps |
| H4 | WhatsApp (gestor) | "clientes inativos" | Lista com ≥1 cliente sem pedido há 30+ dias |
| H5 | WhatsApp (gestor) | "fecha 2 shampoo anticaspa pro Muzel" + confirmação | Pedido criado; PDF enviado ao gestor; `representante_id` no pedido = rep do cliente (verificar no banco) |
| H6 | WhatsApp (rep `5519000000001`) | Qualquer mensagem | Resposta de AgentRep, não de AgentGestor |
| H7 | WhatsApp (cliente `5519992066177`) | "oi" | Resposta de AgentCliente, não de AgentGestor |
| H8 | Browser | GET `/dashboard/home` sem login | Redireciona para `/dashboard/login` |
| H9 | Browser | Login com senha correta | Redireciona para home; mostra KPIs do dia |
| H10 | Browser | Aguardar 30s na home | Seção KPI atualiza via htmx sem reload da página inteira |
| H11 | Browser | Upload Excel em `/dashboard/precos` com arquivo válido | Mensagem de sucesso inline; sem reload de página |
| H12 | Browser | `/dashboard/representantes` | Tabela com nomes dos reps e GMV do mês |

## Decisões pendentes

Nenhuma — D023 incluída neste spec como decisão aprovada.
Generator deve registrar o ADR (E9) antes de implementar E8.

## Fora do escopo

- `cancelar_pedido` via WhatsApp — "a definir" no product spec → Sprint 5
- Criação/edição de clientes via WhatsApp
- Autenticação multi-usuário no dashboard (senha única por tenant em Sprint 4)
- 2FA ou autenticação por senha para WhatsApp
- Edição de configurações do tenant via dashboard (só leitura em Sprint 4)
- Página de catálogo no dashboard (já existe em `/catalog/painel`)
- Regras de comissão por rep (DP-03 é placeholder até Sprint 5)
- SSE/WebSockets (polling htmx suficiente para MVP)
- Onboarding de segundo tenant

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| CHECK CONSTRAINT `ck_conversas_persona` não atualizado | Alta | Bloqueante | Migration 0015 DEVE dropar e recriar o constraint com `'gestor'` incluído |
| Double-commit após criar pedido via OrderService | Média | Médio | Verificar se `OrderService.criar_pedido_from_intent` já chama `session.commit()`; não duplicar |
| TenantProvider bloqueia `/dashboard` | Alta | Médio | E8 critério: adicionar `/dashboard` a `_EXCLUDED_PREFIXES` em `tenant_context.py` |
| Queries de relatório lentas sem índice | Média | Médio | Migration 0015 adiciona `ix_pedidos_tenant_criado_em` |
| Dashboard scope expansion | Alta | Médio | Cada página tem funcionalidade mínima; sem charts em Sprint 4 |

## Handoff para o próximo sprint

- Sprint 5 recebe: três perfis WhatsApp funcionais + dashboard operacional como base
- `cancelar_pedido` backlog aberto para Sprint 5
- DP-03 pode evoluir quando Sprint 5 adicionar regras de comissão por rep
- SSE/real-time avançado avaliável em Sprint 5 se UX exigir
- Auth multi-usuário para dashboard → Sprint 5
