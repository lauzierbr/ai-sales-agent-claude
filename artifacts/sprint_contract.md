# Sprint Contract — Sprint 8 — Hotfixes Piloto + Integração EFOS via Backup Diário

**Status:** Revisão (pós-objeções Evaluator)
**Data:** 2026-04-27
**Versão alvo:** v0.7.0

---

## Entregas comprometidas

### Fase 0 — Hotfixes do piloto JMB

1. **E0-A** — Fix B-10: `get_by_telefone()` em `agents/repo.py` inclui `representante_id` no SELECT; `ClienteB2B` recebe campo `representante_id: UUID | None`; `ui.py` propaga o campo ao criar pedido.
2. **E0-B** — Fix B-11: ao detectar troca de persona no `IdentityRouter` em `agents/ui.py`, todas as chaves Redis do padrão `conv:{tenant_id}:{numero}*` são invalidadas antes de instanciar o novo agente.
3. **E0-C** — Fix B-12: todos os 3 agentes (`agent_cliente.py`, `agent_rep.py`, `agent_gestor.py`) instanciam `AsyncAnthropic()` via `_get_anthropic_client()` com wrapper Langfuse, definem `session_id=str(conversa.id)` no trace e chamam `_lf_ctx.update_current_observation(output=resposta_final)` antes de retornar.

### Fase 1 — Pipeline EFOS

4. **E1** — Domínio `integrations/` criado com `types.py` (enums `SyncStatus`, `ConnectorCapability`; dataclasses `SyncRun`, `SyncArtifact`), `config.py` (`EFOSBackupConfig.for_tenant()`), `repo.py` (`SyncRunRepo`, `SyncArtifactRepo`). Isolado de domínios de negócio por import-linter.
5. **E2** — Conector `integrations/connectors/efos_backup/` com 4 módulos: `acquire.py` (SSH/SFTP + SHA-256), `stage.py` (pg_restore + validação), `normalize.py` (mapeamento EFOS → types commerce), `publish.py` (transação DELETE+INSERT em `commerce_*`).
6. **E3** — 6 migrations Alembic (0018–0023): `sync_runs`, `sync_artifacts`, `commerce_products`, `commerce_accounts_b2b`, `commerce_orders + commerce_order_items`, `commerce_inventory + commerce_sales_history`, `commerce_vendedores`. Todas as tabelas `commerce_*` com `tenant_id UUID NOT NULL`, `source_system`, `external_id`, `synced_at`, `snapshot_checksum`.
7. **E4** — CLI `python -m integrations.jobs.sync_efos` com flags `--tenant`, `--dry-run`, `--force`; launchd plist `com.jmb.efos-sync.plist` agendado para 16:00 UTC (13:00 BRT); staging DB destruído em bloco `finally`; retenção 7 dias de artifacts.

### Fase 2 — Queries do gestor via commerce_*

8. **E5** — Domínio `commerce/` com `types.py` (8 types) e `repo.py` (`CommerceRepo` com 3 métodos: `relatorio_vendas_representante`, `relatorio_vendas_cidade`, `listar_clientes_inativos`). Sem `service.py` nem `runtime/`. Isolado de outros domínios.
9. **E6** — `AgentGestor` recebe 3 novos tools EFOS com fuzzy match (threshold >= 80) para representante, normalização cidade → UPPERCASE, normalização de mês (`"abril"` → 4). Retorno formatado para WhatsApp (bullets `*`, nunca `•` nem `**markdown**`). `AgentGestor.__init__` aceita `commerce_repo: CommerceRepo | None = None`.
10. **E7** — Suite de testes unitários completa: `pytest -m unit` passa com 0 falhas incluindo os 279 testes anteriores + todos os novos; cobertura >= 80% em `integrations/normalize.py`, `integrations/publish.py`, `commerce/repo.py`, `agents/runtime/agent_gestor.py` (partes novas).
11. **E9** — Testes de regressão: `output/src/tests/regression/test_sprint_8_bugs.py` com `test_b10_*`, `test_b11_*`, `test_b12_*`. Cada teste PASS após hotfix e FAIL se o fix for revertido. Criados **antes** da implementação dos hotfixes (test-first).
11. **E8** — `ARCHITECTURE.md` documenta domínios 5 e 6; `docs/design-docs/index.md` inclui ADRs D025–D029 aprovados.

