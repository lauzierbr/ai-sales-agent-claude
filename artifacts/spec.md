# Sprint 10 — Hotfixes críticos + foundations D030 + F-07 + deprecação catalog

**Status:** Em planejamento
**Data:** 2026-04-29
**Pré-requisitos:** Sprint 9 fechado em v0.9.4; ADR D030 aprovado; banco em migration 0024.

## Objetivo

Ao final do Sprint 10, o piloto JMB tem um WhatsApp estável (histórico que não
se autodestrói, áudio funcional, ranking de vendedores eficiente), o dashboard
opera sob a nova modelagem `contacts` (D030 foundations), o sync EFOS é
controlado por UI admin (F-07) e o catalog legado (crawler/enricher/painel/
tabela `produtos`) é removido após migrar embeddings para `commerce_products`.

## Contexto

Sprint 9 foi homologado em 29/04/2026 com 11 bugs abertos (3 críticos, 5 altos,
2 médios/baixos) e duas decisões arquiteturais aprovadas (D030, D031). Sprint
10 reúne quatro frentes pelas quais o piloto não pode avançar:

1. **Showstoppers do gestor via WhatsApp** — B-26 (truncação cega do histórico
   destrói contexto a cada 5 tool calls) e B-27/B-28 (cadastro contato e
   pedido em nome de cliente EFOS quebrados — só resolúveis estruturalmente).
2. **Áudio funcional** — B-23 (Whisper recebe payload criptografado E2E) e
   B-24 (bot nega capacidade no system prompt).
3. **Operação básica** — B-25 (24 chamadas seriais para um ranking, ano
   default arbitrário), B-30 (Langfuse sem custo/tokens — bloqueia
   AnalystAgent), B-29 (logs poluídos).
4. **Foundations D030** — tabela `contacts` (write model do app) + dashboard
   contatos refeito + auto-criação `self_registered` + notificação dual ao
   gestor. Habilita resolução estrutural de B-27/B-28 e o adapter pattern
   para Bling no Sprint 11+.

Adicionalmente: F-07 (UI admin para frequência do sync EFOS, substituindo
launchd por APScheduler interno — temporário) e deprecação do catalog legado
com pré-condição obrigatória de migrar os embeddings `vector(1536)` para
`commerce_products` antes do drop.

> **Risco transversal:** este sprint tem 4 workstreams em um ciclo único.
> Estimativa qualitativa ~1.5 sprint. Mitigação: sequenciamento estrito (W1
> antes de W2; embeddings antes do drop legado), gate por workstream nos
> pre-homolog checks. Se a fase de implementação ultrapassar 5 dias, o
> Generator deve escalar split tático "Sprint 10a/10b".

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents (runtime/repo/config/ui) | Service, Runtime, UI |
| dashboard | Repo, Service, UI |
| commerce | Types, Repo |
| integrations (efos_backup, jobs, scheduler) | Config, Repo, Service, Runtime |
| catalog | Service, Runtime, UI, Schema (remoção) |
| observability (langfuse helper) | Service |

## Considerações multi-tenant

- Todas as queries em `contacts`, `sync_schedule`, `pedidos.account_external_id`
  filtram por `tenant_id`.
- Auto-criação de `contact` `origin='self_registered'` parte do `tenant_id`
  já resolvido pelo IdentityRouter (lookup de instância da Evolution API).
- Notificação dual itera apenas gestores ativos do mesmo tenant (`GestorRepo.
  listar_ativos_por_tenant` já existe).
- `sync_schedule` é por tenant (preparado para futuros tenants além de JMB).
- F-07 valida `gestores.role='admin'` ANTES de operar — gestor comum recebe 403.

## Secrets necessários (Infisical)

