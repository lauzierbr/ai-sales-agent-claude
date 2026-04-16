# Planos de Execução — AI Sales Agent

Para planos detalhados com progresso, ver `docs/exec-plans/`.

## Roadmap

| Sprint | Status | Tipo | Descrição |
|--------|--------|------|-----------|
| Infra-Dev | ✅ | Infra | Ambiente desenvolvimento (mac-lablz) |
| Infra-Staging | ✅ | Infra | Ambiente staging (mac-mini-lablz) |
| Sprint 0 | ✅ | Produto | Catálogo — crawler + enriquecimento |
| Sprint 1 | ✅ | Produto | Infraestrutura da aplicação |
| Sprint 2 | ✅ | Produto | Agente cliente completo |
| Sprint 3 | 🔲 | Produto | Agente representante |
| Sprint 4 | 🔲 | Produto | Painel do gestor |
| Sprint 5 | 🔲 | Produto | Inteligência e escala |

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

### Sprint Infra-Staging — mac-mini-lablz
**Pré-requisito:** Sprint Infra-Dev completo.

Entregas:
- [ ] SSH mac-lablz → mac-mini-lablz configurado e testado
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

### Sprint 4 — Painel do gestor
- Dashboard de pedidos em tempo real
- Monitor de conversas ativas
- Gestão de clientes e representantes
- Upload de planilha de preços
- Configuração do agente por tenant

### Sprint 5 — Inteligência e escala
- Sugestão proativa por ciclo de compra
- Push ativo WhatsApp (promoções, alertas)
- Relatórios de performance por representante
- Onboarding de segundo tenant
- Doc-gardening agent (verifica documentação vs código)
