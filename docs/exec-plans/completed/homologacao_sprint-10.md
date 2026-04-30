# Homologação Sprint 10 — Hotfixes críticos + D030 + F-07 + deprecação catalog

**Status:** ✅ APROVADO
**Data:** 2026-04-30
**Executado por:** Lauzier
**Versão final:** v0.10.13

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head` (até 0028)
- [ ] Embeddings migrados: `python scripts/migrate_embeddings.py --tenant jmb` →
  `commerce_products.embedding` ≥ 95% populado
- [ ] Lauzier marcado admin: `UPDATE gestores SET role='admin' WHERE telefone='+55...';`
- [ ] Plist launchd desativado: `launchctl unload ~/Library/LaunchAgents/com.jmb.efos-sync.plist`
  e renomeado para `.disabled` no repo
- [ ] APScheduler tem job EFOS registrado (verificar logs de startup)
- [ ] Smoke gate passou: `python scripts/smoke_sprint_10.py` → ALL OK
- [ ] Pre-homolog review: `artifacts/pre_homolog_review_sprint_10.md` → PASS
  (10 rotas + cenários bot)
- [ ] Health check: `curl http://100.113.28.85:8000/health` → `version=0.10.0` e `anthropic=ok`

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — Cliente envia áudio real
**Condição inicial:** Número cadastrado em `contacts` autorizado como cliente.
**Ação:** Cliente envia áudio via WhatsApp pedindo um produto.
**Resultado esperado:** Bot responde com base no texto transcrito (prefixo `🎤 Ouvi: ...` no histórico Redis); resposta usa `_buscar_produtos`.
**Verificação de banco:** `SELECT mensagem FROM conversas ORDER BY criado_em DESC LIMIT 1;` mostra texto transcrito.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H2 — Cliente pergunta capacidade de áudio
**Condição inicial:** Mesma conversa de H1.
**Ação:** Cliente envia "você consegue ouvir áudio?".
**Resultado esperado:** Bot confirma que aceita áudio.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H3 — Histórico preservado em conversa longa do gestor
**Condição inicial:** Conversa nova com gestor.
**Ação:** Gestor faz ≥ 6 perguntas seguidas que disparam tools (relatório,
ranking, listar pedidos, etc.) — força truncação em 20 mensagens.
**Resultado esperado:** Bot mantém contexto do início da conversa; nenhuma
mensagem `agent_*_historico_corrompido_recovery` no log; nenhuma resposta
estilo "vamos começar de novo".
**Verificação de banco:** `redis-cli LLEN hist:gestor:jmb:+55...` ≥ 18 entries.
**Verificação de log:** `grep historico_corrompido_recovery logs/staging-*.log` retorna 0 hits durante a conversa.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H4 — Pedido em nome de cliente EFOS
**Condição inicial:** Cliente "Lauzier Pereira" (ou similar) só existe em `commerce_accounts_b2b`.
**Ação:** Gestor: "fazer pedido de 5 Loção X para Lauzier Pereira" → "sim".
**Resultado esperado:** Pedido criado, PDF gerado e enviado, sem mensagem técnica "ID instável" / "Cliente não encontrado".
**Verificação de banco:** `SELECT id, account_external_id, cliente_b2b_id FROM pedidos ORDER BY criado_em DESC LIMIT 1;` mostra `account_external_id` preenchido.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H5 — Cadastro de contato cliente via dashboard
**Condição inicial:** Login como gestor admin em `/dashboard`.
**Ação:** `/dashboard/contatos/novo` → perfil=cliente → selecionar cliente do dropdown (do EFOS) → salvar.
**Resultado esperado:** Redirect com flash de sucesso; novo contato aparece na listagem `/dashboard/contatos` com badge `manual`.
**Verificação de banco:** `SELECT * FROM contacts WHERE origin='manual' ORDER BY criado_em DESC LIMIT 1;` retorna o registro com `account_external_id` preenchido.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H6 — Auto-criação self_registered + notificação dual
**Condição inicial:** Número desconhecido (não em gestores, representantes, contacts).
**Ação:** Enviar "olá, sou da Drogaria Calderari" via WhatsApp.
**Resultado esperado:**
- Remetente recebe "Vou avisar o gestor para te autorizar".
- Gestor recebe via WhatsApp: `[CONTATO PENDENTE] +55... mandou: "olá, sou da Drogaria Calderari". Possível cliente: ...`
- `/dashboard/contatos` mostra badge "1 pendente".
**Verificação de banco:** `SELECT * FROM contacts WHERE origin='self_registered' ORDER BY criado_em DESC LIMIT 1;` retorna registro `authorized=false`.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H7 — Comando AUTORIZAR
**Condição inicial:** H6 executado.
**Ação:** Gestor responde via WhatsApp: `AUTORIZAR +55...`.
**Resultado esperado:** Confirmação. Próxima mensagem do +55... é roteada para `AgentCliente` (não mais para "aguardando autorização").
**Verificação de banco:** `SELECT authorized, authorized_by_gestor_id FROM contacts WHERE channels @> '[{"identifier":"+55..."}]'::jsonb;` mostra `true` e gestor_id preenchido.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H8 — F-07 alterar preset
**Condição inicial:** Login como admin em `/dashboard/sync`.
**Ação:** Mudar preset de `diario` para `2x_dia` → Salvar.
**Resultado esperado:** Página recarrega mostrando "Próxima execução: hoje 13:00" (ou 08:00 depende da hora).
**Verificação:** `SELECT preset, cron_expression FROM sync_schedule WHERE tenant_id='jmb';` retorna `2x_dia` e cron `0 8,13 * * *`.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H9 — F-07 lock anti-overlap
**Condição inicial:** Mesma sessão H8.
**Ação:** Clicar "Rodar agora" 2x em sequência rápida.
**Resultado esperado:** 2º clique mostra erro 409 "sync já em andamento".
**Verificação:** `redis-cli GET sync:efos:jmb:running` retorna timestamp.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H10 — Busca semântica após drop legado
**Condição inicial:** E20 aplicado (tabela `produtos` removida).
**Ação:** Cliente envia "shampoo" via WhatsApp.
**Resultado esperado:** Bot retorna ≥ 1 produto, com nome e preço corretos.
**Verificação:** `SELECT 1 FROM produtos LIMIT 1;` falha com `relation "produtos" does not exist`.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H11 — Langfuse mostra custo
**Condição inicial:** Conversa H1-H4 executada.
**Ação:** Abrir Langfuse UI → trace mais recente.
**Resultado esperado:** Trace com `totalCost > 0`, `usage.input_tokens > 0`, `usage.output_tokens > 0`, `observations` com ≥ 1 generation.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H12 — Ranking eficiente + ano correto
**Condição inicial:** Hoje é 2026-04-29 (ou data posterior).
**Ação:** Gestor: "qual foi o melhor vendedor de março?".
**Resultado esperado:** 1 chamada de tool `ranking_vendedores_efos`, resposta com mês 03 / ano 2026 (ano corrente).
**Verificação:** Langfuse trace mostra 1 generation com tool `ranking_vendedores_efos` (não 24 chamadas a `relatorio_vendas_representante_efos`).
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