Sem secrets novos. Reuso de:

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| EVOLUTION_API_URL | development+staging | Base do endpoint Evolution (B-23) |
| EVOLUTION_API_KEY | development+staging | apikey header (B-23) |
| OPENAI_API_KEY | development+staging | Whisper + embeddings batch (E17) |
| LANGFUSE_PUBLIC_KEY | development+staging | Wrapper Langfuse (B-30) |
| LANGFUSE_SECRET_KEY | development+staging | idem |
| LANGFUSE_HOST | development+staging | idem |
| EFOS_DOCKER_CONTAINER | staging | `ai-sales-postgres` para pg_restore |

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| Anthropic + Langfuse | Sem integração nativa (ao contrário de OpenAI). Cliente puro não cria generations. | Wrapper manual `start_generation` + `update(usage=...)` (Opção A do BUGS.md B-30). |
| asyncpg + pgvector | `ORDER BY` por similaridade retorna 0 rows silenciosamente; `CAST(:p AS vector)` falha. | Manter padrão do Sprint 9: f-string `'{vec}'::vector` + sort em Python. |
| redis-py >= 5.0 | `decode_responses=True` retorna `str`. Chamar `.decode()` quebra. | Remover `.decode()` (B-29). |
| Evolution API base64 | URL de `audioMessage` retorna conteúdo criptografado E2E. | Endpoint `/chat/getBase64FromMediaMessage`. |
| APScheduler | `add_job` com mesmo id sem `replace_existing=True` levanta exceção. | Usar `replace_existing=True` no startup. |
| Alembic + pgvector | `CREATE EXTENSION` nem sempre roda no upgrade. | `CREATE EXTENSION IF NOT EXISTS vector` na 0027 antes do `ADD COLUMN`. |
| Embeddings model dim | `text-embedding-3-small`=1536, `3-large`=3072. Misturar quebra busca. | Confirmar modelo histórico via `SELECT vector_dims(embedding) FROM produtos LIMIT 1` antes do batch (E17). |
| sync DELETE+INSERT | Reescrever `commerce_products` perde a coluna `embedding` migrada. | `publish` do connector EFOS: UPSERT preservando `embedding` (não tocar coluna). |
| Truncação histórico | `messages[-N:]` corta no meio de pares tool_use/tool_result → 400. | Helper `truncate_preserving_pairs` (E1). |

## Entregas

### W1 — Hotfixes não-estruturais

#### E1 — B-26: truncação preservando pares + recovery não-destrutivo
**Camadas:** Service + Runtime
**Arquivo(s):** `agents/runtime/_history.py` (NOVO); `agents/runtime/agent_gestor.py`
(`:1353` truncar, `:495` recovery); `agents/runtime/agent_rep.py` (`:528`, `:539`,
`:502` load); `agents/runtime/agent_cliente.py` (`:469`/`:480`, `:441`/`:301`
load); `tests/regression/test_b26_truncation_integrity.py` (NOVO).
**Critérios de aceitação:**
- [ ] `truncate_preserving_pairs(messages, max_msgs)` nunca retorna `tool_result`
  órfão como primeiro item, nem `tool_use` no último item sem `tool_result`
  imediatamente após.
- [ ] `repair_history(messages)` remove apenas pares órfãos do início, preserva
  texto user/assistant; só descarta total como último recurso e loga ERROR.
- [ ] Os 3 agentes chamam o helper compartilhado (zero duplicação).
- [ ] Bloco `except messages.0.content.0:unexpected tool_result` chama
  `repair_history` em vez de `_limpar_historico_redis`.
- [ ] Teste: histórico de 25 msgs com pares → `truncate(...,20)` retorna
  histórico válido para Anthropic API.
- [ ] Teste: histórico já corrompido → `repair_history` retorna histórico
  válido com ≥ N mensagens text-only preservadas.

#### E2 — B-29: persona_key_redis decode em str já decodada
**Camadas:** UI (agents/ui.py)
**Arquivo(s):** `agents/ui.py:355`.
**Critérios de aceitação:**
- [ ] Remover `.decode()` quando o resultado já é `str`.
- [ ] Logs `persona_key_redis_erro` desaparecem em janela de 24h em staging
  (verificado via grep nos logs).

#### E3 — B-30: wrapper Langfuse para Anthropic
**Camadas:** Service
**Arquivo(s):** `observability/langfuse_anthropic.py` (NOVO);
`agents/runtime/_retry.py`; 3 agentes (`_get_anthropic_client` + chamadas a
`messages.create`).
**Critérios de aceitação:**
- [ ] Toda chamada Anthropic dos 3 agentes em produção gera 1 generation no
  Langfuse com `usage.input_tokens` e `usage.output_tokens` populados.
