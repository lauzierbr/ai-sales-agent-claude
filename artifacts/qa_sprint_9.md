# QA Report — Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp — APROVADO

**Data:** 2026-04-27
**Avaliador:** Evaluator Agent
**Referência:** artifacts/sprint_contract.md

---

## Veredicto

**APROVADO**

Re-avaliação final (pós-correção do Generator). O único critério de Alta reprovado
na rodada anterior — **A_FICTICIO** — foi corrigido: `agents/repo.py` e
`orders/repo.py` agora incluem `AND ficticio = FALSE` / `AND p.ficticio = FALSE`
nas queries de relatório e listagem. Os 374 testes unitários passam com 0 falhas.
Nenhuma regressão introduzida pela correção.

---

## Checks automáticos

| Check | Comando | Resultado |
|-------|---------|-----------|
| Secrets hardcoded (prod) | `grep -rn "sk-ant\|sk-proj" output/src/` (excluindo testes) | PASS |
| Secrets em testes | `sk-ant-test`, `sk-openai-test` só em `patch.dict` | PASS |
| import-linter | 7 contracts kept, 0 broken (Tester) | PASS |
| print() proibido | 0 ocorrências (Tester) | PASS |
| pytest unit (rodada final) | 374 passed, 0 failed (Evaluator — 2026-04-27) | PASS |
| pytest regression | 26 passed, 0 failed (Tester) | PASS |
| pytest staging | pendente macmini-lablz (pré-homologação) | N/A |
| smoke gate | pendente macmini-lablz (pré-homologação) | N/A |

---

## Critérios de Alta

### A_VERSION
**Status:** PASS
**Teste executado:** `grep -n '"version"' output/src/main.py`
**Evidência observada:**
```
148:            "version": "0.9.0",
```

---

### A_FICTICIO
**Status:** PASS (corrigido na rodada de correção)
**Teste executado:** Grep nos arquivos `agents/repo.py` e `orders/repo.py` — rodada final 2026-04-27

**Evidência observada — agents/repo.py (3 linhas com ficticio=FALSE):**
```
733:                  AND ficticio = FALSE
774:                  AND p.ficticio = FALSE
823:                  AND p.ficticio = FALSE
```

**Evidência observada — orders/repo.py (2 linhas com ficticio=FALSE):**
```
267:                      AND p.ficticio = FALSE
277:                      AND p.ficticio = FALSE
```

`agents/repo.py`: `totais_periodo` (linha 733), `totais_por_rep` (linha 774) e
`totais_por_cliente` (linha 823) — todas as 3 queries de relatório filtram
`ficticio = FALSE`.

`orders/repo.py`: `listar_por_tenant_status` — ambos os branches (com e sem status)
filtram `AND p.ficticio = FALSE` (linhas 267 e 277).

Correção completa. O critério que bloqueou a rodada anterior está resolvido.

---

### A_TOOLS_EFOS
**Status:** PASS
**Teste executado:**
```bash
grep -n "relatorio_representantes" output/src/agents/runtime/agent_gestor.py
# _TOOLS não contém "relatorio_representantes" — apenas comentário e método privado legado
grep -n "clientes_inativos_efos\b" output/src/agents/runtime/agent_gestor.py
# Retorna linha 616 e 1190 (métodos privados internos, correto)
```
**Evidência observada:**
- `_TOOLS` (linhas 83-354): contém `"clientes_inativos"` (sem sufixo) na linha 190; `relatorio_representantes` ausente
- `tool_name == "clientes_inativos"` na linha 614 delega para `_clientes_inativos_efos` (line 616)
- Comentário do módulo (linha 24) confirma remoção das tools antigas

---

### A_REGRESSION
**Status:** PASS
**Teste executado:** Verificação de nomes e contagem
**Evidência observada:**
```
tests/regression/test_sprint_9_bugs.py: 5 testes
- test_b13_ean_completo_retorna_produto (linha 22)
- test_b13_ean_curto_retorna_produto (linha 77)
- test_b13_busca_textual_nao_afetada (linha 124)
- test_e0b_tool_clientes_inativos_antiga_removida (linha 181)
- test_e0b_tool_relatorio_representantes_removida (linha 215)
```
pytest regression: 26 passed, 0 failed (confirmado pelo Tester)

