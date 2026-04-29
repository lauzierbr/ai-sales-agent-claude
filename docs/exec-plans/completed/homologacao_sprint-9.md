# Homologação Sprint 9 — Commerce Reads + Dashboard Sync + Áudio WhatsApp
# (Homologação unificada Sprint 8 + Sprint 9)

**Status:** PENDENTE
**Data prevista:** após Sprint 9 APROVADO pelo Evaluator
**Executado por:** Lauzier

> Esta homologação cobre **Sprint 8 (H1–H11)** e **Sprint 9 (H12–H21)** em uma
> única sessão. Todos os 21 cenários devem passar para APROVADO final.

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [ ] Deploy realizado: `./scripts/deploy.sh staging`
- [ ] Migrations aplicadas: `alembic upgrade head` (banco em ≥ 0023)
- [ ] Seed de dados: `infisical run --env=staging -- python scripts/seed_homologacao_sprint-9.py`
- [ ] Smoke gate passou: `python scripts/smoke_sprint_9.py` → ALL OK
- [ ] Health check: `curl http://100.113.28.85:8000/health` → `{"version": "0.9.0", ...}`
- [ ] Run EFOS executado (necessário para H4–H11): `infisical run --env=staging -- python -m integrations.jobs.sync_efos --tenant jmb`

**Nota — Secrets EFOS:** `JMB_EFOS_SSH_HOST`, `JMB_EFOS_SSH_USER`, `JMB_EFOS_SSH_KEY_PATH`,
`JMB_EFOS_BACKUP_REMOTE_PATH` e `JMB_EFOS_ARTIFACT_DIR` devem estar cadastrados no Infisical
env=staging antes de tentar o run EFOS. Cenários H4–H11 dependem desse run.

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação — Sprint 8

### H1 — B-10: pedido criado com representante_id preenchido

**Condição inicial:** Existe cliente em `clientes_b2b` com `representante_id` não-nulo (seed)
**Ação:** Cliente envia pedido completo via WhatsApp e confirma (`sim`)
**Resultado esperado:** Campo `representante_id` no pedido criado é um UUID válido (não nulo)
**Verificação de banco:**
```sql
SELECT id, representante_id, criado_em FROM pedidos ORDER BY criado_em DESC LIMIT 1;
```
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H2 — B-11: nova sessão não carrega histórico de persona anterior

**Condição inicial:** Número não cadastrado em nenhuma persona
**Ação:**
1. Enviar mensagem pelo número (entra como CLIENTE ou DESCONHECIDO)
2. No dashboard, cadastrar esse número como REPRESENTANTE
3. Enviar nova mensagem pelo mesmo número
**Resultado esperado:** Resposta da Fase 3 não menciona contexto da Fase 1 (histórico limpo)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H3 — B-12: traces Langfuse com output, tokens e session_id

**Condição inicial:** Langfuse self-hosted acessível
**Ação:** Trocar 3–4 mensagens com o agente cliente (buscar produto, fazer pedido)
**Resultado esperado:**
- `output` ≠ null (resposta final do agente)
- `usage.input_tokens` > 0 e `usage.output_tokens` > 0
- `session_id` preenchido (UUID da conversa)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H4 — sync_efos: run completo end-to-end

**Condição inicial:** Secrets EFOS no Infisical staging, banco em migration ≥ 0023
**Ação:** `infisical run --env=staging -- python -m integrations.jobs.sync_efos --tenant jmb`
**Resultado esperado:**
- Exit code 0
- `sync_runs` tem 1 registro com `status = 'success'` e `rows_published > 0`
- `commerce_products` tem ≥ 100 linhas para tenant jmb
**Verificação de banco:**
```sql
SELECT status, rows_published, finished_at FROM sync_runs
WHERE tenant_id = 'jmb' ORDER BY started_at DESC LIMIT 1;

SELECT COUNT(*) FROM commerce_products WHERE tenant_id = 'jmb';
SELECT COUNT(*) FROM commerce_accounts_b2b WHERE tenant_id = 'jmb';
SELECT COUNT(*) FROM commerce_vendedores WHERE tenant_id = 'jmb';
```
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H5 — sync_efos: segunda execução é idempotente

