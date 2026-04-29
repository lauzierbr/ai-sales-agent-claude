# Planos de Execução — AI Sales Agent

Para planos detalhados com progresso, ver `docs/exec-plans/`.

## Roadmap

| Sprint | Status | Tipo | Descrição |
|--------|--------|------|-----------|
| Infra-Dev | ✅ | Infra | Ambiente desenvolvimento (macmini-lablz) |
| Infra-Staging | ✅ | Infra | Ambiente staging (macmini-lablz) |
| Sprint 0 | ✅ | Produto | Catálogo — crawler + enriquecimento |
| Sprint 1 | ✅ | Produto | Infraestrutura da aplicação |
| Sprint 2 | ✅ | Produto | Agente cliente completo |
| Sprint 3 | ✅ | Produto | AgentRep + Hardening linguagem brasileira |
| Sprint 4 | ✅ | Produto | Painel do gestor |
| Sprint 5-teste | ✅ | Harness | Validação harness v2 — top produtos (gates mecânicos) |
| Sprint 5 | ✅ | Produto | Observabilidade LLM, feedback, UX dashboard, contatos — v0.6.0 |
| Sprint 6 | ✅ | Hardening | Pre-pilot hardening — rate limit, startup validation, CORS, health Anthropic — v0.6.1 APROVADO |
| **Piloto JMB** | 🚀 | Piloto | Teste com usuários reais iniciado 2026-04-22 — banco limpo, staging em v0.6.1 |
| Sprint 7 | ✅ | Produto | Notificação gestor (TD-08) — v0.7.0, homologado em conjunto com Sprint 9 (29/04/2026) |
| Sprint 8 | ✅ | Produto | Hotfixes piloto (B-10/B-11/B-12) + integração EFOS via backup diário SSH/pg_restore + 3 tools relatório AgentGestor — v0.8.0, homologado com Sprint 9 (29/04/2026) |
| Sprint 9 | ✅ | Produto | Hotfix B-13 + leituras commerce_* + dashboard sync + áudio Whisper + 4 hotfixes pós-homologação (B-14 a B-22, B-31, B-32, formato BR, KPIs mensais) — v0.9.4, homologado 29/04/2026 com 11 bugs abertos para Sprint 10 |
| Sprint 10 | 🔄 | Produto | **Em planejamento** — hotfixes críticos (B-26 truncação histórico, B-23/B-24 áudio, B-25 ranking, B-30 Langfuse, B-29) + foundations D030 (tabela `contacts`) + F-07 controle frequência sync + deprecação catalog legado |

## Sprints de infra (executados via Claude Code direto, sem harness)

### Sprint Infra-Dev — macmini-lablz
**Pré-requisito:** todos os sprints de produto dependem desta infra.

Entregas:
- [ ] Docker Desktop verificado
- [ ] PostgreSQL 16 + pgvector via Docker (5432)
- [ ] Redis 7 via Docker (6379)
- [ ] Evolution API via Docker (8080)
- [ ] VictoriaMetrics via Docker (8428)
- [ ] VictoriaLogs via Docker (9428)
- [ ] OTEL Collector via Docker (4317/4318)
- [ ] Grafana via Docker (3000)
- [ ] `docker-compose.dev.yml` funcional e commitado
- [ ] Playwright instalado com chromium (`playwright install chromium`)
- [ ] Infisical CLI configurado, projeto `ai-sales-agent` inicializado
- [ ] Ambiente `development` no Infisical com todas as variáveis
- [ ] Script `scripts/health_check.py` validando todos os serviços
- [ ] import-linter configurado no `pyproject.toml`

### Sprint Infra-Staging — macmini-lablz
**Pré-requisito:** Sprint Infra-Dev completo.

Entregas:
- [ ] SSH macmini-lablz → macmini-lablz configurado e testado
- [ ] Mesmos serviços do Infra-Dev no mac-mini
- [ ] `docker-compose.staging.yml` commitado
- [ ] Ambiente `staging` no Infisical com variáveis
- [ ] `scripts/deploy.sh` funcional
- [ ] launchd configurado para auto-start dos serviços
- [ ] Health check remoto via deploy script

## Sprints de produto (executados via harness Planner/Generator/Evaluator)

### Sprint 0 — Catálogo
**Pré-requisito:** Sprint Infra-Dev.
Plano detalhado: `docs/exec-plans/active/sprint-0-catalogo.md` (criado pelo Planner)

