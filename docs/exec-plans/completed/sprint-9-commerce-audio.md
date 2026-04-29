# Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp

**Status:** 🔄 Em planejamento
**Data início:** 2026-04-27
**Versão alvo:** v0.9.0
**Spec:** `artifacts/spec.md`
**Homologação:** `docs/exec-plans/active/homologacao_sprint-9.md` (unificada Sprint 8 + Sprint 9)

---

## Objetivo

Migrar leituras de produtos para `commerce_products`, adicionar fallback de clientes para `commerce_accounts_b2b`, exibir status de sync EFOS no dashboard e processar áudio WhatsApp via Whisper.

---

## Entregas (checklist)

### Fase 0 — Hotfix B-13: busca por EAN completo

- [ ] `catalog/repo.py` `_buscar_produtos()`: se query numérica e `len > 6`, tenta também `query[-6:]` em `codigo_externo`
- [ ] Mesmo fix em `agents/runtime/agent_cliente.py` (linha ~633), `agent_rep.py`, `agent_gestor.py`
- [ ] `tests/regression/test_ean_busca.py`: 3 cenários (EAN 13 dígitos, EAN 6 dígitos, busca textual)
- [ ] `pytest -m unit` passa

### Fase 1a — catalog/service.py: leituras de produtos de commerce_products

- [ ] `commerce/repo.py` ganha `buscar_produtos_commerce(tenant_id, query, limit)` (lookup por `external_id`, `name`)
- [ ] `catalog/service.py` verifica contagem de `commerce_products` para o tenant
- [ ] Se ≥ 1 → usa `CommerceRepo.buscar_produtos_commerce`; se 0 → usa `CatalogRepo` legado
- [ ] Busca semântica pgvector permanece em `catalog/repo.py` (embeddings só em `produtos`)
- [ ] Sem violação de import-linter (catalog/service.py → commerce/repo.py: Service → Repo, permitido)
- [ ] `pytest -m unit` passa

### Fase 1b — agents/repo.py: fallback clientes para commerce_accounts_b2b

- [ ] `commerce/repo.py` ganha `buscar_clientes_commerce(tenant_id, query)`
- [ ] `agents/repo.py`: se `clientes_b2b` retorna 0 → chama `CommerceRepo.buscar_clientes_commerce`
- [ ] Resultado homogêneo (mesma estrutura) independente da fonte
- [ ] Tenant isolation em ambas as queries
- [ ] `pytest -m unit` passa

### Fase 2 — Dashboard: bloco "Última sincronização EFOS"

- [ ] Endpoint htmx partial: `GET /dashboard/sync-status` (ou `hx-get` para partial)
- [ ] `integrations/repo.py` ganha (ou já tem) `get_last_sync_run(tenant_id)` → retorna `SyncRun | None`
- [ ] Template HTML: badge status (verde/vermelho), `finished_at` BRT, `rows_published`
- [ ] Estado "Nunca sincronizado" quando `sync_runs` vazio
- [ ] htmx polling `hx-trigger="every 60s"`
- [ ] `pytest -m unit` cobre o endpoint

### Fase 3 — Áudio WhatsApp via Whisper

- [ ] `agents/ui.py` `parse_mensagem()`: detecta `messageType == "audioMessage"`
- [ ] Download via `url` (httpx) ou decodificação base64 como fallback
- [ ] `_transcrever_audio(bytes) -> str` com `asyncio.to_thread` + `openai.audio.transcriptions.create(file=("audio.ogg", ...))`
- [ ] Transcrição substitui `text` da mensagem retornada
- [ ] Agente prefixa resposta com `"🎤 Ouvi: {transcricao}\n\n"`
- [ ] Fallback amigável em caso de erro de transcrição
- [ ] `tests/unit/agents/test_audio_transcricao.py`: 4 cenários
- [ ] `pytest -m unit` passa

### Finalização

- [ ] `GET /health` retorna `"version": "0.9.0"`
- [ ] import-linter: 0 violações (`lint-imports`)
- [ ] `python scripts/smoke_sprint_9.py` → ALL OK
- [ ] `scripts/seed_homologacao_sprint-9.py` criado (idempotente)
- [ ] Deploy staging: `./scripts/deploy.sh staging`

---

## Log de decisões

| Data | Decisão | Autor |
|------|---------|-------|
| 2026-04-27 | Fallback de produto: lógica em catalog/service.py (não em repo) para não violar import-linter D027 | Planner |
| 2026-04-27 | Whisper usa API síncrona com asyncio.to_thread para não bloquear event loop | Planner |
| 2026-04-27 | Busca semântica pgvector permanece em catalog.produtos neste sprint (embeddings para commerce_products = Sprint futuro) | Planner |
| 2026-04-27 | homologacao_sprint-9 unifica cenários Sprint 8 (H1–H11) + cenários Sprint 9 (H12–H18) | Produto |

---

## Notas de execução

### Verificar antes de implementar

1. Confirmar se coluna `ean` existe em `commerce_products` (migrations 0018–0023):
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'commerce_products' AND column_name = 'ean';
   ```
   Se não existir → B-13 usa apenas `external_id` com `query[-6:]`.

2. Confirmar se coluna `rows_published` existe em `sync_runs`:
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'sync_runs' AND column_name = 'rows_published';
   ```

3. Confirmar que `integrations/repo.py` já tem `get_last_sync_run()` ou criar.

### Fluxo de áudio Evolution API

```
Webhook POST /webhook/whatsapp
  └── parse_mensagem()
        ├── messageType == "audioMessage"?
        │     ├── Sim → _transcrever_audio()
        │     │         ├── Tenta url → httpx download
        │     │         ├── Fallback base64
        │     │         └── openai.audio.transcriptions.create("audio.ogg")
        │     │   Retorna Mensagem com text = transcrição
        │     └── Não → fluxo normal
        └── → processar_mensagem() → agente prefixo "🎤 Ouvi: ..."
```

### Gotcha crítico: nome do arquivo Whisper

O arquivo enviado para Whisper DEVE ter extensão `.ogg`:
```python
# CORRETO
("audio.ogg", audio_bytes, "audio/ogg")

# ERRADO — Whisper não reconhece o formato
("audio", audio_bytes, "audio/ogg")
```

### Gotcha crítico: import-linter para catalog/service.py → commerce/repo.py

Verificar contratos em `pyproject.toml`. Se `commerce` tiver contrato `"não importa outros domínios"`, isso não cobre `catalog/service.py` importando `commerce/repo.py` (é o catalog importando commerce, não o contrário). Mas verificar se há contrato reverso.

---

## Dependências externas

| Dependência | Status | Notas |
|-------------|--------|-------|
| `commerce_products` populada | ✅ Sprint 8 | 743 produtos (jmb) |
| `commerce_accounts_b2b` populada | ✅ Sprint 8 | 614 clientes (jmb) |
| `OPENAI_API_KEY` no Infisical | ✅ Sprint 0 | Usada para embeddings; agora também para Whisper |
| sync_efos rodando (launchd 13:00 BRT) | ⏳ Pendente EFOS secrets | Cenários H4–H11 da homologação dependem disso |