### H13 — `/dashboard/clientes` read-only
**Condição inicial:** Login no dashboard.
**Ação:** Navegar para `/dashboard/clientes`.
**Resultado esperado:** Lista 614 clientes do EFOS; **sem botão "Novo Cliente"**.
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** ✅ APROVADO
**Data:** 2026-04-30
**Versão:** v0.10.13

**Resultados por cenário:**
| H | Cenário | Resultado | Observação |
|---|---------|-----------|------------|
| H1 | Áudio cliente | ✅ PASSOU | v0.10.1 — Evolution API retorna 201 (não 200) |
| H2 | Capacidade áudio | ✅ PASSOU | |
| H3 | Histórico longo | ✅ PASSOU | Validado via webhook simulado (6 turnos) |
| H4 | Pedido cliente EFOS | ✅ PASSOU | v0.10.2 — observacao migration + account_external_id |
| H5 | Cadastro contato dashboard | ✅ PASSOU | v0.10.3/v0.10.4 — CAST JSONB + normalize perfil |
| H6 | Self-registered + notify dual | ⏭ NÃO TESTADO | Validado via webhook simulado; sem WhatsApp novo disponível |
| H7 | Comando AUTORIZAR | ⏭ NÃO TESTADO | Validado via webhook simulado |
| H8 | F-07 alterar preset | ✅ PASSOU | |
| H9 | F-07 lock anti-overlap | ✅ PASSOU | |
| H10 | Busca semântica pós-drop | ✅ PASSOU | 743/743 embeddings preservados após sync |
| H11 | Langfuse custo | ✅ PASSOU | v0.10.13 — sessions + input/output + $0.14/sessão |
| H12 | Ranking eficiente | ✅ PASSOU | 1 tool call, ano 2026 |
| H13 | Clientes read-only | ✅ PASSOU | |

**Bugs encontrados durante homologação (13 hotfixes, v0.10.1→v0.10.13):**
- v0.10.1: B-23 (Evolution HTTP 201 ≠ 200)
- v0.10.2: B-28 incompleto (observacao migration + account_external_id)
- v0.10.3: B-33 a B-40 (8 bugs sweep — CAST JSONB, perfil normalize, ON CONFLICT, Rodar Agora síncrono, send_whatsapp kwargs, KPI mês, IdentityRouter)
- v0.10.4: B-34 follow-up (representante→rep mapping)
- v0.10.5: B-33 incompleto (SELECT contacts ainda com ::jsonb)
- v0.10.6: CSS radio/checkbox (width:100% em base.html)
- v0.10.7: aba Sync ausente do menu nav
- v0.10.8: feedback visual Rodar Agora
- v0.10.9: run_sync session_factory kwarg inválido
- v0.10.10: banner sync baseado em query string (falso positivo)
- v0.10.11: ON CONFLICT 2 colunas vs 3 + indexes faltantes
- v0.10.12: session_id no trace Langfuse + modelos Haiku + pricing
- v0.10.13: input/output visíveis na UI de Sessions Langfuse

**Débitos técnicos abertos para Sprint 11:**
- TD-Sprint10-1: 5 rotas dashboard sem evidência de browser MCP (screenshot)
- TD-Sprint10-2: Whisper não instrumentado no Langfuse
- H6/H7 pendente de teste via WhatsApp real (validado via webhook simulado)

---

## Pós-homologação (executado pelo Lauzier após APROVADO)

- [ ] Tag `v0.10.0` criada via auto-tag deploy
- [ ] Mover este arquivo para `docs/exec-plans/completed/`
- [ ] Mover `sprint-10-hotfixes-d030-f07-deprecacao.md` para `completed/`
- [ ] Atualizar `docs/PLANS.md` Sprint 10 → ✅
- [ ] Bugs B-23, B-24, B-25, B-26, B-27, B-28, B-29, B-30 → mover para "Resolvidos" em `docs/BUGS.md`
- [ ] Memória `project_sprint10.md` atualizada
- [ ] Plist launchd `.disabled` agendado para remoção no Sprint 11
