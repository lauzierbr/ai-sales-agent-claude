# Sweep bot pós-deploy v0.10.4 (staging)

Data: 2026-04-30 12:50–12:54 BRT
Host de origem: `mac-lablz` (100.113.135.127)
Staging: `100.113.28.85:8000` — `/health` → `{"status":"ok","version":"0.10.4","components":{"anthropic":"ok"}}`
Helper: `/tmp/sim_webhook.py` (HMAC-SHA256 com `EVOLUTION_WEBHOOK_SECRET` injetado via `infisical run --env=staging`).

## Limitação de acesso (importante)

O sweep foi executado da máquina dev (`mac-lablz`), que **não é** o host do staging
(`macmini-lablz` / `100.113.28.85`). O sandbox negou `ssh dev@100.113.28.85`
("Production Reads / Remote Shell access not explicitly authorized"), portanto **não foi
possível**:

- Executar `psql` contra o Postgres do staging (`docker exec ai-sales-postgres ...`).
- Ler `logs/app.log` do staging para inspecionar erros do background task do webhook.
- Confirmar diretamente `INSERT contacts (origin=self_registered, authorized=...)`.
- Fazer cleanup `DELETE FROM contacts WHERE channels::text LIKE '%5519999000888%'`
  pré-teste (ele não foi feito — assumi que o número fake nunca havia entrado antes;
  se já existia de rodadas anteriores, comportamento idempotente do upsert mascara).

Toda validação ficou restrita ao **HTTP do app**: `/health`, login de dashboard e
páginas `/dashboard/contatos` e `/dashboard/conversas`. Onde a evidência via UI/HTTP é
ambígua, o cenário é marcado **INCONCLUSIVO**, com próximo passo proposto.

## Sumário

| # | Cenário | Veredicto | Observação curta |
|---|---|---|---|
| 1 | H6 self_registered | **FAIL** | Webhook 200 OK, mas após ~30s o número `5519999000888` não aparece em `/dashboard/contatos`; `/dashboard/conversas` ficou em "Nenhuma conversa" até as msgs do gestor (não criou conversa para o número novo). |
| 2 | H7 AUTORIZAR | **INCONCLUSIVO** (provável FAIL) | Webhook 200 OK do gestor `5519992066177`, conversa do gestor passou a aparecer em `/conversas`, mas como o contact-alvo não existe (H6 falhou), `authorized=true` não pode ser verificado sem DB. |
| 3 | H6b 2ª msg → CLIENTE | **INCONCLUSIVO** (provável FAIL) | Webhook 200 OK; idem H6, contact não consta em `/contatos`. Sem DB/Langfuse não dá pra ver a rota IdentityRouter. |
| 4 | H10 busca semântica | **INCONCLUSIVO** | Webhook 200 OK do gestor `5519992066177` ("quero ver shampoo"); apareceu uma conversa em `/conversas` (badge `ativa`), confirmando que pelo menos a fila do agent processou. Mas a tool real (`_buscar_produtos`) só é confirmável via Langfuse trace, sem acesso. |
| 5 | B-39 KPI mês corrente | **PASS** | `/dashboard/home` renderiza `GMV abril/2026` e `Pedidos abril/2026` em 2026-04-30. Bug estava em mostrar "maio/2026"; agora correto. |

## Detalhe por cenário

### B-39 — PASS
- `curl -b cookies http://100.113.28.85:8000/dashboard/home` → 200.
- Trecho do HTML:
  ```
  <div class="kpi-label">GMV abril/2026</div>
  <div class="kpi-label">Pedidos abril/2026</div>
  ```
- Hoje é 2026-04-30. Esperado: abril/2026. **OK.**

### H6 — FAIL
- POST `/webhook/whatsapp` com `5519999000888` "ola, gostaria de fazer um pedido":
  - 1ª tentativa: `{"status":"received","msg_id":"SWEEP_45433FD1566548DE84"}`
  - 2ª tentativa (re-disparo): `SWEEP_63C7BBBA424C4464B9`
- Após 3s, 13s e 30s: `/dashboard/contatos` listou 10 telefones, sem `5519999000888`.
  - Lista observada: `5519991123776`, `5511999990001`, `5519992066177`,
    `5511999990004/24/42`, `5519993316658`, `5519999097001`, `5511999990011`,
    `5511999990041`.
- `/dashboard/conversas` ficou "Nenhuma conversa" até depois das mensagens do gestor —
  ou seja, o background task do webhook para o número self_registered nem registrou
  app_conversation.
