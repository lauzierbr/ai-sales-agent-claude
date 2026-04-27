# Sprint 8 — Hotfixes Piloto + Integração EFOS via Backup Diário

**Status:** Em planejamento
**Versão alvo:** v0.7.0
**Data início:** 2026-04-27

---

## Objetivo

Corrigir os bugs B-10/B-11/B-12 encontrados no piloto JMB e entregar o pipeline
SSH/pg_restore que popula o read model `commerce_*`, mais 3 tools de relatório no
AgentGestor baseados em dados reais do EFOS.

---

## Checklist de entregas

### Fase 0 — Hotfixes do piloto
- [ ] **E0-A** — B-10: `representante_id` no SELECT de `get_by_telefone()` (`repo.py:109`, `ui.py:297`)
- [ ] **E0-B** — B-11: invalidar chaves Redis ao trocar persona (`ui.py` IdentityRouter)
- [ ] **E0-C** — B-12: wrapper Langfuse + `session_id` + `output` nos 3 agentes

### Fase 1 — Pipeline EFOS
- [ ] **E1** — Domínio `integrations/`: types, config (EFOSBackupConfig), repo (SyncRunRepo, SyncArtifactRepo)
- [ ] **E2** — Conector `efos_backup`: acquire, stage, normalize, publish
- [ ] **E3** — Migrations 0018–0023 (sync_runs, sync_artifacts, commerce_*)
- [ ] **E4** — CLI `sync_efos` + launchd plist

### Fase 2 — Queries do gestor via commerce_*
- [ ] **E5** — Domínio `commerce/`: types + CommerceRepo com 3 métodos
- [ ] **E6** — AgentGestor: 3 novos tools + fuzzy matching + normalização cidade/mês
- [ ] **E7** — Testes unitários completos (`pytest -m unit` passa, cobertura ≥ 80%)
- [ ] **E8** — `ARCHITECTURE.md` + ADRs D025–D029 em `docs/design-docs/index.md`

---

## Log de decisões

| Data | Decisão |
|------|---------|
| 2026-04-24 | Schema EFOS confirmado via SSH: tb_itens(1189), tb_clientes(1038), tb_pedido(2589), tb_itenspedido(29394), tb_vendas, tb_estoque |
| 2026-04-24 | D026: sem conexão direta ao Postgres EFOS — usar dump SSH/pg_restore |
| 2026-04-25 | D027: CLI one-shot worker (não FastAPI lifespan) |
| 2026-04-25 | D028: launchd no macmini (não APScheduler do app) |
| 2026-04-25 | D029: read model commerce_* separado do write model do app |
| 2026-04-25 | D025: paramiko para SSH/SFTP |
| 2026-04-27 | Planner concluiu spec — Sprint 8 em planejamento |

---

## Notas de execução

### Secrets no Infisical — obrigatório antes da Fase 1

O Generator deve verificar que os 6 secrets abaixo existem no Infisical nos ambientes
`development` e `staging` antes de iniciar a implementação da Fase 1:

```
JMB_EFOS_SSH_HOST          = jmbdistribuidora.ddns.com.br
JMB_EFOS_SSH_USER          = suporte
JMB_EFOS_SSH_KEY_PATH      = ~/.ssh/oci-lablz-01
JMB_EFOS_BACKUP_REMOTE_PATH = C:\BACKUP EFOS\
JMB_EFOS_ARTIFACT_DIR      = /var/efos-artifacts   (ou outro caminho absoluto local)
JMB_EFOS_STAGING_DB_URL    = postgresql://localhost/efos_staging
```

### Ordem recomendada de implementação

```
1. Fase 0 completa  →  pytest -m unit  →  0 falhas novas
2. E3 (migrations)  →  alembic upgrade head  →  tabelas commerce_* existem
3. E1 (integrations types/config/repo)
4. E2 (conector acquire+stage+normalize+publish)  →  pytest -m unit integrations/
5. E4 (CLI sync_efos + launchd plist)
6. E5 (commerce/ types+repo)  →  pytest -m unit commerce/
7. E6 (AgentGestor 3 tools)  →  pytest -m unit agents/ (gestor)
8. E7 (testes consolidados)  →  pytest -m unit  →  cobertura ≥ 80%
9. E8 (ARCHITECTURE.md + ADRs)
10. scripts/smoke_sprint_8.py  →  ALL OK
```

### Gotchas críticos para o Generator

- `pg_restore` requer `--format=c` explícito — sem a flag, falha silenciosamente
- `tb_vendedor` tem `ve_codigo` duplicado por filial — usar `DISTINCT ON (ve_codigo)`
- Cidades no EFOS são UPPERCASE — normalizar input do gestor antes de qualquer comparação
- Staging DB `efos_staging` deve ser destruído em bloco `finally` (mesmo em caso de erro)
- `paramiko.pkey.PKey.from_private_key_file()` detecta tipo de chave automaticamente
- `structlog`: nunca usar `event=` como kwarg, usar string posicional

---

## Critério de "pronto para homologação" (definido pelo produto)

O Generator deve preparar o ambiente de homologação e o sprint é liberado para
Lauzier quando:
1. `./scripts/deploy.sh staging` → sem erros
2. `alembic upgrade head` no banco de staging
3. `python scripts/smoke_sprint_8.py` → `ALL OK`

Não é necessário aprovação formal do Evaluator para liberar ao Lauzier —
o smoke gate é suficiente. A homologação manual valida o comportamento de ponta a ponta.

## Critério de aprovação final (pós-homologação)

O sprint é marcado APROVADO após homologação humana H1–H11 todos PASSOU
(ver `homologacao_sprint-8.md`). Bugs encontrados na homologação viram hotfixes
antes do Sprint 9.