Escopo previsto:
- Playwright crawler EFOS com autenticação (tenant JMB)
- Pipeline enriquecimento Haiku: nome, marca, tags, texto_rag, meta_agente
- pgvector: embeddings e busca semântica
- Upload Excel preços diferenciados
- Painel simples de revisão de produtos

### Sprint 1 — Infraestrutura da aplicação
**Pré-requisito:** Sprint Infra-Dev + Sprint 0.

- FastAPI com middleware TenantProvider
- Webhook Evolution API → Identity Router
- Schema PostgreSQL multi-tenant (schema por tenant)
- Resposta básica WhatsApp por persona
- OpenTelemetry instrumentado desde o início

### Sprint 2 — Agente cliente completo ✅ APROVADO — v0.3.0
Homologado em 2026-04-15. Tag v0.3.0.

Entregue:
- AgentCliente com Claude SDK (claude-sonnet-4-6), ferramentas buscar_produtos e confirmar_pedido
- Domínio Orders: OrderService, OrderRepo, PDFGenerator (fpdf2), migrations 0007–0012
- IdentityRouter real (lookup DB: clientes_b2b, representantes)
- ConversaRepo + Redis TTL 24h (memória de conversa)
- send_whatsapp_media (PDF para gestor via Evolution API)
- Busca semântica com text-embedding-3-small (pgvector) + lookup exato por código
- Webhook signature: token simples (não HMAC) + filtro fromMe=True

Bugs corrigidos na homologação (pós-QA):
- asyncpg + pgvector ORDER BY silencioso → sort em Python
- session.commit() ausente → rollback silencioso
- catalog_service=None em ui.py
- distancia_maxima 0.4 → 0.75

RCA documentado → prompts atualizados com @pytest.mark.staging, smoke gate
obrigatório, critérios A_SMOKE e M_INJECT no contrato.

### Sprint 3 — Agente representante
- AgentRep com ferramentas específicas
- Pedido em nome de cliente da carteira
- Preço de custo e margem (visível apenas para rep)
- Alertas proativos de clientes inativos

### Sprint 4 — Gestor/Admin ✅ APROVADO — v0.5.0
Homologado em 2026-04-20. Tag v0.5.0.

Entregue:
- AgentGestor WhatsApp: acesso irrestrito, relatórios, ranking reps, clientes inativos, pedidos por status
- Aprovar pedidos: Gestor (todos), Rep (carteira com validação), Cliente (read-only)
- Listar pedidos: `listar_pedidos_por_status` (Gestor), `listar_pedidos_carteira` (Rep), `listar_meus_pedidos` (Cliente)
- Dashboard web: Jinja2 + htmx + CSS puro; 8 páginas; auth cookie JWT; KPIs tempo real (polling 30s)
- Migration 0015: tabela `gestores` + índice `ix_pedidos_tenant_criado_em`
- IdentityRouter: prioridade `gestores → representantes → clientes_b2b` (DP-02)
- DP-03: `representante_id` herdado do cliente em pedidos do gestor
- Auto-recovery Redis: detecta histórico corrompido (400 tool_use_id), limpa e retenta
- WhatsApp formatting: blocos `*bold* + •`, sem tabelas markdown
- Typing indicator UX: fire-and-forget start + stop explícito só em falha (sem bloquear agente)

Bugs corrigidos na homologação (pós-QA):
- Redis history corruption (orphaned tool_result) → auto-recovery
- Capacidades anunciadas sem ferramenta → A_TOOL_COVERAGE implementado
- Parâmetro `dias` hardcoded no SQL → Python timedelta
- Typing indicator loop → race condition → iteração até solução correta
- rsync --relative → scp com destino explícito

### Sprint 4 — Gestor/Admin: persona WhatsApp + dashboard web
- **Nova persona `GESTOR`** no IdentityRouter (tabela `gestores`; prioridade sobre rep)
  - Gestor pode também ser rep no mesmo número (perfil cumulativo — DP-02)
- **AgentGestor via WhatsApp**: acesso irrestrito a clientes e pedidos
  - Consulta catálogo e faz pedido para qualquer cliente do tenant
  - Busca clientes por nome/CNPJ (todos, não só carteira)
  - Pedido para cliente com rep → herda `representante_id` do cliente (DP-03)
  - Relatório de vendas: totais por rep, por cliente, por período
  - Ranking de representantes, clientes inativos, GMV da empresa
