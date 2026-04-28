# Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp

**Status:** Em planejamento
**Data:** 2026-04-27
**Pré-requisitos:** Sprint 8 APROVADO (homologação unificada com Sprint 9); banco em migration 0023; commerce_products com ≥ 100 produtos, commerce_accounts_b2b com ≥ 100 clientes

---

## Objetivo

Ao final deste sprint, o sistema lê produtos de `commerce_products` e aceita fallback em `clientes_b2b`/`commerce_accounts_b2b`, exibe o status da última sincronização EFOS no dashboard, e processa mensagens de áudio WhatsApp via transcrição Whisper.

---

## Contexto

Sprint 8 criou o pipeline EFOS e as tabelas `commerce_*`. Agora os agentes ainda lêem de `catalog.produtos` (dados do crawler, potencialmente desatualizados). A Fase 1 migra leituras de produto para `commerce_products` (743 produtos, dados do ERP real), mantendo fallback para o legado. A Fase 2 expõe o status de sync no dashboard do gestor. A Fase 3 implementa entrada por voz (F-02a do backlog), usando Whisper para transcrever áudio OGG/Opus do WhatsApp — o canal primário de uso do piloto JMB.

O hotfix B-13 (busca por EAN completo) é bloqueante para o piloto: clientes digitam o EAN completo mas o banco armazena apenas os 6 últimos dígitos em `codigo_externo`, tornando qualquer busca numérica por produto ineficaz.

---

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| catalog | Repo, Service |
| agents | Repo, Runtime |
| commerce | Repo |
| dashboard | UI (Jinja2 template, novo bloco htmx) |
| agents/ui | Runtime (parse_mensagem), Repo |

---

## Considerações multi-tenant

- **Fase 0 (B-13):** busca EAN é filtrada por `tenant_id` — sem impacto multi-tenant adicional; truncação de sufixo é local (Python), não altera queries.
- **Fase 1 (catalog/repo.py):** fallback para `produtos` ativado quando `COUNT(commerce_products WHERE tenant_id=X) = 0`. Cada tenant tem seu próprio dado isolado por `tenant_id` nas duas tabelas.
- **Fase 1 (agents/repo.py):** fallback `commerce_accounts_b2b` só consultado se `clientes_b2b` não retornou resultado — ambas as queries filtram por `tenant_id`.
- **Fase 2 (dashboard sync):** `SELECT ... FROM sync_runs WHERE tenant_id = :tenant_id` — tenant resolvido via cookie de sessão (D023).
- **Fase 3 (áudio):** processamento de áudio é por mensagem/jid, sem dado multi-tenant armazenado além do histórico normal de conversa.

---

## Secrets necessários (Infisical)

| Variável | Ambiente | Descrição |
|----------|----------|-----------|
| `OPENAI_API_KEY` | development + staging | Já existe (Sprint 0). Usado para Whisper (`openai.audio.transcriptions`) além dos embeddings. |

Nenhum novo secret necessário para este sprint.

---

## Gotchas conhecidos

| Área | Gotcha | Workaround obrigatório |
|------|--------|------------------------|
| WhatsApp / Evolution API | Áudio OGG Opus sem extensão `.ogg` no nome do arquivo | `openai.audio.transcriptions.create(file=("audio.ogg", content_bytes, "audio/ogg"))` — nome do arquivo deve ter extensão `.ogg` mesmo que o conteúdo venha como base64 |
| WhatsApp / Evolution API | Webhook `audioMessage` pode trazer o conteúdo em `base64` (campo `data.message.audioMessage.jpegThumbnail` é thumbnail; áudio real está em `data.message.audioMessage.url` ou em `data.message.base64`) | Tentar primeiro `url` para download via `httpx`; fallback para decodificar `base64` se `url` ausente |
| OpenAI Whisper | `openai.audio.transcriptions.create()` é API síncrona em `openai>=1.0` | Usar `asyncio.to_thread(client.audio.transcriptions.create, ...)` para não bloquear o event loop FastAPI |
| asyncpg + pgvector | `ORDER BY` com expressão vetorial retorna 0 rows silenciosamente | Fetch all sem `ORDER BY`, sort em Python |
| asyncpg + pgvector | `CAST(:param AS vector)` falha em queries de busca | Interpolar f-string `'{vec}'::vector` |
| fpdf2 2.x | `pdf.output()` retorna `bytearray` | `bytes(pdf.output())` |
| SQLAlchemy AsyncSession | `async with factory() as session` não faz auto-commit | `await session.commit()` explícito após toda escrita |