- [ ] Trace mostra `totalCost > 0` e `latency > 0` para conversas reais.
- [ ] Teste unit: mock de cliente confirma `start_generation` chamado e
  atualizado com `usage`.
- [ ] Smoke staging: enviar mensagem de teste; trace mais recente via API
  Langfuse tem `observations.length >= 1`.

#### E4 — B-23: áudio descriptografado via Evolution API
**Camadas:** UI
**Arquivo(s):** `agents/ui.py:280-330`.
**Critérios de aceitação:**
- [ ] Substituir download por URL+base64 por chamada
  `POST {EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}` com
  header `apikey`.
- [ ] Reuso de `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` (sem secrets novos).
- [ ] Smoke manual: áudio real via WhatsApp → texto transcrito aparece
  prefixado com `🎤 Ouvi: ...` no histórico Redis.
- [ ] Falha do endpoint → resposta amigável vai DIRETO via
  `send_whatsapp_message()` (não passa pelo agente — fix B-24a).

#### E5 — B-24: capacidade de áudio no system prompt + fallback direto
**Camadas:** Service + UI
**Arquivo(s):** `agents/config.py` (3 system prompts); `agents/ui.py:314-330`.
**Critérios de aceitação:**
- [ ] Bloco `## Capacidades de mensagem` adicionado nos 3 system prompts.
- [ ] Pergunta "você consegue ouvir áudio?" → bot confirma.
- [ ] Falha de transcrição → mensagem amigável fixa (não reformulada pelo LLM).
- [ ] A_TOOL_COVERAGE: capacidade declarada tem código + teste.

#### E6 — B-25: ranking_vendedores_efos + ano default + contexto temporal
**Camadas:** Repo + Runtime + Service
**Arquivo(s):** `commerce/repo.py` (método `ranking_vendedores`);
`agents/runtime/agent_gestor.py` (nova tool, defaults);
`agents/config.py` (regras de ano).
**Critérios de aceitação:**
- [ ] "Melhor vendedor de março" não dispara > 1 chamada de tool (verificado
  via Langfuse traces).
- [ ] "Março/26" → "março" mantém ano 2026 (registrado em conversa de teste).
- [ ] SQL agregada usa `commerce_orders JOIN commerce_vendedores` com
  `LIMIT top_n`.
- [ ] System prompt: "Quando o usuário não informar ano, use o ano corrente.
  Se o mês mencionado ainda não passou no ano corrente, use o ano anterior.
  Em sequências, mantenha o ano da pergunta anterior".

### W2 — Foundations D030 (contacts + dashboard refeito)

Bloqueado por W1.E1 (B-26).

#### E7 — Migration `contacts` + extensão `commerce_accounts_b2b` + `pedidos.account_external_id`
**Camadas:** Schema
**Arquivo(s):** `alembic/versions/0025_d030_contacts_and_account_extras.py`.
**Critérios de aceitação:**
- [ ] Tabela `contacts(id UUID PK, tenant_id, account_external_id VARCHAR,
  nome, papel ENUM(comprador|dono|gerente|outro), authorized BOOL,
  channels JSONB, origin ENUM(erp_suggested|manual|self_registered),
  last_active_at, criado_em, atualizado_em, authorized_by_gestor_id NULL)`
  criada com índices `(tenant_id, account_external_id)` e GIN em `channels`.
- [ ] `pedidos.account_external_id VARCHAR NULL` adicionado (transição —
  não removemos `cliente_b2b_id` ainda).
- [ ] `commerce_accounts_b2b` ganha `contato_padrao`, `telefone`,
  `telefone_celular`, `email`, `nome_fantasia`, `dataultimacompra`.
- [ ] Migração de dados: 5 contatos atuais em `clientes_b2b` legado → INSERT
  em `contacts` com `origin='manual'` (data migration na própria 0025).
- [ ] `alembic upgrade head` aplica em staging sem erro.
- [ ] `clientes_b2b` continua existindo (deprecação programada para sprint
  futuro — ainda é fallback de leitura).