- **Dashboard web** (ambos no Sprint 4 — DP-01):
  - Dashboard de pedidos em tempo real
  - Monitor de conversas ativas
  - Gestão de clientes e representantes
  - Upload de planilha de preços
  - Configuração do agente por tenant

### Sprint 5 — Operações, cadastro e observabilidade LLM
- Configuração de números de celular para os perfis (cliente, representante, gestor) via dashboard
- Cadastro de clientes fictícios via dashboard (temporário até integração ERP)
- Relatórios de performance por representante
- Langfuse (auto-hospedado via Docker): instrumentação dos 3 agentes com traces por tool call, custo por conversa e avaliação de qualidade
- Doc-gardening agent (verifica documentação vs código)

### Sprint 6 — Pre-Pilot Hardening ✅ APROVADO — v0.6.1
Plano detalhado: `docs/exec-plans/completed/sprint-6-pre-pilot-hardening.md`
Tag: v0.6.1 | Homologado pré-piloto

Entregue:
- Cadastro de cliente via dashboard (E1) — `TenantService.criar_cliente_ficticio()`
- Upload de preços via dashboard (E2) — `CatalogService.processar_excel_precos()`
- Top produtos: fluxo e navegação corrigidos (E3)
- Tenant isolation em 9 queries do dashboard (E4)
- Startup validation — 9 secrets obrigatórios (E5)
- Rate limiting login: 5 falhas/IP/15min → 429 (E6)
- Rate limiting webhook: 30/min/instance+jid → 429 (E7)
- Health Anthropic ok/degraded/fail + health_check.py exit ≠ 0 (E8)
- CORS por ambiente + cookie Secure apenas em production (E9)
- 281 unit tests; test_ui_injection.py; smoke G1–G9 (E10–E11)

### Sprint 7 — Notificação ao gestor ✅ APROVADO — v0.7.0
Plano detalhado: `docs/exec-plans/completed/sprint-7-notificacao-gestor.md`
Tag: v0.7.0 | Homologado em conjunto com Sprint 9 (29/04/2026)

**Contexto:** durante piloto JMB descobriu-se que `tenant.whatsapp_number = None`,
fazendo notificações ao gestor falharem silenciosamente (B-01 / TD-08). Sprint 7
introduz `GestorRepo.listar_ativos_por_tenant()` e itera sobre todos os gestores
ativos do tenant.

Entregue:
- E1 — `GestorRepo.listar_ativos_por_tenant(tenant_id)` em `agents/repo.py`
- E2 — AgentCliente: loop sobre gestores ativos para enviar PDF do pedido
- E3 — AgentRep: mesmo padrão com caption incluindo nome do rep
- E4 — Testes unitários `test_gestor_repo.py` + atualização A8/A8b
- E5 — Smoke script `scripts/smoke_sprint_7.py`

Lições registradas:
- A_TOOL_COVERAGE obrigatório (capacidade anunciada deve ter tool e teste)

### Sprint 8 — Integração EFOS via backup diário SSH/pg_restore ✅ APROVADO — v0.8.0
Plano detalhado: `docs/exec-plans/completed/sprint-8-efos-backup.md`
Tag: v0.8.0 | Homologado em conjunto com Sprint 9 (29/04/2026)

**Contexto:** aposentar crawler Playwright (frágil, lento, anti-bot) e consumir
dados do dump diário do EFOS via SSH/SFTP + `pg_restore` em staging DB
isolado, normalizando para o read model `commerce_*`.

Entregue:
- Domínio `integrations/` (5º) com `EFOSBackupConfig`, `SyncRunRepo`, `SyncArtifactRepo`
- Conector `efos_backup` em 4 módulos: acquire (SSH+SFTP+SHA-256), stage
  (`pg_restore --format=c` via `docker exec ai-sales-postgres`), normalize
  (tb_itens/clientes/pedido/itenspedido/estoque/vendas/vendedor → commerce_*),
  publish (transação atômica com DELETE+INSERT)
- Domínio `commerce/` (6º) — read model puro com `CommerceRepo`
- Migrations 0018–0023 (sync_runs, sync_artifacts, commerce_products,
  commerce_accounts_b2b, commerce_orders+items, commerce_inventory,
  commerce_sales_history, commerce_vendedores)