---

## Entregas

### Fase 0-A — Migration 0024: flag `ficticio` em pedidos

**Camadas:** Alembic, Orders (Types, Repo), agents/Runtime, dashboard/UI
**Arquivo(s):**
- `output/alembic/versions/0024_pedidos_ficticio.py` (novo)
- `output/src/orders/types.py` → campo `ficticio: bool = False` em `Pedido`
- `output/src/orders/repo.py` → INSERT inclui `ficticio` baseado em `os.getenv("ENVIRONMENT") != "production"`
- `output/src/orders/runtime/pdf_generator.py` → marca d'água "PEDIDO DE TESTE — NÃO PROCESSAR" quando `ficticio=True`
- `output/src/agents/runtime/agent_cliente.py` → caption da notificação ao gestor inclui `⚠️ TESTE |` quando `ficticio=True`
- `output/src/agents/runtime/agent_rep.py` → idem
- `output/src/dashboard/templates/pedidos.html` → badge `TESTE` na listagem quando `ficticio=True`

**Critérios de aceitação:**
- [ ] `alembic upgrade head` adiciona coluna `ficticio BOOLEAN NOT NULL DEFAULT FALSE` à tabela `pedidos`
- [ ] Quando `ENVIRONMENT != production`, todo pedido criado via bot tem `ficticio=True`
- [ ] PDF de pedido fictício contém texto "PEDIDO DE TESTE — NÃO PROCESSAR" visível (marca d'água ou rodapé)
- [ ] Caption WhatsApp ao gestor: `"⚠️ TESTE | Novo pedido PED-XXXXXXXX | N iten(s) | R$ X,XX"`
- [ ] Dashboard lista pedidos com badge vermelho "TESTE" quando `ficticio=True`
- [ ] Pedidos com `ficticio=True` **não** são incluídos nos relatórios EFOS do gestor (tools `relatorio_vendas_*`)
- [ ] `pytest -m unit` passa

---

### Fase 0-B — AgentGestor: substituir tools antigas pelas EFOS

**Camadas:** Runtime (agents)
**Arquivo(s):**
- `output/src/agents/runtime/agent_gestor.py`
- `output/src/agents/config.py` → system prompt atualizado

**Contexto:** Sprint 8 adicionou tools EFOS (`clientes_inativos_efos`, `relatorio_vendas_representante_efos`) ao lado das antigas (`clientes_inativos`, `relatorio_representantes`). O Claude escolhe as antigas porque têm nomes mais genéricos. As antigas retornam dados de staging (fictícios); as novas retornam dados reais do EFOS.

**Critérios de aceitação:**
- [ ] `clientes_inativos` (antiga, baseada em `clientes_b2b`) **removida** de `_TOOLS` e do system prompt
- [ ] `relatorio_representantes` (antiga, baseada em `pedidos` últimos 30 dias) **removida** de `_TOOLS` e do system prompt
- [ ] `clientes_inativos_efos` renomeada para `clientes_inativos` (sem sufixo) em `_TOOLS` e system prompt
- [ ] `relatorio_vendas_representante_efos` permanece com nome atual (sufixo mantém clareza)
- [ ] `relatorio_vendas_cidade_efos` permanece com nome atual
- [ ] Gestor pergunta "lista de clientes inativos" → bot usa `clientes_inativos` (EFOS) → retorna clientes reais
- [ ] Gestor pergunta "quais os representantes" → bot usa `relatorio_vendas_representante_efos` → retorna dados de `commerce_vendedores`
- [ ] Testes unitários atualizados para refletir remoção das tools antigas
- [ ] `pytest -m unit` passa

---

### Fase 0-C — Hotfix B-13: busca por EAN completo

**Camadas:** Repo (catalog, agents)
**Arquivo(s):**
- `catalog/repo.py` → `_buscar_produtos()`
- `agents/runtime/agent_cliente.py` → linha ~633 `_buscar_produtos()`
- `agents/runtime/agent_rep.py` → `_buscar_produtos()`
- `agents/runtime/agent_gestor.py` → `_buscar_produtos()` (se existente)
- `tests/regression/test_ean_busca.py` (novo)

**Critérios de aceitação:**
- [ ] Se `query` é numérica e `len(query) > 6`, a função tenta match em `codigo_externo` com `query` completo E com `query[-6:]` (últimos 6 dígitos)
- [ ] O match exato por `query[-6:]` só é realizado quando `query` é inteiramente dígitos (`query.isdigit()`)
- [ ] Busca semântica não é afetada (comportamento atual preservado para queries textuais)
- [ ] `tests/regression/test_ean_busca.py` cobre: EAN completo (13 dígitos) retorna produto, EAN curto (6 dígitos) retorna produto, busca textual não é afetada
- [ ] `pytest -m unit` passa sem regressão

---

### Fase 1a — catalog/repo.py: leituras de produtos de commerce_products

**Camadas:** Repo (catalog), Repo (commerce)
**Arquivo(s):**
- `catalog/repo.py` → método(s) de busca de produtos (busca semântica e por código)
- `commerce/repo.py` → `buscar_produtos_commerce(tenant_id, query, limit)` (novo método)

**Critérios de aceitação:**
- [ ] `catalog/repo.py` verifica `COUNT(commerce_products WHERE tenant_id=X)` antes de decidir fonte
- [ ] Se `commerce_products` tem ≥ 1 registro para o tenant → busca nessa tabela (lookup por `external_id`, `name`, campos textuais)
- [ ] Se `commerce_products` está vazio para o tenant → fallback para tabela `produtos` (comportamento atual)
- [ ] Busca semântica (pgvector) continua usando tabela `produtos` para embeddings (commerce_products não tem embedding neste sprint — fora do escopo)
- [ ] Busca por código/nome usa `commerce_products` quando disponível
- [ ] Tenant isolation: todas as queries filtram por `tenant_id`
- [ ] Nenhuma violação de import-linter (catalog/repo.py pode importar commerce/repo.py via camada Repo → Repo mesmo domínio? **Não** — catalog e commerce são domínios separados; a lógica de decisão fica em `catalog/service.py` que chama ambos os repos)
- [ ] `pytest -m unit` passa

**Nota arquitetural:** Para não violar D027 (commerce/ não importa outros domínios), a lógica de fallback deve residir em `catalog/service.py`, que chama `CatalogRepo` e `CommerceRepo` independentemente. O `catalog/service.py` pode importar `commerce/repo.py` pois ambos são camada Repo — mas a camada Service de catalog pode importar Repo de outro domínio (catalog/service.py está na camada Service, commerce/repo.py na camada Repo, e Service pode importar Repo). Enforçar que commerce/repo.py não importa catalog/.

---

### Fase 1b — agents/repo.py: fallback de clientes para commerce_accounts_b2b

**Camadas:** Repo (agents), Repo (commerce)
**Arquivo(s):**
- `agents/repo.py` → método de busca de clientes
- `commerce/repo.py` → `buscar_clientes_commerce(tenant_id, query)` (novo método ou ampliação)

**Critérios de aceitação:**
- [ ] Busca de clientes em `agents/repo.py` primeiro consulta `clientes_b2b`
- [ ] Se `clientes_b2b` retorna 0 resultados → tenta `commerce_accounts_b2b` com mesma query (fallback, não substituição)
- [ ] Se `clientes_b2b` retorna resultados → não consulta `commerce_accounts_b2b`
- [ ] Resultado retornado tem mesma estrutura independente da fonte (compat com código existente dos agentes)
- [ ] Tenant isolation em ambas as queries
- [ ] `pytest -m unit` passa

---

### Fase 2 — Dashboard: bloco "Última sincronização EFOS"

**Camadas:** UI (dashboard), Repo (integrations/commerce)
**Arquivo(s):**
- `dashboard/ui.py` (ou `tenants/ui.py`) → novo endpoint `GET /dashboard/sync-status` (htmx partial)
- `integrations/repo.py` → `get_last_sync_run(tenant_id)` (já pode existir — verificar)
- `dashboard/templates/dashboard_home.html` (ou equivalente) → novo bloco htmx

**Critérios de aceitação:**
- [ ] Bloco "Última sincronização EFOS" aparece na página principal do dashboard
- [ ] Exibe: status (`success` → badge verde / `error` → badge vermelho), `finished_at` formatado como DD/MM/YYYY HH:MM (fuso BRT), `rows_published` (produtos publicados)
- [ ] Se não há nenhum registro em `sync_runs` para o tenant → exibe "Nunca sincronizado"
- [ ] Dados carregados via htmx polling `hx-trigger="every 60s"` (consistente com padrão do dashboard)
- [ ] Query: `SELECT status, finished_at, rows_published FROM sync_runs WHERE tenant_id = :tid ORDER BY started_at DESC LIMIT 1`
- [ ] Tenant isolation: query filtra por `tenant_id` extraído do cookie de sessão
- [ ] Sem violação de import-linter: dashboard/ui.py pode importar integrations/repo.py (UI → Repo é permitido na hierarquia de camadas)
- [ ] `pytest -m unit` passa para o endpoint

---

### Fase 3 — Áudio WhatsApp via Whisper

**Camadas:** Runtime (agents/ui.py — parse_mensagem)
**Arquivo(s):**
- `agents/ui.py` → `parse_mensagem()` + nova função `_transcrever_audio()`
- `tests/unit/agents/test_audio_transcricao.py` (novo)

**Critérios de aceitação:**
- [ ] `parse_mensagem()` detecta `messageType == "audioMessage"` no payload Evolution API
- [ ] Tenta baixar o arquivo via `url` em `data.message.audioMessage.url` com `httpx.AsyncClient`; se URL ausente ou falha HTTP, decodifica `data.message.base64`
- [ ] Chama `_transcrever_audio(audio_bytes: bytes) -> str` que usa `asyncio.to_thread(openai_sync_client.audio.transcriptions.create, model="whisper-1", file=("audio.ogg", audio_bytes, "audio/ogg"))`
- [ ] `OPENAI_API_KEY` carregado de Infisical via `os.getenv("OPENAI_API_KEY")`
- [ ] Transcrição substitui o campo `text` da mensagem retornada por `parse_mensagem()`
- [ ] Agente prefixa a resposta com `"🎤 Ouvi: {transcricao}\n\n"` antes de processar normalmente
- [ ] Se transcrição falha (APIError, timeout) → agente responde com mensagem de fallback amigável: `"Desculpe, não consegui entender o áudio. Pode digitar sua mensagem?"`
- [ ] Mensagens não-áudio (`messageType != "audioMessage"`) não são afetadas
- [ ] `OPENAI_API_KEY` nunca hardcoded; variável carregada via `os.getenv`
- [ ] `tests/unit/agents/test_audio_transcricao.py` cobre: mock `audioMessage` com URL → transcrição chamada com bytes corretos; mock `audioMessage` com base64 → decodificação + transcrição; falha de transcrição → mensagem de fallback; mensagem de texto → parse_mensagem não alterado
- [ ] `pytest -m unit` passa

---

## Versão alvo

`v0.9.0` (convenção: 0.N.0 onde N = número do sprint).
Critério `A_VERSION` obrigatório no contrato: `GET /health` retorna `"version": "0.9.0"`.

---

## Ambiente de execução

Este sprint não introduz novos CLIs fora do FastAPI. O pipeline EFOS (`sync_efos`) já existe desde Sprint 8.

| Componente | Localização no macmini-lablz |
|------------|------------------------------|
| Python / venv | `~/ai-sales-agent-claude/.venv/bin/python` |
| Infisical | `/usr/local/bin/infisical` |
| PYTHONPATH | `./src` (a partir de `output/`) |
| psql / pg_restore | Dentro do Docker container `ai-sales-postgres` |

---

## Mapeamento de campos confirmados

### commerce_products (já populada pelo Sprint 8)

| Campo | Tipo | Origem EFOS | Notas |
|-------|------|-------------|-------|
| `id` | UUID PK | gerado | |
| `tenant_id` | TEXT | `jmb` | |
| `external_id` | TEXT | `it_codigo` | últimos 6 dígitos do EAN |
| `name` | TEXT | `it_nome` | |
| `price` | NUMERIC | `it_precovenda` | |
| `ean` | TEXT | `it_codigobarra` | EAN completo (13 dígitos) — **confirmar se coluna existe** |

> Atenção: `it_codigobarra` foi mapeado no Sprint 8 para `ean` em `commerce_products`? Verificar migration 0018–0023. O hotfix B-13 pode usar `ean` se existir, ou derivar de `external_id` com padding.

### commerce_accounts_b2b (já populada pelo Sprint 8)

| Campo | Tipo | Origem EFOS | Notas |
|-------|------|-------------|-------|
| `id` | UUID PK | gerado | |
| `tenant_id` | TEXT | `jmb` | |
| `external_id` | TEXT | `cl_codigo` | |
| `name` | TEXT | `cl_nome` | |
| `cnpj` | TEXT | `cl_cnpjcpfrg` | |
| `city` | TEXT | `cl_cidade` | UPPERCASE |
| `status` | INT | `cl_situacaocliente` | 1=ativo / 2=inativo |
| `vendedor_id` | TEXT | `cl_vendedori` | |

### sync_runs

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | TEXT | |
| `status` | TEXT | `'success'` / `'error'` |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ | |
| `rows_published` | INT | |

---

## Critério de smoke staging (obrigatório)

Script: `scripts/smoke_sprint_9.py`

O script verifica contra infra real (macmini-lablz, `http://100.113.28.85:8000`):

- [ ] `GET /health` → `{"version": "0.9.0", "status": "ok"}`
- [ ] `pytest -m unit` no servidor de staging → 0 falhas
- [ ] `commerce_products` tem ≥ 1 produto para tenant `jmb`
- [ ] `catalog/service.py`: busca de produto via nome retorna resultado de `commerce_products` (não `produtos`) quando disponível
- [ ] `agents/repo.py`: busca de cliente via nome retorna resultado (de `clientes_b2b` ou fallback `commerce_accounts_b2b`)
- [ ] `GET /dashboard/sync-status?tenant_id=jmb` (ou equivalente htmx partial) → HTTP 200, contém `status` e `finished_at`
- [ ] Smoke de áudio: POST mock `audioMessage` ao webhook local → agente responde com prefixo `"🎤 Ouvi:"` (usando mock do Whisper em staging)
- [ ] B-13: busca por EAN completo (ex: `7898923148571`) → retorna produto (verifica que `query[-6:]` funciona)

Execução: `python scripts/smoke_sprint_9.py` → saída `ALL OK`

---

## Checklist de homologação humana

Ver `docs/exec-plans/active/homologacao_sprint-9.md` para checklist unificado Sprint 8 + Sprint 9.

---

## Decisões pendentes

Nenhuma. Todas as decisões arquiteturais estão cobertas por ADRs existentes (D025–D029).

**Verificação pendente pelo Generator:** confirmar se coluna `ean` existe em `commerce_products` (migration 0018–0023). Se não existir, a busca por EAN completo no B-13 deve usar `external_id` com `query[-6:]` e não há coluna separada para EAN.

---

## Fora do escopo

- Geração de embeddings para `commerce_products` (busca semântica continua em `catalog.produtos`)
- Migração de escrita de pedidos para tabelas commerce (pedidos continuam em `orders/`)
- Suporte a vídeo ou imagem WhatsApp (apenas áudio OGG/Opus)
- Respostas de voz (TTS) — apenas transcrição de entrada
- Novo tenant além de JMB
- Migração completa do catálogo de `produtos` para `commerce_products` (fallback mantido)
- Langfuse traces para chamadas Whisper (OTEL é suficiente)

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| `commerce_products` não tem coluna `ean` separada | Médio | Baixo | hotfix B-13 usa `external_id[-6:]` como sufixo — funciona independente de `ean` |
| Evolution API envia áudio sem URL (apenas base64) | Alto | Baixo | Implementar fallback base64 obrigatório na Fase 3 |
| Whisper API indisponível em staging (sem key real) | Médio | Médio | Mock no smoke gate; homologação real com key de produção |
| import-linter viola D027 ao fazer catalog/service.py → commerce/repo.py | Baixo | Alto | Verificar contracts em pyproject.toml antes de submeter; adicionar contrato explícito se necessário |
| Coluna `rows_published` não existe em `sync_runs` | Baixo | Baixo | Verificar migration 0023; se ausente, exibir `row_count` ou omitir |

---

## Handoff para o próximo sprint

- Sprint 9 deixa infraestrutura de leitura de `commerce_products` pronta; Sprint 10+ pode adicionar embeddings às tabelas commerce para busca semântica unificada.
- A integração Whisper abre caminho para outros modelos de áudio (speaker diarization, idioma automático).
- Fallback `clientes_b2b → commerce_accounts_b2b` pode ser invertido ou unificado em sprint de migração de dados futura.
