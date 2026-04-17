# Tech Debt Tracker — AI Sales Agent

Débitos técnicos identificados pelo Evaluator. Itens de Média que não
bloquearam aprovação mas devem ser endereçados.

## Aberto

| ID | Sprint | Domínio | Descrição | Prioridade |
|----|--------|---------|-----------|------------|
| TD-02 | Sprint 3 | Infra/Staging | `ANTHROPIC_API_KEY` sem monitoramento de saldo — chave esgotou silenciosamente em staging. Adicionar health check que valida saldo antes de iniciar homologação. | Média |
| TD-03 | Sprint 3 | Staging | `typing_indicator_erro error=''` — Evolution API retornou erro vazio no endpoint `/chat/sendPresence`. Investigar se endpoint requer formato diferente de `number` (com ou sem `@s.whatsapp.net`). | Baixa |

## Resolvido

| ID | Sprint identificado | Sprint resolvido | Descrição |
|----|---------------------|-----------------|-----------|
| TD-01 | Sprint 1 | Sprint 2 (homologação) | mypy --strict: 66 erros de anotação de tipo. Corrigidos com `dict[str, Any]`, `-> None`, `isinstance` narrowing e remoção de `# type: ignore` desnecessários. `mypy --strict` agora retorna "Success: no issues found in 64 source files". |

---
Atualizado por: Claude | Último sprint: Sprint 3 | Data: 2026-04-17