- [ ] `SELECT COUNT(*) FROM contacts WHERE origin='manual'` ≥ 5 após migration.

#### E8 — `normalize_accounts_b2b` populando os novos campos
**Camadas:** Service (integrations)
**Arquivo(s):** `integrations/connectors/efos_backup/normalize.py`.
**Critérios de aceitação:**
- [ ] Mapear `cl_contato → contato_padrao`, `cl_telefone → telefone`,
  `cl_telefonecelular → telefone_celular`, `cl_email → email`,
  `cl_nomefantasia → nome_fantasia`, `cl_dataultimacompra → dataultimacompra`.
- [ ] Próximo sync EFOS popula os 6 campos.
- [ ] `SELECT COUNT(*) FROM commerce_accounts_b2b WHERE telefone IS NOT NULL`
  ≥ 900 (espelho do 93% real do EFOS).
- [ ] `publish` do connector faz UPSERT preservando `commerce_products.embedding`
  (não destruir coluna no DELETE+INSERT).

#### E9 — `ContactRepo` + auto-criação `self_registered`
**Camadas:** Repo + Service + UI
**Arquivo(s):** `agents/repo.py` (`ContactRepo`); `agents/service.py`
(IdentityRouter consulta `contacts` antes de `clientes_b2b`); `agents/ui.py`
(criação `self_registered` ao receber DESCONHECIDO).
**Critérios de aceitação:**
- [ ] Mensagem de número novo cria `contacts` `origin='self_registered'`,
  `authorized=False` em até 1s.
- [ ] 2ª mensagem do mesmo número antes de autorização não duplica registro;
  remetente recebe a mesma mensagem de "aguardando autorização".
- [ ] Bot NÃO responde como `AgentCliente`/`AgentRep` quando
  `contacts.authorized=false`.

#### E10 — Notificação dual ao gestor (dashboard + WhatsApp) + comando AUTORIZAR
**Camadas:** Service + UI
**Arquivo(s):** `agents/service.py` (`notify_gestor_pendente`); `agents/ui.py`
(comando `AUTORIZAR +55...`); `dashboard/ui.py` (badge de pendentes);
`dashboard/templates/contatos.html`.
**Critérios de aceitação:**
- [ ] Gestor recebe via WhatsApp template:
  `[CONTATO PENDENTE] +55... mandou: "{msg}". Possível cliente:
  {nome_fantasia} (CNPJ {cnpj}). Responda AUTORIZAR {numero} ou abra o painel.`
- [ ] Match de candidato em `commerce_accounts_b2b` por CNPJ explícito ou
  nome de empresa via string match (sem LLM no MVP).
- [ ] `/dashboard/contatos` mostra contagem de pendentes em badge no header.
- [ ] Comando `AUTORIZAR +55...` no WhatsApp do gestor altera
  `contacts.authorized=true` e vincula `account_external_id` se candidato
  indicado pelo gestor.
- [ ] Auditoria: `contacts.authorized_by_gestor_id` registra quem autorizou.
- [ ] Throttle: 1 notificação por número por 6h.

#### E11 — Dashboard `/dashboard/contatos` refeito + `/dashboard/clientes` read-only
**Camadas:** UI + Repo
**Arquivo(s):** `dashboard/ui.py:475-518` (POST contatos/novo);
`dashboard/ui.py:927-1003` (`_get_clientes`); `dashboard/templates/contatos*.html`;
`dashboard/templates/clientes*.html` (remover botão "Novo Cliente").
**Critérios de aceitação:**
- [ ] POST `/dashboard/contatos/novo` com `perfil=cliente` faz INSERT em
  `contacts` (não UPDATE em `clientes_b2b`).
- [ ] `cliente_b2b_id` selecionado é `external_id` do EFOS → registra em
  `contacts.account_external_id`.
- [ ] Listagem `/dashboard/contatos` mostra UNION: contacts (todos) +
  gestores + reps, com badge de origem.
- [ ] `/dashboard/clientes` exibe somente leitura: 614 clientes do EFOS, sem
  botão "Novo Cliente".
