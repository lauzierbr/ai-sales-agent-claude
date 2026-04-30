# Sprint Contract — Sprint 10 — Hotfixes críticos + D030 + F-07 + deprecação catalog

**Status:** Revisao-2
**Data:** 2026-04-29
**Versão alvo:** v0.10.0

---

## Entregas comprometidas

### W1 — Hotfixes não-estruturais

1. **E1** — `agents/runtime/_history.py` (NOVO) com `truncate_preserving_pairs` e `repair_history`; os 3 agentes trocam `messages[-N:]` por chamada compartilhada; recovery chama `repair_history` em vez de `_limpar_historico_redis`. Teste de regressão `test_b26_truncation_integrity.py`.
2. **E2** — Remover `.decode()` de `agents/ui.py:355` quando resultado Redis já é `str` (redis-py >= 5.0).
3. **E3** — `observability/langfuse_anthropic.py` (NOVO) com context manager `call_anthropic_with_langfuse`; os 3 agentes substituem chamada direta a `client.messages.create()` por esta função; generations Langfuse com `usage.input_tokens` e `usage.output_tokens` populados.
4. **E4** — `agents/ui.py` trocando download de URL criptografada por `POST {EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}`; falha → resposta direta via `send_whatsapp_message()` sem passar pelo agente.
5. **E5** — Bloco `## Capacidades de mensagem` adicionado nos 3 system prompts de `agents/config.py`; falha de transcrição manda mensagem amigável fixa direto ao usuário (não via LLM).
6. **E6** — Novo método `ranking_vendedores` em `commerce/repo.py` (SQL agregada com JOIN + LIMIT); nova tool `ranking_vendedores_efos` em `agent_gestor.py`; `ano` com default `datetime.now().year` nas tools de relatório; system prompt com regras de ano e herança de contexto temporal.

### W2 — Foundations D030 (bloqueada por W1)

7. **E7** — Migration `0025_d030_contacts_and_account_extras.py`: tabela `contacts` com todos os campos D030 + índices; `pedidos.account_external_id VARCHAR NULL`; 6 novos campos em `commerce_accounts_b2b`; data migration de 5 contatos existentes em `clientes_b2b` → `contacts` com `origin='manual'`.
8. **E8** — `integrations/connectors/efos_backup/normalize.py` mapeando `cl_contato`, `cl_telefone`, `cl_telefonecelular`, `cl_email`, `cl_nomefantasia`, `cl_dataultimacompra` para `commerce_accounts_b2b`; `publish.py` com UPSERT preservando `commerce_products.embedding` (não DELETE+INSERT cego).
9. **E9** — `ContactRepo` em `agents/repo.py`; IdentityRouter consulta `contacts` antes de `clientes_b2b`; número desconhecido cria `contacts` `origin='self_registered'` `authorized=False`; 2ª mensagem não duplica registro.
10. **E10** — `notify_gestor_pendente` em `agents/service.py`; comando `AUTORIZAR +55...` em `agents/ui.py`; badge de pendentes em `/dashboard/contatos`; throttle 1 notificação por número por 6h; `contacts.authorized_by_gestor_id` preenchido na autorização.
11. **E11** — POST `/dashboard/contatos/novo` faz INSERT em `contacts` (não UPDATE em `clientes_b2b`); listagem `/dashboard/contatos` com UNION contacts + gestores + reps; `/dashboard/clientes` read-only sem botão "Novo Cliente"; `result.rowcount` checado em todos os UPDATEs do dashboard. Teste de regressão `test_b27_contato_dashboard.py`.
12. **E12** — `confirmar_pedido_em_nome_de` aceita `account_external_id`; `pedidos.account_external_id` preenchido quando cliente existe apenas em `commerce_accounts_b2b`; mensagem técnica "ID instável"/"Cliente não encontrado" não aparece. Teste de regressão `test_b28_pedido_efos.py`.

### W3 — F-07 Sync EFOS schedule (paralelo a W2)

