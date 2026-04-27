# Sprint 8 — Hotfixes Piloto + Integração EFOS via Backup Diário

**Status:** Em planejamento
**Data:** 2026-04-27
**Pré-requisitos:** Sprint 7 APROVADO ✅; Piloto JMB ativo desde 2026-04-22

## Objetivo

Corrigir os 3 bugs críticos do piloto (B-10/B-11/B-12) e criar o pipeline diário
SSH/pg_restore que popula um read model canônico (`commerce_*`), habilitando 3 novas
consultas de relatório no AgentGestor.

## Contexto

O piloto JMB expôs 3 bugs em produção durante a semana de 2026-04-24. Ao mesmo tempo,
acesso SSH ao servidor EFOS foi confirmado (dumps diários em `C:\BACKUP EFOS\` às 08:30
e 12:30, 153 MB, formato custom pg_dump). O crawler Playwright segue ativo neste sprint
— a migração dos reads do agente para `commerce_*` é Sprint 9. Sprint 8 entrega:
hotfixes + pipeline funcional + 3 tools de relatório para o AgentGestor baseados em
dados reais do EFOS.

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents | Repo, Runtime (hotfixes B-10/B-11/B-12) |
| integrations (novo — 5º domínio) | Types, Config, Repo, Runtime (connectors/efos_backup), Jobs |
| commerce (novo — 6º domínio) | Types, Repo |
| alembic | Migrations 0018–0023 |

## Considerações multi-tenant

- `sync_runs` e `sync_artifacts` têm `tenant_id` — isolamento por tenant desde o dia 1.
- Todas as tabelas `commerce_*` têm `tenant_id UUID NOT NULL`.
- `EFOSBackupConfig.for_tenant("jmb")` carrega credenciais SSH por tenant via Infisical.
- Na Fase 2, todos os métodos `CommerceRepo` recebem `tenant_id` como primeiro argumento.
- Sprint 8 suporta apenas o tenant `jmb`; o conector EFOS não é multi-tenant ainda (Sprint 9+).

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| `JMB_EFOS_SSH_HOST` | development, staging | jmbdistribuidora.ddns.com.br |
| `JMB_EFOS_SSH_USER` | development, staging | suporte |
| `JMB_EFOS_SSH_KEY_PATH` | development, staging | ~/.ssh/oci-lablz-01 |
| `JMB_EFOS_BACKUP_REMOTE_PATH` | development, staging | C:\BACKUP EFOS\ |
| `JMB_EFOS_ARTIFACT_DIR` | development, staging | Caminho local absoluto para guardar .backup (ex: /var/efos-artifacts) |
| `JMB_EFOS_STAGING_DB_URL` | development, staging | postgresql://... banco local isolado para pg_restore (ex: postgresql://localhost/efos_staging) |

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| asyncpg + pgvector | `ORDER BY` com expressão vetorial retorna 0 rows silenciosamente | Fetch all sem `ORDER BY`, sort em Python |
| asyncpg + pgvector | `CAST(:param AS vector)` falha na inferência de tipo | Interpolar f-string `'{vec}'::vector` |
| paramiko SFTP + Windows | Paths com backslash em servidor Windows | Usar separador `\\` ou `ntpath`; listar dir antes de compor path |
| pg_restore custom format | Sem flag `--format=c` o restore falha silenciosamente | Sempre passar `--format=c` (ou `-Fc`) |
| pg_restore schema conflict | Segundo restore falha se staging DB já tiver schema | Criar staging DB limpo antes de cada run; DROP ao finalizar |
| paramiko SSH key type | `RSAKey` vs `Ed25519Key` — tipo errado lança exceção | Usar `paramiko.pkey.PKey.from_private_key_file()` genérico |
| structlog event reserved | `event=` é kwarg reservado em structlog | Usar string posicional como primeiro argumento |
| EFOS tb_vendedor duplica | Mesma `ve_codigo` aparece 2x (uma linha por filial) | `SELECT DISTINCT ON (ve_codigo)` ao normalizar |
| EFOS cl_cidade uppercase | Cidades armazenadas UPPERCASE no banco EFOS (ex: "VINHEDO") | Normalizar input do gestor com `.upper()` antes de comparar |
| fpdf2 2.x | `pdf.output()` retorna `bytearray` | `bytes(pdf.output())` |

## Entregas

### E0-A — Fix B-10: representante_id ausente no get_by_telefone
**Camadas:** Repo
**Arquivo(s):** `output/src/agents/repo.py`, `output/src/agents/ui.py`
**Critérios de aceitação:**
- [ ] `get_by_telefone()` inclui `representante_id` no SELECT (corrige linha 109 de `repo.py`)
- [ ] `ClienteB2B` type tem campo `representante_id: UUID | None`
- [ ] `ui.py` propaga `representante_id` do objeto `ClienteB2B` para o input do pedido (corrige linha 297)
- [ ] Pedido criado via WhatsApp para cliente com rep vinculado tem `representante_id` não-nulo no banco
- [ ] Teste unitário `test_get_by_telefone_retorna_representante_id` com mock de banco, marcado `@pytest.mark.unit`

### E0-B — Fix B-11: contexto Redis stale ao trocar persona
**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/ui.py`, `output/src/agents/runtime/agent_cliente.py`, `output/src/agents/runtime/agent_rep.py`
**Critérios de aceitação:**
- [ ] Ao trocar persona de um número, todas as chaves Redis do padrão `conv:{tenant_id}:{numero}*` são invalidadas
- [ ] A invalidação ocorre no `IdentityRouter` em `ui.py` antes de instanciar o novo agente
- [ ] Teste unitário `test_troca_persona_invalida_redis` — verifica `redis.delete()` chamado com a chave correta, marcado `@pytest.mark.unit`
- [ ] Teste unitário: segunda mensagem com nova persona não carrega histórico da persona anterior

### E0-C — Fix B-12: instrumentação Langfuse incompleta
**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/runtime/agent_gestor.py`, `output/src/agents/runtime/agent_rep.py`, `output/src/agents/runtime/agent_cliente.py`
**Critérios de aceitação:**
- [ ] `AsyncAnthropic()` instanciado com wrapper Langfuse em todos os 3 agentes dentro de `_get_anthropic_client()` (corrige linhas: agent_cliente.py:401, agent_rep.py:464, agent_gestor.py:920)
- [ ] `session_id=str(conversa.id)` definido no trace Langfuse ao iniciar cada conversa (corrige agent_cliente.py:240, agent_rep.py:291, agent_gestor.py:368)
- [ ] `_lf_ctx.update_current_observation(output=resposta_final)` chamado antes de retornar (corrige agent_cliente.py:384, agent_rep.py:429, agent_gestor.py:489)
- [ ] Teste unitário: mock do Langfuse verifica que `update_current_observation` foi chamado com `output` não-nulo, marcado `@pytest.mark.unit`
- [ ] Testes existentes que injetam `_anthropic` mock não quebram

### E1 — Domínio integrations/ (estrutura + auditoria)
**Camadas:** Types, Config, Repo
**Arquivo(s):** `output/src/integrations/__init__.py`, `output/src/integrations/types.py`, `output/src/integrations/config.py`, `output/src/integrations/repo.py`
**Critérios de aceitação:**
- [ ] `SyncStatus` enum: `RUNNING`, `SUCCESS`, `ERROR`, `SKIPPED`
- [ ] `ConnectorCapability` enum: `CATALOG`, `PRICING_B2B`, `CUSTOMERS_B2B`, `ORDERS_B2B`, `INVENTORY`, `SALES_HISTORY`
- [ ] `SyncRun` dataclass: `id`, `tenant_id`, `connector_kind`, `capabilities`, `started_at`, `finished_at`, `status`, `rows_published`, `error`
- [ ] `SyncArtifact` dataclass: `id`, `tenant_id`, `connector_kind`, `artifact_path`, `artifact_checksum`, `created_at`
- [ ] `EFOSBackupConfig.for_tenant(tenant_id: str)` lê secrets via Infisical usando as variáveis `JMB_EFOS_*`
- [ ] `SyncRunRepo.create(run: SyncRun, session)` e `SyncRunRepo.update_status(run_id, status, rows_published, error, session)` salvam no banco com `tenant_id`
- [ ] `SyncArtifactRepo.find_by_checksum(tenant_id, checksum, session)` retorna `SyncArtifact | None`
- [ ] `import-linter check` confirma: `integrations/` não importa `agents/`, `catalog/`, `orders/`, `tenants/`, `dashboard/`

### E2 — Conector EFOS (acquire + stage + normalize + publish)
**Camadas:** Runtime (connectors)
**Arquivo(s):**
- `output/src/integrations/connectors/efos_backup/__init__.py`
- `output/src/integrations/connectors/efos_backup/acquire.py`
- `output/src/integrations/connectors/efos_backup/stage.py`
- `output/src/integrations/connectors/efos_backup/normalize.py`
- `output/src/integrations/connectors/efos_backup/publish.py`

**Critérios de aceitação:**
- [ ] `acquire.py`: conecta via SSH (paramiko), lista `C:\BACKUP EFOS\`, identifica dump mais recente ≥ 12:30 do dia atual (ou D-1 se hora atual < 13:00 BRT), calcula SHA-256 do arquivo remoto antes de baixar, baixa via SFTP para `artifact_dir` local
- [ ] `stage.py`: cria DB `efos_staging` se não existir, executa `pg_restore --format=c --no-owner --no-privileges -d efos_staging <arquivo>`, valida presença das 6 tabelas mínimas (`tb_itens`, `tb_clientes`, `tb_pedido`, `tb_itenspedido`, `tb_estoque`, `tb_vendas`), lança `StagingValidationError` se alguma tabela faltar
- [ ] `normalize.py`: mapeia `tb_itens` → `CommerceProduct` (sku=it_codigo, ean=it_codigobarra), `tb_clientes` → `CommerceAccountB2B` (com `cl_cidade`, `cl_situacaocliente`, `cl_vendedori` como `vendedor_principal_codigo`), `tb_pedido+tb_itenspedido` → `CommerceOrder+CommerceOrderItem` (com `vendedor_id` e `vendedor_nome` denormalizado via JOIN `tb_vendedor`), `tb_estoque` → `CommerceInventory` (es_saldo), `tb_vendas` → `CommerceSalesHistory`, `tb_vendedor` DISTINCT ON `ve_codigo` → `CommerceVendedor`
- [ ] `publish.py`: transação única — DELETE WHERE tenant_id + INSERT em todas as tabelas `commerce_*` do tenant; rollback total se qualquer INSERT falhar; atualiza `synced_at` e `snapshot_checksum` em cada tabela
- [ ] Testes unitários em `normalize.py` e `publish.py` com dados mockados (sem I/O real), marcados `@pytest.mark.unit`
- [ ] `acquire.py` e `stage.py` testados em integração, marcados `@pytest.mark.integration` (sem rodar em `pytest -m unit`)

### E3 — Migrations 0018–0023
**Camadas:** Alembic
**Arquivo(s):**
- `output/alembic/versions/0018_integrations.py` — `sync_runs`, `sync_artifacts`
- `output/alembic/versions/0019_commerce.py` — `commerce_products`, `commerce_product_channel`
- `output/alembic/versions/0020_commerce_accounts.py` — `commerce_accounts_b2b`
- `output/alembic/versions/0021_commerce_orders.py` — `commerce_orders`, `commerce_order_items`
- `output/alembic/versions/0022_commerce_inventory.py` — `commerce_inventory`, `commerce_sales_history`
- `output/alembic/versions/0023_commerce_vendedores.py` — `commerce_vendedores`

**Critérios de aceitação:**
- [ ] `alembic upgrade head` aplica todas as 6 migrations em sequência sem erro em banco limpo
- [ ] `alembic downgrade -1` reverte a migration mais recente sem deixar resíduos
- [ ] Todas as tabelas `commerce_*` têm colunas: `tenant_id UUID NOT NULL`, `source_system VARCHAR(32)`, `external_id VARCHAR(64)`, `synced_at TIMESTAMPTZ`, `snapshot_checksum VARCHAR(64)`
- [ ] `sync_runs` tem índice em `(tenant_id, connector_kind, started_at DESC)`
- [ ] `sync_artifacts` tem índice UNIQUE em `(tenant_id, artifact_checksum)`
- [ ] `commerce_vendedores` tem `ve_codigo VARCHAR(32)`, `ve_nome TEXT` e índice em `(tenant_id, ve_codigo)`

### E4 — CLI sync_efos + launchd plist
**Camadas:** Jobs
**Arquivo(s):** `output/src/integrations/jobs/sync_efos.py`, `scripts/launchd/com.jmb.efos-sync.plist`
**Critérios de aceitação:**
- [ ] `python -m integrations.jobs.sync_efos --tenant jmb --dry-run` lista dump disponível sem baixar, exit 0
- [ ] `python -m integrations.jobs.sync_efos --tenant jmb` executa pipeline completo (acquire→stage→normalize→publish), popula `commerce_*`, exit 0
- [ ] Segunda execução com mesmo dump: loga "checksum já importado, skip", exit 0 (idempotente — sem modificar banco)
- [ ] `--force` ignora checksum existente e reprocessa o dump
- [ ] Em qualquer erro: `sync_runs.status = 'error'`, log via structlog com detalhes do erro, exit 1
- [ ] Staging DB (`efos_staging`) é destruído ao final, mesmo em caso de erro (bloco `finally`)
- [ ] launchd plist: `RunAtLoad=false`, `StartCalendarInterval` hora 16 minuto 0 (UTC = 13:00 BRT), stdout+stderr → `/var/log/jmb-efos-sync.log`
- [ ] Retenção local de artifacts: arquivos `.backup` mais antigos que 7 dias são apagados após cada run com sucesso

### E5 — Domínio commerce/ (read model + CommerceRepo)
**Camadas:** Types, Repo
**Arquivo(s):** `output/src/commerce/__init__.py`, `output/src/commerce/types.py`, `output/src/commerce/repo.py`
**Critérios de aceitação:**
- [ ] Types: `CommerceProduct`, `CommerceProductChannel`, `CommerceAccountB2B`, `CommerceOrder`, `CommerceOrderItem`, `CommerceInventory`, `CommerceSalesHistory`, `CommerceVendedor`
- [ ] `CommerceRepo.relatorio_vendas_representante(tenant_id, vendedor_id, mes, ano)` → `dict` com `total_vendido`, `qtde_pedidos`, `clientes`
- [ ] `CommerceRepo.relatorio_vendas_cidade(tenant_id, cidade, mes, ano)` → lista de dicts com cliente e total (cidade recebida já normalizada UPPERCASE pelo caller)
- [ ] `CommerceRepo.listar_clientes_inativos(tenant_id, cidade=None)` → lista de dicts com `nome`, `cnpj`, `telefone`, `cidade` (`situacao_cliente=2`; `cidade=None` retorna todas as cidades)
- [ ] Todos os métodos filtram por `tenant_id`
- [ ] `import-linter check` confirma: `commerce/` não importa `agents/`, `catalog/`, `orders/`, `tenants/`, `dashboard/`, `integrations/`
- [ ] Não há `service.py` nem `runtime/` em `commerce/` — é read model puro

### E6 — AgentGestor: 3 novos tools EFOS
**Camadas:** Runtime
**Arquivo(s):** `output/src/agents/runtime/agent_gestor.py`
**Critérios de aceitação:**
- [ ] Tool `relatorio_vendas_representante(nome_rep: str, mes: int, ano: int)`:
  - Fuzzy match de `nome_rep` contra `commerce_vendedores.ve_nome` (case-insensitive, `thefuzz` ou `difflib`, threshold ≥ 80)
  - Normaliza mês: `"abril"` → 4, `"mês 4"` → 4, `"4"` → 4
  - Retorna total vendido (R$), qtde pedidos, top 10 clientes formatados para WhatsApp (bullets `•`, sem markdown)
- [ ] Tool `relatorio_vendas_cidade(cidade: str, mes: int, ano: int)`:
  - Normaliza cidade → UPPERCASE antes de passar para `CommerceRepo`
  - Funciona para qualquer cidade da base (não hardcoded)
  - Retorna lista de clientes com totais formatada para WhatsApp
- [ ] Tool `listar_clientes_inativos(cidade: str | None = None)`:
  - Normaliza cidade → UPPERCASE quando presente; `None` = todas as cidades
  - Retorna nome, CNPJ, telefone, cidade formatados para WhatsApp
- [ ] `AgentGestor.__init__` aceita `commerce_repo: CommerceRepo | None = None` (injetável para testes)
- [ ] Testes unitários: mock de `CommerceRepo`, verifica fuzzy match para `"RONDINELE"`, `"Rondinele Ritter"`, `"rondinele"` → mesmo `ve_codigo`, marcados `@pytest.mark.unit`
- [ ] Teste unitário: normalização de cidade `"Vinhedo"` → `"VINHEDO"`, `"campinas"` → `"CAMPINAS"`
- [ ] Teste unitário: normalização de mês `"abril"` → 4, `"mês 4"` → 4

### E7 — Testes unitários completos
**Camadas:** Tests
**Arquivo(s):**
- `output/src/tests/unit/agents/test_hotfixes_sprint8.py`
- `output/src/tests/unit/integrations/test_normalize.py`
- `output/src/tests/unit/integrations/test_publish.py`
- `output/src/tests/unit/commerce/test_commerce_repo.py`
- `output/src/tests/unit/agents/test_agent_gestor_efos.py`

**Critérios de aceitação:**
- [ ] `pytest -m unit` passa sem falhas (inclui os 279 testes anteriores + todos os novos)
- [ ] Cobertura ≥ 80% das funções de Repo e normalize/publish novos (`integrations/`, `commerce/`)
- [ ] Nenhum teste marcado `@pytest.mark.unit` usa I/O externo (DB real, Redis real, SSH real, Evolution API real)
- [ ] `import-linter check` passa sem violações nas novas camadas

### E8 — Documentação atualizada
**Camadas:** Docs
**Arquivo(s):** `ARCHITECTURE.md`, `docs/design-docs/index.md`
**Critérios de aceitação:**
- [ ] `ARCHITECTURE.md` documenta domínios 5 (`integrations/`) e 6 (`commerce/`) com estrutura de pacotes, responsabilidades e invariantes de import-linter
- [ ] `docs/design-docs/index.md` inclui ADRs D025–D029

## Critério de smoke staging (obrigatório)

Script: `scripts/smoke_sprint_8.py`

O script deve verificar automaticamente, contra infra real (macmini-lablz):
- [ ] `GET /health` → status 200, versão ≥ 0.7.0
- [ ] `pytest -m unit` → 0 falhas
- [ ] Tabelas `commerce_products`, `commerce_accounts_b2b`, `sync_runs` existem no banco (`alembic upgrade head` aplicado)
- [ ] `python -m integrations.jobs.sync_efos --tenant jmb --dry-run` → exit 0, lista dump disponível sem erro
- [ ] `SELECT COUNT(*) FROM commerce_products WHERE tenant_id = 'jmb'` → ≥ 100 (após run completo)
- [ ] `SELECT COUNT(*) FROM sync_runs WHERE tenant_id = 'jmb' AND status = 'success'` → ≥ 1
- [ ] `GET /health` retorna 200 após sync (sem regressão no app)

Execução esperada: `python scripts/smoke_sprint_8.py` → saída `ALL OK`

## Checklist de homologação humana

| ID | Cenário | Como testar | Resultado esperado |
|----|---------|-------------|-------------------|
| H1 | B-10: pedido com representante | Cliente com rep vinculado faz pedido via WhatsApp | `SELECT representante_id FROM pedidos ORDER BY criado_em DESC LIMIT 1` → UUID não-nulo |
| H2 | B-11: troca de persona sem histórico stale | Enviar msg como CLIENTE → cadastrar mesmo número como REP → enviar nova msg | Segunda sessão não menciona contexto da sessão anterior de cliente |
| H3 | B-12: Langfuse traces completos | Trocar 3 msgs com agente; abrir Langfuse UI | Traces com output≠null, tokens>0, session_id preenchido |
| H4 | sync_efos run completo | `python -m integrations.jobs.sync_efos --tenant jmb` | Exit 0; sync_runs com 1 success; commerce_products ≥ 100 linhas |
| H5 | sync_efos idempotência | Executar sync_efos 2x com mesmo dump | Segunda execução loga "skip"; contagem em commerce_* não muda |
| H6 | Tool: relatório por representante | Gestor: "Relatório de vendas do representante Rondinele mês 4" | Total em R$, qtde pedidos, lista de clientes formatada |
| H7 | Tool: relatório por cidade | Gestor: "Relatório de vendas clientes de Vinhedo abril" | Lista de clientes de VINHEDO com totais do mês 4 |
| H8 | Tool: clientes inativos com cidade | Gestor: "Lista de clientes inativos na cidade de Itupeva" | Lista nome, CNPJ, telefone com situacao=inativo e cidade=ITUPEVA |
| H9 | Tool: clientes inativos sem cidade | Gestor: "Lista de clientes inativos" | Lista todos os inativos de todas as cidades |
| H10 | Fuzzy match de representante | Gestor: "vendas do representante rondinele ritter mês 4" | Mesmo resultado que H6 (mesmo ve_codigo) |
| H11 | Sem regressão: pedido normal | Cliente faz pedido completo via WhatsApp | Fluxo sem erros; PDF gerado; gestor recebe notificação |

## Decisões pendentes (ADRs a aprovar antes da implementação)

**D025 — SSH/SFTP via paramiko para aquisição de backup**
- Contexto: precisamos baixar arquivos `.backup` de um servidor Windows via SSH/SFTP sem agente remoto adicional
- Alternativas: rsync (não disponível em Windows sem Cygwin), WinSCP API (requer cliente Windows), curl manual (sem suporte a SFTP nativo)
- Recomendação: `paramiko` — SSH/SFTP em Python puro, sem dependência de binário externo, testável com mocks

**D026 — Staging DB efos_staging isolado do banco principal**
- Contexto: `pg_restore --format=c` requer banco Postgres sem conflito de schema; não podemos usar o banco principal do app
- Recomendação: banco local `efos_staging` criado/destruído por run; sem estado persistente fora de `commerce_*`

**D027 — CLI one-shot worker (não FastAPI lifespan) para sync EFOS**
- Contexto: sync é operação batch diária; não precisa de servidor HTTP nem ciclo de vida de app
- Recomendação: `python -m integrations.jobs.sync_efos` — simples, testável isoladamente, não acoplado ao FastAPI

**D028 — launchd (não APScheduler) para scheduling externo do sync**
- Contexto: D019 adotou APScheduler 3.x para o crawler EFOS (dentro do app); sync EFOS é job de manutenção do macmini, não do app em si
- Recomendação: launchd no macmini-lablz — sistema operacional gerencia restart, logs, timezone; o app não precisa saber do schedule

**D029 — Read model separado commerce_* do write model do app**
- Contexto: dados EFOS são externos e imutáveis do ponto de vista do app; o write model (`pedidos`, `itens_pedido`) deve permanecer independente
- Recomendação: `commerce_*` como read model puro — agente e dashboard leem mas nunca escrevem; escrita exclusiva via `sync_efos`

## Fora do escopo

- Conector B2C (www.jmbdistribuidora.com.br) — Sprint 10+
- Dashboard de sync status ("Última sincronização EFOS") — Sprint 9
- Snapshot versionado com `snapshot_id` — decisão adiada
- `product_identity_map` (cross-source SKU reconciliation entre B2B e B2C)
- Migração dos reads do agente (`catalog/repo.py`, `agents/repo.py`) para `commerce_*` — Sprint 9
- Aposentadoria do crawler Playwright — Sprint 10
- Suporte a segundo tenant no conector EFOS

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Servidor EFOS offline no horário do dump | Média | Alto | sync_efos tenta dump D-1 se dump do dia não disponível; sync_run registra erro com contexto |
| Mudança de schema EFOS sem aviso | Baixa | Alto | stage.py valida tabelas mínimas; falha explícita com StagingValidationError |
| pg_restore demora > 5 min (dump de 153 MB) | Baixa | Médio | launchd não tem timeout padrão; monitorar duração do primeiro run real |
| paramiko incompatível com chave Ed25519 | Baixa | Médio | Usar PKey.from_private_key_file() genérico; testar conexão SSH antes de iniciar Fase 1 |
| Fuzzy match de representante com falso positivo | Média | Médio | Threshold ≥ 80 similarity; se match ambíguo, tool pede confirmação ao gestor antes de executar query |

## Handoff para Sprint 9

- `commerce_products` populado e estável → `catalog/repo.py` pode migrar leituras de `produtos` para `commerce_products`
- `commerce_accounts_b2b` populado → `agents/repo.py` pode complementar clientes com dados do EFOS quando não há cadastro manual
- ADRs D025–D029 aprovados → base arquitetural para conector B2C (D030+)
- Dashboard pode receber bloco "Última sincronização EFOS" sem bloqueio de Sprint 9
- Crawler Playwright permanece ativo até Sprint 9 confirmar migração completa