- [ ] `result.rowcount` é checado em todos os UPDATEs do dashboard
  (anti-NO-OP) — se 0, retornar 400 com mensagem clara.
- [ ] Teste de regressão `test_b27_contato_dashboard.py`.

#### E12 — `confirmar_pedido_em_nome_de` aceita `account_external_id`
**Camadas:** Repo + Runtime + Service
**Arquivo(s):** `agents/runtime/agent_gestor.py:768`; `agents/repo.py:351`
(fallback `commerce_accounts_b2b` em `get_by_id`); `orders/service.py`.
**Critérios de aceitação:**
- [ ] Pedido em nome de cliente que existe apenas em `commerce_accounts_b2b`
  é confirmado e gravado com `pedidos.account_external_id` preenchido;
  `cliente_b2b_id` pode ser NULL.
- [ ] Mensagem técnica "ID instável"/"Cliente não encontrado" não aparece
  para clientes existentes no EFOS.
- [ ] Teste de regressão `test_b28_pedido_efos.py`.

### W3 — F-07 Sync EFOS schedule (admin only)

#### E13 — Migration `sync_schedule` + `gestores.role`
**Camadas:** Schema
**Arquivo(s):** `alembic/versions/0026_sync_schedule_and_gestor_role.py`.
**Critérios de aceitação:**
- [ ] `sync_schedule(id PK, tenant_id, connector_kind, preset
  ENUM(manual|diario|2x_dia|4x_dia|horario), cron_expression NULL,
  enabled BOOL, last_triggered_at NULL, next_run_at NULL, atualizado_em)`
  com `UNIQUE (tenant_id, connector_kind)`.
- [ ] Seed default: `(jmb, efos_backup, diario, '0 13 * * *', true)`.
- [ ] `gestores.role ENUM('admin','gestor') DEFAULT 'gestor'`.
- [ ] Lauzier marcado `role='admin'` em staging via UPDATE pós-deploy
  (documentado em homologação).

#### E14 — APScheduler interno + reschedule em runtime + Redis lock
**Camadas:** Runtime + Repo
**Arquivo(s):** `integrations/runtime/scheduler.py` (NOVO);
`integrations/repo.py` (`SyncScheduleRepo`); `integrations/jobs/sync_efos.py`
(Redis lock); `main.py` (startup hook).
**Critérios de aceitação:**
- [ ] App startup registra jobs APScheduler para todos os schedules
  `enabled=true` (com `replace_existing=True`).
- [ ] Update via UI chama `scheduler.reschedule_job` sem restart.
- [ ] "Rodar agora" cria job one-shot e respeita Redis lock
  `sync:efos:{tenant}:running` (TTL 30min); 2º clique ≤ 30min retorna 409
  com mensagem "sync já em andamento".
- [ ] Sync explodindo dentro do job não derruba o app (try/except interno).

#### E15 — UI `/dashboard/sync` (admin only)
**Camadas:** UI
**Arquivo(s):** `dashboard/ui.py` (rota GET/POST `/dashboard/sync`);
`dashboard/templates/sync.html`.
**Critérios de aceitação:**
- [ ] 5 radio buttons (presets), toggle ativo, Salvar, Rodar agora, blocos
  próxima/última execução, histórico das 10 últimas `sync_runs`.
- [ ] Gate `gestores.role='admin'` — gestor não-admin recebe 403.
- [ ] Após Salvar, página recarrega mostrando próxima execução calculada
  via cron.

#### E16 — Migração launchd → APScheduler
**Camadas:** Runtime + Deploy
**Arquivo(s):** `output/deploy/com.jmb.efos-sync.plist` (renomear `.disabled`).
**Sequência obrigatória:**
1. Deploy E14 + E15 em staging com seed `diario`.
2. Confirmar 1 execução real automática (não manual) no APScheduler.
3. `launchctl unload ~/Library/LaunchAgents/com.jmb.efos-sync.plist`.
4. Renomear plist para `.disabled` no repo (rollback rápido).
5. **Não remover plist do repo neste sprint** — fazer no Sprint 11.

**Critérios de aceitação:**
- [ ] Smoke gate confirma job APScheduler em `scheduler.get_jobs()`.
- [ ] Documentado em `homologacao_sprint-10.md`.

