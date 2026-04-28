# Sprint Contract — Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp

**Status:** Proposta
**Data:** 2026-04-27
**Versão alvo:** v0.9.0

---

## Entregas comprometidas

### Fase 0 — Hardening staging + hotfixes piloto

1. **E0-A** — Migration 0024: coluna `ficticio BOOLEAN NOT NULL DEFAULT FALSE` em `pedidos`; `Pedido` type recebe campo; INSERT em `orders/repo.py` define `ficticio = os.getenv("ENVIRONMENT") != "production"`; PDF com marca d'água "PEDIDO DE TESTE — NÃO PROCESSAR" quando `ficticio=True`; caption ao gestor prefixado com `"⚠️ TESTE | "` em `agent_cliente.py` e `agent_rep.py`; badge "TESTE" no template `pedidos.html`.

2. **E0-B** — `AgentGestor`: tools antigas `clientes_inativos` e `relatorio_representantes` (baseadas em `clientes_b2b`/`pedidos`) removidas de `_TOOLS` e do system prompt; `clientes_inativos_efos` renomeada para `clientes_inativos` sem sufixo; `relatorio_vendas_representante_efos` e `relatorio_vendas_cidade_efos` mantêm sufixo. Testes unitários atualizados.

3. **E0-C** — Hotfix B-13 nos 3 agentes e em `catalog/repo.py`: quando `query.isdigit()` e `len(query) > 6`, tenta match em `codigo_externo` (ou `external_id`) com `query` completo e com `query[-6:]`. Busca semântica textual não alterada. Testes de regressão em `tests/regression/test_sprint_9_bugs.py`.

### Fase 1 — Migração de leituras para commerce_*

4. **E1a** — `catalog/service.py` implementa lógica de fallback: se `commerce_products` tem ≥ 1 registro para `tenant_id`, busca por código/nome usa `commerce/repo.py`; caso contrário usa `catalog/repo.py` (legado). Busca semântica (pgvector) mantém `catalog.produtos`. `CommerceRepo` recebe método `buscar_produtos_commerce(tenant_id, query, limit)`.

5. **E1b** — `agents/repo.py` método de busca de clientes: tenta `clientes_b2b` primeiro; se 0 resultados, fallback para `commerce_accounts_b2b` via `CommerceRepo`. Resultado normalizado para estrutura compatível com código existente dos agentes.

### Fase 2 — Dashboard: bloco de sincronização EFOS

6. **E2** — Endpoint `GET /dashboard/sync-status` (htmx partial) em `dashboard/ui.py`; `integrations/repo.py` expõe `get_last_sync_run(tenant_id)`; template `dashboard_home.html` recebe bloco com polling `hx-trigger="every 60s"`, exibindo status (badge verde/vermelho), `finished_at` em DD/MM/YYYY HH:MM (BRT) e `rows_published`; fallback "Nunca sincronizado" quando sem registros.

### Fase 3 — Áudio WhatsApp via Whisper

7. **E3** — `agents/ui.py` detecta `messageType == "audioMessage"`; tenta download via `url` (httpx); fallback para decodificação de `base64`; chama `_transcrever_audio(bytes)` com `asyncio.to_thread`; prefixo `"🎤 Ouvi: {transcricao}\n\n"` na resposta; fallback amigável em caso de falha da API Whisper. `OPENAI_API_KEY` via `os.getenv`. Testes em `tests/unit/agents/test_audio_transcricao.py`.

### Infraestrutura

8. **E4** — `scripts/smoke_sprint_9.py` cobre todos os checks do spec; `GET /health` retorna `"version": "0.9.0"`. `pytest -m unit` passa com 0 falhas (incluindo regressões de sprints anteriores).

---

## Critérios de aceitação — Alta (bloqueantes)

### A_VERSION
**GET /health retorna version=0.9.0**
Teste: `curl -s http://100.113.28.85:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['version']=='0.9.0', d"`
Evidência esperada: saída sem erro; `"version": "0.9.0"` no JSON.

---