---

## Assinaturas de funções/métodos principais

### E0-A — agents/repo.py
```python
async def get_by_telefone(
    self,
    tenant_id: str,
    telefone: str,
    session: AsyncSession,
) -> ClienteB2B | None: ...
# SELECT inclui representante_id
```

### E0-B — agents/ui.py (IdentityRouter)
```python
async def _invalidar_redis_conversa(
    redis: Redis,
    tenant_id: str,
    numero: str,
) -> None:
    # delete all keys matching conv:{tenant_id}:{numero}*
```

### E0-C — agents/runtime/*.py (todos os 3 agentes)
```python
def _get_anthropic_client(self, session_id: str) -> AsyncAnthropic:
    # retorna AsyncAnthropic com wrapper Langfuse + session_id
```

### E1 — integrations/types.py
```python
class SyncStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"

class ConnectorCapability(str, Enum):
    CATALOG = "catalog"
    PRICING_B2B = "pricing_b2b"
    CUSTOMERS_B2B = "customers_b2b"
    ORDERS_B2B = "orders_b2b"
    INVENTORY = "inventory"
    SALES_HISTORY = "sales_history"

@dataclass
class SyncRun:
    id: UUID
    tenant_id: str
    connector_kind: str
    capabilities: list[ConnectorCapability]
    started_at: datetime
    finished_at: datetime | None
    status: SyncStatus
    rows_published: int
    error: str | None

@dataclass
class SyncArtifact:
    id: UUID
    tenant_id: str
    connector_kind: str
    artifact_path: str
    artifact_checksum: str
    created_at: datetime
```

### E1 — integrations/config.py
```python
@dataclass
class EFOSBackupConfig:
    ssh_host: str
    ssh_user: str
    ssh_key_path: str
    backup_remote_path: str
    artifact_dir: str
    staging_db_url: str

    @classmethod
    def for_tenant(cls, tenant_id: str) -> "EFOSBackupConfig": ...
    # le secrets via os.getenv(): JMB_EFOS_SSH_HOST, JMB_EFOS_SSH_USER,
    # JMB_EFOS_SSH_KEY_PATH, JMB_EFOS_BACKUP_REMOTE_PATH,
    # JMB_EFOS_ARTIFACT_DIR, JMB_EFOS_STAGING_DB_URL
```

### E1 — integrations/repo.py
```python
class SyncRunRepo:
    async def create(self, run: SyncRun, session: AsyncSession) -> SyncRun: ...
    async def update_status(
        self,
        run_id: UUID,
        status: SyncStatus,
        rows_published: int,
        error: str | None,
        session: AsyncSession,
    ) -> None: ...

class SyncArtifactRepo:
    async def find_by_checksum(
        self,
        tenant_id: str,
        checksum: str,
        session: AsyncSession,
    ) -> SyncArtifact | None: ...
    async def create(self, artifact: SyncArtifact, session: AsyncSession) -> SyncArtifact: ...
```

### E2 — integrations/connectors/efos_backup/acquire.py
```python
async def acquire(config: EFOSBackupConfig) -> tuple[Path, str]:
    # retorna (caminho_local, sha256)
    # usa paramiko.pkey.PKey.from_private_key_file() para SSH (detecta RSA/Ed25519)
    # paths Windows compostos com ntpath / separador \\
    # identifica dump mais recente >= 12:30 do dia (ou D-1 se hora atual < 13:00 BRT)
```