### W4 — Deprecação catalog legado

Bloqueado pela migração de embeddings (E17).

#### E17 — Migration: embedding em commerce_products + job batch
**Camadas:** Schema + Service
**Arquivo(s):** `alembic/versions/0027_commerce_products_embedding.py`;
`scripts/migrate_embeddings.py` (NOVO).
**Critérios de aceitação:**
- [ ] `CREATE EXTENSION IF NOT EXISTS vector` antes do `ADD COLUMN`.
- [ ] Coluna `embedding vector(1536)` em `commerce_products`.
- [ ] Confirmação prévia via `SELECT vector_dims(embedding) FROM produtos LIMIT 1`
  documentada (modelo histórico real).
- [ ] Job copia `produtos.embedding` → `commerce_products.embedding` por
  match `codigo_externo`.
- [ ] Produtos `commerce_products` sem match em `produtos` ganham embedding
  via OpenAI antes do drop (modelo confirmado em E17).
- [ ] ≥ 95% das 743 linhas de `commerce_products` têm embedding após o job.
- [ ] Smoke comportamental: cliente pede "shampoo" → bot retorna ≥ 1 produto
  via busca semântica.

#### E18 — AgentCliente + CatalogService leem `commerce_products`
**Camadas:** Service + Runtime
**Arquivo(s):** `catalog/service.py:324` (query troca `produtos` →
`commerce_products`); `agents/runtime/agent_cliente.py:633` (confirma uso).
**Critérios de aceitação:**
- [ ] Grep `FROM produtos\|JOIN produtos` em `output/src/` retorna 0 hits
  (lista categorizada no plano de execução).
- [ ] Cliente busca semântica funciona em staging com query EAN, query nome,
  query genérica.

#### E19 — Remover crawler/enricher/scheduler/painel/rotas/template/playwright
**Camadas:** Runtime + UI + Service + Schema
**Arquivo(s) a remover:**
- `catalog/runtime/crawler/efos.py`, `efos_http.py`, `base.py`.
- `catalog/runtime/enricher.py`, `catalog/runtime/scheduler_job.py`.
- `catalog/templates/produtos.html`.
- Rotas `/catalog/painel`, `/catalog/painel/{id}/aprovar|rejeitar`.
- Métodos `aprovar_produto`/`rejeitar_produto`/`listar_produtos` em
  `CatalogService`.
- Tipo `StatusEnriquecimento`.
- `pyproject.toml` — `playwright`.
- `docs/design-docs/index.md` — D018, D019 marcados obsoletos.
- `ARCHITECTURE.md` — catalog domain reduzido.

**Critérios de aceitação:**
- [ ] `pytest -m unit` passa após remoção.
- [ ] `import-linter` passa.
- [ ] App inicia sem erro de import.
- [ ] Smoke do AgentCliente continua passando.

#### E20 — Migration de drop
**Camadas:** Schema
**Arquivo(s):** `alembic/versions/0028_drop_produtos_legacy.py`.
**Pré-condição obrigatória:** E17, E18, E19 verdes.
**Critérios de aceitação:**
- [ ] DROP TABLE `produtos`, `crawl_runs` (se existir),
  `categorias`/`subcategorias` (somente após grep confirmar que vinham só do
  crawler).
- [ ] `SELECT 1 FROM produtos` falha com tabela inexistente.

## Versão alvo

`v0.10.0` — bumpar `output/src/__init__.py:12` (`__version__ = "0.10.0"`)
no primeiro commit. Critério `A_VERSION` no contrato: `GET /health` retorna
`version=0.10.0`.

## Ambiente de execução

| Componente | Localização no macmini-lablz |
|------------|------------------------------|
| psql / pg_restore | Container `ai-sales-postgres` (`docker exec ...`) |
| Python / venv | `~/MyRepos/ai-sales-agent-claude/output/.venv/bin/python` |
| Infisical | `/usr/local/bin/infisical` |
| APScheduler | dentro do processo FastAPI (uvicorn) |
| Embeddings job (E17) | `python scripts/migrate_embeddings.py --tenant jmb` antes do drop |
| PYTHONPATH | `./src` a partir de `output/` |

