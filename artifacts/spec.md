# Sprint 5 — Observabilidade LLM, Configurações e Relatórios

**Status:** Em planejamento
**Data:** 2026-04-20
**Pré-requisitos:** Sprint 4 APROVADO (v0.5.0), Sprint 5-teste APROVADO (v0.5.1-harness-v2), harness v2 validado

## Objetivo

Adicionar observabilidade LLM via Langfuse, permitir configuração de números de celular e cadastro de clientes fictícios pelo dashboard, e ampliar relatórios de performance de representantes.

## Contexto

Sprint 4 entregou o painel do gestor e AgentGestor WhatsApp. Sprint 5-teste validou os gates mecânicos do harness v2. Sprint 5 real resolve quatro lacunas operacionais identificadas no piloto JMB:

1. **Custo e qualidade LLM invisíveis** — sem traces por conversa não é possível auditar custos ou detectar respostas ruins do agente. Langfuse self-hosted resolve.
2. **Cadastro de clientes travado no ERP** — JMB usa EFOS sem API pública; clientes novos não aparecem no agente até o próximo crawl. Dashboard passa a criar clientes fictícios diretamente.
3. **Números de celular não configuráveis** — gestores e reps não têm campo `telefone` na tabela (só clientes_b2b). IdentityRouter não consegue reconhecer gestores/reps por número.
4. **Relatórios de reps incompletos** — `/dashboard/representantes` só mostra GMV do mês corrente. Gestor precisa de filtro por período, breakdown por cliente, e ferramenta no WhatsApp.

Doc-gardening agent excluído (backlog). OTEL spans completos excluídos (backlog — commit 60fab40).

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents | Config, Repo, Runtime (agent_cliente, agent_rep, agent_gestor) |
| tenants | Repo, Service |
| dashboard (agents/ui.py) | UI |
| infra | docker-compose.dev.yml, docker-compose.staging.yml |

## Considerações multi-tenant

- Langfuse: traces marcados com `tenant_id` em metadata e tags. Chaves Langfuse são por ambiente (não por tenant) — todos os tenants do ambiente compartilham a mesma instância Langfuse, isolados por tag.
- Cadastro de cliente: `ClienteB2BRepo.create()` recebe `tenant_id` explícito. Unique constraint em `(tenant_id, cnpj)`.
- Edição de telefone: dashboard resolve `tenant_id` via cookie JWT. Endpoints de edição filtram por `tenant_id` antes de UPDATE. Rep de tenant A não pode editar dados de tenant B.
- Relatórios de reps: `relatorio_performance_rep(tenant_id, dias)` sempre filtra por `tenant_id`.

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|---|---|---|
| LANGFUSE_HOST | development | http://localhost:3000 |
| LANGFUSE_PUBLIC_KEY | development | chave pública gerada no UI Langfuse após primeiro boot |
| LANGFUSE_SECRET_KEY | development | chave secreta gerada no UI Langfuse após primeiro boot |
| LANGFUSE_HOST | staging | http://100.113.28.85:3000 |
| LANGFUSE_PUBLIC_KEY | staging | idem para staging |
| LANGFUSE_SECRET_KEY | staging | idem para staging |
| LANGFUSE_NEXTAUTH_SECRET | development | string aleatória ≥ 32 chars (openssl rand -base64 32) |
| LANGFUSE_NEXTAUTH_SECRET | staging | idem para staging |
| LANGFUSE_SALT | development | string aleatória ≥ 32 chars |
| LANGFUSE_SALT | staging | idem para staging |

> Nota: `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` só existem após o primeiro boot
> do Langfuse e criação de projeto via UI. Generator deve documentar isso no handoff.

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|---|---|---|
| asyncpg + pgvector | `ORDER BY` com expressão vetorial retorna 0 rows silenciosamente | Fetch all sem ORDER BY, sort em Python |
| SQL período | `INTERVAL '30 days'` hardcoded | `timedelta(days=dias)` em Python, interpolar no SQL |
| Starlette 1.0 | `TemplateResponse("name", {ctx})` — API mudou | `TemplateResponse(request, "name", ctx)` |
| Jinja2 | Filter `\|enumerate` não existe | `loop.index` ou `loop.index0` |
| Langfuse SDK | `@observe()` decorator em coroutines async requer event loop ativo | Usar `langfuse.decorators.observe`; não chamar em contexto sync |
| Langfuse SDK | `langfuse.flush()` deve ser chamado antes de shutdown | Adicionar no lifespan FastAPI ou em finally do processar_mensagem |