### E2 — integrations/connectors/efos_backup/stage.py
```python
async def stage(artifact_path: Path, staging_db_url: str) -> None:
    # cria efos_staging se nao existir
    # pg_restore --format=c --no-owner --no-privileges -d efos_staging <arquivo>
    # valida presenca das 6 tabelas minimas
    # lanca StagingValidationError se alguma faltar

class StagingValidationError(Exception): ...
```

### E2 — integrations/connectors/efos_backup/normalize.py
```python
def normalize_products(rows: list[dict]) -> list[CommerceProduct]: ...
def normalize_accounts_b2b(rows: list[dict]) -> list[CommerceAccountB2B]: ...
def normalize_orders(
    pedido_rows: list[dict],
    itens_rows: list[dict],
    vendedor_rows: list[dict],
) -> tuple[list[CommerceOrder], list[CommerceOrderItem]]: ...
def normalize_inventory(rows: list[dict]) -> list[CommerceInventory]: ...
def normalize_sales_history(rows: list[dict]) -> list[CommerceSalesHistory]: ...
def normalize_vendedores(rows: list[dict]) -> list[CommerceVendedor]:
    # DISTINCT ON ve_codigo — de-duplica linhas por filial
```

### E2 — integrations/connectors/efos_backup/publish.py
```python
async def publish(
    tenant_id: str,
    products: list[CommerceProduct],
    accounts: list[CommerceAccountB2B],
    orders: list[CommerceOrder],
    order_items: list[CommerceOrderItem],
    inventory: list[CommerceInventory],
    sales_history: list[CommerceSalesHistory],
    vendedores: list[CommerceVendedor],
    session: AsyncSession,
) -> int:
    # transacao unica: DELETE WHERE tenant_id + INSERT
    # rollback total se qualquer INSERT falhar
    # retorna total de rows inseridas
```

### E4 — integrations/jobs/sync_efos.py
```python
async def run_sync(
    tenant_id: str,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    # retorna exit code 0 (OK) ou 1 (erro)
    # bloco finally: DROP efos_staging; apagar artifacts > 7 dias
```

### E5 — commerce/repo.py
```python
class CommerceRepo:
    async def relatorio_vendas_representante(
        self,
        tenant_id: str,
        vendedor_id: str,
        mes: int,
        ano: int,
        session: AsyncSession,
    ) -> dict:
        # retorna: {total_vendido: Decimal, qtde_pedidos: int, clientes: list}

    async def relatorio_vendas_cidade(
        self,
        tenant_id: str,
        cidade: str,  # recebida ja UPPERCASE pelo caller
        mes: int,
        ano: int,
        session: AsyncSession,
    ) -> list[dict]:
        # retorna: [{cliente: str, total: Decimal}, ...]

    async def listar_clientes_inativos(
        self,
        tenant_id: str,
        cidade: str | None,  # None = todas as cidades; UPPERCASE quando presente
        session: AsyncSession,
    ) -> list[dict]:
        # situacao_cliente=2; retorna nome, cnpj, telefone, cidade
```

### E6 — agents/runtime/agent_gestor.py (novos tools)

> **Formato WhatsApp obrigatório:** bullets `* item` ou listas com `*` — nunca `•` nem `**markdown**`. Esta regra vale para todos os retornos dos 3 tools abaixo.

```python
async def relatorio_vendas_representante(
    self,
    nome_rep: str,
    mes: int,
    ano: int,
) -> str:
    # fuzzy match nome_rep contra commerce_vendedores.ve_nome (threshold >= 80)
    # normaliza mes: "abril" -> 4, "mes 4" -> 4, "4" -> 4
    # retorna texto formatado WhatsApp (bullets *, sem markdown)

async def relatorio_vendas_cidade(
    self,
    cidade: str,
    mes: int,
    ano: int,
) -> str:
    # normaliza cidade -> .upper()
    # retorna texto formatado WhatsApp

async def listar_clientes_inativos(
    self,
    cidade: str | None = None,
) -> str:
    # normaliza cidade -> .upper() quando presente; None = todas as cidades
    # retorna texto formatado WhatsApp
```