13. **E13** — Migration `0026_sync_schedule_and_gestor_role.py`: tabela `sync_schedule` com UNIQUE `(tenant_id, connector_kind)`; seed default `(jmb, efos_backup, diario, '0 13 * * *', true)`; `gestores.role ENUM('admin','gestor') DEFAULT 'gestor'`.
14. **E14** — `integrations/runtime/scheduler.py` (NOVO) com APScheduler; `SyncScheduleRepo` em `integrations/repo.py`; startup hook em `main.py`; Redis lock `sync:efos:{tenant}:running` TTL 30min; `replace_existing=True` para evitar exceção em re-registro; try/except interno no job.
15. **E15** — Rota GET/POST `/dashboard/sync` com template `sync.html`; gate `gestores.role='admin'` retorna 403 para não-admin; Salvar chama `reschedule_job` sem restart; próxima execução calculada via cron; histórico das 10 últimas `sync_runs`.
16. **E16** — Sequência segura: deploy E14+E15 staging → confirmar 1 execução real APScheduler → `launchctl unload` → renomear plist para `.disabled` no repo. Smoke gate confirma job em `scheduler.get_jobs()`.

### W4 — Deprecação catalog legado (bloqueada por E17)

17. **E17** — Migration `0027_commerce_products_embedding.py` com `CREATE EXTENSION IF NOT EXISTS vector` + `ADD COLUMN embedding vector(1536)`; `scripts/migrate_embeddings.py` copiando `produtos.embedding` → `commerce_products.embedding` por `codigo_externo`; produtos sem match ganham embedding via OpenAI (modelo confirmado via `SELECT vector_dims(embedding) FROM produtos LIMIT 1` antes do batch); ≥ 95% das 743 linhas com embedding.
18. **E18** — `catalog/service.py` e `agents/runtime/agent_cliente.py` lendo `commerce_products` em vez de `produtos`; grep `FROM produtos|JOIN produtos` em `output/src/` retorna 0 hits em código de produção.
19. **E19** — Remoção de: crawler (`efos.py`, `efos_http.py`, `base.py`), `enricher.py`, `scheduler_job.py`, template `produtos.html`, rotas `/catalog/painel` e variantes, métodos `aprovar_produto`/`rejeitar_produto`/`listar_produtos`, tipo `StatusEnriquecimento`, `playwright` do `pyproject.toml`; D018/D019 marcados obsoletos em `docs/design-docs/index.md`.
20. **E20** — Migration `0028_drop_produtos_legacy.py` executada apenas com E17+E18+E19 verdes; `SELECT 1 FROM produtos` falha com "relation does not exist".

---

## Critérios de aceitação — Alta (bloqueantes)

### A_VERSION
**Descrição:** `GET /health` retorna `version=0.10.0`. `output/src/__init__.py` tem `__version__ = "0.10.0"`. `main.py` usa `from src import __version__ as APP_VERSION` (sem hardcode).
**Teste:** `curl http://100.113.28.85:8000/health | python -m json.tool | grep version`
**Evidência esperada:** `"version": "0.10.0"`

---

### A_W1_B26_TRUNCATION
**Descrição:** Helper `truncate_preserving_pairs` nunca retorna `tool_result` órfão como primeiro item nem `tool_use` no último item sem `tool_result` imediato. `repair_history` remove apenas pares órfãos, preserva texto user/assistant, descarta tudo só como último recurso. Os 3 agentes usam o helper compartilhado (zero duplicação).
**Teste:**
```bash
pytest output/src/tests/regression/test_b26_truncation_integrity.py -v
```
**Evidência esperada:** 0 falhas.

---

### A_W1_B23_AUDIO
**Descrição:** Download de áudio usa `POST {EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}` (não URL direta do WhatsApp). Falha do endpoint dispara `send_whatsapp_message()` diretamente, sem processar pelo LLM.
**Teste:**
```bash
pytest output/src/tests/unit/agents/test_audio_evolution.py -v
```
**Evidência esperada:** `send_whatsapp_message` chamado em caso de falha; `client.messages.create` NÃO chamado no path de falha.