## Entregas

### E1 — Langfuse self-hosted Docker + instrumentação dos 3 agentes

**Camadas:** Config, Runtime
**Arquivos:**
- `docker-compose.dev.yml`
- `docker-compose.staging.yml`
- `scripts/health_check.py`
- `output/src/agents/config.py`
- `output/src/agents/runtime/agent_cliente.py`
- `output/src/agents/runtime/agent_rep.py`
- `output/src/agents/runtime/agent_gestor.py`
- `output/src/tests/unit/agents/test_langfuse_instrumentation.py`

**Docker Langfuse v2 (adicionar a ambos os compose):**
```yaml
langfuse:
  image: langfuse/langfuse:2
  ports: ["3000:3000"]
  environment:
    DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
    NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET}
    NEXTAUTH_URL: http://localhost:3000        # dev; staging usa IP real
    SALT: ${LANGFUSE_SALT}
    TELEMETRY_ENABLED: "false"
  depends_on: [langfuse-db]
  restart: unless-stopped

langfuse-db:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: langfuse
    POSTGRES_USER: langfuse
    POSTGRES_PASSWORD: langfuse
  volumes: ["langfuse-db-data:/var/lib/postgresql/data"]
```

**LangfuseConfig (em agents/config.py):**
```python
class LangfuseConfig(BaseSettings):
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_enabled: bool = True  # False em unit tests via LANGFUSE_ENABLED=false
```

**Padrão de instrumentação por agente:**
```python
from langfuse.decorators import observe, langfuse_context

@observe(name="processar_mensagem_cliente")
async def processar_mensagem(self, mensagem: str, conversa_id: str, tenant_id: str):
    langfuse_context.update_current_trace(
        metadata={"tenant_id": tenant_id, "persona": "cliente"},
        tags=[tenant_id],
    )
    # ... lógica do agente ...
```

**Critérios de aceitação:**
- [ ] `docker-compose up langfuse langfuse-db` sobe sem erro; UI acessível em http://localhost:3000
- [ ] `scripts/health_check.py` verifica `GET http://localhost:3000/api/public/health` → 200 OK
- [ ] Cada chamada a `processar_mensagem` dos 3 agentes cria um trace no Langfuse com `tenant_id` em metadata e tags
- [ ] Cada tool call gera span filho com nome da ferramenta, input e output
- [ ] `usage.input_tokens` e `usage.output_tokens` capturados por trace
- [ ] `LANGFUSE_ENABLED=false` desabilita instrumentação sem erro (unit tests passam sem Langfuse real)
- [ ] `pytest -m unit` passa (mock Langfuse via env var, sem HTTP externo)
- [ ] import-linter passa: Langfuse importado apenas em Runtime, não em Repo/Service

---

### E2 — Configuração de números de celular via dashboard