---

## Dependencias entre entregas (ordem de implementacao)

```
Fase 0 (E0-A, E0-B, E0-C) --- independentes entre si, implementar primeiro
           |
           v
  pytest -m unit (0 falhas novas)
           |
           v
    E3 (migrations 0018-0023) --- tabelas commerce_* e sync_* precisam existir
           |
           v
    E1 (integrations types/config/repo) --- base para E2
           |
           v
    E2 (conector: acquire, stage, normalize, publish) --- depende de E1 e E3
           |
           v
    E4 (CLI sync_efos + launchd plist) --- depende de E1, E2, E3
           |
    E5 (commerce/ types+repo) --- depende de E3; pode rodar em paralelo com E4
           |
           v
    E6 (AgentGestor 3 tools) --- depende de E5
           |
           v
    E7 (testes consolidados) --- depende de todas as entregas anteriores
           |
    E8 (documentacao) --- pode rodar em paralelo com E7
           |
           v
  scripts/smoke_sprint_8.py --- depende de todas as entregas
```

---

## Criterios de aceitacao — Alta (bloqueantes)

**A1. [E0-A] `representante_id` propagado para pedidos B2B**
Teste: `pytest -m unit output/src/tests/unit/agents/test_hotfixes_sprint8.py::test_get_by_telefone_retorna_representante_id`
Evidencia esperada: PASS. Mock de banco retorna `ClienteB2B` com `representante_id` nao-nulo; `ui.py` passa o valor ao criar pedido.

**A2. [E0-A] `ClienteB2B.representante_id: UUID | None` existe no type**
Teste: `python -c "from src.tenants.types import ClienteB2B; import inspect; assert 'representante_id' in inspect.get_annotations(ClienteB2B)"`
Evidencia esperada: exit 0, sem AttributeError.

**A3. [E0-B] Troca de persona invalida Redis**
Teste: `pytest -m unit output/src/tests/unit/agents/test_hotfixes_sprint8.py::test_troca_persona_invalida_redis`
Evidencia esperada: PASS. `redis.delete()` chamado com padrao `conv:{tenant_id}:{numero}*`; segunda mensagem com nova persona nao carrega historico anterior.

**A4. [E0-C] Wrapper Langfuse + session_id + output em todos os agentes**
Teste: `pytest -m unit output/src/tests/unit/agents/test_hotfixes_sprint8.py -k "langfuse"`
Evidencia esperada: PASS. Mock do Langfuse verifica `update_current_observation(output=...)` chamado com valor nao-nulo nos 3 agentes.

**A5. [E0-C] Testes existentes nao quebram apos mudanca em agentes**
Teste: `pytest -m unit output/src/tests/unit/agents/`
Evidencia esperada: 0 falhas (inclui os testes anteriores que injetam `_anthropic` mock).

**A6. [E1] Dominio integrations/ nao importa dominios de negocio**
Teste: `lint-imports`
Evidencia esperada: contrato "`integrations/` nao importa `agents/`, `catalog/`, `orders/`, `tenants/`, `dashboard/`" — 0 violacoes.

**A7. [E1] `SyncRunRepo` e `SyncArtifactRepo` persistem com tenant_id**
Teste: `pytest -m unit output/src/tests/unit/integrations/test_repo.py`
Evidencia esperada: PASS. Mock de session verifica que `tenant_id` esta presente em todos os inserts/updates.

**A8. [E1] `EFOSBackupConfig.for_tenant("jmb")` nao usa valor hardcoded**
Teste: `grep -r "jmbdistribuidora\|suporte\|oci-lablz" output/src/integrations/`
Evidencia esperada: saida vazia (nenhum valor real hardcoded — tudo via `os.getenv()`).