---

### A_W1_B30_LANGFUSE
**Descrição:** Toda chamada Anthropic dos 3 agentes passa por `call_anthropic_with_langfuse` em `observability/langfuse_anthropic.py`. Função chama `start_generation` e `gen.update(usage=...)` com tokens reais.
**Teste:**
```bash
pytest output/src/tests/unit/observability/test_langfuse_anthropic.py -v
```
**Evidência esperada:** mock confirma `start_generation` e `gen.update` chamados com `usage.input_tokens` e `usage.output_tokens`.

---

### A_W2_E7_MIGRATION
**Descrição:** Migration 0025 aplica sem erro em staging; tabela `contacts` criada com todos os campos D030; `pedidos.account_external_id` presente; `SELECT COUNT(*) FROM contacts WHERE origin='manual'` ≥ 5.
**Teste:**
```bash
ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales \
  -c \"SELECT COUNT(*) FROM contacts WHERE origin='manual'\""
```
**Evidência esperada:** count ≥ 5.

---

### A_W2_E8_UPSERT_PRESERVES_EMBEDDING
**Descrição:** UPSERT em `publish.py` preserva `commerce_products.embedding` existente após sync EFOS; nenhum embedding é destruído por um sync que não regenera embeddings.
**Teste (staging, em sequência):**
```bash
# Passo 1 — baseline
C1=$(ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales -t \
  -c \"SELECT COUNT(*) FROM commerce_products WHERE embedding IS NOT NULL;\"" | tr -d ' ')

# Passo 2 — disparar sync via dashboard
# GET /dashboard/sync → "Rodar agora" (pode ser via curl autenticado ou click manual)

# Passo 3 — aguardar conclusão
ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales -t \
  -c \"SELECT status FROM sync_runs ORDER BY started_at DESC LIMIT 1;\""
# aguardar status='success'

# Passo 4 — verificar preservação
C2=$(ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales -t \
  -c \"SELECT COUNT(*) FROM commerce_products WHERE embedding IS NOT NULL;\"" | tr -d ' ')
[ "$C2" -ge "$C1" ]
```
**Evidência esperada:** `C2 >= C1` — nenhum embedding destruído pelo sync.

---

### A_W2_E9_SELF_REGISTERED
**Descrição:** Número novo cria `contacts` `origin='self_registered'` `authorized=False` em ≤ 1s. 2ª mensagem não duplica registro. Bot NÃO roteia para AgentCliente/AgentRep quando `contacts.authorized=false`.
**Teste:**
```bash
pytest output/src/tests/unit/agents/test_contact_repo.py::test_self_registered_idempotencia -v
pytest output/src/tests/unit/agents/test_service.py::test_nao_roteia_unauthorized -v
```
**Evidência esperada:** 0 falhas.

---

### A_W2_E10_AUTORIZAR
**Descrição:** Gestor recebe notificação WhatsApp com template correto ao aparecer número novo. Comando `AUTORIZAR +55...` seta `contacts.authorized=true` e `authorized_by_gestor_id`. Throttle de 6h funciona: 2ª notificação do mesmo número dentro de 6h não é enviada.
**Teste:**
```bash
pytest output/src/tests/unit/agents/test_service.py::test_notify_throttle_6h -v
pytest output/src/tests/unit/agents/test_service.py::test_autorizar_comando -v
pytest output/src/tests/unit/agents/test_service.py::test_notify_template_contem_candidato -v
```
**Evidência esperada:** 0 falhas; `send_whatsapp_message` chamado apenas 1x em 2 invocações dentro de 6h.

**Teste adicional — template (objeção 6):**
```python
# test_notify_template_contem_candidato
assert "AUTORIZAR" in msg
assert nome_fantasia in msg  # quando candidato EFOS encontrado por CNPJ/telefone
assert cnpj_formatado in msg  # ex: "12.345.678/0001-99"
```

---