- CLI `python -m integrations.jobs.sync_efos --tenant jmb [--dry-run] [--force]`
  com idempotência por checksum SHA-256
- launchd plist agendando 13:00 BRT diário
- Hotfixes piloto: B-10 (representante_id em get_by_telefone), B-11
  (Redis stale na troca de persona), B-12 (instrumentação Langfuse — parcial,
  ver B-30 em Sprint 10)
- 3 tools EFOS no AgentGestor: `relatorio_vendas_representante_efos`,
  `relatorio_vendas_cidade_efos`, `clientes_inativos_efos` (com fuzzy match
  + normalização de mês/cidade)

ADRs aprovados:
- D025 (paramiko SSH/SFTP), D026 (efos_staging isolado), D027 (CLI one-shot
  vs FastAPI lifespan), D028 (launchd vs APScheduler), D029 (read model
  separado do write model)

Lições registradas (gotchas):
- pg_restore custom format requer `--format=c` explícito
- `tb_vendedor` tem `ve_codigo` duplicado por filial (DISTINCT ON)
- Cidades EFOS são UPPERCASE (normalizar antes de match)
- Postgres em Docker no macmini → usar `docker exec` para psql/pg_restore

### Sprint 9 — Commerce reads + dashboard sync + áudio Whisper ✅ APROVADO — v0.9.4
Plano detalhado: `docs/exec-plans/completed/sprint-9-commerce-audio.md`
Fechamento: `docs/exec-plans/completed/sprint-9-fechamento.md`
Tags: v0.9.0, v0.9.1, v0.9.2, v0.9.3, v0.9.4 | Homologado 29/04/2026

**Contexto:** com `commerce_*` populado pelo Sprint 8, os agentes e dashboard
ainda liam das tabelas legadas vazias após reset. Sprint 9 migra leituras
com fallback, adiciona dashboard de sync EFOS, áudio WhatsApp via Whisper
e corrige B-13 (busca por EAN completo).

Entregas iniciais (v0.9.0):
- Hotfix B-13: busca EAN completo via `query[-6:]` quando query é numérica
  com > 6 dígitos (3 agentes)
- E1a: `catalog/service.py` lê `commerce_products` com fallback para `produtos`
- E1b: `agents/repo.py` fallback `commerce_accounts_b2b` quando `clientes_b2b` vazio
- E2: dashboard bloco "Última sincronização EFOS" (depois removido em v0.9.4)
- E3: áudio WhatsApp via Whisper (`audioMessage` → transcrição → prefixo 🎤)
- Migration 0024: `pedidos.ficticio` + PDF watermark + caption ⚠️ TESTE
- E0-B: AgentGestor — tools antigas removidas, EFOS assumiu o lugar
- Convenção de versionamento `v0.{SPRINT}.{HOTFIX}` + auto-tag deploy
- Badge de versão discreto no dashboard (top-left)

Hotfixes pós-homologação (4 iterações):
- v0.9.1: migração exaustiva — corrige B-14 (listar_pedidos_por_status),
  B-15 (listar_representantes), B-16 (/clientes), B-17 (/pedidos),
  B-18 (sync-status visível), B-19 (KPIs com fallback), B-20 (top-produtos),
  B-21 (rota /representantes na nav), B-22 (emojis no system prompt)
- v0.9.2: formatação monetária pt-BR centralizada (B-31) — função
  `providers/format.py:format_brl()` + filter Jinja `|brl` em 7 templates
- v0.9.3: KPIs HOJE não inflam com histórico EFOS (B-32) — removido
  fallback `efos_total` que mostrava 2592 pedidos cumulativos como "hoje"
- v0.9.4: UX KPIs janela mensal — "GMV Abril/2026" + "Atualizado no sync
  EFOS 27/04/2026 17:42"; removido bloco redundante "Última sincronização EFOS"

ADRs aprovados durante o sprint:
- **D030** — ERP adapter pattern + canonical contact ownership no app
  (App é dono de canais/contatos, ERP é dono de cadastro fiscal). Bling
  como ERP alvo principal.
- **D031** — AnalystAgent meta-agente de observabilidade (persona admin
  consulta Langfuse, extrai custo/anomalias/qualidade). Sprint 11.