**A9. [E2] `normalize.py` aplica DISTINCT ON ve_codigo para tb_vendedor**
Teste: `pytest -m unit output/src/tests/unit/integrations/test_normalize.py::test_normalize_vendedores_deduplica`
Evidencia esperada: PASS. Input com 2 linhas para mesma `ve_codigo` → output com 1 `CommerceVendedor`.

**A10. [E2] `publish.py` faz rollback total em falha**
Teste: `pytest -m unit output/src/tests/unit/integrations/test_publish.py::test_publish_rollback_em_falha`
Evidencia esperada: PASS. Mock de session com `execute` lancando excecao no terceiro INSERT → `session.rollback()` chamado, nao `session.commit()`.

**A11. [E3] Migrations aplicam sem erro em banco limpo**
Teste: `alembic upgrade head` (no staging)
Evidencia esperada: exit 0; tabelas `sync_runs`, `sync_artifacts`, `commerce_products`, `commerce_accounts_b2b`, `commerce_orders`, `commerce_order_items`, `commerce_inventory`, `commerce_sales_history`, `commerce_vendedores` existem com colunas `tenant_id`, `synced_at`, `snapshot_checksum`.

**A12. [E3] Downgrade reverte sem residuos**
Teste: `alembic downgrade -1` apos `alembic upgrade head`
Evidencia esperada: exit 0; tabela `commerce_vendedores` nao existe apos downgrade de 0023.

**A13. [E4] CLI dry-run nao modifica banco**
Teste: `python -m integrations.jobs.sync_efos --tenant jmb --dry-run` (staging)
Evidencia esperada: exit 0; `SELECT COUNT(*) FROM sync_runs WHERE tenant_id='jmb'` nao aumenta.

**A14. [E4] CLI idempotencia (skip se checksum ja importado)**
Teste: duas execucoes consecutivas no staging com mesmo dump
Evidencia esperada: segunda execucao loga "checksum ja importado, skip"; `SELECT COUNT(*) FROM commerce_products WHERE tenant_id='jmb'` identico apos as duas runs.

**A15. [E4] Staging DB destruido em finally (mesmo em caso de erro)**
Teste: `pytest -m unit output/src/tests/unit/integrations/test_sync_efos.py::test_staging_db_destruido_em_erro`
Evidencia esperada: PASS. Mock de `stage()` lancando excecao → `DROP DATABASE efos_staging` executado no bloco `finally`.

**A16. [E5] Dominio commerce/ nao importa outros dominios**
Teste: `lint-imports`
Evidencia esperada: contrato "`commerce/` nao importa `agents/`, `catalog/`, `orders/`, `tenants/`, `dashboard/`, `integrations/`" — 0 violacoes.

**A17. [E5] Todos os metodos `CommerceRepo` filtram por tenant_id**
Teste: `pytest -m unit output/src/tests/unit/commerce/test_commerce_repo.py`
Evidencia esperada: PASS. Mock de session verifica filtro `tenant_id` em todas as queries (0 violacoes de multi-tenancy).

**A18. [E6] Fuzzy match retorna mesmo representante para variacoes de nome**
Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_gestor_efos.py::test_fuzzy_match_representante`
Evidencia esperada: PASS. `"RONDINELE"`, `"Rondinele Ritter"`, `"rondinele"` → mesmo `ve_codigo`.

**A19. [E6] Normalizacao cidade → UPPERCASE**
Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_gestor_efos.py::test_normalizacao_cidade`
Evidencia esperada: PASS. `"Vinhedo"` → `"VINHEDO"`, `"campinas"` → `"CAMPINAS"`.

**A20. [E6] Normalizacao mes aceita string e int**
Teste: `pytest -m unit output/src/tests/unit/agents/test_agent_gestor_efos.py::test_normalizacao_mes`
Evidencia esperada: PASS. `"abril"` → 4, `"mes 4"` → 4, `"4"` → 4, `4` → 4.