### A_W2_E11_DASHBOARD_CONTACTS
**Descrição:** POST `/dashboard/contatos/novo` com `perfil=cliente` cria registro em `contacts` (não UPDATE em `clientes_b2b`). `/dashboard/clientes` sem botão "Novo Cliente" no HTML. Todos os UPDATEs do dashboard têm `result.rowcount` checado (retornam 400 se 0 rows afetadas).
**Teste:**
```bash
pytest output/src/tests/regression/test_b27_contato_dashboard.py -v
```
**Evidência esperada:** 0 falhas; contato aparece em `SELECT * FROM contacts` após POST.

---

### A_W2_E12_PEDIDO_EFOS
**Descrição:** `confirmar_pedido_em_nome_de` aceita `account_external_id` de `commerce_accounts_b2b`; `pedidos.account_external_id` preenchido; nenhuma mensagem "ID instável"/"Cliente não encontrado" para clientes existentes no EFOS.
**Teste:**
```bash
pytest output/src/tests/regression/test_b28_pedido_efos.py -v
```
**Evidência esperada:** 0 falhas; pedido mock criado com `account_external_id` populado.

**Teste adicional — fallback `get_by_id` (objeção 1):**
```python
# test_get_by_id_fallback_commerce_accounts
# mock: clientes_b2b retorna None para o account_id fornecido
# assert: commerce_accounts_b2b é consultado como fallback
```
**Grep evidence:**
```bash
grep -n "commerce_accounts_b2b" output/src/agents/repo.py
# deve mostrar ocorrência dentro de get_by_id (fallback)
```

---

### A_W3_E13_MIGRATION
**Descrição:** Migration 0026 aplica sem erro em staging; tabela `sync_schedule` com seed default `(jmb, efos_backup, diario, '0 13 * * *', true)` presente; `role_enum` com valores 'admin' e 'gestor' registrado no banco.
**Teste:**
```bash
ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales -c \
  \"SELECT preset, cron_expression, enabled FROM sync_schedule \
     WHERE tenant_id='jmb' AND connector_kind='efos_backup'; \
     SELECT enum_range(NULL::role_enum);\""
```
**Evidência esperada:** 1 row `(diario, '0 13 * * *', true)`; enum contém 'admin' e 'gestor'.

---

### A_W3_E14_SCHEDULER
**Descrição:** APScheduler registra jobs no startup com `replace_existing=True`; Redis lock impede sobreposição de sync (TTL 30min); 2º "Rodar agora" dentro de 30min retorna 409; exceção no job não derruba o app.
**Teste:**
```bash
pytest output/src/tests/unit/integrations/test_scheduler.py -v
```
**Evidência esperada:** 0 falhas; teste de lock confirma 409 na 2ª chamada.

---

### A_W3_E15_ADMIN_GATE
**Descrição:** `/dashboard/sync` retorna 403 para gestor sem `role='admin'`; retorna 200 para admin; preset salvo altera `sync_schedule.cron_expression` e próxima execução calculada.
**Teste:**
```bash
pytest output/src/tests/unit/dashboard/test_sync_admin_gate.py -v
```
**Evidência esperada:** 403 com user não-admin; 200 com admin.

---

### A_W4_E17_EMBEDDINGS
**Descrição:** `commerce_products.embedding vector(1536)` presente após migration 0027; ≥ 95% das linhas populadas após `scripts/migrate_embeddings.py --tenant jmb`; `CREATE EXTENSION IF NOT EXISTS vector` precede `ADD COLUMN`; modelo confirmado via `vector_dims` antes do batch (documentado em exec-plan).
**Teste:**
```bash
ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales \
  -c \"SELECT COUNT(*) FROM commerce_products WHERE embedding IS NOT NULL\""
```
**Evidência esperada:** COUNT ≥ 706 (95% de 743).

---

