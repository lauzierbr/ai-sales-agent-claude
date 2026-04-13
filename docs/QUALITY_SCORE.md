# Quality Score — AI Sales Agent

Grade de qualidade por domínio e camada. Atualizado ao final de cada sprint
pelo Evaluator. Permite rastrear gaps e priorizar melhoria contínua.

Escala: ✅ Completo | 🟡 Parcial | 🔲 Não iniciado | ❌ Com débito

## Por domínio

| Domínio | Types | Config | Repo | Service | Runtime | UI | Testes | Docs |
|---------|-------|--------|------|---------|---------|-----|--------|------|
| catalog | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 |
| orders | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 |
| agents | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 |
| tenants | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 |
| providers | — | — | — | — | 🔲 | — | 🔲 | 🔲 |

## Por critério transversal

| Critério | Status | Notas |
|----------|--------|-------|
| import-linter configurado | 🔲 | Sprint Infra-Dev |
| OpenTelemetry instrumentado | 🔲 | Sprint 1 |
| structlog em todo o código | 🔲 | Sprint 1 |
| Isolamento de tenant testado | 🔲 | Sprint 1 |
| Cobertura de testes > 80% | 🔲 | — |
| Secrets via Infisical (0 hardcode) | 🔲 | Sprint Infra-Dev |
| Docs sincronizadas com código | 🔲 | Sprint 5 (doc-gardening) |

## Tech debt tracker

Ver docs/exec-plans/tech-debt-tracker.md

---
Atualizado por: Evaluator | Sprint: - | Data: -