Variável: `EFOS_DOCKER_CONTAINER=ai-sales-postgres` (Infisical staging — já existe).

## Mapeamento de campos confirmados (D030)

| Tabela origem (EFOS) | Campo origem | Campo destino |
|----------------------|--------------|---------------|
| tb_clientes.cl_contato | nome PF (22% preenchido) | commerce_accounts_b2b.contato_padrao |
| tb_clientes.cl_telefone | telefone fixo (93%) | commerce_accounts_b2b.telefone |
| tb_clientes.cl_telefonecelular | celular (92%) | commerce_accounts_b2b.telefone_celular |
| tb_clientes.cl_email | email (95%) | commerce_accounts_b2b.email |
| tb_clientes.cl_nomefantasia | fantasia (~100%) | commerce_accounts_b2b.nome_fantasia |
| tb_clientes.cl_dataultimacompra | última compra | commerce_accounts_b2b.dataultimacompra |
| tb_clientes.cl_codigo | external_id (já existe) | commerce_accounts_b2b.external_id |

PK confirmada única no Sprint 8. Revalidar antes do sync:
`SELECT cl_codigo, COUNT(*) FROM efos_staging.tb_clientes GROUP BY cl_codigo HAVING COUNT(*) > 1` deve retornar 0 linhas.

## Critério de smoke staging

Script: `scripts/smoke_sprint_10.py` (executável contra `http://100.113.28.85:8000`).

Verificações:
- [ ] `GET /health` retorna `version=0.10.0` e `anthropic=ok`.
- [ ] `alembic current` em 0028.
- [ ] `SELECT COUNT(*) FROM contacts` ≥ 5.
- [ ] `SELECT COUNT(*) FROM commerce_accounts_b2b WHERE telefone IS NOT NULL` ≥ 900.
- [ ] `SELECT COUNT(*) FROM commerce_products WHERE embedding IS NOT NULL` ≥ 700.
- [ ] `SELECT enabled FROM sync_schedule WHERE tenant_id='jmb'` = true.
- [ ] APScheduler `scheduler.get_jobs()` lista o job EFOS.
- [ ] `SELECT 1 FROM produtos` falha com tabela inexistente (E20 aplicado).
- [ ] Langfuse trace mais recente tem `observations.length >= 1` e `usage.input_tokens > 0`.
- [ ] `/dashboard/contatos` carrega com badge de pendentes visível.
- [ ] `/dashboard/clientes` retorna 200 sem botão "Novo Cliente" no HTML.
- [ ] `/dashboard/sync` retorna 200 para usuário admin, 403 para não-admin.

Saída esperada: `ALL OK`.

## Critérios A_BEHAVIORAL (obrigatórios)

### A_BEHAVIORAL_AGENT (Cliente, Rep, Gestor)

Executar via Chrome DevTools MCP / webhook simulado. Lista mínima:
- Cliente envia áudio real → bot responde com base no texto transcrito.
- Cliente pergunta "você ouve áudio?" → bot confirma.
- Cliente faz 6 buscas seguidas (forçando truncação em 20) → bot mantém
  contexto do produto inicial.
- Gestor: "melhor vendedor de março" → 1 chamada de tool (verificado via
  Langfuse), resposta com ano corrente.
- Gestor: "fazer pedido para Lauzier Pereira" → "sim" → pedido confirmado,
  PDF emitido (via fallback `commerce_accounts_b2b`).
- Número desconhecido envia "oi" → recebe "vou avisar o gestor"; gestor
  recebe notificação WhatsApp.
- Gestor responde `AUTORIZAR +55...` → 2ª mensagem do número agora é
  processada normalmente.

### A_BEHAVIORAL_UI (Dashboard)

Pre-homologation review (10 rotas) — protocolo `PRE_HOMOLOGATION_REVIEW.md`.
Adicionalmente:
- `/dashboard/contatos`: badge "Pendentes" visível; criar contato cliente
  vinculado a EFOS aparece na listagem em < 1s.