### A_W4_E18_NO_PRODUTOS_READ
**Descrição:** Após E18, grep de SQL e símbolos ORM referenciando `produtos` em código de produção retorna 0 hits; busca semântica usa `commerce_products`.
**Teste:**
```bash
grep -rn "FROM produtos\|JOIN produtos\|from .* import Produto\b\|class Produto\b\|select(Produto)\|query(Produto)" \
  output/src/ --include="*.py" | grep -v test | grep -v "commerce_products"
```
**Evidência esperada:** saída vazia (0 hits). Se restar qualquer referência ao símbolo `Produto`, o Generator deve listá-la explicitamente e justificar (manter com razão clara ou migrar para `CommerceProduct`).

---

### A_W4_E19_REMOCAO
**Descrição:** Artefatos do catalog legado removidos do repositório: crawler EFOS, enricher, scheduler_job, template `produtos.html`, rotas legadas, tipo `StatusEnriquecimento`, e dependência `playwright`.
**Teste:**
```bash
test ! -f output/src/catalog/runtime/crawler/efos.py
test ! -f output/src/catalog/runtime/enricher.py
test ! -f output/src/catalog/templates/produtos.html
! grep -E "^\s*\"?playwright\"?\s*[=:]" output/pyproject.toml
! grep -rn "StatusEnriquecimento" output/src/ --include="*.py"
```
**Evidência esperada:** todos os 5 comandos retornam exit code 0 (ausência confirmada).

---

### A_W4_E20_DROP_CONFIRMADO
**Descrição:** Migration 0028 aplicada; `SELECT 1 FROM produtos` falha; `pytest -m unit` passa após o drop.
**Teste:**
```bash
ssh macmini-lablz "docker exec ai-sales-postgres psql -U app -d ai_sales \
  -c 'SELECT 1 FROM produtos LIMIT 1' 2>&1 | grep 'does not exist'"
pytest -m unit output/src/tests/unit/ -q --tb=short
```
**Evidência esperada:** mensagem `ERROR:  relation "produtos" does not exist`; pytest unit com 0 falhas.

---

### A_BEHAVIORAL_AGENT
**Descrição:** Execução via Chrome DevTools MCP / webhook simulado de todos os cenários abaixo sem erro técnico visível ao usuário:
- Cliente envia áudio real → bot responde com base no texto transcrito (prefixo `Ouvi:` no histórico Redis)
- Cliente: "você ouve áudio?" → bot confirma capacidade
- Gestor faz ≥ 6 tool calls seguidos → histórico mantido; log `historico_corrompido_recovery` ausente
- Gestor: "melhor vendedor de março" → exatamente 1 tool call `ranking_vendedores_efos`; ano 2026 na resposta
- Gestor faz pedido em nome de cliente EFOS → pedido criado, PDF emitido, sem mensagem técnica
- Número desconhecido envia "oi" → recebe "vou avisar o gestor"; gestor recebe notificação WhatsApp
- Gestor responde `AUTORIZAR +55...` → 2ª mensagem do número processada normalmente pelo AgentCliente
**Teste:** protocolo `docs/PRE_HOMOLOGATION_REVIEW.md`
**Evidência esperada:** `artifacts/pre_homolog_review_sprint_10.md` com PASS em todos os cenários de bot.

---

### A_BEHAVIORAL_UI
**Descrição:** 10 rotas do dashboard navegadas via Chrome DevTools MCP / Playwright / Preview MCP. Verificações específicas:
- `/dashboard/contatos`: badge "Pendentes" visível quando há contacts `authorized=false`; criar contato cliente EFOS aparece na listagem
- `/dashboard/clientes`: read-only, sem botão "Novo Cliente" no HTML
- `/dashboard/sync`: salvar preset diferente muda próxima execução; "Rodar agora" cria entry em `sync_runs`
**Teste:** protocolo `docs/PRE_HOMOLOGATION_REVIEW.md`
**Evidência esperada:** `artifacts/pre_homolog_review_sprint_10.md` com PASS nas 10 rotas + itens acima.

---

### A_TOOL_COVERAGE
**Descrição:** Nenhuma capacidade declarada nos system prompts sem tool correspondente; nenhuma tool sem capacidade declarada no prompt.
**Teste:**
```bash
python scripts/check_tool_coverage.py
```
**Evidência esperada:** `capacidade_sem_tool=0 tool_sem_capacidade=0`