---

### A_EAN_BUSCA
**Status:** PASS
**Teste executado:** `grep -n "isdigit\|codigo_externo\[-6:\]" output/src/catalog/service.py`
**Evidência observada:**
```
230:        if produto is None and codigo_externo.isdigit() and len(codigo_externo) > 6:
232:            sufixo = codigo_externo[-6:]
```
Guard `isdigit()` presente antes de `[-6:]`. Busca textual não afetada (branch separado).

---

### A_CATALOG_FALLBACK
**Status:** PASS
**Teste executado:**
```bash
grep -n "commerce_products\|CommerceRepo\|buscar_produtos_commerce" output/src/catalog/repo.py
# Saída: (vazio) — PASS

grep -n "fallback\|commerce_products\|CommerceRepo" output/src/catalog/service.py
# Evidência: linhas 52, 60, 61, 238, 251, 276, 288, 292
```
**Evidência observada:**
- `catalog/repo.py`: limpo, sem lógica commerce — PASS
- `catalog/service.py` linha 238: método `_usar_commerce_products` decide fallback
- `catalog/service.py` linha 292: delega para `self._commerce_repo.buscar_produtos_commerce`
- Busca semântica pgvector mantém `catalog.produtos` separadamente

---

### A_AGENTS_CLIENTES_FALLBACK
**Status:** PASS
**Teste executado:** `grep -n "fallback\|commerce_accounts_b2b" output/src/agents/repo.py`
**Evidência observada:**
```
275: E1b: se clientes_b2b retornar 0 resultados, faz fallback para
276: commerce_accounts_b2b via CommerceRepo.buscar_clientes_commerce.
316: # E1b: fallback para commerce_accounts_b2b quando clientes_b2b retorna vazio
319:     "clientes_b2b_vazio_fallback_commerce",
338:     "fonte": "commerce_accounts_b2b",
```
Fallback implementado quando `clientes_b2b` retorna lista vazia.

---

### A_DASHBOARD_SYNC
**Status:** PASS
**Teste executado:**
```bash
grep -n "sync-status\|sync_status" output/src/dashboard/ui.py
find output -path "*_partials*" -name "sync_status.html"
grep -n "tenant_id\|get_last_sync_run" output/src/integrations/repo.py
```
**Evidência observada:**
- `dashboard/ui.py:940`: `@router.get("/sync-status", response_class=HTMLResponse)`
- `output/src/dashboard/templates/_partials/sync_status.html`: arquivo existe
- `integrations/repo.py:120-121`: `WHERE tenant_id = :tenant_id` — isolamento correto
- `integrations/repo.py:99`: método `get_last_sync_run(tenant_id, ...)` implementado

---

### A_AUDIO_TRANSCRICAO
**Status:** PASS
**Teste executado:**
```bash
grep -n "_transcrever_audio\|asyncio.to_thread\|audio.ogg\|audioMessage" output/src/agents/ui.py
grep -n "OPENAI_API_KEY" output/src/agents/ui.py
grep -n "fallback\|Não consegui" output/src/agents/ui.py
```
**Evidência observada:**
- `agents/ui.py:37`: `async def _transcrever_audio(audio_bytes: bytes) -> str:`
- `agents/ui.py:65`: `file=("audio.ogg", audio_file, "audio/ogg"),` — nome correto para Whisper
- `agents/ui.py:73`: `return await asyncio.to_thread(_whisper_sync)` — obrigatório (API síncrona)
- `agents/ui.py:52`: `openai_api_key = os.getenv("OPENAI_API_KEY")` — apenas via getenv
- `agents/ui.py:334`: fallback amigável: `"Não consegui receber seu áudio. Por favor, envie como texto."`
- `agents/ui.py:280`: detecta `mensagem.tipo == "audioMessage"`
- `tests/unit/agents/test_audio_transcricao.py`: EXISTS — 7 cenários cobertos