**Camadas:** Repo, Service, UI (dashboard)
**Arquivos:**
- `output/alembic/versions/0016_representantes_telefone.py`
- `output/alembic/versions/0017_gestores_telefone.py`
- `output/src/tenants/repo.py`
- `output/src/tenants/service.py`
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/clientes_editar.html`
- `output/src/dashboard/templates/representantes_editar.html`
- `output/src/dashboard/templates/gestores_editar.html`

**Migrations:**
- `0016`: `ALTER TABLE representantes ADD COLUMN telefone VARCHAR(20) NULL`
- `0017`: `ALTER TABLE gestores ADD COLUMN telefone VARCHAR(20) NULL`

**Endpoints novos no dashboard:**
- `GET /dashboard/clientes/{id}/editar` → form de edição (inclui telefone)
- `POST /dashboard/clientes/{id}/editar` → salva
- `GET /dashboard/representantes/{id}/editar` → form de edição (inclui telefone)
- `POST /dashboard/representantes/{id}/editar` → salva
- `GET /dashboard/gestores/{id}/editar` → form de edição (inclui telefone)
- `POST /dashboard/gestores/{id}/editar` → salva

**Repo (update por entidade):**
```python
async def update_cliente_telefone(cliente_id: str, telefone: str, tenant_id: str, session) -> None
async def update_representante_telefone(rep_id: str, telefone: str, tenant_id: str, session) -> None
async def update_gestor_telefone(gestor_id: str, telefone: str, tenant_id: str, session) -> None
```

**Critérios de aceitação:**
- [ ] Migration `alembic upgrade head` adiciona `telefone` a `representantes` e `gestores` sem erro
- [ ] Gestor consegue editar `telefone` de qualquer cliente via `/dashboard/clientes/{id}/editar`
- [ ] Gestor consegue editar `telefone` de rep via `/dashboard/representantes/{id}/editar`
- [ ] Gestor consegue editar próprio `telefone` via `/dashboard/gestores/{id}/editar`
- [ ] UPDATE filtra por `tenant_id` (cross-tenant retorna 404)
- [ ] Após salvar telefone de rep, Identity Router reconhece mensagem desse número como rep
- [ ] Campo `telefone` aceita valor livre (sem regex obrigatório)

---

### E3 — Cadastro de clientes fictícios via dashboard

**Camadas:** Repo, Service, UI (dashboard)
**Arquivos:**
- `output/src/tenants/repo.py`
- `output/src/tenants/service.py`
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/clientes_novo.html`
- `output/src/tests/unit/tenants/test_criar_cliente.py`

**Endpoints:**
- `GET /dashboard/clientes/novo` — exibe form de criação
- `POST /dashboard/clientes/novo` — cria cliente, redirect para `/dashboard/clientes`

**Form (campos):**
- `nome` (obrigatório)
- `cnpj` (obrigatório) — 14 dígitos, validação de formato apenas
- `telefone` (obrigatório)
- `representante_id` (obrigatório) — select com reps ativos do tenant
- `email` (opcional)
- `endereco` (opcional)

**Backend:**
```python
# TenantService
async def criar_cliente_ficticio(tenant_id: str, dados: ClienteB2BCreate, session) -> ClienteB2B

# ClienteB2BRepo
async def create(cliente: ClienteB2B, session) -> ClienteB2B
async def exists_by_cnpj(cnpj: str, tenant_id: str, session) -> bool
```

**Critérios de aceitação:**
- [ ] `POST /dashboard/clientes/novo` com campos válidos cria registro com `tenant_id` correto
- [ ] Cliente criado aparece imediatamente em `/dashboard/clientes`
- [ ] CNPJ com menos de 14 dígitos retorna form com mensagem de erro
- [ ] CNPJ duplicado no mesmo tenant retorna "CNPJ já cadastrado"
- [ ] Select `representante_id` lista apenas reps do tenant logado
- [ ] Cliente criado é localizável pelo AgentCliente via busca por nome/CNPJ
- [ ] `pytest -m unit` cobre: criação válida, CNPJ duplicado, CNPJ formato inválido

---

### E4 — Relatórios de performance por representante (ampliados)

**Camadas:** Repo, Runtime (AgentGestor), UI (dashboard)
**Arquivos:**
- `output/src/agents/repo.py`
- `output/src/agents/config.py`
- `output/src/agents/runtime/agent_gestor.py`
- `output/src/dashboard/ui.py`
- `output/src/dashboard/templates/representantes.html`
- `output/src/dashboard/templates/_partials/representantes_lista.html`
- `output/src/dashboard/templates/representantes_detalhe.html`
- `output/src/tests/unit/agents/test_relatorio_rep.py`

**Ferramenta `relatorio_representantes` no AgentGestor:**
```python
{
    "name": "relatorio_representantes",
    "description": "Retorna ranking de representantes com GMV, pedidos e cliente topo no período",
    "input_schema": {
        "type": "object",
        "properties": {
            "dias": {"type": "integer", "default": 30},
            "representante_id": {"type": "string"}
        }
    }
}
```

**Repo (novo método):**
```python
async def relatorio_performance_rep(
    tenant_id: str,
    dias: int,
    session,
    representante_id: str | None = None,
) -> list[dict]:
    # retorna: [{"rep_nome", "rep_id", "gmv", "pedidos", "cliente_topo"}]
    # WHERE status = 'confirmado' AND criado_em >= NOW() - timedelta(days=dias)
    # NUNCA hardcode INTERVAL
```