### A_FICTICIO
**Pedidos criados em staging têm ficticio=True; pedido fictício gera PDF com watermark e caption com prefixo TESTE; relatórios EFOS NÃO incluem pedidos fictícios**
Teste:
1. `pytest -m unit output/src/tests/unit/orders/ -k ficticio` → 0 falhas
2. Inspeção manual: criar pedido em staging → confirmar coluna `ficticio=true` em `SELECT ficticio FROM pedidos ORDER BY created_at DESC LIMIT 1`
3. PDF gerado contém texto "PEDIDO DE TESTE — NÃO PROCESSAR" (verificado no smoke)
4. `pytest -m staging output/src/tests/staging/orders/test_ficticio.py` → 0 falhas
5. Verificar que relatórios filtram pedidos fictícios:
```bash
grep -n "ficticio" output/src/agents/runtime/agent_gestor.py | grep -i "relatorio\|filter\|where\|False"
# Esperado: confirmar que relatorio_vendas_* filtra ficticio=False ou equivalente
```

Evidência esperada: coluna `ficticio` existe na migration, tests pass, PDF watermark visível, grep retorna ≥ 1 linha confirmando filtro `ficticio=False` (ou equivalente) nas queries de relatório.

---

### A_TOOLS_EFOS
**AgentGestor usa tools EFOS quando consultado sobre clientes inativos e representantes; tools antigas ausentes de _TOOLS e system prompt**
Teste:
1. `grep -n "clientes_inativos\b\|relatorio_representantes\b" output/src/agents/runtime/agent_gestor.py` — deve retornar apenas a tool renomeada `clientes_inativos` (EFOS), não a antiga
2. `grep -n "relatorio_representantes" output/src/agents/runtime/agent_gestor.py` → vazio (tool removida)
3. `python scripts/check_tool_coverage.py` → `capacidade_sem_tool=0 tool_sem_capacidade=0`
4. `pytest -m unit output/src/tests/unit/agents/test_agent_gestor.py` → 0 falhas

Evidência esperada: grep retorna resultados esperados; check_tool_coverage limpo; testes pass.

---

### A_REGRESSION
**Testes de regressão para B-13 e E0-B (tools removidas) passam sem falhas**
Teste:
```bash
pytest output/src/tests/regression/test_sprint_9_bugs.py -v
```
Evidência esperada:
- `test_b13_ean_completo_retorna_produto` PASS
- `test_b13_ean_curto_retorna_produto` PASS
- `test_b13_busca_textual_nao_afetada` PASS
- `test_e0b_tool_clientes_inativos_antiga_removida` PASS
- `test_e0b_tool_relatorio_representantes_removida` PASS
- Exit code 0

---

### A_EAN_BUSCA
**Busca por EAN completo (13 dígitos) retorna produto usando query[-6:] como sufixo**
Teste: `pytest -m unit output/src/tests/regression/test_sprint_9_bugs.py -k ean` → 0 falhas
Evidência esperada: mock de `codigo_externo = "148571"` encontrado quando query = `"7898923148571"` (EAN completo).

---

### A_CATALOG_FALLBACK
**catalog/service.py usa commerce_products quando disponível; fallback para produtos quando vazio; decisão de fallback NÃO está em catalog/repo.py**
Teste:
1. `pytest -m unit output/src/tests/unit/catalog/test_service.py -k commerce` → 0 falhas (mock commerce_products com ≥1 registro → busca retorna de commerce; mock vazio → busca retorna de produtos)
2. `pytest -m staging output/src/tests/staging/catalog/test_commerce_fallback.py` → 0 falhas (verifica com dados reais de staging: tenant jmb tem ≥100 produtos em commerce_products)
3. Confirmar localização correta da lógica de fallback:
```bash
grep -n "commerce_products\|CommerceRepo\|buscar_produtos_commerce" output/src/catalog/repo.py
# Esperado: vazio — repo.py não toma a decisão de fallback
```

Evidência esperada: lógica de seleção de fonte verificada unit + staging; grep em `catalog/repo.py` retorna vazio (fallback vive exclusivamente em `catalog/service.py`).

---

### A_AGENTS_CLIENTES_FALLBACK
**agents/repo.py faz fallback para commerce_accounts_b2b quando clientes_b2b retorna 0 resultados**
Teste: `pytest -m unit output/src/tests/unit/agents/test_repo.py -k fallback_commerce` → 0 falhas
Evidência esperada: mock de `clientes_b2b` retornando lista vazia → `CommerceRepo.buscar_clientes_commerce` chamado; mock retornando resultado → `CommerceRepo` não chamado.

