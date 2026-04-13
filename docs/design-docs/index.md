# Decisões Arquiteturais — AI Sales Agent

Log de decisões técnicas. Atualizar sempre que uma nova decisão for tomada.

## Índice

| ID | Título | Sprint | Status |
|----|--------|--------|--------|
| D001 | Produto SaaS multi-tenant desde o início | Planejamento | ok |
| D002 | Infisical para gestão de secrets | Planejamento | ok |
| D003 | Claude Agent SDK + FastAPI + PostgreSQL | Planejamento | ok |
| D004 | Evolution API para WhatsApp | Planejamento | ok |
| D005 | Preço padrão via crawler, diferenciados via Excel | Planejamento | ok |
| D006 | Crawler apenas do site B2B | Planejamento | ok |
| D007 | Harness com sprints (não rounds autônomos) | Planejamento | ok |
| D008 | Deploy inicial no mac-mini-lablz | Planejamento | ok |
| D009 | Crawler via Playwright (não API REST) | Planejamento | ok |
| D010 | Sprints de infra antes do Sprint 0 | Planejamento | ok |
| D011 | Sprints de infra via Claude Code direto | Planejamento | ok |
| D012 | Repository knowledge como system of record | Planejamento | ok |
| D013 | Arquitetura em camadas fixas (Types→UI) | Planejamento | ok |
| D014 | VictoriaMetrics + VictoriaLogs para observabilidade | Planejamento | ok |
| D015 | Memory Stores: separação e mapeamento (Managed Agents Fase 2) | Planejamento | ok |

---

## D012 — Repository knowledge como system of record
Inspirado no artigo da OpenAI "Harness Engineering" (fev/2026).
AGENTS.md é mapa (~80 linhas), não enciclopédia. Conteúdo vive em docs/.
Conhecimento que não está no repo não existe para o agente.

## D013 — Arquitetura em camadas fixas (Types → Config → Repo → Service → Runtime → UI)
Inspirado no artigo da OpenAI. Agentes replicam padrões em escala.
Camadas fixas com import-linter enforçadas mecanicamente no CI.
Violações bloqueiam com mensagens de remediação injetadas no contexto do agente.

## D014 — VictoriaMetrics + VictoriaLogs para observabilidade
Single binary, PromQL + LogQL, extremamente leve para mac-mini.
OpenTelemetry desde Sprint 1 permite que o Evaluator consulte métricas
diretamente — prompts como "garanta latência < 3s p95" se tornam verificáveis.

(Decisões D001-D011 em docs/design-docs/decisoes-planejamento.md)