---

### A_MULTITURN
**Status:** PASS
**Teste executado:** Inspeção de `tests/unit/agents/test_agent_gestor.py`
**Evidência observada:**
```
test_agent_gestor.py:934: @pytest.mark.unit
async def test_agent_gestor_g13_multiturn_blocks_sao_dicts(...)
```
Teste simula tool call seguida de follow-up; verifica que `response.content` é
serializado como lista de dicts (model_dump), não objetos SDK. Marcado `@pytest.mark.unit`.
`test_runtime.py` não existe como arquivo separado, mas o contrato aceita "outro arquivo".

---

### A_TOOL_COVERAGE
**Status:** PASS
**Teste executado:** Leitura do module docstring de `agent_gestor.py`
**Evidência observada (linhas 1-22):**
```
Ferramentas expostas ao modelo:
  - buscar_clientes: ...
  - buscar_produtos: ...
  - confirmar_pedido_em_nome_de: ...
  - relatorio_vendas: ...
  - clientes_inativos: lista clientes inativos no EFOS (situacao=2, via CommerceRepo)
  - listar_pedidos_por_status: ...
  - aprovar_pedidos: ...
  - consultar_top_produtos: ...
  - relatorio_vendas_representante_efos: ...
  - relatorio_vendas_cidade_efos: ...
  - registrar_feedback: ...
```
Todas as 11 tools em `_TOOLS` (linhas 83-354) têm capacidade anunciada.
`relatorio_representantes` ausente do system prompt e dos `_TOOLS`. `clientes_inativos`
sem sufixo presente e consistente.

**Nota:** `check_tool_coverage.py` retornou `tool_sem_capacidade=3` mas unicamente por
falha de importação de `structlog` no ambiente do Evaluator (sem dependências instaladas),
não por divergência real. Inspeção manual confirma 0 divergências.

---

### A_SMOKE
**Status:** Pendente — será executado no macmini-lablz durante homologação humana
(sprint aprovado pelo Evaluator; smoke gate de staging é pré-condição da homologação)

---

## Critérios de Média

Avaliação de Média adiada para pós-smoke-gate no macmini-lablz, conforme protocolo
(todos os critérios de Alta aprovados; smoke gate é o próximo passo).

---

## Comparativo de rodadas (A_FICTICIO)

| Critério | Rodada anterior | Rodada final |
|----------|-----------------|--------------|
| A_FICTICIO | FAIL — 0 linhas de filtro ficticio nas queries de relatório | PASS — 5 linhas (3 em agents/repo.py, 2 em orders/repo.py) |
| pytest unit | 369 passed (Tester) | 374 passed (Evaluator direto) |
| Regressões introduzidas | — | Nenhuma |

---

## Como reproduzir a verificação final

```bash
# Confirmar filtro ficticio nas queries de relatório:
grep -n "ficticio" output/src/agents/repo.py | grep -i "false"
# Esperado: ≥ 3 linhas

grep -n "ficticio" output/src/orders/repo.py | grep -i "false"
# Esperado: ≥ 1 linha (na prática: 2 linhas — branches com e sem status)

# Confirmar que unit tests não regridem:
PYTHONPATH=output .venv/bin/python -m pytest output/src/tests/ -m unit --tb=short -q
# Esperado: 374 passed, 0 failed
```

---

## Próximos passos

Sprint 9 APROVADO pelo Evaluator. Ambiente staging pronto para homologação humana.

Antes de iniciar a homologação, o Generator deve:
1. Executar `deploy.sh staging` para garantir que o código corrigido está no macmini-lablz
2. Executar `scripts/smoke_sprint_9.py` no macmini-lablz e confirmar `ALL OK`
3. Confirmar que `SELECT ficticio FROM pedidos LIMIT 1` retorna registros com `ficticio=true`

Só avançar para o Sprint 10 após APROVADO na homologação humana.