---

### A_MULTITURN
**Descrição:** Conversa multi-turn com ≥ 6 tool calls não produz histórico inválido após truncação. `truncate_preserving_pairs` garante que Anthropic API não recebe `tool_result` órfão no início nem `tool_use` sem `tool_result` no fim.
**Teste:**
```bash
pytest output/src/tests/unit/agents/test_runtime.py::test_multiturn_truncation_valid -v
```
**Evidência esperada:** 0 falhas; histórico truncado aceito pela API mockada sem erro 400.

---

### A_SMOKE
**Descrição:** Smoke gate completo contra infra real no macmini-lablz passando todas as 12 verificações.
**Teste:**
```bash
ssh macmini-lablz "cd ~/MyRepos/ai-sales-agent-claude && \
  infisical run --env=staging -- python scripts/smoke_sprint_10.py"
```
**Evidência esperada:** saída `ALL OK`, exit code 0. Verificações:
1. `GET /health` → `version=0.10.0` e `anthropic=ok`
2. `alembic current` em 0028
3. `SELECT COUNT(*) FROM contacts WHERE origin='manual'` ≥ 5
4. `SELECT COUNT(*) FROM commerce_accounts_b2b WHERE telefone IS NOT NULL` ≥ 900
5. `SELECT COUNT(*) FROM commerce_products WHERE embedding IS NOT NULL` ≥ 700
6. `SELECT enabled FROM sync_schedule WHERE tenant_id='jmb'` = true
7. APScheduler `scheduler.get_jobs()` lista job EFOS
8. `SELECT 1 FROM produtos` falha com "does not exist"
9. Trace Langfuse mais recente tem ≥ 1 observation com `type='GENERATION'`, `model` contém `'claude'`, `usage.input_tokens > 0` E `usage.output_tokens > 0` (não apenas `observations.length >= 1`) — sub-critério de A_W1_B30_LANGFUSE
10. GET `/dashboard/contatos` retorna 200 e HTML contém indicação de pendentes
11. GET `/dashboard/clientes` retorna 200 e HTML não contém "Novo Cliente"
12. GET `/dashboard/sync` retorna 200 para admin e 403 para não-admin

---

### A_PRE_HOMOLOG
**Descrição:** Pre-homologation review executado e aprovado (PASS) antes do handoff ao usuário para homologação manual.
**Teste:** Verificar existência de `artifacts/pre_homolog_review_sprint_10.md` com status PASS.
**Evidência esperada:** arquivo existe; contém PASS em 10 rotas do dashboard + todos os 7 cenários de A_BEHAVIORAL_AGENT.

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

### M1 — Type hints completos nos arquivos novos
**Teste:** `mypy output/src/agents/repo.py output/src/commerce/repo.py output/src/observability/langfuse_anthropic.py output/src/integrations/runtime/scheduler.py --ignore-missing-imports`
**Evidência esperada:** 0 erros nos arquivos novos/modificados.

### M2 — Docstrings em funções públicas de Service novos
**Teste:** inspeção manual dos arquivos `observability/langfuse_anthropic.py`, `agents/service.py` (métodos novos), `integrations/runtime/scheduler.py`
**Evidência esperada:** cobertura ≥ 80% das funções públicas novas.

### M3 — Cobertura de testes unitários ≥ 80% nos Services e módulos novos
**Teste:** `pytest -m unit --cov=output/src/agents/service --cov=output/src/observability --cov=output/src/integrations/runtime --cov-report=term-missing`
**Evidência esperada:** cobertura ≥ 80% nas linhas novas.

### M_INJECT — Injeção de dependências sem None em `_process_message`
**Teste:**
```bash
pytest -m staging output/src/tests/staging/agents/test_ui_injection.py -v
```
**Evidência esperada:** nenhum atributo crítico de AgentCliente/AgentGestor/AgentRep é None após construção em `_process_message`.

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1 de 4**

Se todos os 4 critérios de Média falharem simultaneamente, o sprint é reprovado mesmo com todos os de Alta passando.