**Critérios de aceitação:**
- [ ] `GET /dashboard/representantes?dias=7` retorna GMV dos últimos 7 dias
- [ ] Seletor de período (7/30/90 dias) atualiza via htmx sem reload completo
- [ ] `GET /dashboard/representantes/{id}` lista clientes com pedidos confirmados do rep, GMV desc
- [ ] AgentGestor responde a "qual rep vendeu mais nos últimos 7 dias?" com `relatorio_representantes`
- [ ] `check_tool_coverage.py` passa: ferramenta em `_TOOLS` E anunciada no system_prompt
- [ ] SQL usa `timedelta(days=dias)` em Python, nunca `INTERVAL` hardcoded
- [ ] `pytest -m unit` cobre: dias=7, dias=90, filtro por representante_id

---

## Critério de smoke staging (obrigatório)

Script: `scripts/smoke_sprint_5.py`

O script verifica automaticamente contra infra real (macmini-lablz):
- [ ] `GET http://100.113.28.85:3000/api/public/health` → HTTP 200 (Langfuse UP)
- [ ] Mensagem de teste via webhook → trace aparece na API Langfuse (`/api/public/traces`)
- [ ] `GET /dashboard/clientes/novo` → HTTP 200
- [ ] `POST /dashboard/clientes/novo` com dados válidos → HTTP 302
- [ ] `GET /dashboard/representantes?dias=7` → HTTP 200
- [ ] `GET /dashboard/representantes/{rep_id}` → HTTP 200

Execução esperada: `python scripts/smoke_sprint_5.py` → `ALL OK`

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | Trace AgentCliente no Langfuse | Msg WhatsApp como cliente → abrir http://localhost:3000 | Trace com spans de tool call visível |
| H2 | Tokens/custo por conversa | Abrir trace → aba Usage | input_tokens e output_tokens registrados |
| H3 | Criar cliente fictício | Dashboard → Clientes → Novo → preencher → salvar | Cliente na lista; localizável pelo agente |
| H4 | CNPJ duplicado | Mesmo CNPJ de cliente existente | Mensagem "CNPJ já cadastrado" |
| H5 | Editar telefone de rep | Dashboard → rep → Editar → novo número → salvar | IdentityRouter reconhece número como rep |
| H6 | Filtro período reps | Dashboard → Representantes → "7 dias" | GMV atualiza via htmx |
| H7 | Detalhe rep por cliente | Dashboard → Representantes → clicar rep | Tabela clientes GMV desc |
| H8 | AgentGestor relatório reps WhatsApp | Gestor: "quais reps venderam mais nos últimos 7 dias?" | Ranking em *bold* com GMV e cliente topo |

## Decisões pendentes

**ADR D024 — Langfuse v2 self-hosted Docker** (aprovado durante planejamento — ver `docs/design-docs/index.md`)

## Fora do escopo

- Doc-gardening agent (excluído → backlog)
- OTEL spans filhos completos em VictoriaMetrics (excluído → backlog — commit 60fab40)
- Exportação Excel de relatórios de reps (excluída → backlog)
- Validação CNPJ na Receita Federal
- Onboarding de segundo tenant
- Sugestão proativa por ciclo de compra / Push ativo WhatsApp
- Auth multi-usuário no dashboard (previsto em D023 — adiado)

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Langfuse Docker consome RAM excessiva no macmini | Média | Médio | Testar `docker stats`; se > 1.5GB usar Langfuse Cloud |
| langfuse-sdk incompatível com Anthropic SDK async | Baixa | Alto | Fixar `langfuse>=2.0,<3.0` no pyproject.toml |
| IdentityRouter não faz lookup por telefone em gestores/reps | Alta | Médio | Verificar `agents/service.py` identity_router() |
| CNPJ fictício duplicado cross-tenant | Baixa | Baixo | Unique constraint `(tenant_id, cnpj)` — verificar se existe |

## Handoff para Sprint 6

Sprint 5 deixará pronto:
- Observabilidade LLM operacional via Langfuse
- Cadastro de clientes sem dependência de ERP
- Números de celular configuráveis
- Relatórios de reps completos

Sprint 6 pode começar: onboarding de segundo tenant, sugestão proativa por ciclo de compra.