**Condição inicial:** H4 passou
**Ação:** Executar `python -m integrations.jobs.sync_efos --tenant jmb` novamente sem `--force`
**Resultado esperado:**
- Exit code 0
- Log contém "checksum já importado" ou equivalente de skip
- Contagem em `commerce_products` não muda (sem duplicatas)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H6 — Tool gestor: relatório de vendas por representante

**Condição inicial:** H4 passou (commerce_* populado)
**Ação:** Gestor envia via WhatsApp: `"Relatório de vendas do representante Rondinele mês 4"`
**Resultado esperado:** Resposta estruturada com total vendido em R$, quantidade de pedidos, principais clientes
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H7 — Tool gestor: relatório de vendas por cidade

**Condição inicial:** H4 passou
**Ação:** Gestor envia via WhatsApp: `"Relatório de vendas clientes de Vinhedo abril"`
**Resultado esperado:** Lista de clientes de VINHEDO com totais de venda do mês 4
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H8 — Tool gestor: clientes inativos de uma cidade específica

**Condição inicial:** H4 passou
**Ação:** Gestor envia via WhatsApp: `"Lista de clientes inativos na cidade de Itupeva"`
**Resultado esperado:** Lista com nome, CNPJ e telefone de clientes com `situacao_cliente = 2` e `cidade = ITUPEVA`
**Verificação de banco:**
```sql
SELECT nome, cnpj, telefone, cidade FROM commerce_accounts_b2b
WHERE tenant_id = 'jmb' AND situacao_cliente = 2 AND cidade = 'ITUPEVA';
```
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H9 — Tool gestor: clientes inativos sem filtro de cidade

**Condição inicial:** H4 passou
**Ação:** Gestor envia via WhatsApp: `"Lista de clientes inativos"`
**Resultado esperado:** Lista de todos os inativos de qualquer cidade
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H10 — Fuzzy match de nome de representante

**Condição inicial:** H6 passou
**Ação:** Gestor envia: `"vendas do representante rondinele ritter mês 4"` e depois `"vendas do RONDINELE mês 4"`
**Resultado esperado:** Ambas as consultas retornam os mesmos dados
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H11 — Sem regressão: fluxo normal de pedido cliente

**Condição inicial:** Staging com seed de dados básicos
**Ação:** Cliente faz pedido completo: buscar produto → adicionar → confirmar (`sim`)
**Resultado esperado:**
- Pedido no banco com status correto
- PDF gerado e enviado ao cliente
- Gestor recebe notificação com PDF
- Nenhum erro nos logs
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Cenários de homologação — Sprint 9

### H12 — Pedido fictício marcado corretamente

**Condição inicial:** Staging com `ENVIRONMENT=staging`, cliente cadastrado
**Ação:** Cliente confirma pedido via WhatsApp
**Resultado esperado:**
- PDF recebido contém texto "PEDIDO DE TESTE — NÃO PROCESSAR"
- Caption recebido pelo gestor começa com `⚠️ TESTE |`
- `SELECT ficticio FROM pedidos ORDER BY criado_em DESC LIMIT 1` → `true`
- Badge "TESTE" aparece no pedido na listagem do dashboard
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H13 — AgentGestor: "lista de clientes inativos" usa dados EFOS

**Condição inicial:** H4 passou (`commerce_accounts_b2b` com clientes reais do EFOS)
**Ação:** Gestor envia: `"Lista de clientes inativos"`
**Resultado esperado:** Resposta contém clientes com `situacao_cliente=2` do EFOS — **não** retorna "nenhum inativo" como antes
**Verificação de banco:** `SELECT COUNT(*) FROM commerce_accounts_b2b WHERE tenant_id='jmb' AND situacao_cliente=2` → ≥ 1
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H14 — AgentGestor: "quais os representantes" usa dados EFOS

**Condição inicial:** H4 passou (`commerce_vendedores` com 24 representantes reais)
**Ação:** Gestor envia: `"Quais os representantes do sistema?"`
**Resultado esperado:** Resposta lista representantes reais do EFOS (ex: 24 nomes), **não** apenas Rondinele com 5 pedidos de teste
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H15 — B-13: busca por EAN completo retorna produto