> **Nota (não-bloqueante):** O threshold pode ser relaxado para **2 de 4** caso A_SMOKE passe 100% (todas as 12 verificações verdes). Decisão do Evaluator no momento da avaliação final; Generator deve documentar no handoff quantos critérios de Média falharam e se A_SMOKE estava 100%.

---

## Sequenciamento obrigatório de implementação

```
W1 (E1, E2, E3, E4, E5, E6 — podem ser paralelos entre si)
    |
    +--> W2 começa APÓS W1 completo
    |    E7 --> E8 --> E9 --> (E10, E11, E12 paralelos)
    |
    +--> W3 pode correr em PARALELO a W2
         E13 --> E14 --> E15 --> E16
              |
              v
         W4 começa APÓS E17 verde + smoke comportamental AgentCliente
         E17 --> E18 --> E19 --> E20
                                  ^
                 Pré-condição obrigatória antes de E20:
                 1. COUNT(commerce_products WHERE embedding IS NOT NULL) >= 706
                 2. grep "FROM produtos" = 0 hits em código produção
                 3. import-linter passa após E19
                 4. Smoke comportamental: "shampoo" -> AgentCliente retorna >= 1 produto
```

---

## Decisões técnicas — a documentar no exec-plan antes da implementação

### DT-1 — Modelo de embedding histórico
Executar antes do batch E17:
```sql
SELECT vector_dims(embedding) FROM produtos LIMIT 1;
```
- Se `1536`: modelo `text-embedding-3-small`; cópia direta da coluna sem custo de regerar.
- Se `3072`: modelo `text-embedding-3-large`; estimar custo de regerar 743 produtos. **Escalar para PO se custo > $5.**
- Resultado e decisão devem ser documentados em `docs/exec-plans/active/sprint-10-hotfixes-d030-f07-deprecacao.md` na seção "Modelo de embedding histórico confirmado".

### DT-2 — Estratégia UPSERT em `publish` para preservar `embedding`
`publish.py` atual faz DELETE+INSERT em `commerce_products`, destruindo `embedding` migrada.
**Solução comprometida:** substituir por:
```sql
INSERT INTO commerce_products (tenant_id, codigo_externo, ...) VALUES (...)
ON CONFLICT (tenant_id, codigo_externo) DO UPDATE SET
  nome = EXCLUDED.nome,
  preco = EXCLUDED.preco,
  -- ... outros campos atualizáveis
  embedding = COALESCE(commerce_products.embedding, EXCLUDED.embedding)
  -- embedding só sobrescrita se a linha existente não tiver embedding
```
Validação no smoke: `COUNT(*) WHERE embedding IS NOT NULL` ≥ 700 após sync simulado.

---

## Ambiente de testes

```
pytest -m unit        → roda no container do Evaluator (sem serviços externos)
pytest -m staging     → roda no macmini-lablz (Postgres + Redis reais), sem WhatsApp real
pytest -m integration → requer macmini-lablz com Evolution API ativa; não roda no Evaluator
```

Binários no staging (todos via docker exec):
- `psql` / `pg_restore`: `docker exec ai-sales-postgres psql ...`
- Python: `~/MyRepos/ai-sales-agent-claude/output/.venv/bin/python`
- Infisical: `/usr/local/bin/infisical`
- PYTHONPATH: `./src` a partir de `output/`

---

## Fora do escopo deste contrato

- Bling adapter (Sprint 11+)
- AnalystAgent D031 (Sprint 11)
- Drop de `clientes_b2b` legado (manter como fallback de leitura por 1-2 sprints)
- Remoção do plist launchd do repo (apenas renomear para `.disabled`)
- Multi-canal Telegram/voice (JSONB preparado; apenas `kind=whatsapp` neste sprint)
- F-06 Painel de Divergências
- Job de cleanup de `self_registered` não autorizados (política PO: manter indefinidamente)
- Correções de B-01, B-10, B-11, B-13 (não estão no sprint_contract)