**A21. [E7] Suite unit completa passa sem falhas**
Teste: `pytest -m unit output/src/tests/`
Evidencia esperada: 0 falhas; inclui os 279 testes anteriores + todos os novos.

**A22. [E7] Nenhum teste `@pytest.mark.unit` usa I/O externo**
Teste: `pytest -m unit --timeout=5 output/src/tests/`
Evidencia esperada: 0 falhas por timeout; nenhum acesso real a banco/Redis/SSH em suite unit.

**A_MULTITURN. [E6] Conversa multi-turn com novo tool do gestor + follow-up na mesma sessão**
Teste: staging — enviar mensagem 1 que aciona um dos 3 novos tools do gestor (ex: "relatório do representante Rondinele mês 4"), enviar mensagem 2 de follow-up na mesma sessão (ex: "e o mês 3?"), verificar que ambas as respostas chegam sem erro.
Evidencia esperada: ambas as mensagens recebem resposta sem erro 400 da API Anthropic; a segunda resposta é coerente com o contexto da primeira (histórico de sessão preservado).

**A_TOOL_COVERAGE. [E6] Cobertura ferramentas vs. system prompt do AgentGestor**
Teste: ler system prompt/saudação do AgentGestor após Sprint 8; listar capacidades anunciadas (incluindo as 3 novas: relatório por representante, por cidade, clientes inativos); verificar que cada capacidade tem tool definida em `_TOOLS` E teste que a exercita end-to-end.
Evidencia esperada: zero capacidades anunciadas no system prompt sem tool correspondente e sem teste que a exercite. Verificação via `pytest -m unit output/src/tests/unit/agents/test_agent_gestor_efos.py` + inspeção de `_TOOLS` no código.

**A_REGRESSION. [E9] Testes de regressão para B-10/B-11/B-12 existem e passam**
Teste: `pytest output/src/tests/regression/test_sprint_8_bugs.py -v --tb=short`
Evidencia esperada: 3 testes (`test_b10_*`, `test_b11_*`, `test_b12_*`) todos PASS após os hotfixes. Cada teste FAIL se o respectivo fix for revertido. Arquivo criado test-first, antes da implementação dos hotfixes.
Arquivo obrigatório: `output/src/tests/regression/test_sprint_8_bugs.py`

**A_SMOKE. Smoke gate staging — caminho critico completo com infra real**
Teste: `ssh macmini-lablz "cd ~/ai-sales-agent-claude && python scripts/smoke_sprint_8.py"`
Evidencia esperada: saida `ALL OK`, exit code 0. O script verifica:
  - `GET /health` → 200, versao >= 0.7.0
  - `pytest -m unit` → 0 falhas
  - Tabelas `commerce_products`, `commerce_accounts_b2b`, `sync_runs` existem (alembic upgrade head aplicado)
  - `python -m integrations.jobs.sync_efos --tenant jmb --dry-run` → exit 0
  - `SELECT COUNT(*) FROM commerce_products WHERE tenant_id='jmb'` → >= 100 (apos run completo)
  - `SELECT COUNT(*) FROM sync_runs WHERE tenant_id='jmb' AND status='success'` → >= 1
  - `GET /health` → 200 apos sync (sem regressao no app)

---

## Criterios de aceitacao — Media (nao bloqueantes individualmente)

**M1. Type hints em todas as funcoes publicas das novas camadas**
Teste: `mypy --strict output/src/integrations/ output/src/commerce/`
Evidencia esperada: 0 erros

**M2. Docstrings em todas as funcoes publicas de `integrations/` e `commerce/`**
Teste: inspecao manual + `pydocstyle output/src/integrations/ output/src/commerce/`
Evidencia esperada: cobertura >= 80%

