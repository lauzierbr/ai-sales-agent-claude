# Homologação Sprint 8 — Hotfixes Piloto + Integração EFOS

**Status:** PRONTO PARA HOMOLOGAÇÃO — smoke gate passou em 2026-04-27 17:20 (checks não-EFOS: ALL OK)
**Data prevista:** 2026-04-30
**Executado por:** Lauzier

---

## Pré-condições (executadas pelo Generator antes de chamar homologação)

- [x] Código implementado e aprovado pelo Evaluator (`artifacts/qa_sprint_8.md`)
- [x] `scripts/smoke_sprint_8.py` — existe e cobre todos os 7 checks do critério A_SMOKE
- [x] `scripts/seed_homologacao_sprint-8.py` — criado; seed idempotente de representante, gestor e cliente B2B com `representante_id` não-nulo (pré-condição H1/B-10)
- [x] Deploy realizado: código Sprint 8 sincronizado em macmini-lablz (commit 06aeb80, 2026-04-27)
- [x] Migrations aplicadas: `alembic upgrade head` — banco em 0023_commerce_vendedores
- [x] Seed executado: tenant, representante, gestor, cliente B2B com representante_id — PASS
- [ ] Run EFOS inicial: `python -m integrations.jobs.sync_efos --tenant jmb` — PENDENTE (secrets JMB_EFOS_SSH_HOST etc. não cadastrados no Infisical staging — ver nota abaixo)
- [x] Smoke gate passou (checks não-EFOS): health, pytest_unit (343 pass), tabelas commerce/sync — ALL OK
- [x] Health check: `curl http://100.113.28.85:8000/health` → versão 0.7.0 confirmada

**Nota — Pendência EFOS:** Os checks do smoke que requerem run real do EFOS
(sync_efos_dry_run, commerce_products_count >= 100, sync_runs_success_count >= 1)
falharam porque os secrets `JMB_EFOS_SSH_HOST`, `JMB_EFOS_SSH_USER`,
`JMB_EFOS_SSH_KEY_PATH`, `JMB_EFOS_BACKUP_REMOTE_PATH` e `JMB_EFOS_ARTIFACT_DIR`
não estão cadastrados no Infisical env=staging.
O módulo importa corretamente — a falha é de configuração de infra, não de código.
**Ação necessária:** Lauzier cadastra os secrets EFOS no Infisical e executa:
```
python -m integrations.jobs.sync_efos --tenant jmb
python scripts/smoke_sprint_8.py  # deve resultar em ALL OK após o run
```
Os cenários H4–H10 da homologação manual dependem desse run ter sido executado.

**Critério de "pronto para homologação" (definido pelo produto):**
O sprint está pronto para homologação manual quando:
1. Deploy bem-sucedido em staging (macmini-lablz): `./scripts/deploy.sh staging` sem erros
2. `alembic upgrade head` aplicado no banco de staging
3. Seed executado: `infisical run --env=staging -- python scripts/seed_homologacao_sprint-8.py`
4. `python scripts/smoke_sprint_8.py` → `ALL OK` (testes mínimos automatizados)

Não é necessário aguardar aprovação do Evaluator para iniciar homologação manual —
o smoke gate é o gate de qualidade suficiente para liberação ao Lauzier.

**Só iniciar homologação manual após todas as pré-condições ✅**

---

## Cenários de homologação

### H1 — B-10: pedido criado com representante_id preenchido

**Condição inicial:** Existe cliente em `clientes_b2b` com `representante_id` não-nulo (seed ou cadastro real)
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
1. Enviar mensagem pelo número (persona DESCONHECIDO ou entra como CLIENTE)
2. No dashboard, cadastrar esse número como REPRESENTANTE
3. Enviar nova mensagem pelo mesmo número
**Resultado esperado:** A resposta da Fase 3 não menciona nenhum contexto da Fase 1 (histórico limpo)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H3 — B-12: traces Langfuse com output, tokens e session_id

**Condição inicial:** Langfuse self-hosted acessível
**Ação:** Trocar 3–4 mensagens com o agente cliente (ex: buscar produto, fazer pedido)
**Resultado esperado:** Em Langfuse UI, os traces mostram:
- `output` ≠ null (preenchido com a resposta final do agente)
- `usage.input_tokens` > 0 e `usage.output_tokens` > 0
- `session_id` preenchido (UUID da conversa)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H4 — sync_efos: run completo end-to-end

**Condição inicial:** Secrets EFOS no Infisical, banco com migrations 0018–0023 aplicadas
**Ação:** `python -m integrations.jobs.sync_efos --tenant jmb`
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

**Condição inicial:** H4 passou (sync bem-sucedido já registrado)
**Ação:** Executar `python -m integrations.jobs.sync_efos --tenant jmb` novamente sem `--force`
**Resultado esperado:**
- Exit code 0
- Log contém "checksum já importado" ou "skip"
- Contagem em `commerce_products` não muda (sem duplicatas)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H6 — Tool gestor: relatório de vendas por representante

**Condição inicial:** H4 passou (commerce_* populado com dados EFOS)
**Ação:** Gestor envia via WhatsApp: `"Relatório de vendas do representante Rondinele mês 4"`
**Resultado esperado:** Resposta estruturada com:
- Total vendido em R$ no mês 4
- Quantidade de pedidos
- Lista dos principais clientes atendidos
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
**Resultado esperado:** Lista de todos os inativos de qualquer cidade (sem filtro geográfico)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H10 — Fuzzy match de nome de representante

**Condição inicial:** H6 passou
**Ação:** Gestor envia: `"vendas do representante rondinele ritter mês 4"` e depois `"vendas do RONDINELE mês 4"`
**Resultado esperado:** Ambas as consultas retornam os mesmos dados (mesmo representante resolvido)
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

### H11 — Sem regressão: fluxo normal de pedido cliente

**Condição inicial:** Staging com seed de dados básicos
**Ação:** Cliente faz pedido completo: buscar produto → adicionar → confirmar (`sim`)
**Resultado esperado:**
- Pedido aparece no banco com status correto
- PDF gerado e enviado ao cliente
- Gestor recebe notificação com PDF (Sprint 7)
- Nenhum erro nos logs
**Resultado:** [ ] PASSOU / [ ] FALHOU
**Observações:** ___

---

## Resultado final

**Veredicto:** [ ] APROVADO / [ ] REPROVADO
**Data:** ___

**Bugs encontrados:**
- [ ] nenhum

**Se REPROVADO — bugs para hotfix antes do Sprint 9:**

| ID | Descrição | Severidade |
|----|-----------|------------|
| | | |

---

**Próximos passos após APROVADO:**
1. `git tag v0.7.0`
2. Mover `sprint-8-efos-backup.md` e `homologacao_sprint-8.md` para `docs/exec-plans/completed/`
3. Atualizar `docs/PLANS.md`: Sprint 8 → ✅
4. Registrar novos gotchas descobertos em `docs/GOTCHAS.yaml`
5. Iniciar Sprint 9: migração reads do agente para `commerce_*` + dashboard sync status
