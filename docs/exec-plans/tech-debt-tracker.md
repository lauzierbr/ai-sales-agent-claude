# Tech Debt Tracker — AI Sales Agent

Débitos técnicos identificados pelo Evaluator. Itens de Média que não
bloquearam aprovação mas devem ser endereçados.

## Aberto

| ID | Sprint | Domínio | Descrição | Prioridade |
|----|--------|---------|-----------|------------|
| TD-02 | Sprint 3 | Infra/Staging | `ANTHROPIC_API_KEY` sem monitoramento de saldo — chave esgotou silenciosamente em staging. Adicionar health check que valida saldo antes de iniciar homologação. | Média |
| TD-03 | Sprint 3 | Staging | `typing_indicator_erro error=''` — Evolution API retornou erro vazio no endpoint `/chat/sendPresence`. Investigar se endpoint requer formato diferente de `number` (com ou sem `@s.whatsapp.net`). | Baixa |
| TD-05 | Sprint 4 | Agents/Infra | **Retry Anthropic 529**: API retornou `overloaded_error` (529) duas vezes seguidas durante homologação; bot não respondeu. Implementar retry com exponential backoff (3 tentativas, delays 2s/4s/8s) nos 3 agentes antes do loop de tool use. Alta prioridade para produção. | Alta |
| TD-04 | Sprint 4 | Agents/UX | **Channel formatter**: hoje as restrições de formatação WhatsApp estão hardcoded nos system prompts dos 3 agentes. Quando Telegram (ou outro canal rico) for adicionado, criar uma camada fina em `src/agents/channel.py` com um `ChannelFormatter` que recebe `(texto: str, canal: Canal) -> str`. O agente gera saída "rica" (markdown completo), o formatter converte para o canal destino antes do envio. WhatsApp: tabela → bullets. Telegram: passa direto. Isso elimina a necessidade de manter variantes de system prompt por canal. Ver discussão de design em sprint 4. | Média |

## Resolvido

| ID | Sprint identificado | Sprint resolvido | Descrição |
|----|---------------------|-----------------|-----------|
| TD-01 | Sprint 1 | Sprint 2 (homologação) | mypy --strict: 66 erros de anotação de tipo. Corrigidos com `dict[str, Any]`, `-> None`, `isinstance` narrowing e remoção de `# type: ignore` desnecessários. `mypy --strict` agora retorna "Success: no issues found in 64 source files". |

---
Atualizado por: Claude | Último sprint: Sprint 4 | Data: 2026-04-20