- `/dashboard/clientes`: read-only, sem "Novo Cliente".
- `/dashboard/sync`: salvar preset diferente → próxima execução muda; "Rodar
  agora" cria entry em `sync_runs`.

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | Áudio cliente | Cliente envia áudio real via WhatsApp | Bot transcreve e responde com base no texto |
| H2 | Capacidade áudio | Cliente pergunta "você consegue ouvir áudio?" | Bot confirma |
| H3 | Histórico preservado | Gestor faz conversa com ≥ 6 tool calls | Contexto preservado, sem reset destrutivo |
| H4 | Pedido EFOS | Gestor pede pedido em nome de cliente EFOS → confirma | Pedido criado, PDF gerado |
| H5 | Cadastro contato | Criar contato cliente via dashboard | Aparece na listagem |
| H6 | Self-registered | Número novo manda mensagem | Gestor notificado WhatsApp + dashboard |
| H7 | Comando AUTORIZAR | Gestor responde `AUTORIZAR +55...` | `contacts.authorized=true`, próxima msg processa |
| H8 | F-07 preset | Admin altera preset em `/dashboard/sync` | Próxima execução muda |
| H9 | F-07 lock | "Rodar agora" 2x em < 30min | 2ª retorna 409 |
| H10 | Busca semântica | Cliente busca "shampoo" após drop legado | Retorna ≥ 1 produto |
| H11 | Langfuse custo | Conversa real | Trace tem `totalCost > 0` |
| H12 | Ranking eficiente | "Melhor vendedor de março" | 1 tool call, ano 2026 |
| H13 | Clientes read-only | Acessar `/dashboard/clientes` | Sem botão "Novo Cliente" |

## Decisões pendentes

Nenhum ADR novo. Decisões técnicas residuais (Generator decide e documenta no
contrato):

1. Modelo de embedding histórico (3-small 1536 vs 3-large 3072) — confirmar
   antes do batch E17. Escalonamento se custo de regerar > $5.
2. Estratégia de UPSERT em `publish` do connector EFOS para preservar
   `commerce_products.embedding` (E18 detalha solução).

## Fora do escopo

- Bling adapter (Sprint 11+).
- AnalystAgent (D031, Sprint 11).
- Drop de `clientes_b2b` legado (manter por 1-2 sprints como fallback).
- Remoção do plist `launchd` do repo (só renomear `.disabled`).
- Multi-canal Telegram/voice (`contacts.channels[]` JSONB já preparado;
  só `kind=whatsapp` neste sprint).
- F-06 Painel de Divergências (pós-Bling).
- Job de cleanup de `self_registered` não autorizados (PO definiu: manter
  indefinidamente).

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Sprint > 5 dias por escopo grande | Alta | Atraso piloto | Split tático 10a/10b se ultrapassar; gate por workstream |
| Migração de embeddings com modelo errado | Média | Busca semântica quebrada | Verificar `vector_dims` antes do batch; rollback simples (não dropar `produtos` até E18 verde) |
| `sync_schedule` vs `launchd` race condition | Média | 2 syncs simultâneos | Sequência E16 obrigatória + Redis lock |
| Notificação dual gera spam ao gestor | Média | UX ruim | Throttle: 1 notificação por número por 6h |
| `result.rowcount=0` em UPDATEs antigos | Alta | Regressão silenciosa | E11 audita TODOS UPDATEs do dashboard |
| `commerce_products.embedding` perdido em sync | Alta | Busca quebra após sync | UPSERT preservando coluna em `publish` |

## Handoff para o próximo sprint

- `contacts` é write model canônico — pronto para Bling adapter pushear via
  `WRITE_CONTACTS` capability.
- `pedidos.account_external_id` permite remover FK rígida quando
  `clientes_b2b` for deprecada (Sprint 11+).
- B-30 resolvido habilita AnalystAgent (D031, Sprint 11) ler generations reais.
- F-07 é temporário — sai quando webhooks Bling entrarem (Sprint 12+).
- Catalog domain reduzido a busca + service over `commerce_*`.
- `gestores.role` permite expansão futura (admin, manager, viewer).
- Plist `launchd` `.disabled` no repo — remover no Sprint 11 com confiança total.
