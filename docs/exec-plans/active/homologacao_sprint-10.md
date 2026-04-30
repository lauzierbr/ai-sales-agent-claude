# Homologação Sprint 10 — Hotfixes críticos + D030 + F-07 + deprecação catalog

**Status:** PENDENTE
**Data prevista:** _(definir após implementação)_
**Executado por:** Lauzier
**Versão alvo:** v0.10.0

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

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — próximos passos:**
[lista de bugs para hotfix antes do Sprint 11]

---

## Pós-homologação (executado pelo Lauzier após APROVADO)

- [ ] Tag `v0.10.0` criada via auto-tag deploy
- [ ] Mover este arquivo para `docs/exec-plans/completed/`
- [ ] Mover `sprint-10-hotfixes-d030-f07-deprecacao.md` para `completed/`
- [ ] Atualizar `docs/PLANS.md` Sprint 10 → ✅
- [ ] Bugs B-23, B-24, B-25, B-26, B-27, B-28, B-29, B-30 → mover para "Resolvidos" em `docs/BUGS.md`
- [ ] Memória `project_sprint10.md` atualizada
- [ ] Plist launchd `.disabled` agendado para remoção no Sprint 11
