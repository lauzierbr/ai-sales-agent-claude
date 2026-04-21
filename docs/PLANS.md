# Planos de Execução — AI Sales Agent

Para planos detalhados com progresso, ver `docs/exec-plans/`.

## Roadmap

| Sprint | Status | Tipo | Descrição |
|--------|--------|------|-----------|
| Infra-Dev | ✅ | Infra | Ambiente desenvolvimento (mac-lablz) |
| Infra-Staging | ✅ | Infra | Ambiente staging (macmini-lablz) |
| Sprint 0 | ✅ | Produto | Catálogo — crawler + enriquecimento |
| Sprint 1 | ✅ | Produto | Infraestrutura da aplicação |
| Sprint 2 | ✅ | Produto | Agente cliente completo |
| Sprint 3 | ✅ | Produto | AgentRep + Hardening linguagem brasileira |
| Sprint 4 | ✅ | Produto | Painel do gestor |
| Sprint 5-teste | ✅ | Harness | Validação harness v2 — top produtos (gates mecânicos) |
| Sprint 5 | ✅ | Produto | Observabilidade LLM, feedback, UX dashboard, contatos — v0.6.0 |
| Sprint 6 | 🔄 | Hardening | Pre-pilot hardening do dashboard e baseline operacional mínimo |

## Sprints de infra (executados via Claude Code direto, sem harness)

### Sprint Infra-Dev — mac-lablz
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
- [ ] SSH mac-lablz → macmini-lablz configurado e testado
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

### Sprint 6 — Pre-Pilot Hardening 🔄 Em planejamento
Plano detalhado: `docs/exec-plans/active/sprint-6-pre-pilot-hardening.md`

Escopo previsto:
- corrigir cadastro de cliente via dashboard
- corrigir upload de preços via dashboard
- revisar fluxo/navegação de top produtos
- revisar queries do dashboard com foco em tenant isolation
- validar secrets críticos no startup
- aplicar rate limiting em login do dashboard e webhook WhatsApp
- expor monitoramento/health check para falhas Anthropic
- ajustar CORS/cookie por ambiente
- expandir testes críticos do dashboard
- fechar smoke e homologação pré-piloto

### Sprints futuros (backlog)
- Sugestão proativa por ciclo de compra
- Push ativo WhatsApp (promoções, alertas)
- Onboarding de segundo tenant
- Enriquecimento OTEL: spans filhos por tool call nos 3 agentes + dashboards Grafana de latência e taxa de erro