---

### A_DASHBOARD_SYNC
**Bloco "Última sincronização EFOS" aparece no dashboard com dados corretos**
Teste:
1. `pytest -m unit output/src/tests/unit/dashboard/test_sync_status.py` → 0 falhas
2. `curl -s -b "session=<token_staging>" http://100.113.28.85:8000/dashboard/sync-status` → HTTP 200 com HTML contendo `status` e `finished_at`
3. Isolamento tenant: query inclui `WHERE tenant_id = :tenant_id`

Evidência esperada: endpoint retorna 200; HTML contém badge de status; query filtrada por tenant (grep em `integrations/repo.py`).

---

### A_AUDIO_TRANSCRICAO
**parse_mensagem detecta audioMessage; transcrição via Whisper prefixada no texto; fallback amigável em falha; asyncio.to_thread obrigatório; nome do arquivo "audio.ogg" passado ao Whisper**
Teste:
1. `pytest -m unit output/src/tests/unit/agents/test_audio_transcricao.py` → 0 falhas (4 cenários: URL, base64, falha API, mensagem texto)
2. `grep -n "OPENAI_API_KEY" output/src/agents/ui.py` → apenas `os.getenv("OPENAI_API_KEY")`, nunca valor literal
3. `grep -rn "sk-" output/src/` → vazio (sem key hardcoded)
4. Verificar gotchas críticos de implementação:
```bash
grep -n "asyncio.to_thread" output/src/agents/ui.py
# Esperado: ≥ 1 ocorrência em _transcrever_audio

grep -n '"audio.ogg"' output/src/agents/ui.py
# Esperado: aparece no tuple passado ao Whisper API
```

Evidência esperada: 4 testes pass; grep de key vazio; `asyncio.to_thread` presente em `_transcrever_audio` (Whisper API é síncrona); `"audio.ogg"` presente no tuple do Whisper API (gotcha da Evolution API — sem esse nome o Whisper rejeita o arquivo).

---

### A_MULTITURN
**Agente conversacional processa múltiplas mensagens em sequência sem perder contexto (multi-turn)**
Teste: `pytest -m unit output/src/tests/unit/agents/test_runtime.py -k multiturn` → 0 falhas
Evidência esperada: sequência de 3+ mensagens do mesmo `jid` resulta em respostas coerentes; estado de conversa mantido via Redis mock; sem `KeyError` ou `AttributeError`.

---

### A_TOOL_COVERAGE
**Ferramentas declaradas em _TOOLS coincidem exatamente com capacidades anunciadas no system prompt (todos os 3 agentes)**
Teste: `python scripts/check_tool_coverage.py`
Evidência esperada: stdout contém `capacidade_sem_tool=0 tool_sem_capacidade=0`; exit code 0.

---

### A_SMOKE
**Smoke gate staging — caminho crítico completo com infra real**
Teste:
```bash
ssh macmini-lablz "cd ~/ai-sales-agent-claude && \
  infisical run --env=staging -- python scripts/smoke_sprint_9.py"
```
Evidência esperada: saída `ALL OK`, exit code 0.

Checks obrigatórios no smoke:
- `GET /health` → `{"version": "0.9.0", "status": "ok"}`
- `commerce_products` tem ≥ 1 produto para tenant `jmb`
- Busca por EAN completo `7898923148571` → retorna produto (B-13)
- Busca por nome de produto → resultado de `commerce_products` (não `produtos`)
- Busca de cliente → resultado de `clientes_b2b` ou `commerce_accounts_b2b`
- `GET /dashboard/sync-status` → HTTP 200 com status e finished_at
- Mock `audioMessage` via webhook local → resposta contém `"🎤 Ouvi:"`
- `SELECT ficticio FROM pedidos WHERE ficticio=true LIMIT 1` → resultado (pedido fictício existe em staging)
- `pytest -m unit` no staging → 0 falhas

---