**Condição inicial:** `commerce_products` populado (H4) ou `catalog.produtos` com produto cadastrado
**Ação:** Cliente envia via WhatsApp o EAN completo de um produto (ex: `7898923148571`)
**Resultado esperado:** Agente encontra o produto e lista nome, preço; não responde "produto não encontrado"
**Verificação:** EAN `7898923148571` → sufixo `148571` → deve bater com `codigo_externo = '148571'`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H16 — Busca de produto via nome usa commerce_products

**Condição inicial:** H4 passou (`commerce_products` com ≥ 100 produtos)
**Ação:** Cliente busca produto pelo nome: `"Quero ver os vinhos disponíveis"` (ou nome de produto real do EFOS)
**Resultado esperado:** Agente retorna produtos com nomes/preços do EFOS (não do catálogo Playwright antigo)
**Verificação de banco:** Conferir nome no resultado vs `SELECT name FROM commerce_products WHERE tenant_id='jmb' LIMIT 5;`
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H17 — Fallback: busca de cliente usa commerce_accounts_b2b quando clientes_b2b não tem resultado

**Condição inicial:** H4 passou; cliente existe em `commerce_accounts_b2b` mas não em `clientes_b2b`
**Ação:** Rep/Gestor envia: `"Busca cliente [nome de cliente do EFOS que não está em clientes_b2b]"`
**Resultado esperado:** Agente encontra o cliente via fallback `commerce_accounts_b2b`; nome exibido corretamente
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H18 — Dashboard: bloco "Última sincronização EFOS" exibe dados corretos

**Condição inicial:** H4 passou (sync_runs tem ao menos 1 registro `success`)
**Ação:** Lauzier abre dashboard web (`http://100.113.28.85:8000/dashboard`) → página principal
**Resultado esperado:**
- Bloco "Última sincronização EFOS" visível
- Badge verde com status `success`
- Data/hora `finished_at` formatada em BRT (ex: `27/04/2026 14:35`)
- Número de `rows_published` exibido
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H19 — Dashboard: bloco sync exibe "Nunca sincronizado" para tenant sem histórico

**Condição inicial:** Criar tenant de teste sem registros em `sync_runs`
**Ação:** Acessar dashboard com tenant sem histórico de sync
**Resultado esperado:** Bloco exibe "Nunca sincronizado" (sem erro 500)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H20 — Áudio WhatsApp: transcrição via Whisper e resposta com prefixo

**Condição inicial:** `OPENAI_API_KEY` válida no Infisical staging
**Ação:** Enviar mensagem de áudio (OGG/Opus) via WhatsApp para o número do agente cliente: gravar uma pergunta sobre produto (ex: "Quero saber o preço do vinho tinto")
**Resultado esperado:**
- Agente responde com linha inicial `"🎤 Ouvi: quero saber o preço do vinho tinto"` (ou similar)
- Em seguida agente processa normalmente e retorna informação sobre produto
- Nenhum erro 500 nos logs
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H21 — Áudio WhatsApp: mensagem de texto não é afetada

**Condição inicial:** H17 passou
**Ação:** Enviar mensagem de texto normal via WhatsApp: `"Quero ver o catálogo"`
**Resultado esperado:** Agente responde normalmente SEM prefixo `"🎤 Ouvi:"` — fluxo de texto não alterado
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___
**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — bugs para hotfix antes do Sprint 10:**

| ID | Descrição | Severidade |
|----|-----------|------------|
| | | |

---

## Próximos passos após APROVADO

1. `git tag v0.9.0`
2. Mover `sprint-8-efos-backup.md`, `homologacao_sprint-8.md`, `sprint-9-commerce-audio.md` e `homologacao_sprint-9.md` para `docs/exec-plans/completed/`
3. Atualizar `docs/PLANS.md`: Sprint 8 → ✅, Sprint 9 → ✅
4. Registrar novos gotchas descobertos em `docs/GOTCHAS.yaml`
5. Iniciar Sprint 10 (backlog: embeddings para commerce_products, push proativo WhatsApp, segundo tenant)
