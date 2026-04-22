# Tech Debt Tracker — AI Sales Agent

Débitos técnicos identificados pelo Evaluator. Itens de Média que não
bloquearam aprovação mas devem ser endereçados.

## Aberto

| ID | Sprint | Domínio | Descrição | Prioridade |
|----|--------|---------|-----------|------------|
| TD-02 | Sprint 3 | Infra/Staging | `ANTHROPIC_API_KEY` sem monitoramento de saldo — chave esgotou silenciosamente em staging. Adicionar health check que valida saldo antes de iniciar homologação. | Média |
| TD-04 | Sprint 4 | Agents/UX | **Channel formatter**: hoje as restrições de formatação WhatsApp estão hardcoded nos system prompts dos 3 agentes. Quando Telegram (ou outro canal rico) for adicionado, criar uma camada fina em `src/agents/channel.py` com um `ChannelFormatter` que recebe `(texto: str, canal: Canal) -> str`. O agente gera saída "rica" (markdown completo), o formatter converte para o canal destino antes do envio. WhatsApp: tabela → bullets. Telegram: passa direto. Isso elimina a necessidade de manter variantes de system prompt por canal. Ver discussão de design em sprint 4. | Média |
| TD-06 | Hotfix v0.6.1 | Agents/UX | **Filtro por cliente em `listar_pedidos_por_status`**: gestor que pergunta "pedidos da LZ Muzel" recebe todos os pedidos e o LLM filtra visualmente. Adicionar parâmetro `cliente_nome: str \| None` à ferramenta e `WHERE ILIKE` condicional na query. | Baixa |

## Resolvido

| ID | Sprint identificado | Sprint resolvido | Descrição |
|----|---------------------|-----------------|-----------|
| TD-01 | Sprint 1 | Sprint 2 (homologação) | mypy --strict: 66 erros de anotação de tipo. Corrigidos com `dict[str, Any]`, `-> None`, `isinstance` narrowing e remoção de `# type: ignore` desnecessários. `mypy --strict` agora retorna "Success: no issues found in 64 source files". |
| TD-03 | Sprint 3 | Hotfix v0.6.1 (2026-04-21) | `typing_indicator_erro error=''` — abordagem inteira substituída por `show_typing_presence` context manager em `service.py`. Não emite `sendPresence` com `delay` — em vez disso faz pulse a cada 15s e emite `paused` explícito ao sair. Issues Evolution API #1639/#418 contornados. |
| TD-05 | Sprint 4 | Sprint 5 (commit `_retry.py`) | **Retry Anthropic 529**: implementado em `output/src/agents/_retry.py` com `call_with_overload_retry` (3 tentativas, backoff 2s/4s/8s). Todos os 3 agentes usam a função antes do loop de tool use. Verificado em auditoria 2026-04-21 — código presente e funcional. |
| TD-07 | Sprint 6 homologação | Observabilidade | **Langfuse sem traces do bot**: código de instrumentação `@observe()` escrito localmente no macmini em Sprint 5, perdido no `git checkout -f` do deploy do Sprint 6. Re-implementado no hotfix pós-Sprint 6: `@_lf_observe(name="processar_mensagem_*")` + `_lf_ctx.update_current_trace()` nos 3 agentes, com bloco condicional `LANGFUSE_ENABLED=false` para testes. `langfuse>=2.0.0` adicionado ao `pyproject.toml`. |

---
Atualizado por: Claude | Último sprint: Hotfix pós-Sprint 6 | Data: 2026-04-22
