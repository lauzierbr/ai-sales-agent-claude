# Quality Score — AI Sales Agent

Grade de qualidade por domínio e camada. Atualizado ao final de cada sprint
pelo Evaluator. Permite rastrear gaps e priorizar melhoria contínua.

Escala: ✅ Completo | 🟡 Parcial | 🔲 Não iniciado | ❌ Com débito

## Por domínio

| Domínio | Types | Config | Repo | Service | Runtime | UI | Testes | Docs |
|---------|-------|--------|------|---------|---------|-----|--------|------|
| catalog | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 |
| orders | ✅ | ✅ | ✅ | ✅ | ✅ | 🔲 | ✅ | ✅ |
| agents | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| tenants | ✅ | 🔲 | ✅ | ✅ | — | ✅ | ✅ | ✅ |
| providers | — | — | — | — | ✅ | — | ✅ | ✅ |
| dashboard | — | — | — | — | — | ✅ | ✅ | ✅ |

> **catalog/runtime**: crawler 🟡 (EfosHttpCrawler funciona, scheduler integrado)  
> **catalog/ui**: ✅ precos/upload POST (Sprint 6); schedule endpoints 🟡 sem auth em GET/PUT  
> **orders/ui**: 🔲 (painel de pedidos — Sprint 4)  
> **dashboard**: ✅ rate-limit login, cookie Secure, tenant isolation, startup validation, CORS env-aware (Sprint 6)  

## Por critério transversal

| Critério | Status | Notas |
|----------|--------|-------|
| import-linter configurado | ✅ | 5/5 contratos KEPT (Sprint 1) |
| OpenTelemetry instrumentado | ✅ | Service + scheduler_job com spans (Sprint 1) |
| structlog em todo o código | ✅ | Zero print(); from_number_hash em webhook (Sprint 1) |
| Isolamento de tenant testado | ✅ | 4 testes @integration + mocks (Sprint 1) |
| Cobertura de testes > 80% | ✅ | agents/service 93%, agents/repo 84%, orders/* 82-87% (Sprint 2) |
| Secrets via Infisical (0 hardcode) | ✅ | Verificado Sprint 1 |
| mypy --strict | ✅ | 0 erros — resolvido na homologação Sprint 1 |
| Docs sincronizadas com código | 🟡 | ADRs D019-D022 atualizados (Sprint 5 doc-gardening) |
| Harness v2 gates mecânicos | ✅ | G2/G3/G5/G7 validados — detectam 4/4 bugs sem inspeção visual (Sprint 5-teste) |
| Smoke exit-code confiável | ✅ | `smoke_sprint_5_teste.sh` exit 1 em falha (débito R2 corrigido) |
| Startup validation (9 secrets) | ✅ | `_validate_secrets()` lista secrets faltantes; RuntimeError no boot (Sprint 6) |
| Rate limiting (login + webhook) | ✅ | Redis; 5 falhas/IP/15min login; 30/min/instance+jid webhook (Sprint 6) |
| Anthropic health endpoint | ✅ | `/health` ok/degraded/fail com componente anthropic (Sprint 6) |
| CORS por ambiente | ✅ | Sem wildcard em staging/production; cookie Secure=True apenas em production (Sprint 6) |
| Smoke gate G1-G9 cobertura | ✅ | POST precos/upload (G7), POST clientes/novo+verify (G8), webhook burst 429 (G9) adicionados Sprint 6 |
| M_INJECT — deps não-None | ✅ | test_ui_injection.py: AgentGestor, AgentCliente, AgentRep verificados em staging (Sprint 6) |

## Tech debt tracker

Ver docs/exec-plans/tech-debt-tracker.md

### Débitos conhecidos (não Sprint 6)

| Débito | Origem | Impacto |
|--------|--------|---------|
| 12 falhas staging Sprint 3-5 | seed_data_ausente (5), asyncio loop (2), FakeRedis setex (4), agents/repo coroutine (1) | Testes de sprints anteriores — não regressões Sprint 6 |
| orders/ui painel de pedidos | Sprint 4 | Dashboard sem view de pedidos |
| catalog/schedule sem auth | Sprint 3 | GET/PUT schedule endpoints sem autenticação |

---
Atualizado por: Evaluator | Sprint: 6 | Data: 2026-04-21