### A_NO_SECRETS
**Nenhum secret hardcoded no código-fonte**
Teste:
```bash
grep -rn "sk-ant\|sk-proj\|password\s*=\s*['\"]" output/src/
grep -rn "OPENAI_API_KEY\s*=\s*['\"]sk-" output/src/
```
Evidência esperada: ambos os greps retornam vazio (exit code 1 do grep = OK).

---

### A_TENANT_ISOLATION
**Toda nova query filtra por tenant_id**
Teste:
```bash
# Verificar catalog/service.py
grep -n "tenant_id" output/src/catalog/service.py | grep -c "commerce"
# Verificar integrations/repo.py
grep -n "WHERE.*tenant_id\|tenant_id.*=" output/src/integrations/repo.py
# Verificar agents/repo.py (métodos novos)
grep -n "tenant_id" output/src/agents/repo.py | grep -c "commerce"
```
Evidência esperada: todas as novas queries incluem `tenant_id` explicitamente (Evaluator verifica inspeção linha a linha nos arquivos afetados).

---

### A_IMPORT_LINTER
**Nenhuma violação de camadas (import-linter)**
Teste: `cd output && python -m importchecker` ou `lint-imports`
Evidência esperada: 0 violações; especialmente `commerce/repo.py` não importa `catalog/` nem `agents/`.

---

## Critérios de aceitação — Média (não bloqueantes individualmente)

M1. **Type hints** em todas as funções públicas de Service e Repo modificadas/criadas
    Teste: `mypy --strict output/src/catalog/service.py output/src/agents/repo.py output/src/commerce/repo.py output/src/integrations/repo.py output/src/agents/ui.py`
    Evidência esperada: 0 erros

M2. **Docstrings** em todas as funções públicas de Service novas
    Teste: inspeção manual
    Evidência esperada: cobertura ≥ 80% das funções públicas criadas neste sprint

M3. **Cobertura de testes unitários**
    Teste: `pytest -m unit --cov=output/src --cov-report=term`
    Evidência esperada: cobertura ≥ 80% nas funções de Service modificadas (`catalog/service.py`, `agents/ui.py`)

M_INJECT. **Injeção de dependências sem None após sprint (CommerceRepo injetado corretamente)**
    Teste: `pytest -m staging output/src/tests/staging/agents/test_ui_injection.py`
    Evidência esperada: nenhum atributo crítico de AgentCliente, AgentRep ou AgentGestor é None após construção em `_process_message`; especialmente `commerce_repo` não é None no AgentGestor.

---

## Threshold de Média

Máximo de falhas de Média permitidas: **1**

(Se M3 falhar mas M1, M2 e M_INJECT passarem, sprint não é bloqueado. Se 2+ critérios de Média falharem, sprint é reprovado mesmo com todos os de Alta passando.)

---

## Fora do escopo deste contrato

- Geração de embeddings para `commerce_products` (busca semântica continua em `catalog.produtos`)
- Migração de escrita de pedidos para tabelas `commerce_*`
- Suporte a vídeo ou imagem WhatsApp (apenas áudio OGG/Opus neste sprint)
- Respostas de voz (TTS)
- Novo tenant além de `jmb`
- Migração completa do catálogo: fallback legado mantido
- Langfuse traces para chamadas Whisper (OTEL é suficiente)
- Testes de performance / carga
- Avaliação de homologação humana (responsabilidade do usuário após smoke gate)

---

## Notas de implementação para o Evaluator

### B-13 — busca EAN
- A verificação `query.isdigit()` é obrigatória antes de `query[-6:]`
- Os 3 agentes (`agent_cliente.py`, `agent_rep.py`, `agent_gestor.py`) e `catalog/repo.py` devem ter o fix
- O Evaluator deve confirmar que busca textual ("shampoo hidratante") não passou pelo branch EAN

### E0-B — tools EFOS
- O Evaluator deve confirmar via `grep` que `relatorio_representantes` (sem sufixo) não aparece em `_TOOLS`
- `clientes_inativos` (sem sufixo) deve existir e ter implementação baseada em `commerce_vendedores`/`commerce_accounts_b2b`
- `check_tool_coverage.py` deve reportar 0 divergências após renomeação