**M3. Cobertura de testes unitarios nas camadas novas (integrations + commerce)**
Teste: `pytest -m unit --cov=output/src/integrations --cov=output/src/commerce --cov-report=term`
Evidencia esperada: cobertura >= 80% de `normalize.py`, `publish.py`, `commerce/repo.py`

**M4. Cobertura de testes unitarios nos hotfixes (agents)**
Teste: `pytest -m unit --cov=output/src/agents --cov-report=term`
Evidencia esperada: cobertura >= 80% das funcoes modificadas em `agents/repo.py`, `agents/ui.py`, `agents/runtime/*.py`

**M5. Zero print() nas novas camadas**
Teste: `grep -r "print(" output/src/integrations/ output/src/commerce/`
Evidencia esperada: saida vazia

**M6. structlog com string posicional (nao `event=` como kwarg)**
Teste: `grep -r "event=" output/src/integrations/ output/src/commerce/` (deve estar vazio)
Evidencia esperada: saida vazia; toda chamada de log usa string posicional como primeiro argumento

**M_INJECT. Injecao de dependencias em AgentGestor sem None**
Teste: `pytest -m staging output/src/tests/staging/agents/test_ui_injection.py`
Evidencia esperada: `commerce_repo` injetado no `AgentGestor` nao e `None` apos construcao em `_process_message`

---

## Threshold de Media

Maximo de falhas de Media permitidas: **1**

Se 2 ou mais criterios de Media falharem, o sprint e reprovado mesmo com todos os de Alta passando.
M_INJECT e tratado como Alta se o `AgentGestor` ficar com `commerce_repo=None` em producao.

---

## Fora do escopo deste contrato

- Conector B2C (www.jmbdistribuidora.com.br)
- Dashboard de sync status ("Ultima sincronizacao EFOS")
- Snapshot versionado com `snapshot_id`
- `product_identity_map` (cross-source SKU reconciliation)
- Migracao de leituras do agente (`catalog/repo.py`, `agents/repo.py`) para `commerce_*`
- Aposentadoria do crawler Playwright
- Suporte a segundo tenant no conector EFOS
- `acquire.py` e `stage.py` testados apenas com `@pytest.mark.integration` (nao executados pelo Evaluator no container)

---

## Ambiente de testes

```
pytest -m unit       → roda no container do Evaluator (sem servicos externos)
                       mocks obrigatorios para banco, Redis, SSH, Anthropic API

pytest -m staging    → roda no macmini-lablz com Postgres + Redis reais, sem WhatsApp real
                       obrigatorio para queries nao-triviais e testes de injecao de deps

pytest -m integration → nao roda no container; requer macmini-lablz com infra completa
                        inclui acquire.py (SSH real) e stage.py (pg_restore real)
```

---

## Gotchas obrigatorios — Generator deve aplicar workaround E testar cada item

| Gotcha | Workaround obrigatorio | Teste de verificacao |
|--------|------------------------|---------------------|
| `tb_vendedor` duplica `ve_codigo` por filial | `DISTINCT ON (ve_codigo)` em `normalize_vendedores()` | `test_normalize_vendedores_deduplica` (unit) |
| Cidades EFOS em UPPERCASE | `.upper()` em tools de cidade antes de passar para `CommerceRepo` | `test_normalizacao_cidade` (unit) |
| `pg_restore` sem `--format=c` falha silenciosamente | Sempre passar `--format=c` em `stage.py` | verificado em `test_stage_flags` (integration) |
| Staging DB acumula schema em segundo restore | DROP/CREATE antes de cada run | `test_staging_db_destruido_em_erro` (unit, mock) |
| paramiko: tipo errado de chave lanca excecao | `PKey.from_private_key_file()` generico | verificado em `test_acquire_ssh_key_type` (integration) |
| structlog: `event=` como kwarg e reservado | String posicional como primeiro argumento | M6 + grep |
| `fpdf2` 2.x: `pdf.output()` retorna bytearray | `bytes(pdf.output())` onde usado | testes existentes (regression) |
| asyncpg + pgvector: `ORDER BY` com vetor retorna 0 rows | Fetch all sem ORDER BY, sort em Python | testes existentes de busca semantica |
| asyncpg + pgvector: `CAST(:param AS vector)` falha | f-string `'{vec}'::vector` | testes existentes de busca semantica |