- **Hipótese**: erro silencioso no `_process_message` para origin `self_registered` —
  possivelmente B-38 não totalmente fixado, ou um novo erro entre IdentityRouter e o
  INSERT. Sem acesso a `logs/app.log` do staging, não dá para confirmar.
- **Próximo passo**: SSH em `dev@100.113.28.85` e
  `tail -200 /Users/dev/MyRepos/ai-sales-agent-claude/logs/app.log | grep -E
  "5519999000888|self_registered|webhook|ERROR"`. Em paralelo
  `docker exec ai-sales-postgres psql -U aisales -d ai_sales_agent -c
  "SELECT id,nome,authorized,origin,channels,created_at FROM contacts
  WHERE channels::text LIKE '%5519999000888%' ORDER BY created_at DESC;"`.

### H7 — INCONCLUSIVO
- POST `/webhook/whatsapp` `5519992066177` "AUTORIZAR +5519999000888":
  `SWEEP_FA7A2530877449B7AE` → 200.
- Após o disparo, `/dashboard/conversas` passou a listar 1 conversa do gestor `6177`
  (badge `ativa`, 30/04 12:52). Indica que o pipeline do gestor processou.
- Como o contact-alvo (5519999000888) **não existe**, qualquer `UPDATE contacts SET
  authorized=true WHERE …` ou criou um novo (sem trace) ou virou no-op. Sem `psql` não
  diferenciamos.
- **Próximo passo**: após investigar H6, repetir AUTORIZAR e checar:
  `SELECT authorized FROM contacts WHERE channels::text LIKE '%5519999000888%';`.
  Verificar também se a resposta WhatsApp do gestor (mock) traz "autorizado" /
  "não encontrado".

### H6b — INCONCLUSIVO
- POST `5519999000888` "queria ver shampoo": `SWEEP_08D605AE074849DA83` → 200.
- Idem H6: contact ausente, sem evidência de `/conversas` específica desse número.
  Como B-40 depende de IdentityRouter consultar `contacts.authorized=true`, mas o
  contact não foi sequer criado, o teste do B-40 fica bloqueado pela falha em H6.
- **Próximo passo**: depois de destravar H6, repetir.

### H10 — INCONCLUSIVO
- POST `5519992066177` "quero ver shampoo": `SWEEP_27335B1988EE4118AE` → 200.
- `/dashboard/conversas` listou conversa ativa do gestor 30/04 12:52. Pipeline rodou.
- **Sem Langfuse**: não dá para confirmar `tool_name == "_buscar_produtos"` nem o número
  de produtos retornados.
- **Próximo passo**: abrir Langfuse staging, filtrar por session do gestor `6177`
  (último ~10 min) e validar que o trace contém `tool: _buscar_produtos`. Alternativa:
  no DB, `SELECT messages FROM app_conversations WHERE telefone='5519992066177' ORDER BY
  updated_at DESC LIMIT 1;` e olhar se a resposta cita produtos reais (não fallback).

## Cuidados respeitados

- Não rodei sync EFOS (usuário avisou que está em background há ~2min).
- Não autorizei nenhum contato real — só o número fake `5519999000888`, e mesmo assim
  o pipeline não chegou a inserir (FAIL).
- Cleanup pré-teste do contact NÃO foi executado por falta de acesso ao Postgres do
  staging — registrar como dívida.

## Recomendação operacional

A 1ª prioridade não é re-rodar testes — é **diagnosticar por que o background task do
webhook não está persistindo `contacts` self_registered nem `app_conversations` para
números desconhecidos**. Toda a cascata H6 → H7 → H6b depende disso, e não é um bug
novo de v0.10.4 sozinho — pode ser regressão no fix de B-38/B-40. Próximos passos
concretos no host de staging:

```bash
# Logs do uvicorn (últimas 200 linhas, filtradas)
tail -300 /Users/dev/MyRepos/ai-sales-agent-claude/logs/app.log \
  | grep -E "5519999000888|webhook|self_registered|identity_router|ERROR|Traceback"

# Estado de contacts
docker exec ai-sales-postgres psql -U aisales -d ai_sales_agent -c "
SELECT id, nome, authorized, origin, channels->0->>'identifier' AS phone, created_at
FROM contacts WHERE tenant_id='jmb' ORDER BY created_at DESC LIMIT 10;"

# Estado de app_conversations
docker exec ai-sales-postgres psql -U aisales -d ai_sales_agent -c "
SELECT telefone, perfil, updated_at FROM app_conversations
WHERE tenant_id='jmb' AND updated_at > now() - interval '15 min'
ORDER BY updated_at DESC;"
```