### E1a — lógica de fallback catalog
- A decisão `commerce` vs `produtos` ocorre em `catalog/service.py`, não em `catalog/repo.py`
- `commerce/repo.py` não deve importar `catalog/` (unidirecional)
- Busca semântica pgvector permanece em `catalog.produtos` — sem alteração

### E3 — áudio Whisper
- `asyncio.to_thread` obrigatório (Whisper API é síncrona)
- Nome do arquivo passado ao Whisper deve ser `"audio.ogg"` (gotcha da Evolution API)
- Fallback `base64` obrigatório (Evolution API frequentemente não envia URL)

### Migration 0024
- `alembic upgrade head` deve ser idempotente
- DEFAULT FALSE não afeta pedidos existentes
- Verificar que `alembic downgrade -1` remove a coluna sem erro

---

## Ambiente de testes

```
pytest -m unit        → roda no container do Evaluator (sem serviços externos)
pytest -m staging     → roda no macmini-lablz com Postgres + Redis reais (sem WhatsApp real)
pytest -m regression  → roda junto com unit no container; cobre regressões de bugs históricos
pytest -m integration → não roda no container; requer macmini-lablz com infra completa
```

Host de staging: `http://100.113.28.85:8000`
Python/venv: `~/ai-sales-agent-claude/.venv/bin/python`
Infisical: `/usr/local/bin/infisical`
PYTHONPATH: `./src` a partir de `output/`
psql/pg_restore: dentro do container Docker `ai-sales-postgres`

---

## Aceite do Evaluator

**ACEITO — Sprint Contract Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp**
**Data:** 2026-04-27
**Avaliador:** Evaluator Agent

Todos os critérios atendem os requisitos de testabilidade.

### Verificação das 3 objeções da rodada anterior

**Objeção 1 — A_FICTICIO (relatorio_vendas_* filtra ficticio=False)**
RESOLVIDA. O critério A_FICTICIO (linhas 56-60) agora inclui o grep obrigatório:
`grep -n "ficticio" output/src/agents/runtime/agent_gestor.py | grep -i "relatorio\|filter\|where\|False"`
com evidência esperada `"grep retorna ≥ 1 linha confirmando filtro ficticio=False"`.
O teste é mecanicamente verificável e bloqueia aprovação se o filtro estiver ausente.

**Objeção 2 — A_CATALOG_FALLBACK (catalog/repo.py esperado vazio)**
RESOLVIDA. O critério A_CATALOG_FALLBACK (linhas 106-110) agora inclui o grep de confirmação:
`grep -n "commerce_products\|CommerceRepo\|buscar_produtos_commerce" output/src/catalog/repo.py`
com evidência esperada `"vazio — repo.py não toma a decisão de fallback"`.
A localização da lógica de fallback em `catalog/service.py` (não `catalog/repo.py`) está explicitamente auditável.

**Objeção 3 — A_AUDIO_TRANSCRICAO (asyncio.to_thread e "audio.ogg" adicionados)**
RESOLVIDA. O critério A_AUDIO_TRANSCRICAO (linhas 141-146) agora inclui ambos os greps:
- `grep -n "asyncio.to_thread" output/src/agents/ui.py` — esperado ≥ 1 ocorrência em `_transcrever_audio`
- `grep -n '"audio.ogg"' output/src/agents/ui.py` — esperado no tuple passado ao Whisper API
A justificativa técnica (Whisper API é síncrona; gotcha da Evolution API) está documentada na evidência esperada.

### Verificação de regressões

Nenhuma regressão introduzida. Todas as seções do contrato original estão intactas:
entregas E0-A/B/C, E1a/b, E2, E3, E4; critérios de Alta A_VERSION…A_IMPORT_LINTER;
critérios de Média M1…M_INJECT; threshold de Média (máx 1 falha); fora do escopo;
notas de implementação; ambiente de testes.

---

## Aprovação final

**APROVADO pelo Evaluator em 2026-04-27**

Re-avaliação pós-correção do A_FICTICIO:
- `agents/repo.py`: 3 queries de relatório filtram `AND ficticio = FALSE` / `AND p.ficticio = FALSE`
- `orders/repo.py`: 2 branches de `listar_por_tenant_status` filtram `AND p.ficticio = FALSE`
- `pytest -m unit`: 374 passed, 0 failed
- Nenhuma regressão introduzida
