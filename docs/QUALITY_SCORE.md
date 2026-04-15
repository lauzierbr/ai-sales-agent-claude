# Quality Score — AI Sales Agent

Grade de qualidade por domínio e camada. Atualizado ao final de cada sprint
pelo Evaluator. Permite rastrear gaps e priorizar melhoria contínua.

Escala: ✅ Completo | 🟡 Parcial | 🔲 Não iniciado | ❌ Com débito

## Por domínio

| Domínio | Types | Config | Repo | Service | Runtime | UI | Testes | Docs |
|---------|-------|--------|------|---------|---------|-----|--------|------|
| catalog | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | 🟡 |
| orders | ✅ | ✅ | ✅ | ✅ | ✅ | 🔲 | ✅ | ✅ |
| agents | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| tenants | ✅ | 🔲 | ✅ | ✅ | — | ✅ | ✅ | ✅ |
| providers | — | — | — | — | ✅ | — | ✅ | ✅ |

> **catalog/runtime**: crawler 🟡 (EfosHttpCrawler funciona, scheduler integrado)  
> **catalog/ui**: 🟡 (schedule endpoints adicionados, sem auth em GET/PUT schedule — Sprint 3)  
> **orders/ui**: 🔲 (painel de pedidos — Sprint 4)  

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

## Tech debt tracker

Ver docs/exec-plans/tech-debt-tracker.md

---
Atualizado por: Evaluator | Sprint: 2 | Data: 2026-04-15