---

## Histórico de negociação

### Decisão do Evaluator — Rodada 1 (2026-04-27): RECUSADO

3 objeções bloqueantes: A_MULTITURN ausente, A_TOOL_COVERAGE ausente, A_REGRESSION ausente.
Objeção menor: bullets `•` no spec E6 devem ser `*`.

### Revisão do Generator — Rodada 1 (2026-04-27)

Correções aplicadas:

1. Adicionado critério bloqueante `A_MULTITURN` — multi-turn com follow-up no AgentGestor.
2. Adicionado critério bloqueante `A_TOOL_COVERAGE` — cobertura tools vs. system prompt.
3. Adicionado critério bloqueante `A_REGRESSION` — `test_sprint_8_bugs.py` com test_b10/b11/b12.
4. Adicionada entrega `E9` (testes de regressão) à lista de entregas comprometidas.
5. Padronizado bullets para `*` (nunca `•` nem `**markdown**`) em E6 e nota explícita na seção de assinaturas.
6. Status atualizado para "Revisão".

Contrato resubmetido para re-avaliação do Evaluator.

### Decisão do Evaluator — Rodada 2 (2026-04-27): ACEITO

**ACEITO**

Data: 2026-04-27
Avaliador: Evaluator Agent

Verificação das 3 objeções bloqueantes da Rodada 1:

1. A_MULTITURN — PRESENTE. Critério Alta nas linhas 398–400. Teste staging com mensagem 1 (tool call) + mensagem 2 (follow-up na mesma sessão). Evidência objetiva: sem erro 400, coerência de histórico. Verifica o padrão de serialização de ToolUseBlock do Sprint 4.

2. A_TOOL_COVERAGE — PRESENTE. Critério Alta nas linhas 402–405. Verificação via inspeção de _TOOLS + suite pytest -m unit test_agent_gestor_efos.py. Evidência objetiva: zero capacidades anunciadas sem tool e sem teste.

3. A_REGRESSION — PRESENTE. Critério Alta nas linhas 406–409. Nomeia explicitamente test_b10_*, test_b11_*, test_b12_*. Caminho obrigatório output/src/tests/regression/test_sprint_8_bugs.py. Requisito test-first antes dos hotfixes.

Objeção menor (bullets *): CORRIGIDA. Seção E6 usa * em todo lugar; nota explícita "nunca • nem **markdown**" adicionada.

Todos os critérios de Alta são testáveis mecanicamente, cobrem casos de erro, incluem A_SMOKE com infra real, A_MULTITURN, A_TOOL_COVERAGE e A_REGRESSION. Threshold de Média (máximo 1 falha) está explícito. Nenhuma objeção nova encontrada na revisão.

### Correção pontual do Generator (2026-04-27)

A_TOOL_COVERAGE falhou na avaliação de código: os 3 tools EFOS estavam em `_TOOLS` e no
dispatcher mas **ausentes** do `system_prompt_template` de `AgentGestorConfig` em `config.py`.

Correção aplicada: 3 linhas adicionadas em `output/src/agents/config.py` (linhas 226–228):
- `relatorio_vendas_representante_efos`
- `relatorio_vendas_cidade_efos`
- `clientes_inativos_efos`

Diff mínimo verificado — sem alterações colaterais.

### APROVADO pelo Evaluator em 2026-04-27

Todos os critérios de Alta PASS. Critérios de Média: 0 falhas de 7 (threshold 1).
Relatório completo: `artifacts/qa_sprint_8.md`.