Documentação criada:
- `docs/VERSIONING.md` — convenção `v0.{SPRINT}.{HOTFIX}` e auto-tag
- `docs/PRE_HOMOLOGATION_REVIEW.md` — protocolo concreto (10 rotas dashboard
  + 13+ cenários bot por persona) — obrigatório antes de declarar pronto
- `docs/DEPRECATIONS.md` — plano de remoção do catalog legado (Sprint 10)

Lições registradas em prompts:
- A_BEHAVIORAL obrigatório em sprints com agente/dashboard (browser real)
- Migração exaustiva via grep antes de declarar fase concluída
- Investigação de Langfuse via API (não só UI) para validar generations
- Modelos por agente: Opus para Evaluator/PO, Sonnet para Generator,
  Haiku para Tester

Bugs abertos para Sprint 10 (ver `sprint-9-fechamento.md`):
- Críticos: B-26 (truncação histórico), B-27/B-28 (clientes EFOS — D030)
- Altos: B-23 (áudio criptografia), B-24 (capacidade áudio), B-25 (ranking)
- Médios: B-30 (Langfuse generations), B-29 (log noise persona_key)

### Sprint 10 — Hotfixes críticos + foundations D030 🔄 Em planejamento
Plano detalhado: a ser criado pelo Planner em `docs/exec-plans/active/sprint-10-*.md`
Versão alvo: v0.10.0

Escopo confirmado pelo PO (29/04/2026):

**Hotfixes críticos:**
- B-26 — truncação cega do histórico Redis (afeta 3 agentes — recovery destrutivo)
- B-27 — cadastro contato cliente NO-OP (resolução estrutural via D030)
- B-28 — pedido em nome de cliente EFOS falha (resolução via D030)
- B-23 — áudio Whisper rejeita criptografia E2E (usar endpoint Evolution API)
- B-24 — bot nega capacidade de áudio (system prompt + fallback direto)
- B-25 — ranking ineficiente + ano default + contexto temporal
- B-30 — Langfuse continua sem tokens/custo (B-12 só parcial — wrapper Anthropic)
- B-29 — log noise persona_key (decode em str já decodada)

**Foundations D030:**
- Migration: tabela `contacts` (PF, write model) referenciando `commerce_accounts_b2b.external_id`
- Migration: `pedidos.account_external_id VARCHAR` (substituindo FK rígida)
- Migration: estender `commerce_accounts_b2b` com `contato_padrao`, `telefone`,
  `email` (campos perdidos no Sprint 8)
- Dashboard `/dashboard/contatos` refeito conforme D030 (busca em commerce, INSERT em contacts)
- `/dashboard/clientes` read-only (sem botão "Novo Cliente")
- Auto-criação de `contacts` `origin='self_registered'` quando número desconhecido manda mensagem
- Notificação dual ao gestor (dashboard + WhatsApp) com candidato em `commerce_accounts_b2b`

**F-07 — Controle de frequência sync EFOS (temporário):**
- Migration: `sync_schedule`
- Tela `/dashboard/sync` (admin only) com 5 presets + toggle + "Rodar agora"
- Migração `launchd` → APScheduler interno
- Redis lock anti-overlap

**Deprecação catalog legado:**
- Pré-condição: migrar embeddings vector(1536) para `commerce_products`
  (atualmente em `produtos` — usado pela busca semântica do AgentCliente)
- Job batch que enriquece embeddings via OpenAI text-embedding-3-small
- Atualizar `AgentCliente._buscar_produtos` para ler de `commerce_products`
- Remover: crawler Playwright, EnricherAgent, scheduler_job, painel,
  template, rotas, tabela `produtos`, dependência `playwright`

### Sprint 11 — AnalystAgent MVP (D031)
Não iniciado. Spec a ser feito após Sprint 10 estabilizar.
Pré-requisito: B-30 corrigido (sem generations no Langfuse, não há o que analisar).

### Sprint 12+ — Bling adapter (D030)
Não iniciado. Discussão estratégica em thread separada do PO.

### Sprints futuros (backlog)
- Sugestão proativa por ciclo de compra
- Push ativo WhatsApp (promoções, alertas)
- Onboarding de segundo tenant
- Enriquecimento OTEL: spans filhos por tool call nos 3 agentes + dashboards Grafana de latência e taxa de erro
- F-02b — imagem/código de barras no WhatsApp (após F-02a áudio estar estável)
- F-03 — status e versão de entrega no feedback
- F-06 — Painel de Divergências do Catálogo ERP (pós-Bling)
